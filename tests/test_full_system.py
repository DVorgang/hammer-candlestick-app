"""
Comprehensive System Health Check
Tests all modules, database integrity, pattern engine, growth engine,
backtest engine, AI analyst, notifier, and app.py Streamlit entrypoint.
"""
import sys
import os
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

results = []

def test(name, fn):
    try:
        fn()
        results.append(("PASS", name))
        print(f"  [PASS] {name}")
    except Exception as e:
        results.append(("FAIL", name, str(e)))
        print(f"  [FAIL] {name}: {e}")

# ============================================================
# 1. MODULE IMPORTS
# ============================================================
print("\n=== 1. MODULE IMPORTS ===")

modules = [
    "core.database", "core.local_env",
    "engines.pattern_engine", "engines.growth_engine", "engines.backtest",
    "ai.analyst_engine", "notifications.notifier",
    "scanners.daily_scanner", "scanners.growth_scanner"
]
for mod in modules:
    test(f"Import {mod}", lambda m=mod: __import__(m))

# ============================================================
# 2. DATABASE INTEGRITY
# ============================================================
print("\n=== 2. DATABASE INTEGRITY ===")

db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sentinel.db")

def _check_tables():
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in c.fetchall()]
    conn.close()
    expected = ["scheduler_state", "sent_alerts", "subscribers", "watchlists"]
    missing = [t for t in expected if t not in tables]
    print(f"    -> Tables found: {tables}")
    assert not missing, f"Missing tables: {missing}"
test("All required tables exist", _check_tables)

def _check_outcome_columns():
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("PRAGMA table_info(sent_alerts)")
    cols = [r[1] for r in c.fetchall()]
    conn.close()
    outcome_cols = ["entry_price", "stop_loss", "profit_target", "outcome_status",
                    "exit_price", "exit_date", "return_pct", "rsi_at_entry", "vol_mult_at_entry"]
    missing = [col for col in outcome_cols if col not in cols]
    assert not missing, f"Missing outcome columns: {missing}"
test("Outcome tracking columns in sent_alerts", _check_outcome_columns)

def _check_subscribers():
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM subscribers")
    count = c.fetchone()[0]
    conn.close()
    print(f"    -> {count} subscriber(s)")
    assert count >= 1, "No subscribers found"
test("At least 1 subscriber exists", _check_subscribers)

def _check_watchlist():
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM watchlists")
    count = c.fetchone()[0]
    conn.close()
    print(f"    -> {count} watchlist ticker(s)")
    assert count >= 1, "No watchlist tickers found"
test("At least 1 watchlist ticker exists", _check_watchlist)

# ============================================================
# 3. PATTERN ENGINE
# ============================================================
print("\n=== 3. PATTERN ENGINE ===")

def _test_download_stock():
    from engines.pattern_engine import download_stock_data
    df = download_stock_data("AAPL", period="5d")
    assert df is not None and len(df) > 0, "No data returned for AAPL"
    required = ["Open", "High", "Low", "Close", "Volume"]
    for col in required:
        assert col in df.columns, f"Missing column: {col}"
    print(f"    -> Got {len(df)} bars for AAPL")
test("download_stock_data('AAPL', 5d)", _test_download_stock)

def _test_add_indicators():
    from engines.pattern_engine import download_stock_data, add_indicators
    df = download_stock_data("AAPL", period="3mo")
    df = add_indicators(df)
    assert "RSI_14" in df.columns, "RSI_14 column not found"
    assert "SMA_50" in df.columns, "SMA_50 column not found"
    last_rsi = df["RSI_14"].dropna().iloc[-1]
    print(f"    -> AAPL latest RSI(14): {last_rsi:.2f}")
    assert 0 <= last_rsi <= 100, f"RSI out of range: {last_rsi}"
test("add_indicators (RSI, SMAs)", _test_add_indicators)

def _test_scan_ticker():
    from engines.pattern_engine import scan_ticker_for_signals
    signals = scan_ticker_for_signals("AAPL", days_to_scan=10)
    assert isinstance(signals, list), f"Expected list, got {type(signals)}"
    print(f"    -> AAPL signals found (last 10 days): {len(signals)}")
test("scan_ticker_for_signals('AAPL', 10)", _test_scan_ticker)

# ============================================================
# 4. GROWTH ENGINE
# ============================================================
print("\n=== 4. GROWTH ENGINE ===")

def _test_volume_metrics():
    from engines.growth_engine import get_volume_metrics
    result = get_volume_metrics("AMD")
    assert result is not None, "get_volume_metrics returned None"
    print(f"    -> AMD volume metrics: {result}")
test("get_volume_metrics('AMD')", _test_volume_metrics)

def _test_google_news():
    from engines.growth_engine import get_google_stock_news
    headlines = get_google_stock_news("NVDA")
    assert isinstance(headlines, list), f"Expected list, got {type(headlines)}"
    print(f"    -> NVDA news headlines: {len(headlines)}")
