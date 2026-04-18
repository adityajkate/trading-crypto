"""Health monitoring and explainability panel."""
import time
from datetime import datetime
from typing import Dict, List, Optional

from services.logger import execution_logger


class HealthMonitor:
    """Monitors system health and provides explainability."""

    def __init__(self):
        self.components = {}
        self.last_checks = {}
        self.connectivity_status = {
            'api': False,
            'websocket_market': False,
            'websocket_user': False
        }
        self.server_time_offset = 0
        self.last_message_times = {}

    def check_api_connectivity(self, client) -> Dict:
        """Check Binance API connectivity."""
        try:
            start_time = time.time()
            response = client.ping()
            latency = (time.time() - start_time) * 1000

            self.connectivity_status['api'] = True
            self.last_checks['api'] = time.time()

            return {
                'status': 'OK',
                'latency_ms': round(latency, 2),
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            self.connectivity_status['api'] = False
            execution_logger.error(f"API connectivity check failed: {e}")
            return {
                'status': 'ERROR',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }

    def check_server_time(self, client) -> Dict:
        """Check server time and calculate offset."""
        try:
            server_time = client.time()
            local_time = int(time.time() * 1000)
            self.server_time_offset = server_time['serverTime'] - local_time

            return {
                'status': 'OK',
                'server_time': server_time['serverTime'],
                'local_time': local_time,
                'offset_ms': self.server_time_offset,
                'synced': abs(self.server_time_offset) < 1000
            }

        except Exception as e:
            execution_logger.error(f"Server time check failed: {e}")
            return {
                'status': 'ERROR',
                'error': str(e)
            }

    def get_symbol_filters(self, validator, symbol: str) -> Dict:
        """Get symbol filter information."""
        try:
            symbol_info = validator.get_symbol_info(symbol)

            if not symbol_info:
                return {'status': 'ERROR', 'error': 'Symbol not found'}

            filters = symbol_info.get('filters', {})

            return {
                'status': 'OK',
                'symbol': symbol,
                'tradeable': symbol_info['status'] == 'TRADING',
                'base_asset': symbol_info['baseAsset'],
                'quote_asset': symbol_info['quoteAsset'],
                'price_filter': filters.get('PRICE_FILTER', {}),
                'lot_size': filters.get('LOT_SIZE', {}),
                'min_notional': filters.get('MIN_NOTIONAL', {}),
                'market_lot_size': filters.get('MARKET_LOT_SIZE', {})
            }

        except Exception as e:
            execution_logger.error(f"Failed to get symbol filters: {e}")
            return {'status': 'ERROR', 'error': str(e)}

    def update_websocket_status(self, stream_type: str, connected: bool, last_message: float = None):
        """Update WebSocket connection status."""
        key = f'websocket_{stream_type}'
        self.connectivity_status[key] = connected

        if last_message:
            self.last_message_times[stream_type] = last_message

    def get_websocket_health(self) -> Dict:
        """Get WebSocket connection health."""
        current_time = time.time()
        health = {}

        for stream_type, last_msg in self.last_message_times.items():
            latency = current_time - last_msg if last_msg else None
            health[stream_type] = {
                'connected': self.connectivity_status.get(f'websocket_{stream_type}', False),
                'last_message_ago': round(latency, 2) if latency else None,
                'healthy': latency < 30 if latency else False
            }

        return health

    def explain_signal(self, signal_data: Dict, indicators: Dict) -> Dict:
        """Provide detailed explanation of trading signal."""
        explanation = {
            'signal_type': signal_data.get('type', 'UNKNOWN'),
            'timestamp': datetime.now().isoformat(),
            'price': signal_data.get('price'),
            'rules_passed': [],
            'rules_failed': [],
            'confidence': 0
        }

        # Check each indicator condition
        rules = [
            {
                'name': 'EMA Trend',
                'condition': indicators.get('ema_trend') == 'bullish',
                'value': indicators.get('ema_trend'),
                'description': 'Fast EMA above Slow EMA indicates uptrend'
            },
            {
                'name': 'RSI Level',
                'condition': 30 < indicators.get('rsi', 50) < 70,
                'value': indicators.get('rsi'),
                'description': 'RSI in neutral zone (30-70)'
            },
            {
                'name': 'MACD Signal',
                'condition': indicators.get('macd_signal') == 'bullish',
                'value': indicators.get('macd_histogram'),
                'description': 'MACD histogram positive and increasing'
            },
            {
                'name': 'Volume Confirmation',
                'condition': indicators.get('volume_ratio', 0) > 1.2,
                'value': indicators.get('volume_ratio'),
                'description': 'Volume 20% above average'
            },
            {
                'name': 'Bollinger Position',
                'condition': indicators.get('bb_position') == 'middle',
                'value': indicators.get('bb_position'),
                'description': 'Price in middle Bollinger Band range'
            }
        ]

        passed_count = 0
        for rule in rules:
            if rule['condition']:
                explanation['rules_passed'].append({
                    'name': rule['name'],
                    'value': rule['value'],
                    'description': rule['description']
                })
                passed_count += 1
            else:
                explanation['rules_failed'].append({
                    'name': rule['name'],
                    'value': rule['value'],
                    'description': rule['description']
                })

        explanation['confidence'] = (passed_count / len(rules)) * 100

        return explanation

    def get_order_limits(self, client, symbol: str) -> Dict:
        """Get order rate limits and current usage."""
        try:
            # Get account info which includes order count
            account = client.account()

            return {
                'status': 'OK',
                'can_trade': account.get('canTrade', False),
                'can_withdraw': account.get('canWithdraw', False),
                'can_deposit': account.get('canDeposit', False),
                'update_time': account.get('updateTime'),
                'account_type': account.get('accountType')
            }

        except Exception as e:
            execution_logger.error(f"Failed to get order limits: {e}")
            return {'status': 'ERROR', 'error': str(e)}

    def get_comprehensive_health(self, client, validator, ws_manager, symbol: str) -> Dict:
        """Get comprehensive system health report."""
        health_report = {
            'timestamp': datetime.now().isoformat(),
            'overall_status': 'UNKNOWN',
            'components': {}
        }

        # API connectivity
        health_report['components']['api'] = self.check_api_connectivity(client)

        # Server time sync
        health_report['components']['server_time'] = self.check_server_time(client)

        # WebSocket health
        if ws_manager:
            ws_status = ws_manager.get_connection_status()
            health_report['components']['websocket'] = {
                'market': {
                    'connected': ws_status['market_connected'],
                    'latency': ws_status.get('market_latency')
                },
                'user': {
                    'connected': ws_status['user_connected'],
                    'latency': ws_status.get('user_latency')
                }
            }

        # Symbol filters
        health_report['components']['symbol'] = self.get_symbol_filters(validator, symbol)

        # Order limits
        health_report['components']['limits'] = self.get_order_limits(client, symbol)

        # Determine overall status
        critical_ok = (
            health_report['components']['api']['status'] == 'OK' and
            health_report['components']['server_time']['status'] == 'OK'
        )

        health_report['overall_status'] = 'HEALTHY' if critical_ok else 'DEGRADED'

        return health_report

    def format_health_display(self, health_report: Dict) -> str:
        """Format health report for display."""
        lines = [
            f"=== System Health Report ===",
            f"Timestamp: {health_report['timestamp']}",
            f"Overall Status: {health_report['overall_status']}",
            "",
            "Components:"
        ]

        for component, data in health_report['components'].items():
            status = data.get('status', 'UNKNOWN')
            lines.append(f"  {component.upper()}: {status}")

            if component == 'api' and status == 'OK':
                lines.append(f"    Latency: {data.get('latency_ms')}ms")

            elif component == 'server_time' and status == 'OK':
                synced = "✓" if data.get('synced') else "✗"
                lines.append(f"    Time Sync: {synced} (offset: {data.get('offset_ms')}ms)")

            elif component == 'symbol' and status == 'OK':
                lines.append(f"    Tradeable: {data.get('tradeable')}")
                lines.append(f"    Base/Quote: {data.get('base_asset')}/{data.get('quote_asset')}")

        return "\n".join(lines)
