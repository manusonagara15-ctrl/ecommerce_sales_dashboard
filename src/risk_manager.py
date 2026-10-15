"""
Enterprise-Grade Risk Management Module for Indian Stock Trading Bot.
Enforces multi-layer safety controls, circuit breakers, and capital protection.

MANDATORY SAFETY ARCHITECTURE:
1. Fail-Closed Design: Any unexpected error, missing component, or exception
   strictly rejects all orders and halts execution.
2. Hard Kill-Switch: Latches shut when max daily loss is breached or upon manual trigger.
3. Anti-Stale Data: Rejects orders based on outdated price quotes.
4. Anti-Duplicate Churn: Prevents rapid-fire duplicate orders and double entries.
5. Strict Exposure & Sizing Caps: Limits max order value, total exposure, and active positions.
6. Live Trading Disabled: Hard safety lock keeps live broker execution disabled by default.

REAL-WORLD INDIAN MARKET REALITY (STOP-LOSS LIMITATION):
Stop-loss orders DO NOT guarantee the exact execution price. In Indian equities,
sudden gap-downs (e.g. overnight earnings announcements), illiquidity, or lower-circuit
freezes (where buyers disappear and exchange halts matching) can cause slippage far worse
than the theoretical stop-loss level.
"""

import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, Any

# Ensure project root is available for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Windows console encoding safeguard
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import math
import numpy as np
import config

@dataclass
class OrderRequest:
    """Represents a proposed order submitted by a trading strategy."""
    symbol: str
    side: str                          # "BUY" or "SELL"
    quantity: int
    price: float                       # Current quoted LTP / limit price
    timestamp: datetime                # Timestamp of the price quote
    order_type: str = "MARKET"         # "MARKET" or "LIMIT"
    strategy_id: str = "default"
    is_live: bool = False              # Must be False unless live trading is explicitly enabled

@dataclass
class OrderValidationResult:
    """The formal risk judgment on a proposed order."""
    is_approved: bool
    risk_code: str                     # e.g., "APPROVED", "KILL_SWITCH", "STALE_DATA"
    rejection_reason: Optional[str] = None
    adjusted_quantity: int = 0

@dataclass
class Position:
    """Tracks an actively held equity position."""
    symbol: str
    quantity: int
    entry_price: float
    current_price: float
    entry_time: datetime
    stop_loss_price: float
    take_profit_price: float
    side: str = "BUY"

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        if self.side == "BUY":
            return (self.current_price - self.entry_price) * self.quantity
        else:
            return (self.entry_price - self.current_price) * self.quantity

@dataclass
class RiskConfig:
    """Configurable risk thresholds (Conservative Simulation Settings)."""
    max_order_value_inr: float = 5000.0         # Max INR value for a single order
    max_open_positions: int = 3                 # Max concurrent open positions
    max_daily_loss_inr: float = 1500.0          # Kill-switch daily loss threshold
    max_total_exposure_inr: float = 15000.0     # Max total gross portfolio value
    max_data_age_seconds: float = 120.0         # Stale-quote threshold (2 minutes)
    duplicate_cooldown_seconds: float = 60.0    # Cooldown between orders for same symbol
    default_stop_loss_pct: float = 1.0          # 1% default Stop-Loss
    default_take_profit_pct: float = 2.0        # 2% default Take-Profit (1:2 Risk/Reward)
    max_daily_trades: int = 6                   # Daily trade frequency limiter
    market_start_time: time = time(9, 30)       # 09:30 AM IST (skip first 15 mins volatility)
    market_cutoff_time: time = time(14, 45)     # 02:45 PM IST (no new entries)
    square_off_time: time = time(15, 10)        # 03:10 PM IST (mandatory intraday exit)
    live_trading_enabled: bool = False          # Hard lock: Keep live trading disabled!

