import sqlite3
import os
import json
import uuid
import logging
import random
from datetime import datetime, timedelta

DB_FILE = os.getenv("DATABASE_PATH", "sentinel.db")
HEARTBEAT_ENTRY_MODEL_VERSION = "next_open_v1"
HEARTBEAT_OUTCOME_RULE_VERSION = "heartbeat_v1"
HEARTBEAT_MODELED_ENTRY_RULE = "next_regular_session_open_after_signal_session"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def get_db_connection():
    """
    Establishes connection to the SQLite database with WAL mode, busy timeout, and foreign key support.
    """
    try:
        db_dir = os.path.dirname(DB_FILE)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(DB_FILE, timeout=30.0)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logging.error(f"Failed to connect to database: {e}")
        raise

def init_db():
    """
    Initializes the database schema if sentinel.db doesn't exist or is missing tables.
    Adds support for 6-digit OTP codes and expiration timestamps.
    """
    create_subscribers_table = """
    CREATE TABLE IF NOT EXISTS subscribers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        secondary_email TEXT,
        management_token TEXT UNIQUE NOT NULL,
        wants_buys INTEGER DEFAULT 1,
        wants_risks INTEGER DEFAULT 1,
        wants_sells INTEGER DEFAULT 1,
        otp_code TEXT,
        otp_expiry TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """
    create_watchlists_table = """
    CREATE TABLE IF NOT EXISTS watchlists (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subscriber_id INTEGER NOT NULL,
        ticker TEXT NOT NULL,
        FOREIGN KEY (subscriber_id) REFERENCES subscribers (id) ON DELETE CASCADE,
        UNIQUE (subscriber_id, ticker)
    );
    """
    create_sent_alerts_table = """
    CREATE TABLE IF NOT EXISTS sent_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subscriber_id INTEGER NOT NULL,
        ticker TEXT NOT NULL,
        pattern_type TEXT NOT NULL,
        day1_date TEXT NOT NULL,
        day2_date TEXT NOT NULL,
        sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (subscriber_id) REFERENCES subscribers (id) ON DELETE CASCADE,
        UNIQUE (subscriber_id, ticker, pattern_type, day1_date, day2_date)
    );
    """
    
    create_scanner_logs_table = """
    CREATE TABLE IF NOT EXISTS scanner_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        duration_seconds REAL NOT NULL,
        tickers_scanned INTEGER NOT NULL,
        signals_found INTEGER NOT NULL,
        alerts_sent INTEGER NOT NULL,
        trigger_type TEXT DEFAULT 'manual'
    );
    """
    create_scheduler_state_table = """
    CREATE TABLE IF NOT EXISTS scheduler_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        is_active INTEGER DEFAULT 0,
        start_timestamp TEXT,
        last_run_timestamp TEXT
    );
    """
    
    create_growth_discoveries_table = """
    CREATE TABLE IF NOT EXISTS growth_discoveries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        discovery_date TEXT NOT NULL,
        initial_price REAL,
        growth_score REAL NOT NULL,
        catalyst_type TEXT,
        headline_summary TEXT,
        last_featured_date TEXT NOT NULL,
        status TEXT DEFAULT 'active_monitoring',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(ticker, discovery_date)
    );
    """
    
    create_heartbeat_discoveries_table = """
    CREATE TABLE IF NOT EXISTS heartbeat_discoveries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        discovery_date TEXT NOT NULL,
        initial_price REAL,
        conviction_score REAL NOT NULL,
        catalyst_type TEXT,
        headline_summary TEXT,
        last_featured_date TEXT NOT NULL,
        status TEXT DEFAULT 'active_monitoring',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(ticker, discovery_date)
    );
    """
    create_heartbeat_outcomes_table = """
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
    create_paper_accounts_table = """
    CREATE TABLE IF NOT EXISTS paper_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subscriber_id INTEGER NOT NULL,
        account_label TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (subscriber_id) REFERENCES subscribers (id) ON DELETE CASCADE,
        UNIQUE (subscriber_id, account_label)
    );
    """
    
    conn = get_db_connection()
    try:
        with conn:
            create_paper_trades_table = """
            CREATE TABLE IF NOT EXISTS paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscriber_id INTEGER NOT NULL,
                account_label TEXT DEFAULT 'Account 1',
                ticker TEXT NOT NULL,
                entry_date TEXT NOT NULL,
                entry_price REAL NOT NULL,
                total_invested REAL NOT NULL,
                shares REAL NOT NULL,
                status TEXT DEFAULT 'OPEN',
                exit_date TEXT,
                exit_price REAL,
                realized_pnl REAL,
                FOREIGN KEY (subscriber_id) REFERENCES subscribers (id) ON DELETE CASCADE
            );
            """
            conn.execute(create_subscribers_table)
            conn.execute(create_watchlists_table)
            conn.execute(create_sent_alerts_table)
            conn.execute(create_scanner_logs_table)
            conn.execute(create_scheduler_state_table)
            conn.execute(create_growth_discoveries_table)
            conn.execute(create_heartbeat_discoveries_table)
            conn.execute(create_heartbeat_outcomes_table)
            conn.execute(create_paper_accounts_table)
            conn.execute(create_paper_trades_table)

            cursor_p = conn.execute("PRAGMA table_info(paper_trades);")
            p_columns = [row["name"] for row in cursor_p.fetchall()]
            if "account_label" not in p_columns:
                conn.execute("ALTER TABLE paper_trades ADD COLUMN account_label TEXT DEFAULT 'Account 1';")
            
            # Ensure default row 1 exists in scheduler_state
            conn.execute("INSERT OR IGNORE INTO scheduler_state (id, is_active, start_timestamp) VALUES (1, 0, NULL);")
            
            # Check columns in subscribers and scheduler_state
            cursor = conn.execute("PRAGMA table_info(subscribers);")
            columns = [row["name"] for row in cursor.fetchall()]
            if "otp_code" not in columns:
                conn.execute("ALTER TABLE subscribers ADD COLUMN otp_code TEXT;")
            if "otp_expiry" not in columns:
                conn.execute("ALTER TABLE subscribers ADD COLUMN otp_expiry TEXT;")
            if "wants_growth" not in columns:
                conn.execute("ALTER TABLE subscribers ADD COLUMN wants_growth INTEGER DEFAULT 1;")
            if "wants_heartbeat" not in columns:
                conn.execute("ALTER TABLE subscribers ADD COLUMN wants_heartbeat INTEGER DEFAULT 1;")
            if "secondary_email" not in columns:
                conn.execute("ALTER TABLE subscribers ADD COLUMN secondary_email TEXT;")
            if "paper_position_size" not in columns:
                conn.execute("ALTER TABLE subscribers ADD COLUMN paper_position_size REAL DEFAULT 500.0;")
            if "is_admin" not in columns:
                conn.execute("ALTER TABLE subscribers ADD COLUMN is_admin INTEGER DEFAULT 0;")

            admin_emails = os.environ.get("ADMIN_EMAILS", "devin.vorgang@gmail.com").lower().split(",")
            for ae in admin_emails:
                if ae.strip():
                    conn.execute("UPDATE subscribers SET is_admin = 1 WHERE email = ?", (ae.strip(),))
                
            cursor_s = conn.execute("PRAGMA table_info(scheduler_state);")
            s_columns = [row["name"] for row in cursor_s.fetchall()]
            if "growth_is_active" not in s_columns:
                conn.execute("ALTER TABLE scheduler_state ADD COLUMN growth_is_active INTEGER DEFAULT 0;")
            if "growth_start_timestamp" not in s_columns:
                conn.execute("ALTER TABLE scheduler_state ADD COLUMN growth_start_timestamp TEXT;")
            if "growth_last_run_timestamp" not in s_columns:
                conn.execute("ALTER TABLE scheduler_state ADD COLUMN growth_last_run_timestamp TEXT;")
            if "heartbeat_is_active" not in s_columns:
                conn.execute("ALTER TABLE scheduler_state ADD COLUMN heartbeat_is_active INTEGER DEFAULT 0;")
            if "heartbeat_start_timestamp" not in s_columns:
                conn.execute("ALTER TABLE scheduler_state ADD COLUMN heartbeat_start_timestamp TEXT;")
            if "heartbeat_last_run_timestamp" not in s_columns:
                conn.execute("ALTER TABLE scheduler_state ADD COLUMN heartbeat_last_run_timestamp TEXT;")

            # Check outcome tracking columns in sent_alerts
            cursor_a = conn.execute("PRAGMA table_info(sent_alerts);")
            a_columns = [row["name"] for row in cursor_a.fetchall()]
            alert_new_cols = [
                ("entry_price", "REAL"),
                ("stop_loss", "REAL"),
                ("profit_target", "REAL"),
                ("outcome_status", "TEXT DEFAULT 'pending'"),
                ("exit_price", "REAL"),
                ("exit_date", "TEXT"),
                ("return_pct", "REAL"),
                ("rsi_at_entry", "REAL"),
                ("vol_mult_at_entry", "REAL"),
                ("trading_date", "TEXT"),
                ("digest_status", "TEXT DEFAULT 'PENDING'")
            ]
            for col_name, col_type in alert_new_cols:
                if col_name not in a_columns:
                    conn.execute(f"ALTER TABLE sent_alerts ADD COLUMN {col_name} {col_type};")

            # Check digest tracking and rich detail columns in growth_discoveries and heartbeat_discoveries
            for tbl in ["growth_discoveries", "heartbeat_discoveries"]:
                cursor_tbl = conn.execute(f"PRAGMA table_info({tbl});")
                tbl_cols = [row["name"] for row in cursor_tbl.fetchall()]
                if "trading_date" not in tbl_cols:
                    conn.execute(f"ALTER TABLE {tbl} ADD COLUMN trading_date TEXT;")
                if "digest_status" not in tbl_cols:
                    conn.execute(f"ALTER TABLE {tbl} ADD COLUMN digest_status TEXT DEFAULT 'PENDING';")
                if "key_catalysts_json" not in tbl_cols:
                    conn.execute(f"ALTER TABLE {tbl} ADD COLUMN key_catalysts_json TEXT;")
                if "risks_json" not in tbl_cols:
                    conn.execute(f"ALTER TABLE {tbl} ADD COLUMN risks_json TEXT;")
                if "plain_english_takeaway" not in tbl_cols:
                    conn.execute(f"ALTER TABLE {tbl} ADD COLUMN plain_english_takeaway TEXT;")
                if "news_articles_json" not in tbl_cols:
                    conn.execute(f"ALTER TABLE {tbl} ADD COLUMN news_articles_json TEXT;")
                if "badge_tag" not in tbl_cols:
                    conn.execute(f"ALTER TABLE {tbl} ADD COLUMN badge_tag TEXT;")
                if "badge_color" not in tbl_cols:
                    conn.execute(f"ALTER TABLE {tbl} ADD COLUMN badge_color TEXT;")
                if "vol_mult" not in tbl_cols:
                    conn.execute(f"ALTER TABLE {tbl} ADD COLUMN vol_mult REAL;")
                if "bb_width_pct" not in tbl_cols:
                    conn.execute(f"ALTER TABLE {tbl} ADD COLUMN bb_width_pct REAL;")
                if "above_200sma" not in tbl_cols:
                    conn.execute(f"ALTER TABLE {tbl} ADD COLUMN above_200sma INTEGER;")

            # Create digest delivery and association tables
            conn.execute("""
            CREATE TABLE IF NOT EXISTS digest_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trading_date TEXT NOT NULL,
                digest_type TEXT NOT NULL,
                subscriber_id INTEGER NOT NULL,
                subscriber_email TEXT NOT NULL,
                status TEXT NOT NULL,
                discovery_ids_json TEXT NOT NULL,
                discoveries_count INTEGER NOT NULL,
                first_attempt_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_attempt_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                delivered_at DATETIME,
                attempt_count INTEGER DEFAULT 0,
                last_error TEXT,
                UNIQUE(trading_date, digest_type, subscriber_id)
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS digest_delivery_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                digest_delivery_id INTEGER NOT NULL REFERENCES digest_deliveries(id),
                attempted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL,
                error_message TEXT,
                provider_message_id TEXT
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS digest_discovery_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                digest_delivery_id INTEGER NOT NULL REFERENCES digest_deliveries(id),
                source_type TEXT NOT NULL,
                source_id INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                score REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(digest_delivery_id, source_type, source_id)
            );
            """)

            # Auto-backfill Heartbeat blueprints if stop_loss or profit_target is NULL
            conn.execute("""
                UPDATE sent_alerts 
                SET stop_loss = ROUND(entry_price * 0.95, 2),
                    profit_target = ROUND(entry_price * 1.20, 2)
                WHERE pattern_type LIKE 'Heartbeat_%' AND entry_price IS NOT NULL AND stop_loss IS NULL;
            """)

        logging.info("Database initialized successfully.")
    except sqlite3.Error as e:
        logging.error(f"Error initializing database: {e}")
        raise

    finally:
        conn.close()


# ─── DIGEST SCHEDULER & DELIVERY STATE QUERY METHODS ───

def is_digest_delivered(trading_date, digest_type, subscriber_id):
    """
    Returns True if a digest has already been successfully delivered for this trading_date, digest_type, and subscriber.
    """
    conn = get_db_connection()
    try:
        row = conn.execute(
            """
            SELECT 1 FROM digest_deliveries
            WHERE trading_date = ? AND digest_type = ? AND subscriber_id = ? AND status = 'SUCCESS'
            """,
            (trading_date, digest_type, subscriber_id)
        ).fetchone()
        return row is not None
    except sqlite3.Error as e:
        logging.error(f"Database error checking digest delivered: {e}")
        return False
    finally:
        conn.close()

def get_or_create_digest_delivery(trading_date, digest_type, subscriber_id, subscriber_email, discovery_ids_json, discoveries_count, status="PENDING"):
    """
    Creates or retrieves the digest_deliveries record for (trading_date, digest_type, subscriber_id).
    Returns dict of the row.
    """
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO digest_deliveries (trading_date, digest_type, subscriber_id, subscriber_email, discovery_ids_json, discoveries_count, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trading_date, digest_type, subscriber_id) DO UPDATE SET
                    subscriber_email = excluded.subscriber_email,
                    discovery_ids_json = excluded.discovery_ids_json,
                    discoveries_count = excluded.discoveries_count,
                    last_attempt_at = CURRENT_TIMESTAMP
                """,
                (trading_date, digest_type, subscriber_id, subscriber_email, str(discovery_ids_json), discoveries_count, status)
            )
        row = conn.execute(
            "SELECT * FROM digest_deliveries WHERE trading_date = ? AND digest_type = ? AND subscriber_id = ?",
            (trading_date, digest_type, subscriber_id)
        ).fetchone()
        return dict(row) if row else None
    except sqlite3.Error as e:
        logging.error(f"Database error getting/creating digest delivery: {e}")
        return None
    finally:
        conn.close()

