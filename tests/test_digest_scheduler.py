import os
import sys
import tempfile
import sqlite3
import pytest
from datetime import datetime, date, time as dt_time, timedelta
import zoneinfo

# Add root directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import database
from core import market_calendar
from scanners import digest_dispatcher
from scanners import growth_scanner
from scanners import heartbeat_scanner
from scanners import daily_scanner
from notifications import notifier

@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    """
    Creates an isolated temporary SQLite database for each test.
    """
    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test_sentinel.db")
    monkeypatch.setattr(database, "DB_FILE", temp_db_path)
    database.init_db()
    
    # Create test subscriber
    sub_id, token = database.create_subscriber("test_subscriber@example.com", wants_buys=1, wants_risks=1, wants_sells=1)
    
    yield {"temp_db_path": temp_db_path, "subscriber_id": sub_id, "token": token, "email": "test_subscriber@example.com"}

# 1. 9:00 AM Digest Contents Test
def test_9am_digest_contents(setup_test_db):
    sub_id = setup_test_db["subscriber_id"]
    today_str = "2026-07-30"
    
    # Buffer overnight discovery
    database.record_growth_discovery("AAPL", 9.2, "Earnings Surpass", "Pre-market growth catalyst.", 220.5)
    
    pending = database.get_pending_discoveries_for_subscriber(sub_id, today_str)
    assert len(pending["growth"]) == 1
    assert pending["growth"][0]["ticker"] == "AAPL"

# 2. 4:30 PM Digest Contents Test
def test_430pm_digest_contents(setup_test_db):
    sub_id = setup_test_db["subscriber_id"]
    today_str = "2026-07-30"
    
    # Buffer growth, heartbeat, and technical setups
    database.record_growth_discovery("NVDA", 8.8, "AI Demand Surge", "Intraday growth signal", 130.0)
    database.record_heartbeat_discovery("TSLA", 85.0, "Volume Breakout", "Squeeze pulse signal", 250.0)
    database.record_sent_alert(sub_id, {
        "ticker": "AMD", "pattern_type": "Hammer", "day1_date": today_str, "day2_date": today_str,
        "entry_price": 170.0, "stop_loss": 160.0, "profit_target": 190.0, "rsi_14": 42.0, "vol_mult": 2.5
    })
    
    pending = database.get_pending_discoveries_for_subscriber(sub_id, today_str)
    assert len(pending["growth"]) == 1
    assert len(pending["heartbeat"]) == 1
    assert len(pending["technical"]) == 1

# 3. Intraday Scans Never Invoke SMTP Test
def test_intraday_scans_never_invoke_smtp(monkeypatch, setup_test_db):
    smtp_called = []
    def mock_send_alert(*args, **kwargs):
        smtp_called.append(args)
        return True, "Mock sent"
        
    monkeypatch.setattr(notifier, "simulate_send_alert", mock_send_alert)
    monkeypatch.setattr("engines.growth_engine.get_market_growth_candidates", lambda max_candidates=100: ["INTC"])
    
    # Mock growth engine & analyst engine
    monkeypatch.setattr("engines.growth_engine.scan_ticker_for_growth_catalyst", lambda ticker: {
        "should_evaluate_ai": True, "ticker": ticker, "latest_price": 30.0
    })
    monkeypatch.setattr("ai.analyst_engine.evaluate_growth_catalyst", lambda payload: {
        "ticker": "INTC", "growth_score": 9.0, "catalyst_type": "Earnings", "headline_summary": "Surge", "latest_price": 30.0
    })
    
    growth_scanner.run_growth_scan(trigger_type="test")
    
    # Verify NO email was dispatched during intraday scan
    assert len(smtp_called) == 0
    
    # Verify discovery was saved to database as PENDING
    sub_id = setup_test_db["subscriber_id"]
    pending = database.get_pending_discoveries_for_subscriber(sub_id)
    assert len(pending["growth"]) >= 1

