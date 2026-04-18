"""Persistent storage for bot state using SQLite."""
import json
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional

from services.logger import execution_logger


class BotStateManager:
    """Manages persistent bot state in SQLite database."""

    def __init__(self, db_path: str = "storage/bot_state.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize database tables."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Bot configuration table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Open positions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    stop_loss REAL,
                    take_profit REAL,
                    order_id TEXT,
                    status TEXT DEFAULT 'OPEN',
                    opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    closed_at TIMESTAMP,
                    pnl REAL,
                    metadata TEXT
                )
            """)

            # Trade history table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    position_id INTEGER,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    commission REAL,
                    order_id TEXT,
                    status TEXT NOT NULL,
                    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT,
                    FOREIGN KEY (position_id) REFERENCES positions(id)
                )
            """)

            # Signals table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    price REAL NOT NULL,
                    indicators TEXT,
                    confidence REAL,
                    acted_upon INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # System health table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS health_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    component TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()
            conn.close()
            execution_logger.info("Database initialized successfully")

        except Exception as e:
            execution_logger.error(f"Database initialization failed: {e}")
            raise

    def set_config(self, key: str, value: any):
        """Set configuration value."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            value_str = json.dumps(value) if not isinstance(value, str) else value

            cursor.execute("""
                INSERT OR REPLACE INTO bot_config (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """, (key, value_str))

            conn.commit()
            conn.close()

        except Exception as e:
            execution_logger.error(f"Failed to set config {key}: {e}")

    def get_config(self, key: str, default=None):
        """Get configuration value."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT value FROM bot_config WHERE key = ?", (key,))
            result = cursor.fetchone()
            conn.close()

            if result:
                try:
                    return json.loads(result[0])
                except:
                    return result[0]
            return default

        except Exception as e:
            execution_logger.error(f"Failed to get config {key}: {e}")
            return default

    def open_position(self, symbol: str, side: str, entry_price: float,
                     quantity: float, stop_loss: float = None,
                     take_profit: float = None, order_id: str = None,
                     metadata: Dict = None) -> int:
        """Record new open position."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            metadata_str = json.dumps(metadata) if metadata else None

            cursor.execute("""
                INSERT INTO positions (symbol, side, entry_price, quantity,
                                     stop_loss, take_profit, order_id, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (symbol, side, entry_price, quantity, stop_loss, take_profit,
                  order_id, metadata_str))

            position_id = cursor.lastrowid
            conn.commit()
            conn.close()

            execution_logger.info(f"Position opened: ID={position_id}, {symbol} {side}")
            return position_id

        except Exception as e:
            execution_logger.error(f"Failed to open position: {e}")
            return -1

    def close_position(self, position_id: int, pnl: float = None):
        """Close an open position."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE positions
                SET status = 'CLOSED', closed_at = CURRENT_TIMESTAMP, pnl = ?
                WHERE id = ?
            """, (pnl, position_id))

            conn.commit()
            conn.close()

            execution_logger.info(f"Position closed: ID={position_id}, PnL={pnl}")

        except Exception as e:
            execution_logger.error(f"Failed to close position {position_id}: {e}")

    def get_open_positions(self) -> List[Dict]:
        """Get all open positions."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT * FROM positions WHERE status = 'OPEN'
                ORDER BY opened_at DESC
            """)

            positions = [dict(row) for row in cursor.fetchall()]
            conn.close()

            return positions

        except Exception as e:
            execution_logger.error(f"Failed to get open positions: {e}")
            return []

    def record_trade(self, symbol: str, side: str, order_type: str,
                    price: float, quantity: float, status: str,
                    position_id: int = None, order_id: str = None,
                    commission: float = None, metadata: Dict = None) -> int:
        """Record trade execution."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            metadata_str = json.dumps(metadata) if metadata else None

            cursor.execute("""
                INSERT INTO trades (position_id, symbol, side, order_type,
                                  price, quantity, commission, order_id,
                                  status, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (position_id, symbol, side, order_type, price, quantity,
                  commission, order_id, status, metadata_str))

            trade_id = cursor.lastrowid
            conn.commit()
            conn.close()

            return trade_id

        except Exception as e:
            execution_logger.error(f"Failed to record trade: {e}")
            return -1

    def get_trade_history(self, limit: int = 100) -> List[Dict]:
        """Get recent trade history."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT * FROM trades
                ORDER BY executed_at DESC
                LIMIT ?
            """, (limit,))

            trades = [dict(row) for row in cursor.fetchall()]
            conn.close()

            return trades

        except Exception as e:
            execution_logger.error(f"Failed to get trade history: {e}")
            return []

    def record_signal(self, symbol: str, signal_type: str, price: float,
                     indicators: Dict = None, confidence: float = None) -> int:
        """Record trading signal."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            indicators_str = json.dumps(indicators) if indicators else None

            cursor.execute("""
                INSERT INTO signals (symbol, signal_type, price, indicators, confidence)
                VALUES (?, ?, ?, ?, ?)
            """, (symbol, signal_type, price, indicators_str, confidence))

            signal_id = cursor.lastrowid
            conn.commit()
            conn.close()

            return signal_id

        except Exception as e:
            execution_logger.error(f"Failed to record signal: {e}")
            return -1

    def mark_signal_acted(self, signal_id: int):
        """Mark signal as acted upon."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE signals SET acted_upon = 1 WHERE id = ?
            """, (signal_id,))

            conn.commit()
            conn.close()

        except Exception as e:
            execution_logger.error(f"Failed to mark signal {signal_id}: {e}")

    def log_health(self, component: str, status: str, message: str = None):
        """Log system health status."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO health_logs (component, status, message)
                VALUES (?, ?, ?)
            """, (component, status, message))

            conn.commit()
            conn.close()

        except Exception as e:
            execution_logger.error(f"Failed to log health: {e}")

    def get_health_status(self, hours: int = 1) -> List[Dict]:
        """Get recent health logs."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT * FROM health_logs
                WHERE timestamp > datetime('now', '-' || ? || ' hours')
                ORDER BY timestamp DESC
            """, (hours,))

            logs = [dict(row) for row in cursor.fetchall()]
            conn.close()

            return logs

        except Exception as e:
            execution_logger.error(f"Failed to get health status: {e}")
            return []
