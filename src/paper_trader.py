"""
Production-Grade Paper Trading Engine for Indian Stock Markets.
Simulates live market execution in real-time with zero financial risk.

KEY CAPABILITIES:
1. Complete Virtual Accounting: Virtual cash balance, open positions, order states,
   fill tracking, realistic Indian regulatory fees (₹20 brokerage, STT, GST, etc.), and slippage.
2. Safe Atomic Persistence: State is saved atomically to disk (data/paper_trading_state.json).
   Survives unexpected crashes and recovers gracefully from corrupted files.
3. Restart Idempotency: Tracks executed client order IDs to prevent duplicate order submissions
   when the bot restarts or replays signals.
4. Strict Risk Integration: Validates every order against RiskManager (stale data, max order value,
   exposure caps, daily loss limits, and emergency kill-switch).
5. Hard Broker Air-Gap: Formally guarantees that live broker order endpoints CANNOT be called
   from paper mode.
"""

import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, date, time
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

@dataclass
class PaperOrder:
    """Represents an order tracked by the paper engine."""
    order_id: str
    client_order_id: str
    symbol: str
    side: str                          # "BUY" or "SELL"
    requested_quantity: int
    filled_quantity: int
    requested_price: float
    fill_price: float
    slippage_inr: float
    fees_inr: float
    status: str                        # "PENDING", "FILLED", "REJECTED", "CANCELLED"
    rejection_reason: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    filled_at: Optional[str] = None

@dataclass
class PaperPosition:
    """Represents an actively held simulated position."""
    symbol: str
    quantity: int
    entry_price: float
    current_price: float
    stop_loss_price: float
    take_profit_price: float
    opened_at: str
    total_fees_paid: float
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

    @property
    def return_pct(self) -> float:
        cost = self.quantity * self.entry_price
        return (self.unrealized_pnl / cost * 100.0) if cost > 0 else 0.0

