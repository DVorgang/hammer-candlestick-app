# TRadar - AI Market Intelligence & 3-Engine Growth Catalyst Platform

TRadar is a local-first market intelligence dashboard and automated email alert system built with Python, Streamlit, Plotly, yfinance, Groq Llama 3.3-70B AI integration, SMTP email delivery, and SQLite.

The platform combines three complementary scanning engines:

1. **📊 Candlestick Technical Reversal Engine:** Watchlist-based technical reversal scanner for Hammer and Hanging Man setups with RSI oversold validation, 3-day life-cycle confirmation, and 2:1 trade blueprints.
2. **🚀 Whole-Market AI Growth Engine:** Market-wide scanner for unusual volume, fresh news catalysts, and AI-ranked contract/earnings breakout candidates.
3. **💓 Heartbeat Volatility Expansion Engine:** Sleeping giant breakout scanner detecting tight multi-week squeezes (Bollinger Band Width < 12%) with sudden QRS Volume Pulses (>= 3.0x Normalized ADTV) and 100-Point Conviction Scoring.

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
- Sends qualifying candidates to the AI analyst (Groq Llama 3.3-70B).
- Sends a single Top-3 Market Growth Digest for elite candidates (`>= 8.0/10` AI score).
- Records growth discoveries and applies 5-day cooldown logic to reduce duplicate growth alerts.

### 💓 Heartbeat Volatility Expansion Engine

- Identifies dormant "Sleeping Giant" stocks ($1.00+ price floor) consolidating in ultra-tight volatility squeezes (15-day Bollinger Band Width < 12%).
- Calculates **StockTitan Normalized ADTV** (trimmed median 20-day volume excluding outlier spike days to prevent baseline distortion).
- Detects **QRS Volume Pulses** (current volume >= 3.0x Normalized ADTV with price breakout >= +3.0% and upper 30% candle close ratio).
- Evaluates setup quality using a **100-Point Conviction Score** (40% Groq AI Catalyst + 25% Squeeze Tightness + 20% Volume Pulse + 15% Candle Close).
- Implements **Smart Conditional Cooldown & Momentum Badges** (`🔥 MULTI-DAY MOMENTUM CONTINUATION`, `⚡ DOUBLE-SYNERGY BREAKOUT`, `💓 SLEEPING GIANT HEARTBEAT PULSE`).
- Formats emails with plain-English labels (`Buying Surge: 3.07x Normal Volume 🔥`, `Price Squeeze: Ultra-Tight (5.3%) 🎯`, `1-Year Trend: Healthy Uptrend ✅`).
- Includes structured Trade Blueprint targets, Current Price, explicit "How to Play" guidance, Trailing Lock Tip advice, crisp SVG heart EKG logo, and 24/7 public TradingView/Yahoo/Finviz chart links.

### Email Alerts & Secondary Recipients

TRadar can send:
- Single technical reversal alerts.
- Watchlist Technical Digest emails when multiple technical setups are found.
- Top-3 Market Growth Digest emails.
- Top-3 Heartbeat Volatility Expansion Digest emails.
- Synergy alerts when a technical reversal appears on a recent growth or heartbeat discovery.

SMTP delivery uses `.env` settings (Gmail SMTP). Subscribers can configure a secondary CC email recipient in the UI. Alert emails are delivered to both the primary subscriber email and optional secondary recipient.

### Streamlit Control Panel

The Streamlit app includes:
- OTP/token-based local account access.
- Watchlist and alert preference management.
- 3-Engine Control Hub (1-click toggles for Technical, Growth, and Heartbeat engines).
- Secondary email recipient management.
- Stock search and deep-dive analysis.
- Live quotes and interactive technical charts.
- Strategy backtester sandbox (2-year simulation).
- Scanner control panel with test buttons.
- Recent scanner run logs with category filtering.
- **Categorized System Learning & Post-Trade Outcome Matrix** with 3 engine sub-tabs (Technical Reversals, AI Growth Discoveries, Heartbeat Volatility Audit).

---

## Repository Structure

```text
hammer-candlestick-app/
  ai/
    analyst_engine.py          # Groq AI analyst fallback chain and JSON parsing
  assets/
    heartbeat_logo.png         # Custom glowing heart EKG logo asset
    tradar_logo.png            # Main TRadar logo options
    traderadar_banner.png
    traderadar_logo.png
  core/
    database.py                # SQLite schema, subscribers, schedulers, logs, outcomes
    local_env.py               # Simple .env loader
  docs/
    plain_english_overview.md  # Simple, non-technical explanation for beginner users
  engines/
    backtest.py                # Historical 2-year strategy backtester
    growth_engine.py           # Market screeners, volume metrics, Google News RSS
    heartbeat_engine.py        # Volatility squeeze & QRS volume pulse math engine
    pattern_engine.py          # Candlestick detection, RSI, SMAs, score calibration
  notifications/
    notifier.py                # HTML email templates and SMTP delivery
  scanners/
    daily_scanner.py           # Watchlist technical scanner
    growth_scanner.py          # Whole-market growth catalyst scanner
    heartbeat_scanner.py       # Whole-market heartbeat volatility scanner
    scheduler_daemon.py        # 24/7 background worker loop
  tests/
    test_docker_health_and_wal.py
    test_full_system.py        # 24-point cross-module integration test suite
    test_gemini.py
    test_heartbeat_engine.py   # Heartbeat math & squeeze test suite
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

---

## Local Setup & Quickstart

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Run the Streamlit dashboard:

```powershell
python -m streamlit run app.py --server.address 0.0.0.0
```

Local browser URL: `http://localhost:8501`

---

## Manual Scanner CLI Commands

Run the watchlist technical scanner:
```powershell
python scanners/daily_scanner.py --days 3
```

Run the whole-market growth catalyst scanner:
```powershell
python scanners/growth_scanner.py
```

Run the whole-market heartbeat volatility scanner:
```powershell
python scanners/heartbeat_scanner.py
```

Run full system integration tests:
```powershell
python tests/test_full_system.py
```

---

## Database Architecture

TRadar uses SQLite via `sentinel.db`. The database layer enables WAL mode for improved concurrent read/write behavior:

```sql
PRAGMA journal_mode = WAL;
```

Primary tables include:
- `subscribers`: User email, secondary email, management token, engine preferences (`wants_buys`, `wants_growth`, `wants_heartbeat`).
- `watchlists`: Tickers monitored per subscriber.
- `sent_alerts`: Log of all dispatched alerts and outcome resolution tracking fields.
- `scanner_logs`: Execution metrics, duration, candidate counts, and errors per scan run.
- `scheduler_state`: 24/7 background scheduler toggles (`is_active`, `growth_is_active`, `heartbeat_is_active`) and last run timestamps.
- `growth_discoveries`: Market growth discovery tracking and 5-day cooldown records.
- `heartbeat_discoveries`: Heartbeat volatility breakout records and conviction scores.

---

## Docker & Server Deployment

Compose services:
- `streamlit-ui`: Streamlit dashboard on port 8501.
- `scanner-worker`: 24/7 daemon running scheduled growth, heartbeat, and technical reversal scans.

Start the stack:
```powershell
docker compose up -d --build
```

View logs:
```powershell
docker compose logs -f
```

---

## Disclaimer

TRadar is for educational and market research purposes only. It does not provide financial, investment, tax, or trading advice. Market data and AI-generated summaries may be delayed or incomplete. Always perform your own research before making financial decisions.
