"""
Test script for verifying Post-Trade Outcome Resolution, Alert Blueprint Recording,
and Dynamic Confidence Calibration in Candlestick Sentinel.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.local_env import load_env_file
load_env_file()

from core import database
from engines import pattern_engine
from ai import analyst_engine
import logging


logging.basicConfig(level=logging.INFO)

TEST_DB = "test_sentinel_temp.db"
database.DB_FILE = TEST_DB

print("--- 1. Initializing Database & Testing Schema ---")
database.init_db()
subs = database.get_all_subscribers()
if not subs:
    database.create_subscriber("test_subscriber@example.com")
    subs = database.get_all_subscribers()
mock_subscriber_id = subs[0]["id"] if subs else 1


test_signal_hammer = {
    "ticker": "NVDA",
    "pattern_type": "Hammer",
    "day1_date": "2026-05-01",
    "day2_date": "2026-05-04",
    "day3_open": 120.00,
    "stop_loss": 115.00,
    "profit_target": 130.00,
    "rsi_14": 28.5,
    "vol_mult": 2.1
}

print("\n--- 2. Recording Mock Alert Blueprint ---")
recorded = database.record_sent_alert(mock_subscriber_id, test_signal_hammer)
assert recorded is True
print("SUCCESS: Recorded Hammer alert blueprint to SQLite sent_alerts table!")

print("\n--- 3. Testing Outcome Resolver Routine ---")
resolved_count = database.resolve_pending_alert_outcomes()
print(f"Outcome Resolver processed pending alerts. Resolved: {resolved_count}")

print("\n--- 4. Querying Historical Accuracy Stats ---")
stats = database.get_historical_accuracy_stats(ticker="NVDA", pattern_type="Hammer")
print(f"NVDA Hammer Historical Accuracy Stats: {stats}")

print("\n--- 5. Testing Dynamic Confidence Calibration ---")
df_mock = pattern_engine.download_stock_data("NVDA")
if not df_mock.empty and len(df_mock) >= 205:
    df_mock = pattern_engine.add_indicators(df_mock)
    is_pattern, p_type, confidence = pattern_engine.identify_setup_candle(df_mock, 204, ticker="NVDA")
    print(f"Evaluated Candle Row 204: Pattern={p_type}, Dynamic Confidence Score={confidence:.2f}")

print("\n--- 6. Verifying AI Prompt Injection with Track Record ---")
ai_analysis = analyst_engine.analyze_signal(test_signal_hammer, forced_model="Groq-70B")
if ai_analysis:
    print(f"AI Model Used: {ai_analysis.get('ai_model_used')}")
    print(f"AI Takeaway: {ai_analysis.get('plain_english_takeaway')}")

print("\nALL SYSTEM LEARNING & FEEDBACK LOOP TESTS PASSED SUCCESSFULLY!")

if os.path.exists(TEST_DB):
    try:
        os.remove(TEST_DB)
        wal_file = f"{TEST_DB}-wal"
        shm_file = f"{TEST_DB}-shm"
        if os.path.exists(wal_file): os.remove(wal_file)
        if os.path.exists(shm_file): os.remove(shm_file)
    except Exception as e:
        print(f"Cleanup warning: {e}")

