"""
Optional Machine Learning Experiment for Indian Stock Market Trading Bot.
Uses scikit-learn for time-series classification with walk-forward validation.

KEY PRINCIPLES & SAFEGUARDS:
1. Strict Anti-Leakage: Features at Bar t use ONLY historical prices <= t.
2. Preprocessing Isolation: StandardScaler is fitted strictly on Train data, then applied to Test data.
3. No Random Splits: Uses Expanding-Window Walk-Forward Validation (time-series chronological folds).
4. Probability Calibration: Calibrates and audits predicted probabilities using Brier Score Loss.
5. Realistic Cost Modeling: Deducts standard Indian regulatory fees (₹20 brokerage, STT, GST, stamp duty, slippage).
6. Objective Benchmarking: Compares out-of-sample ML results against Buy & Hold and the 20/50 SMA strategy.

DISCLAIMER:
Machine learning models in financial markets are susceptible to regime shifts and low signal-to-noise ratios.
This module is strictly an experimental research tool. It does NOT guarantee predictive accuracy or profits,
and does NOT place live orders.
"""

import sys
from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional

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
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, brier_score_loss, roc_auc_score

from src.strategy import calculate_rsi
from src.sma_strategy import SMACrossoverStrategy
from src.ma_backtester import IndianMarketCostModel