def record_digest_attempt(digest_delivery_id, status, error_message=None, provider_message_id=None):
    """
    Appends an audit log entry to digest_delivery_attempts and updates digest_deliveries status/error.
    """
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO digest_delivery_attempts (digest_delivery_id, status, error_message, provider_message_id)
                VALUES (?, ?, ?, ?)
                """,
                (digest_delivery_id, status, error_message, provider_message_id)
            )
            
            if status == "SUCCESS":
                conn.execute(
                    """
                    UPDATE digest_deliveries
                    SET status = 'SUCCESS', delivered_at = CURRENT_TIMESTAMP, attempt_count = attempt_count + 1, last_error = NULL
                    WHERE id = ?
                    """,
                    (digest_delivery_id,)
                )
            else:
                conn.execute(
                    """
                    UPDATE digest_deliveries
                    SET status = ?, attempt_count = attempt_count + 1, last_error = ?
                    WHERE id = ?
                    """,
                    (status, error_message, digest_delivery_id)
                )
        return True
    except sqlite3.Error as e:
        logging.error(f"Database error recording digest attempt: {e}")
        return False
    finally:
        conn.close()

def mark_digest_success(digest_delivery_id, discovery_items):
    """
    Marks delivery SUCCESS, logs associated items in digest_discovery_items,
    and updates source discoveries to digest_status = 'DELIVERED'.
    """
    conn = get_db_connection()
    try:
        with conn:
            record_digest_attempt(digest_delivery_id, "SUCCESS")
            for item in discovery_items:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO digest_discovery_items (digest_delivery_id, source_type, source_id, ticker, score)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (digest_delivery_id, item["source_type"], item["source_id"], item["ticker"], item.get("score", 0.0))
                )
                
                s_type = item["source_type"]
                s_id = item["source_id"]
                if s_type == "growth":
                    conn.execute("UPDATE growth_discoveries SET digest_status = 'DELIVERED' WHERE id = ?", (s_id,))
                elif s_type == "heartbeat":
                    conn.execute("UPDATE heartbeat_discoveries SET digest_status = 'DELIVERED' WHERE id = ?", (s_id,))
                    ensure_heartbeat_outcome_for_discovery(s_id, source_type="live", conn=conn)
                    sync_heartbeat_delivery_first_at(s_id, conn=conn)
                elif s_type == "technical":
                    conn.execute("UPDATE sent_alerts SET digest_status = 'DELIVERED' WHERE id = ?", (s_id,))
        return True
    except sqlite3.Error as e:
        logging.error(f"Database error marking digest success: {e}")
        return False
    finally:
        conn.close()

def get_pending_discoveries_for_subscriber(subscriber_id, trading_date=None):
    """
    Retrieves pending growth, heartbeat, and technical reversal discoveries for a subscriber
    that have NOT yet been included in a SUCCESS digest for this subscriber.
    """
    conn = get_db_connection()
    try:
        growth_rows = conn.execute(
            """
            SELECT g.id, g.ticker, g.growth_score as score, g.catalyst_type, g.headline_summary, g.initial_price, g.key_catalysts_json, g.risks_json, g.plain_english_takeaway, g.news_articles_json, g.vol_mult, g.created_at, 'growth' as source_type
            FROM growth_discoveries g
            WHERE g.id NOT IN (
                SELECT i.source_id 
                FROM digest_discovery_items i
                JOIN digest_deliveries d ON i.digest_delivery_id = d.id
                WHERE d.subscriber_id = ? AND d.status = 'SUCCESS' AND i.source_type = 'growth'
            )
            """,
            (subscriber_id,)
        ).fetchall()
        
        heartbeat_rows = conn.execute(
            """
            SELECT h.id, h.ticker, h.conviction_score as score, h.catalyst_type, h.headline_summary, h.initial_price, h.key_catalysts_json, h.risks_json, h.plain_english_takeaway, h.news_articles_json, h.badge_tag, h.badge_color, h.vol_mult, h.bb_width_pct, h.above_200sma, h.created_at, 'heartbeat' as source_type
            FROM heartbeat_discoveries h
            WHERE h.id NOT IN (
                SELECT i.source_id 
                FROM digest_discovery_items i
                JOIN digest_deliveries d ON i.digest_delivery_id = d.id
                WHERE d.subscriber_id = ? AND d.status = 'SUCCESS' AND i.source_type = 'heartbeat'
            )
            """,
            (subscriber_id,)
        ).fetchall()
        
        tech_rows = conn.execute(
            """
            SELECT a.id, a.ticker, a.rsi_at_entry, a.vol_mult_at_entry, a.pattern_type, a.entry_price, a.stop_loss, a.profit_target, a.sent_at as created_at, 'technical' as source_type
            FROM sent_alerts a
            WHERE a.subscriber_id = ? AND a.id NOT IN (
                SELECT i.source_id 
                FROM digest_discovery_items i
                JOIN digest_deliveries d ON i.digest_delivery_id = d.id
                WHERE d.subscriber_id = ? AND d.status = 'SUCCESS' AND i.source_type = 'technical'
            )
            """,
            (subscriber_id, subscriber_id)
        ).fetchall()

        growth_list = []
        for r in growth_rows:
            d = dict(r)
            try:
                d["key_catalysts"] = json.loads(d["key_catalysts_json"]) if d.get("key_catalysts_json") else []
            except Exception:
                d["key_catalysts"] = []
            try:
                d["risks"] = json.loads(d["risks_json"]) if d.get("risks_json") else []
            except Exception:
                d["risks"] = []
            try:
                d["news_articles"] = json.loads(d["news_articles_json"]) if d.get("news_articles_json") else []
            except Exception:
                d["news_articles"] = []
            d["latest_price"] = d.get("initial_price")
            d["growth_score"] = d.get("score")
            growth_list.append(d)

        heartbeat_list = []
        for r in heartbeat_rows:
            d = dict(r)
            try:
                d["key_catalysts"] = json.loads(d["key_catalysts_json"]) if d.get("key_catalysts_json") else []
            except Exception:
                d["key_catalysts"] = []
            try:
                d["risks"] = json.loads(d["risks_json"]) if d.get("risks_json") else []
            except Exception:
                d["risks"] = []
            try:
                d["news_articles"] = json.loads(d["news_articles_json"]) if d.get("news_articles_json") else []
            except Exception:
                d["news_articles"] = []
            d["latest_price"] = d.get("initial_price")
            d["conviction_score"] = d.get("score")
            d["above_200sma"] = bool(d.get("above_200sma", 0))
            heartbeat_list.append(d)
        
        return {
            "growth": growth_list,
            "heartbeat": heartbeat_list,
            "technical": [dict(r) for r in tech_rows]
        }
    except sqlite3.Error as e:
        logging.error(f"Database error fetching pending discoveries: {e}")
        return {"growth": [], "heartbeat": [], "technical": []}
    finally:
        conn.close()


def create_subscriber(email, wants_buys=1, wants_risks=1, wants_sells=1, wants_growth=1, wants_heartbeat=1, initial_tickers=None):
    """
    Registers a new subscriber, generates a management token, and adds initial watchlist tickers.
    Returns (id, management_token) on success.
    """
    token = uuid.uuid4().hex
    conn = get_db_connection()
    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO subscribers (email, management_token, wants_buys, wants_risks, wants_sells, wants_growth, wants_heartbeat)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (email.strip().lower(), token, int(wants_buys), int(wants_risks), int(wants_sells), int(wants_growth), int(wants_heartbeat))
            )
            subscriber_id = cursor.lastrowid
            
            if initial_tickers:
                unique_tickers = list(set([t.strip().upper() for t in initial_tickers if t.strip()]))
                for ticker in unique_tickers:
                    conn.execute(
                        """
                        INSERT INTO watchlists (subscriber_id, ticker)
                        VALUES (?, ?)
                        """,
                        (subscriber_id, ticker)
                    )
            return subscriber_id, token
    except sqlite3.IntegrityError as e:
        logging.warning(f"Subscriber insertion integrity warning (email likely already exists): {e}")
        raise ValueError("Email already subscribed.")
    except sqlite3.Error as e:
        logging.error(f"Database error creating subscriber: {e}")
        raise
    finally:
        conn.close()

def get_subscriber_by_token(token):
    """
    Retrieves subscriber records by their unique management token.
    """
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT * FROM subscribers WHERE management_token = ?",
            (token,)
        ).fetchone()
        return dict(row) if row else None
    except sqlite3.Error as e:
        logging.error(f"Database error getting subscriber by token: {e}")
        return None
    finally:
        conn.close()

def get_subscriber_by_email(email):
    """
    Retrieves subscriber records by their email address.
    """
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT * FROM subscribers WHERE email = ?",
            (email.strip().lower(),)
        ).fetchone()
        return dict(row) if row else None
    except sqlite3.Error as e:
        logging.error(f"Database error getting subscriber by email: {e}")
        return None
    finally:
        conn.close()

def is_admin_subscriber(subscriber):
    """
    Returns True if subscriber has Admin privileges.
    Checks environment variable ADMIN_EMAILS (defaults to 'devin.vorgang@gmail.com').
    Also checks if subscriber's is_admin column in database is 1.
    """
    if not subscriber or not isinstance(subscriber, dict):
        return False

    admin_emails = os.environ.get("ADMIN_EMAILS", "devin.vorgang@gmail.com").lower().split(",")
    admin_emails = [e.strip() for e in admin_emails if e.strip()]

    email = subscriber.get("email", "").strip().lower()
    if email in admin_emails:
        return True

    if subscriber.get("is_admin") == 1:
        return True

    return False

def set_subscriber_admin_status(email, is_admin_flag=1):
    """
    Sets the is_admin status (1 or 0) for a subscriber by email address.
    """
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("UPDATE subscribers SET is_admin = ? WHERE email = ?", (int(is_admin_flag), email.strip().lower()))
        return True
    except sqlite3.Error as e:
        logging.error(f"Database error setting admin status: {e}")
        return False
    finally:
        conn.close()

def update_subscriber_preferences(token, wants_buys, wants_risks, wants_sells, wants_growth=1):
    """
    Updates the email alert preferences for a subscriber.
    """
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                """
                UPDATE subscribers
                SET wants_buys = ?, wants_risks = ?, wants_sells = ?, wants_growth = ?
                WHERE management_token = ?
                """,
                (int(wants_buys), int(wants_risks), int(wants_sells), int(wants_growth), token)
            )
        return True
    except sqlite3.Error as e:
        logging.error(f"Database error updating preferences: {e}")
        return False
    finally:
        conn.close()


def update_subscriber_secondary_email(token, secondary_email):
    """
    Updates the secondary / CC email recipient for a subscriber by management token.
    """
    sec_email = secondary_email.strip().lower() if secondary_email and secondary_email.strip() else None
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                "UPDATE subscribers SET secondary_email = ? WHERE management_token = ?",
                (sec_email, token)
            )
        logging.info(f"Updated secondary email for token {token[:6]}... to {sec_email}")
        return True
    except sqlite3.Error as e:
        logging.error(f"Database error updating secondary email: {e}")
        return False
    finally:
        conn.close()

def get_watchlist(subscriber_id):
    """
    Retrieves the active watchlist (list of ticker strings) for a given subscriber ID.
    """
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT ticker FROM watchlists WHERE subscriber_id = ? ORDER BY ticker ASC",
            (subscriber_id,)
        ).fetchall()
        return [row["ticker"] for row in rows]
    except sqlite3.Error as e:
        logging.error(f"Database error fetching watchlist: {e}")
        return []
    finally:
        conn.close()

def add_watchlist_ticker(subscriber_id, ticker):
    """
    Adds a ticker to a subscriber's watchlist.
    """
    sanitized_ticker = ticker.strip().upper()
    if not sanitized_ticker:
        return False
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO watchlists (subscriber_id, ticker)
                VALUES (?, ?)
                """,
                (subscriber_id, sanitized_ticker)
            )
        return True
    except sqlite3.IntegrityError:
        return True
    except sqlite3.Error as e:
        logging.error(f"Database error adding ticker: {e}")
        return False
    finally:
        conn.close()

