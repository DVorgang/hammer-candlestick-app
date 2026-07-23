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
    Establishes connection to the SQLite database with WAL mode, busy timeout, and foreign key support.
    """
    try:
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
                ("vol_mult_at_entry", "REAL")
            ]
            for col_name, col_type in alert_new_cols:
                if col_name not in a_columns:
                    conn.execute(f"ALTER TABLE sent_alerts ADD COLUMN {col_name} {col_type};")

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


def resolve_pending_alert_outcomes():
    """
    Evaluates all pending alerts against post-alert daily price history to resolve outcomes:
    - Technical Setups (Hammer / Hanging Man):
      - WIN: Price hit Profit Target (2:1 R/R)
      - LOSS: Price hit Stop Loss
      - TIMEOUT: Reached 10 trading bars without hitting target or stop
    - Growth Setups (Growth_*):
      - TIMEOUT: Reached 10 trading bars post-news; measures net return % over 10 trading bars
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

                if p_type in ("Hammer", "Hanging Man") and stop is not None and target is not None:
                    for _, bar in future_bars.iterrows():
                        b_high = float(bar['High'])
                        b_low = float(bar['Low'])
                        b_date = str(bar['Date_Str'])

                        if p_type == "Hammer":  # Bullish Long
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
                        else:  # Hanging Man Short
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

                # Time-based resolution (10 trading bars elapsed) for technical timeouts or growth catalysts
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
    Calculates historical win rate and return percentage for resolved alerts.
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


def get_all_alert_outcomes(limit=50):
    """
    Fetches historical sent alerts with their resolved outcomes for UI reporting.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        rows = cursor.execute("""
            SELECT id, ticker, pattern_type, day1_date, day2_date, sent_at, entry_price, stop_loss, profit_target, outcome_status, exit_price, exit_date, return_pct
            FROM sent_alerts
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error as e:
        logging.error(f"Database error fetching alert outcomes: {e}")
        return []
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

# Automatically initialize database when database.py is imported or run directly
init_db()
