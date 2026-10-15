"""
Comprehensive Unit & Integration Tests for the Enterprise Broker Adapter.
Tests:
1. Pre-Trade Risk Controls (Order value, Stale data, Market timings, Exposure limits).
2. Rate Limiting Throttling (10 requests/second cap).
3. Session Expiry & 401 Re-authentication handling.
4. Order Preview Calculation (Brokerage, STT, Exchange turnover, GST, SL/TP).
5. Safe Network Timeout Recovery (No blind retries; correlation-ID reconciliation).
6. Order Status Reconciliation (Detection of missing or mismatched orders).
7. Emergency Kill Switch Behavior.
8. Audit Log Stream Verification (logs/broker_audit.jsonl).
9. Live Broker Adapter Triple-Interlock Safety Guards.
"""

import json
import os
import sys
import unittest
from datetime import datetime, time, timedelta
from pathlib import Path

# Ensure project root is available for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from src.broker_adapter import (
    BaseBrokerAdapter,
    MockBrokerAdapter,
    DhanBrokerAdapter,
    BrokerOrderRequest,
    BrokerOrderResult,
    BrokerOrderType,
    BrokerProductType,
    BrokerTransactionType,
    BrokerOrderStatus,
    BrokerAuditLogger,
    LiveTradingDisabledError,
    UnauthorizedLiveModeError,
    RateLimitExceededError,
    SessionExpiredError,
    PreTradeRiskCheckFailedError
)
from src.risk_manager import RiskManager, RiskConfig
from src.ma_backtester import IndianMarketCostModel