def remove_watchlist_ticker(subscriber_id, ticker):
    """
    Removes a ticker from a subscriber's watchlist.
    """
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                "DELETE FROM watchlists WHERE subscriber_id = ? AND ticker = ?",
                (subscriber_id, ticker.strip().upper())
            )
        return True
    except sqlite3.Error as e:
        logging.error(f"Database error removing ticker: {e}")
        return False
    finally:
        conn.close()

def unsubscribe_subscriber(token):
    """
    Deletes the subscriber from the database.
    """
    conn = get_db_connection()
    try:
        with conn:
            cursor = conn.execute(
                "DELETE FROM subscribers WHERE management_token = ?",
                (token,)
            )
            rows_affected = cursor.rowcount
            return rows_affected > 0
    except sqlite3.Error as e:
        logging.error(f"Database error unsubscribing: {e}")
        return False
    finally:
        conn.close()

def generate_otp(email):
    """
    Generates a 6-digit random code, sets expiry (10 minutes from now), 
    saves it to the database for the given subscriber, and returns the code.
    If the email is not registered, it creates a new subscriber profile first.
    """
    code = f"{random.randint(100000, 999999)}"
    expiry = (datetime.now() + timedelta(minutes=10)).isoformat()
    
    # Check if subscriber exists
    sub = get_subscriber_by_email(email)
    if not sub:
        # Create a new user with empty watchlist
        create_subscriber(email, wants_buys=1, wants_risks=1, wants_sells=1, initial_tickers=[])
        
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                """
                UPDATE subscribers
                SET otp_code = ?, otp_expiry = ?
                WHERE email = ?
                """,
                (code, expiry, email.strip().lower())
            )
        logging.info(f"Generated OTP {code} for {email} (expires {expiry})")
        return code
    except sqlite3.Error as e:
        logging.error(f"Database error generating OTP: {e}")
        raise
    finally:
        conn.close()

def verify_otp(email, code):
    """
    Verifies the OTP code. If correct and not expired, clears the code
    and returns the subscriber's management_token (authenticating them).
    Returns None otherwise.
    """
    sub = get_subscriber_by_email(email)
    if not sub or not sub["otp_code"] or not sub["otp_expiry"]:
        return None
        
    saved_code = sub["otp_code"]
    expiry_str = sub["otp_expiry"]
    
    try:
        expiry = datetime.fromisoformat(expiry_str)
    except ValueError:
        return None
        
    if saved_code == code.strip() and datetime.now() < expiry:
        # Clear OTP after successful verify
        conn = get_db_connection()
        try:
            with conn:
                conn.execute(
                    """
                    UPDATE subscribers
                    SET otp_code = NULL, otp_expiry = NULL
                    WHERE email = ?
                    """,
                    (email.strip().lower(),)
                )
            return sub["management_token"]
        except sqlite3.Error as e:
            logging.error(f"Database error clearing verified OTP: {e}")
            return sub["management_token"] # still authenticate even if clear fails
        finally:
            conn.close()
            
    return None

def get_all_subscribers():
    """
    Retrieves all subscribers from the database. Used by the background scanning script.
    """
    conn = get_db_connection()
    try:
        rows = conn.execute("SELECT * FROM subscribers").fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        logging.error(f"Database error getting all subscribers: {e}")
        return []
    finally:
        conn.close()

def has_alert_been_sent(subscriber_id, signal):
    """
    Checks whether this subscriber has already received this exact setup alert.
    """
    conn = get_db_connection()
    try:
        row = conn.execute(
            """
            SELECT 1 FROM sent_alerts
            WHERE subscriber_id = ?
              AND ticker = ?
              AND pattern_type = ?
              AND day1_date = ?
              AND day2_date = ?
            """,
            (
                subscriber_id,
                signal["ticker"].strip().upper(),
                signal["pattern_type"],
                str(signal["day1_date"])[:10],
                str(signal["day2_date"])[:10],
            )
        ).fetchone()
        return row is not None
    except sqlite3.Error as e:
        logging.error(f"Database error checking sent alert: {e}")
        return False
    finally:
        conn.close()

def record_sent_alert(subscriber_id, signal):
    """
    Records that a subscriber received this exact setup alert along with its trade blueprint math.
    """
    conn = get_db_connection()
    try:
        entry_price = signal.get("day3_open") or signal.get("day2_close")
        stop_loss = signal.get("stop_loss")
        profit_target = signal.get("profit_target")
        rsi_14 = signal.get("rsi_14")
        vol_mult = signal.get("vol_mult")
        
        with conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO sent_alerts
                    (subscriber_id, ticker, pattern_type, day1_date, day2_date, entry_price, stop_loss, profit_target, outcome_status, rsi_at_entry, vol_mult_at_entry)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    subscriber_id,
                    signal["ticker"].strip().upper(),
                    signal["pattern_type"],
                    str(signal["day1_date"])[:10],
                    str(signal["day2_date"])[:10],
                    entry_price,
                    stop_loss,
                    profit_target,
                    rsi_14,
                    vol_mult
                )
            )
        return True
    except sqlite3.Error as e:
        logging.error(f"Database error recording sent alert: {e}")
        return False
    finally:
        conn.close()


def _round_money(value):
    if value is None:
        return None
    return round(float(value), 2)


def calculate_heartbeat_modeled_levels(modeled_entry_price):
    """
    Applies the versioned Heartbeat v1 stop/target model to a modeled fill price.
    """
    entry = float(modeled_entry_price)
    if entry <= 5:
        return _round_money(entry * 0.935), _round_money(entry * 1.32)
    return _round_money(entry * 0.95), _round_money(entry * 1.20)


