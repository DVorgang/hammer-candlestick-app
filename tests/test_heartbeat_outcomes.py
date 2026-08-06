import os
import sqlite3
import sys
import tempfile

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import database
from migrations import heartbeat_outcomes_v1


@pytest.fixture()
def temp_db(monkeypatch):
    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "heartbeat_test.db")
    monkeypatch.setattr(database, "DB_FILE", temp_db_path)
    database.init_db()
    return temp_db_path


def _insert_heartbeat_discovery(ticker="TSLA", discovery_date="2026-07-06", price=10.0):
    conn = database.get_db_connection()
    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO heartbeat_discoveries (
                    ticker, discovery_date, initial_price, conviction_score,
                    catalyst_type, headline_summary, last_featured_date, created_at
                )
                VALUES (?, ?, ?, 85.0, 'Volume Breakout', 'Test heartbeat', ?, ?);
                """,
                (ticker, discovery_date, price, discovery_date, f"{discovery_date} 14:15:00")
            )
            return cursor.lastrowid
    finally:
        conn.close()


def test_record_heartbeat_discovery_creates_one_live_outcome(temp_db):
    result = database.record_heartbeat_discovery("TSLA", 85.0, "Volume Breakout", "Test", 10.0)

    assert result["discovery_id"]
    assert result["created"] is True

    duplicate = database.record_heartbeat_discovery("TSLA", 87.0, "Volume Breakout", "Updated", 11.0)
    assert duplicate["discovery_id"] == result["discovery_id"]
    assert duplicate["updated"] is True

    conn = database.get_db_connection()
    try:
        rows = conn.execute("SELECT * FROM heartbeat_outcomes;").fetchall()
        assert len(rows) == 1
        assert rows[0]["source_type"] == "live"
        assert rows[0]["entry_model_version"] == "next_open_v1"
        assert rows[0]["outcome_rule_version"] == "heartbeat_v1"
        assert rows[0]["entry_status"] == "pending"
        assert rows[0]["outcome_status"] == "pending"
    finally:
        conn.close()


def test_resolver_uses_next_regular_session_open_and_modeled_levels(monkeypatch, temp_db):
    discovery_id = _insert_heartbeat_discovery()
    database.ensure_heartbeat_outcome_for_discovery(discovery_id)

    hist = pd.DataFrame({
        "Date": pd.to_datetime(["2026-07-07", "2026-07-08"]),
        "Open": [10.00, 10.50],
        "High": [10.50, 12.25],
        "Low": [9.80, 10.20],
        "Close": [10.25, 12.00],
    })

    class FakeTicker:
        def __init__(self, ticker):
            self.ticker = ticker

        def history(self, period="6mo"):
            return hist

    monkeypatch.setattr("yfinance.Ticker", FakeTicker)

    resolved = database.resolve_pending_heartbeat_outcomes()
    assert resolved == 1

    outcome = database.get_all_heartbeat_outcomes(limit=1)[0]
    assert outcome["entry_status"] == "filled"
    assert outcome["entry_date"] == "2026-07-07"
    assert outcome["modeled_entry_price"] == 10.00
    assert outcome["modeled_stop"] == 9.50
    assert outcome["modeled_target"] == 12.00
    assert outcome["outcome_status"] == "win"
    assert outcome["return_pct"] == 0.2
    assert outcome["mfe_pct"] == 0.225
    assert outcome["mae_pct"] == -0.02
    assert outcome["resolution_error"] is None


def test_resolver_is_stop_first_and_flags_same_bar_ambiguity(monkeypatch, temp_db):
    discovery_id = _insert_heartbeat_discovery(ticker="AMD")
    database.ensure_heartbeat_outcome_for_discovery(discovery_id)

    hist = pd.DataFrame({
        "Date": pd.to_datetime(["2026-07-07"]),
        "Open": [10.00],
        "High": [12.10],
        "Low": [9.40],
        "Close": [11.00],
    })

    class FakeTicker:
        def __init__(self, ticker):
            self.ticker = ticker

        def history(self, period="6mo"):
            return hist

    monkeypatch.setattr("yfinance.Ticker", FakeTicker)

    resolved = database.resolve_pending_heartbeat_outcomes()
    assert resolved == 1

    outcome = database.get_all_heartbeat_outcomes(limit=1)[0]
    assert outcome["outcome_status"] == "loss"
    assert outcome["exit_price"] == 9.50
    assert outcome["same_bar_ambiguous"] == 1


def test_migration_dry_run_and_backfill_mapping(temp_db):
    sub_id, _ = database.create_subscriber("legacy@example.com")
    legacy_discovery_id = _insert_heartbeat_discovery(ticker="MSFT", discovery_date="2026-07-06", price=20.0)
    reconstructed_discovery_id = _insert_heartbeat_discovery(ticker="ITGR", discovery_date="2026-07-06", price=30.0)

    conn = database.get_db_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO sent_alerts (
                    subscriber_id, ticker, pattern_type, day1_date, day2_date,
                    entry_price, stop_loss, profit_target, outcome_status,
                    exit_price, exit_date, return_pct
                )
                VALUES (?, 'MSFT', 'Heartbeat_Test', '2026-07-05', '2026-07-06',
                        20.00, 19.00, 24.00, 'win', 24.00, '2026-07-08', 0.2);
                """,
                (sub_id,)
            )
    finally:
        conn.close()

    plan = heartbeat_outcomes_v1.plan_migration(temp_db)
    assert plan["planned_inserts"] == 2
    assert plan["legacy_migrated"] == 1
    assert plan["reconstructed"] == 1

    result = heartbeat_outcomes_v1.apply_migration(temp_db, backup=False)
    assert result["integrity"] == "ok"

    conn = sqlite3.connect(temp_db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM heartbeat_outcomes ORDER BY discovery_id;").fetchall()
        assert len(rows) == 2
        by_id = {row["discovery_id"]: row for row in rows}
        assert by_id[legacy_discovery_id]["source_type"] == "legacy_migrated"
        assert by_id[legacy_discovery_id]["legacy_sent_alert_id"] is not None
        assert by_id[legacy_discovery_id]["modeled_entry_price"] == 20.00
        assert by_id[reconstructed_discovery_id]["source_type"] == "reconstructed"
        assert by_id[reconstructed_discovery_id]["entry_status"] == "pending"
        assert "modeled fill" in by_id[reconstructed_discovery_id]["reconstruction_notes"]
    finally:
        conn.close()
