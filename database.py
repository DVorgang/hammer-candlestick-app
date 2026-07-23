import sqlite3
import os
import uuid
import logging
import random
from datetime import datetime, timedelta

DB_FILE = "sentinel.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def get_db_connection():
    """
    Establishes connection to the SQLite database and forces foreign key support.
    """
    try:
        conn = sqlite3.connect(DB_FILE)
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
    
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(create_subscribers_table)
            conn.execute(create_watchlists_table)
            conn.execute(create_sent_alerts_table)
            conn.execute(create_scanner_logs_table)
            conn.execute(create_scheduler_state_table)
            
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
                
            cursor_s = conn.execute("PRAGMA table_info(scheduler_state);")
            s_columns = [row["name"] for row in cursor_s.fetchall()]
            if "growth_is_active" not in s_columns:
                conn.execute("ALTER TABLE scheduler_state ADD COLUMN growth_is_active INTEGER DEFAULT 0;")
            if "growth_start_timestamp" not in s_columns:
                conn.execute("ALTER TABLE scheduler_state ADD COLUMN growth_start_timestamp TEXT;")
            if "growth_last_run_timestamp" not in s_columns:
                conn.execute("ALTER TABLE scheduler_state ADD COLUMN growth_last_run_timestamp TEXT;")
                
        logging.info("Database initialized successfully.")
    except sqlite3.Error as e:
        logging.error(f"Error initializing database: {e}")
        raise
    finally:
        conn.close()

def create_subscriber(email, wants_buys=1, wants_risks=1, wants_sells=1, initial_tickers=None):
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
                INSERT INTO subscribers (email, management_token, wants_buys, wants_risks, wants_sells)
                VALUES (?, ?, ?, ?, ?)
                """,
                (email.strip().lower(), token, int(wants_buys), int(wants_risks), int(wants_sells))
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
    Records that a subscriber received this exact setup alert.
    """
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO sent_alerts
                    (subscriber_id, ticker, pattern_type, day1_date, day2_date)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    subscriber_id,
                    signal["ticker"].strip().upper(),
                    signal["pattern_type"],
                    str(signal["day1_date"])[:10],
                    str(signal["day2_date"])[:10],
                )
            )
        return True
    except sqlite3.Error as e:
        logging.error(f"Database error recording sent alert: {e}")
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
            else:
                conn.execute("UPDATE scheduler_state SET last_run_timestamp = ? WHERE id = 1;", (now_str,))
        return True
    except sqlite3.Error as e:
        logging.error(f"Database error recording scan log: {e}")
        return False
    finally:
        conn.close()

def get_last_scan_log(trigger_prefix=None):
    """
    Returns the most recent scan log record (optionally filtered by trigger_type).
    """
    conn = get_db_connection()
    try:
        if trigger_prefix:
            row = conn.execute("SELECT * FROM scanner_logs WHERE trigger_type LIKE ? ORDER BY id DESC LIMIT 1;", (f"%{trigger_prefix}%",)).fetchone()
        else:
            row = conn.execute("SELECT * FROM scanner_logs ORDER BY id DESC LIMIT 1;").fetchone()
        return dict(row) if row else None
    except sqlite3.Error as e:
        logging.error(f"Database error getting last scan log: {e}")
        return None
    finally:
        conn.close()

def get_all_scan_logs(limit=10):
    """
    Returns recent scan logs.
    """
    conn = get_db_connection()
    try:
        rows = conn.execute("SELECT * FROM scanner_logs ORDER BY id DESC LIMIT ?;", (limit,)).fetchall()
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

# Automatically initialize database when database.py is imported or run directly
init_db()
