"""
Dashboard Data & Analytics Engine.
Provides core data structures, portfolio summaries, data freshness audits,
risk limit status trackers, and secret scrubbers for the Streamlit dashboard.
"""

import os
import re
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

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
import config
from src.historical_data import HistoricalDataFetcher
from src.sma_strategy import SMACrossoverStrategy

def check_data_freshness(data_time: Optional[datetime], current_time: Optional[datetime] = None, max_age_seconds: float = 120.0) -> Dict[str, Any]:
    """
    Evaluates data freshness and returns status badges and warning messages.
    - Categorizes into: 'FRESH', 'HISTORICAL_EOD', 'STALE'
    """
    if current_time is None:
        current_time = datetime.now()

    if data_time is None:
        return {
            "status": "UNKNOWN",
            "age_seconds": None,
            "badge_color": "gray",
            "message": "No timestamp available for this dataset."
        }

    # Normalize if data_time is a date object without time
    if isinstance(data_time, date) and not isinstance(data_time, datetime):
        data_time = datetime.combine(data_time, datetime.min.time())

    # If timestamp has no time component (midnight YYYY-MM-DD), it is End-of-Day historical data
    if data_time.hour == 0 and data_time.minute == 0 and data_time.second == 0:
        days_old = (current_time.date() - data_time.date()).days
        return {
            "status": "HISTORICAL_EOD",
            "age_seconds": days_old * 86400,
            "days_old": days_old,
            "badge_color": "blue",
            "message": f"Historical End-of-Day Candle ({data_time.strftime('%Y-%m-%d')}, {days_old} days ago)."
        }

    age_seconds = max(0.0, (current_time - data_time).total_seconds())

    if age_seconds <= max_age_seconds:
        return {
            "status": "FRESH",
            "age_seconds": round(age_seconds, 1),
            "badge_color": "green",
            "message": f"Data Fresh: Last updated {age_seconds:.1f}s ago."
        }
    else:
        return {
            "status": "STALE",
            "age_seconds": round(age_seconds, 1),
            "badge_color": "red",
            "message": f"⚠️ Stale Data Warning: Quote is {age_seconds:.1f}s old (exceeds {max_age_seconds}s limit)."
        }

def compute_portfolio_metrics(
    cash: float,
    open_positions: Dict[str, Dict[str, Any]],
    current_prices: Dict[str, float],
    realized_pnl: float
) -> Dict[str, Any]:
    """
    Calculates virtual equity, unrealized P&L, gross exposure, and margin metrics.
    """
    positions_detail = []
    total_market_value = 0.0
    total_unrealized_pnl = 0.0

    for sym, pos in open_positions.items():
        qty = int(pos.get("quantity", 0))
        entry_p = float(pos.get("entry_price", 0.0))
        curr_p = float(current_prices.get(sym, entry_p))
        sl_p = float(pos.get("stop_loss", entry_p * 0.99))
        tp_p = float(pos.get("take_profit", entry_p * 1.02))

        mkt_val = qty * curr_p
        cost_val = qty * entry_p
        pos_pnl = mkt_val - cost_val
        pos_pnl_pct = (pos_pnl / cost_val * 100.0) if cost_val > 0 else 0.0

        total_market_value += mkt_val
        total_unrealized_pnl += pos_pnl

        positions_detail.append({
            "Symbol": sym,
            "Quantity": qty,
            "Entry Price": round(entry_p, 2),
            "Current Price": round(curr_p, 2),
            "Market Value": round(mkt_val, 2),
            "Unrealized P&L (INR)": round(pos_pnl, 2),
            "Return (%)": round(pos_pnl_pct, 2),
            "Stop-Loss": round(sl_p, 2),
            "Take-Profit": round(tp_p, 2)
        })

    total_equity = cash + total_market_value
    net_total_pnl = realized_pnl + total_unrealized_pnl

    return {
        "cash_balance": round(cash, 2),
        "total_market_value": round(total_market_value, 2),
        "total_equity": round(total_equity, 2),
        "total_unrealized_pnl": round(total_unrealized_pnl, 2),
        "realized_daily_pnl": round(realized_pnl, 2),
        "net_total_pnl": round(net_total_pnl, 2),
        "positions_table": pd.DataFrame(positions_detail) if positions_detail else pd.DataFrame()
    }

