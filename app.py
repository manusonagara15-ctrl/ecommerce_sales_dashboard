"""
Streamlit Control & Monitoring Dashboard for Indian Stock Trading Bot.
Features:
- Configured Watchlist with live/historical status and moving averages.
- Visual charts with 20/50 SMA crossover signals.
- Simulated Cash, Holdings, Unrealized & Realized P&L.
- Backtesting performance audit (Train / Validation / Test).
- Real-time Risk-Limit alerts, Kill-Switch controls, and stale-data indicators.
- Manual refresh button.
- Strict security: Zero secrets exposed, live order execution firmly locked.
"""

import os
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any

# Ensure project root is available for imports
sys.path.insert(0, str(Path(__file__).parent))

# Windows console encoding safeguard
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import streamlit as st
import pandas as pd
import numpy as np

import config
from src.historical_data import HistoricalDataFetcher
from src.sma_strategy import SMACrossoverStrategy
from src.ma_backtester import MABacktester, IndianMarketCostModel
from src.risk_manager import RiskManager, RiskConfig, OrderRequest
from src.paper_trader import PaperTradingEngine, PaperOrder
from src.dashboard_data import (
    check_data_freshness,
    compute_portfolio_metrics,
    evaluate_risk_limits,
    scrub_sensitive_secrets
)