class TestBrokerAdapter(unittest.TestCase):
    def setUp(self):
        self.test_log_path = "logs/test_broker_audit.jsonl"
        self.audit_logger = BrokerAuditLogger(log_path=self.test_log_path)
        
        # Reference market time: 11:00 AM IST (normal market hours)
        self.ref_time = datetime(2026, 10, 15, 11, 0, 0)

        # Conservative Risk Configuration
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

        self.adapter = MockBrokerAdapter(
            initial_cash=50000.0,
            risk_manager=self.risk_mgr,
            cost_model=self.cost_model,
            audit_logger=self.audit_logger,
            rate_limit_per_second=10
        )

    def tearDown(self):
        # Cleanup test audit log
        log_file = Path(self.test_log_path)
        if log_file.exists():
            try:
                log_file.unlink()
            except Exception:
                pass

    # --------------------------------------------------------------------------
    # 1. Order Preview Verification
    # --------------------------------------------------------------------------
    def test_order_preview_calculation(self):
        """Tests that preview_order accurately calculates Indian fees, margin, and SL/TP."""
        req = BrokerOrderRequest(
            symbol="INFY.NS",
            transaction_type=BrokerTransactionType.BUY,
            quantity=3,
            price=1000.0,
            quote_timestamp=self.ref_time
        )
        preview = self.adapter.preview_order(req)

        self.assertEqual(preview.symbol, "INFY.NS")
        self.assertEqual(preview.quantity, 3)
        self.assertEqual(preview.estimated_order_value, 3000.0)
        self.assertEqual(preview.brokerage_inr, 20.0)
        self.assertGreater(preview.total_regulatory_costs_inr, 20.0)
        self.assertGreater(preview.effective_execution_price, 1000.0) # Slippage + costs
        self.assertEqual(preview.stop_loss_price, 990.0)            # 1.0% SL
        self.assertEqual(preview.take_profit_price, 1020.0)         # 2.0% TP
        self.assertEqual(len(preview.warnings), 0)

    # --------------------------------------------------------------------------
    # 2. Pre-Trade Risk Control Rejections
    # --------------------------------------------------------------------------
    def test_pre_trade_risk_check_blocks_excessive_order_value(self):
        """Tests that an order exceeding max_order_value_inr (INR 5,000) is rejected locally."""
        req = BrokerOrderRequest(
            symbol="RELIANCE.NS",
            transaction_type=BrokerTransactionType.BUY,
            quantity=10,
            price=1200.0, # 10 * 1200 = 12,000 > 5,000 limit
            quote_timestamp=self.ref_time
        )
        res = self.adapter.place_order(req, current_time=self.ref_time)
        self.assertEqual(res.status, BrokerOrderStatus.REJECTED)
        self.assertIn("MAX_ORDER_VAL", res.rejection_reason)
        # Verify order was not added to broker order book
        self.assertEqual(len(self.adapter.broker_order_book), 0)

    def test_pre_trade_risk_check_blocks_stale_data(self):
        """Tests that a quote older than max_data_age_seconds (120s) is rejected."""
        stale_time = self.ref_time - timedelta(seconds=200)
        req = BrokerOrderRequest(
            symbol="ITC.NS",
            transaction_type=BrokerTransactionType.BUY,
            quantity=5,
            price=250.0,
            quote_timestamp=stale_time
        )
        res = self.adapter.place_order(req, current_time=self.ref_time)
        self.assertEqual(res.status, BrokerOrderStatus.REJECTED)
        self.assertIn("STALE_DATA", res.rejection_reason)

    def test_pre_trade_risk_check_blocks_market_timings(self):
        """Tests that orders before 09:30 or past 14:45 IST are rejected."""
        # 1. Early morning (09:10 IST)
        early_time = datetime(2026, 10, 15, 9, 10, 0)
        req_early = BrokerOrderRequest(
            symbol="SBIN.NS",
            transaction_type=BrokerTransactionType.BUY,
            quantity=2,
            price=500.0,
            quote_timestamp=early_time
        )
        res_early = self.adapter.place_order(req_early, current_time=early_time)
        self.assertEqual(res_early.status, BrokerOrderStatus.REJECTED)
        self.assertIn("TIMING_REJECT", res_early.rejection_reason)

        # 2. Late afternoon (15:00 IST)
        late_time = datetime(2026, 10, 15, 15, 0, 0)
        req_late = BrokerOrderRequest(
            symbol="SBIN.NS",
            transaction_type=BrokerTransactionType.BUY,
            quantity=2,
            price=500.0,
            quote_timestamp=late_time
        )
        res_late = self.adapter.place_order(req_late, current_time=late_time)
        self.assertEqual(res_late.status, BrokerOrderStatus.REJECTED)
        self.assertIn("TIMING_REJECT", res_late.rejection_reason)

    # --------------------------------------------------------------------------
    # 3. Rate Limiting & Throttling
    # --------------------------------------------------------------------------
    def test_rate_limiter_throttling_enforcement(self):
        """Tests that exceeding rate_limit_per_second raises RateLimitExceededError."""
        # Trigger simulated rate limit breach
        self.adapter.simulate_rate_limit = True
        with self.assertRaises(RateLimitExceededError):
            self.adapter.get_account_balance()

        # Reset flag
        self.adapter.simulate_rate_limit = False

        # Test sliding window rate limit
        for _ in range(10):
            self.adapter.get_account_balance()

        # 11th request within same second must be rejected
        with self.assertRaises(RateLimitExceededError):
            self.adapter.get_account_balance()

    # --------------------------------------------------------------------------
    # 4. Session Expiry Handling
    # --------------------------------------------------------------------------
    def test_session_expiry_handling(self):
        """Tests that simulated session expiry raises SessionExpiredError."""
        self.adapter.simulate_auth_expiry = True
        with self.assertRaises(SessionExpiredError):
            self.adapter.authenticate()

    # --------------------------------------------------------------------------
    # 5. Network Timeout Safe Recovery (CRITICAL)
    # --------------------------------------------------------------------------
    def test_network_timeout_recovery_when_order_reached_broker(self):
        """
        Tests timeout recovery when broker received and filled the order,
        but the client lost the HTTP connection.
        Verifies:
        - place_order returns TIMEOUT_INDETERMINATE.
        - Bot does NOT blindly retry.
        - reconcile_timed_out_order locates order by correlation_id.
        """
        self.adapter.simulate_network_timeout = True
        self.adapter.timeout_order_reached_broker = True

        clo_id = "CORR_TIMEOUT_TEST_001"
        req = BrokerOrderRequest(
            symbol="INFY.NS",
            transaction_type=BrokerTransactionType.BUY,
            quantity=2,
            price=1000.0,
            correlation_id=clo_id,
            quote_timestamp=self.ref_time
        )

        # Order times out
        res = self.adapter.place_order(req, current_time=self.ref_time)
        self.assertEqual(res.status, BrokerOrderStatus.TIMEOUT_INDETERMINATE)
        self.assertIn("NETWORK_TIMEOUT", res.rejection_reason)

        # RECOVERY STEP: Safely query broker by correlation_id without blindly placing a 2nd order!
        reconciled = self.adapter.reconcile_timed_out_order(clo_id)
        self.assertEqual(reconciled.status, BrokerOrderStatus.TRADED)
        self.assertEqual(reconciled.correlation_id, clo_id)
        self.assertIsNotNone(reconciled.broker_order_id)
        self.assertEqual(reconciled.filled_quantity, 2)

    def test_network_timeout_recovery_when_order_dropped_before_broker(self):
        """
        Tests timeout recovery when packet dropped before reaching broker.
        Verifies reconcile_timed_out_order marks it safely dropped without double-execution.
        """
        self.adapter.simulate_network_timeout = True
        self.adapter.timeout_order_reached_broker = False

        clo_id = "CORR_TIMEOUT_TEST_002"
        req = BrokerOrderRequest(
            symbol="ITC.NS",
            transaction_type=BrokerTransactionType.BUY,
            quantity=5,
            price=250.0,
            correlation_id=clo_id,
            quote_timestamp=self.ref_time
        )

        res = self.adapter.place_order(req, current_time=self.ref_time)
        self.assertEqual(res.status, BrokerOrderStatus.TIMEOUT_INDETERMINATE)

        # RECOVERY STEP: Query broker
        reconciled = self.adapter.reconcile_timed_out_order(clo_id)
        self.assertEqual(reconciled.status, BrokerOrderStatus.CANCELLED)
        self.assertEqual(reconciled.rejection_reason, "CONFIRMED_DROPPED_NOT_ON_EXCHANGE")

    # --------------------------------------------------------------------------
    # 6. Order Status Reconciliation
    # --------------------------------------------------------------------------
    def test_order_status_reconciliation(self):
        """Tests reconcile_orders comparing client tracking with broker records."""
        # 1. Place a successful order
        req = BrokerOrderRequest(
            symbol="SBIN.NS",
            transaction_type=BrokerTransactionType.BUY,
            quantity=2,
            price=500.0,
            correlation_id="CLO_RECON_1",
            quote_timestamp=self.ref_time
        )
        filled_order = self.adapter.place_order(req, current_time=self.ref_time)
        self.assertEqual(filled_order.status, BrokerOrderStatus.TRADED)

        # 2. Reconcile with balanced local list
        report = self.adapter.reconcile_orders([filled_order])
        self.assertEqual(report.status, "BALANCED")
        self.assertEqual(report.matched_orders, 1)
        self.assertEqual(len(report.discrepancies), 0)

        # 3. Test with a local ghost order not on broker
        ghost_order = BrokerOrderResult(
            status=BrokerOrderStatus.PENDING,
            broker_order_id="BROK_NON_EXISTENT",
            correlation_id="CLO_GHOST_999",
            symbol="INFY.NS",
            transaction_type="BUY",
            requested_quantity=1,
            filled_quantity=0,
            requested_price=1000.0,
            fill_price=0.0,
            fees_inr=0.0,
            slippage_inr=0.0
        )
        discrepancy_report = self.adapter.reconcile_orders([filled_order, ghost_order])
        self.assertEqual(discrepancy_report.status, "DISCREPANCIES_DETECTED")
        self.assertEqual(len(discrepancy_report.discrepancies), 1)
        self.assertEqual(discrepancy_report.discrepancies[0]["issue"], "LOCAL_ORDER_MISSING_ON_BROKER")

    # --------------------------------------------------------------------------
    # 7. Emergency Kill Switch Behavior
    # --------------------------------------------------------------------------
    def test_emergency_kill_switch_behavior(self):
        """Tests that kill switch blocks all orders and requires correct admin token to reset."""
        self.adapter.activate_kill_switch("Manual test trigger")
        self.assertTrue(self.adapter.is_kill_switch_active)

        req = BrokerOrderRequest(
            symbol="ITC.NS",
            transaction_type=BrokerTransactionType.BUY,
            quantity=2,
            price=250.0,
            quote_timestamp=self.ref_time
        )
        res = self.adapter.place_order(req, current_time=self.ref_time)
        self.assertEqual(res.status, BrokerOrderStatus.REJECTED)
        self.assertIn("KILL_SWITCH_ACTIVE", res.rejection_reason)

        # Reset with wrong token fails
        self.assertFalse(self.adapter.reset_kill_switch("INVALID_TOKEN"))
        self.assertTrue(self.adapter.is_kill_switch_active)

        # Reset with valid token succeeds
        self.assertTrue(self.adapter.reset_kill_switch("RESET_RISK_OVERRIDE"))
        self.assertFalse(self.adapter.is_kill_switch_active)

    # --------------------------------------------------------------------------
    # 8. Audit Logging Persistence
    # --------------------------------------------------------------------------
    def test_audit_logger_records_structured_events(self):
        """Tests that operations persist structured records in logs/test_broker_audit.jsonl."""
        req = BrokerOrderRequest(
            symbol="INFY.NS",
            transaction_type=BrokerTransactionType.BUY,
            quantity=1,
            price=1000.0,
            quote_timestamp=self.ref_time
        )
        self.adapter.preview_order(req)
        self.adapter.place_order(req, current_time=self.ref_time)

        log_path = Path(self.test_log_path)
        self.assertTrue(log_path.exists())

        with open(log_path, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        self.assertGreater(len(lines), 0)
        event_types = [item["event_type"] for item in lines]
        self.assertIn("ORDER_PREVIEW_GENERATED", event_types)
        self.assertIn("ORDER_FILLED_BUY", event_types)

    # --------------------------------------------------------------------------
    # 9. Live Broker Adapter Triple-Interlock Safety
    # --------------------------------------------------------------------------
    def test_live_adapter_triple_interlock_guard(self):
        """
        Verifies that DhanBrokerAdapter CANNOT be initialized or used without:
        1. LIVE_TRADING_ENABLED == True
        2. ENABLE_LIVE_BROKER_ADAPTER == True
        3. Valid runtime authorization passphrase.
        """
        # Ensure default safety flags are False
        self.assertFalse(config.LIVE_TRADING_ENABLED)
        self.assertFalse(config.ENABLE_LIVE_BROKER_ADAPTER)

        # 1. Instantiation must fail with LiveTradingDisabledError
        with self.assertRaises(LiveTradingDisabledError):
            DhanBrokerAdapter()

        # 2. Even if LIVE_TRADING_ENABLED is toggled, ENABLE_LIVE_BROKER_ADAPTER still blocks it
        try:
            config.LIVE_TRADING_ENABLED = True
            with self.assertRaises(LiveTradingDisabledError):
                DhanBrokerAdapter()
        finally:
            config.LIVE_TRADING_ENABLED = False

        # 3. If both flags are temporarily True, place_order must fail without correct passphrase
        try:
            config.LIVE_TRADING_ENABLED = True
            config.ENABLE_LIVE_BROKER_ADAPTER = True
            
            adapter = DhanBrokerAdapter(risk_manager=self.risk_mgr, cost_model=self.cost_model)
            req = BrokerOrderRequest(
                symbol="ITC.NS",
                transaction_type=BrokerTransactionType.BUY,
                quantity=1,
                price=250.0,
                quote_timestamp=self.ref_time
            )
            
            # Missing or invalid authorization token
            with self.assertRaises(UnauthorizedLiveModeError):
                adapter.place_order(req, authorization_token="WRONG_TOKEN", current_time=self.ref_time)
                
        finally:
            # Always restore safety locks
            config.LIVE_TRADING_ENABLED = False
            config.ENABLE_LIVE_BROKER_ADAPTER = False

if __name__ == "__main__":
    unittest.main()
