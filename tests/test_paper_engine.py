"""
Unit Tests for the Air-Gapped Paper Trading Engine.
Verifies:
1. Safe state persistence and exact restart recovery.
2. Partial failure recovery from corrupted state files.
3. Duplicate order rejection across engine restarts via client_order_id.
4. Stale-data and invalid order rejection.
5. Market closures and cutoff timing rejections.
6. Emergency kill-switch rejection.
7. Realistic Indian fee & slippage deductions.
8. Hard broker air-gap policy guard.
"""

import json
import sys
import unittest
from datetime import datetime, time, timedelta
from pathlib import Path

# Ensure project root is available for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.paper_trader import PaperTradingEngine, PaperOrder, PaperPosition
from src.risk_manager import RiskManager, RiskConfig
from src.ma_backtester import IndianMarketCostModel
import config

class TestPaperTradingEngine(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("data/test_paper")
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.test_dir / "test_paper_state.json"
        
        # Clean up any leftover test files
        if self.state_file.exists():
            self.state_file.unlink()

        self.ref_time = datetime(2026, 10, 15, 11, 0, 0) # 11:00 AM IST (normal trading hours)
        
        # Conservative risk configuration
        self.risk_config = RiskConfig(
            max_order_value_inr=5000.0,
            max_open_positions=3,
            max_daily_loss_inr=1500.0,
            max_total_exposure_inr=15000.0,
            max_data_age_seconds=120.0,
            duplicate_cooldown_seconds=60.0,
            market_start_time=time(9, 30),
            market_cutoff_time=time(14, 45),
            square_off_time=time(15, 10),
            live_trading_enabled=False
        )
        self.risk_mgr = RiskManager(risk_config=self.risk_config)
        self.cost_model = IndianMarketCostModel()

        self.engine = PaperTradingEngine(
            state_file=str(self.state_file),
            initial_cash=50000.0,
            risk_manager=self.risk_mgr,
            cost_model=self.cost_model
        )

    def tearDown(self):
        # Cleanup test directory
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

    def test_order_execution_fees_and_slippage(self):
        """Tests that a simulated BUY order incurs slippage and exact Indian fees."""
        order = self.engine.submit_order(
            symbol="INFY.NS",
            side="BUY",
            quantity=3,
            price=1000.0,
            quote_timestamp=self.ref_time,
            client_order_id="TEST_ORDER_001",
            current_time=self.ref_time
        )
        self.assertEqual(order.status, "FILLED")
        self.assertEqual(order.filled_quantity, 3)
        # 0.05% slippage on entry -> 1000 * 1.0005 = 1000.50
        self.assertEqual(order.fill_price, 1000.50)
        self.assertGreater(order.fees_inr, 20.0) # Flat 20 brokerage + STT + GST
        self.assertIn("INFY.NS", self.engine.positions)
        self.assertLess(self.engine.cash, 50000.0 - 3000.0)

    def test_state_persistence_and_restart_recovery(self):
        """Tests that positions, cash, and orders survive an engine restart."""
        # Execute trade
        self.engine.submit_order(
            symbol="ITC.NS",
            side="BUY",
            quantity=10,
            price=250.0,
            quote_timestamp=self.ref_time,
            client_order_id="PERSIST_001",
            current_time=self.ref_time
        )
        saved_cash = self.engine.cash
        self.assertTrue(self.state_file.exists())

        # Instantiate a brand new engine pointing to the same file (simulating reboot)
        new_engine = PaperTradingEngine(
            state_file=str(self.state_file),
            initial_cash=50000.0,
            risk_manager=self.risk_mgr,
            cost_model=self.cost_model
        )
        self.assertEqual(new_engine.cash, saved_cash)
        self.assertIn("ITC.NS", new_engine.positions)
        self.assertEqual(new_engine.positions["ITC.NS"].quantity, 10)
        self.assertIn("PERSIST_001", new_engine.executed_client_order_ids)

    def test_duplicate_order_prevention_across_restarts(self):
        """Tests that an identical client_order_id is rejected after a restart."""
        # Order 1 executed
        self.engine.submit_order(
            symbol="SBIN.NS",
            side="BUY",
            quantity=2,
            price=500.0,
            quote_timestamp=self.ref_time,
            client_order_id="IDEMPOTENT_KEY_123",
            current_time=self.ref_time
        )
        cash_after_first = self.engine.cash

        # Simulate restart
        restarted_engine = PaperTradingEngine(
            state_file=str(self.state_file),
            initial_cash=50000.0,
            risk_manager=self.risk_mgr,
            cost_model=self.cost_model
        )

        # Re-submit with same client_order_id
        dup_time = self.ref_time + timedelta(minutes=5)
        dup_order = restarted_engine.submit_order(
            symbol="SBIN.NS",
            side="BUY",
            quantity=2,
            price=500.0,
            quote_timestamp=dup_time,
            client_order_id="IDEMPOTENT_KEY_123",
            current_time=dup_time
        )
        self.assertEqual(dup_order.status, "REJECTED")
        self.assertIn("Duplicate order ID detected", dup_order.rejection_reason)
        # Cash must not change
        self.assertEqual(restarted_engine.cash, cash_after_first)

    def test_corrupted_state_file_recovery_partial_failure(self):
        """Tests that partial failure (corrupted state JSON) is safely handled without crashing."""
        # Write corrupted JSON to the state file
        with open(self.state_file, "w", encoding="utf-8") as f:
            f.write("<<<CORRUPTED INCOMPLETE JSON CONTENT>>>")

        recovered_engine = PaperTradingEngine(
            state_file=str(self.state_file),
            initial_cash=50000.0,
            risk_manager=self.risk_mgr,
            cost_model=self.cost_model
        )
        # Should gracefully fallback to initial cash and empty positions
        self.assertEqual(recovered_engine.cash, 50000.0)
        self.assertEqual(len(recovered_engine.positions), 0)
        # Verify a .corrupted backup was created
        backup_file = self.state_file.with_suffix(".json.corrupted")
        self.assertTrue(backup_file.exists())

    def test_stale_data_rejection(self):
        """Tests that an order based on stale data (> 120s old) is rejected."""
        stale_time = self.ref_time - timedelta(seconds=180) # 3 mins old!
        order = self.engine.submit_order(
            symbol="INFY.NS",
            side="BUY",
            quantity=2,
            price=1000.0,
            quote_timestamp=stale_time,
            current_time=self.ref_time
        )
        self.assertEqual(order.status, "REJECTED")
        self.assertIn("Stale quote", order.rejection_reason)

    def test_market_closure_and_timing_rejection(self):
        """Tests that orders submitted outside permissible trading hours are rejected."""
        # 1. Before 09:30 AM market opening freeze
        early_time = datetime(2026, 10, 15, 8, 45, 0)
        order_early = self.engine.submit_order(
            symbol="INFY.NS",
            side="BUY",
            quantity=1,
            price=1000.0,
            quote_timestamp=early_time,
            current_time=early_time
        )
        self.assertEqual(order_early.status, "REJECTED")
        self.assertIn("Market opening freeze", order_early.rejection_reason)

        # 2. After 02:45 PM cutoff
        late_time = datetime(2026, 10, 15, 15, 0, 0)
        order_late = self.engine.submit_order(
            symbol="INFY.NS",
            side="BUY",
            quantity=1,
            price=1000.0,
            quote_timestamp=late_time,
            current_time=late_time
        )
        self.assertEqual(order_late.status, "REJECTED")
        self.assertIn("Market intraday entry cutoff", order_late.rejection_reason)

    def test_kill_switch_behavior_blocks_orders(self):
        """Tests that when the kill switch is triggered, all order submissions are blocked."""
        self.risk_mgr.activate_kill_switch("Simulated maximum daily loss breach")
        self.assertTrue(self.risk_mgr.is_kill_switch_active)

        order = self.engine.submit_order(
            symbol="ITC.NS",
            side="BUY",
            quantity=5,
            price=250.0,
            quote_timestamp=self.ref_time,
            current_time=self.ref_time
        )
        self.assertEqual(order.status, "REJECTED")
        self.assertIn("KILL-SWITCH ACTIVE", order.rejection_reason)

    def test_protective_exit_execution(self):
        """Tests that update_market_prices triggers Stop-Loss exit when price drops."""
        # Buy 5 shares @ 1000 with 1% SL = 990
        self.engine.submit_order(
            symbol="INFY.NS",
            side="BUY",
            quantity=5,
            price=1000.0,
            quote_timestamp=self.ref_time,
            client_order_id="PROT_ENTRY",
            current_time=self.ref_time
        )
        self.assertIn("INFY.NS", self.engine.positions)

        # Price drops to 985 (breaching 990 Stop-Loss)
        drop_time = self.ref_time + timedelta(minutes=10)
        self.engine.update_market_prices({"INFY.NS": 985.0}, current_time=drop_time)

        # Position must be automatically closed
        self.assertNotIn("INFY.NS", self.engine.positions)
        self.assertEqual(len(self.engine.trade_history), 1)
        last_trade = self.engine.trade_history[-1]
        self.assertEqual(last_trade["symbol"], "INFY.NS")
        self.assertLess(last_trade["net_pnl_inr"], 0) # Realized loss recorded

    def test_process_signal_execution(self):
        """Tests that process_signal properly maps BUY and EXIT strategy signals to paper orders."""
        # 1. Process BUY signal
        buy_order = self.engine.process_signal("ITC.NS", "BUY", price=250.0, current_time=self.ref_time)
        self.assertIsNotNone(buy_order)
        self.assertEqual(buy_order.status, "FILLED")
        self.assertIn("ITC.NS", self.engine.positions)

        # 2. Duplicate BUY signal for already held position is skipped
        dup_order = self.engine.process_signal("ITC.NS", "BUY", price=251.0, current_time=self.ref_time + timedelta(minutes=1))
        self.assertIsNone(dup_order)

        # 3. Process EXIT signal
        exit_order = self.engine.process_signal("ITC.NS", "EXIT", price=255.0, current_time=self.ref_time + timedelta(minutes=5))
        self.assertIsNotNone(exit_order)
        self.assertEqual(exit_order.status, "FILLED")
        self.assertNotIn("ITC.NS", self.engine.positions)
        self.assertEqual(len(self.engine.trade_history), 1)

    def test_reset_account_safety(self):
        """Tests that reset_account cleanly resets cash, clears positions, orders, and saves to disk."""
        self.engine.submit_order(
            symbol="INFY.NS",
            side="BUY",
            quantity=2,
            price=1000.0,
            quote_timestamp=self.ref_time,
            current_time=self.ref_time
        )
        self.assertIn("INFY.NS", self.engine.positions)
        self.assertLess(self.engine.cash, 50000.0)

        # Reset account
        self.engine.reset_account(initial_cash=50000.0)
        self.assertEqual(self.engine.cash, 50000.0)
        self.assertEqual(len(self.engine.positions), 0)
        self.assertEqual(len(self.engine.orders), 0)
        self.assertEqual(len(self.engine.executed_client_order_ids), 0)

        # Verify persisted state matches
        with open(self.state_file, "r", encoding="utf-8") as f:
            persisted = json.load(f)
        self.assertEqual(persisted["cash"], 50000.0)
        self.assertEqual(persisted["positions"], {})

    def test_hard_broker_air_gap_policy(self):
        """Tests that PaperTradingEngine strictly forbids running if LIVE_TRADING_ENABLED=True."""
        try:
            config.LIVE_TRADING_ENABLED = True
            with self.assertRaises(RuntimeError):
                PaperTradingEngine(state_file=str(self.state_file))
        finally:
            config.LIVE_TRADING_ENABLED = False # Always restore safety lock

if __name__ == "__main__":
    unittest.main()


