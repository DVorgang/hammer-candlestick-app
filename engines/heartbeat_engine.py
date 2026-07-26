import urllib.request
import xml.etree.ElementTree as ET
import yfinance as yf
import logging
import numpy as np
import pandas as pd
import re
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def get_google_stock_news(ticker, max_items=5):
    """
    Fetches real-time news headlines for a stock ticker from Google News RSS.
    """
    try:
        url = f"https://news.google.com/rss/search?q={ticker}+stock+when:3d&hl=en-US&gl=US&ceid=US:en"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        xml_data = urllib.request.urlopen(req, timeout=5).read()
        root = ET.fromstring(xml_data)
        items = root.findall(".//item")
        results = []
        for item in items[:max_items]:
            title = item.find("title").text if item.find("title") is not None else ""
            pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
            link = item.find("link").text if item.find("link") is not None else ""
            if title:
                clean_title = re.sub(r"\s*-\s*[^-]+$", "", title).strip()
                results.append({
                    "title": clean_title,
                    "pubDate": pub_date,
                    "link": link
                })
        return results
    except Exception as e:
        logging.error(f"Error fetching Google News for {ticker}: {e}")
        return []


def calculate_normalized_adtv(volume_series, trim_pct=0.10):
    """
    Calculates StockTitan Normalized Average Daily Trading Volume (ADTV).
    Trims extreme high volume outlier days (top 10%) to prevent recent news spikes from 
    artificially distorting the baseline resting heart rate volume.
    """
    if len(volume_series) == 0:
        return 0
    vol_array = np.array(volume_series, dtype=float)
    if len(vol_array) < 5:
        return float(np.mean(vol_array))
    
    # Sort and trim top 10% highest outlier volume days
    sorted_vols = np.sort(vol_array)
    cutoff = int(np.ceil(len(sorted_vols) * (1.0 - trim_pct)))
    trimmed_vols = sorted_vols[:max(1, cutoff)]
    return float(np.mean(trimmed_vols))


def get_heartbeat_candidates(max_candidates=150):
    """
    Assembles a candidate universe for Heartbeat Volatility Expansion scanning across:
    1. Yahoo Finance screeners (small_cap_gainers, aggressive_small_caps, most_actives, day_gainers, growth_technology_stocks)
    2. Microcap & Penny Stock Growth universe ($1.00+ floor)
    3. High-Beta Tech, Aerospace, Defense, and Biotech tickers.
    """
    candidates = set()
    screener_keys = [
        "small_cap_gainers",
        "aggressive_small_caps",
        "most_actives",
        "day_gainers",
        "growth_technology_stocks"
    ]
    
    for key in screener_keys:
        try:
            res = yf.screen(key)
            if res and "quotes" in res:
                for q in res["quotes"]:
                    sym = q.get("symbol", "").strip().upper()
                    if sym and "^" not in sym and "." not in sym and len(sym) <= 5:
                        candidates.add(sym)
        except Exception as e:
            logging.warning(f"Error querying screener {key}: {e}")

    microcap_universe = [
        "RKLB", "RDW", "MNTS", "INGN", "LEDS", "JOBY", "ACHR", "ASTS", "LUNR", "MARA",
        "RIOT", "CLSK", "BITF", "SOUN", "BZX", "BTAI", "KPTI", "CRIS", "VKTX", "ALT",
        "NVAX", "CELH", "SYM", "APP", "CAVA", "DUOL", "ELF", "POWW", "AMTX", "SOFI",
        "PLTR", "IONQ", "RGTI", "QUBT", "BBAI", "PATH", "OPEN", "ONDS", "SMCI", "AMD",
        "PINS", "WBD", "SIRI", "AAL", "NU", "NOK", "TSLA", "CLF", "SLB", "VRSN", "WKC",
        "THC", "SXT", "AMTB", "FRMI", "IP"
    ]
    candidates.update(microcap_universe)
    
    clean_list = sorted(list(candidates))
    return clean_list[:max_candidates]


