"""
Comprehensive System Health Check (Pytest Compatible)
Tests all modules, database integrity, pattern engine, growth engine,
backtest engine, AI analyst, notifier, and app.py Streamlit entrypoint.
"""
import sys
import os
import sqlite3
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import database

def test_01_module_imports():
    modules = [
        "core.database", "core.local_env",
        "engines.pattern_engine", "engines.growth_engine", "engines.backtest",
        "ai.analyst_engine", "notifications.notifier",
        "scanners.daily_scanner", "scanners.growth_scanner"
    ]
    for mod in modules:
        __import__(mod)

def test_02_database_integrity():
    database.init_db()
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in c.fetchall()]
    conn.close()
    expected = ["scheduler_state", "sent_alerts", "subscribers", "watchlists", "growth_discoveries", "heartbeat_discoveries", "digest_deliveries"]
    missing = [t for t in expected if t not in tables]
    assert not missing, f"Missing tables: {missing}"

def test_03_outcome_columns():
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("PRAGMA table_info(sent_alerts)")
    cols = [r[1] for r in c.fetchall()]
    conn.close()
    outcome_cols = ["entry_price", "stop_loss", "profit_target", "outcome_status",
                    "exit_price", "exit_date", "return_pct", "rsi_at_entry", "vol_mult_at_entry"]
    missing = [col for col in outcome_cols if col not in cols]
    assert not missing, f"Missing outcome columns: {missing}"

def test_04_pattern_engine():
    from engines.pattern_engine import download_stock_data, add_indicators, scan_ticker_for_signals
    df = download_stock_data("AAPL", period="1mo")
    assert df is not None and len(df) > 0
    df = add_indicators(df)
    assert "RSI_14" in df.columns
    signals = scan_ticker_for_signals("AAPL", days_to_scan=5)
    assert isinstance(signals, list)

def test_05_growth_engine():
    from engines.growth_engine import get_volume_metrics, get_google_stock_news
    metrics = get_volume_metrics("AMD")
    assert metrics is not None
    news = get_google_stock_news("NVDA")
    assert isinstance(news, list)

def test_06_backtest_engine():
    from engines.backtest import run_backtest
    result = run_backtest("AAPL")
    assert result is not None and isinstance(result, dict)
    assert "total_trades" in result and "win_rate" in result

def test_07_ai_analyst_engine():
    from ai.analyst_engine import analyze_signal, evaluate_growth_catalyst, is_ai_enabled
    assert callable(analyze_signal)
    assert callable(evaluate_growth_catalyst)
    assert callable(is_ai_enabled)

def test_08_notifier_engine():
    from notifications.notifier import format_alert_email, format_growth_catalyst_email, send_real_email
    assert callable(format_alert_email)
    assert callable(format_growth_catalyst_email)
    assert callable(send_real_email)

def test_09_app_entrypoint():
    import app
    assert hasattr(app, "main")
    assert hasattr(app, "render_stock_detail_page")
    assert hasattr(app, "render_management_dashboard")

def test_10_full_scan_pipeline():
    from engines.pattern_engine import download_stock_data, add_indicators, scan_ticker_for_signals
    df = download_stock_data("MSFT", period="1mo")
    assert df is not None and len(df) > 0
    df = add_indicators(df)
    assert "RSI_14" in df.columns
    signals = scan_ticker_for_signals("MSFT", days_to_scan=5)
    assert isinstance(signals, list)

def test_11_company_profile_in_notifier():
    from notifications.notifier import get_company_profile_info, format_alert_email, format_growth_digest_email
    prof = get_company_profile_info("AAPL")
    assert "sector" in prof and "summary" in prof
    assert prof["sector"] == "Technology"

    mock_signal = {
        "ticker": "AAPL",
        "pattern_type": "Hammer",
        "confidence_score": 85.0,
        "rsi_14": 35.0,
        "vol_mult": 2.0,
        "day1_date": "2026-08-01",
        "day1_close": 220.0,
        "day1_low": 215.0,
        "day1_high": 222.0,
        "day2_close": 221.0
    }
    html_out = format_alert_email(mock_signal, "testtoken")
    assert "Company Overview &amp; Sector" in html_out or "Company Overview & Sector" in html_out or "Sector:" in html_out
    assert "Technology" in html_out

    mock_candidate = [{
        "ticker": "AAPL",
        "growth_score": 9.0,
        "catalyst_type": "Earnings Beat",
        "headline_summary": "Apple reports record revenue.",
        "plain_english_takeaway": "Strong growth catalyst.",
        "vol_mult": 3.0,
        "latest_price": 220.0
    }]
    growth_digest_html = format_growth_digest_email(mock_candidate, "testtoken")
    assert "Sector:" in growth_digest_html
    assert "Technology" in growth_digest_html

