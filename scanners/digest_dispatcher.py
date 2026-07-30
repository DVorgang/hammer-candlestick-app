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

        # Check if digest already delivered for this subscriber today
        if database.is_digest_delivered(trading_date_str, digest_type, sub_id):
            logging.info(f"⏭️ Digest {digest_type} for {email} on {trading_date_str} already delivered. Skipping.")
            continue

        discoveries = database.get_pending_discoveries_for_subscriber(sub_id, trading_date_str)
        growth_setups = discoveries.get("growth", [])
        heartbeat_setups = discoveries.get("heartbeat", [])
        tech_signals = discoveries.get("technical", [])

        total_count = len(growth_setups) + len(heartbeat_setups) + len(tech_signals)

        if total_count == 0:
            database.get_or_create_digest_delivery(
                trading_date_str, digest_type, sub_id, email, "[]", 0, status="SKIPPED_EMPTY"
            )
            logging.info(f"ℹ️ Zero pending discoveries for {email} ({trading_date_str} {digest_type}). Marked SKIPPED_EMPTY.")
            skipped_empty += 1
            continue

        # Build discovery items payload
        discovery_items = []
        discovery_ids = []

        for g in growth_setups:
            discovery_items.append({"source_type": "growth", "source_id": g["id"], "ticker": g["ticker"], "score": g.get("score")})
            discovery_ids.append(f"growth_{g['id']}")

        for h in heartbeat_setups:
            discovery_items.append({"source_type": "heartbeat", "source_id": h["id"], "ticker": h["ticker"], "score": h.get("score")})
            discovery_ids.append(f"heartbeat_{h['id']}")

        for t in tech_signals:
            discovery_items.append({"source_type": "technical", "source_id": t["id"], "ticker": t["ticker"], "score": 0.0})
            discovery_ids.append(f"technical_{t['id']}")

        rec = database.get_or_create_digest_delivery(
            trading_date_str, digest_type, sub_id, email, json.dumps(discovery_ids), total_count, status="PENDING"
        )
        if not rec:
            logging.error(f"Failed to create/get digest delivery record for {email}.")
            failures += 1
            continue

        delivery_id = rec["id"]

        # Build HTML content
        digest_html = notifier.format_unified_pm_digest_email(
            growth_setups, heartbeat_setups, tech_signals, token
        )
        subject_label = f"Market Digest ({trading_date_str}): {total_count} Breakouts"

        # Attempt SMTP delivery
        sent_real, status_msg = notifier.simulate_send_alert(
            email, digest_html, subject_label, secondary_email=sec_email
        )

        if sent_real:
            database.mark_digest_success(delivery_id, discovery_items)
            logging.info(f"✅ Digest {digest_type} successfully delivered to {email} ({total_count} setups).")
            successful_sends += 1
        else:
            database.record_digest_attempt(delivery_id, "FAILED", error_message=status_msg)
            logging.warning(f"⚠️ Digest delivery attempt for {email} failed: {status_msg}")
            failures += 1

    return {
        "subscribers_processed": len(subscribers),
        "successful_sends": successful_sends,
        "failures": failures,
        "skipped_empty": skipped_empty
    }
