"""
TRadar Paper Portfolio Simulator Component
Clean, professional fintech layout without emojis.
Features human-friendly Open Trades Gain/Loss tracking, win/loss position badges,
Today's Change %, Portfolio Weight %, Entry Date, and Ticker/Sector Asset Allocation charts.
"""

import streamlit as st
import plotly.graph_objects as go
import time
from datetime import datetime, date, timedelta
import yfinance as yf
from core import database

# Global Sector Dictionary Cache for fast lookup
SECTOR_MAPPING = {
    "NVDA": "Technology", "AMD": "Technology", "AAPL": "Technology", "MSFT": "Technology",
    "PLTR": "Technology", "TSLA": "Consumer Cyclical", "AMZN": "Consumer Cyclical",
    "GOOGL": "Communication Services", "META": "Communication Services", "NFLX": "Communication Services",
    "BABA": "Consumer Cyclical", "JPM": "Financial Services", "BAC": "Financial Services",
    "SPY": "ETF / Index", "QQQ": "ETF / Index", "IWM": "ETF / Index", "DIA": "ETF / Index",
    "TBLA": "Communication Services", "SIRI": "Communication Services", "WMT": "Consumer Defensive"
}


def get_ticker_sector(ticker):
    sym = ticker.upper().strip()
    if sym in SECTOR_MAPPING:
        return SECTOR_MAPPING[sym]
    try:
        inf = yf.Ticker(sym).info
        sec = inf.get("sector") or inf.get("category")
        if sec:
            SECTOR_MAPPING[sym] = sec
            return sec
    except Exception:
        pass
    return "Other / Miscellaneous"


