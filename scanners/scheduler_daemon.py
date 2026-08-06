import sys
import os
import time
import logging
from datetime import datetime, timezone

# Force UTF-8 stdout formatting
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Configure logging
log_format = "%(asctime)s - %(levelname)s - %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("daemon_scanner.log", encoding="utf-8")
    ]
)

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.local_env import load_env_file
load_env_file()

from core import database
from core import market_calendar
from scanners import growth_scanner
from scanners import daily_scanner
from scanners import heartbeat_scanner
from scanners import digest_dispatcher

HEARTBEAT_PATH = os.path.join(os.environ.get("TMPDIR", "/tmp"), "worker_heartbeat.txt")
INTERVAL_MARKET_MINUTES = int(os.environ.get("SCAN_INTERVAL_MINUTES", "15"))
INTERVAL_OFFMARKET_MINUTES = 15

def update_heartbeat():
    """
    Writes current epoch timestamp to file for Docker healthcheck inspection.
    """
    try:
        with open(HEARTBEAT_PATH, "w", encoding="utf-8") as f:
            f.write(str(time.time()))
    except Exception as e:
        logging.error(f"Failed to update worker heartbeat file: {e}")

def start_daemon_loop():
    logging.info("=========================================")
    logging.info("🚀 Starting 24/7 Production Market Scanner Daemon (Calendar-Aware + Scheduled Digests)")
    logging.info(f"Market Interval: {INTERVAL_MARKET_MINUTES}m | Off-market Interval: {INTERVAL_OFFMARKET_MINUTES}m")
    logging.info("=========================================")
    
    database.init_db()
    database.set_scheduler_active(True)
    database.set_growth_scheduler_active(True)
    database.set_heartbeat_scheduler_active(True)
    
    last_daily_scan_date = None
    
    while True:
        try:
            update_heartbeat()
            m_status = market_calendar.get_market_status()
            now_et = m_status["datetime_et"]
            today_str = m_status["trading_date_str"]
            
            logging.info(f"⏰ Heartbeat check at {now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}")

            # 1. Pre-Market 9:00 AM Digest Delivery Window
            if m_status["is_am_digest_window"]:
                logging.info("🌅 Pre-Market 9:00 AM Window — Checking for 9:00 AM Digest Delivery...")
                digest_dispatcher.dispatch_scheduled_digests("AM_PREMARKET", today_str)

            # 2. Market Hours Active Intraday Scans (Growth & Heartbeat - Buffer Only)
            if m_status["is_market_hours"]:
                logging.info("📈 Market Hours Active — Triggering Growth & Heartbeat Intraday Scans (Buffer Mode)...")
                growth_scanner.run_growth_scan(trigger_type="24_7_daemon")
                heartbeat_scanner.run_heartbeat_scan(trigger_type="24_7_daemon")
                database.resolve_pending_heartbeat_outcomes()
                database.resolve_pending_alert_outcomes()
                sleep_seconds = INTERVAL_MARKET_MINUTES * 60
            
            # 3. Post-Close Daily Pattern Scan (Once per day)
            elif m_status["is_post_close"] and last_daily_scan_date != today_str:
                logging.info("🔔 Market Post-Close Window — Triggering Full Daily Candlestick Pattern Scan...")
                daily_scanner.run_daily_scan(trigger_type="24_7_daemon")
                database.resolve_pending_heartbeat_outcomes()
                database.resolve_pending_alert_outcomes()
                last_daily_scan_date = today_str
                sleep_seconds = INTERVAL_OFFMARKET_MINUTES * 60

            # 4. Post-Market Scheduled PM Digest Window (4:30 PM ET or 1:30 PM ET on Early Close)
            elif m_status["is_pm_digest_window"]:
                logging.info("📊 Post-Market Window — Checking for 4:30 PM Digest Delivery...")
                digest_dispatcher.dispatch_scheduled_digests("PM_POSTMARKET", today_str)
                sleep_seconds = INTERVAL_OFFMARKET_MINUTES * 60

            else:
                # Off-Market Hours / Weekends / Holidays
                logging.info("🌙 Off-Market Hours / Weekend / Holiday — Maintaining heartbeat and waiting.")
                database.resolve_pending_heartbeat_outcomes()
                database.resolve_pending_alert_outcomes()
                sleep_seconds = INTERVAL_OFFMARKET_MINUTES * 60

        except KeyboardInterrupt:
            logging.info("🛑 Daemon interrupted by user/SIGINT. Exiting daemon loop gracefully.")
            database.set_scheduler_active(False)
            database.set_growth_scheduler_active(False)
            sys.exit(0)
        except Exception as e:
            logging.error(f"Unexpected error in daemon loop iteration: {e}", exc_info=True)
            sleep_seconds = 60 # Short sleep on error before retry
            
        update_heartbeat()
        time.sleep(sleep_seconds)

if __name__ == "__main__":
    start_daemon_loop()
