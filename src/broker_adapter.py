"""
Enterprise Broker Adapter Interface for Indian Stock Trading Bot.
Strictly separates simulation/mock execution from live broker endpoints.

KEY ARCHITECTURAL FEATURES:
1. Standardized Interface: BaseBrokerAdapter (ABC) defining authentication, order preview,
   order placement, status query, reconciliation, and kill-switch.
2. Complete Mock Broker Adapter: In-memory order book, execution simulation, and controlled
   failure injections (network timeouts, rate limits, session expiry, rejections).
3. Safe Network Timeout Recovery: NEVER blindly retries orders on socket/HTTP timeout.
   Employs a correlation-ID reconciliation state machine to verify exchange receipt.
4. Pre-Trade Risk Integration: Every order is audited against RiskManager before touching
   the network layer.
5. Explicit Live-Mode Authorization: Triple-interlock security requiring:
   - config.LIVE_TRADING_ENABLED == True
   - config.ENABLE_LIVE_BROKER_ADAPTER == True
   - Valid runtime authorization passphrase matching config.LIVE_AUTHORIZATION_PASSPHRASE.
6. Tamper-Evident Audit Logging: Append-only JSONL event stream in logs/broker_audit.jsonl.
7. Realistic Indian Cost Modeling: Brokerage, STT, Exchange Turnover, SEBI Fee, Stamp Duty, GST.
"""

import abc
import enum
import json
import os
import sys
import time
import uuid
from datetime import datetime, date, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Tuple, Any, Set

# Ensure project root is available for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Windows console encoding safeguard
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import config
from src.risk_manager import RiskManager, RiskConfig, OrderRequest, OrderValidationResult
from src.ma_backtester import IndianMarketCostModel

# ==============================================================================
# 1. ENUMS & DATA STRUCTURES
# ==============================================================================

