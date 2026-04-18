import requests
import hmac
import hashlib
import time
from urllib.parse import urlencode
import config
from services.logger import execution_logger

class BinanceTrade:
    def __init__(self, api_key, api_secret, demo_mode=True):
        self.api_key = (api_key or "").strip()
        self.api_secret = (api_secret or "").strip()
        self.demo_mode = demo_mode
        self.base_url = config.BINANCE_TESTNET_BASE if demo_mode else config.BINANCE_SPOT_BASE
        self.time_offset = 0

    def _get_server_time(self):
        """Get Binance server time"""
        endpoint = f"{self.base_url}/api/v3/time"
        try:
            response = requests.get(endpoint, timeout=5)
            response.raise_for_status()
            server_time = response.json()['serverTime']
            local_time = int(time.time() * 1000)
            self.time_offset = server_time - local_time
            return server_time
        except:
            return int(time.time() * 1000)

    def _get_timestamp(self):
        """Get timestamp synced with server"""
        return int(time.time() * 1000) + self.time_offset

    def test_auth(self):
        """Test API key authentication"""
        self._get_server_time()
        endpoint = f"{self.base_url}/api/v3/account"
        params = {
            'timestamp': self._get_timestamp(),
            'recvWindow': 5000
        }
        params['signature'] = self._sign_request(params)

        try:
            response = requests.get(
                endpoint,
                headers=self._get_headers(),
                params=params,
                timeout=5
            )
            response.raise_for_status()
            execution_logger.info("API auth successful")
            return True, "Auth OK"
        except requests.exceptions.HTTPError as e:
            response = e.response
            error_message = self._parse_error_message(response)

            if response is not None and response.status_code in (400, 401):
                execution_logger.error(f"Auth failed: {error_message}")
                return False, error_message

            execution_logger.error(f"Auth failed: {e}")
            return False, str(e)
        except requests.exceptions.RequestException as e:
            execution_logger.error(f"Auth test failed: {e}")
            return False, str(e)

    def _sign_request(self, params):
        """Sign request with HMAC SHA256"""
        query_string = urlencode(params)
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _get_headers(self):
        """Get request headers"""
        return {
            'X-MBX-APIKEY': self.api_key
        }

    def _parse_error_message(self, response):
        """Extract a useful error message from Binance responses."""
        if response is None:
            return "Authentication request failed"

        try:
            payload = response.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict):
            code = payload.get("code")
            message = payload.get("msg", "").strip()

            if code == -2015:
                return "Invalid API key, IP, or permissions for this environment"

            if message:
                return message

        return f"HTTP {response.status_code}: {response.text[:200]}"

    def test_order(self, symbol, side, quantity, order_type='MARKET'):
        """Test order without execution"""
        endpoint = f"{self.base_url}/api/v3/order/test"

        params = {
            'symbol': symbol,
            'side': side,
            'type': order_type,
            'quantity': quantity,
            'timestamp': self._get_timestamp()
        }

        params['signature'] = self._sign_request(params)

        try:
            response = requests.post(
                endpoint,
                headers=self._get_headers(),
                params=params,
                timeout=10
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            print(f"Test order failed: {e}")
            return False

    def place_order(self, symbol, side, quantity, order_type='MARKET', price=None):
        """Place real order"""
        endpoint = f"{self.base_url}/api/v3/order"

        params = {
            'symbol': symbol,
            'side': side,
            'type': order_type,
            'quantity': quantity,
            'timestamp': self._get_timestamp()
        }

        if order_type == 'LIMIT' and price:
            params['price'] = price
            params['timeInForce'] = 'GTC'

        params['signature'] = self._sign_request(params)

        try:
            response = requests.post(
                endpoint,
                headers=self._get_headers(),
                params=params,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Order failed: {e}")
            return None

    def get_open_orders(self, symbol):
        """Get open orders for symbol"""
        endpoint = f"{self.base_url}/api/v3/openOrders"

        params = {
            'symbol': symbol,
            'timestamp': self._get_timestamp()
        }

        params['signature'] = self._sign_request(params)

        try:
            response = requests.get(
                endpoint,
                headers=self._get_headers(),
                params=params,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Failed to get orders: {e}")
            return None
