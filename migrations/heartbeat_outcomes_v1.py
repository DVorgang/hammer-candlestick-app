import argparse
import os
import sqlite3
import sys
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core import database


MIGRATION_NAME = "heartbeat_outcomes_v1"


def _connect(db_path):
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn, table_name):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?;",
        (table_name,),
    ).fetchone()
    return row is not None


def _ensure_schema_version_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        );
        """
    )


def _ensure_heartbeat_outcomes_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS heartbeat_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discovery_id INTEGER NOT NULL UNIQUE,
            ticker TEXT NOT NULL,
            signal_date TEXT NOT NULL,
            signal_timestamp TEXT,
            signal_price REAL,
            delivery_first_at TEXT,
            modeled_entry_rule TEXT NOT NULL,
            entry_model_version TEXT NOT NULL,
            entry_status TEXT NOT NULL DEFAULT 'pending',
            entry_date TEXT,
            modeled_entry_price REAL,
            advertised_stop REAL,
            advertised_target REAL,
            modeled_stop REAL,
            modeled_target REAL,
            outcome_status TEXT NOT NULL DEFAULT 'pending',
            exit_date TEXT,
            exit_price REAL,
            return_pct REAL,
            mfe_pct REAL,
            mae_pct REAL,
            same_bar_ambiguous INTEGER DEFAULT 0,
            scoring_version TEXT,
            outcome_rule_version TEXT NOT NULL,
            source_type TEXT NOT NULL,
            legacy_sent_alert_id INTEGER REFERENCES sent_alerts(id),
            resolution_data_asof TEXT,
            resolution_error TEXT,
            reconstruction_notes TEXT,
            is_backfilled INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (discovery_id) REFERENCES heartbeat_discoveries(id) ON DELETE RESTRICT
        );
        """
    )


def _fetch_legacy_sent_alerts(conn, discovery):
    return conn.execute(
        """
        SELECT *
        FROM sent_alerts
        WHERE ticker = ?
          AND pattern_type LIKE 'Heartbeat_%'
          AND day2_date = ?
        ORDER BY id ASC;
        """,
        (discovery["ticker"], str(discovery["discovery_date"])[:10]),
    ).fetchall()


def _legacy_signature(row):
    return (
        row["entry_price"],
        row["stop_loss"],
        row["profit_target"],
        row["outcome_status"],
        row["exit_price"],
        row["exit_date"],
        row["return_pct"],
    )


def _select_legacy_sent_alert(conn, discovery):
    rows = _fetch_legacy_sent_alerts(conn, discovery)
    if not rows:
        return None, None

    signatures = {_legacy_signature(row) for row in rows}
    if len(signatures) > 1:
        ids = ", ".join(str(row["id"]) for row in rows)
        return None, f"Conflicting legacy Heartbeat sent_alerts for {discovery['ticker']} {discovery['discovery_date']}: ids {ids}"

    return rows[0], None


def _legacy_notes(discovery):
    return (
        "Legacy Heartbeat outcome linked from sent_alerts. Entry methodology is the "
        "pre-canonical close/day3-open model and must not be aggregated with "
        "next_open_v1 reconstructed/live results without labeling."
    )


def _reconstruction_notes(discovery):
    if discovery["created_at"]:
        return (
            "Reconstructed from heartbeat_discoveries using created_at when available; "
            "if timezone is not verifiable, next session is derived from discovery_date. "
            "This is a modeled fill, not an observed live recommendation fill."
        )
    return (
        "Reconstructed from heartbeat_discoveries.discovery_date because no reliable "
        "created_at timestamp was available. This is a modeled fill, not an observed "
        "live recommendation fill."
    )


def plan_migration(db_path):
    conn = _connect(db_path)
    try:
        if not _table_exists(conn, "heartbeat_discoveries"):
            raise RuntimeError("heartbeat_discoveries table does not exist.")

        discoveries = conn.execute(
            "SELECT * FROM heartbeat_discoveries ORDER BY id ASC;"
        ).fetchall()
        existing = set()
        if _table_exists(conn, "heartbeat_outcomes"):
            rows = conn.execute("SELECT discovery_id FROM heartbeat_outcomes;").fetchall()
            existing = {row["discovery_id"] for row in rows}

        actions = []
        conflicts = []
        for discovery in discoveries:
            if discovery["id"] in existing:
                continue
            legacy = None
            conflict = None
            if _table_exists(conn, "sent_alerts"):
                legacy, conflict = _select_legacy_sent_alert(conn, discovery)
            if conflict:
                conflicts.append({
                    "discovery_id": discovery["id"],
                    "ticker": discovery["ticker"],
                    "error": conflict,
                })
            actions.append({
                "discovery_id": discovery["id"],
                "ticker": discovery["ticker"],
                "source_type": "legacy_migrated" if legacy else "reconstructed",
                "legacy_sent_alert_id": legacy["id"] if legacy else None,
                "error": conflict,
            })

        return {
            "db_path": db_path,
            "discoveries_total": len(discoveries),
            "existing_outcomes": len(existing),
            "planned_inserts": len(actions),
            "legacy_migrated": sum(1 for action in actions if action["source_type"] == "legacy_migrated"),
            "reconstructed": sum(1 for action in actions if action["source_type"] == "reconstructed"),
            "conflicts": conflicts,
            "actions": actions,
        }
    finally:
        conn.close()


