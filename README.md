# TRadar - AI Market Intelligence & Growth Catalyst Engine

TRadar is a local-first market intelligence dashboard and automated email alert system built with Python, Streamlit, Plotly, yfinance, AI model integrations, SMTP email delivery, and SQLite.

The app combines two complementary scanners:

- A watchlist-based candlestick technical reversal scanner for Hammer and Hanging Man setups.
- A whole-market growth catalyst scanner for unusual volume, fresh news catalysts, and AI-ranked breakout candidates.

It also includes a Streamlit control panel, live quote/deep-dive pages, post-alert outcome tracking, digest-style email alerts, secondary email delivery, and Docker/daemon support for 24/7 operation.

> Educational and informational use only. TRadar does not provide financial, investment, or trading advice.

---

## Core Features

### Candlestick Technical Reversal Engine

- Detects Hammer and Hanging Man setups using candle geometry, RSI(14), moving averages, and volume context.
- Enforces a 3-day validation lifecycle to avoid lookahead bias:
  - Day 1: setup candle forms.
  - Day 2: confirmation close is required.
  - Day 3: entry/stop/target blueprint is generated.
- Calculates 2:1 reward-to-risk trade blueprints.
- Rejects setups when gap risk invalidates the trade plan.
- Adds AI technical summaries when API keys are configured.
- Tracks resolved alert outcomes and feeds historical win-rate context back into scoring and AI prompts.

### Whole-Market Growth Catalyst Engine

- Builds a market-wide candidate set using Yahoo Finance screeners and a curated broad growth universe.
- Measures unusual volume against 20-day average volume.
- Pulls recent Google News RSS headlines.
- Pre-filters for catalyst keywords such as contracts, partnerships, FDA approvals, earnings, launches, acquisitions, revenue, grants, and awards.
- Sends qualifying candidates to the AI analyst.
- Sends a single Top-3 Market Growth Digest for elite candidates.
- Records growth discoveries and applies cooldown logic to reduce duplicate growth alerts.

### Email Alerts

TRadar can send:

- Single technical reversal alerts.
- Watchlist Technical Digest emails when multiple technical setups are found.
- Top-3 Market Growth Digest emails.
- Synergy alerts when a technical reversal appears on a recent growth-discovery ticker.
- Test emails from the Streamlit UI.

SMTP delivery uses `.env` settings. If SMTP credentials are missing, emails are simulated/logged instead of delivered.

Subscribers can also configure a secondary email recipient. Alert emails are delivered to both the primary subscriber email and optional secondary email.

### Dashboard

The Streamlit app includes:

- OTP/token-based local account access.
- Watchlist and alert preference management.
- Secondary email recipient management.
- Stock search and deep-dive analysis.
- Live quotes and charts.
- Scanner control panel.
- Email layout inspector and test buttons.
- Recent scanner run logs with category filtering.
- Post-trade outcome matrix for technical candlestick setups.

---

## Repository Structure

```text
hammer-candlestick-app/
  ai/
    analyst_engine.py          # AI analyst fallback chain and JSON parsing
  assets/
    tradar_logo.png
    traderadar_banner.png
    traderadar_logo.png
  core/
    database.py                # SQLite schema, subscribers, schedulers, logs, outcomes
    local_env.py               # Simple .env loader
  engines/
    backtest.py                # Historical 2-year strategy backtester
    growth_engine.py           # Market screeners, volume metrics, Google News RSS
    pattern_engine.py          # Candlestick detection, RSI, SMAs, score calibration
  notifications/
    notifier.py                # HTML email templates and SMTP delivery
  scanners/
    daily_scanner.py           # Watchlist technical scanner
    growth_scanner.py          # Whole-market growth catalyst scanner
    scheduler_daemon.py        # 24/7 Docker worker loop
  tests/
    test_docker_health_and_wal.py
    test_full_system.py
    test_gemini.py
    test_learning_loop.py
    test_outcome_matrix_deepdive.py
  app.py                       # Streamlit UI entrypoint
  docker-compose.yml           # Streamlit UI + scanner worker services
  Dockerfile                   # Container image
  healthcheck.py               # Docker healthchecks
  PROXMOX_DEPLOYMENT_GUIDE.md  # Server deployment notes
  requirements.txt
  README.md
```

---

## Environment Configuration

Create a `.env` file in the repo root. Start from `.env.example`.

```ini
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your.email@gmail.com
SMTP_PASSWORD=your_gmail_app_password

AI_PROVIDER=groq
GROQ_API_KEY=replace_with_your_groq_api_key
OPENAI_API_KEY=replace_with_your_openai_api_key
AI_ANALYST_ENABLED=true
AI_ANALYST_MODEL=llama-3.3-70b-versatile
AI_ANALYST_WEB_SEARCH=false

# Optional fallback provider
GEMINI_API_KEY=replace_with_your_gemini_api_key_optional
```

Notes:

- SMTP credentials are required for real email delivery.
- `GROQ_API_KEY`, `GEMINI_API_KEY`, or `OPENAI_API_KEY` are required for AI analysis.
- Without AI keys, deterministic scanning still works, but AI summaries/growth scoring may be unavailable or fall back where the UI provides mock test content.

---

## Local Setup

Install dependencies:

```powershell
cd D:\repo_stocks\hammer-candlestick-app
& 'C:\Users\Devin\AppData\Local\Programs\Python\Python312\python.exe' -m pip install -r requirements.txt
```

Run the Streamlit dashboard:

