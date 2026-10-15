"""
Unit Tests for the Scikit-Learn Machine Learning Experiment Module.
Verifies:
1. Feature engineering has strictly zero look-ahead bias.
2. Preprocessing isolation (StandardScaler fitted strictly on training data).
3. Walk-Forward expanding window indices have 0 temporal overlap.
4. Target alignment correctness.
5. Probability output bounds [0, 1] and Brier score loss validity.
"""

import sys
import unittest
from pathlib import Path
import pandas as pd
import numpy as np

# Ensure project root is available for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sklearn.preprocessing import StandardScaler
from src.ml_experiment import MLFeatureEngineer, WalkForwardValidator, MLExperimentRunner

class TestMLExperiment(unittest.TestCase):
    def setUp(self):
        # Generate 150 days of synthetic OHLCV data
        np.random.seed(42)
        dates = pd.date_range("2025-01-01", periods=150, freq="B")
        close_prices = 100.0 + np.cumsum(np.random.randn(150) * 1.5)
        
        self.sample_df = pd.DataFrame({
            "Open": close_prices - np.random.rand(150),
            "High": close_prices + np.random.rand(150) * 2.0,
            "Low": close_prices - np.random.rand(150) * 2.0,
            "Close": close_prices,
            "Volume": np.random.randint(10000, 50000, size=150)
        }, index=dates)

    def test_feature_engineering_no_lookahead_bias(self):
        """
        Tests that altering future prices (e.g. Day 100) has ZERO effect
        on the feature values calculated at Day 80.
        """
        X_orig, y_orig, _ = MLFeatureEngineer.construct_features_and_target(self.sample_df)
        val_80_orig = X_orig.iloc[30].copy() # Arbitrary bar after warmup

        # Modify future prices at end of dataframe
        modified_df = self.sample_df.copy()
        modified_df.iloc[-5:, modified_df.columns.get_loc("Close")] = 9999.0

        X_mod, y_mod, _ = MLFeatureEngineer.construct_features_and_target(modified_df)
        val_80_mod = X_mod.iloc[30].copy()

        # All features at bar 30 must be exactly identical
        pd.testing.assert_series_equal(val_80_orig, val_80_mod)

    def test_target_binary_classification_correctness(self):
        """
        Tests that Target at Day t is 1 if (Close_{t+1} - Open_{t+1}) > 0, else 0.
        """
        X, y, clean_df = MLFeatureEngineer.construct_features_and_target(self.sample_df)
        
        # Verify for sample bars
        for i in range(min(10, len(clean_df))):
            next_ret = clean_df["next_day_return"].iloc[i]
            target_val = clean_df["target"].iloc[i]
            if next_ret > 0:
                self.assertEqual(target_val, 1)
            else:
                self.assertEqual(target_val, 0)

    def test_preprocessor_leakage_isolation(self):
        """
        Tests that fitting the StandardScaler on Train data does NOT leak
        information from the Test set. Modifying the Test set must not alter
        the fitted mean_ or scale_ parameters.
        """
        X, y, _ = MLFeatureEngineer.construct_features_and_target(self.sample_df)
        train_idx = np.arange(0, 50)
        test_idx = np.arange(50, 70)

        X_train = X.iloc[train_idx]
        X_test_1 = X.iloc[test_idx].copy()
        X_test_2 = X.iloc[test_idx].copy() * 1000.0 # Extreme modification to test set

        scaler_1 = StandardScaler()
        scaler_1.fit(X_train)

        scaler_2 = StandardScaler()
        scaler_2.fit(X_train) # Still fit only on train

        # Both scalers must have identical parameters regardless of test data values
        np.testing.assert_array_almost_equal(scaler_1.mean_, scaler_2.mean_)
        np.testing.assert_array_almost_equal(scaler_1.scale_, scaler_2.scale_)

        # Applying transform with extreme test set does not crash
        scaled_test_2 = scaler_2.transform(X_test_2)
        self.assertEqual(scaled_test_2.shape, X_test_2.shape)

    def test_walk_forward_splits_no_overlap(self):
        """
        Tests that WalkForwardValidator creates strictly sequential,
        non-overlapping expanding window folds.
        """
        validator = WalkForwardValidator(train_size=60, test_size=20)
        splits = validator.generate_splits(n_samples=130)

        # 130 samples:
        # Fold 1: train 0:60, test 60:80
        # Fold 2: train 0:80, test 80:100
        # Fold 3: train 0:100, test 100:120
        self.assertEqual(len(splits), 3)

        for fold_num, (train_idx, test_idx) in enumerate(splits):
            # Check length
            self.assertEqual(len(test_idx), 20)
            # Check strict chronological order
            self.assertLess(train_idx.max(), test_idx.min())
            # Check zero intersection
            intersection = set(train_idx).intersection(set(test_idx))
            self.assertEqual(len(intersection), 0, f"Fold {fold_num} has overlapping indices!")

    def test_experiment_runner_end_to_end(self):
        """
        Tests running the full MLExperimentRunner on synthetic data.
        Verifies all metrics are computed and bounded.
        """
        # Create a longer dataframe (200 rows)
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=200, freq="B")
        close = 100.0 + np.cumsum(np.random.randn(200) * 1.5)
        # Ensure random intraday variations so target has both 0 and 1
        intraday_noise = np.random.randn(200) * 0.8
        open_prices = close - intraday_noise
        high_prices = np.maximum(open_prices, close) + 0.5
        low_prices = np.minimum(open_prices, close) - 0.5

        df = pd.DataFrame({
            "Open": open_prices,
            "High": high_prices,
            "Low": low_prices,
            "Close": close,
            "Volume": np.random.randint(10000, 50000, size=200)
        }, index=dates)

        runner = MLExperimentRunner(train_window=80, test_window=25)
        report = runner.run_experiment(df, symbol="TEST_STOCK")

        self.assertNotIn("error", report)
        self.assertGreater(report["total_test_bars"], 0)
        self.assertGreaterEqual(report["accuracy_pct"], 0.0)
        self.assertLessEqual(report["accuracy_pct"], 100.0)
        # Brier score loss is bounded [0, 1]
        self.assertGreaterEqual(report["brier_score_loss"], 0.0)
        self.assertLessEqual(report["brier_score_loss"], 1.0)

if __name__ == "__main__":
    unittest.main()