def scan_ticker_for_heartbeat(ticker):
    """
    Performs quantitative Heartbeat Volatility Expansion scan on a single stock:
    - Minimum Price Floor: $1.00
    - Minimum Liquidity: 100,000 shares/day 20-day ADTV
    - Resting Heart Rate Squeeze: 15-day Bollinger Band Width < 0.12 (12%)
    - QRS Heartbeat Pulse: Current Volume >= 3.0x Normalized ADTV AND Price Change >= +3.0%
    - Support Hold: Candle Close in upper 30% of daily range (Close Ratio >= 0.70)
    - Channel Breakout: Close > Max High of previous 15-day squeeze window
    """
    try:
        obj = yf.Ticker(ticker)
        hist = obj.history(period="2mo")
        if hist.empty or len(hist) < 20:
            return {"ticker": ticker, "should_evaluate_ai": False, "reason": "Insufficient data"}
            
        latest_price = round(float(hist["Close"].iloc[-1]), 2)
        prev_price = round(float(hist["Close"].iloc[-2]), 2)
        
        # 1. Price Floor Check ($1.00 Minimum)
        if latest_price < 1.00:
            return {"ticker": ticker, "should_evaluate_ai": False, "reason": f"Price ${latest_price:.2f} below $1.00 floor"}
            
        # 2. Liquidity Floor Check (100k Shares/Day ADTV Min)
        vols_20 = hist["Volume"].iloc[-21:-1] if len(hist) >= 21 else hist["Volume"].iloc[:-1]
        normalized_adtv = calculate_normalized_adtv(vols_20)
        if normalized_adtv < 100000:
            return {"ticker": ticker, "should_evaluate_ai": False, "reason": f"ADTV {int(normalized_adtv)} below 100k liquidity floor"}
            
        latest_vol = float(hist["Volume"].iloc[-1])
        vol_mult = round(latest_vol / normalized_adtv, 2) if normalized_adtv > 0 else 1.0
        
        # 3. Resting Heart Rate Squeeze Math (15-Day Bollinger Band Width)
        window_15 = hist.iloc[-16:-1] if len(hist) >= 16 else hist.iloc[:-1]
        sma_15 = window_15["Close"].mean()
        std_15 = window_15["Close"].std()
        upper_band = sma_15 + (2.0 * std_15)
        lower_band = sma_15 - (2.0 * std_15)
        bb_width = (upper_band - lower_band) / sma_15 if sma_15 > 0 else 1.0
        bb_width_pct = round(bb_width * 100, 2)
        
        # Squeeze Cutoff: Band Width must be tight (< 12.0%)
        is_in_squeeze = bb_width < 0.12
        
        # 4. QRS Heartbeat Pulse Math (Volume >= 3.0x AND Price Change >= +3.0%)
        price_change_pct = round(((latest_price - prev_price) / prev_price) * 100, 2) if prev_price > 0 else 0.0
        has_volume_pulse = vol_mult >= 3.0
        has_price_pulse = price_change_pct >= 3.0
        
        # 5. Candle Support Hold Ratio ((Close - Low) / (High - Low) >= 0.70)
        day_high = float(hist["High"].iloc[-1])
        day_low = float(hist["Low"].iloc[-1])
        range_span = day_high - day_low
        close_ratio = (latest_price - day_low) / range_span if range_span > 0 else 1.0
        has_strong_close = close_ratio >= 0.70
        
        # 6. Channel Breakout Check (Close > Max High of 15-day squeeze window)
        squeeze_max_high = float(window_15["High"].max())
        is_breakout = latest_price > squeeze_max_high
        
        # Moving Average Trend Alignment (200 SMA & 50 SMA for Bonus Points)
        sma_200 = float(hist["Close"].mean()) if len(hist) >= 40 else sma_15
        above_200sma = latest_price >= sma_200
        
        # Calculate Math Portion of 100-Point Conviction Score (Max 60 points pre-AI)
        # Factor 2: Squeeze Tightness (Max 25 pts)
        squeeze_score = max(0, min(25, (0.12 - bb_width) / 0.12 * 25))
        
        # Factor 3: Volume Surge Intensity (Max 20 pts)
        vol_score = max(0, min(20, (vol_mult / 5.0) * 20))
        
        # Factor 4: Candle Close Strength (Max 15 pts)
        candle_score = max(0, min(15, close_ratio * 15))
        
        # Synergy Bonus (Max 10 pts)
        synergy_bonus = 10 if above_200sma else 0
        
        math_score = round(squeeze_score + vol_score + candle_score + synergy_bonus, 1)
        
        # Check if candidate qualifies for AI Evaluation
        should_eval = is_in_squeeze and has_volume_pulse and has_price_pulse and has_strong_close and is_breakout
        
        news = []
        if should_eval:
            logging.info(f"💓 Heartbeat QRS Pulse DETECTED for {ticker}: Vol {vol_mult}x, Price +{price_change_pct}%, BB Width {bb_width_pct}%, Math Score: {math_score}/60")
            news = get_google_stock_news(ticker, max_items=5)
            
        return {
            "ticker": ticker,
            "should_evaluate_ai": should_eval,
            "latest_price": latest_price,
            "prev_price": prev_price,
            "price_change_pct": price_change_pct,
            "vol_mult": vol_mult,
            "latest_vol": int(latest_vol),
            "normalized_adtv": int(normalized_adtv),
            "bb_width_pct": bb_width_pct,
            "close_ratio": round(close_ratio, 2),
            "squeeze_max_high": round(squeeze_max_high, 2),
            "above_200sma": above_200sma,
            "math_score": math_score,
            "news_headlines": news
        }
        
    except Exception as e:
        logging.error(f"Error scanning heartbeat for {ticker}: {e}")
        return {"ticker": ticker, "should_evaluate_ai": False, "reason": str(e)}