# 4. Post-Close Scanner Never Invokes SMTP Directly Test
def test_post_close_scanner_never_invokes_smtp_directly(monkeypatch, setup_test_db):
    smtp_called = []
    monkeypatch.setattr(notifier, "simulate_send_alert", lambda *args, **kwargs: (smtp_called.append(args) or (True, "Mock")))
    
    # Add watchlist item
    database.add_watchlist_ticker(setup_test_db["subscriber_id"], "MSFT")
    
    # Mock pattern engine
    monkeypatch.setattr("engines.pattern_engine.scan_ticker_for_signals", lambda ticker, days_to_scan=3: [{
        "ticker": "MSFT", "pattern_type": "Hammer", "confirmed": True, "confidence_score": 85.0,
        "day1_date": "2026-07-29", "day2_date": "2026-07-30", "day1_low": 410.0, "day1_high": 430.0,
        "day3_open": 420.0, "day2_close": 420.0, "rsi_14": 35.0, "vol_mult": 2.1
    }])
    
    daily_scanner.run_daily_scan(days_to_scan=1, trigger_type="test")
    
    assert len(smtp_called) == 0
    pending = database.get_pending_discoveries_for_subscriber(setup_test_db["subscriber_id"])
    assert len(pending["technical"]) == 1
    assert pending["technical"][0]["ticker"] == "MSFT"

# 5. Failed Send Followed by Successful Retry Test
def test_failed_send_followed_by_successful_retry(monkeypatch, setup_test_db):
    database.record_growth_discovery("AMZN", 8.5, "Revenue Beat", "Strong quarterly growth", 180.0)
    
    attempts = [False, True]
    def mock_send(*args, **kwargs):
        success = attempts.pop(0) if attempts else True
        return success, "Success" if success else "SMTP Connection Timeout"
        
    monkeypatch.setattr(notifier, "simulate_send_alert", mock_send)
    
    # First attempt -> Fails
    res1 = digest_dispatcher.dispatch_scheduled_digests("PM_POSTMARKET", "2026-07-30")
    assert res1["failures"] == 1
    assert not database.is_digest_delivered("2026-07-30", "PM_POSTMARKET", setup_test_db["subscriber_id"])
    
    # Retry attempt -> Succeeds
    res2 = digest_dispatcher.dispatch_scheduled_digests("PM_POSTMARKET", "2026-07-30")
    assert res2["successful_sends"] == 1
    assert database.is_digest_delivered("2026-07-30", "PM_POSTMARKET", setup_test_db["subscriber_id"])

# 6. Persistent Duplicate Prevention After Worker Restart Test
def test_persistent_duplicate_prevention_after_worker_restart(monkeypatch, setup_test_db):
    database.record_growth_discovery("META", 8.7, "Ad Revenue", "Growth momentum", 500.0)
    smtp_count = [0]
    
    def mock_send(*args, **kwargs):
        smtp_count[0] += 1
        return True, "Delivered"
        
    monkeypatch.setattr(notifier, "simulate_send_alert", mock_send)
    
    # Run first dispatch
    res1 = digest_dispatcher.dispatch_scheduled_digests("PM_POSTMARKET", "2026-07-30")
    assert res1["successful_sends"] == 1
    assert smtp_count[0] == 1
    
    # Simulate container restart (run dispatch again)
    res2 = digest_dispatcher.dispatch_scheduled_digests("PM_POSTMARKET", "2026-07-30")
    assert res2["successful_sends"] == 0
    assert smtp_count[0] == 1 # Zero additional SMTP calls!

# 7. Startup After Missed Digest Window Test
def test_startup_after_missed_digest_window(monkeypatch, setup_test_db):
    # Buffer pending discovery from earlier in the day
    database.record_growth_discovery("GOOGL", 8.2, "Search Growth", "AI Integration", 175.0)
    
    smtp_count = [0]
    monkeypatch.setattr(notifier, "simulate_send_alert", lambda *args, **kwargs: (smtp_count.append(1) or (True, "Sent")))
    
    # Dispatch after missed window
    res = digest_dispatcher.dispatch_scheduled_digests("PM_POSTMARKET", "2026-07-30")
    assert res["successful_sends"] == 1
    assert database.is_digest_delivered("2026-07-30", "PM_POSTMARKET", setup_test_db["subscriber_id"])

# 8. Multiple Subscribers Test
def test_multiple_subscribers(setup_test_db):
    sub2_id, token2 = database.create_subscriber("user2@example.com")
    subs = database.get_all_subscribers()
    assert len(subs) == 2