class MLFeatureEngineer:
    """
    Constructs stationary, normalized technical features strictly from past data.
    Ensures zero forward-looking calculations in the feature space.
    """
    @staticmethod
    def construct_features_and_target(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
        """
        Extracts predictive features at Day t and aligns with Target at Day t+1.

        Feature Set (Information available at Day t Close):
        - ret_1d: 1-day percentage return (momentum)
        - ret_5d: 5-day percentage return (weekly momentum)
        - ret_20d: 20-day percentage return (monthly momentum)
        - sma_ratio: Ratio of 20-day SMA to 50-day SMA minus 1 (trend strength)
        - rsi_norm: 14-day RSI scaled between -1 and +1 (mean-reversion indicator)
        - vol_20d: 20-day rolling annualized volatility of daily returns
        - volume_ratio: 5-day average volume relative to 20-day average volume

        Target Variable (Realized on Day t+1):
        - Binary classification: 1 if Day t+1 session return (Close_{t+1} - Open_{t+1}) > 0, else 0.
        """
        if len(df) < 60:
            raise ValueError(f"Insufficient historical data ({len(df)} rows). Need at least 60 rows.")

        data = df.copy()

        # 1. Price Momentum Features (Backward-looking only)
        data["ret_1d"] = data["Close"].pct_change(1)
        data["ret_5d"] = data["Close"].pct_change(5)
        data["ret_20d"] = data["Close"].pct_change(20)

        # 2. Trend & Moving Average Features
        sma_20 = data["Close"].rolling(window=20, center=False).mean()
        sma_50 = data["Close"].rolling(window=50, center=False).mean()
        data["sma_ratio"] = (sma_20 / (sma_50 + 1e-9)) - 1.0

        # 3. Momentum Oscillator (RSI centered around zero: [-1.0 to +1.0])
        rsi_series = calculate_rsi(data["Close"], period=14)
        data["rsi_norm"] = (rsi_series - 50.0) / 50.0

        # 4. Volatility Feature (Rolling standard deviation of returns)
        data["vol_20d"] = data["ret_1d"].rolling(window=20, center=False).std()

        # 5. Volume Feature (Volume expansion / contraction)
        vol_5 = data["Volume"].rolling(window=5, center=False).mean()
        vol_20 = data["Volume"].rolling(window=20, center=False).mean()
        data["volume_ratio"] = (vol_5 / (vol_20 + 1e-9)) - 1.0

        # Target Variable: Next trading day's return from Open to Close
        # Prediction is made at Day t Close. Trade enters at Day t+1 Open and exits at Day t+1 Close.
        next_day_open = data["Open"].shift(-1)
        next_day_close = data["Close"].shift(-1)
        next_day_return = (next_day_close - next_day_open) / (next_day_open + 1e-9)

        data["target"] = (next_day_return > 0.0).astype(int)
        data["next_day_return"] = next_day_return

        feature_cols = ["ret_1d", "ret_5d", "ret_20d", "sma_ratio", "rsi_norm", "vol_20d", "volume_ratio"]

        # Drop the warm-up rows (first 50) and the final row (where next day's return is unknown)
        clean_data = data.dropna(subset=feature_cols + ["next_day_return"]).copy()

        X = clean_data[feature_cols].copy()
        y = clean_data["target"].copy()

        return X, y, clean_data

class WalkForwardValidator:
    """
    Implements Expanding-Window Walk-Forward Validation for time-series.
    Guarantees strict temporal separation with zero leakage.
    """
    def __init__(self, train_size: int = 250, test_size: int = 50):
        """
        - train_size: Number of trading bars for initial training (~1 year = ~250 trading days).
        - test_size: Number of trading bars for out-of-sample testing window (~2.5 months = ~50 days).
        """
        self.train_size = train_size
        self.test_size = test_size

    def generate_splits(self, n_samples: int) -> List[Tuple[np.ndarray, np.ndarray]]:
        """
        Generates expanding-window train/test index folds.
        Ensures max(train_indices) < min(test_indices).
        """
        splits = []
        current_train_end = self.train_size

        while current_train_end + self.test_size <= n_samples:
            train_idx = np.arange(0, current_train_end)
            test_idx = np.arange(current_train_end, current_train_end + self.test_size)
            splits.append((train_idx, test_idx))
            current_train_end += self.test_size

        return splits

class MLExperimentRunner:
    """
    Executes walk-forward evaluation, records out-of-sample predictions,
    calibrates probabilities, and benchmarks trading performance against
    the 20/50 SMA strategy and Buy & Hold.
    """
    def __init__(
        self,
        cost_model: Optional[IndianMarketCostModel] = None,
        train_window: int = 250,
        test_window: int = 50,
        probability_threshold: float = 0.52  # Slightly above 0.50 to cover friction
    ):
        self.cost_model = cost_model if cost_model is not None else IndianMarketCostModel()
        self.validator = WalkForwardValidator(train_size=train_window, test_size=test_window)
        self.prob_threshold = probability_threshold

    def run_experiment(self, df: pd.DataFrame, symbol: str = "STOCK") -> Dict[str, Any]:
        """
        Runs the full walk-forward classification and backtesting comparison.
        """
        X, y, clean_df = MLFeatureEngineer.construct_features_and_target(df)
        n_samples = len(X)
        splits = self.validator.generate_splits(n_samples)

        if len(splits) == 0:
            return {
                "error": f"Dataset too small ({n_samples} bars) for walk-forward validation with train_size={self.validator.train_size}."
            }

        all_y_true = []
        all_y_pred = []
        all_y_prob = []
        all_test_indices = []

        fold_reports = []

        for fold_idx, (train_idx, test_idx) in enumerate(splits):
            X_train, y_train = X.iloc[train_idx], y.iloc[train_idx]
            X_test, y_test = X.iloc[test_idx], y.iloc[test_idx]

            # ---------------------------------------------------------
            # Preprocessing Isolation: FIT ONLY ON TRAIN DATA
            # ---------------------------------------------------------
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)  # Strictly transform using train parameters

            # ---------------------------------------------------------
            # Model Training & Probability Calibration
            # ---------------------------------------------------------
            # Safeguard: Verify that training slice contains both positive and negative classes
            if len(np.unique(y_train)) < 2:
                # Fallback for degenerate slices with zero variation
                majority_class = int(y_train.iloc[0])
                test_probs = np.full(len(test_idx), 1.0 if majority_class == 1 else 0.0)
                test_preds = np.full(len(test_idx), majority_class)
            else:
                base_model = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
                # Use CalibratedClassifierCV with sigmoid (Platt Scaling) using 3-fold internal CV on train only
                calibrated_model = CalibratedClassifierCV(estimator=base_model, method="sigmoid", cv=3)
                calibrated_model.fit(X_train_scaled, y_train)

                # Predict calibrated probabilities on the unseen out-of-sample test window
                test_probs = calibrated_model.predict_proba(X_test_scaled)[:, 1]
                test_preds = (test_probs >= self.prob_threshold).astype(int)

            all_y_true.extend(y_test.values)
            all_y_pred.extend(test_preds)
            all_y_prob.extend(test_probs)
            all_test_indices.extend(test_idx)

            fold_acc = accuracy_score(y_test, test_preds)
            fold_brier = brier_score_loss(y_test, test_probs)
            fold_reports.append({
                "fold": fold_idx + 1,
                "train_bars": len(train_idx),
                "test_bars": len(test_idx),
                "accuracy": round(fold_acc * 100.0, 2),
                "brier_score": round(fold_brier, 4)
            })

        # -------------------------------------------------------------
        # Aggregate Out-of-Sample Classification Metrics
        # -------------------------------------------------------------
        y_true_arr = np.array(all_y_true)
        y_pred_arr = np.array(all_y_pred)
        y_prob_arr = np.array(all_y_prob)

        acc = accuracy_score(y_true_arr, y_pred_arr) * 100.0
        prec = precision_score(y_true_arr, y_pred_arr, zero_division=0) * 100.0
        rec = recall_score(y_true_arr, y_pred_arr, zero_division=0) * 100.0
        f1 = f1_score(y_true_arr, y_pred_arr, zero_division=0)
        brier = brier_score_loss(y_true_arr, y_prob_arr)
        try:
            auc = roc_auc_score(y_true_arr, y_prob_arr)
        except Exception:
            auc = 0.50

        # -------------------------------------------------------------
        # Simulate Out-of-Sample Trading (With Realistic Friction)
        # -------------------------------------------------------------
        test_df_slice = clean_df.iloc[all_test_indices].copy()
        test_df_slice["ML_Signal"] = y_pred_arr
        test_df_slice["ML_Prob"] = y_prob_arr

        initial_capital = 100000.0
        ml_capital = initial_capital
        ml_equity_curve = [initial_capital]
        ml_trades_count = 0
        ml_winning_trades = 0

        # We also benchmark Buy & Hold over the exact same test window
        start_price = float(test_df_slice["Open"].iloc[0])
        end_price = float(test_df_slice["Close"].iloc[-1])
        benchmark_return_pct = ((end_price - start_price) / start_price) * 100.0

        for idx in range(len(test_df_slice)):
            row = test_df_slice.iloc[idx]
            signal = row["ML_Signal"]
            open_p = float(row["Open"])
            close_p = float(row["Close"])

            if signal == 1:
                # Enter at open with slippage and fees, exit at close
                qty = int((ml_capital * 0.99) // (open_p * (1.0 + self.cost_model.slippage_pct)))
                if qty >= 1:
                    eff_buy, buy_fee, _ = self.cost_model.calculate_entry_costs(open_p, qty)
                    eff_sell, sell_fee, _ = self.cost_model.calculate_exit_costs(close_p, qty)
                    
                    gross_pnl = (eff_sell - eff_buy) * qty
                    net_pnl = gross_pnl - buy_fee - sell_fee
                    ml_capital += net_pnl
                    ml_trades_count += 1
                    if net_pnl > 0:
                        ml_winning_trades += 1

            ml_equity_curve.append(ml_capital)

        ml_net_return_pct = ((ml_capital - initial_capital) / initial_capital) * 100.0

        # Maximum Drawdown for ML Strategy
        equity_series = pd.Series(ml_equity_curve)
        peak = equity_series.cummax()
        dd = (equity_series - peak) / peak
        ml_max_dd_pct = abs(float(dd.min())) * 100.0

        # Rule-Based 20/50 SMA comparison over the same out-of-sample window
        sma_strat = SMACrossoverStrategy(fast_period=20, slow_period=50)
        # Evaluate SMA on the original continuous dataframe sliced to the test window dates
        sma_full_results = sma_strat.generate_signals(df)
        sma_test_slice = sma_full_results.loc[test_df_slice.index[0]: test_df_slice.index[-1]]
        
        from src.ma_backtester import MABacktester
        backtester = MABacktester(cost_model=self.cost_model, initial_capital=initial_capital)
        sma_backtest_res = backtester.run(sma_test_slice, period_name="Out-of-Sample Window")

        return {
            "symbol": symbol,
            "total_test_bars": len(all_test_indices),
            "test_start_date": str(test_df_slice.index[0])[:10],
            "test_end_date": str(test_df_slice.index[-1])[:10],
            "n_folds": len(splits),
            "fold_reports": fold_reports,
            # ML Model Diagnostics
            "accuracy_pct": round(acc, 2),
            "precision_pct": round(prec, 2),
            "recall_pct": round(rec, 2),
            "f1_score": round(f1, 4),
            "auc_roc": round(auc, 4),
            "brier_score_loss": round(brier, 4),
            # Comparative Trading Performance
            "ml_strategy_net_return_pct": round(ml_net_return_pct, 2),
            "ml_trades_count": ml_trades_count,
            "ml_win_rate_pct": round((ml_winning_trades / ml_trades_count * 100.0) if ml_trades_count > 0 else 0.0, 2),
            "ml_max_drawdown_pct": round(ml_max_dd_pct, 2),
            "benchmark_buy_and_hold_return_pct": round(benchmark_return_pct, 2),
            "sma_rule_based_net_return_pct": round(sma_backtest_res.get("net_return_pct", 0.0), 2),
            "sma_rule_based_max_dd_pct": round(sma_backtest_res.get("max_drawdown_pct", 0.0), 2)
        }

def print_ml_experiment_report(results: Dict[str, Any]):
    """Prints a clear, educational side-by-side benchmark report."""
    if "error" in results:
        print(f"[ERROR] {results['error']}")
        return

    symbol = results["symbol"]
    print("\n" + "="*80)
    print(f"SCIKIT-LEARN MACHINE LEARNING EXPERIMENT: {symbol}")
    print("="*80)
    print(f"Evaluation Mode:      Expanding-Window Walk-Forward Validation ({results['n_folds']} Folds)")
    print(f"Out-of-Sample Window: {results['test_start_date']} to {results['test_end_date']} ({results['total_test_bars']} Trading Days)")
    print("-" * 80)
    print("PART A: OUT-OF-SAMPLE CLASSIFICATION METRICS (Does the model have edge?)")
    print(f"  • Prediction Accuracy:   {results['accuracy_pct']}%  (Baseline random chance ~ 50%)")
    print(f"  • Precision (Positive):  {results['precision_pct']}%")
    print(f"  • Recall (Sensitivity):  {results['recall_pct']}%")
    print(f"  • F1 Score:              {results['f1_score']}")
    print(f"  • AUC-ROC:               {results['auc_roc']}  (0.50 = No skill; 1.0 = Perfect)")
    print(f"  • Brier Score Loss:      {results['brier_score_loss']} (Probability calibration: lower is better)")
    print("-" * 80)
    print("PART B: COMPARATIVE TRADING AUDIT (After Deducting Indian Taxes & Brokerage)")
    print(f"{'Strategy / Benchmark':35s} | {'Net Return (%)':16s} | {'Max Drawdown (%)':18s}")
    print("-" * 75)
    print(f"{'1. ML Logistic Classifier Strategy':35s} | {results['ml_strategy_net_return_pct']:+15.2f}% | {results['ml_max_drawdown_pct']:17.2f}%")
    print(f"{'2. Rule-Based 20/50 SMA Strategy':35s} | {results['sma_rule_based_net_return_pct']:+15.2f}% | {results['sma_rule_based_max_dd_pct']:17.2f}%")
    print(f"{'3. Buy & Hold Benchmark':35s} | {results['benchmark_buy_and_hold_return_pct']:+15.2f}% | {'N/A':18s}")
    print("-" * 80)
    print(f"ML Trade Count: {results['ml_trades_count']} trades | Win Rate: {results['ml_win_rate_pct']}%")
    print("="*80)
    print("""
KEY SCIKIT-LEARN EXPERIMENT INSIGHTS & LIMITATIONS:
1. Low Signal-to-Noise Ratio: Financial daily returns contain significant noise. An accuracy
   between 51% and 54% is typical for directional market forecasting.
2. Market Friction Drag: Even with >51% directional accuracy, frequent trading generates
   transaction costs (₹20 brokerage + STT + GST) that can erode gross profits.
3. Probability Calibration: The Brier score verifies whether a predicted 60% probability
   actually translates to a 60% empirical win frequency over time.
4. Non-Stationarity: Macroeconomic shifts and regulatory changes can alter feature relationships.
""")

if __name__ == "__main__":
    from src.historical_data import HistoricalDataFetcher
    fetcher = HistoricalDataFetcher()
    test_symbol = "INFY.NS"
    print(f"Loading 3-year historical data for {test_symbol}...")
    try:
        df = fetcher.load_local_data(test_symbol)
        runner = MLExperimentRunner()
        report = runner.run_experiment(df, symbol=test_symbol)
        print_ml_experiment_report(report)
    except Exception as e:
        print(f"ML Experiment error: {e}")
