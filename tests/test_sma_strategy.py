"""
Unit Tests for the Educational 20/50 SMA Crossover Strategy.
Verifies moving average calculations, crossover event triggers,
warm-up NaN handling, and strict prevention of look-ahead bias.
"""

import sys
import unittest
from pathlib import Path
import pandas as pd
import numpy as np

# Ensure project root is available for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.sma_strategy import SMACrossoverStrategy

class TestSMACrossoverStrategy(unittest.TestCase):
    def setUp(self):
        self.strategy = SMACrossoverStrategy(fast_period=20, slow_period=50)

    def test_invalid_parameters_raise_error(self):
        """Tests that setting fast period >= slow period raises ValueError."""
        with self.assertRaises(ValueError):
            SMACrossoverStrategy(fast_period=50, slow_period=20)
        with self.assertRaises(ValueError):
            SMACrossoverStrategy(fast_period=20, slow_period=20)

    def test_missing_close_column_raises_error(self):
        """Tests that DataFrame without 'Close' raises ValueError."""
        df = pd.DataFrame({"Open": [100.0, 101.0]})
        with self.assertRaises(ValueError):
            self.strategy.calculate_indicators(df)

    def test_moving_average_math_and_warmup(self):
        """
        Tests that:
        1. Days 0 to 18 have NaN for SMA_20.
        2. Days 0 to 48 have NaN for SMA_50.
        3. Day 19 has the exact arithmetic mean of the first 20 Close prices.
        4. Day 49 has the exact arithmetic mean of the first 50 Close prices.
        """
        prices = list(range(1, 61)) # 1, 2, 3, ..., 60
        dates = pd.date_range("2026-01-01", periods=60, freq="B")
        df = pd.DataFrame({"Close": prices}, index=dates)

        result = self.strategy.calculate_indicators(df)

        # Check warm-up NaNs
        self.assertTrue(result["SMA_20"].iloc[:19].isna().all())
        self.assertFalse(pd.isna(result["SMA_20"].iloc[19]))
        self.assertTrue(result["SMA_50"].iloc[:49].isna().all())
        self.assertFalse(pd.isna(result["SMA_50"].iloc[49]))

        # Check arithmetic mean on Day 19 (first 20 numbers: 1 to 20, mean = 10.5)
        expected_20 = sum(range(1, 21)) / 20.0
        self.assertAlmostEqual(result["SMA_20"].iloc[19], expected_20)

        # Check arithmetic mean on Day 49 (first 50 numbers: 1 to 50, mean = 25.5)
        expected_50 = sum(range(1, 51)) / 50.0
        self.assertAlmostEqual(result["SMA_50"].iloc[49], expected_50)

    def test_golden_cross_and_subsequent_hold(self):
        """
        Tests that when Fast crosses above Slow after warm-up:
        1. Exactly ONE 'BUY' signal is generated on the crossover bar.
        2. Subsequent bars where Fast remains above Slow generate 'HOLD'.
        3. Target_Position becomes 1 (Long).
        """
        dates = pd.date_range("2026-01-01", periods=75, freq="B")
        # 30 days at 200, 25 days at 100 (ensures Fast < Slow at Day 50), then strong rally
        prices = [200.0] * 30 + [100.0] * 25 + [120.0 + i * 15 for i in range(20)]
        df = pd.DataFrame({"Close": prices}, index=dates)

        result = self.strategy.generate_signals(df)

        # Find the row where BUY occurred
        buy_rows = result[result["Signal"] == "BUY"]
        self.assertEqual(len(buy_rows), 1, "Expected exactly 1 BUY signal on the crossover")
        
        buy_idx = result.index.get_loc(buy_rows.index[0])
        
        # Prior bar was HOLD (not BUY)
        self.assertEqual(result["Signal"].iloc[buy_idx - 1], "HOLD")
        # Immediate next bar is HOLD (maintaining position, not re-buying)
        self.assertEqual(result["Signal"].iloc[buy_idx + 1], "HOLD")
        # Target position is 1 after the BUY signal
        self.assertEqual(result["Target_Position"].iloc[buy_idx], 1)
        self.assertEqual(result["Target_Position"].iloc[buy_idx + 1], 1)

    def test_death_cross_and_exit(self):
        """
        Tests that when Fast crosses below Slow:
        1. Exactly ONE 'EXIT' signal is generated on the crossover bar.
        2. Target_Position drops back to 0 (Cash).
        """
        dates = pd.date_range("2026-01-01", periods=75, freq="B")
        # 45 flat at 100, 15 rally at 150 (triggers Golden Cross), 15 sharp crash at 50 (triggers Death Cross)
        prices = [100.0] * 45 + [160.0] * 15 + [40.0] * 15
        df = pd.DataFrame({"Close": prices}, index=dates)

        result = self.strategy.generate_signals(df)

        exit_rows = result[result["Signal"] == "EXIT"]
        self.assertEqual(len(exit_rows), 1, "Expected exactly 1 EXIT signal on the bearish crossover")

        exit_idx = result.index.get_loc(exit_rows.index[0])
        # Position drops to 0 on exit
        self.assertEqual(result["Target_Position"].iloc[exit_idx], 0)

    def test_lookahead_bias_prevention(self):
        """
        Rigorous Look-Ahead Test:
        Modifying or appending future price data on Day 55 MUST NOT alter
        the moving average or signal generated on Day 50.
        """
        dates = pd.date_range("2026-01-01", periods=60, freq="B")
        prices = [100.0] * 45 + [105.0 + i * 2 for i in range(15)]
        df_original = pd.DataFrame({"Close": prices}, index=dates)

        result_orig = self.strategy.generate_signals(df_original)
        day_50_fast_orig = result_orig["SMA_20"].iloc[50]
        day_50_slow_orig = result_orig["SMA_50"].iloc[50]
        day_50_sig_orig = result_orig["Signal"].iloc[50]

        # Scenario B: Modify future days (55 to 59) to an extreme shock (e.g. 10,000)
        df_modified = df_original.copy()
        df_modified.loc[dates[55:], "Close"] = 10000.0

        result_mod = self.strategy.generate_signals(df_modified)
        day_50_fast_mod = result_mod["SMA_20"].iloc[50]
        day_50_slow_mod = result_mod["SMA_50"].iloc[50]
        day_50_sig_mod = result_mod["Signal"].iloc[50]

        # The values on Day 50 must be 100% IDENTICAL
        self.assertEqual(day_50_fast_orig, day_50_fast_mod)
        self.assertEqual(day_50_slow_orig, day_50_slow_mod)
        self.assertEqual(day_50_sig_orig, day_50_sig_mod)

    def test_next_day_execution_alignment(self):
        """
        Tests that 'Execution_Next_Open' on Day t+1 precisely equals
        'Signal' on Day t, guaranteeing that backtests never assume
        same-bar open execution on a close-generated signal.
        """
        dates = pd.date_range("2026-01-01", periods=60, freq="B")
        prices = [100.0] * 45 + [110.0 + i * 3 for i in range(15)]
        df = pd.DataFrame({"Close": prices}, index=dates)

        result = self.strategy.generate_signals(df)

        # For every bar i from 1 to end, Execution_Next_Open[i] == Signal[i-1]
        for i in range(1, len(result)):
            self.assertEqual(
                result["Execution_Next_Open"].iloc[i],
                result["Signal"].iloc[i - 1]
            )

if __name__ == "__main__":
    unittest.main()
