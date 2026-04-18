import config
from services.logger import strategy_logger

def generate_signal_id(symbol, timestamp):
    """Generate unique signal ID"""
    return f"{symbol}_{timestamp.strftime('%Y%m%d_%H%M%S')}"

def check_long_signal(df, symbol):
    """Check if long entry conditions met"""
    if df is None or len(df) < 2:
        return False, None, None

    current = df.iloc[-1]
    prev = df.iloc[-2]

    signal_id = generate_signal_id(symbol, current['timestamp'])

    # Price above EMA 200
    if current['close'] <= current['ema_200']:
        strategy_logger.debug(f"{signal_id}: Price below EMA 200")
        return False, "Price below EMA 200", signal_id

    # EMA 50 above EMA 200
    if current['ema_50'] <= current['ema_200']:
        strategy_logger.debug(f"{signal_id}: EMA 50 below EMA 200")
        return False, "EMA 50 below EMA 200", signal_id

    # ADX > threshold
    if current['adx'] < config.ADX_THRESHOLD:
        strategy_logger.debug(f"{signal_id}: ADX {current['adx']:.1f} below {config.ADX_THRESHOLD}")
        return False, f"ADX {current['adx']:.1f} below {config.ADX_THRESHOLD}", signal_id

    # RSI in buy zone and turning up
    if not (config.RSI_BUY_MIN <= current['rsi'] <= config.RSI_BUY_MAX):
        strategy_logger.debug(f"{signal_id}: RSI {current['rsi']:.1f} outside buy zone")
        return False, f"RSI {current['rsi']:.1f} outside buy zone", signal_id

    if current['rsi'] <= prev['rsi']:
        strategy_logger.debug(f"{signal_id}: RSI not turning up")
        return False, "RSI not turning up", signal_id

    # OBV rising
    if current['obv'] <= prev['obv']:
        strategy_logger.debug(f"{signal_id}: OBV not rising")
        return False, "OBV not rising", signal_id

    strategy_logger.info(f"{signal_id}: LONG SIGNAL - All conditions met")
    return True, "All conditions met", signal_id

def calculate_stop_loss(entry_price, atr):
    """Calculate stop loss using ATR"""
    stop = entry_price - (config.ATR_STOP_MULTIPLIER * atr)
    return stop

def calculate_take_profit(entry_price, stop_loss):
    """Calculate take profit using risk/reward ratio"""
    risk = entry_price - stop_loss
    target = entry_price + (risk * config.RISK_REWARD_RATIO)
    return target
