"""WebSocket manager for real-time Binance data streams."""
import json
import threading
import time
from typing import Callable, Dict, Optional

import websocket

from services.logger import execution_logger


class BinanceWebSocketManager:
    """Manages WebSocket connections for market data and user data streams."""

    def __init__(self, testnet: bool = True):
        self.testnet = testnet
        self.base_url = "wss://testnet.binance.vision/ws" if testnet else "wss://stream.binance.com:9443/ws"

        # WebSocket connections
        self.market_ws = None
        self.user_ws = None

        # Connection state
        self.market_connected = False
        self.user_connected = False

        # Callbacks
        self.kline_callback = None
        self.ticker_callback = None
        self.order_callback = None
        self.account_callback = None

        # Heartbeat monitoring
        self.last_market_ping = 0
        self.last_user_ping = 0
        self.ping_timeout = 60  # seconds

        # Reconnection
        self.should_reconnect = True
        self.reconnect_delay = 5

        # Threads
        self.market_thread = None
        self.user_thread = None
        self.heartbeat_thread = None

    def start_market_stream(self, symbol: str, interval: str = "1m"):
        """Start market data WebSocket stream."""
        stream_name = f"{symbol.lower()}@kline_{interval}"
        url = f"{self.base_url}/{stream_name}"

        def on_message(ws, message):
            try:
                data = json.loads(message)
                if 'e' in data and data['e'] == 'kline':
                    if self.kline_callback:
                        self.kline_callback(data)
                self.last_market_ping = time.time()
            except Exception as e:
                execution_logger.error(f"Market stream message error: {e}")

        def on_error(ws, error):
            execution_logger.error(f"Market stream error: {error}")
            self.market_connected = False

        def on_close(ws, close_status_code, close_msg):
            execution_logger.warning("Market stream closed")
            self.market_connected = False
            if self.should_reconnect:
                time.sleep(self.reconnect_delay)
                self.start_market_stream(symbol, interval)

        def on_open(ws):
            execution_logger.info(f"Market stream connected: {stream_name}")
            self.market_connected = True
            self.last_market_ping = time.time()

        self.market_ws = websocket.WebSocketApp(
            url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open
        )

        self.market_thread = threading.Thread(
            target=self.market_ws.run_forever,
            kwargs={'ping_interval': 20, 'ping_timeout': 10}
        )
        self.market_thread.daemon = True
        self.market_thread.start()

    def start_user_stream(self, listen_key: str):
        """Start user data WebSocket stream."""
        url = f"{self.base_url}/{listen_key}"

        def on_message(ws, message):
            try:
                data = json.loads(message)
                event_type = data.get('e')

                if event_type == 'executionReport' and self.order_callback:
                    self.order_callback(data)
                elif event_type == 'outboundAccountPosition' and self.account_callback:
                    self.account_callback(data)

                self.last_user_ping = time.time()
            except Exception as e:
                execution_logger.error(f"User stream message error: {e}")

        def on_error(ws, error):
            execution_logger.error(f"User stream error: {error}")
            self.user_connected = False

        def on_close(ws, close_status_code, close_msg):
            execution_logger.warning("User stream closed")
            self.user_connected = False
            if self.should_reconnect:
                time.sleep(self.reconnect_delay)
                self.start_user_stream(listen_key)

        def on_open(ws):
            execution_logger.info("User stream connected")
            self.user_connected = True
            self.last_user_ping = time.time()

        self.user_ws = websocket.WebSocketApp(
            url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open
        )

        self.user_thread = threading.Thread(
            target=self.user_ws.run_forever,
            kwargs={'ping_interval': 20, 'ping_timeout': 10}
        )
        self.user_thread.daemon = True
        self.user_thread.start()

    def start_heartbeat_monitor(self):
        """Monitor WebSocket heartbeats and reconnect if needed."""
        def monitor():
            while self.should_reconnect:
                current_time = time.time()

                # Check market stream
                if self.market_connected and (current_time - self.last_market_ping) > self.ping_timeout:
                    execution_logger.warning("Market stream heartbeat timeout, reconnecting...")
                    if self.market_ws:
                        self.market_ws.close()

                # Check user stream
                if self.user_connected and (current_time - self.last_user_ping) > self.ping_timeout:
                    execution_logger.warning("User stream heartbeat timeout, reconnecting...")
                    if self.user_ws:
                        self.user_ws.close()

                time.sleep(10)

        self.heartbeat_thread = threading.Thread(target=monitor)
        self.heartbeat_thread.daemon = True
        self.heartbeat_thread.start()

    def set_kline_callback(self, callback: Callable):
        """Set callback for kline/candlestick updates."""
        self.kline_callback = callback

    def set_ticker_callback(self, callback: Callable):
        """Set callback for ticker updates."""
        self.ticker_callback = callback

    def set_order_callback(self, callback: Callable):
        """Set callback for order updates."""
        self.order_callback = callback

    def set_account_callback(self, callback: Callable):
        """Set callback for account updates."""
        self.account_callback = callback

    def get_connection_status(self) -> Dict:
        """Get current connection status."""
        return {
            'market_connected': self.market_connected,
            'user_connected': self.user_connected,
            'last_market_ping': self.last_market_ping,
            'last_user_ping': self.last_user_ping,
            'market_latency': time.time() - self.last_market_ping if self.last_market_ping > 0 else None,
            'user_latency': time.time() - self.last_user_ping if self.last_user_ping > 0 else None
        }

    def stop(self):
        """Stop all WebSocket connections."""
        execution_logger.info("Stopping WebSocket connections...")
        self.should_reconnect = False

        if self.market_ws:
            self.market_ws.close()
        if self.user_ws:
            self.user_ws.close()

        self.market_connected = False
        self.user_connected = False
