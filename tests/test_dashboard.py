"""
Unit Tests for Dashboard Analytics & Security Safeguards.
Verifies:
1. Data freshness classification (Fresh, Stale, Historical EOD).
2. Portfolio P&L and equity calculation accuracy.
3. Risk alert triggers (Kill-switch, exposure cap, daily loss limit).
4. Sensitive secret scrubbing (ensuring no API keys/tokens leak into UI).
"""

import sys
import unittest
from datetime import datetime, date, timedelta
from pathlib import Path
import pandas as pd

# Ensure project root is available for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.dashboard_data import (
    check_data_freshness,
    compute_portfolio_metrics,
    evaluate_risk_limits,
    scrub_sensitive_secrets
)

class TestDashboardData(unittest.TestCase):
    def setUp(self):
        self.ref_now = datetime(2026, 10, 15, 12, 0, 0)

    def test_check_data_freshness_fresh_and_stale(self):
        """Tests identifying fresh vs stale vs historical data."""
        # 1. Fresh quote (45s old <= 120s)
        fresh_time = self.ref_now - timedelta(seconds=45)
        res_fresh = check_data_freshness(fresh_time, current_time=self.ref_now, max_age_seconds=120.0)
        self.assertEqual(res_fresh["status"], "FRESH")
        self.assertEqual(res_fresh["badge_color"], "green")

        # 2. Stale quote (150s old > 120s)
        stale_time = self.ref_now - timedelta(seconds=150)
        res_stale = check_data_freshness(stale_time, current_time=self.ref_now, max_age_seconds=120.0)
        self.assertEqual(res_stale["status"], "STALE")
        self.assertEqual(res_stale["badge_color"], "red")
        self.assertIn("Stale Data Warning", res_stale["message"])

        # 3. Historical End-of-Day candle (midnight timestamp)
        eod_time = datetime(2026, 10, 14, 0, 0, 0)
        res_eod = check_data_freshness(eod_time, current_time=self.ref_now)
        self.assertEqual(res_eod["status"], "HISTORICAL_EOD")
        self.assertEqual(res_eod["badge_color"], "blue")

    def test_compute_portfolio_metrics(self):
        """Tests virtual equity and unrealized P&L calculations."""
        cash = 40000.0
        open_positions = {
            "INFY.NS": {"quantity": 10, "entry_price": 1000.0, "stop_loss": 990.0, "take_profit": 1020.0},
            "ITC.NS": {"quantity": 20, "entry_price": 250.0, "stop_loss": 247.5, "take_profit": 255.0}
        }
        current_prices = {
            "INFY.NS": 1050.0,  # +50 * 10 = +500
            "ITC.NS": 240.0     # -10 * 20 = -200
        }
        realized_pnl = 150.0

        metrics = compute_portfolio_metrics(cash, open_positions, current_prices, realized_pnl)

        # Total market value = (10 * 1050) + (20 * 240) = 10,500 + 4,800 = 15,300
        self.assertEqual(metrics["total_market_value"], 15300.0)
        # Total unrealized P&L = +500 - 200 = +300
        self.assertEqual(metrics["total_unrealized_pnl"], 300.0)
        # Total equity = 40,000 (cash) + 15,300 (mkt val) = 55,300
        self.assertEqual(metrics["total_equity"], 55300.0)
        # Net total P&L = 150 (realized) + 300 (unrealized) = 450
        self.assertEqual(metrics["net_total_pnl"], 450.0)

    def test_evaluate_risk_limits_alerts(self):
        """Tests that critical and warning alerts fire appropriately."""
        # Scenario 1: Kill-Switch active
        alerts_ks = evaluate_risk_limits(
            current_equity=50000.0, current_exposure=5000.0, open_positions_count=1,
            net_daily_pnl=0.0, is_kill_switch_active=True
        )
        self.assertTrue(any(a["level"] == "CRITICAL" and "KILL-SWITCH" in a["message"] for a in alerts_ks))

        # Scenario 2: Exposure limit breach (INR 16,000 > INR 15,000 cap)
        alerts_exp = evaluate_risk_limits(
            current_equity=50000.0, current_exposure=16000.0, open_positions_count=2,
            net_daily_pnl=0.0, is_kill_switch_active=False, max_exposure=15000.0
        )
        self.assertTrue(any(a["level"] == "CRITICAL" and "exposure breached" in a["message"] for a in alerts_exp))

        # Scenario 3: Daily loss approaching threshold (85% consumed)
        alerts_loss = evaluate_risk_limits(
            current_equity=50000.0, current_exposure=5000.0, open_positions_count=1,
            net_daily_pnl=-1300.0, is_kill_switch_active=False, max_daily_loss=1500.0
        )
        self.assertTrue(any(a["level"] == "WARNING" and "Daily loss approaching" in a["message"] for a in alerts_loss))

    def test_scrub_sensitive_secrets(self):
        """Tests that confidential API keys, passwords, and tokens are redacted."""
        raw_text = "Connecting with API_KEY = 'secret_abc_123' and ACCESS_TOKEN='xyz_token_456'."
        cleaned = scrub_sensitive_secrets(raw_text)

        self.assertNotIn("secret_abc_123", cleaned)
        self.assertNotIn("xyz_token_456", cleaned)
        self.assertIn("[REDACTED_API_KEY]", cleaned)
        self.assertIn("[REDACTED_ACCESS_TOKEN]", cleaned)

if __name__ == "__main__":
    unittest.main()
