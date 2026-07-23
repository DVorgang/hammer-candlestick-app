import yfinance as yf
import pandas as pd
import numpy as np
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def download_stock_data(ticker, period="2y", interval="1d"):
    """
    Downloads historical stock data from yfinance.
    Protects original data structure by returning an explicit copy.
    """
    try:
        logging.info(f"Downloading data for ticker {ticker}...")
        ticker_obj = yf.Ticker(ticker.strip().upper())
        df = ticker_obj.history(period=period, interval=interval)
        if df.empty:
            logging.warning(f"No data returned for ticker {ticker}.")
            return pd.DataFrame()
        
        # Protect original dataframe via explicit copy
        df_copy = df.copy()
        df_copy.reset_index(inplace=True)
        return df_copy
    except Exception as e:
        logging.error(f"Error downloading data for ticker {ticker}: {e}")
        return pd.DataFrame()

def calculate_wilders_rsi(series, period=14):
    """
    Calculates Wilder's RSI (14-period) matching trading standards.
    """
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    # We copy the gain and loss to calculate rolling average and then smooth
    avg_gain = gain.copy()
    avg_loss = loss.copy()
    
    # Fill first 'period' elements with NaN (since they won't have enough values)
    avg_gain.iloc[:period] = np.nan
    avg_loss.iloc[:period] = np.nan
    
    # First non-NaN average is a simple average of the first 'period' elements
    # Since we diff(), the first diff is at index 1. Index period is the 14th difference.
    if len(series) > period:
        avg_gain.iloc[period] = gain.iloc[1:period+1].mean()
        avg_loss.iloc[period] = loss.iloc[1:period+1].mean()
        
        # Wilder's smoothing for the rest of the array
        for i in range(period + 1, len(series)):
            avg_gain.iloc[i] = (avg_gain.iloc[i-1] * (period - 1) + gain.iloc[i]) / period
            avg_loss.iloc[i] = (avg_loss.iloc[i-1] * (period - 1) + loss.iloc[i]) / period
            
    rs = avg_gain / (avg_loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def add_indicators(df):
    """
    Adds required indicators: RSI_14, SMA_200, SMA_50, and Volume_MA_20.
    Ensures safe calculations.
    """
    if df.empty or len(df) < 200:
        # Cannot calculate SMA_200 properly without at least 200 bars
        logging.warning("DataFrame has fewer than 200 rows. Moving averages might contain NaNs.")
        
    df['RSI_14'] = calculate_wilders_rsi(df['Close'], 14)
    df['SMA_200'] = df['Close'].rolling(window=200).mean()
    df['SMA_50'] = df['Close'].rolling(window=50).mean()
    df['Volume_MA_20'] = df['Volume'].rolling(window=20).mean()
    
    return df

def identify_setup_candle(df, idx):
    """
    Checks if the candle at df.iloc[idx] matches the V3 geometric criteria
    for a Hammer/Hanging Man shape.
    Returns:
        is_pattern: bool
        pattern_type: str ('Hammer', 'Hanging Man', or None)
        confidence_score: float (0-100, or 0 if not a match)
    """
    if idx < 200:
        # Ensure a 200-period SMA is warmed up safely by looping strictly past row 200
        return False, None, 0.0

    row = df.iloc[idx]
    
    # Extract prices
    o = row['Open']
    h = row['High']
    l = row['Low']
    c = row['Close']
    v = row['Volume']
    
    # Calculate geometric details
    body = abs(c - o)
    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - l
    total_range = h - l
    
    if total_range <= 0:
        return False, None, 0.0

    # V3 Geometric Rules
    # 1. Lower shadow is >= 2.0x body
    # 2. Minimal upper shadow: upper shadow <= 10% of total range OR upper shadow <= 20% of body
    is_geometric_match = (lower_shadow >= 2.0 * body) and (
        upper_shadow <= 0.10 * total_range or upper_shadow <= 0.20 * body
    )
    
    if not is_geometric_match:
        return False, None, 0.0

    # Read indicators
    rsi = row['RSI_14']
    sma_200 = row['SMA_200']
    sma_50 = row['SMA_50']
    vol_ma_20 = row['Volume_MA_20']
    
    # Handle NaNs in indicators
    if pd.isna(rsi) or pd.isna(sma_200) or pd.isna(sma_50) or pd.isna(vol_ma_20):
        return False, None, 0.0

    # Distinguish Trend (Hammer vs Hanging Man)
    # Hammer: Bullish Reversal at bottom of downtrend / oversold support (RSI < 50)
    # Hanging Man: Bearish Reversal at top of uptrend / overbought extension (RSI >= 50)
    if rsi < 50:
        pattern_type = "Hammer"
    else:
        pattern_type = "Hanging Man"

    # Calculate Confidence Score (0-100)
    # 1. RSI Factor (up to 35 points)
    score_rsi = 0.0
    if pattern_type == "Hammer":
        # RSI closer to 20 gets higher score, >= 50 gets 0
        if rsi <= 30:
            score_rsi = 35.0
        elif rsi < 50:
            score_rsi = 35.0 * (50.0 - rsi) / 20.0
    else: # Hanging Man
        # RSI closer to 80 gets higher score, <= 50 gets 0
        if rsi >= 70:
            score_rsi = 35.0
        elif rsi > 50:
            score_rsi = 35.0 * (rsi - 50.0) / 20.0
            
    # 2. Volume Factor (up to 35 points)
    score_vol = 0.0
    vol_mult = v / (vol_ma_20 + 1e-10)
    if vol_mult >= 1.5:
        score_vol = 35.0
    elif vol_mult > 0.8:
        score_vol = 35.0 * (vol_mult - 0.8) / 0.7
        
    # 3. SMA Proximity & Trend Alignment (up to 30 points)
    score_trend = 0.0
    if pattern_type == "Hammer":
        # Proximity to SMA_200 or SMA_50
        dist_200 = abs(c - sma_200) / sma_200
        dist_50 = abs(c - sma_50) / sma_50
        
        # High confidence if near long-term key SMAs (within 3% of SMA_200 or 2% of SMA_50)
        if dist_200 <= 0.03 or dist_50 <= 0.02:
            score_trend = 30.0
        elif c > sma_200:
            # Rebounding in a structural uptrend
            score_trend = 15.0
        else:
            score_trend = 5.0
    else: # Hanging Man
        # Wants overextension above SMAs (far from support)
        dist_200 = (c - sma_200) / sma_200
        if dist_200 >= 0.15:
            score_trend = 30.0
        elif dist_200 >= 0.05:
            score_trend = 30.0 * (dist_200 - 0.05) / 0.10
        else:
            score_trend = 5.0

    total_score = score_rsi + score_vol + score_trend
    # Constrain to 0-100 range
    confidence_score = float(max(0.0, min(100.0, total_score)))
    
    return True, pattern_type, confidence_score

def scan_ticker_for_signals(ticker, days_to_scan=5):
    """
    Downloads ticker history, calculates indicators, and scans the last few days
    for Hammer or Hanging Man signals.
    """
    df = download_stock_data(ticker)
    if df.empty or len(df) < 202: # Needs at least 200 rows + some confirmation days
        logging.warning(f"Not enough historical data for {ticker} (need at least 202 days).")
        return []

    df = add_indicators(df)
    signals = []
    
    # Scan back from the end of the dataframe
    # We need to make sure we leave enough days at the end to check for Day 2 confirmation
    # If scanning for active signals that have confirmed, we look back from the end.
    # Specifically, a signal triggered on 'Day 1' is confirmed on 'Day 2' (which could be yesterday or today).
    # Let's scan the last `days_to_scan` completed candles as Day 1.
    start_idx = len(df) - days_to_scan - 2 # Leaves at least 2 days at the end for check
    start_idx = max(200, start_idx)
    
    for idx in range(start_idx, len(df) - 1):
        is_pattern, pattern_type, score = identify_setup_candle(df, idx)
        if is_pattern:
            # Check for Day 2 Confirmation (index: idx + 1)
            # Hammer confirmation: Close_2 > High_1
            # Hanging Man confirmation: Close_2 < Low_1
            day1_high = df['High'].iloc[idx]
            day1_low = df['Low'].iloc[idx]
            day2_close = df['Close'].iloc[idx + 1]
            day2_date = df['Date'].iloc[idx + 1]
            
            day3_open = float(df['Open'].iloc[idx + 2]) if (idx + 2 < len(df)) else None
            day3_date = df['Date'].iloc[idx + 2] if (idx + 2 < len(df)) else None
            
            confirmed = False
            if pattern_type == "Hammer" and day2_close > day1_high:
                confirmed = True
            elif pattern_type == "Hanging Man" and day2_close < day1_low:
                confirmed = True
                
            signals.append({
                "ticker": ticker,
                "day1_index": idx,
                "day1_date": df['Date'].iloc[idx],
                "day1_open": df['Open'].iloc[idx],
                "day1_high": day1_high,
                "day1_low": day1_low,
                "day1_close": df['Close'].iloc[idx],
                "pattern_type": pattern_type,
                "confidence_score": score,
                "rsi_14": df['RSI_14'].iloc[idx],
                "vol_mult": df['Volume'].iloc[idx] / df['Volume_MA_20'].iloc[idx],
                "day2_date": day2_date,
                "day2_close": day2_close,
                "day3_date": day3_date,
                "day3_open": day3_open,
                "confirmed": confirmed,
            })
            
    return signals
