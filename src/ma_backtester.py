"""
Comprehensive Backtesting Module for Moving Average Strategies on Indian Equities (NSE).
Features:
1. Strict Chronological Splits (Train / Validation / Holdout Test) to prevent data leakage.
2. Realistic Indian Market Friction (Zerodha/Dhan style flat ₹20 brokerage, STT, GST, Stamp Duty, Exchange Fees, Slippage).
3. Zero Look-Ahead Bias: Signals on Day t Close execute strictly at Day t+1 Open.
4. Comprehensive Performance & Risk-Adjusted Metrics (Net vs Benchmark, Max Drawdown, Sharpe, Sortino, Win Rate).
5. Explicit Holdout Policy: Test set is evaluated strictly once to prevent overfitting.
"""

import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Any, Tuple, Optional, List

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
from src.sma_strategy import SMACrossoverStrategy

@dataclass
class IndianMarketCostModel:
    """
    Configurable Indian Equity Cash (Delivery/CNC) Transaction Cost Model.
    Values accurately reflect regulatory charges on the National Stock Exchange (NSE).
    """
    brokerage_flat_per_order: float = 20.0   # Flat ₹20 per executed leg (standard discount broker)
    stt_delivery_buy_pct: float = 0.001      # 0.1% Securities Transaction Tax on Buy (Delivery)
    stt_delivery_sell_pct: float = 0.001     # 0.1% Securities Transaction Tax on Sell (Delivery)
    exchange_turnover_pct: float = 0.0000325 # 0.00325% NSE Exchange Transaction Charge
    sebi_turnover_pct: float = 0.000001      # ₹10 per crore (0.0001%) SEBI Turnover Charge
    stamp_duty_buy_pct: float = 0.00015      # 0.015% State Stamp Duty (Buy leg only)
    gst_pct: float = 0.18                    # 18% GST on (Brokerage + Exchange Fees + SEBI Fees)
    slippage_pct: float = 0.0005             # 0.05% slippage on entry and exit (5 bps)

    def calculate_entry_costs(self, price: float, quantity: int) -> Tuple[float, float, Dict[str, float]]:
        """
        Calculates all fees and effective price for buying stock.
        Returns: (effective_execution_price, total_fees_inr, fee_breakdown)
        """
        # Apply slippage on entry (buy slightly higher than quoted price)
        effective_price = price * (1.0 + self.slippage_pct)
        turnover = effective_price * quantity

        brokerage = self.brokerage_flat_per_order
        stt = turnover * self.stt_delivery_buy_pct
        exchange_fee = turnover * self.exchange_turnover_pct
        sebi_fee = turnover * self.sebi_turnover_pct
        stamp_duty = turnover * self.stamp_duty_buy_pct
        gst = (brokerage + exchange_fee + sebi_fee) * self.gst_pct

        total_entry_fees = brokerage + stt + exchange_fee + sebi_fee + stamp_duty + gst

        breakdown = {
            "brokerage": brokerage,
            "stt": stt,
            "exchange_fee": exchange_fee,
            "sebi_fee": sebi_fee,
            "stamp_duty": stamp_duty,
            "gst": gst,
            "total_fees": total_entry_fees,
            "slippage_cost": (effective_price - price) * quantity
        }
        return effective_price, total_entry_fees, breakdown

    def calculate_exit_costs(self, price: float, quantity: int) -> Tuple[float, float, Dict[str, float]]:
        """
        Calculates all fees and effective price for selling stock.
        Returns: (effective_execution_price, total_fees_inr, fee_breakdown)
        """
        # Apply slippage on exit (sell slightly lower than quoted price)
        effective_price = price * (1.0 - self.slippage_pct)
        turnover = effective_price * quantity

        brokerage = self.brokerage_flat_per_order
        stt = turnover * self.stt_delivery_sell_pct
        exchange_fee = turnover * self.exchange_turnover_pct
        sebi_fee = turnover * self.sebi_turnover_pct
        stamp_duty = 0.0  # Stamp duty applies only on the buy leg in India
        gst = (brokerage + exchange_fee + sebi_fee) * self.gst_pct

        total_exit_fees = brokerage + stt + exchange_fee + sebi_fee + stamp_duty + gst

        breakdown = {
            "brokerage": brokerage,
            "stt": stt,
            "exchange_fee": exchange_fee,
            "sebi_fee": sebi_fee,
            "stamp_duty": stamp_duty,
            "gst": gst,
            "total_fees": total_exit_fees,
            "slippage_cost": (price - effective_price) * quantity
        }
        return effective_price, total_exit_fees, breakdown

