import requests
import pandas as pd
import time
from datetime import datetime
import config
from services.logger import market_logger

class BinanceData:
    def __init__(self, demo_mode=True):
        self.demo_mode = demo_mode
        self.base_url = config.BINANCE_TESTNET_BASE if demo_mode else config.BINANCE_SPOT_BASE
        self.valid_symbols = None
        self.last_fetch_time = {}

    def test_connection(self):
        """Test API connection and get server time"""
        endpoint = f"{self.base_url}/api/v3/time"
        try:
            response = requests.get(endpoint, timeout=5)
            response.raise_for_status()
            data = response.json()
            server_time = data['serverTime']
            market_logger.info(f"Connection OK. Server time: {server_time}")
            return True, server_time
        except requests.exceptions.RequestException as e:
            market_logger.error(f"Connection failed: {e}")
            return False, None

    def get_exchange_info(self):
        """Fetch valid symbols from exchange"""
        endpoint = f"{self.base_url}/api/v3/exchangeInfo"
        try:
            response = requests.get(endpoint, timeout=10)
            response.raise_for_status()
            data = response.json()
            symbols = [s['symbol'] for s in data['symbols'] if s['status'] == 'TRADING']
            self.valid_symbols = set(symbols)
            market_logger.info(f"Loaded {len(symbols)} valid symbols")
            return symbols
        except requests.exceptions.RequestException as e:
            market_logger.error(f"Failed to get exchange info: {e}")
            return None

    def validate_symbol(self, symbol):
        """Check if symbol is valid"""
        if self.valid_symbols is None:
            self.get_exchange_info()

        if self.valid_symbols and symbol in self.valid_symbols:
            return True

        market_logger.warning(f"Invalid symbol: {symbol}")
        return False

    def get_klines(self, symbol, interval, limit=500, max_retries=3):
        """Fetch historical klines with retry logic"""
        if not self.validate_symbol(symbol):
            return None

        endpoint = f"{self.base_url}/api/v3/klines"
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": min(limit, 1000)
        }

        for attempt in range(max_retries):
            try:
                response = requests.get(endpoint, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()

                df = pd.DataFrame(data, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                    'taker_buy_quote', 'ignore'
                ])

                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')
                df['open'] = df['open'].astype(float)
                df['high'] = df['high'].astype(float)
                df['low'] = df['low'].astype(float)
                df['close'] = df['close'].astype(float)
                df['volume'] = df['volume'].astype(float)

                df = df.sort_values('timestamp').reset_index(drop=True)

                duplicates = df.duplicated(subset=['timestamp']).sum()
                if duplicates > 0:
                    market_logger.warning(f"{symbol}: {duplicates} duplicate candles removed")
                    df = df.drop_duplicates(subset=['timestamp'], keep='last')

                self.last_fetch_time[symbol] = time.time()
                market_logger.info(f"{symbol}: Fetched {len(df)} candles")

                return df[['timestamp', 'close_time', 'open', 'high', 'low', 'close', 'volume']]

            except requests.exceptions.RequestException as e:
                wait_time = 2 ** attempt
                market_logger.error(f"Attempt {attempt+1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(wait_time)
                else:
                    return None

    def get_current_price(self, symbol, max_retries=3):
        """Get real-time price with retry"""
        endpoint = f"{self.base_url}/api/v3/ticker/price"
        params = {"symbol": symbol}

        for attempt in range(max_retries):
            try:
                response = requests.get(endpoint, params=params, timeout=5)
                response.raise_for_status()
                data = response.json()
                price = float(data['price'])
                return price
            except requests.exceptions.RequestException as e:
                wait_time = 2 ** attempt
                if attempt < max_retries - 1:
                    time.sleep(wait_time)
                else:
                    market_logger.error(f"Failed to get price for {symbol}: {e}")
                    return None

    def is_candle_closed(self, df):
        """Check if last candle is closed"""
        if df is None or len(df) == 0:
            return False

        last_close_time = df.iloc[-1]['close_time']
        current_time = pd.Timestamp.now(tz='UTC')

        closed = current_time > last_close_time
        return closed

    def get_account_balance(self, api_key, api_secret):
        """Get account balance (requires signed request)"""
        pass
