"""
Unit Tests for Historical Market Data Module.
Tests validation rules, OHLC logical constraints, duplicate handling,
missing value rejection (no price invention), and CSV persistence.
"""

import os
import sys
import unittest
from datetime import datetime, date, timedelta
from pathlib import Path
import pandas as pd
import numpy as np

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.historical_data import HistoricalDataFetcher

class TestHistoricalDataFetcher(unittest.TestCase):
    def setUp(self):
        # Use an isolated temporary test directory
        self.test_dir = Path("data/test_historical")
        self.fetcher = HistoricalDataFetcher(data_dir=str(self.test_dir))

    def tearDown(self):
        # Clean up any test files created
        if self.test_dir.exists():
            for f in self.test_dir.glob("*"):
                try:
                    f.unlink()
                except Exception:
                    pass
            try:
                self.test_dir.rmdir()
            except Exception:
                pass

    def test_symbol_formatting(self):
        """Tests standardizing NSE stock tickers with .NS suffix."""
        self.assertEqual(HistoricalDataFetcher.format_symbol("reliance"), "RELIANCE.NS")
        self.assertEqual(HistoricalDataFetcher.format_symbol("SBIN.NS"), "SBIN.NS")
        self.assertEqual(HistoricalDataFetcher.format_symbol("infy"), "INFY.NS")
        self.assertEqual(HistoricalDataFetcher.get_clean_filename_symbol("RELIANCE.NS"), "RELIANCE")

    def test_valid_data_passes(self):
        """Tests that a clean, legitimate OHLCV dataframe passes validation without drops."""
        dates = pd.date_range(end=date.today(), periods=5, freq="B")
        df = pd.DataFrame({
            "Open": [100.0, 102.0, 101.0, 103.0, 105.0],
            "High": [105.0, 106.0, 104.0, 107.0, 108.0],
            "Low": [98.0, 100.0, 99.0, 101.0, 104.0],
            "Close": [103.0, 101.0, 103.0, 106.0, 107.0],
            "Volume": [10000, 15000, 12000, 18000, 20000]
        }, index=dates)

        validated, report = self.fetcher.validate_daily_data(df, "TEST.NS")
        self.assertTrue(report["is_valid"])
        self.assertEqual(len(validated), 5)
        self.assertEqual(report["dropped_duplicates"], 0)
        self.assertEqual(report["dropped_missing"], 0)
        self.assertEqual(report["dropped_invalid_prices"], 0)

    def test_ohlc_logical_integrity_rejection(self):
        """
        Tests that invalid OHLC relationships (e.g. High < Low, High < Open, Low > Close)
        are flagged and dropped.
        """
        dates = pd.date_range(end=date.today(), periods=4, freq="B")
        df = pd.DataFrame({
            "Open": [100.0, 100.0, 100.0, 100.0],
            "High": [105.0, 95.0, 105.0, 105.0],    # Row 1: High (95) < Low (98) -> INVALID!
            "Low": [95.0, 98.0, 102.0, 95.0],       # Row 2: Low (102) > Open (100) -> INVALID!
            "Close": [102.0, 96.0, 103.0, -10.0],   # Row 3: Close (-10) negative -> INVALID!
            "Volume": [1000, 1000, 1000, 1000]
        }, index=dates)

        validated, report = self.fetcher.validate_daily_data(df, "TEST.NS")
        # Only Row 0 is valid; rows 1, 2, 3 should be dropped
        self.assertEqual(len(validated), 1)
        self.assertEqual(report["dropped_invalid_prices"], 3)

    def test_no_price_invention_on_missing_values(self):
        """
        Crucial requirement: Missing prices must NEVER be invented (no ffill/bfill).
        Corrupted rows with NaNs must be removed, not synthesized.
        """
        dates = pd.date_range(end=date.today(), periods=3, freq="B")
        df = pd.DataFrame({
            "Open": [100.0, np.nan, 102.0],
            "High": [105.0, 106.0, 107.0],
            "Low": [95.0, 96.0, 97.0],
            "Close": [102.0, 103.0, 104.0],
            "Volume": [1000, 1000, 1000]
        }, index=dates)

        validated, report = self.fetcher.validate_daily_data(df, "TEST.NS")
        self.assertEqual(len(validated), 2)
        self.assertEqual(report["dropped_missing"], 1)
        # Ensure row 1 (the NaN row) is dropped and not forward-filled
        self.assertNotIn(dates[1], validated.index)

    def test_duplicate_dates_and_sorting(self):
        """Tests that duplicate dates are deduplicated and output is sorted chronologically."""
        d1 = pd.Timestamp("2026-01-05")
        d2 = pd.Timestamp("2026-01-02")
        d3 = pd.Timestamp("2026-01-02") # Duplicate!

        df = pd.DataFrame({
            "Open": [105.0, 100.0, 100.0],
            "High": [110.0, 105.0, 105.0],
            "Low": [100.0, 95.0, 95.0],
            "Close": [108.0, 102.0, 102.0],
            "Volume": [2000, 1000, 1000]
        }, index=[d1, d2, d3])

        validated, report = self.fetcher.validate_daily_data(df, "TEST.NS")
        self.assertEqual(len(validated), 2)
        self.assertEqual(report["dropped_duplicates"], 1)
        # Verify chronological sorting (2026-01-02 comes before 2026-01-05)
        self.assertTrue(validated.index[0] < validated.index[1])

    def test_future_dates_rejection(self):
        """Tests that any rows with timestamps in the future are strictly eliminated."""
        past_date = pd.Timestamp(date.today() - timedelta(days=2))
        future_date = pd.Timestamp(date.today() + timedelta(days=5))

        df = pd.DataFrame({
            "Open": [100.0, 105.0],
            "High": [105.0, 110.0],
            "Low": [95.0, 100.0],
            "Close": [102.0, 107.0],
            "Volume": [1000, 1000]
        }, index=[past_date, future_date])

        validated, report = self.fetcher.validate_daily_data(df, "TEST.NS")
        self.assertEqual(len(validated), 1)
        self.assertEqual(report["dropped_future_dates"], 1)
        self.assertEqual(validated.index[0], past_date)

    def test_csv_persistence_roundtrip(self):
        """Tests saving validated data to CSV and reading it back."""
        dates = pd.date_range(end=date.today(), periods=3, freq="B")
        df = pd.DataFrame({
            "Open": [100.0, 101.0, 102.0],
            "High": [105.0, 106.0, 107.0],
            "Low": [95.0, 96.0, 97.0],
            "Close": [103.0, 104.0, 105.0],
            "Volume": [1000, 1000, 1000]
        }, index=dates)

        saved_path = self.fetcher.save_to_csv(df, "INFY.NS")
        self.assertTrue(saved_path.exists())
        self.assertEqual(saved_path.name, "INFY_daily.csv")

        # Load back
        loaded = self.fetcher.load_local_data("INFY.NS")
        self.assertEqual(len(loaded), 3)
        self.assertIn("Close", loaded.columns)
        self.assertEqual(float(loaded["Close"].iloc[-1]), 105.0)

if __name__ == "__main__":
    unittest.main()