test("get_google_stock_news('NVDA')", _test_google_news)

# ============================================================
# 5. BACKTEST ENGINE
# ============================================================
print("\n=== 5. BACKTEST ENGINE ===")

def _test_backtest():
    from engines.backtest import run_backtest
    result = run_backtest("AAPL")
    assert result is not None, "run_backtest returned None"
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    expected_keys = ["total_trades", "win_rate", "trades"]
    for k in expected_keys:
        assert k in result, f"Missing key: {k}"
    print(f"    -> AAPL backtest: {result['total_trades']} trades, {result['win_rate']:.1f}% win rate")
test("run_backtest('AAPL')", _test_backtest)

# ============================================================
# 6. AI ANALYST ENGINE (function existence only)
# ============================================================
print("\n=== 6. AI ANALYST ENGINE ===")

def _test_ai_fns():
    from ai.analyst_engine import analyze_signal, evaluate_growth_catalyst, is_ai_enabled
    assert callable(analyze_signal), "analyze_signal not callable"
    assert callable(evaluate_growth_catalyst), "evaluate_growth_catalyst not callable"
    assert callable(is_ai_enabled), "is_ai_enabled not callable"
    enabled = is_ai_enabled()
    print(f"    -> AI enabled: {enabled}")
test("AI functions exist (analyze_signal, evaluate_growth_catalyst, is_ai_enabled)", _test_ai_fns)

# ============================================================
# 7. NOTIFIER ENGINE (function existence only)
# ============================================================
print("\n=== 7. NOTIFIER ENGINE ===")

def _test_notifier_fns():
    from notifications.notifier import format_alert_email, format_growth_catalyst_email, send_real_email
    assert callable(format_alert_email), "format_alert_email not callable"
    assert callable(format_growth_catalyst_email), "format_growth_catalyst_email not callable"
    assert callable(send_real_email), "send_real_email not callable"
test("Notifier functions exist (format_alert_email, format_growth_catalyst_email, send_real_email)", _test_notifier_fns)

# ============================================================
# 8. APP.PY ENTRYPOINT
# ============================================================
print("\n=== 8. APP.PY ENTRYPOINT ===")

def _test_app():
    import app
    assert hasattr(app, "main"), "app.main() not found"
    assert hasattr(app, "render_stock_detail_page"), "render_stock_detail_page not found"
    assert hasattr(app, "render_management_dashboard"), "render_management_dashboard not found"
test("app.py: main, render_stock_detail_page, render_management_dashboard", _test_app)

# ============================================================
# 9. CROSS-MODULE INTEGRATION: Database API
# ============================================================
print("\n=== 9. CROSS-MODULE INTEGRATION ===")

def _test_db_api():
    import core.database as db
    # Test subscriber lookup
    subs = db.get_all_subscribers()
    assert isinstance(subs, list) and len(subs) >= 1, "No subscribers returned"
    sub = subs[0]
    # Test watchlist retrieval
    watchlist = db.get_watchlist(sub["id"])
    assert isinstance(watchlist, list), f"Expected list, got {type(watchlist)}"
    print(f"    -> Subscriber #{sub['id']} ({sub.get('email','?')}): {len(watchlist)} tickers")
    # Test outcome resolver
    db.resolve_pending_alert_outcomes()
    print("    -> resolve_pending_alert_outcomes() ran cleanly")
test("Database API: get_all_subscribers, get_watchlist, resolve_pending_alert_outcomes", _test_db_api)

def _test_full_scan_pipeline():
    """Test that the daily scanner can analyze a single ticker end-to-end"""
    from engines.pattern_engine import download_stock_data, add_indicators, scan_ticker_for_signals
    df = download_stock_data("MSFT", period="1mo")
    assert df is not None and len(df) > 0
    df = add_indicators(df)
    assert "RSI_14" in df.columns
    signals = scan_ticker_for_signals("MSFT", days_to_scan=5)
    assert isinstance(signals, list)
    print(f"    -> MSFT full pipeline: {len(df)} bars, {len(signals)} signals")
test("Full scan pipeline: download -> indicators -> scan (MSFT)", _test_full_scan_pipeline)

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "=" * 60)
passes = sum(1 for r in results if r[0] == "PASS")
fails = sum(1 for r in results if r[0] == "FAIL")
total = len(results)

if fails == 0:
    print(f"✅ ALL {total} TESTS PASSED — System is fully operational!")
else:
    print(f"RESULTS: {passes}/{total} PASSED, {fails}/{total} FAILED")
    print("\nFAILED TESTS:")
    for r in results:
        if r[0] == "FAIL":
            print(f"  ✗ {r[1]}: {r[2]}")

print("=" * 60)
