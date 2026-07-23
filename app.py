from datetime import timedelta
from datetime import datetime
import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import logging
import threading
import time

from core.local_env import load_env_file
load_env_file()

from core import database
from engines import pattern_engine, growth_engine, backtest
from ai import analyst_engine
from notifications import notifier
from scanners import daily_scanner, growth_scanner

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Set Page Config
st.set_page_config(
    page_title="Candlestick Sentinel",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)


# Background Auto-Scheduler Daemon Thread Setup
_scheduler_thread = None

def parse_dt(ts_str):
    if not ts_str:
        return None
    for fmt in ("%Y-%m-%d %I:%M:%S %p", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(ts_str, fmt)
        except Exception:
            pass
    return None

def _should_trigger_market_slot_scan(last_run_str):
    """
    Determines if a scheduled scan should trigger based on market wall-clock schedule:
    - Slot 1: Pre-Market Preparation & Blueprint Delivery (9:00 AM EST)
    - Slot 2: Post-Market Settlement & After-Hours News (4:30 PM EST)
    """
    now = datetime.now()
    last_dt = parse_dt(last_run_str)
    
    if not last_dt:
        return True  # If never run, run initial scan immediately on activation
        
    today_slot1 = datetime(now.year, now.month, now.day, 9, 0)
    today_slot2 = datetime(now.year, now.month, now.day, 16, 30)
    
    # Trigger 4:30 PM evening slot if now >= 4:30 PM and last run was prior to 4:30 PM today
    if now >= today_slot2 and last_dt < today_slot2:
        return True
        
    # Trigger 9:00 AM morning slot if now >= 9:00 AM and last run was prior to 9:00 AM today
    if now >= today_slot1 and last_dt < today_slot1:
        return True
        
    return False

def _run_background_scheduler_loop():
    while True:
        try:
            state = database.get_scheduler_state()
            if state:
                # 1. Candlestick Technical Auto-Scheduler (Market Schedule: 9:00 AM & 4:30 PM EST)
                if state.get("is_active"):
                    last_run = state.get("last_run_timestamp")
                    if _should_trigger_market_slot_scan(last_run):
                        logging.info("⏰ Triggering Scheduled Technical Reversal Scan (Market Schedule: 9:00 AM / 4:30 PM EST)")
                        daily_scanner.run_daily_scan(days_to_scan=3, trigger_type="scheduled")

                # 2. AI Growth Catalyst Auto-Scheduler (Market Schedule: 9:00 AM & 4:30 PM EST)
                if state.get("growth_is_active"):
                    g_last_run = state.get("growth_last_run_timestamp")
                    if _should_trigger_market_slot_scan(g_last_run):
                        logging.info("⏰ Triggering Scheduled AI Growth Catalyst Scan (Market Schedule: 9:00 AM / 4:30 PM EST)")
                        growth_scanner.run_growth_scan(trigger_type="scheduled")

        except Exception as e:
            logging.error(f"Error in background scheduler loop: {e}")
        time.sleep(60)


def init_scheduler_daemon():
    global _scheduler_thread
    if _scheduler_thread is None or not _scheduler_thread.is_alive():
        _scheduler_thread = threading.Thread(target=_run_background_scheduler_loop, daemon=True)
        _scheduler_thread.start()
        logging.info("Auto-Scheduler background daemon thread initialized.")

init_scheduler_daemon()

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
    
    /* Premium Ocean Blue Buttons & Tabs Palette */
    button[kind="primary"] {
        background: linear-gradient(135deg, #2563eb 0%, #3b82f6 100%) !important;
        border: none !important;
        color: #ffffff !important;
        font-weight: 600 !important;
        border-radius: 8px !important;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.25) !important;
        transition: all 0.2s ease !important;
    }
    button[kind="primary"]:hover {
        background: linear-gradient(135deg, #1d4ed8 0%, #2563eb 100%) !important;
        box-shadow: 0 6px 16px rgba(37, 99, 235, 0.4) !important;
        transform: translateY(-1px) !important;
    }
    
    button[kind="secondary"] {
        background: #1e293b !important;
        border: 1px solid #334155 !important;
        color: #f8fafc !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        transition: all 0.2s ease !important;
    }
    button[kind="secondary"]:hover {
        border-color: #3b82f6 !important;
        color: #60a5fa !important;
        background: #334155 !important;
    }

    [data-baseweb="tab-highlight"] {
        background-color: #38bdf8 !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #38bdf8 !important;
        font-weight: 700 !important;
    }

    /* Remove empty background containers & tab panel borders */
    [data-baseweb="tab-panel"] {
        padding-top: 15px !important;
        background: transparent !important;
        border: none !important;
    }
    .stTabs [data-baseweb="tab-border"] {
        display: none !important;
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

@st.cache_data(ttl=86400)
def get_company_logo_url(ticker):
    try:
        info = yf.Ticker(ticker).info or {}
        website = info.get("website", "")
        if website:
            domain = website.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
            return f"https://www.google.com/s2/favicons?domain={domain}&sz=64"
    except Exception:
        pass
    return f"https://financialmodelingprep.com/image-stock/{ticker}.png"

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
    
    # 2-Row Subplot: Price (75%) + Volume (25%)
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.75, 0.25]
    )
    
    # 1. Price Panel (Row 1)
    if chart_style == "📈 Gradient Area":
        fig.add_trace(go.Scatter(
            x=data[date_col],
            y=data['Close'],
            mode='lines',
            line=dict(color=line_color, width=2),
            fill='tozeroy',
            fillcolor=fill_color,
            name='Price',
            hovertemplate='<b>%{x}</b><br>Price: <b>$%{y:.2f}</b><extra></extra>'
        ), row=1, col=1)
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
        ), row=1, col=1)
        
    # Baseline Reference Line (Period Start Price)
    fig.add_shape(
        type="line",
        x0=data[date_col].iloc[0],
        y0=start_price,
        x1=data[date_col].iloc[-1],
        y1=start_price,
        line=dict(color="#64748b", width=1, dash="dash"),
        row=1, col=1
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
        font=dict(color="#ffffff", size=11, family="sans-serif"),
        borderpad=3,
        row=1, col=1
    )
    
    # 2. Volume Panel (Row 2)
    vol_colors = []
    for i in range(len(data)):
        if i == 0:
            vol_colors.append("rgba(16, 185, 129, 0.5)")
        else:
            if data['Close'].iloc[i] >= data['Close'].iloc[i-1]:
                vol_colors.append("rgba(16, 185, 129, 0.5)") # Green bar
            else:
                vol_colors.append("rgba(239, 68, 68, 0.5)")  # Red bar
                
    fig.add_trace(go.Bar(
        x=data[date_col],
        y=data['Volume'],
        marker_color=vol_colors,
        name='Volume',
        hovertemplate='Volume: <b>%{y:,.0f}</b><extra></extra>'
    ), row=2, col=1)
    
    sign_str = "+" if period_change >= 0 else ""
    return_badge = f"{sign_str}{period_pct:.2f}% ({timeframe})"
    
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=60, t=30, b=10),
        height=440,
        xaxis=dict(showgrid=False, rangeslider=dict(visible=False)),
        xaxis2=dict(showgrid=True, gridcolor="#1e293b"),
        yaxis=dict(showgrid=True, gridcolor="#1e293b", side="right"),
        yaxis2=dict(showgrid=False, side="right"),
        showlegend=False,
        title=dict(
            text=f"<span style='color:{line_color}; font-size:15px; font-weight:bold;'>{return_badge}</span>",
            x=0.98,
            xanchor="right",
            y=0.98
        )
    )
    
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

