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

def scan_ticker_for_growth_catalyst(ticker, min_vol_mult=2.0):
    """
    Scans a stock for volume surges (>= 2.0x 20-day MA) and catalyst news.
    Returns a unified payload for Groq AI growth evaluation.
    """
    vol_data = get_volume_metrics(ticker)
    news_items = get_google_stock_news(ticker)
    
    return {
        "ticker": ticker.upper(),
        "vol_mult": vol_data["vol_mult"],
        "latest_vol": vol_data["latest_vol"],
        "vol_20ma": vol_data["vol_20ma"],
        "has_volume_surge": vol_data["vol_mult"] >= min_vol_mult,
        "news": news_items
    }
