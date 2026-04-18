"""Order state engine for handling uncertain outcomes."""
import time
from enum import Enum
from typing import Dict, Optional

from services.logger import execution_logger


class OrderStatus(Enum):
    """Order status states."""
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class OrderStateEngine:
    """Manages order state and handles uncertain outcomes."""

    def __init__(self, client, state_manager):
        self.client = client
        self.state_manager = state_manager
        self.pending_orders = {}
        self.max_query_attempts = 5
        self.query_delay = 2  # seconds

    def submit_order(self, symbol: str, side: str, order_type: str,
                    quantity: str, price: Optional[str] = None,
                    stop_price: Optional[str] = None) -> Dict:
        """Submit order with state tracking."""
        order_result = {
            'status': OrderStatus.PENDING,
            'order_id': None,
            'client_order_id': None,
            'error': None,
            'filled_qty': 0,
            'avg_price': 0
        }

        try:
            # Generate client order ID for tracking
            client_order_id = f"order_{int(time.time() * 1000)}"

            params = {
                'symbol': symbol,
                'side': side,
                'type': order_type,
                'quantity': quantity,
                'newClientOrderId': client_order_id
            }

            if price:
                params['price'] = price
                params['timeInForce'] = 'GTC'

            if stop_price:
                params['stopPrice'] = stop_price

            # Submit order
            execution_logger.info(f"Submitting order: {params}")
            response = self.client.new_order(**params)

            order_result['status'] = OrderStatus.SUBMITTED
            order_result['order_id'] = response.get('orderId')
            order_result['client_order_id'] = client_order_id

            # Track pending order
            self.pending_orders[order_result['order_id']] = {
                'symbol': symbol,
                'side': side,
                'order_type': order_type,
                'quantity': quantity,
                'price': price,
                'submitted_at': time.time(),
                'client_order_id': client_order_id
            }

            # Check immediate fill
            if response.get('status') == 'FILLED':
                order_result['status'] = OrderStatus.FILLED
                order_result['filled_qty'] = float(response.get('executedQty', 0))
                order_result['avg_price'] = float(response.get('price', 0))
                self.pending_orders.pop(order_result['order_id'], None)

            execution_logger.info(f"Order submitted: {order_result}")
            return order_result

        except Exception as e:
            error_msg = str(e)
            execution_logger.error(f"Order submission failed: {error_msg}")

            # Check if timeout or network error
            if 'timeout' in error_msg.lower() or 'connection' in error_msg.lower():
                order_result['status'] = OrderStatus.UNKNOWN
                order_result['error'] = 'TIMEOUT - Status uncertain'

                # Attempt to query order status
                if order_result.get('client_order_id'):
                    reconciled = self.reconcile_order(symbol, order_result['client_order_id'])
                    if reconciled:
                        order_result.update(reconciled)
            else:
                order_result['status'] = OrderStatus.REJECTED
                order_result['error'] = error_msg

            return order_result

    def query_order_status(self, symbol: str, order_id: Optional[int] = None,
                          client_order_id: Optional[str] = None) -> Optional[Dict]:
        """Query order status from exchange."""
        try:
            params = {'symbol': symbol}

            if order_id:
                params['orderId'] = order_id
            elif client_order_id:
                params['origClientOrderId'] = client_order_id
            else:
                return None

            response = self.client.get_order(**params)

            status_map = {
                'NEW': OrderStatus.SUBMITTED,
                'PARTIALLY_FILLED': OrderStatus.PARTIALLY_FILLED,
                'FILLED': OrderStatus.FILLED,
                'CANCELED': OrderStatus.CANCELLED,
                'REJECTED': OrderStatus.REJECTED,
                'EXPIRED': OrderStatus.EXPIRED
            }

            return {
                'status': status_map.get(response['status'], OrderStatus.UNKNOWN),
                'order_id': response['orderId'],
                'client_order_id': response['clientOrderId'],
                'filled_qty': float(response.get('executedQty', 0)),
                'avg_price': float(response.get('price', 0)) if response.get('price') else 0,
                'original_qty': float(response.get('origQty', 0)),
                'time': response.get('time')
            }

        except Exception as e:
            execution_logger.error(f"Order query failed: {e}")
            return None

    def reconcile_order(self, symbol: str, client_order_id: str) -> Optional[Dict]:
        """Reconcile order status after timeout or uncertain outcome."""
        execution_logger.warning(f"Reconciling order: {client_order_id}")

        for attempt in range(self.max_query_attempts):
            time.sleep(self.query_delay)

            result = self.query_order_status(symbol, client_order_id=client_order_id)

            if result:
                execution_logger.info(f"Order reconciled: {result}")
                return result

            execution_logger.warning(f"Reconciliation attempt {attempt + 1} failed")

        execution_logger.error(f"Failed to reconcile order after {self.max_query_attempts} attempts")
        return None

    def handle_execution_report(self, event: Dict):
        """Handle execution report from user data stream."""
        order_id = event.get('i')
        client_order_id = event.get('c')
        status = event.get('X')
        symbol = event.get('s')

        execution_logger.info(f"Execution report: OrderID={order_id}, Status={status}")

        status_map = {
            'NEW': OrderStatus.SUBMITTED,
            'PARTIALLY_FILLED': OrderStatus.PARTIALLY_FILLED,
            'FILLED': OrderStatus.FILLED,
            'CANCELED': OrderStatus.CANCELLED,
            'REJECTED': OrderStatus.REJECTED,
            'EXPIRED': OrderStatus.EXPIRED
        }

        order_status = status_map.get(status, OrderStatus.UNKNOWN)

        # Update pending order
        if order_id in self.pending_orders:
            self.pending_orders[order_id]['last_status'] = order_status
            self.pending_orders[order_id]['last_update'] = time.time()

            # Remove if terminal state
            if order_status in [OrderStatus.FILLED, OrderStatus.CANCELLED,
                               OrderStatus.REJECTED, OrderStatus.EXPIRED]:
                self.pending_orders.pop(order_id, None)

        # Record in state manager
        self.state_manager.record_trade(
            symbol=symbol,
            side=event.get('S'),
            order_type=event.get('o'),
            price=float(event.get('p', 0)),
            quantity=float(event.get('q', 0)),
            status=status,
            order_id=str(order_id),
            commission=float(event.get('n', 0)),
            metadata={
                'client_order_id': client_order_id,
                'executed_qty': event.get('z'),
                'cumulative_quote_qty': event.get('Z'),
                'transaction_time': event.get('T')
            }
        )

    def cancel_order(self, symbol: str, order_id: int) -> Dict:
        """Cancel an order."""
        try:
            response = self.client.cancel_order(symbol=symbol, orderId=order_id)

            execution_logger.info(f"Order cancelled: {order_id}")

            self.pending_orders.pop(order_id, None)

            return {
                'status': OrderStatus.CANCELLED,
                'order_id': order_id,
                'cancelled_at': time.time()
            }

        except Exception as e:
            execution_logger.error(f"Cancel order failed: {e}")
            return {
                'status': OrderStatus.UNKNOWN,
                'error': str(e)
            }

    def get_pending_orders(self) -> Dict:
        """Get all pending orders."""
        return self.pending_orders.copy()

    def cleanup_stale_orders(self, max_age_seconds: int = 3600):
        """Remove stale pending orders."""
        current_time = time.time()
        stale_orders = []

        for order_id, order_data in self.pending_orders.items():
            age = current_time - order_data['submitted_at']
            if age > max_age_seconds:
                stale_orders.append(order_id)

        for order_id in stale_orders:
            execution_logger.warning(f"Removing stale order: {order_id}")
            self.pending_orders.pop(order_id, None)

        return len(stale_orders)