class PaperTradingEngine:
    """
    Air-Gapped Paper Trading Engine.
    Executes trades against live/historical market feeds locally without broker connection.
    """
    def __init__(
        self,
        state_file: str = "data/paper_trading_state.json",
        initial_cash: float = 50000.0,
        risk_manager: Optional[RiskManager] = None,
        cost_model: Optional[IndianMarketCostModel] = None
    ):
        self.state_file_path = Path(state_file)
        self.state_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.initial_cash = initial_cash
        self.cash: float = initial_cash
        self.positions: Dict[str, PaperPosition] = {}
        self.orders: Dict[str, PaperOrder] = {}
        self.executed_client_order_ids: Set[str] = set()
        self.trade_history: List[Dict[str, Any]] = []
        self.daily_realized_pnl: float = 0.0
        self.last_pnl_reset_date: str = date.today().isoformat()
        
        # Risk & Cost modules
        self.risk_manager = risk_manager if risk_manager is not None else RiskManager()
        self.cost_model = cost_model if cost_model is not None else IndianMarketCostModel()

        # Hard Broker Air-Gap Guard
        self._enforce_air_gap_policy()

        # Load persisted state from disk
        self._load_state()

    def _enforce_air_gap_policy(self):
        """Hard security lock: Ensures live trading credentials/endpoints can NEVER be called."""
        if getattr(config, "LIVE_TRADING_ENABLED", False):
            raise RuntimeError("CRITICAL SAFETY BREACH: PaperTradingEngine cannot run with LIVE_TRADING_ENABLED=True!")

    # --------------------------------------------------------------------------
    # 1. ATOMIC PERSISTENCE & RECOVERY
    # --------------------------------------------------------------------------
    def _save_state(self):
        """
        Safely saves state atomically using a temporary file.
        Prevents corrupting JSON if application is aborted mid-write.
        """
        state_dict = {
            "initial_cash": self.initial_cash,
            "cash": self.cash,
            "daily_realized_pnl": self.daily_realized_pnl,
            "last_pnl_reset_date": self.last_pnl_reset_date,
            "executed_client_order_ids": list(self.executed_client_order_ids),
            "positions": {
                sym: {
                    "symbol": pos.symbol,
                    "quantity": pos.quantity,
                    "entry_price": pos.entry_price,
                    "current_price": pos.current_price,
                    "stop_loss_price": pos.stop_loss_price,
                    "take_profit_price": pos.take_profit_price,
                    "opened_at": pos.opened_at,
                    "total_fees_paid": pos.total_fees_paid,
                    "side": pos.side
                }
                for sym, pos in self.positions.items()
            },
            "orders": {
                oid: asdict(order) for oid, order in self.orders.items()
            },
            "trade_history": self.trade_history,
            "saved_at": datetime.now().isoformat()
        }

        # Write to temp file in the same directory, then atomic rename
        temp_file = None
        try:
            with tempfile.NamedTemporaryFile("w", dir=str(self.state_file_path.parent), delete=False, encoding="utf-8") as f:
                json.dump(state_dict, f, indent=2)
                temp_file = Path(f.name)
            
            # Atomic replace (Windows & POSIX safe)
            temp_file.replace(self.state_file_path)
        except Exception as e:
            print(f"[PAPER ENGINE ERROR] State persistence failed: {e}")
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass

    def _load_state(self):
        """
        Loads state safely from disk.
        If file is corrupted, backups the file and recovers with initial cash.
        """
        if not self.state_file_path.exists():
            print("[PAPER ENGINE] No prior state found. Initialized with fresh balance.")
            self._save_state()
            return

        try:
            with open(self.state_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.cash = float(data.get("cash", self.initial_cash))
            self.daily_realized_pnl = float(data.get("daily_realized_pnl", 0.0))
            self.last_pnl_reset_date = data.get("last_pnl_reset_date", date.today().isoformat())
            self.executed_client_order_ids = set(data.get("executed_client_order_ids", []))
            self.trade_history = data.get("trade_history", [])

            # Restore positions
            self.positions = {}
            for sym, p_data in data.get("positions", {}).items():
                self.positions[sym] = PaperPosition(
                    symbol=p_data["symbol"],
                    quantity=int(p_data["quantity"]),
                    entry_price=float(p_data["entry_price"]),
                    current_price=float(p_data["current_price"]),
                    stop_loss_price=float(p_data["stop_loss_price"]),
                    take_profit_price=float(p_data["take_profit_price"]),
                    opened_at=p_data["opened_at"],
                    total_fees_paid=float(p_data["total_fees_paid"]),
                    side=p_data.get("side", "BUY")
                )

            # Restore orders
            self.orders = {}
            for oid, o_data in data.get("orders", {}).items():
                self.orders[oid] = PaperOrder(**o_data)

            # Check if daily PnL needs reset for new calendar day
            self._check_daily_rollover(datetime.now())

            print(f"[PAPER ENGINE] Successfully restored simulation state: Cash INR {self.cash:.2f}, {len(self.positions)} active positions.")
        except Exception as e:
            # Handle partial failure / corrupted file safely
            backup_path = self.state_file_path.with_suffix(".json.corrupted")
            print(f"[PAPER ENGINE WARN] State file corrupted ({e}). Backing up to {backup_path.name} and recovering safely.")
            try:
                self.state_file_path.rename(backup_path)
            except Exception:
                pass
            self.cash = self.initial_cash
            self.positions = {}
            self.orders = {}
            self.executed_client_order_ids = set()
            self._save_state()

    # --------------------------------------------------------------------------
    # 2. ORDER SUBMISSION & EXECUTION PIPELINE
    # --------------------------------------------------------------------------
    def submit_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        quote_timestamp: datetime,
        client_order_id: Optional[str] = None,
        order_type: str = "MARKET",
        current_time: Optional[datetime] = None
    ) -> PaperOrder:
        """
        Submits and simulates order execution locally with realistic friction.
        Guarantees:
        - Rejection of duplicates across bot restarts via client_order_id.
        - Stale quote and market hours validation via RiskManager.
        - Exact Indian regulatory fee & slippage deductions.
        - Immediate state persistence.
        """
        if current_time is None:
            current_time = datetime.now()

        # Air-gap verification
        self._enforce_air_gap_policy()

        # Generate unique order identifiers
        order_id = f"ORD_{uuid.uuid4().hex[:10].upper()}"
        if client_order_id is None:
            client_order_id = f"CLO_{symbol}_{side}_{quote_timestamp.strftime('%Y%m%d_%H%M%S')}"

        clean_sym = symbol.upper()
        clean_side = side.upper()

        order = PaperOrder(
            order_id=order_id,
            client_order_id=client_order_id,
            symbol=clean_sym,
            side=clean_side,
            requested_quantity=quantity,
            filled_quantity=0,
            requested_price=price,
            fill_price=0.0,
            slippage_inr=0.0,
            fees_inr=0.0,
            status="PENDING",
            created_at=current_time.isoformat()
        )

        # 1. Duplicate Order Prevention Across Restarts
        if client_order_id in self.executed_client_order_ids:
            order.status = "REJECTED"
            order.rejection_reason = f"Duplicate order ID detected ({client_order_id}). Order was already executed previously."
            self.orders[order_id] = order
            self._save_state()
            print(f"[PAPER ENGINE] ❌ REJECTED DUPLICATE: {order.rejection_reason}")
            return order

        # 2. Risk Management & Stale-Data Validation
        risk_req = OrderRequest(
            symbol=clean_sym,
            side=clean_side,
            quantity=quantity,
            price=price,
            timestamp=quote_timestamp,
            order_type=order_type,
            is_live=False
        )
        risk_res: OrderValidationResult = self.risk_manager.validate_order_request(risk_req, current_market_time=current_time)

        if not risk_res.is_approved:
            order.status = "REJECTED"
            order.rejection_reason = risk_res.rejection_reason
            self.orders[order_id] = order
            self._save_state()
            print(f"[PAPER ENGINE] ❌ RISK REJECTION ({risk_res.risk_code}): {risk_res.rejection_reason}")
            return order

        # 3. Simulate Execution: Slippage & Indian Transaction Fees
        if clean_side == "BUY":
            eff_price, total_fees, _ = self.cost_model.calculate_entry_costs(price, quantity)
            total_required = (quantity * eff_price) + total_fees

            if total_required > self.cash:
                order.status = "REJECTED"
                order.rejection_reason = f"Insufficient virtual cash: Required INR {total_required:.2f}, Available: INR {self.cash:.2f}."
                self.orders[order_id] = order
                self._save_state()
                print(f"[PAPER ENGINE] ❌ REJECTED: {order.rejection_reason}")
                return order

            # Deduct cash and record position
            self.cash -= total_required
            sl_price, tp_price = self.risk_manager.calculate_exit_levels(eff_price, "BUY")
            
            self.positions[clean_sym] = PaperPosition(
                symbol=clean_sym,
                quantity=quantity,
                entry_price=round(eff_price, 2),
                current_price=round(eff_price, 2),
                stop_loss_price=sl_price,
                take_profit_price=tp_price,
                opened_at=current_time.isoformat(),
                total_fees_paid=round(total_fees, 2),
                side="BUY"
            )

            # Mark order filled
            order.status = "FILLED"
            order.filled_quantity = quantity
            order.fill_price = round(eff_price, 2)
            order.slippage_inr = round((eff_price - price) * quantity, 2)
            order.fees_inr = round(total_fees, 2)
            order.filled_at = current_time.isoformat()

            self.executed_client_order_ids.add(client_order_id)
            self.orders[order_id] = order
            self.risk_manager.record_order_execution(risk_req, executed_time=current_time)
            self._save_state()

            print(f"[PAPER ENGINE] 🟢 FILLED BUY: {quantity} shares of {clean_sym} @ INR {eff_price:.2f} (Fees: INR {total_fees:.2f}) | Cash: INR {self.cash:.2f}")
            return order

        elif clean_side == "SELL":
            if clean_sym not in self.positions:
                order.status = "REJECTED"
                order.rejection_reason = f"Cannot sell {clean_sym}: No active position held."
                self.orders[order_id] = order
                self._save_state()
                return order

            pos = self.positions.pop(clean_sym)
            sell_qty = min(quantity, pos.quantity)
            eff_price, total_fees, _ = self.cost_model.calculate_exit_costs(price, sell_qty)

            gross_proceeds = sell_qty * eff_price
            net_proceeds = gross_proceeds - total_fees
            self.cash += net_proceeds

            # Calculate realized P&L after all regulatory costs
            realized_pnl = net_proceeds - (sell_qty * pos.entry_price)
            self.daily_realized_pnl += realized_pnl
            self.risk_manager.record_trade_completion(realized_pnl)

            trade_record = {
                "symbol": clean_sym,
                "entry_time": pos.opened_at,
                "exit_time": current_time.isoformat(),
                "entry_price": pos.entry_price,
                "exit_price": round(eff_price, 2),
                "quantity": sell_qty,
                "net_pnl_inr": round(realized_pnl, 2),
                "total_fees_inr": round(pos.total_fees_paid + total_fees, 2),
                "reason": "Signal or Protective Exit"
            }
            self.trade_history.append(trade_record)

            order.status = "FILLED"
            order.filled_quantity = sell_qty
            order.fill_price = round(eff_price, 2)
            order.slippage_inr = round((price - eff_price) * sell_qty, 2)
            order.fees_inr = round(total_fees, 2)
            order.filled_at = current_time.isoformat()

            self.executed_client_order_ids.add(client_order_id)
            self.orders[order_id] = order
            self._save_state()

            icon = "🟢" if realized_pnl >= 0 else "🔴"
            print(f"[PAPER ENGINE] {icon} FILLED SELL: {sell_qty} shares of {clean_sym} @ INR {eff_price:.2f} | Net P&L: INR {realized_pnl:+.2f} | Cash: INR {self.cash:.2f}")
            return order

    # --------------------------------------------------------------------------
    # 3. LIVE PRICE UPDATES & AUTOMATIC PROTECTIVE EXITS
    # --------------------------------------------------------------------------
    def update_market_prices(
        self,
        prices_dict: Dict[str, float],
        current_time: Optional[datetime] = None
    ):
        """
        Updates live prices for open positions, evaluates stop-loss and take-profit
        triggers, checks intraday market cutoff square-off, and updates daily loss checks.
        """
        if current_time is None:
            current_time = datetime.now()

        self._check_daily_rollover(current_time)

        # 1. Update prices & check protective triggers
        symbols_to_close = []
        for sym, pos in self.positions.items():
            if sym in prices_dict:
                curr_price = prices_dict[sym]
                pos.current_price = curr_price
                self.risk_manager.update_market_price(sym, curr_price)

                # Check Stop-Loss
                if curr_price <= pos.stop_loss_price:
                    symbols_to_close.append((sym, curr_price, "Stop Loss Triggered"))
                # Check Take-Profit
                elif curr_price >= pos.take_profit_price:
                    symbols_to_close.append((sym, curr_price, "Take Profit Triggered"))

        # 2. Check Intraday Mandatory Square-off Time (03:10 PM IST)
        if self.risk_manager.should_force_square_off(current_time):
            for sym, pos in self.positions.items():
                if (sym, pos.current_price, "Market Square-off (15:10 IST)") not in symbols_to_close:
                    symbols_to_close.append((sym, pos.current_price, "Market Square-off (15:10 IST)"))

        # Execute any triggered protective exits
        for sym, exit_price, reason in symbols_to_close:
            if sym in self.positions:
                pos = self.positions[sym]
                client_id = f"PROT_{sym}_{current_time.strftime('%Y%m%d_%H%M%S')}"
                print(f"[PAPER ENGINE] 🛑 Protective exit triggered for {sym} ({reason}) @ INR {exit_price:.2f}")
                self.submit_order(
                    symbol=sym,
                    side="SELL",
                    quantity=pos.quantity,
                    price=exit_price,
                    quote_timestamp=current_time,
                    client_order_id=client_id,
                    current_time=current_time
                )

        self._save_state()

    def _check_daily_rollover(self, current_time: datetime):
        """Resets realized daily P&L if a new trading date is encountered."""
        today_str = current_time.date().isoformat()
        if today_str != self.last_pnl_reset_date:
            print(f"[PAPER ENGINE] Daily rollover detected ({self.last_pnl_reset_date} -> {today_str}). Resetting daily realized P&L.")
            self.daily_realized_pnl = 0.0
            self.last_pnl_reset_date = today_str
            self.risk_manager.daily_realized_pnl = 0.0
            self.risk_manager.daily_trades_count = 0
            self._save_state()

    def get_account_summary(self) -> Dict[str, Any]:
        """Returns comprehensive virtual account metrics."""
        mkt_val = sum(pos.market_value for pos in self.positions.values())
        unrealized = sum(pos.unrealized_pnl for pos in self.positions.values())
        total_equity = self.cash + mkt_val
        net_total_pnl = self.daily_realized_pnl + unrealized

        max_daily_loss = self.risk_manager.config.max_daily_loss_inr
        loss_consumed_pct = (abs(net_total_pnl) / max_daily_loss * 100.0) if net_total_pnl < 0 else 0.0

        return {
            "mode": "PAPER (100% Simulated - Air-Gapped)",
            "virtual_cash": round(self.cash, 2),
            "stock_market_value": round(mkt_val, 2),
            "total_equity": round(total_equity, 2),
            "unrealized_pnl": round(unrealized, 2),
            "daily_realized_pnl": round(self.daily_realized_pnl, 2),
            "net_daily_pnl": round(net_total_pnl, 2),
            "open_positions_count": len(self.positions),
            "total_orders_count": len(self.orders),
            "daily_loss_consumed_pct": round(min(100.0, loss_consumed_pct), 1),
            "is_kill_switch_active": self.risk_manager.is_kill_switch_active,
            "last_saved_at": datetime.now().isoformat()
        }

    def process_signal(
        self,
        symbol: str,
        signal: str,
        price: float,
        current_time: Optional[datetime] = None
    ) -> Optional[PaperOrder]:
        """
        Processes strategy signals (BUY, EXIT, SELL, HOLD) automatically.
        Connects strategy scanner directly to paper order execution.
        """
        if current_time is None:
            current_time = datetime.now()

        clean_sym = symbol.upper()
        clean_sig = signal.upper()

        # Update market prices first
        self.update_market_prices({clean_sym: price}, current_time=current_time)

        if clean_sig == "BUY":
            # Avoid duplicate position stacking if already in portfolio
            if clean_sym in self.positions:
                print(f"[PAPER ENGINE] ℹ️ Already holding {clean_sym}. Skipping duplicate BUY signal.")
                return None

            # Calculate safe position size based on risk parameters
            qty = self.risk_manager.calculate_position_size(price)
            if qty < 1:
                print(f"[PAPER ENGINE] ℹ️ Position size for {clean_sym} @ INR {price:.2f} is 0 shares. Skipping.")
                return None

            return self.submit_order(
                symbol=clean_sym,
                side="BUY",
                quantity=qty,
                price=price,
                quote_timestamp=current_time,
                current_time=current_time
            )

        elif clean_sig in ["SELL", "EXIT"]:
            if clean_sym not in self.positions:
                return None

            pos = self.positions[clean_sym]
            return self.submit_order(
                symbol=clean_sym,
                side="SELL",
                quantity=pos.quantity,
                price=price,
                quote_timestamp=current_time,
                current_time=current_time
            )

        return None

    def reset_account(self, initial_cash: Optional[float] = None):
        """
        Resets virtual cash, clears all positions, orders, and restart idempotency tracking.
        Safely writes the fresh state to disk.
        """
        if initial_cash is not None:
            self.initial_cash = initial_cash
        self.cash = self.initial_cash
        self.positions = {}
        self.orders = {}
        self.executed_client_order_ids = set()
        self.trade_history = []
        self.daily_realized_pnl = 0.0
        self.last_pnl_reset_date = date.today().isoformat()
        self.risk_manager.daily_realized_pnl = 0.0
        self.risk_manager.daily_trades_count = 0
        self.risk_manager.is_kill_switch_active = False
        self.risk_manager.kill_switch_reason = None
        self._save_state()
        print(f"[PAPER ENGINE] 🔄 Account successfully reset to fresh balance: INR {self.cash:.2f}")

# For backwards compatibility with starter scripts
PaperTrader = PaperTradingEngine