def ensure_heartbeat_outcome_for_discovery(discovery_id, source_type="live", legacy_sent_alert_id=None,
                                           is_backfilled=0, reconstruction_notes=None, conn=None):
    """
    Ensures a Heartbeat discovery has exactly one canonical, versioned shadow outcome.
    Existing outcomes are returned without being reset.
    """
    owns_conn = conn is None
    conn = conn or get_db_connection()
    try:
        discovery = conn.execute(
            "SELECT * FROM heartbeat_discoveries WHERE id = ?;",
            (discovery_id,)
        ).fetchone()
        if not discovery:
            return None

        existing = conn.execute(
            "SELECT * FROM heartbeat_outcomes WHERE discovery_id = ?;",
            (discovery_id,)
        ).fetchone()
        if existing:
            return dict(existing)

        now_str = datetime.now().isoformat()
        signal_date = str(discovery["discovery_date"])[:10]
        signal_timestamp = discovery["created_at"] or now_str

        def insert_outcome():
            conn.execute(
                """
                INSERT INTO heartbeat_outcomes (
                    discovery_id, ticker, signal_date, signal_timestamp, signal_price,
                    modeled_entry_rule, entry_model_version, entry_status, outcome_status,
                    scoring_version, outcome_rule_version, source_type, legacy_sent_alert_id,
                    reconstruction_notes, is_backfilled, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 'pending', ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
                """,
                (
                    discovery_id,
                    discovery["ticker"],
                    signal_date,
                    signal_timestamp,
                    discovery["initial_price"],
                    HEARTBEAT_MODELED_ENTRY_RULE,
                    HEARTBEAT_ENTRY_MODEL_VERSION,
                    "legacy_unknown" if source_type == "legacy_migrated" else None,
                    HEARTBEAT_OUTCOME_RULE_VERSION,
                    source_type,
                    legacy_sent_alert_id,
                    reconstruction_notes,
                    int(is_backfilled),
                )
            )

        if owns_conn:
            with conn:
                insert_outcome()
        else:
            insert_outcome()

        row = conn.execute(
            "SELECT * FROM heartbeat_outcomes WHERE discovery_id = ?;",
            (discovery_id,)
        ).fetchone()
        return dict(row) if row else None
    except sqlite3.Error as e:
        logging.error(f"Database error ensuring heartbeat outcome for discovery {discovery_id}: {e}")
        return None
    finally:
        if owns_conn:
            conn.close()


def sync_heartbeat_delivery_first_at(discovery_id, conn=None):
    """
    Sets delivery_first_at to the earliest successful digest delivery for this discovery.
    """
    owns_conn = conn is None
    conn = conn or get_db_connection()
    try:
        def update_delivery():
            conn.execute(
                """
                UPDATE heartbeat_outcomes
                SET delivery_first_at = (
                    SELECT MIN(d.delivered_at)
                    FROM digest_discovery_items i
                    JOIN digest_deliveries d ON i.digest_delivery_id = d.id
                    WHERE i.source_type = 'heartbeat'
                      AND i.source_id = heartbeat_outcomes.discovery_id
                      AND d.status = 'SUCCESS'
                      AND d.delivered_at IS NOT NULL
                ),
                    updated_at = CURRENT_TIMESTAMP
                WHERE discovery_id = ?
                  AND delivery_first_at IS NULL
                  AND EXISTS (
                    SELECT 1
                    FROM digest_discovery_items i
                    JOIN digest_deliveries d ON i.digest_delivery_id = d.id
                    WHERE i.source_type = 'heartbeat'
                      AND i.source_id = heartbeat_outcomes.discovery_id
                      AND d.status = 'SUCCESS'
                      AND d.delivered_at IS NOT NULL
                  );
                """,
                (discovery_id,)
            )
        if owns_conn:
            with conn:
                update_delivery()
        else:
            update_delivery()
        return True
    except sqlite3.Error as e:
        logging.error(f"Database error syncing heartbeat delivery_first_at for {discovery_id}: {e}")
        return False
    finally:
        if owns_conn:
            conn.close()


def _parse_date_only(value):
    if value is None:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _next_regular_session_after(signal_date):
    from core import market_calendar

    current = signal_date + timedelta(days=1)
    for _ in range(14):
        if market_calendar.is_trading_day(current):
            return current
        current += timedelta(days=1)
    return None


def _normalize_history_frame(hist):
    if hist is None or hist.empty:
        return None
    df = hist.reset_index()
    date_col = "Date" if "Date" in df.columns else df.columns[0]
    df["Date_Str"] = df[date_col].astype(str).str[:10]
    return df


def _completed_regular_session_history(hist):
    from core import market_calendar

    df = _normalize_history_frame(hist)
    if df is None:
        return None

    now_et = market_calendar.get_now_eastern()
    completed_dates = []
    for _, row in df.iterrows():
        bar_date = _parse_date_only(row["Date_Str"])
        if not bar_date:
            completed_dates.append(False)
            continue
        if bar_date < now_et.date():
            completed_dates.append(True)
            continue
        if bar_date > now_et.date():
            completed_dates.append(False)
            continue
        schedule = market_calendar.get_market_schedule(bar_date)
        completed_dates.append(now_et.time() > schedule["market_close"])
    return df.loc[completed_dates].copy()


def _resolve_heartbeat_bars(entry, stop, target, future_bars, max_hold_bars=10):
    status = "pending"
    exit_price = None
    exit_date = None
    return_pct = None
    same_bar_ambiguous = 0
    max_high = entry
    min_low = entry
    resolution_bar_index = None

    for idx, bar in future_bars.iloc[:max_hold_bars].iterrows():
        b_high = float(bar["High"])
        b_low = float(bar["Low"])
        b_date = str(bar["Date_Str"])
        max_high = max(max_high, b_high)
        min_low = min(min_low, b_low)

        hit_stop = b_low <= stop
        hit_target = b_high >= target
        if hit_stop and hit_target:
            same_bar_ambiguous = 1

        if hit_stop:
            status = "loss"
            exit_price = stop
            exit_date = b_date
            return_pct = (stop - entry) / entry
            resolution_bar_index = idx
            break
        if hit_target:
            status = "win"
            exit_price = target
            exit_date = b_date
            return_pct = (target - entry) / entry
            resolution_bar_index = idx
            break

    if status == "pending" and len(future_bars) >= max_hold_bars:
        last_bar = future_bars.iloc[max_hold_bars - 1]
        max_high = max(max_high, float(last_bar["High"]))
        min_low = min(min_low, float(last_bar["Low"]))
        status = "timeout"
        exit_price = float(last_bar["Close"])
        exit_date = str(last_bar["Date_Str"])
        return_pct = (exit_price - entry) / entry
        resolution_bar_index = future_bars.index[max_hold_bars - 1]

    if resolution_bar_index is None:
        return {
            "outcome_status": "pending",
            "mfe_pct": round((max_high - entry) / entry, 4),
            "mae_pct": round((min_low - entry) / entry, 4),
            "same_bar_ambiguous": same_bar_ambiguous,
        }

    return {
        "outcome_status": status,
        "exit_price": _round_money(exit_price),
        "exit_date": exit_date,
        "return_pct": round(return_pct, 4) if return_pct is not None else None,
        "mfe_pct": round((max_high - entry) / entry, 4),
        "mae_pct": round((min_low - entry) / entry, 4),
        "same_bar_ambiguous": same_bar_ambiguous,
    }


def resolve_pending_heartbeat_outcomes(max_hold_bars=10):
    """
    Resolves canonical Heartbeat outcomes using next regular-session open entries.
    Leaves rows pending when market data is not yet available.
    """
    import yfinance as yf

    conn = get_db_connection()
    attempted_at = datetime.now().isoformat()
    try:
        rows = conn.execute(
            """
            SELECT *
            FROM heartbeat_outcomes
            WHERE outcome_status = 'pending'
            ORDER BY id ASC;
            """
        ).fetchall()
        if not rows:
            return 0

        resolved_count = 0
        for row in rows:
            outcome = dict(row)
            outcome_id = outcome["id"]
            ticker = outcome["ticker"]
            try:
                hist = _completed_regular_session_history(yf.Ticker(ticker).history(period="6mo"))
                if hist is None:
                    with conn:
                        conn.execute(
                            """
                            UPDATE heartbeat_outcomes
                            SET resolution_data_asof = ?, resolution_error = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?;
                            """,
                            (attempted_at, "No market data returned by provider.", outcome_id)
                        )
                    continue

                entry_status = outcome["entry_status"]
                entry_date = outcome["entry_date"]
                entry = outcome["modeled_entry_price"]
                stop = outcome["modeled_stop"]
                target = outcome["modeled_target"]

                if entry_status == "pending":
                    signal_date = _parse_date_only(outcome["signal_date"])
                    if not signal_date:
                        with conn:
                            conn.execute(
                                """
                                UPDATE heartbeat_outcomes
                                SET resolution_data_asof = ?, resolution_error = ?, updated_at = CURRENT_TIMESTAMP
                                WHERE id = ?;
                                """,
                                (attempted_at, "Unable to parse signal_date for next-open reconstruction.", outcome_id)
                            )
                        continue

                    next_session = _next_regular_session_after(signal_date)
                    if not next_session:
                        with conn:
                            conn.execute(
                                """
                                UPDATE heartbeat_outcomes
                                SET resolution_data_asof = ?, resolution_error = ?, updated_at = CURRENT_TIMESTAMP
                                WHERE id = ?;
                                """,
                                (attempted_at, "Unable to determine next regular session.", outcome_id)
                            )
                        continue

                    entry_date = next_session.strftime("%Y-%m-%d")
                    entry_matches = hist.index[hist["Date_Str"] == entry_date].tolist()
                    if not entry_matches:
                        with conn:
                            conn.execute(
                                """
                                UPDATE heartbeat_outcomes
                                SET resolution_data_asof = ?, resolution_error = NULL, updated_at = CURRENT_TIMESTAMP
                                WHERE id = ?;
                                """,
                                (attempted_at, outcome_id)
                            )
                        continue

                    entry_idx = entry_matches[0]
                    entry = _round_money(hist.loc[entry_idx, "Open"])
                    stop, target = calculate_heartbeat_modeled_levels(entry)
                    with conn:
                        conn.execute(
                            """
                            UPDATE heartbeat_outcomes
                            SET entry_status = 'filled',
                                entry_date = ?,
                                modeled_entry_price = ?,
                                modeled_stop = ?,
                                modeled_target = ?,
                                resolution_data_asof = ?,
                                resolution_error = NULL,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?;
                            """,
                            (entry_date, entry, stop, target, attempted_at, outcome_id)
                        )
                else:
                    if entry is None or stop is None or target is None or not entry_date:
                        with conn:
                            conn.execute(
                                """
                                UPDATE heartbeat_outcomes
                                SET resolution_data_asof = ?, resolution_error = ?, updated_at = CURRENT_TIMESTAMP
                                WHERE id = ?;
                                """,
                                (attempted_at, "Filled outcome is missing entry/stop/target data.", outcome_id)
                            )
                        continue
                    entry = float(entry)
                    stop = float(stop)
                    target = float(target)

                entry_indices = hist.index[hist["Date_Str"] == entry_date].tolist()
                if not entry_indices:
                    with conn:
                        conn.execute(
                            """
                            UPDATE heartbeat_outcomes
                            SET resolution_data_asof = ?, resolution_error = NULL, updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?;
                            """,
                            (attempted_at, outcome_id)
                        )
                    continue

                future_bars = hist.iloc[entry_indices[0]: entry_indices[0] + max_hold_bars]
                resolution = _resolve_heartbeat_bars(float(entry), float(stop), float(target), future_bars, max_hold_bars=max_hold_bars)
                if resolution["outcome_status"] == "pending":
                    with conn:
                        conn.execute(
                            """
                            UPDATE heartbeat_outcomes
                            SET mfe_pct = ?,
                                mae_pct = ?,
                                same_bar_ambiguous = ?,
                                resolution_data_asof = ?,
                                resolution_error = NULL,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?;
                            """,
                            (
                                resolution.get("mfe_pct"),
                                resolution.get("mae_pct"),
                                int(resolution["same_bar_ambiguous"]),
                                attempted_at,
                                outcome_id,
                            )
                        )
                    continue

                with conn:
                    conn.execute(
                        """
                        UPDATE heartbeat_outcomes
                        SET outcome_status = ?,
                            exit_date = ?,
                            exit_price = ?,
                            return_pct = ?,
                            mfe_pct = ?,
                            mae_pct = ?,
                            same_bar_ambiguous = ?,
                            resolution_data_asof = ?,
                            resolution_error = NULL,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?;
                        """,
                        (
                            resolution["outcome_status"],
                            resolution["exit_date"],
                            resolution["exit_price"],
                            resolution["return_pct"],
                            resolution["mfe_pct"],
                            resolution["mae_pct"],
                            int(resolution["same_bar_ambiguous"]),
                            attempted_at,
                            outcome_id,
                        )
                    )
                resolved_count += 1
            except Exception as e:
                logging.error(f"Error resolving canonical heartbeat outcome {outcome_id} ({ticker}): {e}")
                with conn:
                    conn.execute(
                        """
                        UPDATE heartbeat_outcomes
                        SET resolution_data_asof = ?, resolution_error = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?;
                        """,
                        (attempted_at, str(e), outcome_id)
                    )

        return resolved_count
    except sqlite3.Error as e:
        logging.error(f"Database error resolving canonical heartbeat outcomes: {e}")
        return 0
    finally:
        conn.close()


