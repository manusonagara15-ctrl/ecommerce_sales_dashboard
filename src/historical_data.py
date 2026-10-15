"""
Historical Market Data Module for Indian Equities (NSE).
Fetches, validates, and stores daily OHLCV market data locally as CSV.

Key Principles:
1. Strict Validation: Validates dates, logical OHLC relationships, duplicates, and non-positive prices.
2. No Price Invention: Never forward-fills, back-fills, or interpolates missing prices.
3. No Future Data: Eliminates any data points timestamped in the future.
4. Robust Error Handling: Symbol-level failures do not halt the entire pipeline.
"""

import os
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Tuple, Dict, List

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
import yfinance as yf
import config

class DataValidationError(Exception):
    """Raised when data fails critical integrity checks."""
    pass

class HistoricalDataFetcher:
    """
    Fetches and rigorously validates daily OHLCV data for Indian stocks.
    Saves clean, verified datasets to local CSV files.
    """
    def __init__(self, data_dir: str = "data/historical", watchlist: Optional[List[str]] = None):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.watchlist = watchlist if watchlist is not None else getattr(config, "WATCHLIST", [
            "SBIN.NS", "ITC.NS", "INFY.NS", "ICICIBANK.NS", "RELIANCE.NS"
        ])

    @staticmethod
    def format_symbol(symbol: str) -> str:
        """
        Normalizes symbols for Indian National Stock Exchange (NSE).
        Yahoo Finance requires the '.NS' suffix (e.g., 'RELIANCE' -> 'RELIANCE.NS').
        """
        clean = symbol.strip().upper()
        if not clean.endswith(".NS") and not clean.endswith(".BO"):
            clean = f"{clean}.NS"
        return clean

    @staticmethod
    def get_clean_filename_symbol(symbol: str) -> str:
        """Strips exchange suffix for clean file naming (e.g., 'RELIANCE.NS' -> 'RELIANCE')."""
        return symbol.strip().upper().replace(".NS", "").replace(".BO", "")

    def fetch_raw_daily_data(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: Optional[str] = "1y"
    ) -> pd.DataFrame:
        """
        Downloads raw daily candles via yfinance.
        start_date/end_date format: 'YYYY-MM-DD'
        If start_date is None, uses 'period' (default '1y' for 1 year).
        """
        formatted_symbol = self.format_symbol(symbol)
        try:
            ticker = yf.Ticker(formatted_symbol)
            if start_date:
                df = ticker.history(start=start_date, end=end_date, interval="1d", auto_adjust=False)
            else:
                df = ticker.history(period=period, interval="1d", auto_adjust=False)

            if df is None or df.empty:
                print(f"[WARN] No raw data returned by provider for {formatted_symbol}")
                return pd.DataFrame()

            return df
        except Exception as e:
            print(f"[ERROR] Provider request failed for {formatted_symbol}: {e}")
            return pd.DataFrame()

    def validate_daily_data(self, df: pd.DataFrame, symbol: str) -> Tuple[pd.DataFrame, Dict]:
        """
        Applies strict financial data validation rules:
        1. Date Validation:
           - DatetimeIndex conversion and timezone normalization.
           - Sorts chronologically ascending.
           - Checks and removes duplicate dates (retaining the first).
           - Checks for future dates (drops any date > today).
        2. Missing & Corrupted Values:
           - Rejects and drops rows with NaN, null, or non-finite values in OHLCV.
           - NEVER invents missing prices (no forward-fill, back-fill, or interpolation).
        3. Price Integrity (OHLC logic):
           - Prices must be strictly positive (> 0).
           - High must be the highest: High >= Low, High >= Open, High >= Close.
           - Low must be the lowest: Low <= Open, Low <= Close.
        4. Volume Integrity:
           - Volume must be >= 0.
        5. Data Frequency & Gaps:
           - Reports date range, total rows, and trading day continuity.
        """
        report = {
            "symbol": symbol,
            "raw_rows": len(df),
            "valid_rows": 0,
            "dropped_duplicates": 0,
            "dropped_missing": 0,
            "dropped_future_dates": 0,
            "dropped_invalid_prices": 0,
            "is_valid": False,
            "errors": []
        }

        if df.empty:
            report["errors"].append("Dataset is empty.")
            return pd.DataFrame(), report

        data = df.copy()

        # -------------------------------------------------------------
        # 1. Date & Index Validation
        # -------------------------------------------------------------
        if not isinstance(data.index, pd.DatetimeIndex):
            try:
                data.index = pd.to_datetime(data.index)
            except Exception as e:
                report["errors"].append(f"Failed to parse datetime index: {e}")
                return pd.DataFrame(), report

        # Normalize timezone to naive dates (YYYY-MM-DD) for clean daily comparisons
        if data.index.tz is not None:
            data.index = data.index.tz_convert("Asia/Kolkata").tz_localize(None)
        
        # Normalize time component to midnight for daily consistency
        data.index = data.index.normalize()
        data.index.name = "Date"

        # Check and remove future dates
        today_midnight = pd.Timestamp(date.today())
        future_mask = data.index > today_midnight
        if future_mask.any():
            future_count = int(future_mask.sum())
            report["dropped_future_dates"] = future_count
            data = data[~future_mask]

        # Check and handle duplicate dates
        initial_count = len(data)
        data = data[~data.index.duplicated(keep="first")]
        report["dropped_duplicates"] = initial_count - len(data)

        # Ensure chronological ascending order
        data = data.sort_index(ascending=True)

        # -------------------------------------------------------------
        # 2. Required Columns Validation
        # -------------------------------------------------------------
        required_cols = ["Open", "High", "Low", "Close", "Volume"]
        missing_cols = [c for c in required_cols if c not in data.columns]
        if missing_cols:
            report["errors"].append(f"Missing required OHLCV columns: {missing_cols}")
            return pd.DataFrame(), report

        # Keep standard OHLCV columns (plus Adj Close if present)
        cols_to_keep = [c for c in ["Open", "High", "Low", "Close", "Adj Close", "Volume"] if c in data.columns]
        data = data[cols_to_keep]

        # -------------------------------------------------------------
        # 3. Missing & Non-Finite Values (Strict: DO NOT INVENT PRICES)
        # -------------------------------------------------------------
        # Check for NaN / Nulls in any OHLCV column
        null_mask = data[required_cols].isna().any(axis=1) | np.isinf(data[required_cols]).any(axis=1)
        if null_mask.any():
            null_count = int(null_mask.sum())
            report["dropped_missing"] = null_count
            # NEVER invent missing prices: Drop the corrupted rows
            data = data[~null_mask]

        if data.empty:
            report["errors"].append("No valid rows remaining after removing nulls/invalids.")
            return pd.DataFrame(), report

        # -------------------------------------------------------------
        # 4. Price & OHLC Logical Integrity
        # -------------------------------------------------------------
        # Prices must be strictly positive (> 0)
        positive_prices = (
            (data["Open"] > 0) &
            (data["High"] > 0) &
            (data["Low"] > 0) &
            (data["Close"] > 0)
        )
        
        # Volume must be non-negative (>= 0)
        valid_volume = data["Volume"] >= 0

        # Mathematical OHLC relationships
        # High must be greater than or equal to Open, Low, and Close
        high_valid = (data["High"] >= data["Low"]) & (data["High"] >= data["Open"]) & (data["High"] >= data["Close"])
        # Low must be less than or equal to Open, High, and Close
        low_valid = (data["Low"] <= data["Open"]) & (data["Low"] <= data["Close"])

        integrity_mask = positive_prices & valid_volume & high_valid & low_valid
        
        invalid_rows = (~integrity_mask).sum()
        if invalid_rows > 0:
            report["dropped_invalid_prices"] = int(invalid_rows)
            data = data[integrity_mask]

        if data.empty:
            report["errors"].append("All rows failed OHLC logical integrity checks.")
            return pd.DataFrame(), report

        # -------------------------------------------------------------
        # 5. Summary & Verification Metrics
        # -------------------------------------------------------------
        report["valid_rows"] = len(data)
        report["is_valid"] = len(data) > 0
        report["start_date"] = data.index[0].strftime("%Y-%m-%d")
        report["end_date"] = data.index[-1].strftime("%Y-%m-%d")
        report["latest_close"] = float(round(data["Close"].iloc[-1], 2))

        # Check for trading day continuity (detect gaps > 5 calendar days)
        date_diffs = data.index.to_series().diff().dt.days
        large_gaps = date_diffs[date_diffs > 5]
        report["large_gaps_count"] = len(large_gaps)
        if len(large_gaps) > 0:
            report["largest_gap_days"] = int(large_gaps.max())

        return data, report

    def save_to_csv(self, df: pd.DataFrame, symbol: str) -> Path:
        """
        Saves validated dataframe to a clean CSV file.
        Path format: 'data/historical/<SYMBOL>_daily.csv'
        """
        clean_name = self.get_clean_filename_symbol(symbol)
        file_path = self.data_dir / f"{clean_name}_daily.csv"
        
        # Format index cleanly as YYYY-MM-DD
        df_to_save = df.copy()
        df_to_save.index = df_to_save.index.strftime("%Y-%m-%d")
        df_to_save.to_csv(file_path, index=True, index_label="Date")
        return file_path

    def fetch_and_save(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: Optional[str] = "1y"
    ) -> Tuple[Optional[Path], Dict]:
        """
        End-to-end pipeline for a single stock:
        Fetch -> Validate -> Save -> Return Path and Report.
        """
        formatted_symbol = self.format_symbol(symbol)
        print(f"[DATA] Processing {formatted_symbol}...")
        
        raw_df = self.fetch_raw_daily_data(formatted_symbol, start_date=start_date, end_date=end_date, period=period)
        if raw_df.empty:
            return None, {"symbol": formatted_symbol, "is_valid": False, "error": "No data returned from source."}

        validated_df, report = self.validate_daily_data(raw_df, formatted_symbol)
        if not report["is_valid"]:
            print(f"[DATA ERROR] Validation failed for {formatted_symbol}: {report['errors']}")
            return None, report

        csv_path = self.save_to_csv(validated_df, formatted_symbol)
        report["csv_path"] = str(csv_path)
        print(f"  -> Verified {report['valid_rows']} daily candles ({report['start_date']} to {report['end_date']})")
        print(f"  -> Saved to: {csv_path.name} (Latest Close: INR {report['latest_close']:.2f})")
        return csv_path, report

    def fetch_and_save_watchlist(
        self,
        symbols: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: Optional[str] = "1y"
    ) -> Dict[str, Dict]:
        """
        Fetches and validates data for the entire watchlist.
        Returns a dictionary of execution reports per symbol.
        """
        target_symbols = symbols if symbols is not None else self.watchlist
        print(f"\n=======================================================")
        print(f"HISTORICAL MARKET DATA PIPELINE (NSE DAILY OHLCV)")
        print(f"Watchlist: {target_symbols}")
        print(f"Output Directory: {self.data_dir.resolve()}")
        print(f"=======================================================")

        summary = {}
        for symbol in target_symbols:
            try:
                path, report = self.fetch_and_save(symbol, start_date=start_date, end_date=end_date, period=period)
                summary[symbol] = report
            except Exception as e:
                print(f"[DATA ERROR] Unexpected failure on {symbol}: {e}")
                summary[symbol] = {"symbol": symbol, "is_valid": False, "error": str(e)}

        success_count = sum(1 for r in summary.values() if r.get("is_valid", False))
        print("\n=======================================================")
        print(f"PIPELINE COMPLETED: {success_count}/{len(target_symbols)} symbols validated & saved.")
        print(f"=======================================================\n")
        return summary

    def load_local_data(self, symbol: str) -> pd.DataFrame:
        """
        Helper to load previously validated CSV data from disk.
        """
        clean_name = self.get_clean_filename_symbol(symbol)
        file_path = self.data_dir / f"{clean_name}_daily.csv"
        if not file_path.exists():
            raise FileNotFoundError(f"Validated data file not found at {file_path}")
        
        df = pd.read_csv(file_path, parse_dates=["Date"], index_col="Date")
        return df

if __name__ == "__main__":
    fetcher = HistoricalDataFetcher()
    fetcher.fetch_and_save_watchlist()