class DataSplitter:
    """
    Partitions time-series data chronologically into Train, Validation, and Test sets.
    Strictly forbids random shuffling to prevent future data leaking into the past.
    """
    @staticmethod
    def chronological_split(
        df: pd.DataFrame,
        train_ratio: float = 0.60,
        val_ratio: float = 0.20,
        test_ratio: float = 0.20
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Splits DataFrame chronologically.
        Ratios must sum to 1.0.
        """
        if not np.isclose(train_ratio + val_ratio + test_ratio, 1.0):
            raise ValueError(f"Split ratios must sum to 1.0. Got: {train_ratio + val_ratio + test_ratio}")

        if len(df) < 60:
            raise ValueError(f"Insufficient rows ({len(df)}) for 3-way chronological partitioning.")

        n = len(df)
        train_end = int(n * train_ratio)
        val_end = int(n * (train_ratio + val_ratio))

        train_df = df.iloc[:train_end].copy()
        val_df = df.iloc[train_end:val_end].copy()
        test_df = df.iloc[val_end:].copy()

        # Integrity Assertion: Ensure strictly non-overlapping dates
        assert train_df.index[-1] < val_df.index[0], "Data leakage: Train date overlaps with Validation."
        assert val_df.index[-1] < test_df.index[0], "Data leakage: Validation date overlaps with Test."

        return train_df, val_df, test_df

class MABacktester:
    """
    Realistic Backtesting Engine for Moving Average Strategies.
    Simulates actual trade execution, fee deductions, and calculates performance metrics.
    """
    def __init__(
        self,
        strategy: Optional[SMACrossoverStrategy] = None,
        initial_capital: float = 100000.0,
        cost_model: Optional[IndianMarketCostModel] = None,
        risk_free_rate_pct: float = 6.5  # Approx 10-Year Indian Government Bond / RBI Repo Rate
    ):
        self.strategy = strategy if strategy is not None else SMACrossoverStrategy(fast_period=20, slow_period=50)
        self.initial_capital = initial_capital
        self.cost_model = cost_model if cost_model is not None else IndianMarketCostModel()
        self.risk_free_rate = risk_free_rate_pct / 100.0

    def run(self, df: pd.DataFrame, period_name: str = "Backtest Period") -> Dict[str, Any]:
        """
        Executes backtest over a given DataFrame.

        Execution Timing Rules (Look-Ahead Bias Elimination):
        - Indicators are calculated on Bar t using historical Close prices.
        - Signal generated on Bar t Close is executed at Bar t+1 OPEN.
        - If Bar t+1 does not exist (end of data), the trade is not entered.
        """
        if "Signal" not in df.columns or "Execution_Next_Open" not in df.columns:
            if df.empty or len(df) < self.strategy.slow_period + 2:
                return {"error": "Insufficient data to compute 50-SMA and simulate trades.", "period_name": period_name}
            data = self.strategy.generate_signals(df).copy()
        else:
            if df.empty:
                return {"error": "Empty dataset provided.", "period_name": period_name}
            data = df.copy()

        cash = self.initial_capital
        position_shares = 0
        entry_price = 0.0
        entry_date = None
        trades = []
        equity_records = []
        total_costs_paid = 0.0

        dates = data.index
        n_bars = len(data)

        for i in range(n_bars):
            current_bar = data.iloc[i]
            current_date = dates[i]
            
            # Check if we have an execution scheduled for TODAY'S OPEN
            # (Generated by yesterday's close signal: Execution_Next_Open)
            action_today = current_bar["Execution_Next_Open"]
            open_price = float(current_bar["Open"])
            close_price = float(current_bar["Close"])

            # 1. Execute EXIT at Open
            if action_today == "EXIT" and position_shares > 0:
                eff_exit_price, exit_fees, exit_breakdown = self.cost_model.calculate_exit_costs(open_price, position_shares)
                gross_proceeds = position_shares * eff_exit_price
                net_proceeds = gross_proceeds - exit_fees
                
                cash += net_proceeds
                total_costs_paid += exit_fees

                trade_return_inr = net_proceeds - (position_shares * entry_price)
                trade_return_pct = (trade_return_inr / (position_shares * entry_price)) * 100.0

                trades.append({
                    "entry_date": entry_date,
                    "exit_date": current_date,
                    "entry_price": round(entry_price, 2),
                    "exit_price": round(eff_exit_price, 2),
                    "quantity": position_shares,
                    "net_pnl_inr": round(trade_return_inr, 2),
                    "return_pct": round(trade_return_pct, 2)
                })

                position_shares = 0
                entry_price = 0.0
                entry_date = None

            # 2. Execute BUY at Open
            elif action_today == "BUY" and position_shares == 0:
                # Capital allocation: allocate available cash (reserve 1% buffer for fees/slippage)
                investable_cash = cash * 0.99
                approx_shares = int(investable_cash // (open_price * (1.0 + self.cost_model.slippage_pct)))

                if approx_shares >= 1:
                    eff_entry_price, entry_fees, entry_breakdown = self.cost_model.calculate_entry_costs(open_price, approx_shares)
                    total_required = (approx_shares * eff_entry_price) + entry_fees

                    if total_required <= cash:
                        cash -= total_required
                        position_shares = approx_shares
                        entry_price = eff_entry_price
                        entry_date = current_date
                        total_costs_paid += entry_fees

            # Mark-to-market daily portfolio value at today's close
            stock_value = position_shares * close_price
            daily_total_equity = cash + stock_value
            equity_records.append({
                "Date": current_date,
                "Equity": daily_total_equity,
                "Close": close_price
            })

        # Final close of any open position at the last bar's Close for backtest accounting
        if position_shares > 0:
            last_close = float(data["Close"].iloc[-1])
            eff_exit_price, exit_fees, _ = self.cost_model.calculate_exit_costs(last_close, position_shares)
            net_proceeds = (position_shares * eff_exit_price) - exit_fees
            cash += net_proceeds
            total_costs_paid += exit_fees
            trade_return_inr = net_proceeds - (position_shares * entry_price)
            trade_return_pct = (trade_return_inr / (position_shares * entry_price)) * 100.0
            trades.append({
                "entry_date": entry_date,
                "exit_date": dates[-1],
                "entry_price": round(entry_price, 2),
                "exit_price": round(eff_exit_price, 2),
                "quantity": position_shares,
                "net_pnl_inr": round(trade_return_inr, 2),
                "return_pct": round(trade_return_pct, 2)
            })
            position_shares = 0

        # Calculate equity curve metrics
        equity_df = pd.DataFrame(equity_records).set_index("Date")
        final_equity = cash
        net_return_pct = ((final_equity - self.initial_capital) / self.initial_capital) * 100.0

        # Benchmark: Buy and Hold the underlying stock over the exact same period
        start_stock_price = float(df["Close"].iloc[0])
        end_stock_price = float(df["Close"].iloc[-1])
        benchmark_return_pct = ((end_stock_price - start_stock_price) / start_stock_price) * 100.0

        # Maximum Drawdown calculation
        equity_series = equity_df["Equity"]
        peak = equity_series.cummax()
        drawdown_series = (equity_series - peak) / peak
        max_drawdown_pct = abs(float(drawdown_series.min())) * 100.0
        max_drawdown_inr = float((peak - equity_series).max())

        # Trade metrics
        trades_df = pd.DataFrame(trades)
        total_trades = len(trades)
        if total_trades > 0:
            wins = trades_df[trades_df["net_pnl_inr"] > 0]
            losses = trades_df[trades_df["net_pnl_inr"] <= 0]
            win_rate_pct = (len(wins) / total_trades) * 100.0
            avg_trade_return_pct = float(trades_df["return_pct"].mean())
            gross_win_sum = float(wins["net_pnl_inr"].sum()) if len(wins) > 0 else 0.0
            gross_loss_sum = abs(float(losses["net_pnl_inr"].sum())) if len(losses) > 0 else 1.0
            profit_factor = round(gross_win_sum / (gross_loss_sum if gross_loss_sum > 0 else 1.0), 2)
        else:
            win_rate_pct = 0.0
            avg_trade_return_pct = 0.0
            profit_factor = 0.0

        # Risk-Adjusted Returns (Sharpe & Sortino)
        daily_returns = equity_series.pct_change().dropna()
        trading_days_per_year = 252
        if len(daily_returns) > 10 and daily_returns.std() > 0:
            annualized_return = (1.0 + net_return_pct / 100.0) ** (trading_days_per_year / len(daily_returns)) - 1.0
            daily_rf = (1.0 + self.risk_free_rate) ** (1.0 / trading_days_per_year) - 1.0
            excess_daily_returns = daily_returns - daily_rf
            sharpe_ratio = float((excess_daily_returns.mean() / daily_returns.std()) * np.sqrt(trading_days_per_year))

            # Downside deviation for Sortino
            downside_returns = excess_daily_returns[excess_daily_returns < 0]
            if len(downside_returns) > 0 and downside_returns.std() > 0:
                downside_std = float(downside_returns.std() * np.sqrt(trading_days_per_year))
                sortino_ratio = float((annualized_return - self.risk_free_rate) / downside_std)
            else:
                sortino_ratio = 0.0
        else:
            sharpe_ratio = 0.0
            sortino_ratio = 0.0

        return {
            "period_name": period_name,
            "start_date": str(dates[0])[:10],
            "end_date": str(dates[-1])[:10],
            "total_bars": len(df),
            "initial_capital_inr": self.initial_capital,
            "final_equity_inr": round(final_equity, 2),
            "net_pnl_inr": round(final_equity - self.initial_capital, 2),
            "net_return_pct": round(net_return_pct, 2),
            "benchmark_return_pct": round(benchmark_return_pct, 2),
            "alpha_vs_benchmark_pct": round(net_return_pct - benchmark_return_pct, 2),
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "max_drawdown_inr": round(max_drawdown_inr, 2),
            "total_trades": total_trades,
            "winning_trades": len(trades_df[trades_df["net_pnl_inr"] > 0]) if total_trades > 0 else 0,
            "losing_trades": len(trades_df[trades_df["net_pnl_inr"] <= 0]) if total_trades > 0 else 0,
            "win_rate_pct": round(win_rate_pct, 2),
            "avg_trade_return_pct": round(avg_trade_return_pct, 2),
            "profit_factor": profit_factor,
            "sharpe_ratio": round(sharpe_ratio, 2),
            "sortino_ratio": round(sortino_ratio, 2),
            "total_costs_paid_inr": round(total_costs_paid, 2),
            "trades": trades
        }

    def run_partitioned_evaluation(self, df: pd.DataFrame, symbol: str = "STOCK") -> Dict[str, Any]:
        """
        Executes the formal 3-phase Chronological Evaluation:
        1. Train Set (60%): For strategy design and baseline.
        2. Validation Set (20%): For parameter stability verification.
        3. Test Set (20%): Blind holdout evaluated strictly once.

        Zero Look-Ahead Bias:
        Moving average signals are computed continuously backward-looking across the timeline
        so that Validation and Test sets have active indicators without losing 50 bars to warm-up.
        """
        full_data = self.strategy.generate_signals(df).copy()
        train_df, val_df, test_df = DataSplitter.chronological_split(full_data, 0.60, 0.20, 0.20)

        train_res = self.run(train_df, period_name="TRAIN SET (In-Sample 60%)")
        val_res = self.run(val_df, period_name="VALIDATION SET (Out-of-Sample 20%)")
        test_res = self.run(test_df, period_name="TEST SET (Blind Holdout 20%)")

        return {
            "symbol": symbol,
            "train": train_res,
            "validation": val_res,
            "test": test_res
        }

def print_partitioned_report(eval_results: Dict[str, Any]):
    """Prints a comparative institutional-style backtesting audit table."""
    symbol = eval_results["symbol"]
    t = eval_results["train"]
    v = eval_results["validation"]
    te = eval_results["test"]

    print("\n" + "="*80)
    print(f"CHRONOLOGICAL BACKTEST AUDIT REPORT: {symbol}")
    print("="*80)
    print(f"{'Metric':30s} | {'Train (In-Sample)':14s} | {'Validation':14s} | {'Test (Blind Holdout)':18s}")
    print("-" * 80)
    print(f"{'Date Range':30s} | {t.get('start_date', '')} to {t.get('end_date', ''):5s} | {v.get('start_date', '')} to {v.get('end_date', ''):5s} | {te.get('start_date', '')} to {te.get('end_date', ''):5s}")
    print(f"{'Total Trading Bars':30s} | {t.get('total_bars', 0):<14d} | {v.get('total_bars', 0):<14d} | {te.get('total_bars', 0):<18d}")
    print(f"{'Net Return (%)':30s} | {t.get('net_return_pct', 0.0):+13.2f}% | {v.get('net_return_pct', 0.0):+13.2f}% | {te.get('net_return_pct', 0.0):+17.2f}%")
    print(f"{'Benchmark Return (B&H %)':30s} | {t.get('benchmark_return_pct', 0.0):+13.2f}% | {v.get('benchmark_return_pct', 0.0):+13.2f}% | {te.get('benchmark_return_pct', 0.0):+17.2f}%")
    print(f"{'Alpha vs Benchmark (%)':30s} | {t.get('alpha_vs_benchmark_pct', 0.0):+13.2f}% | {v.get('alpha_vs_benchmark_pct', 0.0):+13.2f}% | {te.get('alpha_vs_benchmark_pct', 0.0):+17.2f}%")
    print(f"{'Max Drawdown (%)':30s} | {t.get('max_drawdown_pct', 0.0):13.2f}% | {v.get('max_drawdown_pct', 0.0):13.2f}% | {te.get('max_drawdown_pct', 0.0):17.2f}%")
    print(f"{'Total Trades':30s} | {t.get('total_trades', 0):<14d} | {v.get('total_trades', 0):<14d} | {te.get('total_trades', 0):<18d}")
    print(f"{'Win Rate (%)':30s} | {t.get('win_rate_pct', 0.0):13.2f}% | {v.get('win_rate_pct', 0.0):13.2f}% | {te.get('win_rate_pct', 0.0):17.2f}%")
    print(f"{'Profit Factor':30s} | {t.get('profit_factor', 0.0):<14.2f} | {v.get('profit_factor', 0.0):<14.2f} | {te.get('profit_factor', 0.0):<18.2f}")
    print(f"{'Sharpe Ratio (Rf=6.5%)':30s} | {t.get('sharpe_ratio', 0.0):<14.2f} | {v.get('sharpe_ratio', 0.0):<14.2f} | {te.get('sharpe_ratio', 0.0):<18.2f}")
    print(f"{'Total Costs & Taxes Paid':30s} | INR {t.get('total_costs_paid_inr', 0.0):<10.2f} | INR {v.get('total_costs_paid_inr', 0.0):<10.2f} | INR {te.get('total_costs_paid_inr', 0.0):<14.2f}")
    print("="*80)
    print("""
CRITICAL BACKTESTING RULES & LIMITATIONS:
1. Overfitting Rule: Do NOT iteratively tune strategy parameters against the Test Set!
   The Test Set serves strictly as a blind audit of real-world generalization.
2. Survivorship Bias: This test evaluates currently listed large-cap stocks.
   It does not include companies that were delisted, liquidated, or failed in the past.
3. Market Impact & Liquidity: Assumes complete order execution at Open without moving market price.
""")

if __name__ == "__main__":
    from src.historical_data import HistoricalDataFetcher
    fetcher = HistoricalDataFetcher()
    test_symbol = "SBIN.NS"
    print(f"Loading historical data for {test_symbol}...")
    try:
        df = fetcher.load_local_data(test_symbol)
        backtester = MABacktester()
        results = backtester.run_partitioned_evaluation(df, symbol=test_symbol)
        print_partitioned_report(results)
    except Exception as e:
        print(f"Backtest error: {e}")
