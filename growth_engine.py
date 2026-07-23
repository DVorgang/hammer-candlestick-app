import urllib.request
import xml.etree.ElementTree as ET
import yfinance as yf
import logging
import json
import re
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def get_google_stock_news(ticker, max_items=5):
    """
    Fetches clean real-time news headlines for a stock ticker from Google News RSS.
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
                # Clean title
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

def get_volume_metrics(ticker):
    """
    Calculates today's volume multiplier against the 20-day Volume Moving Average.
    """
    try:
        obj = yf.Ticker(ticker)
        hist = obj.history(period="1mo")
        if hist.empty or len(hist) < 15:
            return {"vol_mult": 1.0, "latest_vol": 0, "vol_20ma": 0}
            
        vol_20ma = hist["Volume"].iloc[-21:-1].mean() if len(hist) >= 21 else hist["Volume"].mean()
        latest_vol = float(hist["Volume"].iloc[-1])
        vol_mult = latest_vol / vol_20ma if vol_20ma > 0 else 1.0
        
        return {
            "vol_mult": round(float(vol_mult), 2),
            "latest_vol": int(latest_vol),
            "vol_20ma": int(vol_20ma)
        }
    except Exception as e:
        logging.error(f"Error fetching volume metrics for {ticker}: {e}")
        return {"vol_mult": 1.0, "latest_vol": 0, "vol_20ma": 0}

def get_market_growth_candidates(max_candidates=100):
    """
    Scans the entire US market for active breakout candidates using Yahoo Finance real-time 
    screeners (most_actives, day_gainers, small_cap_gainers, aggressive_small_caps, growth_technology_stocks)
    plus a broad market ticker universe.
    Returns a clean, deduplicated list of uppercase ticker symbols.
    """
    candidates = set()
    
    # 1. Query Yahoo Finance Real-time Screeners for active movers & small caps
    screener_keys = [
        "most_actives", 
        "day_gainers", 
        "small_cap_gainers", 
        "aggressive_small_caps", 
        "growth_technology_stocks"
    ]
    
    for key in screener_keys:
        try:
            res = yf.screen(key)
            if res and "quotes" in res:
                for q in res["quotes"]:
                    sym = q.get("symbol", "").strip().upper()
                    # Filter out indices, test symbols, and non-alphanumeric tickers
                    if sym and "^" not in sym and "." not in sym and len(sym) <= 5:
                        candidates.add(sym)
        except Exception as e:
            logging.warning(f"Error querying screener {key}: {e}")

    # 2. Add Broad Market Core Tickers (S&P 500, Nasdaq-100 & High-Beta Small Caps)
    broad_universe = [
        "AMD", "NVDA", "PLTR", "SOFI", "SMCI", "RKLB", "RDW", "MNTS", "INGN", "LEDS", 
        "PINS", "WBD", "SIRI", "PATH", "OPEN", "ONDS", "AAL", "NU", "NOK", "TSLA", 
        "IONQ", "RGTI", "QUBT", "BBAI", "JOBY", "ACHR", "ASTS", "LUNR", "MARA", "RIOT",
        "CLSK", "BITF", "SOUN", "BZX", "BTAI", "KPTI", "CRIS", "VKTX", "ALT", "NVAX",
        "MRNA", "BNTX", "CELH", "SYM", "APP", "CAVA", "DUOL", "ELF", "POWW", "AMTX"
    ]
    for sym in broad_universe:
        candidates.add(sym)

    candidate_list = list(candidates)
    logging.info(f"Market Growth Screener assembled {len(candidate_list)} market-wide breakout candidates.")
    return candidate_list[:max_candidates]

CATALYST_KEYWORDS = [
    "contract", "deal", "partnership", "acquire", "acquisition", "earnings",
    "revenue", "profit", "fda", "approval", "patent", "launch", "billion", "million",
    "grant", "award", "skyrocket", "surge", "growth"
]

def scan_ticker_for_growth_catalyst(ticker, min_vol_mult=2.0):
    """
    Scans a stock for volume surges (>= 2.0x 20-day MA) and catalyst news.
    Returns a unified payload for Groq AI growth evaluation.
    """
    vol_data = get_volume_metrics(ticker)
    news_items = get_google_stock_news(ticker)
    
    has_vol_surge = vol_data["vol_mult"] >= min_vol_mult
    has_keyword_news = False
    
    for item in news_items:
        title_lower = item.get("title", "").lower()
        if any(kw in title_lower for kw in CATALYST_KEYWORDS):
            has_keyword_news = True
            break

    return {
        "ticker": ticker.upper(),
        "vol_mult": vol_data["vol_mult"],
        "latest_vol": vol_data["latest_vol"],
        "vol_20ma": vol_data["vol_20ma"],
        "has_volume_surge": has_vol_surge,
        "has_keyword_news": has_keyword_news,
        "should_evaluate_ai": has_vol_surge and has_keyword_news,
        "news": news_items
    }

