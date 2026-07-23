import sys
import os
import argparse
import logging
from datetime import datetime
import time

# Set up UTF-8 console output for Windows terminal safety
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Set up logging to both console and log file
log_format = "%(asctime)s - %(levelname)s - %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("growth_scanner.log", encoding="utf-8")
    ]
)

# Add local path to import modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from local_env import load_env_file

load_env_file()

import database
import growth_engine
import analyst_engine
import notifier

def run_growth_scan(trigger_type="manual"):
    start_time = time.time()
    logging.info("=========================================")
    logging.info(f"Starting Standalone AI Growth & Contract Catalyst Scan (Trigger: {trigger_type})")
    logging.info("=========================================")
    
    database.init_db()
    subscribers = database.get_all_subscribers()
    if not subscribers:
        logging.info("No active subscribers found in the database. Exiting.")
        return

    logging.info(f"Loaded {len(subscribers)} subscribers for Growth Catalyst scan.")
    
    growth_cache = {}
    total_signals_found = 0
    total_alerts_sent = 0
    
    for sub in subscribers:
        email = sub["email"]
        token = sub["management_token"]
        sub_id = sub["id"]
        
        wants_growth = bool(sub.get("wants_growth", 1))
        if not wants_growth:
            logging.info(f"Subscriber {email} has opted out of Growth Catalyst alerts. Skipping.")
            continue

        watchlist = database.get_watchlist(sub_id)
        if not watchlist:
            logging.info(f"Subscriber {email} has an empty watchlist. Skipping.")
            continue
            
        logging.info(f"Scanning Growth Catalysts for {email} (Watchlist: {watchlist})...")
        
        for ticker in watchlist:
            if ticker not in growth_cache:
                try:
                    g_payload = growth_engine.scan_ticker_for_growth_catalyst(ticker)
                    if g_payload.get("should_evaluate_ai"):
                        g_res = analyst_engine.evaluate_growth_catalyst(g_payload)
                    else:
                        g_res = None
                    growth_cache[ticker] = g_res
                except Exception as e:
                    logging.error(f"Error evaluating growth catalyst for {ticker}: {e}")
                    growth_cache[ticker] = None

            growth_eval = growth_cache[ticker]
            if growth_eval and float(growth_eval.get("growth_score") or 0.0) >= 7.0:
                total_signals_found += 1
                score = float(growth_eval.get("growth_score"))
                cat_type = growth_eval.get("catalyst_type", "Growth Catalyst")
                logging.info(f"🚀 Growth Catalyst MATCHED for {email}: {ticker} {cat_type} (Score: {score:.1f}/10)")
                
                g_signal = {
                    "ticker": ticker,
                    "pattern_type": f"Growth_{cat_type}",
                    "day1_date": str(datetime.now())[:10],
                    "day2_date": str(datetime.now())[:10]
                }
                
                if not database.has_alert_been_sent(sub_id, g_signal):
                    g_html = notifier.format_growth_catalyst_email(growth_eval, token)
                    sent_real_email, status_msg = notifier.simulate_send_alert(email, g_html, f"{ticker} Growth Catalyst")
                    logging.info(f"Growth email delivery status for {email} / {ticker}: {status_msg}")
                    if sent_real_email:
                        database.record_sent_alert(sub_id, g_signal)
                        total_alerts_sent += 1
                else:
                    logging.info(f"Skipping duplicate growth alert for {email}: {ticker} {cat_type}.")

    duration = time.time() - start_time
    tickers_count = len(growth_cache)
    database.record_scan_log(duration, tickers_count, total_signals_found, total_alerts_sent, trigger_type=f"growth_{trigger_type}")
    
    logging.info("=========================================")
    logging.info(f"Growth Scan completed successfully in {duration:.2f}s across {tickers_count} tickers.")
    logging.info("=========================================")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Standalone AI Growth & Contract Catalyst Scanner.")
    args = parser.parse_args()
    run_growth_scan(trigger_type="manual_cli")
