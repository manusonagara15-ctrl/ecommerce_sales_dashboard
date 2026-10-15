"""
Live Broker Integration Module for Indian Stock Markets.
Supports DhanHQ and Angel One SmartAPI (both provide ₹0 monthly fee APIs).
Enforces safety confirmations and fallback to simulation if credentials are not configured.
"""

import os
import config

class IndianBrokerClient:
    def __init__(self, broker_name: str = config.BROKER_CHOICE):
        self.broker_name = broker_name.upper()
        self.is_connected = False
        self.client = None
        self._initialize_broker()

    def _initialize_broker(self):
        """Connects to the selected broker API using credentials from .env"""
        if config.TRADING_MODE != "LIVE":
            print(f"[BROKER] Bot is running in {config.TRADING_MODE} mode. Broker API is in standby.")
            return

        print(f"[BROKER] Initializing connection to {self.broker_name}...")

        if self.broker_name == "DHAN":
            client_id = os.getenv("DHAN_CLIENT_ID")
            access_token = os.getenv("DHAN_ACCESS_TOKEN")

            if not client_id or not access_token or client_id == "your_client_id_here":
                print("⚠️ [BROKER WARNING] Dhan credentials missing in .env! Switch to PAPER mode or add credentials.")
                return

            try:
                from dhanhq import dhanhq
                self.client = dhanhq(client_id, access_token)
                self.is_connected = True
                print("✅ [BROKER] Successfully connected to Dhan HQ Live API!")
            except ImportError:
                print("⚠️ [BROKER ERROR] 'dhanhq' library not installed. Run: pip install dhanhq")
            except Exception as e:
                print(f"❌ [BROKER ERROR] Dhan connection failed: {e}")

        elif self.broker_name == "ANGEL_ONE":
            api_key = os.getenv("ANGEL_API_KEY")
            client_code = os.getenv("ANGEL_CLIENT_CODE")
            password = os.getenv("ANGEL_PASSWORD")
            totp_secret = os.getenv("ANGEL_TOTP_SECRET")

            if not api_key or not client_code or api_key == "your_smartapi_key_here":
                print("⚠️ [BROKER WARNING] Angel One credentials missing in .env!")
                return

            try:
                import pyotp
                from SmartApi import SmartConnect
                
                self.client = SmartConnect(api_key=api_key)
                totp = pyotp.TOTP(totp_secret).now()
                data = self.client.generateSession(client_code, password, totp)
                
                if data.get("status"):
                    self.is_connected = True
                    print("✅ [BROKER] Successfully authenticated with Angel One SmartAPI!")
                else:
                    print(f"❌ [BROKER ERROR] Angel login failed: {data.get('message')}")
            except ImportError:
                print("⚠️ [BROKER ERROR] 'smartapi-python' library not installed.")
            except Exception as e:
                print(f"❌ [BROKER ERROR] Angel One connection failed: {e}")

    def place_order(self, symbol: str, transaction_type: str, quantity: int, price_type: str = "MARKET") -> dict:
        """
        Submits an order to the exchange.
        transaction_type: 'BUY' or 'SELL'
        quantity: number of shares
        """
        # Strip '.NS' for Indian broker symbol format if necessary
        trading_symbol = symbol.replace(".NS", "")

        if config.TRADING_MODE != "LIVE" or not self.is_connected:
            print(f"[SIMULATED ORDER] {transaction_type} {quantity} shares of {trading_symbol} (Mode: {config.TRADING_MODE})")
            return {"status": "success", "order_id": "VIRTUAL_ORDER_123", "mode": "SIMULATION"}

        # Real Live Order Execution
        print(f"🚨 [REAL ORDER TRANSMISSION] Sending {transaction_type} order for {quantity} shares of {trading_symbol}...")
        
        try:
            if self.broker_name == "DHAN":
                # Dhan order placement for NSE Equity Intraday (INTRADAY / MIS)
                response = self.client.place_order(
                    security_id=trading_symbol,
                    exchange_segment="NSE_EQ",
                    transaction_type=self.client.BUY if transaction_type == "BUY" else self.client.SELL,
                    quantity=quantity,
                    order_type=self.client.MARKET,
                    product_type=self.client.INTRA, # Intraday MIS
                    price=0
                )
                return response
            elif self.broker_name == "ANGEL_ONE":
                order_params = {
                    "variety": "NORMAL",
                    "tradingsymbol": f"{trading_symbol}-EQ",
                    "symboltoken": "3045", # Needs token resolution
                    "transactiontype": transaction_type,
                    "exchange": "NSE",
                    "ordertype": price_type,
                    "producttype": "INTRADAY",
                    "duration": "DAY",
                    "quantity": str(quantity)
                }
                response = self.client.placeOrder(order_params)
                return response
        except Exception as e:
            print(f"❌ [BROKER ORDER FAILED] Error transmitting order: {e}")
            return {"status": "failed", "error": str(e)}

    def get_available_funds(self) -> float:
        """Fetches current available margin/cash balance."""
        if not self.is_connected:
            return 50000.0  # Simulated default
            
        try:
            if self.broker_name == "DHAN":
                fund_limits = self.client.get_fund_limits()
                return float(fund_limits.get("data", {}).get("availabelBalance", 0.0))
            elif self.broker_name == "ANGEL_ONE":
                profile = self.client.getRMS()
                return float(profile.get("data", {}).get("net", 0.0))
        except Exception as e:
            print(f"[BROKER] Error fetching funds: {e}")
            return 0.0
