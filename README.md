# 🇮🇳 Indian Stock Market Trading Bot (Antigravity Edition)

An institutional-grade, educational trading bot tailored for the Indian stock market (NSE). Designed from the ground up with **strict pre-trade risk controls, air-gapped paper trading simulation, chronological backtesting, machine-learning experiments, and full SEBI compliance readiness**.

---

## 🌟 Key Features

1. **📊 Real-Time Technical Scanner & Strategy:**
   - Evaluates a 20-Day and 50-Day Simple Moving Average (SMA) crossover system on liquid NSE stocks (`SBIN.NS`, `ITC.NS`, `INFY.NS`, `ICICIBANK.NS`, `RELIANCE.NS`).
   - Strict look-ahead bias prevention: Evaluates signals using strictly closed bars available at the time of calculation.

2. **📈 3-Phase Chronological Backtesting Engine:**
   - Splits historical market data chronologically into:
     - **Train (60%):** In-sample strategy design and parameter tuning.
     - **Validation (20%):** Out-of-sample parameter verification.
     - **Test (20%):** Blind holdout partition evaluated strictly once to prevent data snooping.
   - Realistic Indian cost model deducting:
     - Brokerage (flat ₹20 / order)
     - Securities Transaction Tax (STT: 0.1% on delivery / 0.025% on intraday)
     - Exchange Turnover Fees (NSE: 0.00345%)
     - SEBI Turnover Fees (0.0001%)
     - Stamp Duty (0.015% on BUY)
     - Goods and Services Tax (GST: 18% on brokerage + turnover fees)
     - Realistic market slippage (0.05%).

3. **🤖 Scikit-Learn Walk-Forward ML Experiment:**
   - Predicts next-day return direction using momentum and moving-average distance features.
   - Fits standard scalers and classifiers (Logistic Regression / Random Forest) strictly on training windows to prevent look-ahead contamination.

4. **🛡️ Comprehensive Risk Management Module:**
   - Maximum single order value limit (₹5,000 default).
   - Maximum concurrent open positions limit (3 positions default).
   - Maximum gross portfolio exposure cap (₹15,000 default).
   - Stale market quote rejection (>120s cutoff).
   - Market timing circuit breakers: Rejects orders before 09:30 AM IST (opening freeze) and after 02:45 PM IST (intraday entry cutoff).
   - Mandatory 03:10 PM IST intraday square-off auditing to prevent broker auto-square-off penalty charges.
   - Emergency Kill-Switch with fail-closed protection.

5. **💼 Air-Gapped Paper Trading Engine:**
   - Executes virtual trades locally against NSE market quotes with zero financial risk.
   - Safely persists simulation state atomically to disk (`data/paper_trading_state.json`).
   - Prevents duplicate order re-execution across bot crashes and restarts via client order ID idempotency.
   - Corrupted file recovery: automatically backs up corrupted state and re-initializes cleanly without crashing.

6. **🔌 SEBI-Compliant Broker Adapter Interface:**
   - Standardized `BaseBrokerAdapter` interface supporting both **MockBrokerAdapter** and **DhanBrokerAdapter** (DhanHQ API v2).
   - Implements SEBI Circular 2025/0000013 mandates: static IP whitelisting, daily 2FA/TOTP sessions, 10 requests/second rate limiting, and client correlation ID tagging.
   - **Safe Network Timeout Recovery:** Never blindly retries timed-out HTTP orders; uses correlation-ID reconciliation to verify exchange receipt.
   - **Triple-Interlock Live Safety Lock:** Real broker execution is disabled by default (`LIVE_TRADING_ENABLED = False`).

7. **💻 Interactive Streamlit Web Dashboard:**
   - Real-time portfolio equity, available cash, gross exposure, and unrealized/realized P&L.
   - Interactive candlestick and SMA crossover charts.
   - Virtual order submission widget for testing paper execution live from the browser.
   - Active holdings, order audit book, and closed trade history tables.

---

## 📁 Repository Structure

```
Trading Bot/
├── config.py                     # Central configuration & risk limits
├── app.py                        # Streamlit web control dashboard
├── main.py                       # Interactive CLI entry point
├── requirements.txt              # Project dependencies
├── .env.example                  # Environment credentials template
├── .gitignore                    # Secrets & cache safeguards
├── data/
│   ├── historical/               # Verified 3-year NSE daily OHLCV candles
│   └── paper_trading_state.json  # Persisted paper simulation state
├── src/
│   ├── historical_data.py        # yfinance historical data fetcher & validator
│   ├── sma_strategy.py           # 20/50 SMA crossover strategy
│   ├── ma_backtester.py          # 3-phase backtester & Indian cost model
│   ├── ml_experiment.py          # Walk-forward ML classification experiment
│   ├── risk_manager.py           # Pre-trade risk controls & emergency kill-switch
│   ├── paper_trader.py           # Air-gapped paper trading simulation engine
│   ├── broker_adapter.py         # Broker adapter interface & SEBI compliance
│   ├── live_broker.py            # Live broker connectors (standby mode)
│   └── dashboard_data.py         # Dashboard analytics & secret scrubbers
└── tests/                        # 62 Automated Unit & Integration Tests
    ├── test_historical_data.py
    ├── test_sma_strategy.py
    ├── test_ma_backtester.py
    ├── test_ml_experiment.py
    ├── test_risk_manager.py
    ├── test_paper_engine.py
    ├── test_broker_adapter.py
    └── test_dashboard.py
```

---

## 🚀 Quickstart Guide

### 1. Installation
Clone the repository and install required dependencies:
```bash
git clone https://github.com/manusonagara15-ctrl/Trading-Bot.git
cd Trading-Bot
pip install -r requirements.txt
```

### 2. Run the Interactive Web Dashboard
Launch the dashboard locally:
```bash
streamlit run app.py
```
Open **`http://localhost:8501`** in your browser.

### 3. Run via Command-Line Interface (CLI)
```bash
python main.py
```
Select an option:
- `1`: Run 3-Phase Backtesting Audit
- `2`: Run Real-Time Paper Trading Loop
- `3`: Test Live Price Fetching (NSE)
- `4`: Download & Validate Historical Data
- `5`: Run Scikit-Learn Walk-Forward ML Experiment
- `6`: Launch Streamlit Dashboard

### 4. Run the Full Test Suite
Verify that all 62 automated unit and integration tests pass:
```bash
python -m unittest discover tests
```

---

## 🛡️ Risk Disclaimer

This software is developed strictly for **educational and algorithmic simulation purposes**. Trading in equities, derivatives, and financial instruments involves substantial financial risk. Past performance does not guarantee future results. **Live trading is permanently disabled by default.**
