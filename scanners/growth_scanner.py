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

# Add parent path to import modular packages
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.local_env import load_env_file
load_env_file()

from core import database
from engines import growth_engine
from ai import analyst_engine
from notifications import notifier


def run_growth_scan(trigger_type="manual"):
    start_time = time.time()
    logging.info("=========================================")
    logging.info(f"Starting Whole-Market AI Growth & Hidden Gem Catalyst Scan (Trigger: {trigger_type})")
    logging.info("=========================================")
    
    database.init_db()
    subscribers = database.get_all_subscribers()
    if not subscribers:
        logging.info("No active subscribers found in the database. Exiting.")
        return

    # Filter subscribers who want growth alerts
    growth_subscribers = [s for s in subscribers if bool(s.get("wants_growth", 1))]
    if not growth_subscribers:
        logging.info("No subscribers have Growth Catalyst alerts enabled. Exiting.")
        return

    logging.info(f"Loaded {len(growth_subscribers)} growth-enabled subscribers. Assembling market-wide candidate list...")
    
    # 1. Fetch Whole-Market Candidates (Most Actives, Small-Cap Gainers, Aggressive Small Caps, Tech Growth + Broad Universe)
    market_tickers = growth_engine.get_market_growth_candidates(max_candidates=100)
    
    total_signals_found = 0
    total_alerts_sent = 0
    daily_rate_limited = False
    
    logging.info(f"Scanning Whole-Market Universe across {len(market_tickers)} active tickers...")
    
    # ─── PASS 1: Fast pre-filter (no AI calls) ───
    # Scan all tickers for volume surges + catalyst news keywords.
    # Only tickers with BOTH a volume surge AND keyword news will be sent to Groq AI.
    candidates = []
    skipped = 0
    for ticker in market_tickers:
        try:
            g_payload = growth_engine.scan_ticker_for_growth_catalyst(ticker)
            if g_payload.get("should_evaluate_ai"):
                candidates.append(g_payload)
            else:
                skipped += 1
        except Exception as e:
            logging.error(f"Error pre-scanning {ticker}: {e}")
    
    # Sort candidates by volume multiplier descending — strongest signals first
    candidates.sort(key=lambda x: x.get("vol_mult", 0), reverse=True)
    
    logging.info(f"Pre-filter complete: {len(candidates)} candidates have BOTH volume surge + catalyst news (skipped {skipped} tickers). Evaluating with Groq AI...")
    
    # ─── PASS 2: AI evaluation (rate-limit aware) ───
    high_growth_setups = []
    
    for idx, g_payload in enumerate(candidates):
        ticker = g_payload["ticker"]
        
        if daily_rate_limited:
            logging.warning(f"⏸️ Skipping AI evaluation for {ticker} — daily token limit reached.")
            continue
        
        try:
            g_res = analyst_engine.evaluate_growth_catalyst(g_payload)
        except Exception as e:
            error_str = str(e)
            if "429" in error_str and "tokens per day" in error_str.lower():
                daily_rate_limited = True
                logging.warning(f"🛑 Groq daily token limit reached at ticker {ticker}. Stopping AI calls for remaining {len(candidates) - idx - 1} candidates.")
                continue
            logging.error(f"Error evaluating growth catalyst for {ticker}: {e}")
            g_res = None
        
        if g_res and float(g_res.get("growth_score") or 0.0) >= 8.0:
            if database.is_growth_in_cooldown(ticker, cooldown_days=5):
                logging.info(f"⏸️ Ticker {ticker} is in 5-day growth cooldown. Skipping duplicate email dispatch.")
                continue

            total_signals_found += 1
            score = float(g_res.get("growth_score"))
            cat_type = g_res.get("catalyst_type", "Growth Catalyst")
            logging.info(f"🚀 Elite Market Growth Catalyst DISCOVERED (>= 8.0/10): {ticker} ({cat_type}) - Score: {score:.1f}/10")
            high_growth_setups.append(g_res)
        
        # Inter-request delay to avoid per-minute rate limits (12K TPM on free tier)
        if idx < len(candidates) - 1 and not daily_rate_limited:
            time.sleep(3)

    # ─── PASS 3: Single Digest Email Dispatch (Top 3 Candidates) ───
    if high_growth_setups:
        # Sort candidates by AI growth score descending — highest score rank first
        high_growth_setups.sort(key=lambda x: float(x.get("growth_score") or 0.0), reverse=True)
        top_3_setups = high_growth_setups[:3]
        top_tickers_label = ", ".join(x.get("ticker", "") for x in top_3_setups)
        
        logging.info(f"📦 Bundling Top {len(top_3_setups)} Growth Catalysts ({top_tickers_label}) into single email digest...")
        
        for sub in growth_subscribers:
            email = sub["email"]
            token = sub["management_token"]
            sub_id = sub["id"]
            sec_email = sub.get("secondary_email")
            
            digest_html = notifier.format_growth_digest_email(top_3_setups, token)
            subject_label = f"Market Growth Digest: Top {len(top_3_setups)} Breakouts ({top_tickers_label})"
            sent_real_email, status_msg = notifier.simulate_send_alert(email, digest_html, subject_label, secondary_email=sec_email)
            
            logging.info(f"Market Growth Digest delivery status for {email}: {status_msg}")
            
            if sent_real_email:
                for item in top_3_setups:
                    t_sym = item.get("ticker")
                    c_type = item.get("catalyst_type", "Growth")
                    l_price = item.get("latest_price")
                    g_score = item.get("growth_score", 8.0)
                    g_summary = item.get("headline_summary", "")
                    
                    # Record in sentinel.db growth_discoveries table
                    database.record_growth_discovery(t_sym, g_score, c_type, g_summary, l_price)
                    
                    g_signal = {
                        "ticker": t_sym,
                        "pattern_type": f"Growth_{c_type}",
                        "day1_date": str(datetime.now())[:10],
                        "day2_date": str(datetime.now())[:10],
                        "day3_open": l_price,
                        "entry_price": l_price,
                        "vol_mult": item.get("vol_mult")
                    }
                    database.record_sent_alert(sub_id, g_signal)
                    total_alerts_sent += 1

    duration = time.time() - start_time
    tickers_count = len(market_tickers)
    database.record_scan_log(duration, tickers_count, total_signals_found, total_alerts_sent, trigger_type=f"growth_{trigger_type}")
    
    if daily_rate_limited:
        logging.warning(f"⚠️ Scan finished with Groq daily token limit reached. {total_signals_found} signal(s) discovered before limit hit.")
    
    logging.info("=========================================")
    logging.info(f"Whole-Market Growth Scan completed in {duration:.2f}s. Evaluated {len(candidates)} AI candidates from {tickers_count} tickers. Discovered {total_signals_found} high-growth setup(s).")
    logging.info("=========================================")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Standalone AI Growth & Contract Catalyst Scanner.")
    args = parser.parse_args()
    run_growth_scan(trigger_type="manual_cli")
