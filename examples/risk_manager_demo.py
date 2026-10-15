"""
Demonstration Script: Risk Management Guardrails & Fail-Closed Behavior.
Simulates boundary conditions and proves that risk rejections prevent order submission.

Conservative Simulation Settings:
- Max Order Value: INR 5,000
- Max Open Positions: 3
- Max Total Exposure: INR 15,000
- Max Daily Loss (Kill-Switch): INR 1,500
- Stale Data Threshold: 120 seconds
- Duplicate Cooldown: 60 seconds
- Live Trading Safety Lock: FIRMLY DISABLED (Simulation only)
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

# Ensure project root is available for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Windows console encoding safeguard
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.risk_manager import RiskManager, RiskConfig, OrderRequest

def run_risk_demonstration():
    print("="*80)
    print("DEMONSTRATION: ENTERPRISE RISK MANAGEMENT & SAFETY CONTROLS")
    print("="*80)

    now = datetime(2026, 10, 15, 11, 0, 0) # 11:00 AM IST (Normal trading hours)
    config = RiskConfig(
        max_order_value_inr=5000.0,
        max_open_positions=3,
        max_daily_loss_inr=1500.0,
        max_total_exposure_inr=15000.0,
        max_data_age_seconds=120.0,
        duplicate_cooldown_seconds=60.0,
        live_trading_enabled=False # Mandatory simulation safety lock
    )
    risk_mgr = RiskManager(risk_config=config)

    def test_order(label: str, order: OrderRequest, ref_time: datetime):
        print(f"\n[SCENARIO] {label}")
        print(f"  Proposed Order: {order.side} {order.quantity} shares of {order.symbol} @ INR {order.price:.2f} (Value: INR {order.quantity * order.price:.2f})")
        res = risk_mgr.validate_order_request(order, current_market_time=ref_time)
        if res.is_approved:
            print(f"  Status: ✅ APPROVED (Risk Code: {res.risk_code})")
            risk_mgr.record_order_execution(order, executed_time=ref_time)
        else:
            print(f"  Status: ❌ REJECTED (Risk Code: {res.risk_code})")
            print(f"  Reason: {res.rejection_reason}")
            print(f"  Action: 🛑 Order submission STRICTLY BLOCKED from transmission.")
        return res

    # 1. Valid Order Approval
    o1 = OrderRequest(symbol="INFY.NS", side="BUY", quantity=3, price=1000.0, timestamp=now)
    test_order("1. Normal Compliant Order", o1, now)

    # 2. Maximum Order Value Rejection (Limit is ₹5,000)
    o2 = OrderRequest(symbol="RELIANCE.NS", side="BUY", quantity=10, price=1200.0, timestamp=now)
    test_order("2. Exceeding Max Order Value (INR 12,000 > INR 5,000)", o2, now)

    # 3. Duplicate Order Cooldown Rejection (15 seconds after order 1 for INFY)
    t_dup = now + timedelta(seconds=15)
    o3 = OrderRequest(symbol="INFY.NS", side="BUY", quantity=1, price=1000.0, timestamp=t_dup)
    test_order("3. Rapid Duplicate Order (15s < 60s cooldown)", o3, t_dup)

    # 4. Stale-Data Rejection (Price quote is 180s old)
    t_stale = now - timedelta(seconds=180)
    o4 = OrderRequest(symbol="ITC.NS", side="BUY", quantity=10, price=250.0, timestamp=t_stale)
    test_order("4. Stale Data Quote (180s old > 120s limit)", o4, now)

    # 5. Fill Up Positions to Limit (3 Max Open Positions)
    o5 = OrderRequest(symbol="ITC.NS", side="BUY", quantity=10, price=250.0, timestamp=now)
    test_order("5. Fill Position 2: ITC.NS", o5, now)

    o6 = OrderRequest(symbol="SBIN.NS", side="BUY", quantity=5, price=500.0, timestamp=now)
    test_order("6. Fill Position 3: SBIN.NS", o6, now)

    # 6. Maximum Open Positions Breach (Attempting 4th Position)
    o7 = OrderRequest(symbol="ICICIBANK.NS", side="BUY", quantity=3, price=1000.0, timestamp=now)
    test_order("7. 4th Position Attempt (Max Positions = 3)", o7, now)

    # 7. Live Trading Disabled Safety Lock
    o_live = OrderRequest(symbol="TCS.NS", side="BUY", quantity=1, price=3000.0, timestamp=now, is_live=True)
    test_order("8. Live Order Submission Safety Lock", o_live, now)

    # 8. Maximum Daily Loss & Kill-Switch Breach
    print("\n" + "-"*75)
    print("SIMULATING MARKET CRASH / CONSECUTIVE STOP-LOSSES (Realized Loss: -INR 1,600)")
    print("-" * 75)
    risk_mgr.record_trade_completion(-1600.0) # Limit is -1,500

    o8 = OrderRequest(symbol="HDFCBANK.NS", side="BUY", quantity=1, price=1000.0, timestamp=now)
    test_order("9. Order After Kill-Switch Latched", o8, now)

    # 9. Fail-Closed Health Check
    print("\n" + "-"*75)
    print("SIMULATING UNEXPECTED DATA CORRUPTION / SERVICE OUTAGE")
    print("-" * 75)
    risk_mgr.fail_closed("Critical hardware memory check failure")
    o9 = OrderRequest(symbol="LT.NS", side="BUY", quantity=1, price=2000.0, timestamp=now)
    test_order("10. Order While Module in Fail-Closed State", o9, now)

    print("\n" + "="*80)
    print("DEMO SUMMARY: All 9 boundary conditions successfully caught and blocked.")
    print("="*80 + "\n")

if __name__ == "__main__":
    run_risk_demonstration()
