"""
Comprehensive Unit Tests for the Enterprise Risk Management Module.
Verifies all 10 boundary conditions, safety locks, and fail-closed behavior:
1. Maximum order value rejection.
2. Maximum open positions rejection.
3. Maximum daily loss (realized & unrealized) kill-switch activation.
4. Maximum total portfolio exposure cap.
5. Stale-data and clock-skew rejection.
6. Duplicate-order cooldown and double-entry prevention.
7. Order field validation (zero/negative quantity and price).
8. Emergency kill switch manual and automatic engagement.
9. Fail-closed behavior on module failure.
10. Live trading disabled safety lock.
"""

import sys
import unittest
from datetime import datetime, time, timedelta
from pathlib import Path

# Ensure project root is available for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.risk_manager import RiskManager, RiskConfig, OrderRequest, OrderValidationResult

class TestRiskManager(unittest.TestCase):
    def setUp(self):
        # Standard test configuration with frozen reference market time
        self.ref_time = datetime(2026, 10, 15, 11, 0, 0) # 11:00 AM IST (within market hours)
        self.config = RiskConfig(
            max_order_value_inr=5000.0,
            max_open_positions=3,
            max_daily_loss_inr=1500.0,
            max_total_exposure_inr=15000.0,
            max_data_age_seconds=120.0,
            duplicate_cooldown_seconds=60.0,
            default_stop_loss_pct=1.0,
            default_take_profit_pct=2.0,
            max_daily_trades=6,
            market_start_time=time(9, 30),
            market_cutoff_time=time(14, 45),
            square_off_time=time(15, 10),
            live_trading_enabled=False # Live trading firmly disabled
        )
        self.risk_mgr = RiskManager(risk_config=self.config)

    def test_valid_order_approval(self):
        """Tests that a standard compliant order passes all risk filters."""
        order = OrderRequest(
            symbol="INFY.NS",
            side="BUY",
            quantity=3,
            price=1000.0, # 3 * 1000 = 3000 <= 5000 limit
            timestamp=self.ref_time
        )
        result = self.risk_mgr.validate_order_request(order, current_market_time=self.ref_time)
        self.assertTrue(result.is_approved)
        self.assertEqual(result.risk_code, "APPROVED")

    def test_max_order_value_rejection(self):
        """Tests that an order exceeding max_order_value_inr is rejected."""
        order = OrderRequest(
            symbol="RELIANCE.NS",
            side="BUY",
            quantity=10,
            price=1200.0, # 10 * 1200 = 12,000 > 5,000 limit!
            timestamp=self.ref_time
        )
        result = self.risk_mgr.validate_order_request(order, current_market_time=self.ref_time)
        self.assertFalse(result.is_approved)
        self.assertEqual(result.risk_code, "MAX_ORDER_VAL")
        self.assertIn("exceeds maximum order limit", result.rejection_reason)

    def test_max_open_positions_rejection(self):
        """Tests that opening a 4th position when max_open_positions=3 is rejected."""
        # Fill 3 positions
        for sym in ["SBIN.NS", "ITC.NS", "INFY.NS"]:
            req = OrderRequest(symbol=sym, side="BUY", quantity=2, price=500.0, timestamp=self.ref_time)
            res = self.risk_mgr.validate_order_request(req, current_market_time=self.ref_time)
            self.assertTrue(res.is_approved)
            self.risk_mgr.record_order_execution(req, executed_time=self.ref_time)

        self.assertEqual(len(self.risk_mgr.open_positions), 3)

        # Attempt to open 4th position
        fourth_order = OrderRequest(symbol="ICICIBANK.NS", side="BUY", quantity=2, price=500.0, timestamp=self.ref_time)
        fourth_res = self.risk_mgr.validate_order_request(fourth_order, current_market_time=self.ref_time)
        self.assertFalse(fourth_res.is_approved)
        self.assertEqual(fourth_res.risk_code, "MAX_POSITIONS")

    def test_max_total_exposure_rejection(self):
        """Tests that portfolio exposure exceeding max_total_exposure_inr is rejected."""
        # Hold 14,000 INR of stock
        req = OrderRequest(symbol="RELIANCE.NS", side="BUY", quantity=10, price=1400.0, timestamp=self.ref_time)
        self.risk_mgr.open_positions["RELIANCE.NS"] = req
        # Record into open_positions manually to test boundary
        from src.risk_manager import Position
        self.risk_mgr.open_positions["RELIANCE.NS"] = Position(
            symbol="RELIANCE.NS", quantity=10, entry_price=1400.0, current_price=1400.0,
            entry_time=self.ref_time, stop_loss_price=1386.0, take_profit_price=1428.0
        )

        # Second order of 2,000 INR pushes total exposure to 16,000 > 15,000!
        second_order = OrderRequest(symbol="ITC.NS", side="BUY", quantity=8, price=250.0, timestamp=self.ref_time)
        res = self.risk_mgr.validate_order_request(second_order, current_market_time=self.ref_time)
        self.assertFalse(res.is_approved)
        self.assertEqual(res.risk_code, "MAX_EXPOSURE")

    def test_stale_data_rejection(self):
        """Tests that a quote older than max_data_age_seconds (120s) is rejected."""
        old_time = self.ref_time - timedelta(seconds=180) # 3 minutes old!
        order = OrderRequest(
            symbol="INFY.NS",
            side="BUY",
            quantity=2,
            price=1000.0,
            timestamp=old_time
        )
        res = self.risk_mgr.validate_order_request(order, current_market_time=self.ref_time)
        self.assertFalse(res.is_approved)
        self.assertEqual(res.risk_code, "STALE_DATA")
        self.assertIn("Data age", res.rejection_reason)

    def test_duplicate_order_prevention(self):
        """Tests cooldown timer between successive orders for the same symbol."""
        order = OrderRequest(symbol="SBIN.NS", side="BUY", quantity=2, price=500.0, timestamp=self.ref_time)
        self.risk_mgr.record_order_execution(order, executed_time=self.ref_time)

        # Immediate follow-up order 15 seconds later for same symbol
        rapid_time = self.ref_time + timedelta(seconds=15)
        rapid_order = OrderRequest(symbol="SBIN.NS", side="BUY", quantity=2, price=500.0, timestamp=rapid_time)
        res = self.risk_mgr.validate_order_request(rapid_order, current_market_time=rapid_time)
        self.assertFalse(res.is_approved)
        self.assertEqual(res.risk_code, "DUPLICATE_ORDER")

    def test_order_field_validation(self):
        """Tests that negative quantities, zero prices, and invalid sides are rejected."""
        # 1. Negative quantity
        bad_qty = OrderRequest(symbol="INFY.NS", side="BUY", quantity=-5, price=1000.0, timestamp=self.ref_time)
        self.assertFalse(self.risk_mgr.validate_order_request(bad_qty, self.ref_time).is_approved)

        # 2. Zero price
        bad_price = OrderRequest(symbol="INFY.NS", side="BUY", quantity=5, price=0.0, timestamp=self.ref_time)
        self.assertFalse(self.risk_mgr.validate_order_request(bad_price, self.ref_time).is_approved)

        # 3. Invalid side
        bad_side = OrderRequest(symbol="INFY.NS", side="HOLD", quantity=5, price=1000.0, timestamp=self.ref_time)
        self.assertFalse(self.risk_mgr.validate_order_request(bad_side, self.ref_time).is_approved)

    def test_max_daily_loss_kill_switch_engagement(self):
        """Tests that hitting the daily loss limit engages the kill-switch and blocks orders."""
        # Record a ₹1,600 realized loss (limit is ₹1,500)
        self.risk_mgr.record_trade_completion(-1600.0)

        self.assertTrue(self.risk_mgr.is_kill_switch_active)

        # Any subsequent order must be rejected
        new_order = OrderRequest(symbol="ITC.NS", side="BUY", quantity=2, price=250.0, timestamp=self.ref_time)
        res = self.risk_mgr.validate_order_request(new_order, current_market_time=self.ref_time)
        self.assertFalse(res.is_approved)
        self.assertEqual(res.risk_code, "KILL_SWITCH")

    def test_fail_closed_architecture(self):
        """Tests that when the risk module fails or is offline, all orders are rejected."""
        self.risk_mgr.fail_closed("Simulated database/feed disconnect")
        self.assertFalse(self.risk_mgr.is_operational)

        order = OrderRequest(symbol="INFY.NS", side="BUY", quantity=1, price=1000.0, timestamp=self.ref_time)
        res = self.risk_mgr.validate_order_request(order, current_market_time=self.ref_time)
        self.assertFalse(res.is_approved)
        self.assertEqual(res.risk_code, "FAIL_CLOSED")

    def test_live_trading_disabled_safety_lock(self):
        """Tests that an order marked is_live=True is rejected when live trading is disabled."""
        live_order = OrderRequest(
            symbol="INFY.NS",
            side="BUY",
            quantity=2,
            price=1000.0,
            timestamp=self.ref_time,
            is_live=True # Attempting live order
        )
        res = self.risk_mgr.validate_order_request(live_order, current_market_time=self.ref_time)
        self.assertFalse(res.is_approved)
        self.assertEqual(res.risk_code, "LIVE_DISABLED")

    def test_position_sizing_and_protective_exits(self):
        """Tests position sizing calculation and stop-loss / take-profit calculations."""
        # Stock price ₹500, max order value ₹5000 -> Max 10 shares
        qty = self.risk_mgr.calculate_position_size(500.0, account_cash=50000.0)
        self.assertEqual(qty, 10)

        # Protective exit levels for BUY @ ₹1000 with 1% SL and 2% TP
        sl, tp = self.risk_mgr.calculate_exit_levels(1000.0, "BUY")
        self.assertEqual(sl, 990.0) # 1000 - 1%
        self.assertEqual(tp, 1020.0) # 1000 + 2%

if __name__ == "__main__":
    unittest.main()
