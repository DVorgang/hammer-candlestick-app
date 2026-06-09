import pandas as pd
import numpy as np
import logging
from pattern_engine import download_stock_data, add_indicators, identify_setup_candle

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def run_backtest(ticker, period="2y"):
    """
    Executes a historical backtest of the 3-Day Candlestick Sentinel strategy on a ticker.
    Guarantees ZERO lookahead bias by strictly following the 3-day validation timeline:
    - Day 1 (Setup Candle at i): Geometric match.
    - Day 2 (Confirmation Candle at i+1): Close confirmations.
    - Day 3 (Execution/Entry at i+2): Executable at Open. Stop/target limits calculated.
    - Day 3 to 11 (Max 10 trading bars): Exit on stop loss, profit target, or close of 10th bar.
    """
    df = download_stock_data(ticker, period=period)
    if df.empty or len(df) < 205:
        logging.warning(f"Not enough data to backtest {ticker}.")
        return {
            "ticker": ticker,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "timeouts": 0,
            "win_rate": 0.0,
            "avg_return": 0.0,
            "trades": []
        }
    
    df = add_indicators(df)
    trades = []
    
    # We must start past row 200 (warmup) and stop where we still have room to run a 10-day trade
    # Day 1 index is i. Day 2 is i+1. Day 3 (entry) is i+2. Max hold is 10 bars (ends at i+11).
    # So max index for Day 1 is len(df) - 12
    end_idx = len(df) - 12
    
    i = 200
    while i <= end_idx:
        is_pattern, pattern_type, score = identify_setup_candle(df, i)
        if not is_pattern:
            i += 1
            continue
            
        # Day 2 Confirmation check
        day1_high = df['High'].iloc[i]
        day1_low = df['Low'].iloc[i]
        day1_close = df['Close'].iloc[i]
        day1_date = df['Date'].iloc[i]
        
        day2_close = df['Close'].iloc[i+1]
        day2_date = df['Date'].iloc[i+1]
        
        confirmed = False
        if pattern_type == "Hammer":
            if day2_close > day1_high:
                confirmed = True
        elif pattern_type == "Hanging Man":
            if day2_close < day1_low:
                confirmed = True
                
        if not confirmed:
            i += 1 # Not confirmed, move to next candle
            continue
            
        # Day 3 Execution
        entry_idx = i + 2
        entry_date = df['Date'].iloc[entry_idx]
        entry_price = df['Open'].iloc[entry_idx]
        
        # Stop Loss
        epsilon = 0.01
        if pattern_type == "Hammer":
            stop_loss = day1_low - epsilon
            risk = entry_price - stop_loss
            if risk <= 0:
                # Gap down past stop loss before execution
                i += 1
                continue
            profit_target = entry_price + (2.0 * risk)
        else: # Hanging Man
            stop_loss = day1_high + epsilon
            risk = stop_loss - entry_price
            if risk <= 0:
                # Gap up past stop loss before execution
                i += 1
                continue
            profit_target = entry_price - (2.0 * risk)
            
        # Trade Loop: Check from entry_idx (Day 3 / Bar 1) to entry_idx + 9 (Bar 10)
        exit_price = None
        exit_date = None
        exit_reason = None
        
        for trade_bar_idx in range(entry_idx, entry_idx + 10):
            if trade_bar_idx >= len(df):
                break
                
            bar_high = df['High'].iloc[trade_bar_idx]
            bar_low = df['Low'].iloc[trade_bar_idx]
            bar_close = df['Close'].iloc[trade_bar_idx]
            bar_date = df['Date'].iloc[trade_bar_idx]
            
            # Check for Hammer (Long Position)
            if pattern_type == "Hammer":
                # Check Stop Loss first (conservative)
                if bar_low <= stop_loss:
                    exit_price = stop_loss
                    exit_date = bar_date
                    exit_reason = "Stop Loss"
                    break
                elif bar_high >= profit_target:
                    exit_price = profit_target
                    exit_date = bar_date
                    exit_reason = "Take Profit"
                    break
            # Check for Hanging Man (Short Position)
            else:
                if bar_high >= stop_loss:
                    exit_price = stop_loss
                    exit_date = bar_date
                    exit_reason = "Stop Loss"
                    break
                elif bar_low <= profit_target:
                    exit_price = profit_target
                    exit_date = bar_date
                    exit_reason = "Take Profit"
                    break
                    
        # Time-based Exit at close of 10th bar
        if exit_price is None:
            final_bar_idx = min(entry_idx + 9, len(df) - 1)
            exit_price = df['Close'].iloc[final_bar_idx]
            exit_date = df['Date'].iloc[final_bar_idx]
            exit_reason = "Time Exit"
            
        # Calculate Returns
        if pattern_type == "Hammer":
            trade_return = (exit_price - entry_price) / entry_price
        else: # Hanging Man (Short)
            trade_return = (entry_price - exit_price) / entry_price
            
        trades.append({
            "day1_date": day1_date.strftime("%Y-%m-%d"),
            "pattern_type": pattern_type,
            "confidence_score": score,
            "entry_date": entry_date.strftime("%Y-%m-%d"),
            "entry_price": float(entry_price),
            "stop_loss": float(stop_loss),
            "profit_target": float(profit_target),
            "exit_date": exit_date.strftime("%Y-%m-%d"),
            "exit_price": float(exit_price),
            "exit_reason": exit_reason,
            "return": float(trade_return)
        })
        
        # Move index forward. Since the lifecycle lasts up to 10 trading bars,
        # we can jump forward past the entry day to look for the next distinct setup,
        # or just increment by 1. Standard approach is incrementing by 1 (allowing overlapping setups),
        # but to keep it simple and clean, let's step by 1.
        i += 1
        
    # Summarize results
    total_trades = len(trades)
    wins = sum(1 for t in trades if t["return"] > 0)
    losses = sum(1 for t in trades if t["return"] < 0)
    timeouts = sum(1 for t in trades if t["exit_reason"] == "Time Exit")
    
    win_rate = (wins / total_trades) if total_trades > 0 else 0.0
    avg_return = np.mean([t["return"] for t in trades]) if total_trades > 0 else 0.0
    
    return {
        "ticker": ticker,
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "timeouts": timeouts,
        "win_rate": float(win_rate),
        "avg_return": float(avg_return),
        "trades": trades
    }
