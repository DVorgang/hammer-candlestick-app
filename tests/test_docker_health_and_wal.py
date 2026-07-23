import os
import sys
import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import database
import healthcheck

def test_database_wal_mode_and_connection():
    """
    Verifies that get_db_connection() configures SQLite WAL mode and busy_timeout.
    """
    conn = database.get_db_connection()
    try:
        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        busy_timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
        foreign_keys = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        
        assert journal_mode.lower() == "wal", f"Expected WAL mode, got {journal_mode}"
        assert busy_timeout >= 5000, f"Expected busy_timeout >= 5000, got {busy_timeout}"
        assert foreign_keys == 1, "Expected foreign_keys = 1"
    finally:
        conn.close()

def test_database_healthcheck_helper():
    """
    Verifies that database.get_system_health() returns expected healthy status keys.
    """
    health = database.get_system_health()
    assert health["status"] == "healthy"
    assert health["journal_mode"].lower() == "wal"
    assert health["integrity_check"] == "ok"

def test_healthcheck_script_functions():
    """
    Verifies that healthcheck script functions return True for valid database state.
    """
    assert healthcheck.check_database_health() is True
    assert healthcheck.check_worker_heartbeat() is True