def resolve_pending_alert_outcomes():
    """
    Evaluates all pending alerts against post-alert daily price history to resolve outcomes:
    - Technical Setups (Hammer / Hanging Man):
      - WIN: Price hit Profit Target (2:1 R/R)
      - LOSS: Price hit Stop Loss
      - TIMEOUT: Reached 10 trading bars without hitting target or stop
    - Growth Setups (Growth_*):
      - TIMEOUT: Reached 10 trading bars post-news; measures net return % over 10 trading bars
    - Heartbeat Setups (Heartbeat_*):
      - WIN: Price hit Heartbeat profit target
      - LOSS: Price hit Heartbeat stop loss
      - TIMEOUT: Reached 10 trading bars without hitting target or stop
    """
    import yfinance as yf
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        rows = cursor.execute("""
            SELECT id, ticker, pattern_type, day2_date, entry_price, stop_loss, profit_target 
            FROM sent_alerts 
            WHERE outcome_status = 'pending' AND entry_price IS NOT NULL
        """).fetchall()
        
        if not rows:
            return 0

        resolved_count = 0
        for r in rows:
            alert_id = r["id"]
            ticker = r["ticker"]
            p_type = r["pattern_type"]
            day2_str = r["day2_date"]
            entry = float(r["entry_price"]) if r["entry_price"] is not None else None
            stop = float(r["stop_loss"]) if r["stop_loss"] is not None else None
            target = float(r["profit_target"]) if r["profit_target"] is not None else None
            
            if entry is None:
                continue
                
            if p_type.startswith("Heartbeat_"):
                if stop is None:
                    stop = round(entry * 0.95, 2)
                    conn.execute("UPDATE sent_alerts SET stop_loss = ? WHERE id = ?;", (stop, alert_id))
                if target is None:
                    target = round(entry * 1.20, 2)
                    conn.execute("UPDATE sent_alerts SET profit_target = ? WHERE id = ?;", (target, alert_id))
                
            try:
                hist = yf.Ticker(ticker).history(period="3mo")
                if hist.empty:
                    continue
                hist = hist.reset_index()
                hist['Date_Str'] = hist['Date'].astype(str).str[:10]
                
                # Find index of day2_date or closest date
                match_indices = hist.index[hist['Date_Str'] == day2_str].tolist()
                if not match_indices:
                    match_indices = hist.index[hist['Date_Str'] >= day2_str].tolist()
                    if not match_indices:
                        continue
                
                start_idx = match_indices[0] + 1  # Day 3 onwards
                future_bars = hist.iloc[start_idx : start_idx + 10]
                
                if future_bars.empty:
                    continue
                
                status = "pending"
                exit_price = None
                exit_date = None
                return_pct = None

                tracks_target_stop = (
                    p_type in ("Hammer", "Hanging Man")
                    or p_type.startswith("Heartbeat_")
                ) and stop is not None and target is not None

                if tracks_target_stop:
                    for _, bar in future_bars.iterrows():
                        b_high = float(bar['High'])
                        b_low = float(bar['Low'])
                        b_date = str(bar['Date_Str'])

                        if p_type == "Hanging Man":  # Bearish Short
                            if b_high >= stop:
                                status = "loss"
                                exit_price = stop
                                exit_date = b_date
                                return_pct = (entry - stop) / entry
                                break
                            elif b_low <= target:
                                status = "win"
                                exit_price = target
                                exit_date = b_date
                                return_pct = (entry - target) / entry
                                break
                        else:  # Bullish Long: Hammer or Heartbeat
                            if b_low <= stop:
                                status = "loss"
                                exit_price = stop
                                exit_date = b_date
                                return_pct = (stop - entry) / entry
                                break
                            elif b_high >= target:
                                status = "win"
                                exit_price = target
                                exit_date = b_date
                                return_pct = (target - entry) / entry
                                break

                # Time-based resolution (10 trading bars elapsed) for unresolved setups.
                if status == "pending" and len(future_bars) >= 10:
                    last_bar = future_bars.iloc[-1]
                    status = "timeout"
                    exit_price = float(last_bar['Close'])
                    exit_date = str(last_bar['Date_Str'])
                    if p_type == "Hanging Man":
                        return_pct = (entry - exit_price) / entry
                    else:
                        return_pct = (exit_price - entry) / entry

                if status != "pending":
                    with conn:
                        conn.execute("""
                            UPDATE sent_alerts 
                            SET outcome_status = ?, exit_price = ?, exit_date = ?, return_pct = ? 
                            WHERE id = ?
                        """, (status, exit_price, exit_date, round(return_pct, 4) if return_pct is not None else None, alert_id))
                    resolved_count += 1

            except Exception as e:
                logging.error(f"Error resolving alert outcome for id {alert_id} ({ticker}): {e}")

        logging.info(f"Outcome Resolver processed {len(rows)} pending alerts and resolved {resolved_count} outcomes.")
        return resolved_count

    except sqlite3.Error as e:
        logging.error(f"Database error resolving alert outcomes: {e}")
        return 0
    finally:
        conn.close()



def get_historical_accuracy_stats(ticker=None, pattern_type=None):
    """
    Calculates historical win rate and return percentage for resolved technical candlestick alerts.
    """
    conn = get_db_connection()
    try:
        query = "SELECT outcome_status, return_pct FROM sent_alerts WHERE outcome_status IN ('win', 'loss', 'timeout')"
        params = []
        if ticker:
            query += " AND ticker = ?"
            params.append(ticker.strip().upper())
        if pattern_type:
            query += " AND pattern_type = ?"
            params.append(pattern_type)
        else:
            query += " AND pattern_type IN ('Hammer', 'Hanging Man')"
            
        cursor = conn.cursor()
        rows = cursor.execute(query, params).fetchall()
        
        if not rows:
            return {"total_resolved": 0, "wins": 0, "losses": 0, "win_rate": None, "avg_return_pct": 0.0}
            
        total = len(rows)
        wins = sum(1 for r in rows if r["outcome_status"] == "win")
        losses = sum(1 for r in rows if r["outcome_status"] == "loss")
        avg_ret = sum(r["return_pct"] or 0.0 for r in rows) / total
        win_rate = (wins / total) if total > 0 else 0.0
        
        return {
            "total_resolved": total,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 4),
            "avg_return_pct": round(avg_ret, 4)
        }
    except sqlite3.Error as e:
        logging.error(f"Database error fetching accuracy stats: {e}")
        return {"total_resolved": 0, "wins": 0, "losses": 0, "win_rate": None, "avg_return_pct": 0.0}
    finally:
        conn.close()


def get_all_alert_outcomes(limit=50, filter_technical_only=True, pattern_prefix=None):
    """
    Fetches historical sent alerts with their resolved outcomes for UI reporting.
    By default, restricts to Technical Candlestick Setups (Hammer / Hanging Man).
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT id, ticker, pattern_type, day1_date, day2_date, sent_at, entry_price, stop_loss, profit_target, outcome_status, exit_price, exit_date, return_pct
            FROM sent_alerts
        """
        params = []
        if pattern_prefix:
            query += " WHERE pattern_type LIKE ?"
            params.append(f"{pattern_prefix}%")
        elif filter_technical_only:
            query += " WHERE pattern_type IN ('Hammer', 'Hanging Man')"
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        
        rows = cursor.execute(query, params).fetchall()
        out_list = []
        for r in rows:
            d = dict(r)
            if d.get("pattern_type", "").startswith("Heartbeat_") and d.get("entry_price") is not None:
                ep = float(d["entry_price"])
                if d.get("stop_loss") is None:
                    d["stop_loss"] = round(ep * 0.95, 2)
                if d.get("profit_target") is None:
                    d["profit_target"] = round(ep * 1.20, 2)
            out_list.append(d)
        return out_list
    except sqlite3.Error as e:
        logging.error(f"Database error fetching alert outcomes: {e}")
        return []
    finally:
        conn.close()


