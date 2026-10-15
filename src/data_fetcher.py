"""
Data Fetcher Module for Indian Stocks.
Uses Yahoo Finance (yfinance) for 100% free historical and live price fetching.
NSE stocks use the '.NS' suffix (e.g., TATAMOTORS.NS).
"""

import yfinance as yf
import pandas as pd

def fetch_historical_candles(symbol: str, period: str = "30d", interval: str = "5m") -> pd.DataFrame:
    """
    Downloads historical OHLCV candle data for a given NSE stock.
    - period: '5d', '30d', '60d' (for 5m interval, yfinance supports up to 60 days)
    - interval: '1m', '5m', '15m', '1d'
    """
    try:
        # Standardize symbol for NSE
        clean_symbol = symbol if symbol.endswith(".NS") else f"{symbol}.NS"
        ticker = yf.Ticker(clean_symbol)
        df = ticker.history(period=period, interval=interval)
        
        if df.empty:
            print(f"[WARN] No data returned for {clean_symbol}")
            return pd.DataFrame()

        # Clean column names and drop empty values
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        
        # Localize/convert to IST if tz-aware
        if df.index.tz is not None:
            df.index = df.index.tz_convert("Asia/Kolkata")
            
        return df
    except Exception as e:
        print(f"[ERROR] Failed to fetch data for {symbol}: {e}")
        return pd.DataFrame()

def fetch_current_ltp(symbol: str) -> float:
    """
    Gets the latest traded price (LTP) for a symbol.
    """
    try:
        clean_symbol = symbol if symbol.endswith(".NS") else f"{symbol}.NS"
        ticker = yf.Ticker(clean_symbol)
        # Fast quote retrieval
        fast_info = getattr(ticker, "fast_info", None)
        if fast_info and "last_price" in fast_info and fast_info["last_price"]:
            return float(fast_info["last_price"])
            
        # Fallback to recent candle
        df = ticker.history(period="1d", interval="1m")
        if not df.empty:
            return float(df["Close"].iloc[-1])
        return 0.0
    except Exception as e:
        print(f"[ERROR] Error fetching LTP for {symbol}: {e}")
        return 0.0

if __name__ == "__main__":
    test_symbol = "TATAMOTORS.NS"
    print(f"Testing data fetcher with {test_symbol}...")
    ltp = fetch_current_ltp(test_symbol)
    print(f"Latest price of {test_symbol}: ₹{ltp:.2f}")
    hist = fetch_historical_candles(test_symbol, period="2d", interval="5m")
    print(f"Fetched {len(hist)} candles:")
    print(hist.tail(3))
