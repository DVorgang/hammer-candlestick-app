import json
import logging
from core import database
from notifications import notifier

def dispatch_scheduled_digests(digest_type: str, trading_date_str: str) -> dict:
    """
    Executes isolated per-subscriber digest email delivery for digest_type ('AM_PREMARKET' or 'PM_POSTMARKET')
    and trading_date_str ('YYYY-MM-DD').
    
    Idempotent: Checks digest_deliveries in SQLite before attempting delivery.
    Failure-isolated: One subscriber's SMTP failure will not affect another subscriber.
    """
    subscribers = database.get_all_subscribers()
    if not subscribers:
        logging.info("No active subscribers found for digest delivery.")
        return {"subscribers_processed": 0, "successful_sends": 0, "failures": 0, "skipped_empty": 0}

    successful_sends = 0
    failures = 0
    skipped_empty = 0

    for sub in subscribers:
        sub_id = sub["id"]
        email = sub["email"]
        sec_email = sub.get("secondary_email")
        token = sub["management_token"]
        
        wants_growth = bool(sub.get("wants_growth", 1))
        wants_hb = bool(sub.get("wants_heartbeat", 1))
        wants_tech = bool(sub.get("wants_buys", 1) or sub.get("wants_risks", 1) or sub.get("wants_sells", 1))

        # Check if digest already delivered for this subscriber today
        if database.is_digest_delivered(trading_date_str, digest_type, sub_id):
            logging.info(f"⏭️ Digest {digest_type} for {email} on {trading_date_str} already delivered. Skipping.")
            continue

        discoveries = database.get_pending_discoveries_for_subscriber(sub_id, trading_date_str)
        growth_setups = discoveries.get("growth", []) if wants_growth else []
        heartbeat_setups = discoveries.get("heartbeat", []) if wants_hb else []
        tech_signals = discoveries.get("technical", []) if wants_tech else []

        total_count = len(growth_setups) + len(heartbeat_setups) + len(tech_signals)

        if total_count == 0:
            database.get_or_create_digest_delivery(
                trading_date_str, digest_type, sub_id, email, "[]", 0, status="SKIPPED_EMPTY"
            )
            logging.info(f"ℹ️ Zero pending discoveries for {email} ({trading_date_str} {digest_type}). Marked SKIPPED_EMPTY.")
            skipped_empty += 1
            continue

        discovery_items = []
        discovery_ids = []

        sub_success = 0
        sub_fails = 0

        # --- 1. DISPATCH DEDICATED AI GROWTH DIGEST EMAIL ---
        if wants_growth and growth_setups:
            for g in growth_setups:
                discovery_items.append({"source_type": "growth", "source_id": g["id"], "ticker": g["ticker"], "score": g.get("score")})
                discovery_ids.append(f"growth_{g['id']}")

            growth_html = notifier.format_growth_digest_email(growth_setups, token)
            g_sent, g_msg = notifier.simulate_send_alert(
                email, growth_html, f"TRadar Market Growth Digest ({trading_date_str})", secondary_email=sec_email
            )
            if g_sent:
                sub_success += 1
            else:
                sub_fails += 1
                logging.warning(f"⚠️ Growth digest send for {email}: {g_msg}")

        # --- 2. DISPATCH DEDICATED HEARTBEAT VOLATILITY DIGEST EMAIL ---
        if wants_hb and heartbeat_setups:
            for h in heartbeat_setups:
                discovery_items.append({"source_type": "heartbeat", "source_id": h["id"], "ticker": h["ticker"], "score": h.get("score")})
                discovery_ids.append(f"heartbeat_{h['id']}")

            hb_html = notifier.format_heartbeat_digest_email(heartbeat_setups, token)
            h_sent, h_msg = notifier.simulate_send_alert(
                email, hb_html, f"TRadar Heartbeat Volatility Digest ({trading_date_str})", secondary_email=sec_email
            )
            if h_sent:
                sub_success += 1
            else:
                sub_fails += 1
                logging.warning(f"⚠️ Heartbeat digest send for {email}: {h_msg}")

        # --- 3. DISPATCH DEDICATED WATCHLIST TECHNICAL DIGEST EMAIL ---
        if wants_tech and tech_signals:
            for t in tech_signals:
                discovery_items.append({"source_type": "technical", "source_id": t["id"], "ticker": t["ticker"], "score": 0.0})
                discovery_ids.append(f"technical_{t['id']}")

            tech_html = notifier.format_technical_digest_email(tech_signals, token)
            t_sent, t_msg = notifier.simulate_send_alert(
                email, tech_html, f"TRadar Watchlist Technical Digest ({trading_date_str})", secondary_email=sec_email
            )
            if t_sent:
                sub_success += 1
            else:
                sub_fails += 1
                logging.warning(f"⚠️ Technical digest send for {email}: {t_msg}")

        # Record delivery tracking in SQLite
        rec = database.get_or_create_digest_delivery(
            trading_date_str, digest_type, sub_id, email, json.dumps(discovery_ids), total_count, status="PENDING"
        )
        if rec:
            delivery_id = rec["id"]
            if sub_fails == 0:
                database.mark_digest_success(delivery_id, discovery_items)
                logging.info(f"✅ Dedicated channel digests delivered to {email} ({total_count} total setups).")
                successful_sends += 1
            else:
                database.record_digest_attempt(delivery_id, "FAILED", error_message="One or more dedicated digests failed delivery.")
                failures += 1
        else:
            failures += 1

    return {
        "subscribers_processed": len(subscribers),
        "successful_sends": successful_sends,
        "failures": failures,
        "skipped_empty": skipped_empty
    }