@st.dialog("✏️ Edit Position Date & Shares")
def render_edit_trade_dialog(trade, key_prefix):
    # Inject CSS to make dropdown popover menus 100% crisp, sharp, non-transparent and clear
    st.markdown("""
    <style>
    div[data-baseweb="popover"], div[data-baseweb="menu"], ul[role="listbox"] {
        background-color: #0f172a !important;
        background: #0f172a !important;
        backdrop-filter: none !important;
        -webkit-backdrop-filter: none !important;
        opacity: 1 !important;
        border: 1px solid #334155 !important;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.9) !important;
        border-radius: 8px !important;
    }
    div[data-baseweb="popover"] li, ul[role="listbox"] li, div[role="option"] {
        background-color: #0f172a !important;
        color: #f8fafc !important;
        font-weight: 700 !important;
        font-size: 0.9rem !important;
        opacity: 1 !important;
    }
    div[data-baseweb="popover"] li:hover, ul[role="listbox"] li:hover, div[role="option"]:hover, [aria-selected="true"] {
        background-color: #1e293b !important;
        color: #38bdf8 !important;
    }
    </style>
    """, unsafe_allow_html=True)
    t_id = trade["id"]
    sym = trade["ticker"]
    
    st.markdown(f"""
    <div style="background: rgba(30, 41, 59, 0.7); border: 1px solid #38bdf8; border-radius: 8px; padding: 12px; margin-bottom: 12px; text-align: center;">
        <div style="font-size: 1.1rem; font-weight: 800; color: #38bdf8;">✏️ Edit Position: {sym}</div>
        <div style="font-size: 0.78rem; color: #94a3b8; margin-top: 2px;">Modify purchase date or share size for <strong>{sym}</strong>. Historical price is auto-calculated.</div>
    </div>
    """, unsafe_allow_html=True)
    
    raw_dt_str = str(trade.get("entry_date", ""))
    try:
        init_date = datetime.strptime(raw_dt_str.split(" ")[0], "%Y-%m-%d").date()
    except Exception:
        init_date = datetime.now().date()

    # Fetch stock earliest trading date (IPO date)
    earliest_date_str, earliest_price = database.fetch_earliest_trading_date(sym)
    
    current_year = datetime.now().year
    if earliest_date_str:
        try:
            ipo_year = int(earliest_date_str.split("-")[0])
        except Exception:
            ipo_year = 1980
    else:
        ipo_year = 1980

    # Dynamically restrict Year dropdown to stock's actual trading history (down to IPO year)
    years = list(range(current_year, ipo_year - 1, -1))
    if not years:
        years = [current_year]

    months = [
        ("01", "01 - Jan"), ("02", "02 - Feb"), ("03", "03 - Mar"), ("04", "04 - Apr"),
        ("05", "05 - May"), ("06", "06 - Jun"), ("07", "07 - Jul"), ("08", "08 - Aug"),
        ("09", "09 - Sep"), ("10", "10 - Oct"), ("11", "11 - Nov"), ("12", "12 - Dec")
    ]
    month_labels = [m[1] for m in months]
    month_val_map = {m[1]: m[0] for m in months}
    month_idx_map = {m[0]: i for i, m in enumerate(months)}

    init_year = init_date.year if init_date.year in years else years[0]
    init_month_str = f"{init_date.month:02d}"
    init_month_idx = month_idx_map.get(init_month_str, 0)
    init_day = init_date.day

    st.markdown('<div style="font-size:0.82rem; font-weight:700; color:#94a3b8; margin-bottom:4px;">Purchase Date</div>', unsafe_allow_html=True)
    dc1, dc2, dc3 = st.columns(3)
    with dc1:
        sel_year = st.selectbox("Year", options=years, index=years.index(init_year) if init_year in years else 0, key=f"{key_prefix}_dlg_yr_{t_id}")
    with dc2:
        sel_month_lbl = st.selectbox("Month", options=month_labels, index=init_month_idx, key=f"{key_prefix}_dlg_mo_{t_id}")
    with dc3:
        sel_day = st.selectbox("Day", options=list(range(1, 32)), index=min(init_day - 1, 30), key=f"{key_prefix}_dlg_dy_{t_id}")

    if earliest_date_str:
        st.markdown(f'<div style="font-size:0.72rem; color:#38bdf8; margin-top:-6px; margin-bottom:10px;">Showing valid trading years for {sym}: <strong>{ipo_year} – {current_year}</strong> (IPO: {earliest_date_str})</div>', unsafe_allow_html=True)

    sel_month_str = month_val_map[sel_month_lbl]

    # Handle end-of-month dates cleanly
    try:
        valid_date = date(int(sel_year), int(sel_month_str), int(sel_day))
    except ValueError:
        import calendar
        max_d = calendar.monthrange(int(sel_year), int(sel_month_str))[1]
        valid_date = date(int(sel_year), int(sel_month_str), max_d)

    new_date_str = valid_date.strftime("%Y-%m-%d")

    new_edit_shares = st.number_input(
        "Shares Quantity",
        min_value=0.001,
        value=float(trade["shares"]),
        step=1.0,
        key=f"{key_prefix}_dlg_edit_shares_{t_id}"
    )

    # ─── LIVE AUTO-CALCULATED PRICE PREVIEW CARD ───
    auto_price = database.fetch_historical_price_on_date(sym, new_date_str)
    earliest_date_str, earliest_price = database.fetch_earliest_trading_date(sym)
    is_pre_ipo = False
    if earliest_date_str and new_date_str < earliest_date_str:
        is_pre_ipo = True

    if auto_price is not None:
        calc_price = auto_price
        st.markdown(f"""
        <div style="background: rgba(15, 23, 42, 0.9); border: 1px solid #38df88; border-radius: 8px; padding: 12px; margin: 12px 0; text-align: center;">
            <div style="font-size:0.75rem; font-weight:700; color:#94a3b8; text-transform:uppercase; letter-spacing:0.05em;">Auto-Calculated Historical Price for {sym}</div>
            <div style="font-size: 1.6rem; font-weight: 800; color: #38df88; margin-top: 4px;">${calc_price:,.2f}</div>
            <div style="font-size:0.72rem; color:#94a3b8; margin-top:2px;">Market closing price for <strong>{sym}</strong> on <strong>{new_date_str}</strong></div>
        </div>
        """, unsafe_allow_html=True)
    elif is_pre_ipo:
        calc_price = float(trade["entry_price"])
        st.markdown(f"""
        <div style="background: rgba(248, 113, 113, 0.12); border: 1px solid #f87171; border-radius: 8px; padding: 12px; margin: 12px 0; text-align: center;">
            <div style="font-size:0.75rem; font-weight:700; color:#f87171; text-transform:uppercase;">⚠️ Pre-IPO Date Selected for {sym}</div>
            <div style="font-size: 0.85rem; font-weight: 700; color: #f87171; margin-top: 4px;"><strong>{sym}</strong> was not publicly traded on <strong>{new_date_str}</strong></div>
            <div style="font-size:0.72rem; color:#94a3b8; margin-top:4px;">{sym} went public on <strong>{earliest_date_str}</strong> (IPO Price: ${earliest_price:,.2f}). Please select a date on or after {earliest_date_str}.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        calc_price = float(trade["entry_price"])
        st.markdown(f"""
        <div style="background: rgba(15, 23, 42, 0.9); border: 1px solid #334155; border-radius: 8px; padding: 12px; margin: 12px 0; text-align: center;">
            <div style="font-size:0.75rem; font-weight:700; color:#94a3b8; text-transform:uppercase;">Selected Date for {sym}: <strong>{new_date_str}</strong></div>
            <div style="font-size: 1.4rem; font-weight: 800; color: #38bdf8; margin-top: 4px;">${calc_price:,.2f}</div>
            <div style="font-size:0.72rem; color:#fbbf24; margin-top:2px;">Using position entry price (market closed / holiday on selected date)</div>
        </div>
        """, unsafe_allow_html=True)

    with st.form(key=f"{key_prefix}_form_edit_{t_id}"):
        submitted = st.form_submit_button("Save & Recalculate Position", type="primary", use_container_width=True)
        if submitted:
            full_entry_date = f"{new_date_str} 09:30"
            updated_invested = float(new_edit_shares) * calc_price
            ok, msg = database.update_paper_trade(
                t_id,
                entry_date=full_entry_date,
                entry_price=calc_price,
                shares=float(new_edit_shares),
                total_invested=updated_invested
            )
            if ok:
                st.session_state.pending_toast = msg
                st.rerun()
            else:
                st.error(msg)


def render_paper_trading_tab(subscriber, token):
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<div class="card-title">Paper Trading Portfolio Simulator</div>', unsafe_allow_html=True)
    st.write("Manually enter paper trades with live position tracking, sector & ticker allocation charts, and realized P&L logs:")
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('<div style="margin-top: 14px;"></div>', unsafe_allow_html=True)

    if st.session_state.get("clear_new_paper_account_label"):
        st.session_state["new_paper_account_label"] = ""
        del st.session_state["clear_new_paper_account_label"]

    accounts = database.get_paper_accounts(subscriber["id"])
    can_add_account = len(accounts) < database.MAX_PAPER_ACCOUNTS

    account_name_col, account_btn_col = st.columns([4, 1.2])
    with account_name_col:
        new_account_label = st.text_input(
            "Portfolio Name",
            placeholder="e.g. Swing Trades, Long-Term Ideas",
            label_visibility="collapsed",
            key="new_paper_account_label",
            disabled=not can_add_account
        )
    with account_btn_col:
        add_account = st.button(
            "Create Portfolio",
            type="primary",
            use_container_width=True,
            key="btn_add_paper_account",
            disabled=not can_add_account
        )

    if not can_add_account:
        st.markdown(
            f'<div style="color:#94a3b8; font-size:0.82rem; margin-top:6px;">Portfolio limit reached ({len(accounts)}/{database.MAX_PAPER_ACCOUNTS}).</div>',
            unsafe_allow_html=True
        )

    if add_account:
        success, msg = database.add_paper_account(subscriber["id"], new_account_label)
        if success:
            st.session_state["clear_new_paper_account_label"] = True
            st.session_state.pending_toast = msg
            st.rerun()
        else:
            st.error(msg)

    account_labels = [account["account_label"] for account in accounts]
    pending_active_label = st.session_state.get("pending_active_paper_account_label")
    if pending_active_label:
        if pending_active_label in account_labels:
            st.session_state.active_paper_account_label = pending_active_label
        del st.session_state["pending_active_paper_account_label"]

    active_label = st.session_state.get("active_paper_account_label")
    if active_label not in account_labels:
        active_label = account_labels[0]
        st.session_state.active_paper_account_label = active_label

    st.markdown("""
    <style>
    div[data-testid="stElementContainer"]:has(#paper_account_delete_top_marker)
        + div[data-testid="stElementContainer"] div[data-testid="stButton"] button {
        background: #dc2626 !important;
        border: 1px solid #ef4444 !important;
        color: #ffffff !important;
        height: 36px !important;
        font-weight: 800 !important;
    }
    div[data-testid="stElementContainer"]:has(#paper_account_delete_top_marker)
        + div[data-testid="stElementContainer"] div[data-testid="stButton"] button:hover {
        background: #b91c1c !important;
        border-color: #fca5a5 !important;
        color: #ffffff !important;
    }
    div[data-testid="stElementContainer"]:has(#paper_account_delete_top_marker)
        + div[data-testid="stElementContainer"] div[data-testid="stButton"] button:disabled {
        background: rgba(71, 85, 105, 0.35) !important;
        border-color: #475569 !important;
        color: #94a3b8 !important;
    }
    div[data-testid="stElementContainer"]:has(#paper_account_delete_top_marker) {
        display: none !important;
    }
    div[data-testid="stElementContainer"]:has(#paper_account_confirm_delete_marker)
        + div[data-testid="stElementContainer"] div[data-testid="stButton"] button {
        background: #dc2626 !important;
        border: 1px solid #ef4444 !important;
        color: #ffffff !important;
        height: 36px !important;
        font-weight: 800 !important;
    }
    div[data-testid="stElementContainer"]:has(#paper_account_confirm_delete_marker)
        + div[data-testid="stElementContainer"] div[data-testid="stButton"] button:hover {
        background: #b91c1c !important;
        border-color: #fca5a5 !important;
        color: #ffffff !important;
    }
    div[data-testid="stElementContainer"]:has(#paper_account_confirm_delete_marker) {
        display: none !important;
    }
    </style>
    """, unsafe_allow_html=True)

    selector_col, rename_action_col, delete_col = st.columns([3.3, 0.9, 1.2])
    with selector_col:
        selected_label = st.radio(
            "Paper Portfolio",
            account_labels,
            index=account_labels.index(active_label),
            horizontal=True,
            label_visibility="collapsed",
            key="active_paper_account_label"
        )
    with rename_action_col:
        rename_requested = st.button(
            "Rename Portfolio",
            use_container_width=True,
            key="btn_show_rename_paper_account"
        )
    with delete_col:
        st.markdown('<span id="paper_account_delete_top_marker"></span>', unsafe_allow_html=True)
        delete_account = st.button(
            "Delete Portfolio",
            use_container_width=True,
            key="btn_delete_active_paper_account",
            disabled=len(accounts) <= 1
        )

    selected_account = next(account for account in accounts if account["account_label"] == selected_label)
    rename_input_key = f"rename_paper_account_input_{selected_account['id']}"
    rename_state_key = "renaming_paper_account_label"

    if rename_requested:
        st.session_state[rename_state_key] = selected_account["account_label"]
        st.session_state.pending_rename_paper_account_prefill = {
            "key": rename_input_key,
            "value": selected_account["account_label"]
        }
        st.rerun()

    rename_target_label = st.session_state.get(rename_state_key)
    if rename_target_label not in account_labels:
        rename_target_label = None
        st.session_state.pop(rename_state_key, None)

    if rename_target_label:
        target_account = next(account for account in accounts if account["account_label"] == rename_target_label)
        rename_input_key = f"rename_paper_account_input_{target_account['id']}"
        pending_rename_prefill = st.session_state.get("pending_rename_paper_account_prefill")
        if pending_rename_prefill and pending_rename_prefill.get("key") == rename_input_key:
            st.session_state[rename_input_key] = pending_rename_prefill.get("value", rename_target_label)
            del st.session_state["pending_rename_paper_account_prefill"]

        with st.form(f"rename_paper_account_form_{target_account['id']}", clear_on_submit=False):
            st.markdown(f"""
            <div style="color:#bae6fd; font-weight:800; margin-bottom:4px;">Rename portfolio</div>
            <div style="color:#cbd5e1; font-size:0.9rem; margin-bottom:14px;">Editing <strong>{rename_target_label}</strong>.</div>
            """, unsafe_allow_html=True)
            rename_col, save_col, cancel_col = st.columns([3.4, 0.9, 0.9])
            with rename_col:
                rename_label = st.text_input(
                    "New Portfolio Name",
                    label_visibility="collapsed",
                    key=rename_input_key
                )
            with save_col:
                save_rename = st.form_submit_button("Save Name", type="primary", use_container_width=True)
            with cancel_col:
                cancel_rename = st.form_submit_button("Cancel", use_container_width=True)

        if cancel_rename:
            st.session_state.pop(rename_state_key, None)
            st.rerun()

        if save_rename:
            success, msg = database.rename_paper_account(
                subscriber["id"],
                rename_target_label,
                rename_label
            )
            if success:
                new_label = rename_label.strip()[:60]
                st.session_state.pending_active_paper_account_label = new_label
                st.session_state.pop(rename_state_key, None)
                st.session_state.pending_toast = msg
                st.rerun()
            else:
                st.error(msg)

    if delete_account:
        st.session_state.confirm_delete_paper_account_label = selected_account["account_label"]
        st.rerun()

    confirm_delete_label = st.session_state.get("confirm_delete_paper_account_label")
    if confirm_delete_label not in account_labels:
        confirm_delete_label = None
        st.session_state.pop("confirm_delete_paper_account_label", None)

    if confirm_delete_label:
        st.markdown(f"""
        <div class="card" style="border-color:#ef4444; background:rgba(127, 29, 29, 0.18);">
            <div style="color:#fecaca; font-weight:800; margin-bottom:4px;">Confirm portfolio deletion</div>
            <div style="color:#cbd5e1; font-size:0.9rem;">This will permanently delete <strong>{confirm_delete_label}</strong> and every paper trade inside it.</div>
        </div>
        """, unsafe_allow_html=True)
        cancel_col, confirm_col = st.columns([4, 1.2])
        with cancel_col:
            cancel_delete = st.button("Cancel", use_container_width=True, key="btn_cancel_delete_paper_account")
        with confirm_col:
            st.markdown('<span id="paper_account_confirm_delete_marker"></span>', unsafe_allow_html=True)
            confirm_delete = st.button("Confirm Delete", use_container_width=True, key="btn_confirm_delete_paper_account")

        if cancel_delete:
            st.session_state.pop("confirm_delete_paper_account_label", None)
            st.rerun()

        if confirm_delete:
            delete_status = st.empty()
            delete_progress = st.progress(0)
            for pct, label in [
                (25, "Preparing delete..."),
                (60, "Removing paper trades..."),
                (100, "Deleting portfolio...")
            ]:
                delete_status.markdown(f"""
                <div class="card" style="border-color:#f59e0b; background:rgba(245, 158, 11, 0.12);">
                    <div style="color:#fbbf24; font-weight:800;">{label}</div>
                    <div style="color:#cbd5e1; font-size:0.9rem;">{confirm_delete_label}</div>
                </div>
                """, unsafe_allow_html=True)
                delete_progress.progress(pct)
                time.sleep(0.35)

            success, msg = database.delete_paper_account(subscriber["id"], confirm_delete_label)
            if success:
                remaining_accounts = [
                    account for account in accounts
                    if account["account_label"] != confirm_delete_label
                ]
                if remaining_accounts:
                    st.session_state.pending_active_paper_account_label = remaining_accounts[0]["account_label"]
                st.session_state.pop("confirm_delete_paper_account_label", None)
                st.session_state.pending_toast = msg
                st.rerun()
            else:
                st.error(msg)

    _render_paper_account(subscriber, selected_account)


def _render_paper_account(subscriber, account):
    account_label = account["account_label"]
    key_prefix = f"paper_account_{account['id']}"
    clear_key = f"clear_paper_inputs_{key_prefix}"

    # Pre-instantiation session state reset for form fields
    if st.session_state.get(clear_key):
        st.session_state[f"{key_prefix}_paper_ticker_in"] = ""
        st.session_state[f"{key_prefix}_paper_amt_in"] = 1000.0
        st.session_state[f"{key_prefix}_paper_shares_in"] = 12.0
        st.session_state[f"{key_prefix}_paper_custom_price_in"] = 100.0
        del st.session_state[clear_key]

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(f'<div class="card-title">{account_label}</div>', unsafe_allow_html=True)
    st.markdown('<div style="margin-top: 14px;"></div>', unsafe_allow_html=True)

    # ----------------------------------------------------
    # 1. ADD PAPER POSITION FORM (Clean Professional Layout)
    # ----------------------------------------------------
    fcol1, fcol2, fcol3, fcol4 = st.columns([2.0, 3.8, 3.8, 1.4])

    # Group 1: Target Ticker
    with fcol1:
        st.markdown('<div style="font-size:0.8rem; font-weight:700; color:#94a3b8; margin-bottom:6px;">Target Ticker</div>', unsafe_allow_html=True)
        ticker_input = st.text_input(
            "Target Ticker",
            placeholder="e.g. NVDA, PLTR",
            label_visibility="collapsed",
            key=f"{key_prefix}_paper_ticker_in"
        ).strip().upper()

    # Group 2: Sizing Unit Selector + Input Field SIDE-BY-SIDE
    with fcol2:
        st.markdown('<div style="font-size:0.8rem; font-weight:700; color:#94a3b8; margin-bottom:6px;">Position Sizing</div>', unsafe_allow_html=True)
        scol_unit, scol_val = st.columns([1.5, 2.3])
        with scol_unit:
            alloc_unit = st.selectbox(
                "Unit",
                ["Shares", "$ Dollars"],
                label_visibility="collapsed",
                key=f"{key_prefix}_paper_alloc_unit"
            )
        with scol_val:
            if "Shares" in alloc_unit:
                shares_qty = st.number_input(
                    "Shares",
                    min_value=0.001,
                    value=12.0,
                    step=1.0,
                    label_visibility="collapsed",
                    key=f"{key_prefix}_paper_shares_in"
                )
                invest_sum = None
            else:
                invest_sum = st.number_input(
                    "Invest $",
                    min_value=1.0,
                    value=1000.0,
                    step=250.0,
                    label_visibility="collapsed",
                    key=f"{key_prefix}_paper_amt_in"
                )
                shares_qty = None

    # Group 3: Price Mode Selector + Price Field SIDE-BY-SIDE
    with fcol3:
        st.markdown('<div style="font-size:0.8rem; font-weight:700; color:#94a3b8; margin-bottom:6px;">Price Execution</div>', unsafe_allow_html=True)
        pcol_mode, pcol_val = st.columns([1.5, 2.3])
        with pcol_mode:
            price_mode = st.selectbox(
                "Price Mode",
                ["Auto Live", "Custom Price"],
                label_visibility="collapsed",
                key=f"{key_prefix}_paper_price_mode"
            )
        with pcol_val:
            if "Custom Price" in price_mode:
                entry_price_input = st.number_input(
                    "Entry Price",
                    min_value=0.01,
                    value=100.0,
                    step=1.0,
                    label_visibility="collapsed",
                    key=f"{key_prefix}_paper_custom_price_in"
                )
            else:
                st.markdown('<div style="height: 42px; display: flex; align-items: center; justify-content: center; background: rgba(30, 41, 59, 0.7); border: 1px solid #334155; border-radius: 8px; font-size: 0.85rem; font-weight: 700; color: #38bdf8;">Live Market</div>', unsafe_allow_html=True)
                entry_price_input = None

    # Group 4: Execute Button
    with fcol4:
        st.markdown('<div style="font-size:0.8rem; font-weight:700; color:transparent; margin-bottom:6px;">Action</div>', unsafe_allow_html=True)
        submit_btn = st.button("Add to Portfolio", type="primary", use_container_width=True, key=f"{key_prefix}_btn_buy_paper_position")

    if submit_btn:
        sym = ticker_input.split(" ")[0].split("-")[0].strip().upper()
        if not sym:
            st.error("Please enter a valid ticker symbol.")
        else:
            success, msg = database.add_paper_trade(
                subscriber_id=subscriber["id"],
                ticker=sym,
                total_invested=invest_sum,
                shares=shares_qty,
                entry_price=entry_price_input,
                account_label=account_label
            )
            if success:
                st.session_state[clear_key] = True
                st.session_state.active_main_tab = "🎮 Paper Portfolio"
                st.rerun()
            else:
                st.error(msg)

    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('<div style="margin-top: 20px;"></div>', unsafe_allow_html=True)

    # ----------------------------------------------------
    # 2. FETCH OPEN & CLOSED POSITIONS
    # ----------------------------------------------------
    open_trades = database.get_open_paper_trades(subscriber["id"], account_label=account_label)
    closed_trades = database.get_closed_paper_trades(subscriber["id"], account_label=account_label)

    if not open_trades and not closed_trades:
        st.markdown('<div class="card" style="text-align: center; padding: 24px;">', unsafe_allow_html=True)
        st.markdown('<div style="font-size: 1.1rem; font-weight: 700; color: #f8fafc; margin-bottom: 8px;">Your Paper Portfolio is currently empty</div>', unsafe_allow_html=True)
        st.write("Use the form above to add a custom position to this portfolio.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    # Fail-safe ticker-by-ticker live market quote & daily change fetcher
    ticker_quotes = {}
    ticker_daily_changes = {}
    if open_trades:
        unique_tickers = list(set(t["ticker"] for t in open_trades))
        for t in unique_tickers:
            try:
                hist = yf.Ticker(t).history(period="5d")
                if not hist.empty and "Close" in hist:
                    closes = hist["Close"].dropna()
                    if len(closes) >= 1:
                        val = float(closes.iloc[-1])
                        ticker_quotes[t] = val
                    if len(closes) >= 2:
                        prev = float(closes.iloc[-2])
                        d_chg = ((val - prev) / prev * 100.0) if prev > 0 else 0.0
                        ticker_daily_changes[t] = d_chg
            except Exception:
                pass

    # Calculate metrics for open positions
    total_invested = 0.0
    total_current_value = 0.0
    processed_open_trades = []

    winning_count = 0
    losing_count = 0

    for t in open_trades:
        sym = t["ticker"]
        entry_p = float(t["entry_price"])
        shrs = float(t["shares"])
        inv = float(t["total_invested"])
        cur_p = ticker_quotes.get(sym, entry_p)
        cur_val = cur_p * shrs
        pnl = cur_val - inv
        pnl_pct = (pnl / inv * 100.0) if inv > 0 else 0.0
        sector = get_ticker_sector(sym)
        daily_chg = ticker_daily_changes.get(sym, 0.0)

        if pnl >= 0:
            winning_count += 1
        else:
            losing_count += 1

        total_invested += inv
        total_current_value += cur_val

        processed_open_trades.append({
            "id": t["id"],
            "ticker": sym,
            "sector": sector,
            "entry_date": t["entry_date"],
            "entry_price": entry_p,
            "total_invested": inv,
            "shares": shrs,
            "current_price": cur_p,
            "current_value": cur_val,
            "daily_change_pct": daily_chg,
            "unrealized_pnl": pnl,
            "unrealized_pnl_pct": pnl_pct
        })

    # Calculate portfolio weights
    for trade in processed_open_trades:
        trade["weight_pct"] = (trade["current_value"] / total_current_value * 100.0) if total_current_value > 0 else 0.0

    total_unrealized_pnl = total_current_value - total_invested
    total_unrealized_pnl_pct = (total_unrealized_pnl / total_invested * 100.0) if total_invested > 0 else 0.0
    total_realized_pnl = sum(float(ct.get("realized_pnl", 0.0)) for ct in closed_trades)

    # ----------------------------------------------------
    # 3. SUMMARY KPI CARDS
    # ----------------------------------------------------
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f"""
        <div class="card" style="padding: 16px; min-height: 90px; text-align: center;">
            <div style="color: #94a3b8; font-size: 0.72rem; font-weight: 700; text-transform: uppercase;">PORTFOLIO VALUE</div>
            <div style="font-size: 1.5rem; font-weight: 800; color: #f8fafc; margin-top: 4px;">${total_current_value:,.2f}</div>
        </div>
        """, unsafe_allow_html=True)
    with k2:
        unr_color = "#38df88" if total_unrealized_pnl >= 0 else "#f87171"
        unr_sign = "+" if total_unrealized_pnl >= 0 else ""
        st.markdown(f"""
        <div class="card" style="padding: 16px; min-height: 90px; text-align: center;">
            <div style="color: #94a3b8; font-size: 0.72rem; font-weight: 700; text-transform: uppercase;">OPEN TRADES GAIN / LOSS</div>
            <div style="font-size: 1.4rem; font-weight: 800; color: {unr_color}; margin-top: 4px;">{unr_sign}${total_unrealized_pnl:,.2f} ({unr_sign}{total_unrealized_pnl_pct:.2f}%)</div>
        </div>
        """, unsafe_allow_html=True)
    with k3:
        st.markdown(f"""
        <div class="card" style="padding: 16px; min-height: 90px; text-align: center;">
            <div style="color: #94a3b8; font-size: 0.72rem; font-weight: 700; text-transform: uppercase;">CAPITAL INVESTED</div>
            <div style="font-size: 1.5rem; font-weight: 800; color: #38bdf8; margin-top: 4px;">${total_invested:,.2f}</div>
        </div>
        """, unsafe_allow_html=True)
    with k4:
        real_color = "#38df88" if total_realized_pnl >= 0 else "#f87171"
        real_sign = "+" if total_realized_pnl >= 0 else ""
        st.markdown(f"""
        <div class="card" style="padding: 16px; min-height: 90px; text-align: center;">
            <div style="color: #94a3b8; font-size: 0.72rem; font-weight: 700; text-transform: uppercase;">CLOSED REALIZED P&L</div>
            <div style="font-size: 1.4rem; font-weight: 800; color: {real_color}; margin-top: 4px;">{real_sign}${total_realized_pnl:,.2f}</div>
        </div>
        """, unsafe_allow_html=True)

    # ----------------------------------------------------
    # 4. PORTFOLIO ASSET ALLOCATION CHART (Above Active Holdings)
    # ----------------------------------------------------
    if processed_open_trades:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        
        top_h1, top_h2 = st.columns([3, 2])
        with top_h1:
            st.markdown('<div class="card-title" style="margin: 0;">Portfolio Asset Allocation</div>', unsafe_allow_html=True)
        with top_h2:
            alloc_view = st.radio(
                "Breakdown Mode",
                ["By Sector", "By Ticker"],
                horizontal=True,
                label_visibility="collapsed",
                key=f"{key_prefix}_paper_alloc_view_toggle"
            )

        if "Ticker" in alloc_view:
            pie_labels = [t["ticker"] for t in processed_open_trades]
            pie_values = [t["current_value"] for t in processed_open_trades]
        else:
            sector_totals = {}
            for t in processed_open_trades:
                sec = t["sector"]
                sector_totals[sec] = sector_totals.get(sec, 0.0) + t["current_value"]
            
            pie_labels = list(sector_totals.keys())
            pie_values = list(sector_totals.values())

        fig_pie = go.Figure(data=[go.Pie(
            labels=pie_labels,
            values=pie_values,
            hole=0.45,
            hoverinfo="label+value+percent",
            textinfo="label+percent",
            marker=dict(colors=["#38bdf8", "#818cf8", "#38df88", "#f472b6", "#fbbf24", "#a78bfa", "#34d399", "#f43f5e"])
        )])
        fig_pie.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#94a3b8"),
            margin=dict(l=20, r=20, t=10, b=10),
            height=280,
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5)
        )
        st.plotly_chart(fig_pie, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('<div style="margin-top: 20px;"></div>', unsafe_allow_html=True)

    # ----------------------------------------------------
    # 5. ACTIVE OPEN POSITIONS TABLE (Detailed Institutional Columns)
    # ----------------------------------------------------
    if processed_open_trades:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        
        t_col1, t_col2 = st.columns([3, 2])
        with t_col1:
            st.markdown(f'<div class="card-title">Active Holdings ({len(processed_open_trades)})</div>', unsafe_allow_html=True)
        with t_col2:
            st.markdown(f"""
            <div style="text-align: right; margin-bottom: 8px;">
                <span style="background: rgba(56, 223, 136, 0.15); color: #38df88; border: 1px solid #38df88; padding: 4px 8px; border-radius: 6px; font-size: 11px; font-weight: 700; margin-right: 6px;">{winning_count} Winning</span>
                <span style="background: rgba(248, 113, 113, 0.15); color: #f87171; border: 1px solid #f87171; padding: 4px 8px; border-radius: 6px; font-size: 11px; font-weight: 700;">{losing_count} Losing</span>
            </div>
            """, unsafe_allow_html=True)
        st.markdown('<div style="margin-top: 10px;"></div>', unsafe_allow_html=True)
        
        # Column Headers Row (10 Dedicated Columns optimized for zero wrapping)
        h_c1, h_c2, h_c3, h_c4, h_c5, h_c6, h_c7, h_c8, h_c9, h_c10 = st.columns([1.2, 1.6, 1.1, 1.4, 1.0, 1.0, 1.3, 1.1, 2.3, 2.6])
        with h_c1:
            st.markdown('<div style="font-size: 0.72rem; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em;">Ticker</div>', unsafe_allow_html=True)
        with h_c2:
            st.markdown('<div style="font-size: 0.72rem; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em;">Sector</div>', unsafe_allow_html=True)
        with h_c3:
            st.markdown('<div style="font-size: 0.72rem; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em;">Entry Price</div>', unsafe_allow_html=True)
        with h_c4:
            st.markdown('<div style="font-size: 0.72rem; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em;">Entry Date</div>', unsafe_allow_html=True)
        with h_c5:
            st.markdown('<div style="font-size: 0.72rem; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em;">Shares</div>', unsafe_allow_html=True)
        with h_c6:
            st.markdown('<div style="font-size: 0.72rem; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em;">Weight %</div>', unsafe_allow_html=True)
        with h_c7:
            st.markdown('<div style="font-size: 0.72rem; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em;">Market Value</div>', unsafe_allow_html=True)
        with h_c8:
            st.markdown('<div style="font-size: 0.72rem; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em;">Today %</div>', unsafe_allow_html=True)
        with h_c9:
            st.markdown('<div style="font-size: 0.72rem; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em;">Gain / Loss</div>', unsafe_allow_html=True)
        with h_c10:
            st.markdown('<div style="font-size: 0.72rem; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; text-align: center;">Actions</div>', unsafe_allow_html=True)

        st.markdown('<hr style="border-color: #334155; margin: 8px 0 14px 0;">', unsafe_allow_html=True)

        for trade in processed_open_trades:
            t_id = trade["id"]
            sym = trade["ticker"]
            sec_name = trade["sector"]
            pnl_c = "#38df88" if trade["unrealized_pnl"] >= 0 else "#f87171"
            pnl_bg = "rgba(56, 223, 136, 0.12)" if trade["unrealized_pnl"] >= 0 else "rgba(248, 113, 113, 0.12)"
            pnl_border = "#38df88" if trade["unrealized_pnl"] >= 0 else "#f87171"
            pnl_s = "+" if trade["unrealized_pnl"] >= 0 else ""

            day_chg = trade["daily_change_pct"]
            day_c = "#38df88" if day_chg >= 0 else "#f87171"
            day_s = "+" if day_chg >= 0 else ""

            row_c1, row_c2, row_c3, row_c4, row_c5, row_c6, row_c7, row_c8, row_c9, row_c10 = st.columns([1.2, 1.6, 1.1, 1.4, 1.0, 1.0, 1.3, 1.1, 2.3, 2.6])
            with row_c1:
                if st.button(f"Analyze {sym}", key=f"{key_prefix}_btn_deep_paper_{t_id}", use_container_width=True):
                    st.session_state.selected_ticker_detail = sym
                    st.rerun()
            with row_c2:
                st.markdown(f'<div style="color:#38bdf8; font-weight:600; font-size:0.82rem; padding-top:6px;">{sec_name}</div>', unsafe_allow_html=True)
            with row_c3:
                st.markdown(f'<div style="font-weight:700; color:#f8fafc; padding-top:6px;">${trade["entry_price"]:,.2f}</div>', unsafe_allow_html=True)
            with row_c4:
                st.markdown(f'<div style="color:#94a3b8; font-size:0.78rem; padding-top:6px;">{trade["entry_date"]}</div>', unsafe_allow_html=True)
            with row_c5:
                st.markdown(f'<div style="font-weight:700; color:#f8fafc; padding-top:6px;">{trade["shares"]:.2f}</div>', unsafe_allow_html=True)
            with row_c6:
                st.markdown(f'<div style="color:#38bdf8; font-size:0.85rem; font-weight:700; padding-top:6px;">{trade["weight_pct"]:.1f}%</div>', unsafe_allow_html=True)
            with row_c7:
                st.markdown(f'<div style="font-weight:700; color:#f8fafc; padding-top:6px;">${trade["current_value"]:,.2f}</div>', unsafe_allow_html=True)
            with row_c8:
                st.markdown(f'<div style="color:{day_c}; font-size:0.85rem; font-weight:700; padding-top:6px;">{day_s}{day_chg:.2f}%</div>', unsafe_allow_html=True)
            with row_c9:
                st.markdown(f"""
                <div style="padding-top: 2px;">
                    <span style="background: {pnl_bg}; color: {pnl_c}; border: 1px solid {pnl_border}; padding: 4px 8px; border-radius: 6px; font-weight: 800; font-size: 0.82rem; display: inline-block; white-space: nowrap;">
                        {pnl_s}${trade['unrealized_pnl']:,.2f} ({pnl_s}{trade['unrealized_pnl_pct']:.2f}%)
                    </span>
                </div>
                """, unsafe_allow_html=True)
            with row_c10:
                bcol1, bcol2, bcol3 = st.columns([1, 1, 1.1])
                with bcol1:
                    if st.button("Edit", key=f"{key_prefix}_btn_edit_paper_{t_id}", use_container_width=True):
                        render_edit_trade_dialog(trade, key_prefix)
                with bcol2:
                    if st.button("Sell", key=f"{key_prefix}_btn_sell_paper_{t_id}", type="primary", use_container_width=True):
                        ok, msg = database.close_paper_trade(t_id, exit_price=trade["current_price"])
                        if ok:
                            st.session_state.active_main_tab = "🎮 Paper Portfolio"
                            st.rerun()
                with bcol3:
                    if st.button("Remove", key=f"{key_prefix}_btn_del_paper_{t_id}", use_container_width=True):
                        database.delete_paper_trade(t_id)
                        st.session_state.active_main_tab = "🎮 Paper Portfolio"
                        st.rerun()

            st.markdown('<hr style="border-color:#1e293b; margin:10px 0;">', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

    # ----------------------------------------------------
    # 6. CLOSED TRADES HISTORY LOG
    # ----------------------------------------------------
    if closed_trades:
        st.markdown('<div style="margin-top: 20px;"></div>', unsafe_allow_html=True)
        with st.expander(f"Closed Trade History ({len(closed_trades)} Trades)", expanded=False):
            for ct in closed_trades:
                c_pnl = float(ct.get("realized_pnl", 0.0))
                c_color = "#38df88" if c_pnl >= 0 else "#f87171"
                c_sign = "+" if c_pnl >= 0 else ""

                cc1, cc2, cc3, cc4 = st.columns([2, 3, 3, 3])
                with cc1:
                    st.write(f"**{ct['ticker']}**")
                with cc2:
                    st.write(f"In: ${ct['entry_price']:,.2f} ({ct['entry_date']})")
                with cc3:
                    st.write(f"Out: ${ct['exit_price']:,.2f} ({ct['exit_date']})")
                with cc4:
                    st.markdown(f"<span style='color:{c_color}; font-weight:800;'>{c_sign}${c_pnl:,.2f}</span>", unsafe_allow_html=True)
                st.markdown('<hr style="border-color:#1e293b; margin:6px 0;">', unsafe_allow_html=True)
