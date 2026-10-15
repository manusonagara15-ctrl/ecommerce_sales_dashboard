"""
Trading Strategy Module: 9/21 EMA Crossover with RSI Filter.
Implemented using pure pandas (Zero C-compiler dependencies, 100% Windows compatible).
Simple, transparent, and proven trend-following baseline.
"""

import pandas as pd
import numpy as np

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculates Relative Strength Index (RSI) using pure pandas."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0.0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean()
    
    rs = gain / (loss + 1e-9)  # Avoid division by zero
    rsi = 100 - (100 / (1 + rs))
    return rsi

def generate_indicators(df: pd.DataFrame, fast_ema: int = 9, slow_ema: int = 21, rsi_period: int = 14) -> pd.DataFrame:
    """
    Computes technical indicators on OHLCV dataframe.
    """
    df = df.copy()
    df["EMA_Fast"] = df["Close"].ewm(span=fast_ema, adjust=False).mean()
    df["EMA_Slow"] = df["Close"].ewm(span=slow_ema, adjust=False).mean()
    df["RSI"] = calculate_rsi(df["Close"], period=rsi_period)
    return df

def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Generates actionable signals:
    - BUY (1): Fast EMA crosses above Slow EMA AND RSI > 50 (Bullish Momentum)
    - EXIT/SELL (-1): Fast EMA crosses below Slow EMA OR RSI < 40
    - HOLD (0): No new signal
    """
    if "EMA_Fast" not in df.columns or "EMA_Slow" not in df.columns:
        df = generate_indicators(df)
        
    df["Signal"] = 0
    
    # Previous candle values to detect exact crossover
    prev_fast = df["EMA_Fast"].shift(1)
    prev_slow = df["EMA_Slow"].shift(1)
    
    # Golden Crossover (Fast crosses above Slow)
    bullish_crossover = (prev_fast <= prev_slow) & (df["EMA_Fast"] > df["EMA_Slow"])
    bullish_filter = df["RSI"] > 50.0
    buy_condition = bullish_crossover & bullish_filter
    
    # Death Crossover (Fast crosses below Slow)
    bearish_crossover = (prev_fast >= prev_slow) & (df["EMA_Fast"] < df["EMA_Slow"])
    exit_condition = bearish_crossover | (df["RSI"] < 38.0)
    
    df.loc[buy_condition, "Signal"] = 1   # BUY
    df.loc[exit_condition, "Signal"] = -1 # SELL / EXIT
    
    return df

def evaluate_latest_signal(df: pd.DataFrame) -> tuple[str, float]:
    """
    Evaluates the most recent completed candle to check if an action should be triggered.
    Returns: (Action: 'BUY' | 'SELL' | 'HOLD', current_close_price)
    """
    if len(df) < 30:
        return "HOLD", 0.0
        
    df_signals = generate_signals(df)
    latest_candle = df_signals.iloc[-1]
    last_price = float(latest_candle["Close"])
    signal = int(latest_candle["Signal"])
    
    if signal == 1:
        return "BUY", last_price
    elif signal == -1:
        return "SELL", last_price
    return "HOLD", last_price
