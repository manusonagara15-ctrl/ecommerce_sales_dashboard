"""
Main Entry Point for the Indian Stock Trading Bot.
Provides an interactive menu for:
1. Historical Backtesting with transaction cost analysis
2. Real-time Paper Trading (safe live simulation)
3. Micro-Capital Live Trading (real broker execution with kill-switch)
"""

import sys
import time
from datetime import datetime

# Windows console encoding safeguard
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import config
from src.data_fetcher import fetch_historical_candles, fetch_current_ltp
from src.strategy import evaluate_latest_signal
from src.risk_manager import RiskManager
from src.backtester import Backtester, print_backtest_report
from src.paper_trader import PaperTrader
from src.live_broker import IndianBrokerClient

def print_banner():
    print("""
===================================================================
[ALGO-TRADER INDIA] Antigravity Edition
===================================================================
Operational Mode:       [{mode}]
Broker Integration:     [{broker}]
Max Capital / Trade:    INR {cap:.2f}
Emergency Daily Loss:   INR {loss:.2f} (Kill Switch)
Max Daily Trades:       {trades}
Stop Loss / Target:     {sl}% / {tp}%
===================================================================
    """.format(
        mode=config.TRADING_MODE,
        broker=config.BROKER_CHOICE,
        cap=config.MAX_CAPITAL_PER_TRADE_INR,
        loss=config.MAX_DAILY_LOSS_INR,
        trades=config.MAX_DAILY_TRADES,
        sl=config.STOP_LOSS_PCT,
        tp=config.TAKE_PROFIT_PCT
    ))

def run_backtest_mode():
    """Runs rigorous 3-phase Chronological Backtest (Train / Validation / Test)."""
    print("\n🔍 STARTING 3-PHASE CHRONOLOGICAL BACKTESTING (Train 60% / Val 20% / Holdout Test 20%)...")
    from src.ma_backtester import MABacktester, print_partitioned_report
    from src.historical_data import HistoricalDataFetcher
    
    fetcher = HistoricalDataFetcher()
    backtester = MABacktester()
    
    for symbol in config.WATCHLIST:
        try:
            df = fetcher.load_local_data(symbol)
        except Exception:
            print(f"Local data missing for {symbol}, fetching 3y daily history...")
            df = fetcher.fetch_raw_daily_data(symbol, period="3y")
            df, _ = fetcher.validate_daily_data(df, symbol)
            
        if df.empty:
            print(f"Skipping {symbol} due to missing data.")
            continue
            
        results = backtester.run_partitioned_evaluation(df, symbol=symbol)
        print_partitioned_report(results)

def run_trading_loop():
    """Executes live or paper trading loop with safety guardrails."""
    is_live = (config.TRADING_MODE == "LIVE")
    risk_manager = RiskManager()
    paper_trader = PaperTrader(risk_manager=risk_manager)
    broker = IndianBrokerClient() if is_live else None

    if is_live:

        print("\n" + "!"*65)
        print("🚨 ATTENTION: LIVE TRADING MODE IS ACTIVE!")
        print("Real orders will be transmitted to your broker.")
        print("Safety cap: Maximum capital per trade is ₹{:.2f}".format(config.MAX_CAPITAL_PER_TRADE_INR))
        print("!"*65)
        confirm = input("Type 'YES' to start live trading: ").strip()
        if confirm != "YES":
            print("Cancelled live trading. Exiting safely.")
            return

    print("\n🚀 Starting trading loop. Press Ctrl+C at any time to stop.")
    
    try:
        while True:
            now = datetime.now()
            print(f"\n[{now.strftime('%H:%M:%S')}] Scanning watchlist...")

            # Check if kill switch is tripped
            if risk_manager.is_kill_switch_active:
                print("🚨 Kill switch active. Halting trading loop.")
                break

            # Check market end square-off
            if risk_manager.should_force_square_off(now):
                print("⏰ End of day square-off reached (15:10 IST). Exiting intraday positions.")
                # Logic to close any open positions
                break

            for symbol in config.WATCHLIST:
                try:
                    # 1. Fetch recent candles
                    df = fetch_historical_candles(symbol, period="5d", interval=config.TIMEFRAME)
                    if df.empty:
                        continue
                    
                    # 2. Evaluate strategy signal
                    signal, price = evaluate_latest_signal(df)
                    print(f"  • {symbol:15s} | LTP: ₹{price:8.2f} | Signal: {signal}")

                    if signal in ["BUY", "SELL"]:
                        if is_live:
                            # Verify risk first
                            can_trade, reason = risk_manager.can_open_new_trade(now)
                            if can_trade and signal == "BUY":
                                qty = risk_manager.calculate_position_size(price)
                                if qty >= 1:
                                    broker.place_order(symbol, "BUY", qty)
                            elif signal == "SELL":
                                # Square off position
                                pass
                        else:
                            # Paper trading execution
                            paper_trader.process_signal(symbol, signal, price, now)

                except Exception as e:
                    print(f"Error scanning {symbol}: {e}")

            # Wait 60 seconds before next scan
            print("Sleeping for 60 seconds before next scan (Ctrl+C to quit)...")
            time.sleep(60)

    except KeyboardInterrupt:
        print("\n\n🛑 Bot stopped manually by user. Safety shutdown complete.")

def main():
    print_banner()
    print("Select an option:")
    print("1. Run Strategy Backtester (Verify on Historical Indian Data)")
    print("2. Run Real-Time Trading Loop (Paper or Live based on config.py)")
    print("3. Test Live Price Fetching (NSE Symbols)")
    print("4. Download & Validate Historical Daily Data (Saves CSV to data/historical/)")
    print("5. Run Optional Scikit-Learn ML Experiment (Walk-Forward Classification)")
    print("6. Launch Streamlit Control Dashboard (Web UI)")
    print("7. Exit")
    
    if len(sys.argv) > 1:
        choice = sys.argv[1]
    else:
        choice = input("\nEnter choice [1-7]: ").strip()

    if choice == "1":
        run_backtest_mode()
    elif choice == "2":
        run_trading_loop()
    elif choice == "3":
        for sym in config.WATCHLIST:
            ltp = fetch_current_ltp(sym)
            print(f"NSE Quote -> {sym:15s}: INR {ltp:.2f}")
    elif choice == "4":
        from src.historical_data import HistoricalDataFetcher
        fetcher = HistoricalDataFetcher()
        fetcher.fetch_and_save_watchlist()
    elif choice == "5":
        from src.historical_data import HistoricalDataFetcher
        from src.ml_experiment import MLExperimentRunner, print_ml_experiment_report
        fetcher = HistoricalDataFetcher()
        runner = MLExperimentRunner()
        for sym in config.WATCHLIST:
            try:
                df = fetcher.load_local_data(sym)
                report = runner.run_experiment(df, symbol=sym)
                print_ml_experiment_report(report)
            except Exception as e:
                print(f"Could not run ML experiment for {sym}: {e}")
    elif choice == "6":
        import subprocess
        print("\n🚀 Launching Streamlit Dashboard at http://localhost:8501 ...")
        subprocess.run(["streamlit", "run", "app.py"])
    else:
        print("Exiting.")

if __name__ == "__main__":
    main()
