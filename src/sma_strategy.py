"""
Educational 20-Day / 50-Day Simple Moving Average (SMA) Crossover Strategy.
Designed for the Indian Stock Market (NSE/BSE).

DISCLAIMER:
This strategy is implemented solely for educational and illustrative purposes.
It is NOT financial advice, and there is NO claim or guarantee that this strategy
is profitable. In real-world markets, simple moving average crossovers frequently
suffer from "whipsaws" (false signals and repeated small losses during sideways/range-bound
markets). It does NOT place real orders.

Look-Ahead Bias Prevention:
1. Indicators use strictly backward-looking rolling windows (center=False).
2. A signal generated on Day t uses ONLY prices available up to Day t's market close.
3. Realistic execution occurs at the OPEN of Day t+1.
"""

import sys
from pathlib import Path
from typing import Tuple, Dict, Any

# Ensure project root is available for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Windows console encoding safeguard
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import pandas as pd
import numpy as np

class SMACrossoverStrategy:
    """
    Transparent, beginner-friendly 20/50 SMA Crossover Strategy.

    How it works in plain language:
    - 20-Day SMA (Fast): The average closing price of the last 20 trading days.
      Reacts faster to recent market movements.
    - 50-Day SMA (Slow): The average closing price of the last 50 trading days.
      Shows the broader, medium-term trend.
    - Golden Cross (BUY): When the 20-day average climbs ABOVE the 50-day average.
      Indicates that recent momentum is turning bullish compared to the medium-term.
    - Death Cross (EXIT): When the 20-day average falls BELOW the 50-day average.
      Indicates that recent momentum is weakening.
    - HOLD: When no crossover occurred today (maintain your current state: either stay
      in your existing position or stay in cash).
    """

    def __init__(self, fast_period: int = 20, slow_period: int = 50):
        if fast_period >= slow_period:
            raise ValueError(f"fast_period ({fast_period}) must be less than slow_period ({slow_period}).")
        self.fast_period = fast_period
        self.slow_period = slow_period

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates the 20-day and 50-day Simple Moving Averages.

        Strict Look-Ahead Bias Prevention:
        - `rolling(window=N, center=False)` ensures day t's average uses ONLY
          prices from days (t - N + 1) through t. No future prices are ever accessed.
        - The first (slow_period - 1) days will naturally be NaN (warm-up period),
          because 50 historical days are required to calculate a 50-day average.
        """
        if df.empty or "Close" not in df.columns:
            raise ValueError("Input DataFrame must contain a 'Close' price column.")

        data = df.copy()

        # Calculate Simple Moving Averages
        # Formally: SMA_t = (Close_t + Close_{t-1} + ... + Close_{t-N+1}) / N
        data[f"SMA_{self.fast_period}"] = (
            data["Close"].rolling(window=self.fast_period, center=False).mean()
        )
        data[f"SMA_{self.slow_period}"] = (
            data["Close"].rolling(window=self.slow_period, center=False).mean()
        )

        return data

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generates BUY, EXIT, and HOLD signals based strictly on crossover events.

        Signal Definitions:
        - 'BUY': On Day t, Fast SMA crossed ABOVE Slow SMA.
                 (Fast[t] > Slow[t] AND Fast[t-1] <= Slow[t-1])
        - 'EXIT': On Day t, Fast SMA crossed BELOW Slow SMA.
                  (Fast[t] < Slow[t] AND Fast[t-1] >= Slow[t-1])
        - 'HOLD': No crossover event occurred on Day t.

        Timing & Real-World Execution:
        - Day t's signal is generated at market close (03:30 PM IST) once Day t's
          Close price is finalized.
        - Because you cannot trade at Day t's Close before it exists, any real trade
          is executed at Day t+1's OPEN (09:15 AM IST).
        - We record 'Signal' on Day t, and 'Next_Day_Action' for Day t+1 execution.
        """
        fast_col = f"SMA_{self.fast_period}"
        slow_col = f"SMA_{self.slow_period}"

        # Ensure indicators exist
        if fast_col not in df.columns or slow_col not in df.columns:
            data = self.calculate_indicators(df)
        else:
            data = df.copy()

        # Previous day's values (Day t - 1) to identify the exact crossover moment
        data["Prev_Fast"] = data[fast_col].shift(1)
        data["Prev_Slow"] = data[slow_col].shift(1)

        # Initialize all signals to HOLD
        data["Signal"] = "HOLD"

        # Golden Cross Condition: Fast was <= Slow yesterday, but is now > Slow today
        golden_cross = (data["Prev_Fast"] <= data["Prev_Slow"]) & (data[fast_col] > data[slow_col])

        # Death Cross Condition: Fast was >= Slow yesterday, but is now < Slow today
        death_cross = (data["Prev_Fast"] >= data["Prev_Slow"]) & (data[fast_col] < data[slow_col])

        data.loc[golden_cross, "Signal"] = "BUY"
        data.loc[death_cross, "Signal"] = "EXIT"

        # During the warm-up period (first 50 bars), moving averages are NaN
        # We explicitly ensure no false signals are generated during warm-up
        warmup_mask = data[fast_col].isna() | data[slow_col].isna() | data["Prev_Slow"].isna()
        data.loc[warmup_mask, "Signal"] = "HOLD"

        # Position tracking (1 = Holding Stock, 0 = In Cash)
        # Position is entered at Open of Day t+1 following a BUY signal on Day t
        # Position is exited at Open of Day t+1 following an EXIT signal on Day t
        data["Target_Position"] = 0
        current_pos = 0
        positions = []
        for sig in data["Signal"]:
            if sig == "BUY":
                current_pos = 1
            elif sig == "EXIT":
                current_pos = 0
            positions.append(current_pos)
        
        data["Target_Position"] = positions

        # Execution column: what action should be executed at tomorrow's open
        # This completely eliminates look-ahead ambiguity for beginners:
        data["Execution_Next_Open"] = data["Signal"].shift(1).fillna("HOLD")

        # Clean up temporary helper columns
        data = data.drop(columns=["Prev_Fast", "Prev_Slow"])

        return data

    def evaluate_latest_bar(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Evaluates the most recent completed trading day to explain the current market state.
        Returns a friendly dictionary report.
        """
        if len(df) < self.slow_period + 1:
            return {
                "status": "WARMUP",
                "message": f"Need at least {self.slow_period + 1} days of data to compute 50-day SMA. Provided: {len(df)}."
            }

        analyzed = self.generate_signals(df)
        latest_bar = analyzed.iloc[-1]
        prev_bar = analyzed.iloc[-2]

        fast_val = float(latest_bar[f"SMA_{self.fast_period}"])
        slow_val = float(latest_bar[f"SMA_{self.slow_period}"])
        close_val = float(latest_bar["Close"])
        signal = str(latest_bar["Signal"])
        current_position = int(latest_bar["Target_Position"])

        if signal == "BUY":
            reason = (f"Golden Cross! 20-Day SMA ({fast_val:.2f}) climbed above "
                      f"50-Day SMA ({slow_val:.2f}). Bullish momentum detected.")
        elif signal == "EXIT":
            reason = (f"Death Cross! 20-Day SMA ({fast_val:.2f}) fell below "
                      f"50-Day SMA ({slow_val:.2f}). Bearish weakness detected.")
        else:
            if fast_val > slow_val:
                reason = (f"20-Day SMA ({fast_val:.2f}) is above 50-Day SMA ({slow_val:.2f}), "
                          f"but crossover happened previously. Existing state maintained.")
            else:
                reason = (f"20-Day SMA ({fast_val:.2f}) is below 50-Day SMA ({slow_val:.2f}). "
                          f"Market is in a downtrend/sideways. Sitting in cash.")

        return {
            "date": str(latest_bar.name),
            "close_price": close_val,
            "fast_sma": round(fast_val, 2),
            "slow_sma": round(slow_val, 2),
            "signal_today": signal,
            "target_position": "LONG (Holding Stock)" if current_position == 1 else "CASH (Flat)",
            "explanation": reason
        }

if __name__ == "__main__":
    from src.historical_data import HistoricalDataFetcher
    fetcher = HistoricalDataFetcher()
    
    print("\n" + "="*65)
    print("EDUCATIONAL 20/50 SMA CROSSOVER STRATEGY DEMO")
    print("="*65)
    
    # Load previously verified local NSE data for Reliance
    symbol = "RELIANCE.NS"
    try:
        df = fetcher.load_local_data(symbol)
        strategy = SMACrossoverStrategy(fast_period=20, slow_period=50)
        result_df = strategy.generate_signals(df)
        
        # Filter rows where an actual crossover occurred
        crossovers = result_df[result_df["Signal"].isin(["BUY", "EXIT"])]
        
        print(f"\nAnalyzed {len(result_df)} daily candles for {symbol}.")
        print(f"Total Crossover Signals Detected: {len(crossovers)}")
        print("\nRecent Crossover Signals Table:")
        print(crossovers[["Close", "SMA_20", "SMA_50", "Signal", "Target_Position"]].tail(10))
        
        latest = strategy.evaluate_latest_bar(df)
        print("\nLatest Completed Day Analysis:")
        print(f"  • Date:            {latest['date']}")
        print(f"  • Close Price:     INR {latest['close_price']}")
        print(f"  • 20-Day SMA:      INR {latest['fast_sma']}")
        print(f"  • 50-Day SMA:      INR {latest['slow_sma']}")
        print(f"  • Signal Generated: {latest['signal_today']}")
        print(f"  • Position State:  {latest['target_position']}")
        print(f"  • Explanation:     {latest['explanation']}")
        print("="*65 + "\n")
        
    except Exception as e:
        print(f"Could not load data for {symbol}: {e}")