def get_all_heartbeat_outcomes(limit=50):
    """
    Fetches canonical Heartbeat outcomes for audit reporting.
    """
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT
                o.*,
                h.catalyst_type,
                h.conviction_score
            FROM heartbeat_outcomes o
            LEFT JOIN heartbeat_discoveries h ON h.id = o.discovery_id
            ORDER BY o.id DESC
            LIMIT ?;
            """,
            (limit,)
        ).fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        logging.error(f"Database error fetching canonical heartbeat outcomes: {e}")
        return []
    finally:
        conn.close()


def get_heartbeat_outcome_summary():
    """
    Returns methodology-aware Heartbeat outcome counts and comparable next-open performance.
    """
    conn = get_db_connection()
    try:
        rows = conn.execute("SELECT * FROM heartbeat_outcomes;").fetchall()
        summary = {
            "total": len(rows),
            "live": 0,
            "legacy_migrated": 0,
            "reconstructed": 0,
            "pending": 0,
            "filled": 0,
            "not_filled": 0,
            "resolved_next_open": 0,
            "wins_next_open": 0,
            "profitable_timeouts_next_open": 0,
            "return_sum_next_open": 0.0,
        }
        for row in rows:
            source_type = row["source_type"]
            if source_type in summary:
                summary[source_type] += 1
            if row["entry_status"] == "filled":
                summary["filled"] += 1
            elif row["entry_status"] == "not_filled":
                summary["not_filled"] += 1
            if row["outcome_status"] == "pending":
                summary["pending"] += 1

            comparable = source_type in ("live", "reconstructed")
            resolved = row["outcome_status"] in ("win", "loss", "timeout")
            if comparable and resolved and row["return_pct"] is not None:
                summary["resolved_next_open"] += 1
                summary["return_sum_next_open"] += float(row["return_pct"])
                if row["outcome_status"] == "win":
                    summary["wins_next_open"] += 1
                elif row["outcome_status"] == "timeout" and float(row["return_pct"]) > 0:
                    summary["profitable_timeouts_next_open"] += 1

        if summary["resolved_next_open"]:
            summary["win_rate_next_open"] = round(summary["wins_next_open"] / summary["resolved_next_open"], 4)
            summary["avg_return_next_open"] = round(summary["return_sum_next_open"] / summary["resolved_next_open"], 4)
        else:
            summary["win_rate_next_open"] = None
            summary["avg_return_next_open"] = 0.0
        return summary
    except sqlite3.Error as e:
        logging.error(f"Database error fetching heartbeat outcome summary: {e}")
        return {
            "total": 0,
            "live": 0,
            "legacy_migrated": 0,
            "reconstructed": 0,
            "pending": 0,
            "filled": 0,
            "not_filled": 0,
            "resolved_next_open": 0,
            "wins_next_open": 0,
            "profitable_timeouts_next_open": 0,
            "return_sum_next_open": 0.0,
            "win_rate_next_open": None,
            "avg_return_next_open": 0.0,
        }
    finally:
        conn.close()


def update_scheduler_last_run(scan_type="technical"):
    """
    Atomically updates last_run_timestamp, growth_last_run_timestamp, or heartbeat_last_run_timestamp 
    BEFORE scan execution to prevent duplicate concurrent scan triggers.
    """
    conn = get_db_connection()
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
        with conn:
            if scan_type == "growth":
                conn.execute("UPDATE scheduler_state SET growth_last_run_timestamp = ? WHERE id = 1;", (now_str,))
            elif scan_type == "heartbeat":
                conn.execute("UPDATE scheduler_state SET heartbeat_last_run_timestamp = ? WHERE id = 1;", (now_str,))
            else:
                conn.execute("UPDATE scheduler_state SET last_run_timestamp = ? WHERE id = 1;", (now_str,))
        return True
    except sqlite3.Error as e:
        logging.error(f"Database error updating scheduler last run: {e}")
        return False
    finally:
        conn.close()

def record_scan_log(duration_seconds, tickers_scanned, signals_found, alerts_sent, trigger_type="manual"):
    """
    Records execution metrics of a scanner run.
    """
    conn = get_db_connection()
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
        with conn:
            conn.execute(
                """
                INSERT INTO scanner_logs (timestamp, duration_seconds, tickers_scanned, signals_found, alerts_sent, trigger_type)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (now_str, round(duration_seconds, 2), tickers_scanned, signals_found, alerts_sent, trigger_type)
            )
            if "growth" in str(trigger_type).lower():
                conn.execute("UPDATE scheduler_state SET growth_last_run_timestamp = ? WHERE id = 1;", (now_str,))
            elif "heartbeat" in str(trigger_type).lower():
                conn.execute("UPDATE scheduler_state SET heartbeat_last_run_timestamp = ? WHERE id = 1;", (now_str,))
            else:
                conn.execute("UPDATE scheduler_state SET last_run_timestamp = ? WHERE id = 1;", (now_str,))
        return True
    except sqlite3.Error as e:
        logging.error(f"Database error recording scan log: {e}")
        return False
    finally:
        conn.close()


def get_last_scan_log(trigger_prefix=None, exclude_prefix=None):
    """
    Returns the most recent scan log record (optionally filtered by trigger_type).
    """
    conn = get_db_connection()
    try:
        if trigger_prefix:
            row = conn.execute("SELECT * FROM scanner_logs WHERE trigger_type LIKE ? ORDER BY id DESC LIMIT 1;", (f"%{trigger_prefix}%",)).fetchone()
        elif exclude_prefix:
            row = conn.execute("SELECT * FROM scanner_logs WHERE trigger_type NOT LIKE ? ORDER BY id DESC LIMIT 1;", (f"%{exclude_prefix}%",)).fetchone()
        else:
            row = conn.execute("SELECT * FROM scanner_logs ORDER BY id DESC LIMIT 1;").fetchone()
        return dict(row) if row else None
    except sqlite3.Error as e:
        logging.error(f"Database error getting last scan log: {e}")
        return None
    finally:
        conn.close()

def get_all_scan_logs(limit=25, filter_type=None):
    """
    Returns recent scan logs, with optional filtering by scanner type or trigger category.
    """
    conn = get_db_connection()
    try:
        if filter_type == "technical":
            query = "SELECT * FROM scanner_logs WHERE trigger_type NOT LIKE '%growth%' AND trigger_type NOT LIKE '%heartbeat%' ORDER BY id DESC LIMIT ?;"
            rows = conn.execute(query, (limit,)).fetchall()
        elif filter_type == "growth":
            query = "SELECT * FROM scanner_logs WHERE trigger_type LIKE '%growth%' ORDER BY id DESC LIMIT ?;"
            rows = conn.execute(query, (limit,)).fetchall()
        elif filter_type == "heartbeat":
            query = "SELECT * FROM scanner_logs WHERE trigger_type LIKE '%heartbeat%' ORDER BY id DESC LIMIT ?;"
            rows = conn.execute(query, (limit,)).fetchall()
        elif filter_type == "scheduled":
            query = "SELECT * FROM scanner_logs WHERE trigger_type LIKE '%scheduled%' ORDER BY id DESC LIMIT ?;"
            rows = conn.execute(query, (limit,)).fetchall()
        elif filter_type == "manual":
            query = "SELECT * FROM scanner_logs WHERE trigger_type LIKE '%manual%' ORDER BY id DESC LIMIT ?;"
            rows = conn.execute(query, (limit,)).fetchall()
        else:
            query = "SELECT * FROM scanner_logs ORDER BY id DESC LIMIT ?;"
            rows = conn.execute(query, (limit,)).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error as e:
        logging.error(f"Database error getting scan logs: {e}")
        return []
    finally:
        conn.close()

def set_scheduler_active(is_active):
    """
    Toggles candlestick auto-scheduler active state and records start timestamp.
    """
    conn = get_db_connection()
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p") if is_active else None
        with conn:
            conn.execute(
                "UPDATE scheduler_state SET is_active = ?, start_timestamp = CASE WHEN ? = 1 THEN ? ELSE NULL END WHERE id = 1;",
                (1 if is_active else 0, 1 if is_active else 0, now_str)
            )
        return True
    except sqlite3.Error as e:
        logging.error(f"Database error setting scheduler active: {e}")
        return False
    finally:
        conn.close()

def set_growth_scheduler_active(is_active):
    """
    Toggles growth auto-scheduler active state and records start timestamp.
    """
    conn = get_db_connection()
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p") if is_active else None
        with conn:
            conn.execute(
                "UPDATE scheduler_state SET growth_is_active = ?, growth_start_timestamp = CASE WHEN ? = 1 THEN ? ELSE NULL END WHERE id = 1;",
                (1 if is_active else 0, 1 if is_active else 0, now_str)
            )
        return True
    except sqlite3.Error as e:
        logging.error(f"Database error setting growth scheduler active: {e}")
        return False
    finally:
        conn.close()

def get_scheduler_state():
    """
    Returns current auto-scheduler toggle state and start timestamp for both scanners.
    """
    conn = get_db_connection()
    try:
        row = conn.execute("SELECT * FROM scheduler_state WHERE id = 1;").fetchone()
        return dict(row) if row else {
            "is_active": 0, "start_timestamp": None, "last_run_timestamp": None,
            "growth_is_active": 0, "growth_start_timestamp": None, "growth_last_run_timestamp": None
        }
    except sqlite3.Error as e:
        logging.error(f"Database error getting scheduler state: {e}")
        return {
            "is_active": 0, "start_timestamp": None, "last_run_timestamp": None,
            "growth_is_active": 0, "growth_start_timestamp": None, "growth_last_run_timestamp": None
        }
    finally:
        conn.close()

