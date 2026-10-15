"""
Configuration Settings for the Indian Stock Trading Bot
Tailored for beginners: safe defaults, clear explanations, and strict risk limits.
"""

import os
from datetime import time
from dotenv import load_dotenv

# Load sensitive variables from .env
load_dotenv()

# ==============================================================================
# 1. TRADING ENVIRONMENT & SAFETY MODE
# ==============================================================================
# "PAPER" = Simulated orders using live/historical market data (Zero financial risk)
# "LIVE"  = Real orders sent to your Indian Broker account (Real capital at stake)
# Recommendation: Run "PAPER" first, then switch to "LIVE" with 1 single share.
# Operational Mode & Hard Safety Lock
TRADING_MODE = os.getenv("TRADING_MODE", "PAPER").upper()
LIVE_TRADING_ENABLED = False  # Hard safety lock: live orders strictly disabled
ENABLE_LIVE_BROKER_ADAPTER = False  # Separate adapter interlock: live broker adapter disabled
LIVE_AUTHORIZATION_PASSPHRASE = os.getenv("LIVE_AUTHORIZATION_PASSPHRASE", "STRICT_MANUAL_OVERRIDE_DO_NOT_DEPLOY")

# Broker Choice: "DHAN" or "ANGEL_ONE" (both offer 100% free APIs)
BROKER_CHOICE = "DHAN"


# ==============================================================================
# 2. STRICT RISK MANAGEMENT LIMITS (THE ARMOR)
# ==============================================================================
# Conservative Simulation Settings:
MAX_ORDER_VALUE_INR = 5000.0               # Max value for any single order
MAX_OPEN_POSITIONS = 3                      # Max concurrent open positions
MAX_DAILY_LOSS_INR = 1500.0                 # Emergency Kill Switch threshold
MAX_TOTAL_EXPOSURE_INR = 15000.0           # Max gross portfolio exposure
MAX_DATA_AGE_SECONDS = 120.0               # Stale data cutoff (2 minutes)
DUPLICATE_COOLDOWN_SECONDS = 60.0          # Anti-churn cooldown between orders for same symbol

# Maximum capital to allocate for a single trade (in INR)
MAX_CAPITAL_PER_TRADE_INR = 2000.0

# Maximum number of trades allowed per day (Prevents churn & excessive brokerage)
MAX_DAILY_TRADES = 4

# Stop-Loss: Percentage loss at which the position is closed (subject to market slippage)
STOP_LOSS_PCT = 1.0  # 1.0%

# Take-Profit: Target percentage gain to book profits
TAKE_PROFIT_PCT = 2.0  # 2.0% (1:2 Risk-Reward Ratio)

# ==============================================================================
# 3. INDIAN MARKET TIMINGS (IST: UTC+5:30)
# ==============================================================================
# NSE Equity Market opens at 09:15 AM and closes at 03:30 PM.
# Intraday MIS positions are auto-squared off by brokers around 03:15-03:20 PM with penalties.
MARKET_START_TIME = time(9, 15)
# Avoid trading the first 15 mins (too volatile for simple bots)
BOT_START_TIME = time(9, 30)
# Cease looking for new trades after 02:45 PM
BOT_STOP_NEW_TRADES = time(14, 45)
# Force close any open intraday positions before broker auto-square-off
BOT_SQUARE_OFF_TIME = time(15, 10)

# ==============================================================================
# 4. WATCHLIST (High Liquidity NSE Large-Cap Stocks)
# ==============================================================================
# High volume stocks minimize slippage and ensure rapid order execution.
# yfinance format uses '.NS' suffix for National Stock Exchange of India.
WATCHLIST = [
    "SBIN.NS",
    "ITC.NS",
    "INFY.NS",
    "ICICIBANK.NS",
    "RELIANCE.NS"
]

# Timeframe for intraday candles (e.g., '5m', '15m')
TIMEFRAME = "5m"

# ==============================================================================
# 5. ESTIMATED BROKERAGE & TAXES (Per round-trip trade in India)
# ==============================================================================
# Discount brokers charge flat ₹20 per executed order (₹40 round trip),
# plus STT, GST, SEBI fees, and stamp charges. Total ~ ₹45-50 per trade.
ESTIMATED_BROKERAGE_PER_TRADE = 45.0  # Used in backtester for realistic profit/loss