def evaluate_risk_limits(
    current_equity: float,
    current_exposure: float,
    open_positions_count: int,
    net_daily_pnl: float,
    is_kill_switch_active: bool,
    max_exposure: float = 15000.0,
    max_positions: int = 3,
    max_daily_loss: float = 1500.0
) -> List[Dict[str, Any]]:
    """
    Evaluates whether any risk threshold is safe, approaching limit (>= 80%), or breached (>= 100%).
    Returns a list of structured risk alerts.
    """
    alerts = []

    # 1. Kill-Switch Alert
    if is_kill_switch_active:
        alerts.append({
            "level": "CRITICAL",
            "category": "Kill-Switch",
            "message": "🚨 EMERGENCY KILL-SWITCH IS ENGAGED! All new order entries are strictly blocked."
        })

    # 2. Daily Loss Limit Alert
    loss_consumed_pct = (abs(net_daily_pnl) / max_daily_loss * 100.0) if net_daily_pnl < 0 else 0.0
    if net_daily_pnl <= -abs(max_daily_loss):
        alerts.append({
            "level": "CRITICAL",
            "category": "Daily Loss",
            "message": f"🚨 Maximum daily loss limit breached! Current loss: INR {abs(net_daily_pnl):.2f} / INR {max_daily_loss:.2f}."
        })
    elif loss_consumed_pct >= 80.0:
        alerts.append({
            "level": "WARNING",
            "category": "Daily Loss",
            "message": f"⚠️ Daily loss approaching limit: {loss_consumed_pct:.1f}% consumed (INR {abs(net_daily_pnl):.2f} / INR {max_daily_loss:.2f})."
        })

    # 3. Total Portfolio Exposure Alert
    exposure_pct = (current_exposure / max_exposure * 100.0) if max_exposure > 0 else 0.0
    if current_exposure > max_exposure:
        alerts.append({
            "level": "CRITICAL",
            "category": "Exposure",
            "message": f"🚨 Maximum portfolio exposure breached! INR {current_exposure:.2f} exceeds cap of INR {max_exposure:.2f}."
        })
    elif exposure_pct >= 80.0:
        alerts.append({
            "level": "WARNING",
            "category": "Exposure",
            "message": f"⚠️ High exposure warning: {exposure_pct:.1f}% of limit utilized (INR {current_exposure:.2f} / INR {max_exposure:.2f})."
        })

    # 4. Open Positions Count Alert
    if open_positions_count >= max_positions:
        alerts.append({
            "level": "INFO",
            "category": "Position Capacity",
            "message": f"ℹ️ Max open positions capacity reached ({open_positions_count}/{max_positions}). New entries paused."
        })

    return alerts

def scrub_sensitive_secrets(text: str) -> str:
    """
    Sanitizes any confidential keys, passwords, or tokens to prevent accidental UI leakage.
    """
    if not isinstance(text, str):
        return str(text)

    # Patterns like TOKEN=xyz, KEY=xyz, SECRET=xyz
    patterns = [
        (r"(?i)(api[_-]?key\s*[:=]\s*)(['\"]?)[^\s'\"]+\2", r"\1\2[REDACTED_API_KEY]\2"),
        (r"(?i)(access[_-]?token\s*[:=]\s*)(['\"]?)[^\s'\"]+\2", r"\1\2[REDACTED_ACCESS_TOKEN]\2"),
        (r"(?i)(password\s*[:=]\s*)(['\"]?)[^\s'\"]+\2", r"\1\2[REDACTED_PASSWORD]\2"),
        (r"(?i)(totp[_-]?secret\s*[:=]\s*)(['\"]?)[^\s'\"]+\2", r"\1\2[REDACTED_TOTP]\2"),
        (r"(?i)(bot[_-]?token\s*[:=]\s*)(['\"]?)[^\s'\"]+\2", r"\1\2[REDACTED_BOT_TOKEN]\2")
    ]
    sanitized = text
    for pattern, repl in patterns:
        sanitized = re.sub(pattern, repl, sanitized)
    return sanitized
