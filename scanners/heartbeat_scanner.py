import sys
import os
import time
import logging
import argparse
from datetime import datetime

# Set up UTF-8 console output for Windows terminal safety
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add parent path to import modular packages
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.local_env import load_env_file
load_env_file()

from core import database
from engines import heartbeat_engine
from ai import analyst_engine
from notifications import notifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def run_heartbeat_scan(trigger_type="manual"):
    """
    Executes whole-market + watchlist Heartbeat Volatility Expansion scan:
    - Pass 1: Quantitative math pre-filter (Resting Squeeze + QRS Volume Pulse)
    - Pass 2: Groq AI catalyst evaluation & 100-Point Conviction Scoring
    - Pass 3: Smart Conditional Cooldown & Single Top-3 Digest Email dispatch
    """
    start_time = time.time()
    logging.info("=========================================")
    logging.info(f"Starting TRadar Heartbeat Volatility Expansion Scan (Trigger: {trigger_type})")
    logging.info("=========================================")
    
    database.init_db()
    subscribers = database.get_all_subscribers()
    if not subscribers:
        logging.info("No active subscribers found in database. Exiting.")
        return

    # Filter subscribers who want heartbeat alerts (defaults to enabled or wants_growth/wants_heartbeat)
    heartbeat_subscribers = [s for s in subscribers if bool(s.get("wants_heartbeat", 1))]
    if not heartbeat_subscribers:
        logging.info("No subscribers have Heartbeat Volatility alerts enabled. Exiting.")
        return

    logging.info(f"Loaded {len(heartbeat_subscribers)} heartbeat-enabled subscribers. Assembling candidate universe...")
    
    # 1. Fetch Candidate Universe (Watchlists + Penny Microcap Pool + Screeners)
    candidate_tickers = heartbeat_engine.get_heartbeat_candidates(max_candidates=150)
    
    total_signals_found = 0
    total_alerts_sent = 0
    daily_rate_limited = False
    
    logging.info(f"Pre-screening {len(candidate_tickers)} candidates for Resting Squeeze & QRS Volume Pulse...")
    
    # ─── PASS 1: Fast Quantitative Math Pre-Filter (No AI calls) ───
    math_candidates = []
    skipped = 0
    for ticker in candidate_tickers:
        try:
            h_payload = heartbeat_engine.scan_ticker_for_heartbeat(ticker)
            if h_payload.get("should_evaluate_ai"):
                math_candidates.append(h_payload)
            else:
                skipped += 1
        except Exception as e:
            logging.error(f"Error pre-scanning heartbeat for {ticker}: {e}")
            
    # Sort candidates by pre-AI math score descending
    math_candidates.sort(key=lambda x: x.get("math_score", 0), reverse=True)
    logging.info(f"Pass 1 Math Pre-Filter Complete: {len(math_candidates)} candidates passed resting squeeze + volume pulse (skipped {skipped}). Evaluating with Groq AI...")

    # ─── PASS 2: Groq AI Catalyst Evaluation & 100-Point Conviction Scoring ───
    qualified_heartbeats = []
    
    for idx, h_payload in enumerate(math_candidates):
        ticker = h_payload["ticker"]
        
        if daily_rate_limited:
            logging.warning(f"⏸️ Skipping AI evaluation for {ticker} — daily token limit reached.")
            continue
            
        try:
            h_res = analyst_engine.evaluate_heartbeat_catalyst(h_payload)
        except Exception as e:
            error_str = str(e)
            if "429" in error_str and "tokens per day" in error_str.lower():
                daily_rate_limited = True
                logging.warning(f"🛑 Groq daily token limit reached at {ticker}. Stopping AI calls for remaining candidates.")
                continue
            logging.error(f"Error evaluating heartbeat catalyst for {ticker}: {e}")
            h_res = None
            
        if h_res:
            conviction = float(h_res.get("conviction_score") or 0.0)
            # High Bar Quality Cutoff: Conviction Score >= 80.0 / 100.0
            if conviction >= 80.0:
                # Smart Conditional Cooldown Check
                cooldown_info = database.check_heartbeat_cooldown_status(ticker, conviction_score=conviction)
                if cooldown_info.get("is_suppressed"):
                    logging.info(f"⏸️ Ticker {ticker} is in active duplicate cooldown (no new score/news change). Skipping digest inclusion.")
                    continue
                    
                # Apply Momentum / Synergy Badge
                if cooldown_info.get("is_retrigger"):
                    h_res["badge_tag"] = "🔥 MULTI-DAY MOMENTUM CONTINUATION"
                    h_res["badge_color"] = "#ff4757"
                elif h_res.get("above_200sma"):
                    h_res["badge_tag"] = "⚡ DOUBLE-SYNERGY BREAKOUT"
                    h_res["badge_color"] = "#eccc68"
                else:
                    h_res["badge_tag"] = "💓 SLEEPING GIANT HEARTBEAT PULSE"
                    h_res["badge_color"] = "#ff007f"
                    
                total_signals_found += 1
                cat_type = h_res.get("catalyst_type", "Heartbeat Surge")
                logging.info(f"💓 Elite Heartbeat Breakout DISCOVERED (>= 80.0/100): {ticker} ({cat_type}) - Conviction: {conviction:.1f}/100")
                qualified_heartbeats.append(h_res)

        # Inter-request delay to avoid per-minute rate limits
        if idx < len(math_candidates) - 1 and not daily_rate_limited:
            time.sleep(3)

    # ─── PASS 3: Buffer Heartbeat Discoveries to Database (Pending Digest Delivery) ───
    if qualified_heartbeats:
        today_str = datetime.now().strftime("%Y-%m-%d")
        logging.info(f"💾 Buffering {len(qualified_heartbeats)} Heartbeat Discovery setups to database for scheduled digest delivery...")
        
        for item in qualified_heartbeats:
            t_sym = item.get("ticker")
            c_type = item.get("catalyst_type", "Heartbeat Surge")
            l_price = item.get("latest_price")
            c_score = item.get("conviction_score", 80.0)
            g_summary = item.get("headline_summary", "")
            
            # Record in sentinel.db heartbeat_discoveries table with digest_status = 'PENDING'
            database.record_heartbeat_discovery(t_sym, c_score, c_type, g_summary, l_price)
            total_alerts_sent += 1

    duration = time.time() - start_time
    tickers_count = len(candidate_tickers)
    database.record_scan_log(duration, tickers_count, total_signals_found, total_alerts_sent, trigger_type=f"heartbeat_{trigger_type}")
    
    if daily_rate_limited:
        logging.warning(f"⚠️ Heartbeat scan finished with Groq daily token limit reached. {total_signals_found} signal(s) discovered before limit hit.")
    
    logging.info("=========================================")
    logging.info(f"Heartbeat Volatility Scan completed in {duration:.2f}s. Evaluated {len(math_candidates)} candidates. Discovered {total_signals_found} high-conviction setup(s).")
    logging.info("=========================================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Standalone TRadar Heartbeat Volatility Expansion Scanner.")
    args = parser.parse_args()
    run_heartbeat_scan(trigger_type="manual_cli")
