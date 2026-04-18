"""Pre-trade validation layer for Binance exchange rules."""
import time
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Optional, Tuple

from services.logger import execution_logger


class ExchangeValidator:
    """Validates orders against Binance exchange rules before execution."""

    def __init__(self, client):
        self.client = client
        self.exchange_info = None
        self.symbol_filters = {}
        self.last_update = 0
        self.cache_duration = 3600  # 1 hour

    def refresh_exchange_info(self, force: bool = False) -> bool:
        """Fetch and cache exchange info from Binance."""
        current_time = time.time()

        if not force and self.exchange_info and (current_time - self.last_update) < self.cache_duration:
            return True

        try:
            self.exchange_info = self.client.exchange_info()
            self.last_update = current_time

            # Parse symbol filters
            for symbol_data in self.exchange_info.get('symbols', []):
                symbol = symbol_data['symbol']
                self.symbol_filters[symbol] = {
                    'status': symbol_data['status'],
                    'baseAsset': symbol_data['baseAsset'],
                    'quoteAsset': symbol_data['quoteAsset'],
                    'filters': {}
                }

                for filter_data in symbol_data.get('filters', []):
                    filter_type = filter_data['filterType']
                    self.symbol_filters[symbol]['filters'][filter_type] = filter_data

            execution_logger.info(f"Exchange info refreshed: {len(self.symbol_filters)} symbols")
            return True

        except Exception as e:
            execution_logger.error(f"Failed to refresh exchange info: {e}")
            return False

    def is_symbol_tradeable(self, symbol: str) -> Tuple[bool, str]:
        """Check if symbol is tradeable."""
        if not self.exchange_info:
            if not self.refresh_exchange_info():
                return False, "Exchange info not available"

        if symbol not in self.symbol_filters:
            return False, f"Symbol {symbol} not found"

        status = self.symbol_filters[symbol]['status']
        if status != 'TRADING':
            return False, f"Symbol status: {status}"

        return True, "OK"

    def round_price(self, symbol: str, price: float) -> Optional[str]:
        """Round price according to PRICE_FILTER rules."""
        if symbol not in self.symbol_filters:
            return None

        price_filter = self.symbol_filters[symbol]['filters'].get('PRICE_FILTER')
        if not price_filter:
            return str(price)

        tick_size = Decimal(price_filter['tickSize'])
        min_price = Decimal(price_filter['minPrice'])
        max_price = Decimal(price_filter['maxPrice'])

        price_decimal = Decimal(str(price))

        # Round to tick size
        rounded = (price_decimal / tick_size).quantize(Decimal('1'), rounding=ROUND_DOWN) * tick_size

        # Clamp to min/max
        if rounded < min_price:
            rounded = min_price
        elif rounded > max_price:
            rounded = max_price

        return str(rounded)

    def round_quantity(self, symbol: str, quantity: float) -> Optional[str]:
        """Round quantity according to LOT_SIZE rules."""
        if symbol not in self.symbol_filters:
            return None

        lot_filter = self.symbol_filters[symbol]['filters'].get('LOT_SIZE')
        if not lot_filter:
            return str(quantity)

        step_size = Decimal(lot_filter['stepSize'])
        min_qty = Decimal(lot_filter['minQty'])
        max_qty = Decimal(lot_filter['maxQty'])

        qty_decimal = Decimal(str(quantity))

        # Round to step size
        rounded = (qty_decimal / step_size).quantize(Decimal('1'), rounding=ROUND_DOWN) * step_size

        # Clamp to min/max
        if rounded < min_qty:
            rounded = min_qty
        elif rounded > max_qty:
            rounded = max_qty

        return str(rounded)

    def validate_notional(self, symbol: str, price: float, quantity: float) -> Tuple[bool, str]:
        """Validate order meets MIN_NOTIONAL requirements."""
        if symbol not in self.symbol_filters:
            return False, "Symbol filters not available"

        notional_filter = self.symbol_filters[symbol]['filters'].get('MIN_NOTIONAL')
        if not notional_filter:
            return True, "OK"

        notional = price * quantity
        min_notional = float(notional_filter['minNotional'])

        if notional < min_notional:
            return False, f"Notional {notional:.2f} below minimum {min_notional:.2f}"

        return True, "OK"

    def validate_order(self, symbol: str, side: str, order_type: str,
                      price: Optional[float] = None, quantity: Optional[float] = None) -> Dict:
        """Complete order validation with rounding."""
        result = {
            'valid': False,
            'errors': [],
            'warnings': [],
            'rounded_price': None,
            'rounded_quantity': None
        }

        # Check symbol tradeable
        tradeable, msg = self.is_symbol_tradeable(symbol)
        if not tradeable:
            result['errors'].append(msg)
            return result

        # Round price if provided
        if price is not None:
            rounded_price = self.round_price(symbol, price)
            if rounded_price is None:
                result['errors'].append("Failed to round price")
                return result
            result['rounded_price'] = rounded_price

            if abs(float(rounded_price) - price) / price > 0.001:
                result['warnings'].append(f"Price rounded from {price} to {rounded_price}")

        # Round quantity if provided
        if quantity is not None:
            rounded_qty = self.round_quantity(symbol, quantity)
            if rounded_qty is None:
                result['errors'].append("Failed to round quantity")
                return result
            result['rounded_quantity'] = rounded_qty

            if abs(float(rounded_qty) - quantity) / quantity > 0.001:
                result['warnings'].append(f"Quantity rounded from {quantity} to {rounded_qty}")

        # Validate notional
        if price is not None and quantity is not None:
            valid_notional, msg = self.validate_notional(
                symbol,
                float(result['rounded_price']),
                float(result['rounded_quantity'])
            )
            if not valid_notional:
                result['errors'].append(msg)
                return result

        result['valid'] = len(result['errors']) == 0
        return result

    def test_order(self, symbol: str, side: str, order_type: str,
                   quantity: str, price: Optional[str] = None) -> Tuple[bool, str]:
        """Test order with Binance test endpoint."""
        try:
            params = {
                'symbol': symbol,
                'side': side,
                'type': order_type,
                'quantity': quantity
            }

            if price is not None:
                params['price'] = price

            # Use test order endpoint
            self.client.new_order_test(**params)
            return True, "Test order passed"

        except Exception as e:
            error_msg = str(e)
            execution_logger.error(f"Test order failed: {error_msg}")
            return False, error_msg

    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """Get complete symbol information."""
        if not self.exchange_info:
            self.refresh_exchange_info()

        return self.symbol_filters.get(symbol)
