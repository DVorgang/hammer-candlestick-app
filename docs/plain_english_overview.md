# TRadar Plain-English Overview

This document explains TRadar in simple, non-technical language. It is meant for friends, family, or anyone who wants to understand what the app does without needing to understand programming or trading software.

---

## What TRadar Does

TRadar is a personal stock alert system. Think of it like a radar system for the stock market—it watches quietly in the background and only speaks up when a stock meets strict alert conditions.

The app does not place trades and does not tell anyone what they must buy or sell. It scans stocks, checks mathematical rules, uses artificial intelligence (Groq Llama 3.3-70B) to evaluate news catalysts, and delivers structured email alerts when a setup looks worthy of review.

---

## The Three Main Scanners

TRadar features three specialized scanning engines that look for different market opportunities:

1. **The Technical Reversal Scanner** *(Watchlist Hammer & Hanging Man Setups)*
2. **The Growth Catalyst Scanner** *(Market-Wide News, Contracts & Earnings Beats)*
3. **The Heartbeat Volatility Expansion Scanner** *(The "Sleeping Giant" Breakout Detector)*

---

## Scanner 1: Technical Reversal Scanner

The Technical Reversal Scanner monitors a personal watchlist for specific candlestick patterns.

A candlestick is a simple visual summary of a stock's trading day: where it opened, how high it went, how low it went, and where it closed.

This scanner focuses on two main patterns:
- **Hammer:** Suggests that buyers stepped in after lower prices, indicating a possible price bounce.
- **Hanging Man:** Suggests that sellers took control after a price rise, indicating possible profit-taking risk.

### The 3-Day Rule (Avoiding False Signals)
TRadar never sends an alert just because one day's candle looks interesting. It enforces a strict 3-day validation lifecycle:

- **Day 1 (Setup Day):** The stock forms a proper Hammer or Hanging Man shape (long wick, small body).
- **Day 2 (Confirmation Day):** TRadar waits for the next trading day. For a Hammer, price must close higher than Day 1's high. For a Hanging Man, price must close lower than Day 1's low. If confirmation fails, the setup is discarded.
- **Day 3 (Trade Blueprint Day):** If confirmed, TRadar generates a structured email alert with an Entry Zone, Stop-Loss, Take-Profit Target, and a 2-to-1 Reward-to-Risk ratio.

---

## Scanner 2: Growth Catalyst Scanner

Instead of scanning a personal watchlist for chart shapes, the Growth Catalyst Scanner searches the broader U.S. stock market for stocks experiencing sudden momentum driven by company news.

It looks for events like:
- Major government or commercial contracts
- Strategic partnerships
- FDA drug/device approvals
- Strong earnings beats & revenue guidance
- New product launches & acquisitions

### How It Works:
1. **Market Screening:** Scans active stock screeners (gainers, volume leaders, tech growth) for candidates.
2. **Volume Surge Pre-Filter:** Requires the stock to trade at **2.0x or higher** its normal 20-day average volume.
3. **News Matching:** Scans Google News for high-impact catalyst keywords (contract, earnings, patent, revenue, approval).
4. **AI Catalyst Scoring:** Passes candidates to Groq AI (Llama 3.3-70B) for evaluation. Only setups scoring **8.0 / 10** or higher qualify.
5. **Top-3 Digest:** Sends a single, sleek digest email bundling the top candidates to prevent inbox clutter.

---

## Scanner 3: Heartbeat Volatility Expansion Scanner (The "Sleeping Giant" Breakout Detector)

The Heartbeat Volatility Expansion Scanner searches for stocks that have been completely flat and dormant for weeks, and alerts you the exact moment they erupt into a major new trend.

### Think of a Coiled Spring (The "Resting Heart Rate" Squeeze)
When a stock stays in an ultra-tight, narrow price range for 2 to 4 weeks, volatility shrinks like a compressed spring. Traders call this a **Bollinger Band Squeeze** (Band Width < 12%). The stock looks dead or forgotten, but big institutions are quietly accumulating shares.

### The "QRS Volume Pulse" Breakout
Suddenly, a massive surge of buying volume hits the stock (over **3.0x to 5.0x normal volume**), driving the price up sharply (+3% or more) and closing near the high of the day. This sudden pulse is like an EKG heartbeat monitor jumping to life.

### Key Innovations in Scanner 3:
- **StockTitan Trimmed Volume Baseline:** Uses a trimmed median 20-day volume calculation. This prevents a single historical news spike from distorting what "normal volume" really is.
- **100-Point AI Conviction Score:** Combines 40% Groq AI catalyst rating + 25% squeeze tightness + 20% volume pulse strength + 15% candle close ratio. Only setups scoring **80.0 / 100** or higher are featured.
- **Plain-English Email Metrics:** Displays instant, easy-to-understand metrics:
  - `Buying Surge: 3.07x Normal Volume 🔥`
  - `Price Squeeze: Ultra-Tight (5.3%) 🎯`
  - `1-Year Trend: Healthy Uptrend ✅`
- **Structured Trade Blueprint & "How to Play":** Clearly lists the Current Market Price ($28.50), Suggested Entry Zone ($27.93 – $29.64), Take-Profit Target ($34.20), Stop-Loss ($27.07), and a 1-line plain-English instruction telling you exactly how to execute (buy at open or set a limit order on a dip).

---

## Smart Conditional Cooldowns & Momentum Badges

To prevent your inbox from being flooded with the exact same stock day after day, TRadar uses **Smart Conditional Rules**:

1. **Suppressed (Duplicate / No-Change):** If a stock was featured yesterday and has no new news or score increase today, the alert is suppressed.
2. **Re-Triggered with Momentum Badges:** If a stock continues surging on massive volume or fresh AI news, TRadar re-sends the alert immediately with a visual badge:
   - `🔥 MULTI-DAY MOMENTUM CONTINUATION` (Stock featured 2 days in a row on rising score)
   - `⚡ DOUBLE-SYNERGY BREAKOUT` (Stock triggered both a technical reversal and a heartbeat pulse)
   - `💓 SLEEPING GIANT HEARTBEAT PULSE` (Fresh Stage-2 squeeze breakout)

---

## The Dashboard & Outcome Tracking Matrix

TRadar includes an interactive Streamlit dashboard accessible from any browser on your network:

- **3-Engine Control Hub:** Toggle Technical, Growth, or Heartbeat scanners on/off with 1-click controls.
- **Watchlist & CC Recipient Management:** Add/remove stock tickers and configure a secondary CC email address.
- **Instant Ticker Deep-Dive:** Search any U.S. stock symbol for live financial metrics, technical indicators, and historical backtests.
- **🧠 System Learning & Post-Trade Outcome Matrix:** Automatically monitors every alert sent to your email. Tracks whether price reached the Take-Profit Target (WIN) or Stop-Loss Cutoff (LOSS) over time, and feeds that track record back into future AI evaluations!

---

## Summary

TRadar is a sophisticated, local-first market intelligence platform that acts as your personal 24/7 research analyst. By combining mathematical pattern detection, volume squeeze math, and Groq Llama 3.3-70B AI news evaluation, it delivers clear, actionable, plain-English trade blueprints straight to your inbox.
