import streamlit as st
from local_env import load_env_file

load_env_file()

import database
import pattern_engine
import backtest
import notifier
import analyst_engine
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Set Page Config
st.set_page_config(
    page_title="Candlestick Sentinel",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom premium CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', 'Outfit', sans-serif;
    }
    
    .main-title {
        font-size: 2.8rem;
        font-weight: 800;
        background: linear-gradient(135deg, #38bdf8 0%, #818cf8 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    
    .subtitle {
        color: #94a3b8;
        font-size: 1.1rem;
        margin-bottom: 2rem;
    }
    
    .card {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 24px;
        margin-bottom: 1.5rem;
    }
    
    .card-title {
        font-size: 1.3rem;
        font-weight: 700;
        color: #f8fafc;
        margin-bottom: 1rem;
    }
    
    .ticker-chip {
        display: inline-block;
        background-color: #334155;
        color: #f8fafc;
        font-weight: 600;
        padding: 4px 12px;
        border-radius: 9999px;
        margin-right: 8px;
        margin-bottom: 8px;
        border: 1px solid #475569;
    }
    
    .metric-value {
        font-size: 1.8rem;
        font-weight: 800;
        color: #38bdf8;
    }
    
    .metric-label {
        font-size: 0.9rem;
        color: #94a3b8;
    }
</style>
""", unsafe_allow_html=True)

# Main Application Router
def main():
    # Parse URL parameters
    query_params = st.query_params
    token = query_params.get("token")
    unsubscribe_flow = query_params.get("unsubscribe") == "true"
    
    # Store token in session state if accessed via link
    if token and "logged_in_token" not in st.session_state:
        st.session_state.logged_in_token = token
        
    # Check session state token
    session_token = st.session_state.get("logged_in_token")
    
    # ----------------------------------------------------
    # STATE 1: Unsubscribe Confirmation Flow
    # ----------------------------------------------------
    if session_token and unsubscribe_flow:
        render_unsubscribe_flow(session_token)
        return

    # ----------------------------------------------------
    # STATE 2: Management State (Valid token / session present)
    # ----------------------------------------------------
    if session_token:
        subscriber = database.get_subscriber_by_token(session_token)
        if subscriber:
            # Sync URL query params to keep access URL clean
            if query_params.get("token") != session_token:
                st.query_params.update(token=session_token)
            render_management_dashboard(subscriber, session_token)
            return
        else:
            st.error("Session expired or token invalid. Please log in again.")
            st.query_params.clear()
            if "logged_in_token" in st.session_state:
                del st.session_state.logged_in_token
            
    # ----------------------------------------------------
    # STATE 3: OTP Verification Screen
    # ----------------------------------------------------
    if st.session_state.get("auth_state") == "verify_otp":
        render_otp_verification_page()
        return
        
    # ----------------------------------------------------
    # STATE 4: Landing / Signup & Login state (or Stock Detail preview)
    # ----------------------------------------------------
    if st.session_state.get("selected_ticker_detail"):
        render_stock_detail_page(st.session_state.selected_ticker_detail, subscriber=None, token=None)
        return

    render_landing_page()

def render_landing_page():
    st.markdown('<div class="main-title">📈 Candlestick Sentinel</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Scans market setups, confirms reversals, and sends trade blueprints directly to your inbox.</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns([3, 2])
    
    with col1:
        st.markdown("""
        <div class="card">
            <div class="card-title">How It Works</div>
            <p style="color: #cbd5e1; font-size: 14px; line-height: 1.6;">
                Trading candlestick reversals without confirmation is a recipe for losses. Candlestick Sentinel enforces a rigid <strong>3-day data validation cycle</strong> to completely eliminate lookahead bias:
            </p>
            <ol style="color: #cbd5e1; font-size: 14px; line-height: 1.8; padding-left: 20px;">
                <li><strong>Day 1 (Setup):</strong> We scan watchlists for high-probability geometrical <strong>Hammer</strong> (bullish) and <strong>Hanging Man</strong> (bearish) reversal shapes.</li>
                <li><strong>Day 2 (Confirmation):</strong> We wait for the next day's close. A Hammer must close above Day 1's High; a Hanging Man must close below Day 1's Low. Unconfirmed patterns are immediately discarded.</li>
                <li><strong>Day 3 (Execution):</strong> At 9:31 AM EST, risk parameters are calculated using the live Opening price. If a gap has not invalidated the setup, a complete trade blueprint (Entry, Stop Loss, 2:1 Profit Target) is emailed to you.</li>
            </ol>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("### Featured Growth Ticklists")
        st.write("Click any stock button below to inspect live market data & technical indicators:")
        tickers_show = ["NVDA", "AMD", "PLTR", "RKLB", "SOFI", "MU"]
        cols = st.columns(len(tickers_show))
        for idx, tick in enumerate(tickers_show):
            with cols[idx]:
                if st.button(f"📈 {tick}", key=f"land_tick_{tick}", use_container_width=True):
                    st.session_state.selected_ticker_detail = tick
                    st.rerun()
                
    with col2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        
        tab_login, tab_register = st.tabs(["🔑 Sign In", "📝 Register"])
        
        # TAB: SIGN IN
        with tab_login:
            st.markdown("Enter your email to receive a secure 6-digit login code:")
            with st.form("login_form"):
                login_email = st.text_input("Email Address", key="login_email_input").strip().lower()
                login_submit = st.form_submit_button("Send Code")
                
                if login_submit:
                    if not login_email or "@" not in login_email:
                        st.error("Please enter a valid email address.")
                    else:
                        # Check if user exists
                        sub = database.get_subscriber_by_email(login_email)
                        if not sub:
                            st.error("This email is not registered yet. Please click the 'Register' tab to sign up first.")
                        else:
                            # Generate OTP
                            otp = database.generate_otp(login_email)
                            st.session_state.auth_state = "verify_otp"
                            st.session_state.auth_email = login_email
                            st.session_state.auth_otp_intercepted = otp
                            st.toast("Code generated!", icon="🔑")
                            st.rerun()
                            
        # TAB: REGISTER
        with tab_register:
            with st.form("register_form"):
                reg_email = st.text_input("Your Email Address", placeholder="e.g. investor@example.com").strip().lower()
                
                watchlist_input = st.text_area(
                    "Watchlist Tickers (comma-separated)",
                    value="NVDA, AMD, PLTR, RKLB, SOFI, MU",
                    placeholder="e.g. NVDA, AMD, PLTR"
                )
                
                st.write("**Alert Preferences**")
                wants_buys = st.checkbox("🟢 Buy Opportunities (Hammer Reversals)", value=True, key="reg_wants_buys")
                wants_risks = st.checkbox("🟡 Risk Alerts (Medium Score Hanging Man)", value=True, key="reg_wants_risks")
                wants_sells = st.checkbox("🔴 Sell Alerts (High Score Hanging Man)", value=True, key="reg_wants_sells")
                
                reg_submit = st.form_submit_button("Create Account & Send Code")
                
                if reg_submit:
                    if not reg_email or "@" not in reg_email:
                        st.error("Please enter a valid email address.")
                    else:
                        sub_check = database.get_subscriber_by_email(reg_email)
                        if sub_check:
                            st.info("You already have an account! Please go to the 'Sign In' tab to log in.")
                        else:
                            try:
                                tickers = [t.strip().upper() for t in watchlist_input.split(",") if t.strip()]
                                # Create subscriber profile
                                database.create_subscriber(
                                    email=reg_email,
                                    wants_buys=1 if wants_buys else 0,
                                    wants_risks=1 if wants_risks else 0,
                                    wants_sells=1 if wants_sells else 0,
                                    initial_tickers=tickers
                                )
                                # Generate OTP
                                otp = database.generate_otp(reg_email)
                                st.session_state.auth_state = "verify_otp"
                                st.session_state.auth_email = reg_email
                                st.session_state.auth_otp_intercepted = otp
                                st.toast("Verification code sent!", icon="✉️")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error creating account: {e}")
                                
        st.markdown('</div>', unsafe_allow_html=True)

def render_otp_verification_page():
    email = st.session_state.get("auth_email")
    otp_code = st.session_state.get("auth_otp_intercepted")
    
    st.markdown('<div class="main-title" style="text-align: center; margin-top: 50px;">✉️ Enter Verification Code</div>', unsafe_allow_html=True)
    
    st.markdown(f"""
    <div style="max-width: 500px; margin: 20px auto; padding: 24px; background-color: #1e293b; border: 1px solid #334155; border-radius: 12px;">
        <p style="color: #cbd5e1; font-size: 14px; line-height: 1.6; text-align: center;">
            We have generated a 6-digit verification code for <strong>{email}</strong>. Please enter the code below to sign in.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Local Test Notice displaying intercepted code
    st.markdown(f"""
    <div style="max-width: 500px; margin: 0 auto 20px auto; background-color: #1e1b4b; border: 1px solid #4338ca; border-radius: 8px; padding: 16px;">
        <span style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: #818cf8; display: block; margin-bottom: 4px;">🔧 Local Development Intercept</span>
        <p style="color: #c7d2fe; font-size: 13px; margin: 0;">
            Since this is running locally, the mock email was caught by our console. Your OTP code is: 
            <strong style="color: #a5b4fc; font-size: 16px; font-family: monospace; letter-spacing: 0.1em; margin-left: 6px;">{otp_code}</strong>
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    with st.form("otp_verification_form", clear_on_submit=True):
        code_input = st.text_input("6-Digit Verification Code", placeholder="e.g. 123456").strip()
        verify_btn = st.form_submit_button("Verify & Login")
        
        if verify_btn:
            if not code_input:
                st.error("Please enter the verification code.")
            else:
                token = database.verify_otp(email, code_input)
                if token:
                    st.session_state.logged_in_token = token
                    st.session_state.auth_state = None
                    st.session_state.auth_email = None
                    st.session_state.auth_otp_intercepted = None
                    st.query_params.update(token=token)
                    st.success("Verification successful! Logging you in...")
                    st.rerun()
                else:
                    st.error("Invalid, incorrect, or expired verification code. Please check your code or request a new one.")
                    
    if st.button("Cancel & Go Back"):
        st.session_state.auth_state = None
        st.session_state.auth_email = None
        st.session_state.auth_otp_intercepted = None
        st.rerun()

def render_unsubscribe_flow(token):
    subscriber = database.get_subscriber_by_token(token)
    
    st.markdown('<div class="main-title" style="text-align: center; margin-top: 50px;">🗑️ Unsubscribe Request</div>', unsafe_allow_html=True)
    
    if not subscriber:
        st.error("Invalid or expired token.")
        if st.button("Go to Homepage"):
            st.query_params.clear()
            if "logged_in_token" in st.session_state:
                del st.session_state.logged_in_token
            st.rerun()
        return
        
    st.markdown(f"""
    <div style="max-width: 500px; margin: 40px auto; padding: 24px; background-color: #1e293b; border: 1px solid #ef4444; border-radius: 12px; text-align: center;">
        <h3 style="color: #f8fafc; margin-top: 0;">Confirm Unsubscription</h3>
        <p style="color: #cbd5e1; font-size: 14px; line-height: 1.6;">
            Are you sure you want to completely delete your account for <strong>{subscriber['email']}</strong>? 
            This will permanently erase your preferences and watchlist.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("No, Keep Subscription", use_container_width=True):
            st.query_params.clear()
            st.query_params.update(token=token)
            st.rerun()
    with col2:
        if st.button("Yes, Unsubscribe Completely", type="primary", use_container_width=True):
            success = database.unsubscribe_subscriber(token)
            if success:
                st.success("You have been unsubscribed successfully.")
                st.query_params.clear()
                if "logged_in_token" in st.session_state:
                    del st.session_state.logged_in_token
                st.button("Back to Homepage", on_click=st.rerun)
            else:
                st.error("Error deleting your record. Please try again.")

def format_large_number(num):
    if num is None or pd.isna(num):
        return "n/a"
    try:
        num = float(num)
        if num >= 1e12:
            return f"${num / 1e12:.2f}T"
        elif num >= 1e9:
            return f"${num / 1e9:.2f}B"
        elif num >= 1e6:
            return f"${num / 1e6:.2f}M"
        elif num >= 1e3:
            return f"${num / 1e3:.2f}K"
        else:
            return f"${num:.2f}"
    except (TypeError, ValueError):
        return "n/a"

def format_exchange_name(info):
    full_name = info.get("fullExchangeName") or ""
    short_code = info.get("exchange") or ""
    
    if "Nasdaq" in full_name or short_code in ["NMS", "NCM", "NGS", "NAS"]:
        return "NASDAQ"
    elif "NYSE" in full_name or short_code in ["NYQ", "NYS"]:
        return "NYSE"
    elif "AMEX" in full_name or short_code in ["ASE"]:
        return "AMEX"
    elif "OTC" in full_name or short_code in ["PNK", "OQB", "QX"]:
        return "OTC"
    elif full_name:
        return full_name.upper()
    elif short_code:
        return short_code.upper()
    return "NASDAQ"

@st.cache_data(ttl=3600)
def get_company_short_name(ticker):
    try:
        info = yf.Ticker(ticker).info or {}
        return info.get("shortName") or info.get("longName") or ticker
    except Exception:
        return ticker

def render_plotly_stock_chart(ticker, timeframe, chart_style):
    tf_map = {
        "1D": ("1d", "5m"),
        "5D": ("5d", "15m"),
        "1M": ("1mo", "1d"),
        "3M": ("3mo", "1d"),
        "6M": ("6mo", "1d"),
        "YTD": ("ytd", "1d"),
        "1Y": ("1y", "1d"),
        "2Y": ("2y", "1d"),
        "5Y": ("5y", "1wk"),
        "Max": ("max", "1wk")
    }
    period, interval = tf_map.get(timeframe, ("1y", "1d"))
    
    try:
        data = yf.Ticker(ticker).history(period=period, interval=interval)
    except Exception:
        data = pd.DataFrame()
        
    if data.empty:
        st.info("Chart data not available for this timeframe.")
        return

    data = data.reset_index()
    start_price = float(data['Close'].iloc[0])
    current_price = float(data['Close'].iloc[-1])
    period_change = current_price - start_price
    period_pct = (period_change / start_price) * 100 if start_price != 0 else 0.0
    
    is_positive = period_change >= 0
    line_color = "#10b981" if is_positive else "#ef4444"
    fill_color = "rgba(16, 185, 129, 0.12)" if is_positive else "rgba(239, 68, 68, 0.12)"
    
    date_col = 'Datetime' if 'Datetime' in data.columns else 'Date'
    
    fig = go.Figure()
    
    if chart_style == "📈 Gradient Area":
        fig.add_trace(go.Scatter(
            x=data[date_col],
            y=data['Close'],
            mode='lines',
            line=dict(color=line_color, width=2),
            fill='tozeroy',
            fillcolor=fill_color,
            name='Close Price',
            hovertemplate='<b>%{x}</b><br>Price: <b>$%{y:.2f}</b><extra></extra>'
        ))
    else:
        fig.add_trace(go.Candlestick(
            x=data[date_col],
            open=data['Open'],
            high=data['High'],
            low=data['Low'],
            close=data['Close'],
            increasing_line_color='#10b981',
            decreasing_line_color='#ef4444',
            name='OHLC'
        ))
        
    # Baseline Reference Line (Period Start Price)
    fig.add_shape(
        type="line",
        x0=data[date_col].iloc[0],
        y0=start_price,
        x1=data[date_col].iloc[-1],
        y1=start_price,
        line=dict(color="#64748b", width=1, dash="dash")
    )
    
    # Current Price Tag Badge on Right Y-Axis
    fig.add_annotation(
        x=data[date_col].iloc[-1],
        y=current_price,
        text=f"${current_price:.2f}",
        showarrow=False,
        xanchor="left",
        yanchor="middle",
        bgcolor=line_color,
        font=dict(color="#ffffff", size=12, family="sans-serif"),
        borderpad=4
    )
    
    sign_str = "+" if period_change >= 0 else ""
    return_badge = f"{sign_str}{period_pct:.2f}% ({timeframe})"
    
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=60, t=30, b=10),
        height=400,
        xaxis=dict(
            showgrid=True,
            gridcolor="#1e293b",
            showline=False,
            zeroline=False
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="#1e293b",
            showline=False,
            zeroline=False,
            side="right"
        ),
        showlegend=False,
        title=dict(
            text=f"<span style='color:{line_color}; font-size:16px; font-weight:bold;'>{return_badge}</span>",
            x=0.98,
            xanchor="right",
            y=0.98
        )
    )
    
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

def render_stock_detail_page(ticker, subscriber, token):
    # Top Action Navigation Bar
    nav_col1, nav_col2 = st.columns([1, 1])
    with nav_col1:
        if st.button("⬅️ Back to Control Panel", use_container_width=False):
            st.session_state.selected_ticker_detail = None
            st.rerun()
            
    watchlist = database.get_watchlist(subscriber["id"]) if subscriber else []
    in_watchlist = ticker in watchlist
    with nav_col2:
        if subscriber:
            if in_watchlist:
                if st.button(f"🗑️ Remove {ticker} from Watchlist", key="btn_remove_detail"):
                    database.remove_watchlist_ticker(subscriber["id"], ticker)
                    st.toast(f"Removed {ticker} from watchlist.", icon="🗑️")
                    st.rerun()
            else:
                if st.button(f"➕ Add {ticker} to Watchlist", key="btn_add_detail", type="primary"):
                    database.add_watchlist_ticker(subscriber["id"], ticker)
                    st.toast(f"Added {ticker} to watchlist!", icon="⭐")
                    st.rerun()

    # Load Ticker Metadata & Historical Market Data
    with st.spinner(f"Downloading real-time financial statistics & chart for {ticker}..."):
        ticker_obj = yf.Ticker(ticker)
        try:
            info = ticker_obj.info or {}
        except Exception:
            info = {}
            
        df = pattern_engine.download_stock_data(ticker, period="2y")
        
    if df.empty or len(df) < 20:
        st.error(f"Could not load market data for ticker '{ticker}'. Please verify symbol.")
        return
        
    df = pattern_engine.add_indicators(df)
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    
    company_name = info.get("shortName") or info.get("longName") or ticker
    exchange = format_exchange_name(info)
    currency = info.get("currency") or "USD"
    
    latest_price = latest['Close']
    price_change = latest['Close'] - prev['Close']
    price_pct = (price_change / prev['Close']) * 100
    
    change_color = "#38df88" if price_change >= 0 else "#ef4444"
    change_sign = "+" if price_change >= 0 else ""
    
    latest_date_str = str(latest['Date'])[:10] if 'Date' in latest else "Latest Close"
    
    # 1. Big Header Banner (Matching User Screenshot Layout)
    st.markdown(f"""
    <div style="margin-top: 10px; margin-bottom: 20px;">
        <div style="display: flex; justify-content: space-between; align-items: flex-end;">
            <div>
                <h1 style="margin: 0; font-size: 2.3rem; font-weight: 800; color: #f8fafc; font-family: sans-serif;">{company_name} ({ticker})</h1>
                <span style="color: #94a3b8; font-size: 0.95rem; font-weight: 500;">{exchange}: {ticker} · Real-Time Price · {currency}</span>
            </div>
        </div>
        <div style="margin-top: 12px; display: flex; align-items: baseline; gap: 12px;">
            <span style="font-size: 3rem; font-weight: 800; color: #ffffff; letter-spacing: -0.02em;">${latest_price:.2f}</span>
            <span style="font-size: 1.5rem; font-weight: 700; color: {change_color};">{change_sign}${abs(price_change):.2f} ({change_sign}{price_pct:.2f}%)</span>
            <span style="color: #94a3b8; font-size: 0.85rem;">At close: {latest_date_str}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # --- ABOUT SECTION ---
    description = info.get("longBusinessSummary") or ""
    industry = info.get("industry") or "n/a"
    sector = info.get("sector") or "n/a"
    employees = info.get("fullTimeEmployees")
    website = info.get("website") or ""

    if description or industry != "n/a" or sector != "n/a":
        st.markdown('<div class="card" style="margin-bottom: 25px;">', unsafe_allow_html=True)
        st.markdown(f'<div class="card-title">About {company_name} ({ticker})</div>', unsafe_allow_html=True)
        
        col_about_text, col_about_meta = st.columns([3, 2])
        with col_about_text:
            if description:
                st.markdown(f"""
                <p style="color: #cbd5e1; font-size: 0.95rem; line-height: 1.6; margin-top: 5px;">
                    {description}
                </p>
                """, unsafe_allow_html=True)
        with col_about_meta:
            meta_rows = [
                ("Industry", industry),
                ("Sector", sector),
            ]
            if employees:
                meta_rows.append(("Employees", f"{employees:,}"))
            meta_rows.append(("Stock Exchange", exchange))
            meta_rows.append(("Ticker Symbol", ticker))
            if website:
                meta_rows.append(("Website", website))

            for label, val in meta_rows:
                if label == "Website":
                    st.markdown(f"""
                    <div style="display: flex; justify-content: space-between; border-bottom: 1px solid #334155; padding: 8px 0; font-size: 13px;">
                        <span style="color: #94a3b8; font-weight: 600;">{label}</span>
                        <a href="{val}" target="_blank" style="color: #60a5fa; font-weight: 700; text-decoration: none;">{val}</a>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div style="display: flex; justify-content: space-between; border-bottom: 1px solid #334155; padding: 8px 0; font-size: 13px;">
                        <span style="color: #94a3b8; font-weight: 600;">{label}</span>
                        <span style="color: #f8fafc; font-weight: 700;">{val}</span>
                    </div>
                    """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # 2. Main Page Layout Tabs
    tab_overview, tab_financials, tab_technicals, tab_signals, tab_backtest = st.tabs([
        " Overview", 
        "💰 Financial Performance",
        "📈 Technical Indicators", 
        "🔍 Pattern Signals", 
        "🧪 Strategy Backtest"
    ])
    
    # TAB 1: OVERVIEW (Matching User Screenshot Layout)
    with tab_overview:
        col_stats, col_chart = st.columns([2, 3])
        
        with col_stats:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="card-title">Key Statistics</div>', unsafe_allow_html=True)
            
            # Format Statistics
            market_cap_str = format_large_number(info.get("marketCap"))
            volume_str = f"{int(latest['Volume']):,}"
            open_str = f"${latest['Open']:.2f}"
            prev_close_str = f"${prev['Close']:.2f}"
            day_range_str = f"${latest['Low']:.2f} - ${latest['High']:.2f}"
            
            wk_low = info.get('fiftyTwoWeekLow') or df['Low'].min()
            wk_high = info.get('fiftyTwoWeekHigh') or df['High'].max()
            fifty_two_range = f"${wk_low:.2f} - ${wk_high:.2f}"
            
            pe_str = f"{info.get('trailingPE'):.2f}" if info.get('trailingPE') else "n/a"
            fwd_pe_str = f"{info.get('forwardPE'):.2f}" if info.get('forwardPE') else "n/a"
            beta_str = f"{info.get('beta'):.2f}" if info.get('beta') else "n/a"
            shares_out_str = format_large_number(info.get('sharesOutstanding'))
            
            rsi_val = latest['RSI_14']
            rsi_str = f"{rsi_val:.1f} ({'Oversold' if rsi_val < 30 else 'Overbought' if rsi_val > 70 else 'Neutral'})" if not pd.isna(rsi_val) else "n/a"
            sma_50_str = f"${latest['SMA_50']:.2f}" if not pd.isna(latest['SMA_50']) else "n/a"
            sma_200_str = f"${latest['SMA_200']:.2f}" if not pd.isna(latest['SMA_200']) else "n/a"
            
            stats_items = [
                ("Market Cap", market_cap_str, "Volume", volume_str),
                ("Open", open_str, "Previous Close", prev_close_str),
                ("Day's Range", day_range_str, "52-Week Range", fifty_two_range),
                ("PE Ratio", pe_str, "Forward PE", fwd_pe_str),
                ("Shares Out", shares_out_str, "Beta", beta_str),
                ("Wilder's RSI (14)", rsi_str, "50-Day SMA", sma_50_str),
                ("200-Day SMA", sma_200_str, "Volume MA (20)", f"{int(latest['Volume_MA_20']):,}" if not pd.isna(latest['Volume_MA_20']) else "n/a"),
            ]
            
            for label1, val1, label2, val2 in stats_items:
                st.markdown(f"""
                <div style="display: flex; justify-content: space-between; border-bottom: 1px solid #334155; padding: 10px 0; font-size: 13px;">
                    <div style="display: flex; justify-content: space-between; width: 48%;">
                        <span style="color: #94a3b8; font-weight: 500;">{label1}</span>
                        <span style="color: #f8fafc; font-weight: 700;">{val1}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; width: 48%;">
                        <span style="color: #94a3b8; font-weight: 500;">{label2}</span>
                        <span style="color: #f8fafc; font-weight: 700;">{val2}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
            st.markdown('</div>', unsafe_allow_html=True)
            
        with col_chart:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="card-title">Interactive Price Chart</div>', unsafe_allow_html=True)
            
            tcol1, tcol2 = st.columns([3, 1])
            with tcol1:
                tf = st.radio(
                    "Timeframe", 
                    ["1D", "5D", "1M", "3M", "6M", "YTD", "1Y", "2Y", "5Y", "Max"], 
                    index=2, 
                    horizontal=True, 
                    key="tf_select",
                    label_visibility="collapsed"
                )
            with tcol2:
                c_style = st.selectbox(
                    "Style", 
                    ["📈 Gradient Area", "📊 Candlesticks"], 
                    index=0, 
                    key="c_style_select",
                    label_visibility="collapsed"
                )
                
            render_plotly_stock_chart(ticker, tf, c_style)
            st.markdown('</div>', unsafe_allow_html=True)
    # TAB 2: FINANCIAL PERFORMANCE
    with tab_financials:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Financial Performance</div>', unsafe_allow_html=True)

        fin_view = st.radio("View", ["Annual", "Quarterly"], horizontal=True, key="fin_view_select")

        try:
            if fin_view == "Annual":
                income_stmt = ticker_obj.income_stmt
            else:
                income_stmt = ticker_obj.quarterly_income_stmt

            if income_stmt is not None and not income_stmt.empty:
                # Extract Revenue and Net Income rows
                revenue_row = None
                earnings_row = None

                for label in ["Total Revenue", "TotalRevenue", "Revenue"]:
                    if label in income_stmt.index:
                        revenue_row = income_stmt.loc[label]
                        break

                for label in ["Net Income", "NetIncome", "Net Income Common Stockholders"]:
                    if label in income_stmt.index:
                        earnings_row = income_stmt.loc[label]
                        break

                if revenue_row is not None or earnings_row is not None:
                    # Build a clean DataFrame for the chart
                    chart_dict = {}
                    if revenue_row is not None:
                        chart_dict["Revenue"] = revenue_row
                    if earnings_row is not None:
                        chart_dict["Earnings"] = earnings_row

                    fin_df = pd.DataFrame(chart_dict)
                    # Columns are dates - sort chronologically
                    fin_df.index = pd.to_datetime(fin_df.index)
                    fin_df = fin_df.sort_index()

                    if fin_view == "Annual":
                        fin_df.index = fin_df.index.strftime("%Y")
                    else:
                        fin_df.index = fin_df.index.strftime("%Y Q") + ((pd.to_datetime(fin_df.index).month - 1) // 3 + 1).astype(str)

                    st.bar_chart(fin_df)

                    # Show raw data table below chart
                    display_df = fin_df.copy()
                    for col in display_df.columns:
                        display_df[col] = display_df[col].apply(lambda x: format_large_number(x) if pd.notna(x) else "n/a")
                    st.table(display_df)
                else:
                    st.info(f"Revenue / Earnings data not available for {ticker}.")
            else:
                st.info(f"Financial statement data not available for {ticker}.")
        except Exception as e:
            st.warning(f"Could not load financial data: {e}")

        st.markdown('</div>', unsafe_allow_html=True)

    # TAB 3: TECHNICAL INDICATORS
    with tab_technicals:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Technical Moving Averages & RSI</div>', unsafe_allow_html=True)
        
        tech_chart_df = df.copy()
        if 'Date' in tech_chart_df.columns:
            tech_chart_df['Date_Str'] = tech_chart_df['Date'].astype(str).str[:10]
            tech_chart_df.set_index('Date_Str', inplace=True)
            
        st.write("**Price & Moving Averages (50-Day & 200-Day SMA)**")
        price_cols = [c for c in ['Close', 'SMA_50', 'SMA_200'] if c in tech_chart_df.columns]
        st.line_chart(tech_chart_df[price_cols])
        
        st.write("---")
        st.write("**Wilder's 14-Period RSI**")
        if 'RSI_14' in tech_chart_df.columns:
            st.line_chart(tech_chart_df[['RSI_14']])
            st.caption("RSI < 30 indicates Oversold / Reversal Support; RSI > 70 indicates Overbought / Extension.")
            
        st.markdown('</div>', unsafe_allow_html=True)
        
    # TAB 3: PATTERN SIGNALS
    with tab_signals:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Recent Candlestick Setup Reversals (Last 30 Days)</div>', unsafe_allow_html=True)
        
        with st.spinner("Scanning for recent setup candles..."):
            recent_signals = pattern_engine.scan_ticker_for_signals(ticker, days_to_scan=30)
            
        if not recent_signals:
            st.info(f"No Hammer or Hanging Man reversal setups detected for {ticker} over the last 30 trading days.")
        else:
            sig_display = []
            for s in recent_signals:
                sig_display.append({
                    "Setup Date": str(s["day1_date"])[:10],
                    "Pattern": s["pattern_type"],
                    "Confidence Score": f"{s['confidence_score']:.1f}/100",
                    "RSI (14)": f"{s['rsi_14']:.1f}",
                    "Volume Mult": f"{s['vol_mult']:.2f}x",
                    "Day 2 Confirmation": "✅ Confirmed" if s["confirmed"] else "❌ Unconfirmed",
                    "Day 3 Open": f"${s['day3_open']:.2f}" if s.get("day3_open") else "N/A"
                })
            st.table(pd.DataFrame(sig_display))
        st.markdown('</div>', unsafe_allow_html=True)

    # TAB 4: STRATEGY BACKTEST
    with tab_backtest:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(f'<div class="card-title">2-Year Strategy Backtest Performance for {ticker}</div>', unsafe_allow_html=True)
        
        with st.spinner(f"Simulating historical strategy execution for {ticker}..."):
            bt_res = backtest.run_backtest(ticker, period="2y")
            
        if bt_res["total_trades"] == 0:
            st.warning(f"No trades were triggered for {ticker} under strict 3-day confirmation rules in the last 2 years.")
        else:
            bc1, bc2, bc3, bc4 = st.columns(4)
            with bc1:
                st.markdown(f'<div class="metric-value">{bt_res["total_trades"]}</div>', unsafe_allow_html=True)
                st.markdown('<div class="metric-label">Total Trades</div>', unsafe_allow_html=True)
            with bc2:
                st.markdown(f'<div class="metric-value">{bt_res["win_rate"]:.2%}</div>', unsafe_allow_html=True)
                st.markdown('<div class="metric-label">Strategy Win Rate</div>', unsafe_allow_html=True)
            with bc3:
                st.markdown(f'<div class="metric-value">{bt_res["avg_return"]:.2%}</div>', unsafe_allow_html=True)
                st.markdown('<div class="metric-label">Average Return</div>', unsafe_allow_html=True)
            with bc4:
                st.markdown(f'<div class="metric-value">{bt_res["wins"]} W / {bt_res["losses"]} L</div>', unsafe_allow_html=True)
                st.markdown('<div class="metric-label">Win / Loss Ratio</div>', unsafe_allow_html=True)
                
            st.write("---")
            st.write("**Historical Strategy Trade Log (Zero Lookahead Bias)**")
            bt_df = pd.DataFrame(bt_res["trades"])
            if not bt_df.empty:
                bt_df["entry_price"] = bt_df["entry_price"].map(lambda x: f"${x:.2f}")
                bt_df["stop_loss"] = bt_df["stop_loss"].map(lambda x: f"${x:.2f}")
                bt_df["profit_target"] = bt_df["profit_target"].map(lambda x: f"${x:.2f}")
                bt_df["exit_price"] = bt_df["exit_price"].map(lambda x: f"${x:.2f}")
                bt_df["return"] = bt_df["return"].map(lambda x: f"{x:.2%}")
                
                bt_df.columns = [
                    "Setup Date", "Pattern", "Score", "Entry Date", "Entry Price",
                    "Stop Loss", "Profit Target", "Exit Date", "Exit Price", "Exit Reason", "Return"
                ]
                st.dataframe(bt_df, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

def render_management_dashboard(subscriber, token):
    if st.session_state.get("selected_ticker_detail"):
        render_stock_detail_page(st.session_state.selected_ticker_detail, subscriber, token)
        return

    st.markdown(f'<div class="main-title">🔧 Sentinel Control Panel</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="subtitle">Managing: <strong>{subscriber["email"]}</strong></div>', unsafe_allow_html=True)
    
    # Session state update functions
    def on_pref_change():
        database.update_subscriber_preferences(
            token,
            st.session_state.wants_buys_check,
            st.session_state.wants_risks_check,
            st.session_state.wants_sells_check
        )
        st.toast("Alert preferences updated and saved!", icon="💾")

    # Logout Function
    def logout():
        if "logged_in_token" in st.session_state:
            del st.session_state.logged_in_token
        st.query_params.clear()
        st.toast("Logged out successfully.", icon="🔓")
        st.rerun()

    # Sidebar details
    with st.sidebar:
        st.write(f"Logged in as:")
        st.markdown(f"**{subscriber['email']}**")
        st.write("---")
        st.write("🔗 **Personal Access Link**")
        st.markdown(f"<code style='font-size: 11px; word-break: break-all;'>http://localhost:8501/?token={token}</code>", unsafe_allow_html=True)
        st.write("Use this link to bypass the OTP login screen on this device.")
        st.write("---")
        st.button("🔓 Sign Out / Logout", on_click=logout, use_container_width=True)

    watchlist = database.get_watchlist(subscriber["id"])

    # 1. Clean Top Header
    st.markdown(f"""
    <div style="margin-top: 5px; margin-bottom: 20px;">
        <h1 style="margin: 0; font-size: 2.1rem; font-weight: 800; color: #f8fafc;">🔧 Sentinel Control Panel</h1>
        <span style="color: #94a3b8; font-size: 0.95rem;">Managing portfolio alerts for <strong style="color: #60a5fa;">{subscriber["email"]}</strong></span>
    </div>
    """, unsafe_allow_html=True)

    # 2. Top KPI Stat Badges Bar
    buys_active = "Buys" if subscriber["wants_buys"] else ""
    risks_active = "Risks" if subscriber["wants_risks"] else ""
    sells_active = "Sells" if subscriber["wants_sells"] else ""
    active_channels = ", ".join(filter(None, [buys_active, risks_active, sells_active])) or "None"

    kpi1, kpi2, kpi3 = st.columns(3)
    with kpi1:
        st.markdown(f"""
        <div class="card" style="padding: 16px; margin-bottom: 20px;">
            <span style="color: #94a3b8; font-size: 0.85rem; font-weight: 600;">MONITORED WATCHLIST</span>
            <div style="font-size: 1.8rem; font-weight: 800; color: #f8fafc; margin-top: 4px;">{len(watchlist)} Tickers</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi2:
        st.markdown(f"""
        <div class="card" style="padding: 16px; margin-bottom: 20px;">
            <span style="color: #94a3b8; font-size: 0.85rem; font-weight: 600;">ACTIVE ALERT CHANNELS</span>
            <div style="font-size: 1.4rem; font-weight: 700; color: #38df88; margin-top: 8px;">{active_channels}</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi3:
        st.markdown(f"""
        <div class="card" style="padding: 16px; margin-bottom: 20px;">
            <span style="color: #94a3b8; font-weight: 600; font-size: 0.85rem;">AI ANALYST ENGINE</span>
            <div style="font-size: 1.4rem; font-weight: 700; color: #60a5fa; margin-top: 8px;">Groq Llama 3.3-70B</div>
        </div>
        """, unsafe_allow_html=True)

    # Main Dashboard Tabs
    tab_watchlist, tab_scanner, tab_backtester, tab_settings = st.tabs([
        "📋 Watchlist", 
        "🔍 Live Scanner", 
        "🧪 Backtest Sandbox",
        "⚙️ Alert Settings"
    ])
    
    # ----------------------------------------------------
    # TAB 1: WATCHLIST GRID & QUICK ADD
    # ----------------------------------------------------
    with tab_watchlist:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Manage Watchlist</div>', unsafe_allow_html=True)
        
        # Simplified Inline Ticker Adder Bar
        with st.form("add_ticker_form_inline", clear_on_submit=True):
            fcol1, fcol2 = st.columns([4, 1])
            with fcol1:
                new_ticker = st.text_input("Add New Ticker", placeholder="Enter ticker symbol (e.g. AMD, NVDA, PLTR, TSLA)", label_visibility="collapsed").strip().upper()
            with fcol2:
                add_btn = st.form_submit_button("➕ Add Stock", type="primary", use_container_width=True)
                
            if add_btn:
                if not new_ticker:
                    st.error("Please enter a ticker symbol.")
                elif new_ticker in watchlist:
                    st.info(f"{new_ticker} is already in your watchlist.")
                else:
                    success = database.add_watchlist_ticker(subscriber["id"], new_ticker)
                    if success:
                        st.toast(f"Added {new_ticker} to watchlist!", icon="⭐")
                        st.rerun()
                    else:
                        st.error("Failed to add ticker.")
                        
        st.markdown('<div style="margin-top: 20px;"></div>', unsafe_allow_html=True)

        if not watchlist:
            st.warning("Your watchlist is currently empty. Add tickers above to start monitoring setups.")
            st.markdown("**Quick Add Suggestions:**")
            scol1, scol2, scol3, scol4 = st.columns(4)
            for col, sugg in zip([scol1, scol2, scol3, scol4], ["AMD", "NVDA", "PLTR", "TSLA"]):
                with col:
                    if st.button(f"➕ Add {sugg}", key=f"sugg_{sugg}", use_container_width=True):
                        database.add_watchlist_ticker(subscriber["id"], sugg)
                        st.rerun()
        else:
            st.write("Click any stock card to open full financial analysis, or click 🗑️ to remove:")
            
            # Stock Cards Grid (2 Tickers per Row)
            cols_per_row = 2
            for i in range(0, len(watchlist), cols_per_row):
                row_tickers = watchlist[i:i + cols_per_row]
                grid_cols = st.columns(cols_per_row)
                
                for idx, ticker in enumerate(row_tickers):
                    c_name = get_company_short_name(ticker)
                    with grid_cols[idx]:
                        st.markdown(f"""
                        <div style="background-color: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 14px; margin-bottom: 12px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; overflow: hidden; white-space: nowrap;">
                                <div style="overflow: hidden; text-overflow: ellipsis;">
                                    <span style="font-size: 1.25rem; font-weight: 800; color: #ffffff;">📈 {ticker}</span>
                                    <span style="color: #94a3b8; font-size: 0.9rem; font-weight: 600; margin-left: 6px;">· {c_name}</span>
                                </div>
                                <span style="color: #64748b; font-size: 0.75rem; font-weight: 600; margin-left: 8px;">US Equity</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        btn_col1, btn_col2 = st.columns([4, 1])
                        with btn_col1:
                            if st.button(f"Open {ticker} Analysis Page", key=f"view_card_{ticker}", type="primary", use_container_width=True):
                                st.session_state.selected_ticker_detail = ticker
                                st.rerun()
                        with btn_col2:
                            if st.button("🗑️", key=f"del_card_{ticker}", use_container_width=True):
                                database.remove_watchlist_ticker(subscriber["id"], ticker)
                                st.toast(f"Removed {ticker} from watchlist.", icon="🗑️")
                                st.rerun()
                                
        st.markdown('</div>', unsafe_allow_html=True)

    # ----------------------------------------------------
    # TAB 4: CONSOLIDATED ALERT SETTINGS
    # ----------------------------------------------------
    with tab_settings:
        col_set1, col_set2 = st.columns([1, 1])
        
        with col_set1:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="card-title">Alert Notification Preferences</div>', unsafe_allow_html=True)
            
            st.checkbox(
                "🟢 Buy Opportunities (Hammer Reversals)",
                value=bool(subscriber["wants_buys"]),
                key="wants_buys_check",
                on_change=on_pref_change
            )
            st.checkbox(
                "🟡 Medium Risk Alerts (Hanging Man Reversals)",
                value=bool(subscriber["wants_risks"]),
                key="wants_risks_check",
                on_change=on_pref_change
            )
            st.checkbox(
                "🔴 High Risk Sell Warnings (High-Volume Hanging Man)",
                value=bool(subscriber["wants_sells"]),
                key="wants_sells_check",
                on_change=on_pref_change
            )
            
            st.markdown('<p style="font-size: 13px; color: #94a3b8; margin-top: 15px;">Preferences update automatically in real-time when toggled.</p>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
        with col_set2:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="card-title">Email Delivery Tester</div>', unsafe_allow_html=True)
            st.write("Send a test alert email to your address:")
            
            test_btn = st.button("📧 Send Test Alert Email", use_container_width=True)
            if test_btn:
                mock_ticker = watchlist[0] if watchlist else "NVDA"
                mock_signal = {
                    "ticker": mock_ticker,
                    "pattern_type": "Hammer",
                    "confidence_score": 88.5,
                    "rsi_14": 28.2,
                    "vol_mult": 1.95,
                    "day1_date": "2026-06-05",
                    "day1_close": 120.0,
                    "day1_low": 115.0,
                    "day1_high": 121.0,
                    "day2_date": "2026-06-08",
                    "day2_close": 125.0
                }
                
                with st.spinner("Running Groq AI analyst check..."):
                    ai_analysis = analyst_engine.analyze_signal(mock_signal)
                if ai_analysis:
                    mock_signal["ai_analysis"] = ai_analysis
                email_html = notifier.format_alert_email(mock_signal, token)
                real_sent, status_msg = notifier.simulate_send_alert(subscriber["email"], email_html, mock_ticker)
                
                if real_sent:
                    st.success(f"✅ {status_msg}")
                else:
                    st.info(f"ℹ️ {status_msg}")
                    st.write("**Simulated Email Output:**")
                    st.components.v1.html(email_html, height=450, scrolling=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
            st.markdown('<div class="card" style="margin-top: 15px;">', unsafe_allow_html=True)
            st.markdown('<div class="card-title">Unsubscribe Account</div>', unsafe_allow_html=True)
            st.write("Erase all alert preferences and delete your watchlist:")
            if st.button("Unsubscribe Completely", type="primary", use_container_width=True):
                st.query_params.update(unsubscribe="true")
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
            
    # ----------------------------------------------------
    # TAB 2: LIVE SCANNER
    # ----------------------------------------------------
    with tab_scanner:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Live Watchlist Scanner (Last 10 Days)</div>', unsafe_allow_html=True)
        
        watchlist = database.get_watchlist(subscriber["id"])
        
        if not watchlist:
            st.info("Please add tickers to your watchlist under the 'Watchlist & Preferences' tab first.")
        else:
            scan_btn = st.button("Trigger Scan Now", type="primary")
            
            if scan_btn or "last_scan_results" in st.session_state:
                if scan_btn:
                    with st.spinner("Scanning tickers and pulling market data from Yahoo Finance..."):
                        all_signals = []
                        for ticker in watchlist:
                            signals = pattern_engine.scan_ticker_for_signals(ticker, days_to_scan=10)
                            all_signals.extend(signals)
                        st.session_state.last_scan_results = all_signals
                
                signals = st.session_state.get("last_scan_results", [])
                
                if not signals:
                    st.success("No active geometric setups identified on your watchlist over the last 10 trading days.")
                else:
                    st.write(f"Identified **{len(signals)}** pattern setups:")
                    
                    display_data = []
                    for s in signals:
                        display_data.append({
                            "Ticker": s["ticker"],
                            "Setup Date": s["day1_date"].strftime("%Y-%m-%d") if hasattr(s["day1_date"], "strftime") else str(s["day1_date"])[:10],
                            "Pattern": s["pattern_type"],
                            "Conf. Score": f"{s['confidence_score']:.1f}/100",
                            "RSI (14)": f"{s['rsi_14']:.1f}",
                            "Vol Mult": f"{s['vol_mult']:.2f}x",
                            "Confirmed": "✅ Yes" if s["confirmed"] else "❌ No"
                        })
                    
                    st.table(pd.DataFrame(display_data))
                    
                    st.write("### Preview Alert Email Layout")
                    st.write("Select a setup from the list below to inspect the generated beginner-friendly email layout sent to users:")
                    
                    selected_idx = st.selectbox(
                        "Select Signal to Preview",
                        options=list(range(len(signals))),
                        format_func=lambda i: (
                            f"{signals[i]['ticker']} - {signals[i]['pattern_type']} "
                            f"({signals[i]['day1_date'].strftime('%Y-%m-%d') if hasattr(signals[i]['day1_date'], 'strftime') else str(signals[i]['day1_date'])[:10]}) "
                            f"[Score: {signals[i]['confidence_score']:.1f}]"
                        )
                    )
                    selected_signal = signals[selected_idx]
                    
                    email_html = notifier.format_alert_email(selected_signal, token)
                    
                    st.markdown("""
                    <div style="background-color: #f1f5f9; padding: 20px; border-radius: 8px; border: 3px solid #cbd5e1;">
                        <div style="background-color: #ffffff; padding: 10px; border-bottom: 1px solid #e2e8f0; font-family: sans-serif; font-size: 13px; color: #475569; border-radius: 5px 5px 0 0;">
                            <strong>From:</strong> alerts@candlesticksentinel.com<br>
                            <strong>To:</strong> your-email@address.com<br>
                            <strong>Subject:</strong> Candlestick Sentinel Alert: Market action for ticker
                        </div>
                    """, unsafe_allow_html=True)
                    
                    st.components.v1.html(email_html, height=580, scrolling=True)
                    st.markdown("</div>", unsafe_allow_html=True)
                    
        st.markdown('</div>', unsafe_allow_html=True)

    # ----------------------------------------------------
    # TAB 3: BACKTESTER SANDBOX
    # ----------------------------------------------------
    with tab_backtester:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Historical Backtester Sandbox</div>', unsafe_allow_html=True)
        
        st.write("Run historical simulations of the **3-day rigid trading strategy** to verify how a ticker performed over a 2-year window:")
        
        watchlist = database.get_watchlist(subscriber["id"])
        default_ticker = watchlist[0] if watchlist else "NVDA"
        
        backtest_ticker = st.text_input("Enter Ticker to Backtest", value=default_ticker).strip().upper()
        
        bt_btn = st.button("Run Simulation", type="primary")
        if bt_btn:
            if not backtest_ticker:
                st.error("Please enter a valid ticker symbol.")
            else:
                with st.spinner(f"Simulating strategy for {backtest_ticker}..."):
                    res = backtest.run_backtest(backtest_ticker, period="2y")
                    
                    if res["total_trades"] == 0:
                        st.warning(f"No trades were triggered for {backtest_ticker} under our strict confirmation rules in the last 2 years.")
                    else:
                        col_bt1, col_bt2, col_bt3, col_bt4 = st.columns(4)
                        with col_bt1:
                            st.markdown(f'<div class="metric-value">{res["total_trades"]}</div>', unsafe_allow_html=True)
                            st.markdown('<div class="metric-label">Total Trades</div>', unsafe_allow_html=True)
                        with col_bt2:
                            st.markdown(f'<div class="metric-value">{res["win_rate"]:.2%}</div>', unsafe_allow_html=True)
                            st.markdown('<div class="metric-label">Strategy Win Rate</div>', unsafe_allow_html=True)
                        with col_bt3:
                            st.markdown(f'<div class="metric-value">{res["avg_return"]:.2%}</div>', unsafe_allow_html=True)
                            st.markdown('<div class="metric-label">Average Return per Trade</div>', unsafe_allow_html=True)
                        with col_bt4:
                            st.markdown(f'<div class="metric-value">{res["wins"]} W / {res["losses"]} L</div>', unsafe_allow_html=True)
                            st.markdown('<div class="metric-label">Win/Loss Ratio</div>', unsafe_allow_html=True)
                            
                        st.write("### Simulation Trade Logs (No Lookahead Bias)")
                        
                        trade_df = pd.DataFrame(res["trades"])
                        
                        trade_df["entry_price"] = trade_df["entry_price"].map(lambda x: f"${x:.2f}")
                        trade_df["stop_loss"] = trade_df["stop_loss"].map(lambda x: f"${x:.2f}")
                        trade_df["profit_target"] = trade_df["profit_target"].map(lambda x: f"${x:.2f}")
                        trade_df["exit_price"] = trade_df["exit_price"].map(lambda x: f"${x:.2f}")
                        trade_df["return"] = trade_df["return"].map(lambda x: f"{x:.2%}")
                        
                        trade_df.columns = [
                            "Setup Date", "Pattern", "Score", "Entry Date", "Entry Price", 
                            "Stop Loss", "Profit Target", "Exit Date", "Exit Price", "Exit Reason", "Return"
                        ]
                        
                        st.dataframe(trade_df, use_container_width=True)
                        
        st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
