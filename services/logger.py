import logging
from datetime import datetime
import os

def setup_logger(name, log_file, level=logging.INFO):
    """Setup logger with file and console handlers"""

    os.makedirs('storage/logs', exist_ok=True)

    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    handler = logging.FileHandler(log_file)
    handler.setFormatter(formatter)

    console = logging.StreamHandler()
    console.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)
    logger.addHandler(console)

    return logger

market_logger = setup_logger('market', 'storage/logs/market.log')
strategy_logger = setup_logger('strategy', 'storage/logs/strategy.log')
execution_logger = setup_logger('execution', 'storage/logs/execution.log')
