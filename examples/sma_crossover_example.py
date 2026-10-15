"""
Educational Step-by-Step Walkthrough: 20/50 SMA Crossover.
Shows beginners how moving averages and signals are calculated with exact numbers.

Key Learning Objective:
Understand how moving averages smooth price data, how crossover signals are triggered,
and why execution must happen on the NEXT bar to prevent look-ahead bias.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Ensure project root is available for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Windows console encoding safeguard
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.sma_strategy import SMACrossoverStrategy
from src.historical_data import HistoricalDataFetcher

def run_toy_demonstration():
    print("="*70)
    print("PART 1: STEP-BY-STEP MATH DEMO (Synthetic 75-Day Dataset)")
    print("="*70)
    print("We create 75 consecutive trading days:")
    print("  - Days 1 to 30: Flat price at 150")
    print("  - Days 31 to 55: Downtrend to 90 (Pulling 20-SMA below 50-SMA)")
    print("  - Days 56 to 75: Bullish reversal from 110 to 250 (Triggers Golden Cross)")
    print()

    dates = pd.date_range("2026-01-01", periods=75, freq="B")
    prices = [150.0] * 30 + [90.0] * 25 + [100.0 + i * 10 for i in range(20)]
    
    toy_df = pd.DataFrame({"Close": prices}, index=dates)
    
    strategy = SMACrossoverStrategy(fast_period=20, slow_period=50)
    result = strategy.generate_signals(toy_df)
    
    # Locate where the BUY signal fires
    buy_indices = result.index[result["Signal"] == "BUY"]
    if len(buy_indices) > 0:
        buy_pos = result.index.get_loc(buy_indices[0])
        sample = result.iloc[max(0, buy_pos - 3): min(len(result), buy_pos + 4)]
    else:
        sample = result.iloc[50:58]

    print("Notice what happens before, during, and after the Golden Cross:")
    print("-" * 75)
    print(f"{'Date':12s} | {'Close':7s} | {'20-SMA':8s} | {'50-SMA':8s} | {'Signal':6s} | {'Next Open Action':16s}")
    print("-" * 75)
    
    for dt, row in sample.iterrows():
        date_str = dt.strftime("%Y-%m-%d")
        close_str = f"{row['Close']:6.1f}"
        fast_str = f"{row['SMA_20']:6.2f}" if not pd.isna(row['SMA_20']) else "   NaN"
        slow_str = f"{row['SMA_50']:6.2f}" if not pd.isna(row['SMA_50']) else "   NaN"
        sig_str = row['Signal']
        exec_str = row['Execution_Next_Open']
        
        star = " <-- GOLDEN CROSS TRIGGER!" if sig_str == "BUY" else ""
        print(f"{date_str:12s} | {close_str:7s} | {fast_str:8s} | {slow_str:8s} | {sig_str:6s} | {exec_str:16s}{star}")
    print("-" * 75)
    print("""
Key Observations for Beginners:
1. Warm-up Period: Days 1 to 49 cannot compute a 50-day average, so 50-SMA is NaN.
2. The Trigger: On the day when 20-SMA (Fast) exceeds 50-SMA (Slow), 'BUY' fires.
3. The Next-Day Action:
   - On the crossover day, the signal is calculated at 03:30 PM (Close).
   - The trade is EXECUTED the following morning at 09:15 AM (Open).
   - This prevents 'look-ahead bias' because you cannot buy at yesterday's open
     using information that only became available at yesterday's close!
""")

def run_real_market_demonstration():
    print("="*70)
    print("PART 2: REAL NSE MARKET DATA DEMO (State Bank of India - SBIN.NS)")
    print("="*70)
    
    fetcher = HistoricalDataFetcher()
    try:
        df = fetcher.load_local_data("SBIN.NS")
    except Exception:
        print("Fetching SBIN.NS data directly...")
        df = fetcher.fetch_raw_daily_data("SBIN.NS", period="1y")
        df, _ = fetcher.validate_daily_data(df, "SBIN.NS")
        
    strategy = SMACrossoverStrategy(fast_period=20, slow_period=50)
    signals_df = strategy.generate_signals(df)
    
    crossovers = signals_df[signals_df["Signal"].isin(["BUY", "EXIT"])]
    
    print(f"Loaded {len(signals_df)} trading days for SBIN.")
    print(f"Detected {len(crossovers)} trend changes over the past year:\n")
    
    print(f"{'Date':12s} | {'Close':8s} | {'SMA_20':8s} | {'SMA_50':8s} | {'Signal':6s} | {'Target State':12s}")
    print("-" * 65)
    for dt, row in crossovers.iterrows():
        dt_str = dt.strftime("%Y-%m-%d") if hasattr(dt, 'strftime') else str(dt)[:10]
        pos_str = "HOLDING" if row['Target_Position'] == 1 else "CASH"
        icon = "[+]" if row['Signal'] == "BUY" else "[-]"
        print(f"{dt_str:12s} | INR {row['Close']:6.2f} | INR {row['SMA_20']:6.2f} | INR {row['SMA_50']:6.2f} | {row['Signal']:6s} | {pos_str:12s} {icon}")
    print("-" * 65)
    
    latest_report = strategy.evaluate_latest_bar(df)
    print("\nCURRENT STATUS REPORT:")
    print(f"  • Date:             {latest_report['date']}")
    print(f"  • SBIN Close Price: INR {latest_report['close_price']:.2f}")
    print(f"  • 20-Day SMA:       INR {latest_report['fast_sma']:.2f}")
    print(f"  • 50-Day SMA:       INR {latest_report['slow_sma']:.2f}")
    print(f"  • Signal Today:     {latest_report['signal_today']}")
    print(f"  • Current Stance:   {latest_report['target_position']}")
    print(f"  • Analysis:         {latest_report['explanation']}")
    print("="*70 + "\n")

if __name__ == "__main__":
    run_toy_demonstration()
    run_real_market_demonstration()
