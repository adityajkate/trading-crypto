import pandas as pd
from ta.trend import EMAIndicator, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
from ta.volume import OnBalanceVolumeIndicator
import config

def calculate_indicators(df):
    """Calculate all indicators on OHLCV dataframe"""
    if df is None or len(df) < config.EMA_SLOW:
        return None

    df = df.copy()

    # EMA 50 and 200
    ema_fast = EMAIndicator(close=df['close'], window=config.EMA_FAST)
    ema_slow = EMAIndicator(close=df['close'], window=config.EMA_SLOW)
    df['ema_50'] = ema_fast.ema_indicator()
    df['ema_200'] = ema_slow.ema_indicator()

    # ADX 14
    adx = ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=config.ADX_PERIOD)
    df['adx'] = adx.adx()

    # RSI 14
    rsi = RSIIndicator(close=df['close'], window=config.RSI_PERIOD)
    df['rsi'] = rsi.rsi()

    # ATR 14
    atr = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=config.ATR_PERIOD)
    df['atr'] = atr.average_true_range()

    # OBV
    obv = OnBalanceVolumeIndicator(close=df['close'], volume=df['volume'])
    df['obv'] = obv.on_balance_volume()

    # Drop rows with NaN (warmup period)
    df = df.dropna()

    return df

def is_ready(df):
    """Check if enough data for strategy"""
    if df is None or len(df) == 0:
        return False, "No data"

    required_cols = ['ema_50', 'ema_200', 'adx', 'rsi', 'atr', 'obv']
    for col in required_cols:
        if col not in df.columns:
            return False, f"Missing {col}"

    if df[required_cols].isna().any().any():
        return False, "NaN values present"

    if len(df) < 2:
        return False, "Need at least 2 candles"

    return True, "Ready"