def create_sqlite_backup(db_path, backup_path=None):
    backup_path = backup_path or f"{db_path}.{MIGRATION_NAME}.{datetime.now().strftime('%Y%m%d%H%M%S')}.bak"
    src = _connect(db_path)
    dest = sqlite3.connect(backup_path)
    try:
        src.backup(dest)
    finally:
        dest.close()
        src.close()

    verify = _connect(backup_path)
    try:
        integrity = verify.execute("PRAGMA integrity_check;").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"Backup integrity check failed: {integrity}")
    finally:
        verify.close()
    return backup_path


def apply_migration(db_path, backup=True):
    if backup:
        backup_path = create_sqlite_backup(db_path)
    else:
        backup_path = None

    database.DB_FILE = db_path
    conn = database.get_db_connection()
    try:
        with conn:
            _ensure_schema_version_table(conn)
            _ensure_heartbeat_outcomes_table(conn)
            discoveries = conn.execute(
                "SELECT * FROM heartbeat_discoveries ORDER BY id ASC;"
            ).fetchall()
            for discovery in discoveries:
                existing = conn.execute(
                    "SELECT 1 FROM heartbeat_outcomes WHERE discovery_id = ?;",
                    (discovery["id"],),
                ).fetchone()
                if existing:
                    database.sync_heartbeat_delivery_first_at(discovery["id"], conn=conn)
                    continue

                legacy, conflict = _select_legacy_sent_alert(conn, discovery)
                if conflict:
                    raise RuntimeError(conflict)
                source_type = "legacy_migrated" if legacy else "reconstructed"
                notes = _legacy_notes(discovery) if legacy else _reconstruction_notes(discovery)
                outcome = database.ensure_heartbeat_outcome_for_discovery(
                    discovery["id"],
                    source_type=source_type,
                    legacy_sent_alert_id=legacy["id"] if legacy else None,
                    is_backfilled=1,
                    reconstruction_notes=notes,
                    conn=conn,
                )
                if legacy and outcome:
                    conn.execute(
                        """
                        UPDATE heartbeat_outcomes
                        SET entry_status = 'filled',
                            entry_date = ?,
                            modeled_entry_price = ?,
                            advertised_stop = ?,
                            advertised_target = ?,
                            modeled_stop = ?,
                            modeled_target = ?,
                            outcome_status = ?,
                            exit_date = ?,
                            exit_price = ?,
                            return_pct = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE discovery_id = ?;
                        """,
                        (
                            str(legacy["day2_date"])[:10],
                            legacy["entry_price"],
                            legacy["stop_loss"],
                            legacy["profit_target"],
                            legacy["stop_loss"],
                            legacy["profit_target"],
                            legacy["outcome_status"] or "pending",
                            legacy["exit_date"],
                            legacy["exit_price"],
                            legacy["return_pct"],
                            discovery["id"],
                        ),
                    )
                database.sync_heartbeat_delivery_first_at(discovery["id"], conn=conn)

            fk_errors = conn.execute("PRAGMA foreign_key_check;").fetchall()
            integrity = conn.execute("PRAGMA integrity_check;").fetchone()[0]
            if fk_errors:
                raise RuntimeError(f"Foreign key check failed: {fk_errors}")
            if integrity != "ok":
                raise RuntimeError(f"Integrity check failed: {integrity}")

            conn.execute(
                """
                INSERT OR REPLACE INTO schema_migrations (name, applied_at)
                VALUES (?, ?);
                """,
                (MIGRATION_NAME, datetime.now().isoformat()),
            )

        return {"backup_path": backup_path, "integrity": "ok"}
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Create/backfill canonical Heartbeat outcomes.")
    parser.add_argument("--db", required=True, help="Explicit SQLite database path.")
    parser.add_argument("--apply", action="store_true", help="Apply the migration. Omit for dry-run.")
    parser.add_argument("--no-backup", action="store_true", help="Skip backup when applying.")
    args = parser.parse_args()

    db_path = os.path.abspath(args.db)
    if not os.path.exists(db_path):
        raise SystemExit(f"Database not found: {db_path}")

    plan = plan_migration(db_path)
    print(f"Migration: {MIGRATION_NAME}")
    print(f"Database: {plan['db_path']}")
    print(f"Discoveries: {plan['discoveries_total']}")
    print(f"Existing outcomes: {plan['existing_outcomes']}")
    print(f"Planned inserts: {plan['planned_inserts']}")
    print(f"Legacy migrated: {plan['legacy_migrated']}")
    print(f"Reconstructed: {plan['reconstructed']}")
    print(f"Conflicts: {len(plan['conflicts'])}")
    for action in plan["actions"]:
        legacy = action["legacy_sent_alert_id"] if action["legacy_sent_alert_id"] is not None else "none"
        suffix = f" error={action['error']}" if action.get("error") else ""
        print(f"- discovery_id={action['discovery_id']} ticker={action['ticker']} source={action['source_type']} legacy_sent_alert_id={legacy}{suffix}")

    if not args.apply:
        print("Dry-run only. No changes written.")
        return
    if plan["conflicts"]:
        raise SystemExit("Conflicting legacy rows found. Resolve conflicts before applying migration.")

    result = apply_migration(db_path, backup=not args.no_backup)
    print(f"Applied successfully. Integrity: {result['integrity']}")
    if result["backup_path"]:
        print(f"Backup: {result['backup_path']}")


if __name__ == "__main__":
    main()
