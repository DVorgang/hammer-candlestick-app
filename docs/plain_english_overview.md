# TRadar Plain-English Overview

This document explains TRadar in simple, non-technical language. It is meant for friends, family, or anyone who wants to understand what the app does without needing to understand programming or trading software.

## What TRadar Does

TRadar is a personal stock alert system.

It watches the market for two main kinds of situations:

- Stocks that may be showing a technical reversal pattern.
- Stocks that may be getting attention because of strong news, unusual volume, or a possible business growth catalyst.

The app does not place trades. It does not tell anyone what they must buy or sell. It scans stocks, checks a set of rules, and sends an email when something looks interesting enough to review.

Think of it like a radar system for the stock market. It watches quietly in the background and only speaks up when something meets its alert conditions.

## The Two Main Scanners

TRadar has two separate scanners:

- The Technical Reversal Scanner
- The Growth Catalyst Scanner

They look for different things.

## Scanner 1: Technical Reversal Scanner

The Technical Reversal Scanner looks for specific candlestick patterns on stocks in a personal watchlist.

A candlestick is a simple visual summary of a stock's trading day. It shows:

- Where the stock opened
- How high it went
- How low it went
- Where it closed

This scanner focuses mainly on two patterns:

- Hammer
- Hanging Man

A Hammer can suggest that a stock may be trying to bounce after weakness.

A Hanging Man can suggest that a stock may be showing risk after strength.

TRadar does not send an alert just because one candle looks interesting. It uses a stricter 3-day process.

### Day 1: The Setup Day

On the first day, the scanner checks whether the stock formed the right candle shape.

For a Hammer or Hanging Man shape, it looks for:

- A small candle body
- A long lower wick
- Very little upper wick

In plain English, this means sellers pushed the stock down during the day, but buyers brought it back up before the close.

That can be meaningful because it shows the stock rejected lower prices.

But the app does not stop there.

It also checks supporting conditions such as:

- RSI
- Volume
- Moving averages
- Recent price trend

RSI is a momentum reading. It helps estimate whether a stock is weak, stretched, oversold, or overbought.

Volume matters because a pattern with stronger-than-normal trading activity is usually more meaningful than one that happens on quiet volume.

Moving averages help the app understand whether the stock is near important price areas or extended away from them.

### Day 2: The Confirmation Day

This is one of the most important parts of the app.

TRadar waits for the next trading day before trusting the pattern.

For a Hammer, the next day must close above the high of the Hammer day.

That means buyers actually followed through.

For a Hanging Man, the next day must close below the low of the Hanging Man day.

That means sellers actually followed through.

If confirmation does not happen, the pattern is ignored.

This helps reduce false alerts.

### Day 3: The Trade Blueprint Day

If the setup forms on Day 1 and confirms on Day 2, then TRadar creates an email alert.

The alert includes a simple trade blueprint:

- Possible entry area
- Stop loss area
- Profit target
- Risk/reward math
- Plain-English explanation

For Hammer alerts, the app treats the setup like a possible bullish reversal.

For Hanging Man alerts, the app treats the setup like a possible warning or risk-reduction signal.

It also checks gap risk. If the stock opens in a way that already invalidates the setup, the alert can be skipped.

## Scanner 2: Growth Catalyst Scanner

The Growth Catalyst Scanner looks for something different.

Instead of only scanning a personal watchlist for chart patterns, it scans a broader market list for stocks that may have fresh momentum because of news or unusual attention.

It looks for things like:

- Unusual trading volume
- Strong price movement
- Fresh company news
- Catalyst headlines
- Possible business growth events

Examples of catalyst news might include:

- A major contract
- A strategic partnership
- An FDA approval
- A strong earnings report
- A new product launch
- A large revenue announcement
- An acquisition
- A major award or grant

The scanner first builds a list of market candidates using sources like Yahoo Finance screeners.

It looks at groups such as:

- Most active stocks
- Daily gainers
- Small-cap gainers
- Aggressive growth names
- Technology growth stocks

Then it checks whether the stock has unusual volume.

A stock usually needs volume around 2 times higher than normal before it becomes interesting to this scanner.

That means the stock is trading much more actively than usual.

Then TRadar checks recent news headlines.

It looks for catalyst keywords such as:

- contract
- deal
- partnership
- approval
- earnings
- revenue
- launch
- acquisition
- grant
- award
- growth

If a stock has both unusual volume and relevant news, then the app sends that candidate to the AI analyst.

The AI analyst reviews the news and gives the catalyst a score.

The current growth scanner is looking for stronger setups, usually around 8 out of 10 or higher.

If multiple strong candidates are found, TRadar sends a single digest email with the top growth opportunities instead of flooding the inbox with separate emails.

## What The Emails Mean

An email from TRadar is not a command to buy or sell.

It is more like:

> Something interesting just happened. Here is why it may be worth reviewing.

A technical alert explains the chart setup.

A growth alert explains the news, volume, and possible business catalyst.

A digest email groups multiple interesting stocks into one cleaner summary.

## Why The App Waits For Confirmation

Many stock patterns look promising for one day and then fail immediately.

TRadar tries to avoid that by waiting for confirmation.

That means the app is designed to be slower and more selective.

It would rather miss some early moves than send too many weak alerts.

## Simple Summary

TRadar watches stocks for:

- Confirmed technical reversal setups
- Unusual volume
- Fresh market-moving news
- Strong AI-rated growth catalysts

When something passes the scanner rules, it sends an email with a plain-English explanation and key price levels.

The app is meant to help someone notice potential setups earlier, stay organized, and review opportunities with more context. It is not a trading bot and does not make decisions for the user.