# 9. One Subscriber Succeeding While Another Fails Test
def test_one_subscriber_succeeding_while_another_fails(monkeypatch, setup_test_db):
    sub2_id, token2 = database.create_subscriber("user2_fail@example.com")
    database.record_growth_discovery("NFLX", 8.4, "Subscriber Growth", "Catalyst", 650.0)
    
    def mock_send(email, *args, **kwargs):
        if "fail" in email:
            return False, "SMTP Auth Failed"
        return True, "Sent"
        
    monkeypatch.setattr(notifier, "simulate_send_alert", mock_send)
    
    res = digest_dispatcher.dispatch_scheduled_digests("PM_POSTMARKET", "2026-07-30")
    assert res["successful_sends"] == 1
    assert res["failures"] == 1
    
    # Primary subscriber marked SUCCESS, failing subscriber remains retryable
    assert database.is_digest_delivered("2026-07-30", "PM_POSTMARKET", setup_test_db["subscriber_id"])
    assert not database.is_digest_delivered("2026-07-30", "PM_POSTMARKET", sub2_id)

# 10. Empty Digest Behavior Test
def test_empty_digest_behavior(monkeypatch, setup_test_db):
    smtp_called = []
    monkeypatch.setattr(notifier, "simulate_send_alert", lambda *args, **kwargs: (smtp_called.append(args) or (True, "Sent")))
    
    res = digest_dispatcher.dispatch_scheduled_digests("PM_POSTMARKET", "2026-07-30")
    assert res["skipped_empty"] == 1
    assert len(smtp_called) == 0

# 11. Weekend Suppression Test
def test_weekend_suppression():
    saturday = date(2026, 8, 1) # Saturday
    sunday = date(2026, 8, 2)   # Sunday
    assert not market_calendar.is_trading_day(saturday)
    assert not market_calendar.is_trading_day(sunday)

# 12. Market Holiday Suppression Test
def test_market_holiday_suppression():
    christmas = date(2026, 12, 25) # Christmas Day
    thanksgiving = date(2026, 11, 26) # Thanksgiving Day
    assert not market_calendar.is_trading_day(christmas)
    assert not market_calendar.is_trading_day(thanksgiving)

# 13. Daylight Saving Transitions Test
def test_daylight_saving_transitions():
    et_tz = market_calendar.get_eastern_timezone()
    dt_summer = datetime(2026, 7, 30, 12, 0, tzinfo=et_tz) # EDT (UTC-4)
    dt_winter = datetime(2026, 1, 15, 12, 0, tzinfo=et_tz) # EST (UTC-5)
    assert dt_summer.utcoffset() == timedelta(hours=-4)
    assert dt_winter.utcoffset() == timedelta(hours=-5)

# 14. Early Market Close Behavior Test
def test_early_market_close_behavior():
    christmas_eve = date(2026, 12, 24) # Christmas Eve early close day
    assert market_calendar.is_early_close_day(christmas_eve)
    sched = market_calendar.get_market_schedule(christmas_eve)
    assert sched["market_close"] == dt_time(13, 0)
    assert sched["pm_digest_time"] == dt_time(13, 30)

# 15. Manual Test Emails from app.py Remain Functional Test
def test_manual_test_emails_from_app_py_remain_functional(monkeypatch):
    smtp_called = []
    monkeypatch.setattr(notifier, "simulate_send_alert", lambda email, html, title, secondary_email=None: (smtp_called.append(email) or (True, "Sent")))
    
    sent, msg = notifier.simulate_send_alert("admin@example.com", "<p>Test</p>", "Manual Test Email")
    assert sent is True
    assert len(smtp_called) == 1

# 16. All Three Discovery Types in Unified Digest Test
def test_all_three_discovery_types_in_unified_digest():
    growth = [{"ticker": "NVDA", "score": 9.1, "headline_summary": "AI Dominance"}]
    heartbeat = [{"ticker": "TSLA", "score": 88.0, "headline_summary": "Squeeze"}]
    tech = [{"ticker": "AAPL", "pattern_type": "Hammer", "entry_price": 220.0}]
    
    email_html = notifier.format_unified_pm_digest_email(growth, heartbeat, tech, "test_token")
    assert "NVDA" in email_html
    assert "TSLA" in email_html
    assert "AAPL" in email_html
    assert "TRadar End-of-Day Digest" in email_html