def get_system_health():
    """
    Returns system database connectivity status, SQLite journal mode, and scheduler timestamps.
    Used by healthcheck scripts and system monitoring.
    """
    conn = get_db_connection()
    try:
        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        integrity = conn.execute("PRAGMA quick_check;").fetchone()[0]
        state = get_scheduler_state()
        last_log = get_last_scan_log()
        return {
            "status": "healthy" if integrity == "ok" else "unhealthy",
            "journal_mode": journal_mode,
            "integrity_check": integrity,
            "scheduler_state": state,
            "last_scan_log": last_log
        }
    except Exception as e:
        logging.error(f"Healthcheck database error: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        conn.close()


def record_growth_discovery(ticker, growth_score, catalyst_type, headline_summary="", initial_price=None,
                            key_catalysts=None, risks=None, plain_english_takeaway="", news_articles=None, vol_mult=None):
    """
    Records a new AI Growth Discovery in sentinel.db or updates last_featured_date if existing.
    Persists rich catalyst details, risks, takeaways, and news articles for email rendering.
    """
    ticker = ticker.strip().upper()
    now_str = datetime.now().strftime("%Y-%m-%d")
    conn = get_db_connection()
    k_json = json.dumps(key_catalysts or [])
    r_json = json.dumps(risks or [])
    n_json = json.dumps(news_articles or [])
    try:
        with conn:
            conn.execute("""
                INSERT INTO growth_discoveries 
                (ticker, discovery_date, initial_price, growth_score, catalyst_type, headline_summary, last_featured_date, status, key_catalysts_json, risks_json, plain_english_takeaway, news_articles_json, vol_mult)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active_monitoring', ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, discovery_date) DO UPDATE SET
                    growth_score = excluded.growth_score,
                    headline_summary = excluded.headline_summary,
                    last_featured_date = excluded.last_featured_date,
                    key_catalysts_json = excluded.key_catalysts_json,
                    risks_json = excluded.risks_json,
                    plain_english_takeaway = excluded.plain_english_takeaway,
                    news_articles_json = excluded.news_articles_json,
                    vol_mult = excluded.vol_mult;
            """, (ticker, now_str, initial_price, float(growth_score), catalyst_type, headline_summary, now_str, k_json, r_json, plain_english_takeaway, n_json, vol_mult))
        logging.info(f"Recorded Growth Discovery for {ticker} (Score: {growth_score:.1f}, Price: {initial_price})")
        return True
    except sqlite3.Error as e:
        logging.error(f"Database error recording growth discovery for {ticker}: {e}")
        return False
    finally:
        conn.close()


def is_growth_in_cooldown(ticker, cooldown_days=5):
    """
    Checks if a ticker was featured in growth_discoveries within the last N days.
    """
    ticker = ticker.strip().upper()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute("""
            SELECT last_featured_date FROM growth_discoveries 
            WHERE ticker = ? 
            ORDER BY id DESC LIMIT 1;
        """, (ticker,)).fetchone()
        
        if not row:
            return False
            
        last_date_str = row["last_featured_date"]
        try:
            last_dt = datetime.strptime(last_date_str[:10], "%Y-%m-%d")
            delta_days = (datetime.now() - last_dt).days
            return delta_days < cooldown_days
        except Exception:
            return False
    except sqlite3.Error as e:
        logging.error(f"Database error checking growth cooldown for {ticker}: {e}")
        return False
    finally:
        conn.close()


def get_growth_discovery_by_ticker(ticker):
    """
    Fetches the latest growth discovery record for a specific ticker to populate the Synergy email context box.
    """
    ticker = ticker.strip().upper()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute("""
            SELECT * FROM growth_discoveries 
            WHERE ticker = ? 
            ORDER BY id DESC LIMIT 1;
        """, (ticker,)).fetchone()
        return dict(row) if row else None
    except sqlite3.Error as e:
        logging.error(f"Database error fetching growth discovery for {ticker}: {e}")
        return None
    finally:
        conn.close()


def get_recent_growth_discoveries(limit=30):
    """
    Fetches all recent growth discoveries for UI reporting in Section 3 and outcome tracking.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        rows = cursor.execute("""
            SELECT * FROM growth_discoveries 
            ORDER BY id DESC LIMIT ?;
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error as e:
        logging.error(f"Database error fetching recent growth discoveries: {e}")
        return []
    finally:
        conn.close()


def set_heartbeat_scheduler_active(is_active):
    """
    Sets the heartbeat auto-scheduler active toggle state.
    """
    conn = get_db_connection()
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with conn:
            if is_active:
                conn.execute(
                    "UPDATE scheduler_state SET heartbeat_is_active = 1, heartbeat_start_timestamp = ? WHERE id = 1;",
                    (now_str,)
                )
            else:
                conn.execute(
                    "UPDATE scheduler_state SET heartbeat_is_active = 0, heartbeat_start_timestamp = NULL WHERE id = 1;"
                )
        return True
    except sqlite3.Error as e:
        logging.error(f"Database error setting heartbeat scheduler active: {e}")
        return False
    finally:
        conn.close()


def record_heartbeat_discovery(ticker, conviction_score, catalyst_type, headline_summary="", initial_price=None,
                               key_catalysts=None, risks=None, plain_english_takeaway="", news_articles=None,
                               badge_tag="", badge_color="", vol_mult=None, bb_width_pct=None, above_200sma=None):
    """
    Records a new AI Heartbeat Volatility Discovery in sentinel.db or updates last_featured_date if existing.
    Persists rich catalyst details, risks, takeaways, badges, and news articles for email rendering.
    """
    ticker = ticker.strip().upper()
    now_date = datetime.now().strftime("%Y-%m-%d")
    now_timestamp = datetime.now().isoformat()
    conn = get_db_connection()
    k_json = json.dumps(key_catalysts or [])
    r_json = json.dumps(risks or [])
    n_json = json.dumps(news_articles or [])
    try:
        cursor = conn.cursor()
        existing = cursor.execute(
            "SELECT id FROM heartbeat_discoveries WHERE ticker = ? AND discovery_date = ?;",
            (ticker, now_date)
        ).fetchone()

        with conn:
            if existing:
                conn.execute(
                    """
                    UPDATE heartbeat_discoveries 
                    SET conviction_score = ?, catalyst_type = ?, headline_summary = ?, last_featured_date = ?,
                        key_catalysts_json = ?, risks_json = ?, plain_english_takeaway = ?, news_articles_json = ?,
                        badge_tag = ?, badge_color = ?, vol_mult = ?, bb_width_pct = ?, above_200sma = ?
                    WHERE id = ?;
                    """,
                    (float(conviction_score), catalyst_type, headline_summary, now_date, k_json, r_json, plain_english_takeaway, n_json, badge_tag, badge_color, vol_mult, bb_width_pct, 1 if above_200sma else 0, existing["id"])
                )
                discovery_id = existing["id"]
                created = False
                updated = True
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO heartbeat_discoveries 
                    (ticker, discovery_date, initial_price, conviction_score, catalyst_type, headline_summary, last_featured_date, key_catalysts_json, risks_json, plain_english_takeaway, news_articles_json, badge_tag, badge_color, vol_mult, bb_width_pct, above_200sma)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (ticker, now_date, initial_price, float(conviction_score), catalyst_type, headline_summary, now_date, k_json, r_json, plain_english_takeaway, n_json, badge_tag, badge_color, vol_mult, bb_width_pct, 1 if above_200sma else 0)
                )
                discovery_id = cursor.lastrowid
                created = True
                updated = False
            outcome = ensure_heartbeat_outcome_for_discovery(discovery_id, source_type="live", conn=conn)
            if not outcome:
                raise sqlite3.Error(f"Failed to create canonical heartbeat outcome for discovery {discovery_id}")
        return {
            "discovery_id": discovery_id,
            "created": created,
            "updated": updated,
            "signal_timestamp": now_timestamp,
        }
    except sqlite3.Error as e:
        logging.error(f"Database error recording heartbeat discovery for {ticker}: {e}")
        return None
    finally:
        conn.close()