def _render_stock_body(ticker, subscriber, token):
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
    now_time_str = datetime.now().strftime("%I:%M:%S %p EST")
    
    # 1. Big Header Banner (Matching User Screenshot Layout)
    st.markdown(f"""
    <div style="margin-top: 10px; margin-bottom: 20px;">
        <div style="display: flex; justify-content: space-between; align-items: flex-end;">
            <div>
                <h1 style="margin: 0; font-size: 2.3rem; font-weight: 800; color: #f8fafc; font-family: sans-serif;">{company_name} ({ticker})</h1>
                <span style="color: #94a3b8; font-size: 0.95rem; font-weight: 500;">{exchange}: {ticker} · Live Price Quote · {currency}</span>
            </div>
            <div style="text-align: right;">
                <span style="display: inline-block; background-color: #0f172a; color: #38bdf8; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 9999px; border: 1px solid #1e293b;">
                    🟢 Live Updated at {now_time_str}
                </span>
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

        fin_view = st.radio("View", ["Annual", "Quarterly", "TTM"], horizontal=True, key="fin_view_select")

        try:
            if fin_view in ["Annual", "TTM"]:
                stmt = ticker_obj.income_stmt
                q_stmt = ticker_obj.quarterly_income_stmt
            else:
                stmt = ticker_obj.quarterly_income_stmt

            if stmt is not None and not stmt.empty:
                # Find Revenue and Net Income rows
                revenue_row = None
                earnings_row = None

                for label in ["Total Revenue", "Operating Revenue", "Revenue"]:
                    if label in stmt.index:
                        revenue_row = stmt.loc[label]
                        break

                for label in ["Net Income", "Net Income Common Stockholders", "Net Income Continuous Operations"]:
                    if label in stmt.index:
                        earnings_row = stmt.loc[label]
                        break

                if revenue_row is not None or earnings_row is not None:
                    chart_dict = {}
                    if revenue_row is not None:
                        chart_dict["Revenue"] = revenue_row
                    if earnings_row is not None:
                        chart_dict["Earnings"] = earnings_row

                    fin_df = pd.DataFrame(chart_dict)
                    fin_df.index = pd.to_datetime(fin_df.index)
                    fin_df = fin_df.sort_index()

                    if fin_view == "Annual":
                        fin_df.index = fin_df.index.strftime("%Y")
                    elif fin_view == "Quarterly":
                        fin_df.index = fin_df.index.strftime("%Y Q") + ((fin_df.index.month - 1) // 3 + 1).astype(str)
                    elif fin_view == "TTM":
                        # Compute Trailing Twelve Months (TTM)
                        if q_stmt is not None and not q_stmt.empty:
                            q_rev = q_stmt.loc[revenue_row.name] if revenue_row.name in q_stmt.index else None
                            q_net = q_stmt.loc[earnings_row.name] if earnings_row.name in q_stmt.index else None
                            
                            ttm_rev = q_rev.iloc[:4].sum() if q_rev is not None and len(q_rev) >= 4 else (revenue_row.iloc[0] if revenue_row is not None else 0)
                            ttm_net = q_net.iloc[:4].sum() if q_net is not None and len(q_net) >= 4 else (earnings_row.iloc[0] if earnings_row is not None else 0)
                            
                            fin_df = pd.DataFrame({
                                "Revenue": [ttm_rev],
                                "Earnings": [ttm_net]
                            }, index=["TTM (Trailing 12 Mo)"])
                        else:
                            fin_df.index = fin_df.index.strftime("%Y")

                    # 1. Generate Executive Narrative Summary Text (Matching Screenshot)
                    if len(fin_df) > 0:
                        latest_period = fin_df.index[-1]
                        latest_rev = fin_df["Revenue"].iloc[-1] if "Revenue" in fin_df.columns else 0
                        latest_net = fin_df["Earnings"].iloc[-1] if "Earnings" in fin_df.columns else 0

                        rev_str = format_large_number(latest_rev)
                        is_loss = latest_net < 0
                        net_label = "losses were" if is_loss else "net income was"
                        net_str = format_large_number(abs(latest_net))
                        if is_loss:
                            net_str = f"-{net_str}"

                        summary_text = f"In {latest_period}, **{company_name}** recorded revenue of **{rev_str}**."

                        if len(fin_df) >= 2:
                            prev_period = fin_df.index[-2]
                            prev_rev = fin_df["Revenue"].iloc[-2] if "Revenue" in fin_df.columns else 0
                            prev_net = fin_df["Earnings"].iloc[-2] if "Earnings" in fin_df.columns else 0

                            if prev_rev and prev_rev != 0:
                                rev_pct = ((latest_rev - prev_rev) / abs(prev_rev)) * 100
                                rev_dir = "an increase" if rev_pct >= 0 else "a decrease"
                                summary_text += f" This represents {rev_dir} of **{abs(rev_pct):.2f}%** compared to {prev_period}'s {format_large_number(prev_rev)}."

                            if prev_net and prev_net != 0:
                                net_pct = ((latest_net - prev_net) / abs(prev_net)) * 100
                                net_dir = "higher" if net_pct >= 0 else "lower"
                                summary_text += f" {net_label.capitalize()} **{net_str}** ({abs(net_pct):.2f}% {net_dir} than {prev_period})."
                            else:
                                summary_text += f" {net_label.capitalize()} **{net_str}**."

                        st.markdown(f"""
                        <div style="background-color: #1e293b; border-left: 4px solid #38bdf8; padding: 14px; border-radius: 4px; margin-bottom: 20px; color: #cbd5e1; font-size: 0.95rem; line-height: 1.6;">
                            {summary_text}
                        </div>
                        """, unsafe_allow_html=True)

                    # 2. Plotly Grouped Bar Chart (Matching Screenshot Style)
                    fig_fin = go.Figure()
                    
                    if "Revenue" in fin_df.columns:
                        fig_fin.add_trace(go.Bar(
                            x=list(fin_df.index),
                            y=fin_df["Revenue"],
                            name="Revenue",
                            marker_color="#2563eb",
                            hovertemplate="%{x}<br>Revenue: <b>$%{y:,.0f}</b><extra></extra>"
                        ))
                    if "Earnings" in fin_df.columns:
                        fig_fin.add_trace(go.Bar(
                            x=list(fin_df.index),
                            y=fin_df["Earnings"],
                            name="Earnings",
                            marker_color="#f87171",
                            hovertemplate="%{x}<br>Earnings: <b>$%{y:,.0f}</b><extra></extra>"
                        ))

                    fig_fin.update_layout(
                        barmode="group",
                        template="plotly_dark",
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        margin=dict(l=10, r=20, t=30, b=10),
                        height=360,
                        legend=dict(
                            orientation="h",
                            yanchor="bottom",
                            y=1.02,
                            xanchor="left",
                            x=0
                        ),
                        xaxis=dict(showgrid=False),
                        yaxis=dict(showgrid=True, gridcolor="#334155", side="right")
                    )

                    st.plotly_chart(fig_fin, use_container_width=True, config={'displayModeBar': False})

                    # 3. Formatted Table View Below Chart
                    st.write("**Financial Statements Data Breakdown**")
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
        st.markdown('</div>', unsafe_allow_html=True)

def render_stock_detail_page(ticker, subscriber, token, show_back_button=True):
    # Top Action Navigation & Refresh Bar
    if show_back_button:
        nav_col1, nav_col2, nav_col3, nav_col4 = st.columns([2, 2, 3, 2])
        with nav_col1:
            if st.button("⬅️ Back to Control Panel", use_container_width=True):
                st.session_state.selected_ticker_detail = None
                st.rerun()
    else:
        nav_col2, nav_col3, nav_col4 = st.columns([2, 3, 2])

    with nav_col2:
        if st.button("🔄 Refresh Quote Now", use_container_width=True, key=f"btn_manual_refresh_{ticker}"):
            st.toast(f"Refreshed live data for {ticker}!", icon="🔄")
            st.rerun()

    with nav_col3:
        refresh_mode = st.selectbox(
            "Auto Refresh Rate",
            ["⏱️ Auto-Refresh: 30s (Rec.)", "⚡ Auto-Refresh: 15s (Fast)", "⏳ Auto-Refresh: 60s", "🛑 Auto-Refresh: Off"],
            key=f"auto_refresh_select_{ticker}",
            label_visibility="collapsed"
        )

    watchlist = database.get_watchlist(subscriber["id"]) if subscriber else []
    in_watchlist = ticker in watchlist
    with nav_col4:
        if subscriber:
            if in_watchlist:
                if st.button("🗑️ Remove Watchlist", key=f"btn_remove_detail_{ticker}", use_container_width=True):
                    database.remove_watchlist_ticker(subscriber["id"], ticker)
                    st.toast(f"Removed {ticker} from watchlist.", icon="🗑️")
                    st.rerun()
            else:
                if st.button("➕ Add Watchlist", key=f"btn_add_detail_{ticker}", type="primary", use_container_width=True):
                    database.add_watchlist_ticker(subscriber["id"], ticker)
                    st.toast(f"Added {ticker} to watchlist!", icon="⭐")
                    st.rerun()


    # Route auto-refresh interval based on dropdown selection
    if "15s" in refresh_mode:
        @st.fragment(run_every=15)
        def _draw_15():
            _render_stock_body(ticker, subscriber, token)
        _draw_15()
    elif "30s" in refresh_mode:
        @st.fragment(run_every=30)
        def _draw_30():
            _render_stock_body(ticker, subscriber, token)
        _draw_30()
    elif "60s" in refresh_mode:
        @st.fragment(run_every=60)
        def _draw_60():
            _render_stock_body(ticker, subscriber, token)
        _draw_60()
    else:
        _render_stock_body(ticker, subscriber, token)

def render_management_dashboard(subscriber, token):

    if st.session_state.get("selected_ticker_detail"):
        render_stock_detail_page(st.session_state.selected_ticker_detail, subscriber, token)
        return

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

    # Render pending notification banner if present
    if st.session_state.get("pending_toast"):
        st.success(f"✅ {st.session_state.pending_toast}")
        st.toast(st.session_state.pending_toast, icon="⭐")
        st.session_state.pending_toast = None

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

    # Main Dashboard Tabs (Clean 3-Tab Layout)
    tab_watchlist, tab_search, tab_hub = st.tabs([
        "📋 Watchlist", 
        "🔍 Stock Search & Deep-Dive",
        "⚡ Scanner, Alerts & Backtesting"
    ])
    
    # ----------------------------------------------------
    # TAB 1: WATCHLIST GRID & QUICK ADD
    # ----------------------------------------------------
    with tab_watchlist:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">Manage Watchlist</div>', unsafe_allow_html=True)
        
        # Universal Free-Text Ticker Input with Dual Action Buttons (Analyze or Add)
        with st.form("add_ticker_form_universal", clear_on_submit=False):
            fcol1, fcol2, fcol3 = st.columns([3, 1, 1])
            with fcol1:
                new_ticker_input = st.text_input(
                    "Add Ticker Symbol",
                    placeholder="Type ANY ticker symbol (e.g. SIRI, AMD, NVDA, PLTR, BABA)...",
                    label_visibility="collapsed",
                    key="wl_form_ticker_input"
                ).strip().upper()
            with fcol2:
                analyze_btn = st.form_submit_button("🔍 Analyze", use_container_width=True)
            with fcol3:
                add_btn = st.form_submit_button("➕ Add Stock", type="primary", use_container_width=True)

            if analyze_btn:
                target_symbol = new_ticker_input.split(" ")[0].split("-")[0].strip().upper()
                if not target_symbol:
                    st.error("Please enter a ticker symbol to analyze.")
                else:
                    st.session_state.selected_ticker_detail = target_symbol
                    st.session_state.search_tab_ticker = None
                    st.rerun()

            if add_btn:
                target_symbol = new_ticker_input.split(" ")[0].split("-")[0].strip().upper()
                if not target_symbol:
                    st.error("Please enter a ticker symbol.")
                elif target_symbol in watchlist:
                    st.info(f"{target_symbol} is already in your watchlist.")
                else:
                    success = database.add_watchlist_ticker(subscriber["id"], target_symbol)
                    if success:
                        st.session_state.pending_toast = f"Added {target_symbol} to your Watchlist!"
                        st.rerun()
                    else:
                        st.error("Failed to add ticker.")

        st.markdown('<div style="margin-top: 15px;"></div>', unsafe_allow_html=True)

        if not watchlist:
            st.warning("Your watchlist is currently empty. Add tickers above to start monitoring setups.")
            st.markdown("**Quick Add Suggestions:**")
            scol1, scol2, scol3, scol4 = st.columns(4)
            for col, sugg in zip([scol1, scol2, scol3, scol4], ["AMD", "NVDA", "PLTR", "TSLA"]):
                with col:
                    if st.button(f"➕ Add {sugg}", key=f"sugg_{sugg}", use_container_width=True):
                        database.add_watchlist_ticker(subscriber["id"], sugg)
                        st.session_state.pending_toast = f"Added {sugg} to your Watchlist!"
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
                    c_logo = get_company_logo_url(ticker)
                    with grid_cols[idx]:
                        st.markdown(f"""
                        <div style="background-color: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 14px; margin-bottom: 12px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; overflow: hidden; white-space: nowrap;">
                                <div style="display: flex; align-items: center; overflow: hidden; text-overflow: ellipsis;">
                                    <img src="{c_logo}" style="width: 22px; height: 22px; border-radius: 4px; object-fit: contain; margin-right: 8px; background-color: #0f172a; padding: 2px;">
                                    <span style="font-size: 1.2rem; font-weight: 800; color: #ffffff;">{ticker}</span>
                                    <span style="color: #94a3b8; font-size: 0.9rem; font-weight: 600; margin-left: 6px; overflow: hidden; text-overflow: ellipsis;">· {c_name}</span>
                                </div>
                                <span style="color: #64748b; font-size: 0.75rem; font-weight: 600; margin-left: 8px;">US Equity</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        btn_col1, btn_col2 = st.columns([4, 1])
                        with btn_col1:
                            if st.button(f"Open {ticker} Analysis Page", key=f"view_card_{ticker}", type="primary", use_container_width=True):
                                st.session_state.selected_ticker_detail = ticker
                                st.session_state.search_tab_ticker = None
                                st.rerun()

                        with btn_col2:
                            if st.button("🗑️", key=f"del_card_{ticker}", use_container_width=True):
                                database.remove_watchlist_ticker(subscriber["id"], ticker)
                                st.session_state.pending_toast = f"Removed {ticker} from your Watchlist."
                                st.rerun()
                                
        st.markdown('</div>', unsafe_allow_html=True)

    # ----------------------------------------------------
    # TAB 2: INSTANT STOCK SEARCH & DEEP-DIVE ANALYSIS
    # ----------------------------------------------------
    with tab_search:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">🔍 Search Any Stock for Instant Deep-Dive Analysis</div>', unsafe_allow_html=True)
        st.write("Perform comprehensive financial, indicator, and technical backtest analysis on any US stock ticker instantly (no watchlist required):")
        
        with st.form("search_ticker_form_tab", clear_on_submit=True):
            scol1, scol2, scol3 = st.columns([3, 1, 1])
            with scol1:
                search_symbol_input = st.text_input(
                    "Search Ticker Symbol",
                    placeholder="Type ANY ticker symbol (e.g. NVDA, AMD, PLTR, BABA, TSLA, AAPL)...",
                    label_visibility="collapsed",
                    key="search_tab_ticker_input_field"
                ).strip().upper()
            with scol2:
                search_submit = st.form_submit_button("🔍 Search & Analyze", type="primary", use_container_width=True)
            with scol3:
                clear_submit = st.form_submit_button("❌ Clear Search", use_container_width=True)

            if search_submit:
                clean_search = search_symbol_input.split(" ")[0].split("-")[0].strip().upper()
                if not clean_search:
                    st.error("Please enter a ticker symbol to search.")
                else:
                    st.session_state.search_tab_ticker = clean_search
                    st.rerun()

            if clear_submit:
                st.session_state.search_tab_ticker = None
                st.rerun()



        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('<div style="margin-top: 15px;"></div>', unsafe_allow_html=True)

        active_search_ticker = st.session_state.get("search_tab_ticker")
        if not active_search_ticker:
            st.info("💡 Enter any ticker symbol above (e.g. `NVDA`, `AMD`, `PLTR`, `AAPL`) and click 'Search & Analyze' to open its interactive analysis page.")
        else:
            # Render Full Stock Detail View (without redundant Back button)
            render_stock_detail_page(active_search_ticker, subscriber, token, show_back_button=False)



    # ----------------------------------------------------
    # TAB 3: SCANNER, ALERTS & BACKTESTING
    # ----------------------------------------------------
    with tab_hub:



        # SECTION 1: AUTOMATED SCANNER & SCHEDULER CONTROL
        sched_state = database.get_scheduler_state()
        
        # 1. Technical Scheduler State
        is_sched_active = bool(sched_state.get("is_active"))
        start_ts_str = sched_state.get("start_timestamp")
        
        uptime_str = "Stopped"
        if is_sched_active and start_ts_str:
            start_dt = parse_dt(start_ts_str)
            if start_dt:
                delta = datetime.now() - start_dt
                days = delta.days
                hours, remainder = divmod(delta.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                uptime_str = f"{days}d {hours}h {minutes}m" if days > 0 else (f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m")
            else:
                uptime_str = "Active"

        # 2. Growth Scheduler State
        is_growth_active = bool(sched_state.get("growth_is_active"))
        g_start_ts_str = sched_state.get("growth_start_timestamp")
        
        g_uptime_str = "Stopped"
        if is_growth_active and g_start_ts_str:
            g_start_dt = parse_dt(g_start_ts_str)
            if g_start_dt:
                delta = datetime.now() - g_start_dt
                days = delta.days
                hours, remainder = divmod(delta.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                g_uptime_str = f"{days}d {hours}h {minutes}m" if days > 0 else (f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m")
            else:
                g_uptime_str = "Active"

        # Fetch latest logs for metrics display
        tech_log = database.get_last_scan_log(trigger_prefix="manual") or database.get_last_scan_log(trigger_prefix="scheduled") or database.get_last_scan_log()
        t_last_time = tech_log["timestamp"] if tech_log else "Never"
        t_last_dur = f"{tech_log['duration_seconds']:.2f}s" if tech_log else "n/a"

        growth_log = database.get_last_scan_log(trigger_prefix="growth")
        g_last_time = growth_log["timestamp"] if growth_log else "Never"
        g_last_dur = f"{growth_log['duration_seconds']:.2f}s" if growth_log else "n/a"

        # Section 1 Header
        st.markdown('<h3 style="color: #f8fafc; font-weight: 800; margin-top: 0; margin-bottom: 8px;">⚡ Scanner Control Hub & Auto-Schedulers</h3>', unsafe_allow_html=True)
        st.write("Manage your **Candlestick Technical Scanner** and **AI Growth Catalyst Scanner** below. Choose to run scans on-demand or enable automatic twice-daily background scheduling:")

        col_tech, col_growth = st.columns(2)
        
        # ------------------- COLUMN 1: TECHNICAL SCANNER -------------------
        with col_tech:
            st.markdown("""
            <div style="background: #0f172a; padding: 18px; border-radius: 10px; border: 1px solid #334155; margin-bottom: 15px; min-height: 130px; box-sizing: border-box;">
                <h4 style="margin-top: 0; margin-bottom: 6px; color: #f8fafc; font-size: 1.1rem;">📊 Candlestick Technical Reversal Engine</h4>
                <p style="color: #94a3b8; font-size: 0.85rem; line-height: 1.4; margin: 0;">
                    Scans price charts & volume over the past 3 trading days for confirmed 
                    <strong style="color: #38df88;">Hammer Buy Reversals</strong> (RSI &lt; 50) and 
                    <strong style="color: #f87171;">Hanging Man Risk Warnings</strong>.
                </p>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("<p style='font-weight: 700; color: #f8fafc; margin-bottom: 6px;'>1. Run On-Demand:</p>", unsafe_allow_html=True)
            if st.button("▶️ Run Instant Technical Scan", type="primary", use_container_width=True, key="btn_tech_manual"):
                with st.spinner("Scanning watchlist for Hammer & Hanging Man pattern setups..."):
                    start_t = time.time()
                    daily_scanner.run_daily_scan(days_to_scan=3, trigger_type="manual")
                    dur = time.time() - start_t
                    st.session_state.pending_toast = f"Technical scan complete! Took {dur:.2f}s."
                    st.rerun()

            st.markdown("<p style='font-weight: 700; color: #f8fafc; margin-top: 14px; margin-bottom: 6px;'>2. Market-Aligned Auto-Scheduler (9:00 AM & 4:30 PM EST):</p>", unsafe_allow_html=True)
            toggle_label = "🛑 Stop Technical Auto-Scheduler" if is_sched_active else "⚡ Start Technical Auto-Scheduler"
            btn_type = "secondary" if is_sched_active else "primary"
            if st.button(toggle_label, type=btn_type, use_container_width=True, key="btn_tech_sched"):
                new_state = not is_sched_active
                database.set_scheduler_active(new_state)
                status_txt = "started" if new_state else "stopped"
                st.session_state.pending_toast = f"Technical Auto-Scheduler has been {status_txt}."
                st.rerun()

            t_status_color = "#38df88" if is_sched_active else "#f87171"
            t_status_label = f"🟢 Active ({uptime_str})" if is_sched_active else "🔴 Stopped"
            st.markdown(f"""
            <div style="background: #090d16; padding: 14px; border-radius: 8px; border: 1px solid #1e293b; margin-top: 14px;">
                <span style="color: #94a3b8; font-size: 11px; font-weight: 700; text-transform: uppercase;">AUTOMATED SCHEDULER STATUS</span>
                <div style="color: {t_status_color}; font-size: 1.1rem; font-weight: 800; margin-top: 4px;">{t_status_label}</div>
                <div style="color: #cbd5e1; font-size: 0.85rem; margin-top: 6px;">Last Executed: <strong style="color: #f8fafc;">{t_last_time}</strong> ({t_last_dur})</div>
            </div>
            """, unsafe_allow_html=True)

        # ------------------- COLUMN 2: GROWTH CATALYST SCANNER -------------------
        with col_growth:
            st.markdown("""
            <div style="background: #0f172a; padding: 18px; border-radius: 10px; border: 1px solid #334155; margin-bottom: 15px; min-height: 130px; box-sizing: border-box;">
                <h4 style="margin-top: 0; margin-bottom: 6px; color: #f8fafc; font-size: 1.1rem;">🚀 Whole-Market AI Growth & Hidden Gem Catalyst Engine</h4>
                <p style="color: #94a3b8; font-size: 0.85rem; line-height: 1.4; margin: 0;">
                    Scans the <strong style="color: #38df88;">entire US stock market</strong> (unusual volume &ge; 2.0x, small-cap gainers, tech growth) 
                    using <strong style="color: #60a5fa;">Groq Llama 3.3-70B</strong> to discover unexpected contract wins & breakout catalysts (&ge; 7.0/10).
                </p>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("<p style='font-weight: 700; color: #f8fafc; margin-bottom: 6px;'>1. Run On-Demand:</p>", unsafe_allow_html=True)
            if st.button("🚀 Run Instant Market Growth Scan", type="primary", use_container_width=True, key="btn_growth_manual"):
                with st.spinner("Scanning whole-market volume surges & news catalysts with Groq Llama 3.3-70B..."):
                    start_t = time.time()
                    growth_scanner.run_growth_scan(trigger_type="manual_ui")
                    dur = time.time() - start_t
                    st.session_state.pending_toast = f"Growth catalyst scan complete! Took {dur:.2f}s."
                    st.rerun()

            st.markdown("<p style='font-weight: 700; color: #f8fafc; margin-top: 14px; margin-bottom: 6px;'>2. Market-Aligned Auto-Scheduler (9:00 AM & 4:30 PM EST):</p>", unsafe_allow_html=True)

            g_toggle_label = "🛑 Stop Growth Auto-Scheduler" if is_growth_active else "🚀 Start Growth Auto-Scheduler"
            g_btn_type = "secondary" if is_growth_active else "primary"
            if st.button(g_toggle_label, type=g_btn_type, use_container_width=True, key="btn_growth_sched"):
                g_new_state = not is_growth_active
                database.set_growth_scheduler_active(g_new_state)
                g_status_txt = "started" if g_new_state else "stopped"
                st.session_state.pending_toast = f"Growth Auto-Scheduler has been {g_status_txt}."
                st.rerun()

            g_status_color = "#38df88" if is_growth_active else "#f87171"
            g_status_label = f"🟢 Active ({g_uptime_str})" if is_growth_active else "🔴 Stopped"
            st.markdown(f"""
            <div style="background: #090d16; padding: 14px; border-radius: 8px; border: 1px solid #1e293b; margin-top: 14px;">
                <span style="color: #94a3b8; font-size: 11px; font-weight: 700; text-transform: uppercase;">AUTOMATED SCHEDULER STATUS</span>
                <div style="color: {g_status_color}; font-size: 1.1rem; font-weight: 800; margin-top: 4px;">{g_status_label}</div>
                <div style="color: #cbd5e1; font-size: 0.85rem; margin-top: 6px;">Last Executed: <strong style="color: #f8fafc;">{g_last_time}</strong> ({g_last_dur})</div>
            </div>
            """, unsafe_allow_html=True)

        def on_pref_change():
            w_buys = st.session_state.get("wants_buys_check", True)
            w_risks = st.session_state.get("wants_risks_check", True)
            w_sells = st.session_state.get("wants_sells_check", True)
            w_growth = st.session_state.get("wants_growth_check", True)
            database.update_subscriber_preferences(token, w_buys, w_risks, w_sells, w_growth)
            st.session_state.pending_toast = "Alert Channel preferences updated successfully."

        # SECTION 2: ALERT NOTIFICATION PREFERENCES
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">🔔 Alert Notification Channel Preferences</div>', unsafe_allow_html=True)
        
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
        st.checkbox(
            "🚀 Growth & Contract Catalysts (High Volume + Groq AI Growth Score >= 7/10)",
            value=bool(subscriber.get("wants_growth", 1)),
            key="wants_growth_check",
            on_change=on_pref_change
        )
        st.markdown('<p style="font-size: 13px; color: #94a3b8; margin-top: 10px;">Preferences update automatically in real-time when toggled.</p>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # SECTION 3: EXPANDABLE DROPDOWNS FOR LOGS & UTILITIES
        with st.expander("🧪 2-Year Strategy Backtest Sandbox", expanded=False):
            st.write("Run historical simulations of the **3-day rigid trading strategy** to verify how a ticker performed over a 2-year window:")
            
            default_ticker = watchlist[0] if watchlist else "NVDA"
            backtest_ticker = st.text_input("Enter Ticker to Backtest", value=default_ticker, key="hub_bt_ticker").strip().upper()
            
            bt_btn = st.button("Run Strategy Backtest Simulation", type="primary")
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

        # SECTION 3: SYSTEM LEARNING & OUTCOME PERFORMANCE MATRIX
        with st.expander("🧠 System Learning & Post-Trade Outcome Matrix", expanded=True):
            st.write("Candlestick Sentinel continuously tracks post-alert price action to evaluate setup accuracy, feed outcomes back into AI analysis, and dynamically calibrate confidence scoring:")
            
            stats = database.get_historical_accuracy_stats()
            outcomes = database.get_all_alert_outcomes(limit=20)
            
            sc1, sc2, sc3, sc4 = st.columns(4)
            with sc1:
                st.markdown(f'<div class="metric-value">{stats["total_resolved"]}</div>', unsafe_allow_html=True)
                st.markdown('<div class="metric-label">Total Resolved Signals</div>', unsafe_allow_html=True)
            with sc2:
                wr_str = f"{stats['win_rate']:.1%}" if stats['win_rate'] is not None else "N/A"
                st.markdown(f'<div class="metric-value" style="color: #38df88;">{wr_str}</div>', unsafe_allow_html=True)
                st.markdown('<div class="metric-label">Historical Win Rate</div>', unsafe_allow_html=True)
            with sc3:
                ret_str = f"{stats['avg_return_pct']:.2%}" if stats['avg_return_pct'] is not None else "0.00%"
                st.markdown(f'<div class="metric-value">{ret_str}</div>', unsafe_allow_html=True)
                st.markdown('<div class="metric-label">Avg Return per Alert</div>', unsafe_allow_html=True)
            with sc4:
                st.markdown(f'<div class="metric-value">{stats["wins"]} W / {stats["losses"]} L</div>', unsafe_allow_html=True)
                st.markdown('<div class="metric-label">Win / Loss Ratio</div>', unsafe_allow_html=True)
                
            st.write("---")
            if not outcomes:
                st.info("No recorded setup alerts in database yet. Run a daily scan above to generate your first alert blueprint!")
            else:
                st.write("**Recent Alert Outcome Audit Log:**")
                out_df = pd.DataFrame(outcomes)
                out_df["Entry"] = out_df["entry_price"].map(lambda x: f"${x:.2f}" if (pd.notna(x) and x is not None) else "N/A")
                out_df["Stop Loss"] = out_df["stop_loss"].map(lambda x: f"${x:.2f}" if (pd.notna(x) and x is not None) else "N/A")
                out_df["Target"] = out_df["profit_target"].map(lambda x: f"${x:.2f}" if (pd.notna(x) and x is not None) else "N/A")
                out_df["Exit Price"] = out_df["exit_price"].map(lambda x: f"${x:.2f}" if (pd.notna(x) and x is not None) else "N/A")
                out_df["Return"] = out_df["return_pct"].map(lambda x: f"{x:.2%}" if (pd.notna(x) and x is not None) else "N/A")
                out_df["Status"] = out_df["outcome_status"].map(lambda x: "🟢 WIN (Target Hit)" if x == "win" else ("🔴 LOSS (Stop Hit)" if x == "loss" else ("⏳ TIMEOUT" if x == "timeout" else "🟡 Pending Evaluation")))
                
                out_df = out_df.rename(columns={
                    "ticker": "Ticker",
                    "pattern_type": "Pattern",
                    "sent_at": "Alert Sent At",
                    "day1_date": "Setup Date"
                })
                st.dataframe(out_df[["Ticker", "Pattern", "Setup Date", "Entry", "Stop Loss", "Target", "Status", "Exit Price", "Return"]], use_container_width=True, hide_index=True)


        # SECTION 4: EXPANDABLE DROPDOWNS FOR LOGS & UTILITIES
        with st.expander("📄 View Recent Scanner Run Logs", expanded=False):

            logs = database.get_all_scan_logs(limit=10)
            if not logs:
                st.info("No scanner execution logs recorded yet. Click 'Run Instant Daily Scan Now' above to perform your first scan!")
            else:
                log_df = pd.DataFrame(logs)
                log_df["duration_seconds"] = log_df["duration_seconds"].apply(lambda x: f"{x:.2f}s")
                log_df = log_df.rename(columns={
                    "timestamp": "Timestamp",
                    "duration_seconds": "Duration",
                    "tickers_scanned": "Tickers",
                    "signals_found": "Setups Found",
                    "alerts_sent": "Alerts Sent",
                    "trigger_type": "Trigger Type"
                })
                st.table(log_df[["Timestamp", "Trigger Type", "Duration", "Tickers", "Setups Found", "Alerts Sent"]])

        with st.expander("📧 Email Delivery Tester & Layout Inspector", expanded=False):
            st.write("Send a test alert email to your address or inspect how different AI models format email notifications:")
            
            model_options = [
                "⚡ Auto (Default Fallback Chain)",
                "🔥 Groq 70B (llama-3.3-70b-versatile)",
                "⚡ Groq 8B (llama-3.1-8b-instant)",
                "✨ Gemma 4 (gemma-4-26b-a4b-it)",
                "🚀 Gemini Flash (gemini-2.0-flash)"
            ]
            selected_model_label = st.selectbox(
                "🤖 Select AI Model Provider for Test Email:",
                model_options,
                key="test_email_model_selectbox"
            )
            
            forced_model_map = {
                "🔥 Groq 70B (llama-3.3-70b-versatile)": "Groq-70B",
                "⚡ Groq 8B (llama-3.1-8b-instant)": "Groq-8B",
                "✨ Gemma 4 (gemma-4-26b-a4b-it)": "Gemma-4",
                "🚀 Gemini Flash (gemini-2.0-flash)": "Gemini-Flash"
            }
            forced_model_arg = forced_model_map.get(selected_model_label)

            c_test1, c_test2 = st.columns(2)
            
            with c_test1:
                if st.button("📧 Test Technical Reversal Email", use_container_width=True, key="btn_test_tech_email"):
                    mock_ticker = watchlist[0] if watchlist else "NVDA"
                    with st.spinner(f"Fetching real market quote for {mock_ticker} & running AI check via {selected_model_label}..."):
                        try:
                            hist = yf.Ticker(mock_ticker).history(period="1mo")
                            if not hist.empty:
                                cur_price = float(hist['Close'].iloc[-1])
                                day1_l = round(cur_price * 0.96, 2)
                                day1_h = round(cur_price * 1.01, 2)
                                day1_c = round(cur_price * 0.97, 2)
                                day2_c = round(cur_price, 2)
                            else:
                                cur_price, day1_l, day1_h, day1_c, day2_c = 125.0, 115.0, 126.0, 120.0, 125.0
                        except Exception:
                            cur_price, day1_l, day1_h, day1_c, day2_c = 125.0, 115.0, 126.0, 120.0, 125.0

                        mock_signal = {
                            "ticker": mock_ticker,
                            "pattern_type": "Hammer",
                            "confidence_score": 88.5,
                            "rsi_14": 28.2,
                            "vol_mult": 1.95,
                            "day1_date": (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d"),
                            "day1_close": day1_c,
                            "day1_low": day1_l,
                            "day1_high": day1_h,
                            "day2_date": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
                            "day2_close": day2_c
                        }
                        ai_analysis = analyst_engine.analyze_signal(mock_signal, forced_model=forced_model_arg)
                    if ai_analysis:
                        mock_signal["ai_analysis"] = ai_analysis
                    email_html = notifier.format_alert_email(mock_signal, token)
                    real_sent, status_msg = notifier.simulate_send_alert(subscriber["email"], email_html, mock_ticker)
                    
                    model_tag = (ai_analysis.get("ai_model_used") if ai_analysis else None) or "AI"
                    if real_sent:
                        st.success(f"✅ Technical Alert Sent for {mock_ticker} (${day2_c}) via {model_tag}: {status_msg}")
                    else:
                        st.info(f"ℹ️ [{model_tag}] {status_msg}")
                    st.session_state.inspect_html = (f"Technical Reversal Alert ({model_tag})", email_html)
                    st.rerun()


            with c_test2:
                if st.button("🚀 Test Growth Catalyst Email", use_container_width=True, key="btn_test_growth_email"):
                    mock_ticker = watchlist[0] if watchlist else "AMD"
                    with st.spinner(f"Evaluating real-time growth catalysts for {mock_ticker} via {selected_model_label}..."):
                        g_payload = growth_engine.scan_ticker_for_growth_catalyst(mock_ticker)
                        g_res = analyst_engine.evaluate_growth_catalyst(g_payload, forced_model=forced_model_arg)
                        if not g_res:
                            # Mock sample if news fetch is empty
                            g_res = {
                                "ticker": mock_ticker,
                                "growth_score": 8.5,
                                "catalyst_type": "Partnership & Computing Power Deal",
                                "headline_summary": f"{mock_ticker} announces strategic $5 Billion AI partnership & multi-year agreement.",
                                "key_catalysts": ["$5B strategic investment", "Next-gen AI computing power agreement", "Expanded market share"],
                                "risks": ["High initial capex requirements", "Market competition"],
                                "plain_english_takeaway": f"Major growth driver for {mock_ticker} over the next 12-24 months.",
                                "ai_model_used": forced_model_arg or "Gemini-Flash (gemma-4-26b-a4b-it)",
                                "news_articles": [

                                    {"title": f"{mock_ticker} Lands Massive $5B AI Computing Partnership", "link": "https://news.google.com", "pubDate": "Tue, 22 Jul 2026 14:00:00 GMT"},
                                    {"title": f"{mock_ticker} Stock Surges on New Multi-Year Revenue Agreement", "link": "https://news.google.com", "pubDate": "Mon, 21 Jul 2026 09:30:00 GMT"},
                                    {"title": f"Why Analysts Are Upgrading {mock_ticker} After Strategic Deal", "link": "https://news.google.com", "pubDate": "Mon, 21 Jul 2026 08:15:00 GMT"},
                                ]
                            }
                    growth_html = notifier.format_growth_catalyst_email(g_res, token)
                    real_sent, status_msg = notifier.simulate_send_alert(subscriber["email"], growth_html, f"{mock_ticker} Growth Catalyst")
                    
                    g_model_tag = g_res.get("ai_model_used", "Groq AI")
                    if real_sent:
                        st.success(f"✅ Growth Catalyst Alert Sent via {g_model_tag}: {status_msg}")
                    else:
                        st.info(f"ℹ️ [{g_model_tag}] {status_msg}")
                    st.session_state.inspect_html = (f"Growth Catalyst Alert ({g_model_tag})", growth_html)
                    st.rerun()

            if "inspect_html" in st.session_state:
                label, h_content = st.session_state.inspect_html
                st.write(f"**Live Layout Inspector Preview ({label}):**")
                st.components.v1.html(h_content, height=450, scrolling=True)


        with st.expander("🗑️ Account Settings & Unsubscribe", expanded=False):
            st.write("Erase all alert preferences and delete your watchlist:")
            if st.button("Unsubscribe Completely", type="primary", use_container_width=True):
                st.query_params.update(unsubscribe="true")
                st.rerun()

if __name__ == "__main__":
    main()
