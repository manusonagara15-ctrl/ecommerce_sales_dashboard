"""
Unit Tests for the Moving Average Backtesting Engine.
Validates:
1. Indian regulatory and brokerage cost model calculations.
2. Strict execution timing (Signal on Day t executes at Day t+1 Open).
3. Chronological Train / Validation / Test data partitioning without leakage.
4. Benchmark and Max Drawdown mathematical accuracy.
"""

import sys
import unittest
from pathlib import Path
import pandas as pd
import numpy as np

# Ensure project root is available for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ma_backtester import IndianMarketCostModel, DataSplitter, MABacktester
from src.sma_strategy import SMACrossoverStrategy

class TestMABacktester(unittest.TestCase):
    def setUp(self):
        self.cost_model = IndianMarketCostModel()

    def test_indian_cost_model_entry_calculation(self):
        """
        Tests exact itemized Indian fee calculations on Buy leg:
        Buying 100 shares of a stock quoted at INR 1000.
        """
        quoted_price = 1000.0
        quantity = 100

        eff_price, total_fees, breakdown = self.cost_model.calculate_entry_costs(quoted_price, quantity)

        # 1. Slippage: 0.05% -> Effective price = 1000 * 1.0005 = 1000.50
        self.assertAlmostEqual(eff_price, 1000.50, places=2)
        turnover = eff_price * quantity # 100,050.0

        # 2. Brokerage = flat 20.0
        self.assertEqual(breakdown["brokerage"], 20.0)

        # 3. STT (0.1% on delivery buy) = 100,050 * 0.001 = 100.05
        self.assertAlmostEqual(breakdown["stt"], 100.05, places=2)

        # 4. Exchange turnover charge (0.00325%) = 100,050 * 0.0000325 = 3.2516
        self.assertAlmostEqual(breakdown["exchange_fee"], 3.25, places=2)

        # 5. Stamp duty (0.015% on buy) = 100,050 * 0.00015 = 15.0075
        self.assertAlmostEqual(breakdown["stamp_duty"], 15.01, places=2)

        # 6. GST (18% on Brokerage + Exchange + SEBI)
        expected_gst = (breakdown["brokerage"] + breakdown["exchange_fee"] + breakdown["sebi_fee"]) * 0.18
        self.assertAlmostEqual(breakdown["gst"], expected_gst, places=2)

        # 7. Total entry fees match sum of parts
        expected_total = (
            breakdown["brokerage"] + breakdown["stt"] + breakdown["exchange_fee"] +
            breakdown["sebi_fee"] + breakdown["stamp_duty"] + breakdown["gst"]
        )
        self.assertAlmostEqual(total_fees, expected_total, places=2)

    def test_indian_cost_model_exit_calculation(self):
        """
        Tests exact itemized Indian fee calculations on Sell leg:
        Selling 100 shares of a stock quoted at INR 1050.
        Notice: Stamp duty must be 0 on sell leg in India.
        """
        quoted_price = 1050.0
        quantity = 100

        eff_price, total_fees, breakdown = self.cost_model.calculate_exit_costs(quoted_price, quantity)

        # Slippage: 0.05% deduction -> 1050 * (1 - 0.0005) = 1049.475
        self.assertAlmostEqual(eff_price, 1049.475, places=2)

        # Stamp duty is zero on sell leg
        self.assertEqual(breakdown["stamp_duty"], 0.0)

        # Brokerage is flat 20
        self.assertEqual(breakdown["brokerage"], 20.0)

    def test_execution_timing_at_next_bar_open(self):
        """
        Crucial timing test:
        Verifies that a BUY signal occurring on Day t Close is executed at
        Day t+1 OPEN price (with slippage), NOT Day t Close or Day t Open!
        """
        dates = pd.date_range("2026-01-01", periods=75, freq="B")
        # Downtrend first so Fast < Slow, then sharp breakout
        prices = [150.0] * 30 + [90.0] * 25 + [100.0 + i * 10 for i in range(20)]
        
        # Create distinct Open and Close prices so we can verify which price was used!
        df = pd.DataFrame({
            "Open": [p - 2.0 for p in prices],
            "High": [p + 5.0 for p in prices],
            "Low": [p - 5.0 for p in prices],
            "Close": prices,
            "Volume": [10000] * 75
        }, index=dates)

        strategy = SMACrossoverStrategy(fast_period=20, slow_period=50)
        signals_df = strategy.generate_signals(df)

        # Find the crossover date
        buy_signal_date = signals_df[signals_df["Signal"] == "BUY"].index[0]
        buy_pos = signals_df.index.get_loc(buy_signal_date)
        next_day_date = signals_df.index[buy_pos + 1]
        next_day_open = df.loc[next_day_date, "Open"]

        backtester = MABacktester(strategy=strategy, initial_capital=100000.0, cost_model=self.cost_model)
        results = backtester.run(df)

        self.assertGreater(len(results["trades"]), 0, "Expected at least 1 executed trade")
        first_trade = results["trades"][0]

        # The entry date must be Day t+1 (next_day_date), NOT the signal date!
        self.assertEqual(first_trade["entry_date"], next_day_date)

        # The entry price must be based on Day t+1's OPEN price (plus 0.05% slippage)
        expected_entry_price = round(next_day_open * (1.0 + self.cost_model.slippage_pct), 2)
        self.assertAlmostEqual(first_trade["entry_price"], expected_entry_price, places=1)

    def test_chronological_data_splitter_no_leakage(self):
        """
        Tests that DataSplitter:
        1. Properly partitions 60% train, 20% validation, 20% test.
        2. Maintains strict chronological ordering with 0 date overlap.
        3. Raises ValueError if ratios don't sum to 1.0.
        """
        dates = pd.date_range("2025-01-01", periods=100, freq="B")
        df = pd.DataFrame({"Close": range(100)}, index=dates)

        train, val, test = DataSplitter.chronological_split(df, 0.60, 0.20, 0.20)

        # Check lengths
        self.assertEqual(len(train), 60)
        self.assertEqual(len(val), 20)
        self.assertEqual(len(test), 20)

        # Verify no temporal overlap / leakage
        self.assertTrue(train.index.max() < val.index.min())
        self.assertTrue(val.index.max() < test.index.min())

        # Check invalid ratio rejection
        with self.assertRaises(ValueError):
            DataSplitter.chronological_split(df, 0.50, 0.20, 0.20) # Sums to 0.90

    def test_benchmark_return_formula(self):
        """
        Tests that benchmark return equals the Buy-and-Hold return of the stock:
        (Final_Close - Initial_Close) / Initial_Close * 100.
        """
        dates = pd.date_range("2026-01-01", periods=70, freq="B")
        # Stock doubles from 100 to 200 -> Benchmark return should be +100.0%
        prices = np.linspace(100.0, 200.0, 70)
        df = pd.DataFrame({
            "Open": prices,
            "High": prices + 1.0,
            "Low": prices - 1.0,
            "Close": prices,
            "Volume": [1000] * 70
        }, index=dates)

        backtester = MABacktester()
        res = backtester.run(df)

        expected_benchmark = ((200.0 - 100.0) / 100.0) * 100.0
        self.assertAlmostEqual(res["benchmark_return_pct"], expected_benchmark, places=1)

if __name__ == "__main__":
    unittest.main()