```powershell
cd D:\repo_stocks\hammer-candlestick-app
& 'C:\Users\Devin\AppData\Local\Programs\Python\Python312\python.exe' -m streamlit run app.py --server.address 0.0.0.0
```

Local browser URL:

```text
http://localhost:8501
```

LAN URL from another computer:

```text
http://<this-computer-lan-ip>:8501
```

---

## Manual Scanner Commands

Run the watchlist technical scanner:

```powershell
cd D:\repo_stocks\hammer-candlestick-app
& 'C:\Users\Devin\AppData\Local\Programs\Python\Python312\python.exe' scanners\daily_scanner.py --days 3
```

Run the whole-market growth catalyst scanner:

```powershell
cd D:\repo_stocks\hammer-candlestick-app
& 'C:\Users\Devin\AppData\Local\Programs\Python\Python312\python.exe' scanners\growth_scanner.py
```

Run tests:

```powershell
cd D:\repo_stocks\hammer-candlestick-app
& 'C:\Users\Devin\AppData\Local\Programs\Python\Python312\python.exe' -m pytest
```

---

## Scanner Behavior

### Technical Scanner

Entrypoint:

```text
scanners/daily_scanner.py
```

The technical scanner:

- Loads all subscribers from SQLite.
- Scans each subscriber watchlist.
- Detects confirmed Hammer/Hanging Man setups.
- Builds entry, stop loss, and profit target fields.
- Adds optional AI technical analysis.
- Checks for synergy with recent growth discoveries.
- Sends either a single alert or a Watchlist Technical Digest.
- Sends to secondary email when configured.
- Records sent alerts to avoid duplicates.
- Records scanner runtime metrics.

### Growth Scanner

Entrypoint:

```text
scanners/growth_scanner.py
```

The growth scanner:

- Builds up to 100 market-wide candidates.
- Pre-filters candidates using volume surge and news keywords.
- Evaluates candidates with the AI analyst.
- Requires an elite growth score threshold of `>= 8.0`.
- Applies a 5-day growth-discovery cooldown.
- Sends one Top-3 Market Growth Digest email.
- Records discoveries in `growth_discoveries`.
- Records sent alerts and scanner logs.

---

## Docker

Docker support is included, but Docker Desktop on Windows requires virtualization support enabled in BIOS/UEFI.

Compose services:

```text
streamlit-ui     # Streamlit dashboard on port 8501
scanner-worker   # 24/7 daemon that runs growth scans and post-close technical scans
```

Start the stack:

```powershell
cd D:\repo_stocks\hammer-candlestick-app
docker compose up -d --build
```

View logs:

```powershell
docker compose logs -f
```

Stop the stack:

```powershell
docker compose down
```

Healthchecks:

- UI healthcheck uses `python healthcheck.py --mode ui`.
- Worker healthcheck uses `python healthcheck.py --mode worker`.

The Docker worker runs:

```text
python -m scanners.scheduler_daemon
```

The worker loop:

- Runs growth scans during market hours.
- Runs a full daily candlestick scan once during the post-close window.
- Resolves pending alert outcomes periodically.
- Updates a heartbeat file used by the worker healthcheck.

Docker data mounts:

```text
./sentinel.db -> /app/sentinel.db
./.env        -> /app/.env
```

---

## Database

TRadar uses SQLite via `sentinel.db`. The database layer enables WAL mode for improved concurrent read/write behavior:

```sql
PRAGMA journal_mode = WAL;
```

Primary tables include:

- `subscribers`
- `watchlists`
- `sent_alerts`
- `scanner_logs`
- `scheduler_state`
- `growth_discoveries`

Important subscriber fields:

- `email`
- `secondary_email`
- `management_token`
- `wants_buys`
- `wants_risks`
- `wants_sells`
- `wants_growth`
- `otp_code`
- `otp_expiry`

The app also stores alert outcome/resolution fields on `sent_alerts` for post-trade tracking.

---

## Scheduler Options

There are two practical ways to schedule scans.

### Local Windows Task Scheduler

Use Windows Task Scheduler to run:

```powershell
& 'C:\Users\Devin\AppData\Local\Programs\Python\Python312\python.exe' scanners\daily_scanner.py --days 3
```

or:

```powershell
& 'C:\Users\Devin\AppData\Local\Programs\Python\Python312\python.exe' scanners\growth_scanner.py
```

Make sure the task working directory is:

```text
D:\repo_stocks\hammer-candlestick-app
```

### Docker Worker

Use the included `scanner-worker` service for a 24/7 daemon:

```powershell
docker compose up -d --build scanner-worker
```

This requires Docker Desktop or another Docker host with virtualization/container support.

---

## Backtesting

The backtesting engine lives at:

```text
engines/backtest.py
```

It simulates:

- Day 1 setup.
- Day 2 confirmation.
- Day 3 entry.
- Stop loss or take profit.
- Time exit after 10 trading bars.

The dashboard exposes this through the stock analysis and deep-dive views.

---

## Operational Notes

- Restart Streamlit after pulling code changes.
- Keep `.env` out of git.
- Keep `sentinel.db` backed up if it contains important subscriber/watchlist history.
- The app is local-first; exposing it outside your LAN requires additional security work.
- Docker files are included, but local Python execution remains valid and useful while Docker virtualization is unavailable.

---

## Disclaimer

TRadar is for educational and informational market research only. It does not provide financial, investment, tax, or trading advice. Market data and AI-generated summaries may be delayed, incomplete, or incorrect. Always do your own research before making financial decisions.
