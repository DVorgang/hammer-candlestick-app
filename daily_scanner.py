import sys
import os
import argparse
import logging

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

# Add local path to import modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from local_env import load_env_file

load_env_file()

import database
import pattern_engine
import notifier
import analyst_engine

import time

def run_daily_scan(days_to_scan=3, trigger_type="manual"):
    start_time = time.time()
    logging.info("=========================================")
    logging.info(f"Starting Daily Candlestick Sentinel Scan (Trigger: {trigger_type})")
    logging.info("=========================================")
    
    # 1. Initialize database
    database.init_db()
    
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
        
        watchlist = database.get_watchlist(sub_id)
        if not watchlist:
            logging.info(f"Subscriber {email} (ID: {sub_id}) has an empty watchlist. Skipping.")
            continue
            
        logging.info(f"Processing subscriber {email} (Watchlist: {watchlist})...")
        
        for ticker in watchlist:
            # Check cache to avoid hitting Yahoo Finance API repeatedly for the same ticker
            if ticker not in ticker_cache:
                try:
                    signals = pattern_engine.scan_ticker_for_signals(ticker, days_to_scan=days_to_scan)
                    ticker_cache[ticker] = signals
                except Exception as e:
                    logging.error(f"Error scanning ticker {ticker}: {e}")
                    ticker_cache[ticker] = []
                    
            signals = ticker_cache[ticker]
            
            # Filter and process signals
            for signal in signals:
                if not signal["confirmed"]:
                    continue # Discard unconfirmed patterns
                    
                total_signals_found += 1
                pattern_type = signal["pattern_type"]
                score = signal["confidence_score"]
                
                # Check preferences
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
                    logging.info(f"🔥 Signal MATCHED for {email}: {ticker} {pattern_type} (Score: {score:.1f}) -> Preparing {alert_type} email.")
                    
                    if database.has_alert_been_sent(sub_id, signal):
                        logging.info(f"Skipping duplicate alert for {email}: {ticker} {pattern_type} from {str(signal['day1_date'])[:10]} confirmed {str(signal['day2_date'])[:10]}.")
                        continue

                    # Estimate Day 3 opening price as latest close/estimation
                    entry_est = signal.get("day3_open") or signal.get("day2_close")
                    day1_low = signal["day1_low"]
                    day1_high = signal["day1_high"]
                    
                    # Final safety check: gap risk validation
                    invalidation_gap = False
                    if pattern_type == "Hammer" and entry_est <= day1_low:
                        invalidation_gap = True
                    elif pattern_type == "Hanging Man" and entry_est >= day1_high:
                        invalidation_gap = True
                        
                    if invalidation_gap:
                        logging.warning(f"❌ Alert aborted: Ticker {ticker} opened past invalidation level (Gap risk).")
                        continue
                        
                    ai_analysis = analyst_engine.analyze_signal(signal)
                    if ai_analysis:
                        signal["ai_analysis"] = ai_analysis
                        logging.info(f"AI analyst notes added for {ticker}: {ai_analysis.get('status')}")
                    else:
                        logging.info(f"AI analyst notes skipped for {ticker}.")

                    # Format HTML email
                    html_body = notifier.format_alert_email(signal, token)
                    
                    # Deliver
                    sent_real_email, status_msg = notifier.simulate_send_alert(email, html_body, ticker)
                    logging.info(f"Delivery status for {email} / {ticker}: {status_msg}")
                    if sent_real_email:
                        database.record_sent_alert(sub_id, signal)
                        total_alerts_sent += 1
                else:
                    logging.debug(f"Signal detected for {ticker} but subscriber {email} has opted out of {pattern_type} alert preferences.")
                    
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
