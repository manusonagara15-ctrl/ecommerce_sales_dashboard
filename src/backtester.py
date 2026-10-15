"""
Backtesting Engine for Indian Equities.
Specifically modeled with realistic Indian market friction:
- Brokerage charges (₹20 per executed leg = ₹40 round trip)
- STT, GST, Exchange turnover fees (~₹5 - ₹10)
- Hard Stop-Loss and Take-Profit evaluation per candle
- Maximum Drawdown calculation
"""

import pandas as pd
import numpy as np
import config
from src.strategy import generate_signals

class Backtester:
    def __init__(self, initial_capital: float = 50000.0, brokerage_per_trade: float = config.ESTIMATED_BROKERAGE_PER_TRADE):
        self.initial_capital = initial_capital
        self.brokerage_per_trade = brokerage_per_trade

    def run(self, df: pd.DataFrame, symbol: str = "STOCK") -> dict:
        """
        Runs an iterative backtest simulating realistic intraday execution.
        """
        if df.empty or len(df) < 50:
            return {"error": "Insufficient data"}

        # Generate indicators & signals
        data = generate_signals(df).copy()

        capital = self.initial_capital
        peak_capital = capital
        max_drawdown_inr = 0.0
        
        position = 0      # Current share quantity
        entry_price = 0.0
        stop_loss = 0.0
        take_profit = 0.0
        
        trades = []
        equity_curve = [capital]

        for i in range(1, len(data)):
            current_bar = data.iloc[i]
            prev_bar = data.iloc[i - 1]
            
            # Check open position exits first (Stop-Loss or Take-Profit hit)
            if position > 0:
                exit_price = None
                exit_reason = None
                
                # Did low pierce Stop Loss?
                if current_bar["Low"] <= stop_loss:
                    exit_price = stop_loss
                    exit_reason = "Stop Loss Hit"
                # Did high pierce Take Profit?
                elif current_bar["High"] >= take_profit:
                    exit_price = take_profit
                    exit_reason = "Target Profit Hit"
                # Did strategy generate an explicit exit signal?
                elif prev_bar["Signal"] == -1:
                    exit_price = current_bar["Open"]
                    exit_reason = "Signal Exit"
                    
                if exit_price:
                    gross_pnl = (exit_price - entry_price) * position
                    net_pnl = gross_pnl - self.brokerage_per_trade
                    capital += (position * exit_price) + (gross_pnl - (position * entry_price)) - self.brokerage_per_trade
                    
                    trades.append({
                        "entry_time": entry_time,
                        "exit_time": current_bar.name,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "quantity": position,
                        "gross_pnl": round(gross_pnl, 2),
                        "net_pnl": round(net_pnl, 2),
                        "reason": exit_reason
                    })
                    
                    position = 0
                    entry_price = 0.0

            # Check new entry condition (if not currently holding a position)
            if position == 0 and prev_bar["Signal"] == 1:
                # Enter at open of current candle
                entry_price = current_bar["Open"]
                entry_time = current_bar.name
                
                # Position sizing based on config limit
                position = int(config.MAX_CAPITAL_PER_TRADE_INR // entry_price)
                if position >= 1:
                    stop_loss = round(entry_price * (1.0 - config.STOP_LOSS_PCT / 100.0), 2)
                    take_profit = round(entry_price * (1.0 + config.TAKE_PROFIT_PCT / 100.0), 2)
                else:
                    position = 0  # Share price too high for allotted capital

            # Track Drawdown
            equity_curve.append(capital)
            if capital > peak_capital:
                peak_capital = capital
            dd = peak_capital - capital
            if dd > max_drawdown_inr:
                max_drawdown_inr = dd

        # Compute summary metrics
        total_trades = len(trades)
        if total_trades == 0:
            return {
                "symbol": symbol,
                "total_trades": 0,
                "message": "No trades triggered in this period."
            }

        trades_df = pd.DataFrame(trades)
        gross_wins = trades_df[trades_df["gross_pnl"] > 0]
        net_wins = trades_df[trades_df["net_pnl"] > 0]
        losses = trades_df[trades_df["gross_pnl"] <= 0]
        
        total_net_pnl = trades_df["net_pnl"].sum()
        total_gross_pnl = trades_df["gross_pnl"].sum()
        total_brokerage_paid = total_trades * self.brokerage_per_trade
        gross_win_rate = (len(gross_wins) / total_trades) * 100.0
        net_win_rate = (len(net_wins) / total_trades) * 100.0
        
        gross_profit = gross_wins["gross_pnl"].sum() if len(gross_wins) > 0 else 0.0
        gross_loss = abs(losses["gross_pnl"].sum()) if len(losses) > 0 else 1.0
        profit_factor = round(gross_profit / (gross_loss if gross_loss > 0 else 1.0), 2)
        
        max_dd_pct = (max_drawdown_inr / self.initial_capital) * 100.0

        return {
            "symbol": symbol,
            "total_trades": total_trades,
            "gross_winning_trades": len(gross_wins),
            "net_winning_trades": len(net_wins),
            "gross_win_rate_pct": round(gross_win_rate, 2),
            "net_win_rate_pct": round(net_win_rate, 2),
            "gross_pnl_inr": round(total_gross_pnl, 2),
            "total_brokerage_paid_inr": round(total_brokerage_paid, 2),
            "net_pnl_inr": round(total_net_pnl, 2),
            "max_drawdown_inr": round(max_drawdown_inr, 2),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "profit_factor": profit_factor,
            "sample_trades": trades[-5:] if total_trades >= 5 else trades
        }

def print_backtest_report(results: dict):
    """Prints a beautiful, clean summary table for the user."""
    print("\n" + "="*55)
    print(f"BACKTEST AUDIT REPORT: {results.get('symbol', 'N/A')}")
    print("="*55)
    if results.get("total_trades", 0) == 0:
        print(results.get("message", "No trades triggered."))
        return

    print(f"  • Total Trades Executed:      {results['total_trades']}")
    print(f"  • Gross Winning Trades:       {results['gross_winning_trades']} ({results['gross_win_rate_pct']}%)")
    print(f"  • Net Winning Trades (w/ Fee):{results['net_winning_trades']} ({results['net_win_rate_pct']}%)")
    print(f"  • Gross Profit/Loss (Raw):    INR {results['gross_pnl_inr']:+.2f}")
    print(f"  • Estimated Brokerage/Tax:    INR {results['total_brokerage_paid_inr']:.2f}")
    print(f"  • NET Realized PnL:           INR {results['net_pnl_inr']:+.2f}")
    print(f"  • Raw Profit Factor:          {results['profit_factor']}")
    print(f"  • Maximum Drawdown:           INR {results['max_drawdown_inr']:.2f} ({results['max_drawdown_pct']}%)")
    print("="*55 + "\n")