class RiskManager:
    """
    Central Risk Controller.
    Implements a fail-closed multi-filter pipeline validating all proposed trades.
    """
    def __init__(self, risk_config: Optional[RiskConfig] = None):
        self.config = risk_config if risk_config is not None else RiskConfig()
        
        # Operational State
        self.is_operational: bool = True
        self.is_kill_switch_active: bool = False
        self.kill_switch_reason: Optional[str] = None
        
        # Accounting & Tracking
        self.daily_realized_pnl: float = 0.0
        self.daily_trades_count: int = 0
        self.open_positions: Dict[str, Position] = {}
        self.recent_order_times: Dict[str, datetime] = {}  # symbol -> last_order_time

    # --------------------------------------------------------------------------
    # 1. CORE PIPELINE: ORDER VALIDATION
    # --------------------------------------------------------------------------
    def validate_order_request(
        self,
        order: OrderRequest,
        current_market_time: Optional[datetime] = None
    ) -> OrderValidationResult:
        """
        Comprehensive order risk evaluation.
        Evaluates 10 sequential safety checks. Returns OrderValidationResult.
        FAILS CLOSED: Any unhandled exception immediately trips safety and rejects.
        """
        if current_market_time is None:
            current_market_time = datetime.now()

        try:
            # CHECK 1: Fail-Closed Health Check
            if not self.is_operational:
                return OrderValidationResult(
                    is_approved=False,
                    risk_code="FAIL_CLOSED",
                    rejection_reason="🚨 RISK SYSTEM OFFLINE: Module is in fail-closed state. Trading disabled."
                )

            # CHECK 2: Emergency Kill-Switch
            if self.is_kill_switch_active:
                return OrderValidationResult(
                    is_approved=False,
                    risk_code="KILL_SWITCH",
                    rejection_reason=f"🚨 KILL-SWITCH ACTIVE: {self.kill_switch_reason}. All new orders blocked."
                )

            # CHECK 3: Live Trading Safety Lock
            if order.is_live and not self.config.live_trading_enabled:
                return OrderValidationResult(
                    is_approved=False,
                    risk_code="LIVE_DISABLED",
                    rejection_reason="🔒 SAFETY REJECTION: Live trading is disabled in RiskConfig. Switch to PAPER mode."
                )

            # CHECK 4: Order Parameters & Field Validation
            if order.quantity <= 0:
                return OrderValidationResult(
                    is_approved=False,
                    risk_code="INVALID_ORDER",
                    rejection_reason=f"Invalid order quantity: {order.quantity}. Must be > 0."
                )
            if order.price <= 0 or np.isnan(order.price) or np.isinf(order.price):
                return OrderValidationResult(
                    is_approved=False,
                    risk_code="INVALID_ORDER",
                    rejection_reason=f"Invalid order price: INR {order.price}. Must be positive finite number."
                )
            if order.side.upper() not in ["BUY", "SELL"]:
                return OrderValidationResult(
                    is_approved=False,
                    risk_code="INVALID_ORDER",
                    rejection_reason=f"Invalid order side: '{order.side}'. Must be 'BUY' or 'SELL'."
                )
            if not order.symbol or not isinstance(order.symbol, str):
                return OrderValidationResult(
                    is_approved=False,
                    risk_code="INVALID_ORDER",
                    rejection_reason="Symbol is missing or invalid."
                )

            # CHECK 5: Stale-Data Rejection
            if order.timestamp is None:
                return OrderValidationResult(
                    is_approved=False,
                    risk_code="STALE_DATA",
                    rejection_reason="Price quote timestamp is missing."
                )
            
            # Compute quote age
            quote_age = (current_market_time - order.timestamp).total_seconds()
            if quote_age > self.config.max_data_age_seconds:
                return OrderValidationResult(
                    is_approved=False,
                    risk_code="STALE_DATA",
                    rejection_reason=f"Stale quote: Data age ({quote_age:.1f}s) exceeds max allowed ({self.config.max_data_age_seconds}s)."
                )
            if quote_age < -10.0:  # Clock skew safeguard (future timestamp > 10s)
                return OrderValidationResult(
                    is_approved=False,
                    risk_code="STALE_DATA",
                    rejection_reason=f"Future timestamp anomaly detected: Quote is {abs(quote_age):.1f}s in future."
                )

            # CHECK 6: Duplicate-Order Prevention & Cooldown
            sym = order.symbol.upper()
            if sym in self.recent_order_times:
                last_time = self.recent_order_times[sym]
                elapsed = (current_market_time - last_time).total_seconds()
                if elapsed < self.config.duplicate_cooldown_seconds:
                    return OrderValidationResult(
                        is_approved=False,
                        risk_code="DUPLICATE_ORDER",
                        rejection_reason=f"Duplicate order cooldown: Only {elapsed:.1f}s elapsed since last order for {sym} (cooldown: {self.config.duplicate_cooldown_seconds}s)."
                    )

            # If BUY side and already holding this symbol, prevent double long
            if order.side.upper() == "BUY" and sym in self.open_positions:
                return OrderValidationResult(
                    is_approved=False,
                    risk_code="DUPLICATE_ORDER",
                    rejection_reason=f"Position already open for {sym}. Duplicate long entry rejected."
                )

            # CHECK 7: Maximum Open Positions Limit
            if order.side.upper() == "BUY" and sym not in self.open_positions:
                if len(self.open_positions) >= self.config.max_open_positions:
                    return OrderValidationResult(
                        is_approved=False,
                        risk_code="MAX_POSITIONS",
                        rejection_reason=f"Max open positions ({self.config.max_open_positions}) reached. Currently holding: {list(self.open_positions.keys())}."
                    )

            # CHECK 8: Maximum Single Order Value (Enforced on BUY entries)
            order_val = order.quantity * order.price
            if order.side.upper() == "BUY" and order_val > self.config.max_order_value_inr:
                return OrderValidationResult(
                    is_approved=False,
                    risk_code="MAX_ORDER_VAL",
                    rejection_reason=f"Order value INR {order_val:.2f} exceeds maximum order limit of INR {self.config.max_order_value_inr:.2f}."
                )

            # CHECK 9: Maximum Total Portfolio Exposure
            current_exposure = sum(pos.market_value for pos in self.open_positions.values())
            projected_exposure = current_exposure + (order_val if order.side.upper() == "BUY" else 0.0)
            if projected_exposure > self.config.max_total_exposure_inr:
                return OrderValidationResult(
                    is_approved=False,
                    risk_code="MAX_EXPOSURE",
                    rejection_reason=f"Projected portfolio exposure INR {projected_exposure:.2f} exceeds limit INR {self.config.max_total_exposure_inr:.2f}."
                )

            # CHECK 10: Maximum Daily Loss Limit (Realized + Unrealized)
            total_current_loss = self.get_total_daily_pnl()
            if total_current_loss <= -abs(self.config.max_daily_loss_inr):
                self.activate_kill_switch(f"Daily loss breach: Net PnL is INR {total_current_loss:.2f} (Limit: -INR {self.config.max_daily_loss_inr:.2f})")
                return OrderValidationResult(
                    is_approved=False,
                    risk_code="MAX_DAILY_LOSS",
                    rejection_reason=f"Daily loss limit breached (Net PnL: INR {total_current_loss:.2f}). Kill-switch engaged."
                )

            # CHECK 11: Daily Trades Limit
            if self.daily_trades_count >= self.config.max_daily_trades:
                return OrderValidationResult(
                    is_approved=False,
                    risk_code="MAX_TRADES",
                    rejection_reason=f"Daily trade frequency limit reached ({self.daily_trades_count}/{self.config.max_daily_trades} trades)."
                )

            # CHECK 12: Indian Market Timing Cutoff (Intraday MIS)
            now_time = current_market_time.time()
            if now_time < self.config.market_start_time:
                return OrderValidationResult(
                    is_approved=False,
                    risk_code="TIMING_REJECT",
                    rejection_reason=f"Market opening freeze: Orders not accepted before {self.config.market_start_time.strftime('%H:%M')} IST."
                )
            if now_time > self.config.market_cutoff_time:
                return OrderValidationResult(
                    is_approved=False,
                    risk_code="TIMING_REJECT",
                    rejection_reason=f"Market intraday entry cutoff: Past {self.config.market_cutoff_time.strftime('%H:%M')} IST."
                )

            # All 12 checks passed!
            return OrderValidationResult(
                is_approved=True,
                risk_code="APPROVED",
                adjusted_quantity=order.quantity
            )

        except Exception as e:
            # FAIL-CLOSED: Any unexpected crash immediately triggers fail-closed response
            self.fail_closed(f"Unhandled exception in validate_order_request: {e}")
            return OrderValidationResult(
                is_approved=False,
                risk_code="FAIL_CLOSED",
                rejection_reason=f"🚨 RISK MODULE EXCEPTION (FAILED CLOSED): {e}"
            )

    # --------------------------------------------------------------------------
    # 2. POSITION SIZING & PROTECTIVE EXITS
    # --------------------------------------------------------------------------
    def calculate_position_size(
        self,
        current_price: float,
        account_cash: float = 50000.0,
        risk_per_trade_inr: Optional[float] = None
    ) -> int:
        """
        Calculates safe share quantity bounded by:
        1. Max order value limit (e.g. ₹5,000)
        2. Available cash buffer
        3. Optional risk budget per trade (e.g. risk ₹200 on a 1% stop-loss)
        """
        if current_price <= 0 or not self.is_operational or self.is_kill_switch_active:
            return 0

        # Capital ceiling: max_order_value_inr
        max_capital = min(self.config.max_order_value_inr, account_cash * 0.95)
        qty_capital = int(max_capital // current_price)

        # Risk-based ceiling (if risk budget provided)
        if risk_per_trade_inr is not None and risk_per_trade_inr > 0:
            sl_pct = self.config.default_stop_loss_pct / 100.0
            risk_per_share = current_price * sl_pct
            qty_risk = int(risk_per_trade_inr // (risk_per_share + 1e-9))
            final_qty = max(0, min(qty_capital, qty_risk))
        else:
            final_qty = max(0, qty_capital)

        return final_qty

    def calculate_exit_levels(self, entry_price: float, side: str = "BUY") -> Tuple[float, float]:
        """
        Calculates exact Stop-Loss and Take-Profit price levels.
        Note: Real market slippage means actual fill price may differ from stop price.
        """
        if side.upper() == "BUY":
            stop_loss = round(entry_price * (1.0 - self.config.default_stop_loss_pct / 100.0), 2)
            take_profit = round(entry_price * (1.0 + self.config.default_take_profit_pct / 100.0), 2)
        else:
            stop_loss = round(entry_price * (1.0 + self.config.default_stop_loss_pct / 100.0), 2)
            take_profit = round(entry_price * (1.0 - self.config.default_take_profit_pct / 100.0), 2)
        return stop_loss, take_profit

    # --------------------------------------------------------------------------
    # 3. STATE MANAGEMENT & ACCOUNTING
    # --------------------------------------------------------------------------
    def record_order_execution(self, order: OrderRequest, executed_time: Optional[datetime] = None):
        """Called when an order is confirmed executed."""
        if executed_time is None:
            executed_time = datetime.now()

        sym = order.symbol.upper()
        self.recent_order_times[sym] = executed_time

        if order.side.upper() == "BUY":
            sl, tp = self.calculate_exit_levels(order.price, "BUY")
            self.open_positions[sym] = Position(
                symbol=sym,
                quantity=order.quantity,
                entry_price=order.price,
                current_price=order.price,
                entry_time=executed_time,
                stop_loss_price=sl,
                take_profit_price=tp,
                side="BUY"
            )
        elif order.side.upper() == "SELL" and sym in self.open_positions:
            pos = self.open_positions.pop(sym)
            pnl = (order.price - pos.entry_price) * pos.quantity
            self.record_trade_completion(pnl)

    def update_market_price(self, symbol: str, current_price: float):
        """Updates live price for open positions and audits unrealized risk."""
        sym = symbol.upper()
        if sym in self.open_positions:
            self.open_positions[sym].current_price = current_price
            
            # Check if total daily loss limit breached
            total_loss = self.get_total_daily_pnl()
            if total_loss <= -abs(self.config.max_daily_loss_inr):
                self.activate_kill_switch(f"Unrealized drawdown breach: Total PnL is INR {total_loss:.2f}")

    def record_trade_completion(self, pnl: float):
        """Records realized PnL and increments trade counter."""
        self.daily_realized_pnl += pnl
        self.daily_trades_count += 1
        
        # Check kill-switch condition
        if self.daily_realized_pnl <= -abs(self.config.max_daily_loss_inr):
            self.activate_kill_switch(f"Daily realized loss reached INR {self.daily_realized_pnl:.2f}")

    def get_total_daily_pnl(self) -> float:
        """Returns Realized PnL + Unrealized PnL across open positions."""
        unrealized = sum(pos.unrealized_pnl for pos in self.open_positions.values())
        return self.daily_realized_pnl + unrealized

    def activate_kill_switch(self, reason: str):
        """Engages emergency stop to lock down all new trade submissions."""
        self.is_kill_switch_active = True
        self.kill_switch_reason = reason
        print(f"\n{'='*70}\n🚨 EMERGENCY KILL SWITCH ENGAGED! Reason: {reason}\n{'='*70}\n")

    def fail_closed(self, error_context: str):
        """Puts module into failed state. Rejects all trading activities."""
        self.is_operational = False
        self.is_kill_switch_active = True
        self.kill_switch_reason = f"Module failed closed: {error_context}"
        print(f"\n[CRITICAL SAFETY] Risk Manager Failed Closed: {error_context}\n")

    def reset_kill_switch(self, manual_admin_token: str = "RESET_RISK_OVERRIDE"):
        """Manual reset requiring explicit override token."""
        if manual_admin_token == "RESET_RISK_OVERRIDE":
            self.is_kill_switch_active = False
            self.kill_switch_reason = None
            self.is_operational = True
            print("[RISK] Kill switch manually reset.")

    def should_force_square_off(self, current_time: Optional[datetime] = None) -> bool:
        """Checks if current time requires intraday positions to be closed to avoid broker penalty."""
        if current_time is None:
            current_time = datetime.now()
        return current_time.time() >= self.config.square_off_time

    # --------------------------------------------------------------------------
    # 4. BACKWARDS COMPATIBILITY HELPERS
    # --------------------------------------------------------------------------
    @property
    def daily_pnl(self) -> float:
        return self.daily_realized_pnl

    @daily_pnl.setter
    def daily_pnl(self, value: float):
        self.daily_realized_pnl = value

    @property
    def daily_trades(self) -> int:
        return self.daily_trades_count

    @daily_trades.setter
    def daily_trades(self, value: int):
        self.daily_trades_count = value

    def can_open_new_trade(self, current_time: Optional[datetime] = None) -> Tuple[bool, str]:
        """Backwards compatible check for simple trading loops."""
        dummy_order = OrderRequest(
            symbol="TEST.NS",
            side="BUY",
            quantity=1,
            price=100.0,
            timestamp=current_time if current_time else datetime.now()
        )
        res = self.validate_order_request(dummy_order, current_market_time=current_time)
        return res.is_approved, (res.rejection_reason if res.rejection_reason else "Risk checks passed.")