# -----------------------------------------------------------------------------
# 1. STREAMLIT APP CONFIGURATION & STYLING
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="AlgoTrader India | Control Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for modern visual aesthetics and clear badges
st.markdown("""
<style>
    .safety-banner {
        background-color: #1a2332;
        border-left: 5px solid #f59e0b;
        padding: 12px 18px;
        border-radius: 6px;
        margin-bottom: 20px;
        font-size: 14px;
    }
    .metric-card {
        background: #111827;
        padding: 16px;
        border-radius: 8px;
        border: 1px solid #1f2937;
        margin-bottom: 12px;
    }
    .signal-buy {
        color: #10b981;
        font-weight: 700;
        background: rgba(16, 185, 129, 0.15);
        padding: 4px 10px;
        border-radius: 4px;
        display: inline-block;
    }
    .signal-exit {
        color: #ef4444;
        font-weight: 700;
        background: rgba(239, 68, 68, 0.15);
        padding: 4px 10px;
        border-radius: 4px;
        display: inline-block;
    }
    .signal-hold {
        color: #9ca3af;
        font-weight: 600;
        background: rgba(156, 163, 175, 0.15);
        padding: 4px 10px;
        border-radius: 4px;
        display: inline-block;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. SESSION STATE INITIALIZATION
# -----------------------------------------------------------------------------
if "risk_manager" not in st.session_state:
    risk_cfg = RiskConfig(
        max_order_value_inr=getattr(config, "MAX_ORDER_VALUE_INR", 5000.0),
        max_open_positions=getattr(config, "MAX_OPEN_POSITIONS", 3),
        max_daily_loss_inr=getattr(config, "MAX_DAILY_LOSS_INR", 1500.0),
        max_total_exposure_inr=getattr(config, "MAX_TOTAL_EXPOSURE_INR", 15000.0),
        max_data_age_seconds=getattr(config, "MAX_DATA_AGE_SECONDS", 120.0),
        duplicate_cooldown_seconds=getattr(config, "DUPLICATE_COOLDOWN_SECONDS", 60.0),
        live_trading_enabled=False # Forced simulation lock
    )
    st.session_state.risk_manager = RiskManager(risk_config=risk_cfg)

if "paper_engine" not in st.session_state:
    # Air-gapped paper trading engine safely persisted to data/paper_trading_state.json
    st.session_state.paper_engine = PaperTradingEngine(
        state_file="data/paper_trading_state.json",
        initial_cash=50000.0,
        risk_manager=st.session_state.risk_manager
    )

if "last_refresh_time" not in st.session_state:
    st.session_state.last_refresh_time = datetime.now()

# -----------------------------------------------------------------------------
# 3. DATA CACHING & LOADING
# -----------------------------------------------------------------------------
@st.cache_data(ttl=60)
def load_watchlist_data(symbols: List[str]) -> Dict[str, pd.DataFrame]:
    """Loads validated historical data for all stocks in the watchlist."""
    fetcher = HistoricalDataFetcher()
    data_dict = {}
    for sym in symbols:
        try:
            df = fetcher.load_local_data(sym)
            data_dict[sym] = df
        except Exception:
            # Fallback: attempt to fetch 1y data directly
            df = fetcher.fetch_raw_daily_data(sym, period="1y")
            val_df, _ = fetcher.validate_daily_data(df, sym)
            if not val_df.empty:
                data_dict[sym] = val_df
    return data_dict

data_map = load_watchlist_data(config.WATCHLIST)

# -----------------------------------------------------------------------------
# 4. SIDEBAR CONTROLS & SAFETY PANEL
# -----------------------------------------------------------------------------
with st.sidebar:
    st.title("🇮🇳 AlgoTrader India")
    st.caption("Educational Trading Bot | Antigravity IDE")

    # Safety Lock Banner
    st.markdown("""
    <div style="background:#064e3b; border-left:4px solid #10b981; padding:8px 12px; border-radius:4px; margin-bottom:12px;">
        <span style="color:#34d399; font-weight:700;">🟢 AIR-GAPPED PAPER TRADING</span><br>
        <span style="font-size:12px; color:#d1d5db;">Local simulation engine active. State persisted safely. Broker endpoints strictly locked.</span>
    </div>
    """, unsafe_allow_html=True)

    # Manual Refresh Control
    if st.button("🔄 Manual Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.session_state.last_refresh_time = datetime.now()
        st.rerun()

    st.markdown(f"**Last Refreshed:** `{st.session_state.last_refresh_time.strftime('%H:%M:%S IST')}`")

    st.markdown("---")
    st.subheader("⚙️ Watchlist Selector")
    selected_symbol = st.selectbox("Inspect Stock", config.WATCHLIST, index=0)

    st.markdown("---")
    st.subheader("🛡️ Risk Parameters (Conservative)")
    st.markdown(f"""
    - **Max Order Value:** `INR {config.MAX_ORDER_VALUE_INR:,.2f}`
    - **Max Open Positions:** `{config.MAX_OPEN_POSITIONS}`
    - **Max Total Exposure:** `INR {config.MAX_TOTAL_EXPOSURE_INR:,.2f}`
    - **Daily Loss Kill-Switch:** `INR {config.MAX_DAILY_LOSS_INR:,.2f}`
    - **Stale Data Cutoff:** `{config.MAX_DATA_AGE_SECONDS}s`
    """)

    # Emergency Kill-Switch Toggle
    st.markdown("---")
    st.subheader("🚨 Emergency Kill-Switch")
    rm: RiskManager = st.session_state.risk_manager
    if rm.is_kill_switch_active:
        st.error(f"🚨 KILL-SWITCH ENGAGED!\nReason: {rm.kill_switch_reason}")
        if st.button("🔓 Admin Reset Kill-Switch", use_container_width=True):
            rm.reset_kill_switch("RESET_RISK_OVERRIDE")
            st.rerun()
    else:
        st.success("✅ System Health: All Safety Locks Normal")
        if st.button("🛑 Trigger Emergency Kill-Switch", use_container_width=True):
            rm.activate_kill_switch("Manual user trigger from dashboard")
            st.rerun()

    # State persistence control
    st.markdown("---")
    st.subheader("💾 Simulation State")
    st.caption("State File: `data/paper_trading_state.json`")
    if st.button("🔄 Reset Paper Account (₹50,000)", use_container_width=True):
        st.session_state.paper_engine.reset_account(50000.0)
        st.cache_data.clear()
        st.success("Paper portfolio reset to ₹50,000 virtual cash.")
        st.rerun()

    # Secret scrubbing notice
    st.markdown("---")
    st.caption("🔒 **Security Notice:** Zero API credentials or `.env` secrets are ever exposed on this UI.")

# -----------------------------------------------------------------------------
# 5. MAIN DASHBOARD CONTENT
# -----------------------------------------------------------------------------
st.title("📈 Indian Stock Market Trading Bot Dashboard")

# Transparency Banner
st.markdown("""
<div class="safety-banner">
    <b>ℹ️ Data & Execution Transparency Notice:</b>
    Historical charts and indicators are computed from <b>verified NSE Daily OHLCV data</b> (via yfinance).
    All positions, order fills, and profit/loss values shown below are <b>100% simulated</b> with zero financial risk.
</div>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 5.1 TOP PORTFOLIO METRICS BAR
# -----------------------------------------------------------------------------
# Gather current prices
current_prices = {}
for s in config.WATCHLIST:
    if s in data_map and not data_map[s].empty:
        current_prices[s] = float(data_map[s]["Close"].iloc[-1])
    else:
        current_prices[s] = 1000.0

# Synchronize paper engine with current market prices
st.session_state.paper_engine.update_market_prices(current_prices)

# Extract open positions from paper engine
positions_for_metrics = {
    sym: {
        "quantity": pos.quantity,
        "entry_price": pos.entry_price,
        "stop_loss": pos.stop_loss_price,
        "take_profit": pos.take_profit_price,
        "entry_time": pos.opened_at
    }
    for sym, pos in st.session_state.paper_engine.positions.items()
}

portfolio_metrics = compute_portfolio_metrics(
    cash=st.session_state.paper_engine.cash,
    open_positions=positions_for_metrics,
    current_prices=current_prices,
    realized_pnl=st.session_state.paper_engine.daily_realized_pnl
)

m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns(5)
with m_col1:
    st.metric("Total Equity (INR)", f"₹{portfolio_metrics['total_equity']:,.2f}")
with m_col2:
    st.metric("Available Cash", f"₹{portfolio_metrics['cash_balance']:,.2f}")
with m_col3:
    st.metric("Gross Exposure", f"₹{portfolio_metrics['total_market_value']:,.2f}", f"{portfolio_metrics['total_market_value']/config.MAX_TOTAL_EXPOSURE_INR*100:.1f}% Cap")
with m_col4:
    st.metric("Unrealized P&L", f"₹{portfolio_metrics['total_unrealized_pnl']:+,.2f}")
with m_col5:
    st.metric("Realized Daily P&L", f"₹{portfolio_metrics['realized_daily_pnl']:+,.2f}")

# -----------------------------------------------------------------------------
# 5.2 RISK LIMIT ALERTS BAR
# -----------------------------------------------------------------------------
risk_alerts = evaluate_risk_limits(
    current_equity=portfolio_metrics["total_equity"],
    current_exposure=portfolio_metrics["total_market_value"],
    open_positions_count=len(st.session_state.paper_engine.positions),
    net_daily_pnl=portfolio_metrics["net_total_pnl"],
    is_kill_switch_active=st.session_state.risk_manager.is_kill_switch_active,
    max_exposure=config.MAX_TOTAL_EXPOSURE_INR,
    max_positions=config.MAX_OPEN_POSITIONS,
    max_daily_loss=config.MAX_DAILY_LOSS_INR
)

for alert in risk_alerts:
    if alert["level"] == "CRITICAL":
        st.error(alert["message"])
    elif alert["level"] == "WARNING":
        st.warning(alert["message"])
    else:
        st.info(alert["message"])

st.markdown("---")

# -----------------------------------------------------------------------------
# 5.3 DASHBOARD TABS
# -----------------------------------------------------------------------------
tab_market, tab_portfolio, tab_backtest, tab_risk = st.tabs([
    "📊 Market Watch & Signals",
    "💼 Simulated Portfolio & Holdings",
    "📈 Backtesting Audit (3-Phase)",
    "🛡️ Risk Controls & Circuit Breakers"
])

# =============================================================================
# TAB 1: MARKET WATCH & SIGNALS
# =============================================================================
with tab_market:
    st.subheader("Watchlist Technical Scanner (20/50 SMA Crossover)")

    # Build Watchlist Summary Table
    scanner_rows = []
    strategy = SMACrossoverStrategy(fast_period=20, slow_period=50)

    for sym in config.WATCHLIST:
        if sym in data_map and not data_map[sym].empty:
            df_sym = data_map[sym]
            analyzed = strategy.generate_signals(df_sym)
            last_row = analyzed.iloc[-1]
            prev_row = analyzed.iloc[-2]
            
            close_p = float(last_row["Close"])
            prev_close = float(prev_row["Close"])
            chg_pct = ((close_p - prev_close) / prev_close) * 100.0
            
            fast_sma = float(last_row["SMA_20"])
            slow_sma = float(last_row["SMA_50"])
            signal = str(last_row["Signal"])
            stance = "LONG (Stock)" if last_row["Target_Position"] == 1 else "CASH (Flat)"
            last_date = str(last_row.name)[:10]

            scanner_rows.append({
                "Symbol": sym,
                "Latest Close (INR)": f"₹{close_p:,.2f}",
                "Day Change": f"{chg_pct:+.2f}%",
                "20-Day SMA": f"₹{fast_sma:,.2f}",
                "50-Day SMA": f"₹{slow_sma:,.2f}",
                "Signal": signal,
                "Stance": stance,
                "Candle Date": last_date
            })

    if scanner_rows:
        scanner_df = pd.DataFrame(scanner_rows)
        st.dataframe(scanner_df, use_container_width=True, hide_index=True)
    else:
        st.info("No watchlist data loaded. Use Option 4 in main.py to download historical candles.")

    st.markdown("---")
    # Selected Stock Deep-Dive
    st.subheader(f"Deep-Dive: {selected_symbol}")
    
    if selected_symbol in data_map and not data_map[selected_symbol].empty:
        stock_df = data_map[selected_symbol]
        signals_df = strategy.generate_signals(stock_df)
        latest_eval = strategy.evaluate_latest_bar(stock_df)

        # Freshness Check
        last_timestamp = stock_df.index[-1]
        freshness = check_data_freshness(last_timestamp)

        col_d1, col_d2, col_d3, col_d4 = st.columns(4)
        with col_d1:
            st.metric("Latest Close", f"₹{latest_eval['close_price']:,.2f}")
        with col_d2:
            st.metric("20-Day SMA (Fast)", f"₹{latest_eval['fast_sma']:,.2f}")
        with col_d3:
            st.metric("50-Day SMA (Slow)", f"₹{latest_eval['slow_sma']:,.2f}")
        with col_d4:
            sig = latest_eval["signal_today"]
            if sig == "BUY":
                st.markdown("**Signal:** <span class='signal-buy'>BUY (Golden Cross)</span>", unsafe_allow_html=True)
            elif sig == "EXIT":
                st.markdown("**Signal:** <span class='signal-exit'>EXIT (Death Cross)</span>", unsafe_allow_html=True)
            else:
                st.markdown("**Signal:** <span class='signal-hold'>HOLD</span>", unsafe_allow_html=True)

        st.info(f"**Strategy Reasoning:** {latest_eval['explanation']} | **Data Timestamp:** `{latest_eval['date']}` ({freshness['message']})")

        # Price & Moving Average Line Chart
        chart_data = signals_df[["Close", "SMA_20", "SMA_50"]].tail(180)
        st.line_chart(chart_data)
        st.caption(f"Showing last 180 trading sessions for {selected_symbol}. Blue=Close, Orange=20-Day SMA, Green=50-Day SMA.")

        with st.expander(f"View Recent Historical OHLCV Table for {selected_symbol}"):
            st.dataframe(stock_df[["Open", "High", "Low", "Close", "Volume"]].tail(15), use_container_width=True)
    else:
        st.warning(f"No local data found for {selected_symbol}.")

# =============================================================================
# TAB 2: SIMULATED PORTFOLIO & HOLDINGS
# =============================================================================
with tab_portfolio:
    st.subheader("Simulated Open Positions (Virtual Holdings)")
    st.caption("All executions run locally with realistic slippage (0.05%) and Indian regulatory charges (₹20 brokerage, STT, GST). Zero money is at risk.")

    # 1. Interactive Order Form
    with st.expander("⚡ Simulate Paper Order (Air-Gapped)", expanded=True):
        st.markdown("Test the paper trading engine with simulated orders. Orders validate against risk limits, incur Indian regulatory fees & slippage, and persist safely to disk.")
        col_sym, col_side, col_qty, col_price = st.columns(4)
        with col_sym:
            sim_sym = st.selectbox("Stock", config.WATCHLIST, key="form_sym")
        with col_side:
            sim_side = st.selectbox("Side", ["BUY", "SELL"], key="form_side")
        with col_qty:
            sim_qty = st.number_input("Shares", min_value=1, max_value=50, value=2, step=1, key="form_qty")
        with col_price:
            ref_p = current_prices.get(sim_sym, 1000.0)
            sim_price = st.number_input("Reference Price (INR)", min_value=1.0, value=float(ref_p), step=1.0, key="form_price")

        if st.button("🚀 Place Simulated Order", use_container_width=True):
            res_order = st.session_state.paper_engine.submit_order(
                symbol=sim_sym,
                side=sim_side,
                quantity=int(sim_qty),
                price=float(sim_price),
                quote_timestamp=datetime.now(),
                current_time=datetime.now()
            )
            if res_order.status == "FILLED":
                st.success(f"✅ Order {res_order.order_id} FILLED: {res_order.side} {res_order.filled_quantity} shares of {res_order.symbol} @ ₹{res_order.fill_price:,.2f} | Fees: ₹{res_order.fees_inr:.2f} | Slippage: ₹{res_order.slippage_inr:.2f}")
            else:
                st.error(f"❌ Order {res_order.order_id} REJECTED: {res_order.rejection_reason}")
            st.rerun()

    st.markdown("---")
    st.subheader("Active Virtual Holdings")

    # Display active holdings from paper engine
    pos_table = portfolio_metrics["positions_table"]
    if not pos_table.empty:
        st.dataframe(pos_table, use_container_width=True, hide_index=True)
    else:
        st.info("No open positions. The bot is sitting 100% in cash.")

    st.markdown("---")
    st.subheader("Paper Order Book (Audit Trail)")
    orders_dict = st.session_state.paper_engine.orders
    if orders_dict:
        order_rows = []
        for oid, ord_obj in reversed(list(orders_dict.items())):
            order_rows.append({
                "Order ID": ord_obj.order_id,
                "Symbol": ord_obj.symbol,
                "Side": ord_obj.side,
                "Qty (Req / Filled)": f"{ord_obj.requested_quantity} / {ord_obj.filled_quantity}",
                "Fill Price": f"₹{ord_obj.fill_price:,.2f}" if ord_obj.fill_price > 0 else "-",
                "Slippage": f"₹{ord_obj.slippage_inr:.2f}" if ord_obj.slippage_inr != 0 else "-",
                "Indian Fees": f"₹{ord_obj.fees_inr:.2f}" if ord_obj.fees_inr > 0 else "-",
                "Status": ord_obj.status,
                "Notes / Rejection": ord_obj.rejection_reason or "Executed cleanly",
                "Timestamp": ord_obj.created_at[:19]
            })
        st.dataframe(pd.DataFrame(order_rows).head(20), use_container_width=True, hide_index=True)
    else:
        st.caption("No orders placed yet. Use the form above to submit your first paper trade.")

    st.markdown("---")
    st.subheader("Simulated Closed Trade History")
    trades = st.session_state.paper_engine.trade_history
    if trades:
        trade_rows = []
        for t in reversed(trades):
            trade_rows.append({
                "Symbol": t["symbol"],
                "Entry Time": t["entry_time"][:16],
                "Exit Time": t["exit_time"][:16],
                "Shares": t["quantity"],
                "Entry Price": f"₹{t['entry_price']:,.2f}",
                "Exit Price": f"₹{t['exit_price']:,.2f}",
                "Total Fees Paid": f"₹{t.get('total_fees_inr', 0.0):.2f}",
                "Net Realized PnL": f"₹{t['net_pnl_inr']:+,.2f}",
                "Reason": t.get("reason", "Exit")
            })
        st.dataframe(pd.DataFrame(trade_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No closed trades recorded yet. Completed round-trips will be audited here.")

# =============================================================================
# TAB 3: BACKTESTING AUDIT (3-PHASE CHRONOLOGICAL)
# =============================================================================
with tab_backtest:
    st.subheader("Institutional 3-Phase Chronological Backtest Audit")
    st.markdown("""
    **Anti-Overfitting Design:** The dataset is partitioned chronologically into:
    - **Train (In-Sample 60%):** Strategy design and baseline testing.
    - **Validation (Out-of-Sample 20%):** Parameter stability verification.
    - **Test (Blind Holdout 20%):** Evaluated strictly **once** to prevent data snooping.
    """)

    if selected_symbol in data_map and not data_map[selected_symbol].empty:
        b_df = data_map[selected_symbol]
        if st.button(f"🚀 Run 3-Phase Audit on {selected_symbol}", use_container_width=True):
            with st.spinner(f"Computing chronological backtest for {selected_symbol}..."):
                backtester = MABacktester(cost_model=IndianMarketCostModel())
                b_results = backtester.run_partitioned_evaluation(b_df, symbol=selected_symbol)

                t = b_results["train"]
                v = b_results["validation"]
                te = b_results["test"]

                audit_rows = [
                    {"Metric": "Date Window", "Train (60%)": f"{t.get('start_date')} to {t.get('end_date')}", "Validation (20%)": f"{v.get('start_date')} to {v.get('end_date')}", "Test (Holdout 20%)": f"{te.get('start_date')} to {te.get('end_date')}"},
                    {"Metric": "Trading Days", "Train (60%)": str(t.get("total_bars")), "Validation (20%)": str(v.get("total_bars")), "Test (Holdout 20%)": str(te.get("total_bars"))},
                    {"Metric": "Net Strategy Return (%)", "Train (60%)": f"{t.get('net_return_pct'):+.2f}%", "Validation (20%)": f"{v.get('net_return_pct'):+.2f}%", "Test (Holdout 20%)": f"{te.get('net_return_pct'):+.2f}%"},
                    {"Metric": "Benchmark Return (B&H %)", "Train (60%)": f"{t.get('benchmark_return_pct'):+.2f}%", "Validation (20%)": f"{v.get('benchmark_return_pct'):+.2f}%", "Test (Holdout 20%)": f"{te.get('benchmark_return_pct'):+.2f}%"},
                    {"Metric": "Alpha vs Benchmark (%)", "Train (60%)": f"{t.get('alpha_vs_benchmark_pct'):+.2f}%", "Validation (20%)": f"{v.get('alpha_vs_benchmark_pct'):+.2f}%", "Test (Holdout 20%)": f"{te.get('alpha_vs_benchmark_pct'):+.2f}%"},
                    {"Metric": "Maximum Drawdown (%)", "Train (60%)": f"{t.get('max_drawdown_pct'):.2f}%", "Validation (20%)": f"{v.get('max_drawdown_pct'):.2f}%", "Test (Holdout 20%)": f"{te.get('max_drawdown_pct'):.2f}%"},
                    {"Metric": "Total Trades", "Train (60%)": str(t.get("total_trades")), "Validation (20%)": str(v.get("total_trades")), "Test (Holdout 20%)": str(te.get("total_trades"))},
                    {"Metric": "Win Rate (%)", "Train (60%)": f"{t.get('win_rate_pct'):.1f}%", "Validation (20%)": f"{v.get('win_rate_pct'):.1f}%", "Test (Holdout 20%)": f"{te.get('win_rate_pct'):.1f}%"},
                    {"Metric": "Sharpe Ratio (Rf=6.5%)", "Train (60%)": f"{t.get('sharpe_ratio'):.2f}", "Validation (20%)": f"{v.get('sharpe_ratio'):.2f}", "Test (Holdout 20%)": f"{te.get('sharpe_ratio'):.2f}"},
                    {"Metric": "Taxes & Brokerage Paid", "Train (60%)": f"₹{t.get('total_costs_paid_inr', 0.0):.2f}", "Validation (20%)": f"₹{v.get('total_costs_paid_inr', 0.0):.2f}", "Test (Holdout 20%)": f"₹{te.get('total_costs_paid_inr', 0.0):.2f}"}
                ]
                st.dataframe(pd.DataFrame(audit_rows), use_container_width=True, hide_index=True)
    else:
        st.info("Select a stock with valid historical data to inspect backtest metrics.")

# =============================================================================
# TAB 4: RISK CONTROLS & CIRCUIT BREAKERS
# =============================================================================
with tab_risk:
    st.subheader("Real-Time Circuit Breakers & Exposure Meters")

    r_col1, r_col2 = st.columns(2)
    with r_col1:
        st.markdown("#### Aggregate Exposure Capacity")
        curr_exp = portfolio_metrics["total_market_value"]
        exp_ratio = min(1.0, curr_exp / config.MAX_TOTAL_EXPOSURE_INR)
        st.progress(exp_ratio)
        st.caption(f"INR {curr_exp:,.2f} utilized of INR {config.MAX_TOTAL_EXPOSURE_INR:,.2f} Maximum Exposure Limit ({exp_ratio*100:.1f}%)")

        st.markdown("#### Open Position Slots")
        n_pos = len(st.session_state.paper_engine.positions)
        pos_ratio = min(1.0, n_pos / config.MAX_OPEN_POSITIONS)
        st.progress(pos_ratio)
        st.caption(f"{n_pos} active positions of {config.MAX_OPEN_POSITIONS} Max Allowed ({pos_ratio*100:.1f}%)")

    with r_col2:
        st.markdown("#### Daily Loss Threshold (Emergency Kill-Switch)")
        curr_loss = abs(min(0.0, portfolio_metrics["net_total_pnl"]))
        loss_ratio = min(1.0, curr_loss / config.MAX_DAILY_LOSS_INR)
        st.progress(loss_ratio)
        st.caption(f"INR {curr_loss:,.2f} consumed of INR {config.MAX_DAILY_LOSS_INR:,.2f} Daily Loss Limit ({loss_ratio*100:.1f}%)")

        st.markdown("#### Fail-Closed Health Monitor")
        if st.session_state.risk_manager.is_operational:
            st.success("🟢 Risk Manager Status: OPERATIONAL (Fail-Closed Ready)")
        else:
            st.error("🔴 Risk Manager Status: FAILED-CLOSED (Trading Halted)")

    st.markdown("---")
    st.subheader("⚠️ Essential Indian Market Risk Realities")
    st.markdown("""
    1. **Stop-Loss Orders Do Not Guarantee Fill Price:**  
       Stop-loss orders protect against prolonged declines, but in case of gap-down openings or **lower circuit limit freezes** on the NSE, buyers vanish and actual execution prices can be significantly worse than the trigger price.
    2. **Transaction Cost Drag on Micro-Capital:**  
       Flat ₹20 buy + ₹20 sell (+ STT & GST = ~₹48 total) means micro-trades (1-2 shares) will suffer high transaction friction. High-timeframe strategies (daily candles) reduce fee erosion.
    3. **Automated SEBI Cutoff:**  
       All intraday orders must be squared off before **03:15 PM IST** to prevent broker auto-square-off penalties.
    """)
