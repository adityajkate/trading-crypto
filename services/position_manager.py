import json
import os
from datetime import datetime

class PositionManager:
    def __init__(self):
        self.position_file = 'storage/position.json'
        self.executed_signals = set()

    def has_position(self, symbol):
        """Check if position exists for symbol"""
        pos = self.load_position()
        return pos is not None and pos.get('symbol') == symbol

    def load_position(self):
        """Load position from file"""
        if not os.path.exists(self.position_file):
            return None

        try:
            with open(self.position_file, 'r') as f:
                return json.load(f)
        except:
            return None

    def save_position(self, position):
        """Save position to file"""
        with open(self.position_file, 'w') as f:
            json.dump(position, f, indent=2, default=str)

    def clear_position(self):
        """Clear position file"""
        if os.path.exists(self.position_file):
            os.remove(self.position_file)

    def is_signal_executed(self, signal_id):
        """Check if signal already executed"""
        return signal_id in self.executed_signals

    def mark_signal_executed(self, signal_id):
        """Mark signal as executed"""
        self.executed_signals.add(signal_id)

    def clear_old_signals(self, max_age_hours=24):
        """Clear old signal IDs to prevent memory bloat"""
        # Simple implementation: clear all if too many
        if len(self.executed_signals) > 1000:
            self.executed_signals.clear()