def _parse_iso_date(date_str):
    try:
        return datetime.strptime(str(date_str)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _is_trading_weekday(day):
    return day.weekday() < 5


def _trading_weekdays_elapsed_since(start_date, end_date=None):
    """
    Counts trading weekdays after start_date through end_date.
    Weekends are excluded; exchange holidays are not modeled.
    """
    if not start_date:
        return 0
    end_date = end_date or datetime.now().date()
    if end_date <= start_date:
        return 0

    elapsed = 0
    current = start_date + timedelta(days=1)
    while current <= end_date:
        if _is_trading_weekday(current):
            elapsed += 1
        current += timedelta(days=1)
    return elapsed


def _add_trading_weekdays(start_date, trading_days):
    if not start_date:
        return None

    added = 0
    current = start_date
    while added < trading_days:
        current += timedelta(days=1)
        if _is_trading_weekday(current):
            added += 1
    return current


def get_heartbeat_cooldown_summary(last_featured_date, cooldown_days=5):
    """
    Returns UI-friendly Heartbeat cooldown metadata based on trading weekdays.
    """
    last_date = _parse_iso_date(last_featured_date)
    if not last_date:
        return {
            "cooldown_days_remaining": None,
            "eligible_again_date": None,
            "cooldown_status": "Unknown",
        }

    elapsed = _trading_weekdays_elapsed_since(last_date)
    days_remaining = max(0, cooldown_days - elapsed)
    eligible_date = _add_trading_weekdays(last_date, cooldown_days)
    eligible_str = eligible_date.strftime("%Y-%m-%d") if eligible_date else None

    if days_remaining <= 0:
        status = f"Eligible now (since {eligible_str})" if eligible_str else "Eligible now"
    elif days_remaining == 1:
        status = "In cooldown: 1 trading day left"
    else:
        status = f"In cooldown: {days_remaining} trading days left"

    return {
        "cooldown_days_remaining": days_remaining,
        "eligible_again_date": eligible_str,
        "cooldown_status": status,
    }


def check_heartbeat_cooldown_status(ticker, conviction_score=0.0, cooldown_days=5):
    """
    Implements Smart Conditional Cooldown for Heartbeat setups:
    - Case 1: Suppressed if featured within 5 trading days AND score/news hasn't improved.
    - Case 2: Re-triggered with '🔥 MULTI-DAY MOMENTUM CONTINUATION' if conviction score increased by >= 5.0 points.
    Returns dict: {'is_suppressed': bool, 'is_retrigger': bool}
    """
    ticker = ticker.strip().upper()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute(
            """
            SELECT last_featured_date, conviction_score FROM heartbeat_discoveries 
            WHERE ticker = ? 
            ORDER BY id DESC LIMIT 1;
            """,
            (ticker,)
        ).fetchone()

        if not row:
            return {"is_suppressed": False, "is_retrigger": False}

        last_date_str = row["last_featured_date"]
        prev_score = float(row["conviction_score"] or 0.0)

        try:
            last_date = _parse_iso_date(last_date_str)
            elapsed_trading_days = _trading_weekdays_elapsed_since(last_date)

            if elapsed_trading_days >= cooldown_days:
                return {"is_suppressed": False, "is_retrigger": False}

            # If within 5 days, check if score increased significantly (+5.0 points)
            if float(conviction_score) >= prev_score + 5.0:
                logging.info(f"🔥 Heartbeat re-trigger for {ticker}: Conviction score jumped from {prev_score:.1f} to {conviction_score:.1f}")
                return {"is_suppressed": False, "is_retrigger": True}

            # Otherwise suppressed as duplicate
            return {"is_suppressed": True, "is_retrigger": False}

        except Exception:
            return {"is_suppressed": False, "is_retrigger": False}

    except sqlite3.Error as e:
        logging.error(f"Database error checking heartbeat cooldown for {ticker}: {e}")
        return {"is_suppressed": False, "is_retrigger": False}
    finally:
        conn.close()


def get_recent_heartbeat_discoveries(limit=30):
    """
    Fetches all recent heartbeat discoveries for UI reporting in Section 3 and outcome tracking.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        rows = cursor.execute("""
            SELECT * FROM heartbeat_discoveries 
            ORDER BY id DESC LIMIT ?;
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error as e:
        logging.error(f"Database error fetching recent heartbeat discoveries: {e}")
        return []
    finally:
        conn.close()


def get_subscriber_paper_position_size(token):
    """
    Returns the subscriber's configured paper benchmark position size (defaults to 500.0).
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute("SELECT paper_position_size FROM subscribers WHERE management_token = ?;", (token,)).fetchone()
        if row and row["paper_position_size"] is not None:
            return float(row["paper_position_size"])
        return 500.0
    except sqlite3.Error as e:
        logging.error(f"Database error getting subscriber paper position size: {e}")
        return 500.0
    finally:
        conn.close()


def update_subscriber_paper_position_size(token, position_size):
    """
    Updates the subscriber's configured paper benchmark position size.
    """
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                "UPDATE subscribers SET paper_position_size = ? WHERE management_token = ?;",
                (float(position_size), token)
            )
        return True
    except sqlite3.Error as e:
        logging.error(f"Database error updating subscriber paper position size: {e}")
        return False
    finally:
        conn.close()


def get_ticker_heartbeat_blueprint(ticker):
    """
    Fetches the latest recorded Heartbeat blueprint (entry_price, stop_loss, profit_target, outcome_status) for a ticker.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute("""
            SELECT entry_price, stop_loss, profit_target, outcome_status, return_pct
            FROM sent_alerts 
            WHERE ticker = ? AND pattern_type LIKE 'Heartbeat_%' AND entry_price IS NOT NULL
            ORDER BY id DESC LIMIT 1;
        """, (ticker.upper(),)).fetchone()
        if row:
            return dict(row)
        return None
    except sqlite3.Error as e:
        logging.error(f"Database error fetching ticker heartbeat blueprint for {ticker}: {e}")
        return None
    finally:
        conn.close()



# ----------------------------------------------------
# PAPER PORTFOLIO SIMULATOR FUNCTIONS
# ----------------------------------------------------
DEFAULT_PAPER_ACCOUNT_LABELS = ("Account 1", "Account 2")
MAX_PAPER_ACCOUNTS = 5


def _clean_paper_account_label(account_label):
    label = (account_label or "").strip()
    return label[:60] if label else ""


def _ensure_default_paper_accounts(conn, subscriber_id):
    account_count = conn.execute("""
        SELECT COUNT(*) AS count
        FROM paper_accounts
        WHERE subscriber_id = ?;
    """, (subscriber_id,)).fetchone()["count"]
    if account_count == 0:
        for label in DEFAULT_PAPER_ACCOUNT_LABELS:
            conn.execute("""
                INSERT OR IGNORE INTO paper_accounts (subscriber_id, account_label)
                VALUES (?, ?);
            """, (subscriber_id, label))

    existing_trade_accounts = conn.execute("""
        SELECT DISTINCT account_label
        FROM paper_trades
        WHERE subscriber_id = ? AND account_label IS NOT NULL AND TRIM(account_label) != '';
    """, (subscriber_id,)).fetchall()
    for row in existing_trade_accounts:
        conn.execute("""
            INSERT OR IGNORE INTO paper_accounts (subscriber_id, account_label)
            VALUES (?, ?);
        """, (subscriber_id, row["account_label"]))


def get_paper_accounts(subscriber_id):
    """
    Returns persisted paper trading account labels for a subscriber.
    Ensures the two original default accounts exist for backward compatibility.
    """
    conn = get_db_connection()
    try:
        with conn:
            _ensure_default_paper_accounts(conn, subscriber_id)
        rows = conn.execute("""
            SELECT id, account_label, created_at
            FROM paper_accounts
            WHERE subscriber_id = ?
            ORDER BY id ASC;
        """, (subscriber_id,)).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error as e:
        logging.error(f"Database error getting paper accounts: {e}")
        return [{"id": 0, "account_label": "Account 1"}, {"id": 0, "account_label": "Account 2"}]
    finally:
        conn.close()


def add_paper_account(subscriber_id, account_label=None):
    """
    Creates a new paper trading account for a subscriber.
    If no label is supplied, picks the next available Account N label.
    """
    conn = get_db_connection()
    try:
        with conn:
            _ensure_default_paper_accounts(conn, subscriber_id)
            account_count = conn.execute("""
                SELECT COUNT(*) AS count
                FROM paper_accounts
                WHERE subscriber_id = ?;
            """, (subscriber_id,)).fetchone()["count"]
            if account_count >= MAX_PAPER_ACCOUNTS:
                return False, f"You can only have up to {MAX_PAPER_ACCOUNTS} paper portfolios."

            label = _clean_paper_account_label(account_label)
            if not label:
                existing = conn.execute("""
                    SELECT account_label
                    FROM paper_accounts
                    WHERE subscriber_id = ?;
                """, (subscriber_id,)).fetchall()
                existing_labels = {row["account_label"] for row in existing}
                next_num = len(existing_labels) + 1
                label = f"Account {next_num}"
                while label in existing_labels:
                    next_num += 1
                    label = f"Account {next_num}"

            conn.execute("""
                INSERT INTO paper_accounts (subscriber_id, account_label)
                VALUES (?, ?);
            """, (subscriber_id, label))
        return True, f"Added paper portfolio: {label}"
    except sqlite3.IntegrityError:
        return False, "That paper portfolio name already exists."
    except sqlite3.Error as e:
        logging.error(f"Database error adding paper account: {e}")
        return False, f"Database error: {e}"
    finally:
        conn.close()


def delete_paper_account(subscriber_id, account_label):
    """
    Deletes a paper trading account and all paper trades inside it.
    Keeps at least one paper portfolio available for the subscriber.
    """
    account_label = _clean_paper_account_label(account_label)
    if not account_label:
        return False, "Paper portfolio name is required."

    conn = get_db_connection()
    try:
        with conn:
            _ensure_default_paper_accounts(conn, subscriber_id)
            account_count = conn.execute("""
                SELECT COUNT(*) AS count
                FROM paper_accounts
                WHERE subscriber_id = ?;
            """, (subscriber_id,)).fetchone()["count"]
            if account_count <= 1:
                return False, "You need at least one paper portfolio."

            existing = conn.execute("""
                SELECT id
                FROM paper_accounts
                WHERE subscriber_id = ? AND account_label = ?;
            """, (subscriber_id, account_label)).fetchone()
            if not existing:
                return False, "Paper portfolio not found."

            conn.execute("""
                DELETE FROM paper_trades
                WHERE subscriber_id = ? AND account_label = ?;
            """, (subscriber_id, account_label))
            conn.execute("""
                DELETE FROM paper_accounts
                WHERE subscriber_id = ? AND account_label = ?;
            """, (subscriber_id, account_label))
        return True, f"Deleted paper portfolio: {account_label}"
    except sqlite3.Error as e:
        logging.error(f"Database error deleting paper account: {e}")
        return False, f"Database error: {e}"
    finally:
        conn.close()


def rename_paper_account(subscriber_id, old_account_label, new_account_label):
    """
    Renames a paper trading account and moves its existing paper trades to the new label.
    """
    old_account_label = _clean_paper_account_label(old_account_label)
    new_account_label = _clean_paper_account_label(new_account_label)
    if not old_account_label or not new_account_label:
        return False, "Paper portfolio name is required."
    if old_account_label == new_account_label:
        return False, "Please enter a new portfolio name."

    conn = get_db_connection()
    try:
        with conn:
            _ensure_default_paper_accounts(conn, subscriber_id)
            existing = conn.execute("""
                SELECT id
                FROM paper_accounts
                WHERE subscriber_id = ? AND account_label = ?;
            """, (subscriber_id, old_account_label)).fetchone()
            if not existing:
                return False, "Paper portfolio not found."

            duplicate = conn.execute("""
                SELECT id
                FROM paper_accounts
                WHERE subscriber_id = ? AND account_label = ?;
            """, (subscriber_id, new_account_label)).fetchone()
            if duplicate:
                return False, "That paper portfolio name already exists."

            conn.execute("""
                UPDATE paper_accounts
                SET account_label = ?
                WHERE subscriber_id = ? AND account_label = ?;
            """, (new_account_label, subscriber_id, old_account_label))
            conn.execute("""
                UPDATE paper_trades
                SET account_label = ?
                WHERE subscriber_id = ? AND account_label = ?;
            """, (new_account_label, subscriber_id, old_account_label))
        return True, f"Renamed paper portfolio to: {new_account_label}"
    except sqlite3.IntegrityError:
        return False, "That paper portfolio name already exists."
    except sqlite3.Error as e:
        logging.error(f"Database error renaming paper account: {e}")
        return False, f"Database error: {e}"
    finally:
        conn.close()


def add_paper_trade(subscriber_id, ticker, total_invested=None, shares=None, entry_price=None, account_label="Account 1"):
    """
    Adds a new paper trade for subscriber.
    Accepts either total_invested ($) or shares quantity.
    Fetches current market price if entry_price is not provided.
    """
    ticker = ticker.strip().upper()
    if not ticker:
        return False, "Ticker symbol is required."
    account_label = (account_label or "Account 1").strip() or "Account 1"

    if entry_price is None or float(entry_price) <= 0:
        try:
            import yfinance as yf
            data = yf.Ticker(ticker).history(period="1d")
            if not data.empty and "Close" in data:
                entry_price = float(data["Close"].iloc[-1])
            else:
                return False, f"Could not fetch current market price for {ticker}."
        except Exception as e:
            return False, f"Error fetching price for {ticker}: {e}"

    entry_price = float(entry_price)

    if shares is not None and float(shares) > 0:
        shares = float(shares)
        total_invested = shares * entry_price
    elif total_invested is not None and float(total_invested) > 0:
        total_invested = float(total_invested)
        shares = total_invested / entry_price
    else:
        return False, "Please specify a valid total dollar investment or share quantity."

    entry_date = datetime.now().strftime("%Y-%m-%d %H:%M")

    conn = get_db_connection()
    try:
        with conn:
            conn.execute("""
                INSERT OR IGNORE INTO paper_accounts (subscriber_id, account_label)
                VALUES (?, ?);
            """, (subscriber_id, account_label))
            conn.execute("""
                INSERT INTO paper_trades (subscriber_id, account_label, ticker, entry_date, entry_price, total_invested, shares, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN');
            """, (subscriber_id, account_label, ticker, entry_date, entry_price, total_invested, shares))
        return True, f"Successfully added paper position: {shares:.3f} shares of {ticker} @ ${entry_price:,.2f} (${total_invested:,.2f})!"
    except sqlite3.Error as e:
        logging.error(f"Database error adding paper trade: {e}")
        return False, f"Database error: {e}"
    finally:
        conn.close()

def get_open_paper_trades(subscriber_id, account_label="Account 1"):
    """
    Returns list of open paper trades for subscriber.
    """
    conn = get_db_connection()
    try:
        account_label = (account_label or "Account 1").strip() or "Account 1"
        cursor = conn.cursor()
        rows = cursor.execute("""
            SELECT id, account_label, ticker, entry_date, entry_price, total_invested, shares, status
            FROM paper_trades
            WHERE subscriber_id = ? AND account_label = ? AND status = 'OPEN'
            ORDER BY id DESC;
        """, (subscriber_id, account_label)).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error as e:
        logging.error(f"Database error getting open paper trades: {e}")
        return []
    finally:
        conn.close()

def get_closed_paper_trades(subscriber_id, account_label="Account 1"):
    """
    Returns list of closed paper trades for subscriber.
    """
    conn = get_db_connection()
    try:
        account_label = (account_label or "Account 1").strip() or "Account 1"
        cursor = conn.cursor()
        rows = cursor.execute("""
            SELECT id, account_label, ticker, entry_date, entry_price, total_invested, shares, status, exit_date, exit_price, realized_pnl
            FROM paper_trades
            WHERE subscriber_id = ? AND account_label = ? AND status = 'CLOSED'
            ORDER BY exit_date DESC, id DESC;
        """, (subscriber_id, account_label)).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error as e:
        logging.error(f"Database error getting closed paper trades: {e}")
        return []
    finally:
        conn.close()

def close_paper_trade(trade_id, exit_price=None):
    """
    Closes an open paper trade, recording exit date, exit price, and realized profit/loss.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute("SELECT ticker, entry_price, shares, total_invested FROM paper_trades WHERE id = ?;", (trade_id,)).fetchone()
        if not row:
            return False, "Trade not found."

        ticker = row["ticker"]
        entry_price = float(row["entry_price"])
        shares = float(row["shares"])

        if exit_price is None or float(exit_price) <= 0:
            try:
                import yfinance as yf
                data = yf.Ticker(ticker).history(period="1d")
                if not data.empty and "Close" in data:
                    exit_price = float(data["Close"].iloc[-1])
                else:
                    return False, f"Could not fetch current market exit price for {ticker}."
            except Exception as e:
                return False, f"Error fetching exit price for {ticker}: {e}"

        exit_price = float(exit_price)
        exit_date = datetime.now().strftime("%Y-%m-%d %H:%M")
        current_val = exit_price * shares
        realized_pnl = current_val - float(row["total_invested"])

        with conn:
            conn.execute("""
                UPDATE paper_trades
                SET status = 'CLOSED', exit_date = ?, exit_price = ?, realized_pnl = ?
                WHERE id = ?;
            """, (exit_date, exit_price, realized_pnl, trade_id))
        return True, f"Closed paper position in {ticker} with P&L: {'+' if realized_pnl>=0 else ''}${realized_pnl:,.2f}"
    except sqlite3.Error as e:
        logging.error(f"Database error closing paper trade {trade_id}: {e}")
        return False, f"Database error: {e}"
    finally:
        conn.close()

def delete_paper_trade(trade_id):
    """
    Deletes a paper trade from database.
    """
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("DELETE FROM paper_trades WHERE id = ?;", (trade_id,))
        return True
    except sqlite3.Error as e:
        logging.error(f"Database error deleting paper trade {trade_id}: {e}")
        return False
    finally:
        conn.close()


# Automatically initialize database when database.py is imported or run directly
init_db()
