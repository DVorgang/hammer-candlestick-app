import os
import sqlite3
import sys
import tempfile
from datetime import datetime

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

        def history(self, *args, **kwargs):
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

        def history(self, *args, **kwargs):
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
    assert plan["conflicts"] == []

    result = heartbeat_outcomes_v1.apply_migration(temp_db, backup=False)
    assert result["integrity"] == "ok"

    conn = sqlite3.connect(temp_db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM heartbeat_outcomes ORDER BY discovery_id;").fetchall()
        assert len(rows) == 2
        by_id = {row["discovery_id"]: row for row in rows}
        assert by_id[legacy_discovery_id]["source_type"] == "legacy_migrated"
        assert by_id[legacy_discovery_id]["modeled_entry_rule"] == "legacy_close_or_day3_open"
        assert by_id[legacy_discovery_id]["entry_model_version"] == "legacy_precanonical_v0"
        assert by_id[legacy_discovery_id]["outcome_rule_version"] == "legacy_heartbeat_v0"
        assert by_id[legacy_discovery_id]["legacy_sent_alert_id"] is not None
        assert by_id[legacy_discovery_id]["modeled_entry_price"] == 20.00
        assert by_id[reconstructed_discovery_id]["source_type"] == "reconstructed"
        assert by_id[reconstructed_discovery_id]["entry_model_version"] == "next_open_v1"
        assert by_id[reconstructed_discovery_id]["entry_status"] == "pending"
        assert "modeled fill" in by_id[reconstructed_discovery_id]["reconstruction_notes"]
    finally:
        conn.close()


def test_migration_is_idempotent_and_preserves_legacy_sent_alerts(temp_db):
    sub_id, _ = database.create_subscriber("legacy2@example.com")
    _insert_heartbeat_discovery(ticker="MSFT", discovery_date="2026-07-06", price=20.0)

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
        before = [tuple(row) for row in conn.execute("SELECT * FROM sent_alerts ORDER BY id;").fetchall()]
    finally:
        conn.close()

    heartbeat_outcomes_v1.apply_migration(temp_db, backup=False)
    heartbeat_outcomes_v1.apply_migration(temp_db, backup=False)

    conn = sqlite3.connect(temp_db)
    conn.row_factory = sqlite3.Row
    try:
        assert conn.execute("SELECT COUNT(*) FROM heartbeat_outcomes;").fetchone()[0] == 1
        after = [tuple(row) for row in conn.execute("SELECT * FROM sent_alerts ORDER BY id;").fetchall()]
        assert after == before
    finally:
        conn.close()


def test_migration_detects_conflicting_legacy_matches(temp_db):
    sub_1, _ = database.create_subscriber("legacy-a@example.com")
    sub_2, _ = database.create_subscriber("legacy-b@example.com")
    _insert_heartbeat_discovery(ticker="MSFT", discovery_date="2026-07-06", price=20.0)

    conn = database.get_db_connection()
    try:
        with conn:
            for sub_id, entry in [(sub_1, 20.0), (sub_2, 21.0)]:
                conn.execute(
                    """
                    INSERT INTO sent_alerts (
                        subscriber_id, ticker, pattern_type, day1_date, day2_date,
                        entry_price, stop_loss, profit_target, outcome_status
                    )
                    VALUES (?, 'MSFT', 'Heartbeat_Test', '2026-07-05', '2026-07-06',
                            ?, 19.00, 24.00, 'pending');
                    """,
                    (sub_id, entry)
                )
    finally:
        conn.close()

    plan = heartbeat_outcomes_v1.plan_migration(temp_db)
    assert len(plan["conflicts"]) == 1
    with pytest.raises(RuntimeError, match="Conflicting legacy Heartbeat"):
        heartbeat_outcomes_v1.apply_migration(temp_db, backup=False)


def test_migration_syncs_historical_delivery_first_at(temp_db):
    sub_id, _ = database.create_subscriber("delivery@example.com")
    discovery_id = _insert_heartbeat_discovery(ticker="MSFT", discovery_date="2026-07-06", price=20.0)

    conn = database.get_db_connection()
    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO digest_deliveries (
                    trading_date, digest_type, subscriber_id, subscriber_email, status,
                    discovery_ids_json, discoveries_count, delivered_at
                )
                VALUES ('2026-07-06', 'PM_POSTMARKET', ?, 'delivery@example.com',
                        'SUCCESS', '[1]', 1, '2026-07-06 16:35:00');
                """,
                (sub_id,)
            )
            conn.execute(
                """
                INSERT INTO digest_discovery_items (digest_delivery_id, source_type, source_id, ticker, score)
                VALUES (?, 'heartbeat', ?, 'MSFT', 85.0);
                """,
                (cursor.lastrowid, discovery_id)
            )
    finally:
        conn.close()

    heartbeat_outcomes_v1.apply_migration(temp_db, backup=False)
    outcome = database.get_all_heartbeat_outcomes(limit=1)[0]
    assert outcome["delivery_first_at"] == "2026-07-06 16:35:00"


def test_multiple_subscriber_deliveries_keep_one_outcome_and_earliest_delivery(temp_db):
    sub_1, _ = database.create_subscriber("delivery-a@example.com")
    sub_2, _ = database.create_subscriber("delivery-b@example.com")
    discovery_id = _insert_heartbeat_discovery(ticker="MSFT", discovery_date="2026-07-06", price=20.0)
    database.ensure_heartbeat_outcome_for_discovery(discovery_id)

    conn = database.get_db_connection()
    try:
        with conn:
            for sub_id, email, delivered_at in [
                (sub_1, "delivery-a@example.com", "2026-07-06 16:40:00"),
                (sub_2, "delivery-b@example.com", "2026-07-06 16:35:00"),
            ]:
                cursor = conn.execute(
                    """
                    INSERT INTO digest_deliveries (
                        trading_date, digest_type, subscriber_id, subscriber_email, status,
                        discovery_ids_json, discoveries_count, delivered_at
                    )
                    VALUES ('2026-07-06', 'PM_POSTMARKET', ?, ?, 'SUCCESS', '[1]', 1, ?);
                    """,
                    (sub_id, email, delivered_at)
                )
                conn.execute(
                    """
                    INSERT INTO digest_discovery_items (digest_delivery_id, source_type, source_id, ticker, score)
                    VALUES (?, 'heartbeat', ?, 'MSFT', 85.0);
                    """,
                    (cursor.lastrowid, discovery_id)
                )
            database.sync_heartbeat_delivery_first_at(discovery_id, conn=conn)
    finally:
        conn.close()

    conn = database.get_db_connection()
    try:
        rows = conn.execute("SELECT * FROM heartbeat_outcomes;").fetchall()
        assert len(rows) == 1
        assert rows[0]["delivery_first_at"] == "2026-07-06 16:35:00"
    finally:
        conn.close()


def test_sqlite_backup_uses_online_backup_api(temp_db):
    _insert_heartbeat_discovery(ticker="MSFT", discovery_date="2026-07-06", price=20.0)
    backup_path = heartbeat_outcomes_v1.create_sqlite_backup(temp_db)
    assert os.path.exists(backup_path)

    conn = sqlite3.connect(backup_path)
    try:
        assert conn.execute("PRAGMA integrity_check;").fetchone()[0] == "ok"
        assert conn.execute("SELECT COUNT(*) FROM heartbeat_discoveries;").fetchone()[0] == 1
    finally:
        conn.close()


def test_resolver_persists_pending_mfe_mae_and_clears_transient_error(monkeypatch, temp_db):
    discovery_id = _insert_heartbeat_discovery(ticker="PEND")
    database.ensure_heartbeat_outcome_for_discovery(discovery_id)
    conn = database.get_db_connection()
    try:
        with conn:
            conn.execute(
                "UPDATE heartbeat_outcomes SET resolution_error = 'temporary provider failure' WHERE discovery_id = ?;",
                (discovery_id,)
            )
    finally:
        conn.close()

    hist = pd.DataFrame({
        "Date": pd.to_datetime(["2026-07-07", "2026-07-08"]),
        "Open": [10.00, 10.50],
        "High": [10.80, 11.00],
        "Low": [9.80, 10.10],
        "Close": [10.25, 10.75],
    })

    class FakeTicker:
        def __init__(self, ticker):
            self.ticker = ticker

        def history(self, *args, **kwargs):
            return hist

    monkeypatch.setattr("yfinance.Ticker", FakeTicker)
    assert database.resolve_pending_heartbeat_outcomes() == 0

    outcome = database.get_all_heartbeat_outcomes(limit=1)[0]
    assert outcome["outcome_status"] == "pending"
    assert outcome["mfe_pct"] == 0.1
    assert outcome["mae_pct"] == -0.02
    assert outcome["resolution_data_asof"] is not None
    assert outcome["resolution_error"] is None


def test_resolver_does_not_timeout_on_intraday_tenth_bar(monkeypatch, temp_db):
    discovery_id = _insert_heartbeat_discovery(ticker="TIME", discovery_date="2026-07-06")
    database.ensure_heartbeat_outcome_for_discovery(discovery_id)

    dates = pd.date_range("2026-07-07", periods=10, freq="B")
    hist = pd.DataFrame({
        "Date": dates,
        "Open": [10.00] * 10,
        "High": [10.50] * 10,
        "Low": [9.80] * 10,
        "Close": [10.10] * 10,
    })

    class FakeTicker:
        def __init__(self, ticker):
            self.ticker = ticker

        def history(self, *args, **kwargs):
            return hist

    from core import market_calendar

    monkeypatch.setattr("yfinance.Ticker", FakeTicker)
    monkeypatch.setattr(
        market_calendar,
        "get_now_eastern",
        lambda: datetime(2026, 7, 20, 12, 0, tzinfo=market_calendar.get_eastern_timezone())
    )

    assert database.resolve_pending_heartbeat_outcomes() == 0
    outcome = database.get_all_heartbeat_outcomes(limit=1)[0]
    assert outcome["outcome_status"] == "pending"


def test_entry_populates_after_open_before_close_without_outcome_timeout(monkeypatch, temp_db):
    discovery_id = _insert_heartbeat_discovery(ticker="OPEN", discovery_date="2026-07-06")
    database.ensure_heartbeat_outcome_for_discovery(discovery_id)

    hist = pd.DataFrame({
        "Date": pd.to_datetime(["2026-07-07"]),
        "Open": [10.00],
        "High": [10.20],
        "Low": [9.90],
        "Close": [10.10],
    })

    class FakeTicker:
        def __init__(self, ticker):
            self.ticker = ticker

        def history(self, *args, **kwargs):
            return hist

    from core import market_calendar

    monkeypatch.setattr("yfinance.Ticker", FakeTicker)
    monkeypatch.setattr(
        market_calendar,
        "get_now_eastern",
        lambda: datetime(2026, 7, 7, 10, 0, tzinfo=market_calendar.get_eastern_timezone())
    )

    assert database.resolve_pending_heartbeat_outcomes() == 0
    outcome = database.get_all_heartbeat_outcomes(limit=1)[0]
    assert outcome["entry_status"] == "filled"
    assert outcome["entry_date"] == "2026-07-07"
    assert outcome["modeled_entry_price"] == 10.0
    assert outcome["modeled_stop"] == 9.5
    assert outcome["modeled_target"] == 12.0
    assert outcome["outcome_status"] == "pending"


def test_entry_stays_pending_before_regular_market_open(monkeypatch, temp_db):
    discovery_id = _insert_heartbeat_discovery(ticker="PREMKT", discovery_date="2026-07-06")
    database.ensure_heartbeat_outcome_for_discovery(discovery_id)

    hist = pd.DataFrame({
        "Date": pd.to_datetime(["2026-07-07"]),
        "Open": [10.00],
        "High": [10.20],
        "Low": [9.90],
        "Close": [10.10],
    })

    class FakeTicker:
        def __init__(self, ticker):
            self.ticker = ticker

        def history(self, *args, **kwargs):
            return hist

    from core import market_calendar

    monkeypatch.setattr("yfinance.Ticker", FakeTicker)
    monkeypatch.setattr(
        market_calendar,
        "get_now_eastern",
        lambda: datetime(2026, 7, 7, 9, 0, tzinfo=market_calendar.get_eastern_timezone())
    )

    assert database.resolve_pending_heartbeat_outcomes() == 0
    outcome = database.get_all_heartbeat_outcomes(limit=1)[0]
    assert outcome["entry_status"] == "pending"
    assert outcome["modeled_entry_price"] is None
    assert outcome["modeled_stop"] is None
    assert outcome["modeled_target"] is None
    assert outcome["outcome_status"] == "pending"


def test_completed_tenth_bar_produces_timeout(monkeypatch, temp_db):
    discovery_id = _insert_heartbeat_discovery(ticker="DONE", discovery_date="2026-07-06")
    database.ensure_heartbeat_outcome_for_discovery(discovery_id)

    dates = pd.date_range("2026-07-07", periods=10, freq="B")
    hist = pd.DataFrame({
        "Date": dates,
        "Open": [10.00] * 10,
        "High": [10.50] * 10,
        "Low": [9.80] * 10,
        "Close": [10.10] * 10,
    })

    class FakeTicker:
        def __init__(self, ticker):
            self.ticker = ticker

        def history(self, *args, **kwargs):
            return hist

    from core import market_calendar

    monkeypatch.setattr("yfinance.Ticker", FakeTicker)
    monkeypatch.setattr(
        market_calendar,
        "get_now_eastern",
        lambda: datetime(2026, 7, 20, 17, 0, tzinfo=market_calendar.get_eastern_timezone())
    )

    assert database.resolve_pending_heartbeat_outcomes() == 1
    outcome = database.get_all_heartbeat_outcomes(limit=1)[0]
    assert outcome["outcome_status"] == "timeout"
    assert outcome["exit_date"] == "2026-07-20"
    assert outcome["return_pct"] == 0.01


def test_provider_failure_records_error_without_bad_outcome(monkeypatch, temp_db):
    discovery_id = _insert_heartbeat_discovery(ticker="FAIL")
    database.ensure_heartbeat_outcome_for_discovery(discovery_id)

    class FakeTicker:
        def __init__(self, ticker):
            self.ticker = ticker

        def history(self, *args, **kwargs):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr("yfinance.Ticker", FakeTicker)
    assert database.resolve_pending_heartbeat_outcomes() == 0

    outcome = database.get_all_heartbeat_outcomes(limit=1)[0]
    assert outcome["outcome_status"] == "pending"
    assert "provider unavailable" in outcome["resolution_error"]


def test_history_fetch_uses_date_start_and_raw_adjustment_policy(monkeypatch, temp_db):
    discovery_id = _insert_heartbeat_discovery(ticker="POLICY", discovery_date="2026-07-06")
    database.ensure_heartbeat_outcome_for_discovery(discovery_id)
    calls = []

    hist = pd.DataFrame({
        "Date": pd.to_datetime(["2026-07-07"]),
        "Open": [10.00],
        "High": [10.20],
        "Low": [9.90],
        "Close": [10.10],
    })

    class FakeTicker:
        def __init__(self, ticker):
            self.ticker = ticker

        def history(self, *args, **kwargs):
            calls.append(kwargs)
            return hist

    monkeypatch.setattr("yfinance.Ticker", FakeTicker)
    database.resolve_pending_heartbeat_outcomes()

    assert calls
    assert calls[0]["start"] == "2026-06-26"
    assert calls[0]["auto_adjust"] is False


def test_record_heartbeat_discovery_rolls_back_when_outcome_creation_fails(monkeypatch, temp_db):
    def fail_outcome(*args, **kwargs):
        return None

    monkeypatch.setattr(database, "ensure_heartbeat_outcome_for_discovery", fail_outcome)
    result = database.record_heartbeat_discovery("ROLL", 85.0, "Volume Breakout", "Test", 10.0)
    assert result is None

    conn = database.get_db_connection()
    try:
        assert conn.execute("SELECT COUNT(*) FROM heartbeat_discoveries WHERE ticker = 'ROLL';").fetchone()[0] == 0
    finally:
        conn.close()


def test_summary_does_not_count_profitable_timeout_as_win(temp_db):
    for ticker, status, ret in [("WINR", "win", 0.2), ("TIME", "timeout", 0.05)]:
        discovery_id = _insert_heartbeat_discovery(ticker=ticker)
        database.ensure_heartbeat_outcome_for_discovery(discovery_id)
        conn = database.get_db_connection()
        try:
            with conn:
                conn.execute(
                    """
                    UPDATE heartbeat_outcomes
                    SET source_type = 'live', outcome_status = ?, return_pct = ?
                    WHERE discovery_id = ?;
                    """,
                    (status, ret, discovery_id)
                )
        finally:
            conn.close()

    summary = database.get_heartbeat_outcome_summary()
    assert summary["resolved_next_open"] == 2
    assert summary["wins_next_open"] == 1
    assert summary["profitable_timeouts_next_open"] == 1
    assert summary["win_rate_next_open"] == 0.5
