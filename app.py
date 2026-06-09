import streamlit as st
from local_env import load_env_file

load_env_file()

import database
import pattern_engine
import backtest
import notifier
import analyst_engine
import importlib
import inspect
import pandas as pd
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
    # STATE 4: Landing / Signup & Login state
    # ----------------------------------------------------
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
        tickers_show = ["NVDA", "AMD", "PLTR", "RKLB", "SOFI", "MU"]
        cols = st.columns(len(tickers_show))
        for idx, tick in enumerate(tickers_show):
            with cols[idx]:
                st.markdown(f"""
                <div style="background-color: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 12px; text-align: center;">
                    <span style="font-weight: 700; color: #f8fafc; font-size: 13px;">{tick}</span>
                </div>
                """, unsafe_allow_html=True)
                
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

def render_management_dashboard(subscriber, token):
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
        # Personal access link explanation
        st.write("🔗 **Personal Access Link**")
        st.markdown(f"<code style='font-size: 11px; word-break: break-all;'>http://localhost:8501/?token={token}</code>", unsafe_allow_html=True)
        st.write("Use this link to bypass the OTP login screen on this device in the future.")
        st.write("---")
        st.button("🔓 Sign Out / Logout", on_click=logout, use_container_width=True)

    # Tabs
    tab_watchlist, tab_scanner, tab_backtester = st.tabs([
        "📋 Watchlist & Preferences", 
        "🔍 Live Watchlist Scanner", 
        "🧪 Backtester Sandbox"
    ])
    
    # ----------------------------------------------------
    # TAB 1: WATCHLIST & PREFERENCES
    # ----------------------------------------------------
    with tab_watchlist:
        col_left, col_right = st.columns([1, 1])
        
        with col_left:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="card-title">Manage Watchlist</div>', unsafe_allow_html=True)
            
            watchlist = database.get_watchlist(subscriber["id"])
            
            if watchlist:
                st.write("Click the red trash bin next to any ticker to delete it:")
                for ticker in watchlist:
                    wcol1, wcol2 = st.columns([4, 1])
                    with wcol1:
                        st.markdown(f"""
                        <div style="background-color: #334155; padding: 6px 12px; border-radius: 6px; font-weight: 700; margin-bottom: 6px; border: 1px solid #475569;">
                            📈 {ticker}
                        </div>
                        """, unsafe_allow_html=True)
                    with wcol2:
                        if st.button("🗑️", key=f"del_{ticker}", use_container_width=True):
                            database.remove_watchlist_ticker(subscriber["id"], ticker)
                            st.toast(f"Removed {ticker} from watchlist.", icon="🗑️")
                            st.rerun()
            else:
                st.warning("Your watchlist is currently empty. Add tickers below to receive alerts.")
                
            st.write("---")
            st.write("**Add Ticker to Watchlist**")
            with st.form("add_ticker_form"):
                new_ticker = st.text_input("Enter Ticker (e.g. AMD, RKLB)").strip().upper()
                add_btn = st.form_submit_button("Add Ticker")
                if add_btn:
                    if not new_ticker:
                        st.error("Please enter a ticker symbol.")
                    elif new_ticker in watchlist:
                        st.info(f"{new_ticker} is already in your watchlist.")
                    else:
                        success = database.add_watchlist_ticker(subscriber["id"], new_ticker)
                        if success:
                            st.success(f"Added {new_ticker} to watchlist.")
                            st.rerun()
                        else:
                            st.error("Failed to add ticker.")
            
            st.markdown('</div>', unsafe_allow_html=True)
            
        with col_right:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="card-title">Alert Preferences</div>', unsafe_allow_html=True)
            
            st.checkbox(
                "🟢 Wants Buy Opportunities (Hammer Reversals)",
                value=bool(subscriber["wants_buys"]),
                key="wants_buys_check",
                on_change=on_pref_change
            )
            st.checkbox(
                "🟡 Wants Risk Alerts (Medium Score Hanging Man)",
                value=bool(subscriber["wants_risks"]),
                key="wants_risks_check",
                on_change=on_pref_change
            )
            st.checkbox(
                "🔴 Wants Sell Alerts (High Score Hanging Man)",
                value=bool(subscriber["wants_sells"]),
                key="wants_sells_check",
                on_change=on_pref_change
            )
            
            st.markdown('<p style="font-size: 13px; color: #94a3b8; margin-top: 15px;">Preferences are updated instantly in the database on checkbox toggle.</p>', unsafe_allow_html=True)
            
            st.write("---")
            st.write("**Unsubscribe Option**")
            st.write("If you no longer wish to receive any scans or alerts, click the button below to permanently erase your data:")
            
            if st.button("Unsubscribe Completely", type="primary", use_container_width=True):
                st.query_params.update(unsubscribe="true")
                st.rerun()
                
            st.markdown('</div>', unsafe_allow_html=True)
            
            # Email Delivery Tester Card
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="card-title">Email Delivery Tester</div>', unsafe_allow_html=True)
            st.write("Test if the alerting system is sending emails correctly to your address:")
            
            test_btn = st.button("Send Test Alert Email", use_container_width=True)
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
                
                # Force reload notifier to guarantee latest function signatures are used
                importlib.reload(notifier)
                with st.spinner("Running optional AI analyst check..."):
                    ai_analysis = analyst_engine.analyze_signal(mock_signal)
                if ai_analysis:
                    mock_signal["ai_analysis"] = ai_analysis
                email_html = notifier.format_alert_email(mock_signal, token)
                send_alert_params = inspect.signature(notifier.simulate_send_alert).parameters
                if "ticker" in send_alert_params or len(send_alert_params) >= 3:
                    real_sent, status_msg = notifier.simulate_send_alert(subscriber["email"], email_html, mock_ticker)
                else:
                    real_sent, status_msg = notifier.simulate_send_alert(subscriber["email"], email_html)
                
                if real_sent:
                    st.success(f"✅ {status_msg}")
                else:
                    st.info(f"ℹ️ {status_msg}")
                    st.write("**Simulated Email Output:**")
                    st.components.v1.html(email_html, height=450, scrolling=True)
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
                    
                    options = [f"{s['ticker']} - {s['pattern_type']} ({s['day1_date'].strftime('%Y-%m-%d') if hasattr(s['day1_date'], 'strftime') else str(s['day1_date'])[:10]})" for s in signals]
                    selected_opt = st.selectbox("Select Signal to Preview", options)
                    selected_idx = options.index(selected_opt)
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