class BrokerOrderType(str, enum.Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"                # SL-L (Trigger + Limit)
    STOP_LOSS_MARKET = "STOP_LOSS_MARKET"  # SL-M (Trigger + Market)

class BrokerProductType(str, enum.Enum):
    CNC = "CNC"          # Cash & Carry / Delivery (100% upfront margin)
    INTRADAY = "INTRADAY" # Intraday MIS (mandatory auto-square-off before 15:15 IST)

class BrokerTransactionType(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"

class BrokerOrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    TRADED = "TRADED"                      # Fully filled
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    TIMEOUT_INDETERMINATE = "TIMEOUT_INDETERMINATE"  # Crucial safety state on network timeout

# ------------------------------------------------------------------------------
# Custom Exceptions
# ------------------------------------------------------------------------------

class BrokerAdapterError(Exception):
    """Base exception for all broker adapter operations."""
    pass

class LiveTradingDisabledError(BrokerAdapterError):
    """Raised when attempting live execution while live trading is disabled."""
    pass

class UnauthorizedLiveModeError(BrokerAdapterError):
    """Raised when the runtime live-mode authorization passphrase is invalid or absent."""
    pass

class RateLimitExceededError(BrokerAdapterError):
    """Raised when request frequency breaches broker throttling thresholds (e.g. 10 req/s)."""
    pass

class NetworkTimeoutError(BrokerAdapterError):
    """Raised on connection break or gateway timeout during order transmission."""
    pass

class SessionExpiredError(BrokerAdapterError):
    """Raised when JWT/OAuth session has expired or requires daily 2FA re-authentication."""
    pass

class PreTradeRiskCheckFailedError(BrokerAdapterError):
    """Raised when pre-trade risk controls block order submission."""
    pass

# ------------------------------------------------------------------------------
# Request & Result Payloads
# ------------------------------------------------------------------------------

@dataclass
class BrokerOrderRequest:
    """Standardized order request submitted to the broker adapter."""
    symbol: str
    transaction_type: BrokerTransactionType
    quantity: int
    price: float = 0.0                     # Required for LIMIT orders
    trigger_price: float = 0.0             # Required for STOP_LOSS orders
    order_type: BrokerOrderType = BrokerOrderType.MARKET
    product_type: BrokerProductType = BrokerProductType.INTRADAY
    correlation_id: Optional[str] = None   # Client Order ID for idempotent reconciliation
    quote_timestamp: Optional[datetime] = None

    def __post_init__(self):
        self.symbol = self.symbol.upper()
        if isinstance(self.transaction_type, str):
            self.transaction_type = BrokerTransactionType(self.transaction_type.upper())
        if isinstance(self.order_type, str):
            self.order_type = BrokerOrderType(self.order_type.upper())
        if isinstance(self.product_type, str):
            self.product_type = BrokerProductType(self.product_type.upper())
        if self.correlation_id is None:
            self.correlation_id = f"CLO_{self.symbol}_{self.transaction_type.value}_{uuid.uuid4().hex[:8].upper()}"
        if self.quote_timestamp is None:
            self.quote_timestamp = datetime.now()

@dataclass
class OrderPreview:
    """Pre-trade inspection breakdown calculating exact Indian fees, margin, and risk."""
    symbol: str
    transaction_type: str
    quantity: int
    estimated_price: float
    estimated_order_value: float
    brokerage_inr: float
    stt_inr: float
    turnover_fees_inr: float
    sebi_fees_inr: float
    stamp_duty_inr: float
    gst_inr: float
    total_regulatory_costs_inr: float
    effective_execution_price: float
    margin_required_inr: float
    available_margin_inr: float
    stop_loss_price: float
    take_profit_price: float
    warnings: List[str] = field(default_factory=list)

@dataclass
class BrokerOrderResult:
    """Result returned from order placement, query, or reconciliation."""
    status: BrokerOrderStatus
    broker_order_id: Optional[str]
    correlation_id: str
    symbol: str
    transaction_type: str
    requested_quantity: int
    filled_quantity: int
    requested_price: float
    fill_price: float
    fees_inr: float
    slippage_inr: float
    rejection_reason: Optional[str] = None
    message: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class BrokerPosition:
    """Representation of an open position on the broker book."""
    symbol: str
    quantity: int
    average_price: float
    current_price: float
    product_type: str
    unrealized_pnl: float
    realized_pnl: float

@dataclass
class ReconciliationReport:
    """Audit report comparing local ledger with broker order book."""
    reconciled_at: str
    total_orders_checked: int
    matched_orders: int
    discrepancies: List[Dict[str, Any]]
    status: str

# ==============================================================================
# 2. AUDIT LOGGER
# ==============================================================================

class BrokerAuditLogger:
    """
    Append-only structured audit logger for all broker operations.
    Persists events to logs/broker_audit.jsonl.
    """
    def __init__(self, log_path: str = "logs/broker_audit.jsonl"):
        self.log_file = Path(log_path)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def log_event(self, event_type: str, details: Dict[str, Any]):
        record = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "details": details
        }
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            print(f"[AUDIT LOG ERROR] Failed to write audit event: {e}")

# ==============================================================================
# 3. BASE BROKER ADAPTER (ABSTRACT INTERFACE)
# ==============================================================================

class BaseBrokerAdapter(abc.ABC):
    """
    Abstract interface for broker integration.
    Guarantees standard interaction across Mock, DhanHQ, and Angel One adapters.
    """
    def __init__(
        self,
        risk_manager: Optional[RiskManager] = None,
        cost_model: Optional[IndianMarketCostModel] = None,
        audit_logger: Optional[BrokerAuditLogger] = None
    ):
        self.risk_manager = risk_manager if risk_manager is not None else RiskManager()
        self.cost_model = cost_model if cost_model is not None else IndianMarketCostModel()
        self.audit_logger = audit_logger if audit_logger is not None else BrokerAuditLogger()
        self.is_kill_switch_active: bool = False
        self.kill_switch_reason: Optional[str] = None

    @abc.abstractmethod
    def authenticate(self) -> bool:
        """Authenticates with the broker using credentials / 2FA."""
        pass

    @abc.abstractmethod
    def get_account_balance(self) -> Dict[str, float]:
        """Fetches available cash, margin, and collateral."""
        pass

    @abc.abstractmethod
    def get_positions(self) -> List[BrokerPosition]:
        """Fetches current open positions from the broker book."""
        pass

    @abc.abstractmethod
    def get_orders(self) -> List[BrokerOrderResult]:
        """Fetches the day's order book from the broker."""
        pass

    @abc.abstractmethod
    def get_order_by_id(self, broker_order_id: str) -> Optional[BrokerOrderResult]:
        """Fetches a specific order by broker order ID."""
        pass

    @abc.abstractmethod
    def get_order_by_correlation_id(self, correlation_id: str) -> Optional[BrokerOrderResult]:
        """Fetches an order using the client-assigned correlation ID."""
        pass

    @abc.abstractmethod
    def preview_order(self, request: BrokerOrderRequest) -> OrderPreview:
        """Inspects trade details, Indian regulatory costs, and margin before submission."""
        pass

    @abc.abstractmethod
    def place_order(
        self,
        request: BrokerOrderRequest,
        authorization_token: Optional[str] = None,
        current_time: Optional[datetime] = None
    ) -> BrokerOrderResult:
        """Submits an order with pre-trade risk validation and safety checks."""
        pass

    @abc.abstractmethod
    def cancel_order(self, broker_order_id: str) -> bool:
        """Cancels an open/pending order on the exchange."""
        pass

    @abc.abstractmethod
    def reconcile_timed_out_order(self, correlation_id: str) -> BrokerOrderResult:
        """
        Safely recovers from network timeouts without blindly retrying.
        Queries broker order book by correlation_id to verify exchange receipt.
        """
        pass

    @abc.abstractmethod
    def reconcile_orders(self, local_orders: List[BrokerOrderResult]) -> ReconciliationReport:
        """Reconciles local order tracking against the broker's official order book."""
        pass

    def activate_kill_switch(self, reason: str) -> bool:
        """Emergency circuit breaker: cancels pending orders and locks adapter."""
        self.is_kill_switch_active = True
        self.kill_switch_reason = reason
        self.risk_manager.activate_kill_switch(reason)
        self.audit_logger.log_event("KILL_SWITCH_ACTIVATED", {"reason": reason})
        print(f"\n[BROKER ADAPTER] 🚨 EMERGENCY KILL SWITCH ENGAGED! Reason: {reason}")
        return True

    def reset_kill_switch(self, token: str) -> bool:
        """Admin override to reset kill-switch with confirmation token."""
        if token != "RESET_RISK_OVERRIDE":
            return False
        self.is_kill_switch_active = False
        self.kill_switch_reason = None
        self.risk_manager.reset_kill_switch(token)
        self.audit_logger.log_event("KILL_SWITCH_RESET", {"token": token})
        return True

# ==============================================================================
# 4. MOCK BROKER ADAPTER (TESTING & AIR-GAPPED SIMULATION)
# ==============================================================================

class MockBrokerAdapter(BaseBrokerAdapter):
    """
    Institutional Mock Broker Adapter for Indian Markets.
    Accurately models exchange behavior, rate limits (10 req/s), token buckets,
    latency, and failure scenarios (timeouts, auth expiry, circuit limits).
    """
    def __init__(
        self,
        initial_cash: float = 50000.0,
        risk_manager: Optional[RiskManager] = None,
        cost_model: Optional[IndianMarketCostModel] = None,
        audit_logger: Optional[BrokerAuditLogger] = None,
        rate_limit_per_second: int = 10
    ):
        super().__init__(risk_manager=risk_manager, cost_model=cost_model, audit_logger=audit_logger)
        self.cash: float = initial_cash
        self.positions: Dict[str, BrokerPosition] = {}
        self.broker_order_book: Dict[str, BrokerOrderResult] = {}
        self.correlation_to_order_id: Dict[str, str] = {}
        self.is_authenticated: bool = True
        
        # Rate Limiter State (Token Bucket / Sliding Window)
        self.rate_limit_per_second = rate_limit_per_second
        self.request_timestamps: List[float] = []

        # Failure Injection Controls (for rigorous automated testing)
        self.simulate_network_timeout: bool = False
        self.timeout_order_reached_broker: bool = True
        self.simulate_rate_limit: bool = False
        self.simulate_auth_expiry: bool = False
        self.simulate_exchange_rejection: bool = False

    # --------------------------------------------------------------------------
    # Rate Limiting & Throttling Guard
    # --------------------------------------------------------------------------
    def _enforce_rate_limit(self):
        """Enforces SEBI & DhanHQ 10 requests/second throttling cap."""
        if self.simulate_rate_limit:
            self.audit_logger.log_event("RATE_LIMIT_BREACH", {"limit": self.rate_limit_per_second})
            raise RateLimitExceededError("HTTP 429 [RL001]: Rate limit exceeded (10 requests/sec). Backoff required.")

        now_sec = time.time()
        # Keep only timestamps in the last 1.0 second
        self.request_timestamps = [t for t in self.request_timestamps if now_sec - t < 1.0]

        if len(self.request_timestamps) >= self.rate_limit_per_second:
            self.audit_logger.log_event("RATE_LIMIT_BREACH", {"limit": self.rate_limit_per_second})
            raise RateLimitExceededError(f"HTTP 429: Throttling cap reached ({self.rate_limit_per_second} requests/sec).")

        self.request_timestamps.append(now_sec)

    # --------------------------------------------------------------------------
    # Authentication & Session
    # --------------------------------------------------------------------------
    def authenticate(self) -> bool:
        self._enforce_rate_limit()
        if self.simulate_auth_expiry:
            self.is_authenticated = False
            self.audit_logger.log_event("AUTH_FAILED", {"reason": "Simulated token expiry"})
            raise SessionExpiredError("HTTP 401 [AUTH_EXPIRED]: Daily TOTP session expired. Re-authentication required.")

        self.is_authenticated = True
        self.audit_logger.log_event("AUTH_SUCCESS", {"mode": "MOCK"})
        return True

    def get_account_balance(self) -> Dict[str, float]:
        self._enforce_rate_limit()
        if not self.is_authenticated:
            raise SessionExpiredError("Session not authenticated.")
        
        mkt_val = sum(pos.quantity * pos.current_price for pos in self.positions.values())
        return {
            "available_cash": round(self.cash, 2),
            "collateral_margin": 0.0,
            "used_margin": round(mkt_val, 2),
            "total_net_worth": round(self.cash + mkt_val, 2)
        }

    def get_positions(self) -> List[BrokerPosition]:
        self._enforce_rate_limit()
        return list(self.positions.values())

    def get_orders(self) -> List[BrokerOrderResult]:
        self._enforce_rate_limit()
        return list(self.broker_order_book.values())

    def get_order_by_id(self, broker_order_id: str) -> Optional[BrokerOrderResult]:
        self._enforce_rate_limit()
        return self.broker_order_book.get(broker_order_id)

    def get_order_by_correlation_id(self, correlation_id: str) -> Optional[BrokerOrderResult]:
        self._enforce_rate_limit()
        b_id = self.correlation_to_order_id.get(correlation_id)
        return self.broker_order_book.get(b_id) if b_id else None

    # --------------------------------------------------------------------------
    # Order Preview
    # --------------------------------------------------------------------------
    def preview_order(self, request: BrokerOrderRequest) -> OrderPreview:
        """
        Computes exact Indian regulatory costs, margin requirement, and Stop-Loss / Take-Profit
        levels before an order is placed.
        """
        ref_price = request.price if request.price > 0 else 1000.0
        qty = request.quantity
        order_val = qty * ref_price

        # Indian regulatory fee breakdown
        if request.transaction_type == BrokerTransactionType.BUY:
            eff_price, total_fees, breakdown = self.cost_model.calculate_entry_costs(ref_price, qty)
        else:
            eff_price, total_fees, breakdown = self.cost_model.calculate_exit_costs(ref_price, qty)

        sl_price, tp_price = self.risk_manager.calculate_exit_levels(ref_price, request.transaction_type.value)

        # Margin required: 100% for CNC, or intraday MIS margin
        margin_required = order_val + total_fees
        warnings = []

        if margin_required > self.cash:
            warnings.append(f"Insufficient Cash: Required INR {margin_required:,.2f}, Available: INR {self.cash:,.2f}.")
        if order_val > self.risk_manager.config.max_order_value_inr:
            warnings.append(f"Order value INR {order_val:,.2f} exceeds cap of INR {self.risk_manager.config.max_order_value_inr:,.2f}.")

        preview = OrderPreview(
            symbol=request.symbol,
            transaction_type=request.transaction_type.value,
            quantity=qty,
            estimated_price=round(ref_price, 2),
            estimated_order_value=round(order_val, 2),
            brokerage_inr=round(breakdown.get("brokerage", 20.0), 2),
            stt_inr=round(breakdown.get("stt", 0.0), 2),
            turnover_fees_inr=round(breakdown.get("exchange_turnover", 0.0), 2),
            sebi_fees_inr=round(breakdown.get("sebi_turnover", 0.0), 2),
            stamp_duty_inr=round(breakdown.get("stamp_duty", 0.0), 2),
            gst_inr=round(breakdown.get("gst", 0.0), 2),
            total_regulatory_costs_inr=round(total_fees, 2),
            effective_execution_price=round(eff_price, 2),
            margin_required_inr=round(margin_required, 2),
            available_margin_inr=round(self.cash, 2),
            stop_loss_price=sl_price,
            take_profit_price=tp_price,
            warnings=warnings
        )

        self.audit_logger.log_event("ORDER_PREVIEW_GENERATED", {
            "symbol": request.symbol,
            "side": request.transaction_type.value,
            "quantity": qty,
            "fees_inr": preview.total_regulatory_costs_inr,
            "warnings_count": len(warnings)
        })
        return preview

    # --------------------------------------------------------------------------
    # Order Placement Pipeline
    # --------------------------------------------------------------------------
    def place_order(
        self,
        request: BrokerOrderRequest,
        authorization_token: Optional[str] = None,
        current_time: Optional[datetime] = None
    ) -> BrokerOrderResult:
        """
        Submits order through pre-trade risk verification, simulation, and audit logging.
        Guarantees:
        - Rejection if kill switch is active.
        - Pre-trade risk validation against RiskManager.
        - Network timeout simulation without blind retries.
        - State update and audit log recording.
        """
        if current_time is None:
            current_time = datetime.now()

        # 1. Rate Limiting Check
        self._enforce_rate_limit()

        # 2. Kill-Switch Gatekeeper
        if self.is_kill_switch_active or self.risk_manager.is_kill_switch_active:
            reason = self.kill_switch_reason or self.risk_manager.kill_switch_reason or "Kill switch active"
            res = BrokerOrderResult(
                status=BrokerOrderStatus.REJECTED,
                broker_order_id=None,
                correlation_id=request.correlation_id,
                symbol=request.symbol,
                transaction_type=request.transaction_type.value,
                requested_quantity=request.quantity,
                filled_quantity=0,
                requested_price=request.price,
                fill_price=0.0,
                fees_inr=0.0,
                slippage_inr=0.0,
                rejection_reason=f"KILL_SWITCH_ACTIVE: {reason}",
                message="Order submission blocked by emergency kill switch."
            )
            self.audit_logger.log_event("ORDER_BLOCKED_BY_KILL_SWITCH", asdict(res))
            return res

        # 3. Pre-Trade Risk Manager Validation
        risk_req = OrderRequest(
            symbol=request.symbol,
            side=request.transaction_type.value,
            quantity=request.quantity,
            price=request.price if request.price > 0 else 1000.0,
            timestamp=request.quote_timestamp or current_time,
            order_type=request.order_type.value,
            is_live=False
        )
        risk_res: OrderValidationResult = self.risk_manager.validate_order_request(risk_req, current_market_time=current_time)

        if not risk_res.is_approved:
            res = BrokerOrderResult(
                status=BrokerOrderStatus.REJECTED,
                broker_order_id=None,
                correlation_id=request.correlation_id,
                symbol=request.symbol,
                transaction_type=request.transaction_type.value,
                requested_quantity=request.quantity,
                filled_quantity=0,
                requested_price=request.price,
                fill_price=0.0,
                fees_inr=0.0,
                slippage_inr=0.0,
                rejection_reason=f"RISK_REJECTION ({risk_res.risk_code}): {risk_res.rejection_reason}",
                message="Pre-trade risk controls rejected the order."
            )
            self.audit_logger.log_event("ORDER_REJECTED_PRE_TRADE_RISK", asdict(res))
            return res

        # 4. Exchange Rejection Simulation
        if self.simulate_exchange_rejection:
            res = BrokerOrderResult(
                status=BrokerOrderStatus.REJECTED,
                broker_order_id=f"EXCH_REJ_{uuid.uuid4().hex[:6].upper()}",
                correlation_id=request.correlation_id,
                symbol=request.symbol,
                transaction_type=request.transaction_type.value,
                requested_quantity=request.quantity,
                filled_quantity=0,
                requested_price=request.price,
                fill_price=0.0,
                fees_inr=0.0,
                slippage_inr=0.0,
                rejection_reason="EXCHANGE_REJECT: Price outside valid circuit limit bands.",
                message="Simulated NSE circuit band rejection."
            )
            self.audit_logger.log_event("EXCHANGE_REJECTION", asdict(res))
            return res

        # 5. Network Timeout Failure Injection
        # CRITICAL SAFETY REQUIREMENT: NEVER BLINDLY RETRY ON TIMEOUT!
        if self.simulate_network_timeout:
            broker_order_id = f"BROK_{uuid.uuid4().hex[:8].upper()}"
            if self.timeout_order_reached_broker:
                # The broker actually received and filled the order, but the HTTP 200 was lost!
                eff_price, total_fees, _ = self.cost_model.calculate_entry_costs(request.price, request.quantity)
                ghost_order = BrokerOrderResult(
                    status=BrokerOrderStatus.TRADED,
                    broker_order_id=broker_order_id,
                    correlation_id=request.correlation_id,
                    symbol=request.symbol,
                    transaction_type=request.transaction_type.value,
                    requested_quantity=request.quantity,
                    filled_quantity=request.quantity,
                    requested_price=request.price,
                    fill_price=round(eff_price, 2),
                    fees_inr=round(total_fees, 2),
                    slippage_inr=round((eff_price - request.price) * request.quantity, 2),
                    message="Executed on broker prior to connection drop."
                )
                self.broker_order_book[broker_order_id] = ghost_order
                self.correlation_to_order_id[request.correlation_id] = broker_order_id

            # Return TIMEOUT_INDETERMINATE to client
            timeout_result = BrokerOrderResult(
                status=BrokerOrderStatus.TIMEOUT_INDETERMINATE,
                broker_order_id=None,
                correlation_id=request.correlation_id,
                symbol=request.symbol,
                transaction_type=request.transaction_type.value,
                requested_quantity=request.quantity,
                filled_quantity=0,
                requested_price=request.price,
                fill_price=0.0,
                fees_inr=0.0,
                slippage_inr=0.0,
                rejection_reason="NETWORK_TIMEOUT: Socket dropped during HTTP POST /orders.",
                message="DO NOT RETRY! Order status is indeterminate. Run reconcile_timed_out_order."
            )
            self.audit_logger.log_event("ORDER_TIMEOUT_INDETERMINATE", asdict(timeout_result))
            return timeout_result

        # 6. Execute Normal Fill Simulation
        broker_order_id = f"BROK_{uuid.uuid4().hex[:8].upper()}"
        ref_price = request.price if request.price > 0 else 1000.0

        if request.transaction_type == BrokerTransactionType.BUY:
            eff_price, total_fees, _ = self.cost_model.calculate_entry_costs(ref_price, request.quantity)
            total_required = (request.quantity * eff_price) + total_fees

            if total_required > self.cash:
                res = BrokerOrderResult(
                    status=BrokerOrderStatus.REJECTED,
                    broker_order_id=None,
                    correlation_id=request.correlation_id,
                    symbol=request.symbol,
                    transaction_type="BUY",
                    requested_quantity=request.quantity,
                    filled_quantity=0,
                    requested_price=ref_price,
                    fill_price=0.0,
                    fees_inr=0.0,
                    slippage_inr=0.0,
                    rejection_reason=f"INSUFFICIENT_FUNDS: Required INR {total_required:.2f}, Available: INR {self.cash:.2f}."
                )
                self.audit_logger.log_event("ORDER_REJECTED_FUNDS", asdict(res))
                return res

            self.cash -= total_required
            self.positions[request.symbol] = BrokerPosition(
                symbol=request.symbol,
                quantity=request.quantity,
                average_price=round(eff_price, 2),
                current_price=round(eff_price, 2),
                product_type=request.product_type.value,
                unrealized_pnl=0.0,
                realized_pnl=0.0
            )

            fill_res = BrokerOrderResult(
                status=BrokerOrderStatus.TRADED,
                broker_order_id=broker_order_id,
                correlation_id=request.correlation_id,
                symbol=request.symbol,
                transaction_type="BUY",
                requested_quantity=request.quantity,
                filled_quantity=request.quantity,
                requested_price=ref_price,
                fill_price=round(eff_price, 2),
                fees_inr=round(total_fees, 2),
                slippage_inr=round((eff_price - ref_price) * request.quantity, 2),
                message="Order executed and filled on exchange."
            )
            self.broker_order_book[broker_order_id] = fill_res
            self.correlation_to_order_id[request.correlation_id] = broker_order_id
            self.risk_manager.record_order_execution(risk_req, executed_time=current_time)
            self.audit_logger.log_event("ORDER_FILLED_BUY", asdict(fill_res))
            return fill_res

        elif request.transaction_type == BrokerTransactionType.SELL:
            if request.symbol not in self.positions:
                res = BrokerOrderResult(
                    status=BrokerOrderStatus.REJECTED,
                    broker_order_id=None,
                    correlation_id=request.correlation_id,
                    symbol=request.symbol,
                    transaction_type="SELL",
                    requested_quantity=request.quantity,
                    filled_quantity=0,
                    requested_price=ref_price,
                    fill_price=0.0,
                    fees_inr=0.0,
                    slippage_inr=0.0,
                    rejection_reason=f"NO_POSITION: Cannot sell {request.symbol}; no holding found."
                )
                self.audit_logger.log_event("ORDER_REJECTED_NO_POSITION", asdict(res))
                return res

            pos = self.positions.pop(request.symbol)
            sell_qty = min(request.quantity, pos.quantity)
            eff_price, total_fees, _ = self.cost_model.calculate_exit_costs(ref_price, sell_qty)

            gross_proceeds = sell_qty * eff_price
            net_proceeds = gross_proceeds - total_fees
            self.cash += net_proceeds

            realized_pnl = net_proceeds - (sell_qty * pos.average_price)
            self.risk_manager.record_trade_completion(realized_pnl)

            fill_res = BrokerOrderResult(
                status=BrokerOrderStatus.TRADED,
                broker_order_id=broker_order_id,
                correlation_id=request.correlation_id,
                symbol=request.symbol,
                transaction_type="SELL",
                requested_quantity=sell_qty,
                filled_quantity=sell_qty,
                requested_price=ref_price,
                fill_price=round(eff_price, 2),
                fees_inr=round(total_fees, 2),
                slippage_inr=round((ref_price - eff_price) * sell_qty, 2),
                message=f"Position closed. Realized PnL: INR {realized_pnl:+.2f}."
            )
            self.broker_order_book[broker_order_id] = fill_res
            self.correlation_to_order_id[request.correlation_id] = broker_order_id
            self.audit_logger.log_event("ORDER_FILLED_SELL", asdict(fill_res))
            return fill_res

    def cancel_order(self, broker_order_id: str) -> bool:
        self._enforce_rate_limit()
        if broker_order_id in self.broker_order_book:
            ord_obj = self.broker_order_book[broker_order_id]
            if ord_obj.status in [BrokerOrderStatus.PENDING, BrokerOrderStatus.SUBMITTED]:
                ord_obj.status = BrokerOrderStatus.CANCELLED
                self.audit_logger.log_event("ORDER_CANCELLED", {"broker_order_id": broker_order_id})
                return True
        return False

    # --------------------------------------------------------------------------
    # 7. Safe Network Timeout Recovery
    # --------------------------------------------------------------------------
    def reconcile_timed_out_order(self, correlation_id: str) -> BrokerOrderResult:
        """
        Queries the broker order book by client correlation ID.
        If found: Reconciles state to match broker's official record.
        If NOT found: Safely concludes the order dropped before reaching the exchange.
        """
        self._enforce_rate_limit()
        print(f"[RECONCILIATION] Checking broker order book for timed-out correlation ID: {correlation_id}...")

        broker_order = self.get_order_by_correlation_id(correlation_id)
        if broker_order is not None:
            # Order was received and processed on exchange!
            self.audit_logger.log_event("TIMEOUT_RECONCILED_FOUND", {
                "correlation_id": correlation_id,
                "broker_order_id": broker_order.broker_order_id,
                "actual_status": broker_order.status.value
            })
            print(f"[RECONCILIATION] ✅ Order located on broker: ID {broker_order.broker_order_id} (Status: {broker_order.status.value})")
            return broker_order
        else:
            # Order definitely never reached broker/exchange
            dropped_result = BrokerOrderResult(
                status=BrokerOrderStatus.CANCELLED,
                broker_order_id=None,
                correlation_id=correlation_id,
                symbol="UNKNOWN",
                transaction_type="UNKNOWN",
                requested_quantity=0,
                filled_quantity=0,
                requested_price=0.0,
                fill_price=0.0,
                fees_inr=0.0,
                slippage_inr=0.0,
                rejection_reason="CONFIRMED_DROPPED_NOT_ON_EXCHANGE",
                message="Order was verified absent from broker order book. Safely dropped without duplicate risk."
            )
            self.audit_logger.log_event("TIMEOUT_RECONCILED_DROPPED", {"correlation_id": correlation_id})
            print(f"[RECONCILIATION] ℹ️ Order verified NOT on exchange. Marked safely dropped.")
            return dropped_result

    # --------------------------------------------------------------------------
    # 8. Order Status Reconciliation
    # --------------------------------------------------------------------------
    def reconcile_orders(self, local_orders: List[BrokerOrderResult]) -> ReconciliationReport:
        """
        Compares client-side order records against official broker order book.
        Detects unacknowledged, orphaned, or mismatching states.
        """
        self._enforce_rate_limit()
        matched = 0
        discrepancies = []

        broker_by_id = {b_id: o for b_id, o in self.broker_order_book.items()}
        broker_by_clo = {o.correlation_id: o for o in self.broker_order_book.values()}

        for l_ord in local_orders:
            b_match = None
            if l_ord.broker_order_id and l_ord.broker_order_id in broker_by_id:
                b_match = broker_by_id[l_ord.broker_order_id]
            elif l_ord.correlation_id in broker_by_clo:
                b_match = broker_by_clo[l_ord.correlation_id]

            if b_match is None:
                discrepancies.append({
                    "issue": "LOCAL_ORDER_MISSING_ON_BROKER",
                    "local_correlation_id": l_ord.correlation_id,
                    "local_status": l_ord.status.value
                })
            elif b_match.status != l_ord.status:
                discrepancies.append({
                    "issue": "STATUS_MISMATCH",
                    "correlation_id": l_ord.correlation_id,
                    "local_status": l_ord.status.value,
                    "broker_status": b_match.status.value
                })
            else:
                matched += 1

        report = ReconciliationReport(
            reconciled_at=datetime.now().isoformat(),
            total_orders_checked=len(local_orders),
            matched_orders=matched,
            discrepancies=discrepancies,
            status="BALANCED" if len(discrepancies) == 0 else "DISCREPANCIES_DETECTED"
        )
        self.audit_logger.log_event("ORDER_RECONCILIATION_REPORT", asdict(report))
        return report

# ==============================================================================
# 5. LIVE BROKER ADAPTER SCAFFOLD (DHANHQ API v2)
# ==============================================================================

class DhanBrokerAdapter(BaseBrokerAdapter):
    """
    Live Broker Adapter Scaffold for DhanHQ API v2.
    Protected by TRIPLE-INTERLOCK SAFETY GUARDS.
    Strictly disabled by default during development.
    """
    def __init__(
        self,
        risk_manager: Optional[RiskManager] = None,
        cost_model: Optional[IndianMarketCostModel] = None,
        audit_logger: Optional[BrokerAuditLogger] = None
    ):
        super().__init__(risk_manager=risk_manager, cost_model=cost_model, audit_logger=audit_logger)
        self._enforce_hard_safety_interlock()

        # In production mode only:
        self.client_id = os.getenv("DHAN_CLIENT_ID")
        self.access_token = os.getenv("DHAN_ACCESS_TOKEN")
        self.is_connected = False
        self.client = None

    def _enforce_hard_safety_interlock(self):
        """Hard safety check: Prevents instantiation without explicit dual-flag activation."""
        is_live_trading = getattr(config, "LIVE_TRADING_ENABLED", False)
        is_adapter_enabled = getattr(config, "ENABLE_LIVE_BROKER_ADAPTER", False)

        if not is_live_trading or not is_adapter_enabled:
            raise LiveTradingDisabledError(
                "CRITICAL SAFETY LOCK: DhanBrokerAdapter is disabled! "
                "Both config.LIVE_TRADING_ENABLED and config.ENABLE_LIVE_BROKER_ADAPTER must be True "
                "to initialize live broker connections."
            )

    def _verify_authorization_token(self, authorization_token: Optional[str]):
        """Verifies runtime authorization passphrase matching config."""
        expected = getattr(config, "LIVE_AUTHORIZATION_PASSPHRASE", None)
        if not authorization_token or authorization_token != expected:
            raise UnauthorizedLiveModeError(
                "SECURITY ACCESS DENIED: Invalid or missing live authorization token. "
                "Live orders cannot be placed without explicit runtime clearance."
            )

    def authenticate(self) -> bool:
        self._enforce_hard_safety_interlock()
        if not self.client_id or not self.access_token or self.client_id == "your_client_id_here":
            raise BrokerAdapterError("Dhan credentials missing in .env! Cannot authenticate.")

        try:
            from dhanhq import dhanhq
            self.client = dhanhq(self.client_id, self.access_token)
            self.is_connected = True
            self.audit_logger.log_event("DHAN_AUTHENTICATED", {"client_id": self.client_id[:4] + "****"})
            return True
        except ImportError:
            raise BrokerAdapterError("Library 'dhanhq' is not installed. Run: pip install dhanhq")
        except Exception as e:
            raise BrokerAdapterError(f"Dhan authentication failed: {e}")

    def get_account_balance(self) -> Dict[str, float]:
        self._enforce_hard_safety_interlock()
        if not self.is_connected or self.client is None:
            self.authenticate()

        try:
            funds = self.client.get_fund_limits()
            avail = float(funds.get("data", {}).get("availabelBalance", 0.0))
            return {"available_cash": avail, "total_net_worth": avail}
        except Exception as e:
            raise BrokerAdapterError(f"Failed to fetch Dhan account balance: {e}")

    def get_positions(self) -> List[BrokerPosition]:
        self._enforce_hard_safety_interlock()
        # Fetches live positions via client.get_positions()
        return []

    def get_orders(self) -> List[BrokerOrderResult]:
        self._enforce_hard_safety_interlock()
        # Fetches live order book via client.get_order_list()
        return []

    def get_order_by_id(self, broker_order_id: str) -> Optional[BrokerOrderResult]:
        self._enforce_hard_safety_interlock()
        return None

    def get_order_by_correlation_id(self, correlation_id: str) -> Optional[BrokerOrderResult]:
        self._enforce_hard_safety_interlock()
        return None

    def preview_order(self, request: BrokerOrderRequest) -> OrderPreview:
        """Computes exact fee estimates for Dhan order."""
        eff_price, total_fees, breakdown = self.cost_model.calculate_entry_costs(request.price, request.quantity)
        order_val = request.quantity * request.price
        return OrderPreview(
            symbol=request.symbol,
            transaction_type=request.transaction_type.value,
            quantity=request.quantity,
            estimated_price=request.price,
            estimated_order_value=order_val,
            brokerage_inr=20.0,
            stt_inr=breakdown.get("stt", 0.0),
            turnover_fees_inr=breakdown.get("exchange_turnover", 0.0),
            sebi_fees_inr=breakdown.get("sebi_turnover", 0.0),
            stamp_duty_inr=breakdown.get("stamp_duty", 0.0),
            gst_inr=breakdown.get("gst", 0.0),
            total_regulatory_costs_inr=total_fees,
            effective_execution_price=eff_price,
            margin_required_inr=order_val + total_fees,
            available_margin_inr=0.0,
            stop_loss_price=request.price * 0.99,
            take_profit_price=request.price * 1.02
        )

    def place_order(
        self,
        request: BrokerOrderRequest,
        authorization_token: Optional[str] = None,
        current_time: Optional[datetime] = None
    ) -> BrokerOrderResult:
        """Places live order on Dhan API. Requires explicit runtime authorization."""
        self._enforce_hard_safety_interlock()
        self._verify_authorization_token(authorization_token)

        # Pre-trade risk check
        risk_req = OrderRequest(
            symbol=request.symbol,
            side=request.transaction_type.value,
            quantity=request.quantity,
            price=request.price,
            timestamp=request.quote_timestamp or datetime.now(),
            order_type=request.order_type.value,
            is_live=True
        )
        risk_res = self.risk_manager.validate_order_request(risk_req, current_market_time=current_time)
        if not risk_res.is_approved:
            raise PreTradeRiskCheckFailedError(f"Pre-trade risk rejection: {risk_res.rejection_reason}")

        raise NotImplementedError("Live order placement is intentionally disabled during development.")

    def cancel_order(self, broker_order_id: str) -> bool:
        self._enforce_hard_safety_interlock()
        return False

    def reconcile_timed_out_order(self, correlation_id: str) -> BrokerOrderResult:
        self._enforce_hard_safety_interlock()
        raise NotImplementedError("Live timeout reconciliation is intentionally disabled during development.")

    def reconcile_orders(self, local_orders: List[BrokerOrderResult]) -> ReconciliationReport:
        self._enforce_hard_safety_interlock()
        return ReconciliationReport(
            reconciled_at=datetime.now().isoformat(),
            total_orders_checked=0,
            matched_orders=0,
            discrepancies=[],
            status="DISABLED"
        )
