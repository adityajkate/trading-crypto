SYMBOLS = ["BTCUSDT", "ETHUSDT"]
TIMEFRAME = "1h"
DEMO_MODE = True

# Bot Mode - Always start in safe mode
BOT_MODE = "DEMO"  # DEMO, TESTNET, LIVE
START_IN_DEMO = True

# Technical Indicators
EMA_FAST = 50
EMA_SLOW = 200
ADX_PERIOD = 14
ADX_THRESHOLD = 20
RSI_PERIOD = 14
RSI_BUY_MIN = 40
RSI_BUY_MAX = 55
ATR_PERIOD = 14
ATR_STOP_MULTIPLIER = 1.5
RISK_REWARD_RATIO = 2.0

# Risk Management
RISK_PER_TRADE = 0.02
MAX_POSITION_SIZE = 0.1

# API Endpoints
BINANCE_SPOT_BASE = "https://api.binance.com"
BINANCE_TESTNET_BASE = "https://testnet.binance.vision"
BINANCE_WS_BASE = "wss://stream.binance.com:9443"
BINANCE_TESTNET_WS_BASE = "wss://testnet.binance.vision"

KLINES_LIMIT = 500

# WebSocket Configuration
WS_RECONNECT_DELAY = 5
WS_PING_TIMEOUT = 60
WS_HEARTBEAT_INTERVAL = 10

# Order Configuration
ORDER_QUERY_ATTEMPTS = 5
ORDER_QUERY_DELAY = 2
ORDER_TIMEOUT = 30

# Health Monitoring
HEALTH_CHECK_INTERVAL = 60
MAX_SERVER_TIME_OFFSET = 1000

# Database
DB_PATH = "storage/bot_state.db"
