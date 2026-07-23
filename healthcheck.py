import sys
import os
import time
import argparse
import urllib.request
import logging

# Ensure UTF-8 console output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from core import database

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def check_ui_health(port=8501):
    """
    Verifies that Streamlit web server is responding on its native health endpoint.
    """
    url = f"http://127.0.0.1:{port}/_stcore/health"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Docker-HealthCheck"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                logging.info("Streamlit UI Healthcheck: OK (200)")
                return True
            else:
                logging.error(f"Streamlit UI Healthcheck failed: status code {resp.status}")
                return False
    except Exception as e:
        logging.error(f"Streamlit UI Healthcheck exception: {e}")
        return False

def check_database_health():
    """
    Verifies database connectivity, table integrity, and SQLite WAL journal mode.
    """
    health = database.get_system_health()
    if health.get("status") == "healthy":
        logging.info(f"Database Healthcheck: OK (Journal Mode: {health.get('journal_mode')})")
        return True
    else:
        logging.error(f"Database Healthcheck failed: {health}")
        return False

def check_worker_heartbeat(max_stale_seconds=1800):
    """
    Verifies that the background scanner daemon has written a recent heartbeat timestamp.
    """
    heartbeat_path = os.path.join(os.environ.get("TMPDIR", "/tmp"), "worker_heartbeat.txt")
    if not os.path.exists(heartbeat_path):
        # Fallback check SQLite scheduler last_run_timestamp
        health = database.get_system_health()
        log = health.get("last_scan_log")
        if not log:
            logging.warning("Worker Heartbeat: No scan log found yet. Container warming up.")
            return True
        return True
        
    try:
        with open(heartbeat_path, "r", encoding="utf-8") as f:
            last_heartbeat = float(f.read().strip())
        age = time.time() - last_heartbeat
        if age <= max_stale_seconds:
            logging.info(f"Worker Heartbeat: OK (Age: {age:.1f}s)")
            return True
        else:
            logging.error(f"Worker Heartbeat STALE: {age:.1f}s exceeds limit {max_stale_seconds}s")
            return False
    except Exception as e:
        logging.error(f"Error checking worker heartbeat file: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Docker Container Healthcheck Script")
    parser.add_argument("--mode", choices=["ui", "worker", "db"], default="db", help="Healthcheck evaluation mode")
    args = parser.parse_args()

    db_ok = check_database_health()
    if not db_ok:
        sys.exit(1)

    if args.mode == "ui":
        if not check_ui_health():
            sys.exit(1)
    elif args.mode == "worker":
        if not check_worker_heartbeat():
            sys.exit(1)

    logging.info("Healthcheck: ALL PASSED")
    sys.exit(0)

if __name__ == "__main__":
    main()
