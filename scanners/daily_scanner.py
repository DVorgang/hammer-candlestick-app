import sys
import os
import argparse
import logging
from datetime import datetime

# Set up UTF-8 console output for Windows terminal safety
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Set up logging to both console and a log file for task scheduler tracking
log_format = "%(asctime)s - %(levelname)s - %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("daily_scanner.log", encoding="utf-8")
    ]
)

# Add parent path to import modular packages
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.local_env import load_env_file
load_env_file()

from core import database
from engines import pattern_engine, growth_engine
from ai import analyst_engine
from notifications import notifier

import time


def run_daily_scan(days_to_scan=3, trigger_type="manual"):
    start_time = time.time()
    logging.info("=========================================")
    logging.info(f"Starting Daily Candlestick & Growth Sentinel Scan (Trigger: {trigger_type})")
    logging.info("=========================================")
    
    # 1. Initialize database & resolve post-trade alert outcomes
    database.init_db()
    try:
        database.resolve_pending_alert_outcomes()
    except Exception as e:
        logging.error(f"Error resolving alert outcomes: {e}")

    
    # 2. Retrieve all subscribers
    subscribers = database.get_all_subscribers()
    if not subscribers:
        logging.info("No active subscribers found in the database. Exiting.")
        duration = time.time() - start_time
        database.record_scan_log(duration, 0, 0, 0, trigger_type=trigger_type)
        return

    logging.info(f"Loaded {len(subscribers)} subscribers from SQLite.")
    
    # Track metrics
    ticker_cache = {}
    growth_cache = {}
    total_signals_found = 0
    total_alerts_sent = 0
    
    for sub in subscribers:
        email = sub["email"]
        token = sub["management_token"]
        sub_id = sub["id"]
        
        # Load user alerts preferences
        wants_buys = bool(sub["wants_buys"])
        wants_risks = bool(sub["wants_risks"])
        wants_sells = bool(sub["wants_sells"])
        wants_growth = bool(sub.get("wants_growth", 1))
        
        watchlist = database.get_watchlist(sub_id)
        if not watchlist:
            logging.info(f"Subscriber {email} (ID: {sub_id}) has an empty watchlist. Skipping.")
            continue
            
        logging.info(f"Processing subscriber {email} (Watchlist: {watchlist})...")
        
        subscriber_tech_signals = []
        for ticker in watchlist:
            # --- 1. Candlestick Pattern Scan ---
            if ticker not in ticker_cache:
                try:
                    signals = pattern_engine.scan_ticker_for_signals(ticker, days_to_scan=days_to_scan)
                    ticker_cache[ticker] = signals
                except Exception as e:
                    logging.error(f"Error scanning ticker {ticker}: {e}")
                    ticker_cache[ticker] = []
                    
            signals = ticker_cache[ticker]
            
            for signal in signals:
                if not signal["confirmed"]:
                    continue
                    
                total_signals_found += 1
                pattern_type = signal["pattern_type"]
                score = signal["confidence_score"]
                
                send_alert = False
                alert_type = ""
                
                if pattern_type == "Hammer":
                    if wants_buys:
                        send_alert = True
                        alert_type = "Buy Opportunity"
                elif pattern_type == "Hanging Man":
                    if score >= 70:
                        if wants_sells:
                            send_alert = True
                            alert_type = "Sell Alert"
                    else:
                        if wants_risks:
                            send_alert = True
                            alert_type = "Risk Warning"
                            
                if send_alert:
                    logging.info(f"🔥 Pattern MATCHED for {email}: {ticker} {pattern_type} (Score: {score:.1f}) -> Preparing {alert_type} email.")
                    
                    if database.has_alert_been_sent(sub_id, signal):
                        logging.info(f"Skipping duplicate alert for {email}: {ticker} {pattern_type}.")
                        continue

                    entry_est = signal.get("day3_open") or signal.get("day2_close")
                    day1_low = signal["day1_low"]
                    day1_high = signal["day1_high"]
                    
                    if pattern_type == "Hammer":
                        stop_loss = round(day1_low - 0.01, 2)
                        profit_target = round(entry_est + 2.0 * (entry_est - stop_loss), 2)
                    else:
                        stop_loss = round(day1_high + 0.01, 2)
                        profit_target = round(entry_est - 2.0 * (stop_loss - entry_est), 2)
                        
                    signal["entry_price"] = entry_est
                    signal["stop_loss"] = stop_loss
                    signal["profit_target"] = profit_target
                    
                    invalidation_gap = False
                    if pattern_type == "Hammer" and entry_est <= day1_low:
                        invalidation_gap = True
                    elif pattern_type == "Hanging Man" and entry_est >= day1_high:
                        invalidation_gap = True
                        
                    if invalidation_gap:
                        logging.warning(f"❌ Alert aborted: Ticker {ticker} opened past invalidation level.")
                        continue

                    ai_analysis = analyst_engine.analyze_signal(signal)
                    if ai_analysis:
                        signal["ai_analysis"] = ai_analysis

                    # Check if ticker is a Growth Discovery for Synergy formatting
                    disc_info = database.get_growth_discovery_by_ticker(ticker)
                    if disc_info:
                        signal["is_synergy"] = True
                        signal["discovery_info"] = disc_info

                    subscriber_tech_signals.append(signal)

        sec_email = sub.get("secondary_email")

        # Buffer Technical Notifications for scheduled PM Digest Delivery
        if subscriber_tech_signals:
            logging.info(f"💾 Buffering {len(subscriber_tech_signals)} Technical Signals for {email} to database for scheduled digest delivery...")
            for sig in subscriber_tech_signals:
                database.record_sent_alert(sub_id, sig)
                total_alerts_sent += 1
                    
    duration = time.time() - start_time
    tickers_count = len(ticker_cache)
    database.record_scan_log(duration, tickers_count, total_signals_found, total_alerts_sent, trigger_type=trigger_type)

    logging.info("=========================================")
    logging.info(f"Scan completed successfully in {duration:.2f}s across {tickers_count} tickers.")
    logging.info("=========================================\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Candlestick Sentinel Headless Daily Scanner")
    parser.add_argument(
        "--days", 
        type=int, 
        default=3, 
        help="Number of historical days to scan (default: 3 to check recent confirmed setups)"
    )
    args = parser.parse_args()
    
    run_daily_scan(days_to_scan=args.days)
