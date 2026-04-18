import time
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
from services.binance_data import BinanceData
from services.binance_trade import BinanceTrade
from services.bot_state import BotStateManager
from services.exchange_validator import ExchangeValidator
from services.health_monitor import HealthMonitor
from services.logger import execution_logger, strategy_logger
from services.order_engine import OrderStateEngine
from services.position_manager import PositionManager
from services.websocket_manager import BinanceWebSocketManager
from strategy.indicators import calculate_indicators, is_ready
from strategy.risk import calculate_position_size, validate_trade
from strategy.signals import (
    calculate_stop_loss,
    calculate_take_profit,
    check_long_signal,
)

st.set_page_config(page_title="Crypto Trading Bot", layout="wide")

# Initialize session state
if "bot_running" not in st.session_state:
    st.session_state.bot_running = False
if "connection_status" not in st.session_state:
    st.session_state.connection_status = None
if "auth_status" not in st.session_state:
    st.session_state.auth_status = None
if "state_manager" not in st.session_state:
    st.session_state.state_manager = BotStateManager(config.DB_PATH)
if "health_monitor" not in st.session_state:
    st.session_state.health_monitor = HealthMonitor()
if "ws_manager" not in st.session_state:
    st.session_state.ws_manager = None


def get_secret(name):
    """Read and normalize a secret value."""
    value = st.secrets.get(name)
    if isinstance(value, str):
        value = value.strip()
    return value or None


def get_available_credentials():
    """Build credential candidates in priority order."""
    candidates = []

    testnet_key = get_secret("BINANCE_TESTNET_API_KEY")
    testnet_secret = get_secret("BINANCE_TESTNET_API_SECRET")
    if testnet_key and testnet_secret:
        candidates.append(
            {
                "label": "Testnet",
                "api_key": testnet_key,
                "api_secret": testnet_secret,
                "demo_mode": True,
            }
        )

    live_key = get_secret("BINANCE_API_KEY")
    live_secret = get_secret("BINANCE_API_SECRET")
    if live_key and live_secret:
        candidates.append(
            {
                "label": "Live",
                "api_key": live_key,
                "api_secret": live_secret,
                "demo_mode": False,
            }
        )

    return candidates


def get_trade_service(demo_mode):
    """Select the appropriate credential set for the current mode."""
    credentials = get_available_credentials()

    if demo_mode:
        for candidate in credentials:
            if candidate["label"] == "Testnet":
                return BinanceTrade(
                    candidate["api_key"], candidate["api_secret"], demo_mode=True
                )

        for candidate in credentials:
            if candidate["label"] == "Live":
                st.sidebar.info(
                    "Using live API keys for demo auth checks; trades remain paper-only."
                )
                return BinanceTrade(
                    candidate["api_key"], candidate["api_secret"], demo_mode=False
                )
    else:
        for candidate in credentials:
            if candidate["label"] == "Live":
                return BinanceTrade(
                    candidate["api_key"], candidate["api_secret"], demo_mode=False
                )

    raise KeyError("No usable Binance credentials found.")


def format_status(label, status):
    """Render status rows consistently in the sidebar."""
    if not status:
        return

    success_prefixes = (
        "Connected",
        "Valid",
        "Live keys valid",
        "Testnet keys rejected by Binance",
    )
    icon = "[OK]" if status.startswith(success_prefixes) else "[ERR]"
    st.sidebar.write(f"**{label}:** {icon} {status}")


st.title("Crypto Trading Bot - Spot Long Only")

# Sidebar controls
st.sidebar.header("Settings")

bot_mode = st.sidebar.selectbox(
    "Bot Mode",
    ["DEMO", "TESTNET", "LIVE"],
    index=0 if config.START_IN_DEMO else 1
)
demo_mode = bot_mode in ["DEMO", "TESTNET"]

selected_symbol = st.sidebar.selectbox("Symbol", config.SYMBOLS)
risk_per_trade = st.sidebar.number_input(
    "Risk per trade (%)", min_value=0.5, max_value=5.0, value=1.0, step=0.5
)
account_balance = st.sidebar.number_input(
    "Account Balance (USDT)", min_value=100.0, value=1000.0, step=100.0
)

# API keys from secrets
try:
    trade_service = get_trade_service(demo_mode)
except Exception as e:
    st.error(f"API keys not found in secrets.toml: {e}")
    st.stop()

# Initialize services
data_service = BinanceData(demo_mode=demo_mode)
position_manager = PositionManager()
state_manager = st.session_state.state_manager
health_monitor = st.session_state.health_monitor

# Initialize validator and order engine
validator = ExchangeValidator(data_service)
order_engine = OrderStateEngine(trade_service if not demo_mode else None, state_manager)

# Connection health panel
st.sidebar.markdown("---")
st.sidebar.subheader("Connection Health")

if st.sidebar.button("Test Connection"):
    with st.spinner("Testing connection..."):
        # API connectivity
        api_health = health_monitor.check_api_connectivity(data_service)
        st.session_state.connection_status = "Connected" if api_health['status'] == 'OK' else "Failed"

        # Server time sync
        time_health = health_monitor.check_server_time(data_service)

        # Auth check
        auth_ok, auth_msg = trade_service.test_auth()
        if auth_ok:
            if demo_mode and not trade_service.demo_mode:
                st.session_state.auth_status = (
                    "Live keys valid (demo trades stay paper-only)"
                )
            else:
                st.session_state.auth_status = "Valid"
        elif demo_mode and trade_service.demo_mode:
            live_candidates = [
                c for c in get_available_credentials() if c["label"] == "Live"
            ]
            if live_candidates:
                fallback = live_candidates[0]
                fallback_service = BinanceTrade(
                    fallback["api_key"], fallback["api_secret"], demo_mode=False
                )
                live_auth_ok, live_auth_msg = fallback_service.test_auth()

                if live_auth_ok:
                    st.session_state.auth_status = (
                        "Testnet keys rejected by Binance; live keys are valid and demo trades stay paper-only"
                    )
                else:
                    st.session_state.auth_status = (
                        f"Testnet auth failed: {auth_msg} | Live auth failed: {live_auth_msg}"
                    )
            else:
                st.session_state.auth_status = auth_msg
        else:
            st.session_state.auth_status = auth_msg

        # Log health
        state_manager.log_health('api', api_health['status'], str(api_health.get('latency_ms')))
        state_manager.log_health('server_time', time_health['status'], str(time_health.get('offset_ms')))

format_status("API", st.session_state.connection_status)
format_status("Auth", st.session_state.auth_status)
st.sidebar.write(f"**Mode:** {'[DEMO]' if bot_mode == 'DEMO' else '[TESTNET]' if bot_mode == 'TESTNET' else '[LIVE]'} {bot_mode}")

# Bot control
st.sidebar.markdown("---")
col1, col2 = st.sidebar.columns(2)
if col1.button("Start Bot", disabled=st.session_state.bot_running):
    st.session_state.bot_running = True
    strategy_logger.info("Bot started")
if col2.button("Stop Bot", disabled=not st.session_state.bot_running):
    st.session_state.bot_running = False
    strategy_logger.info("Bot stopped")

st.sidebar.markdown(
    f"**Status:** {'[RUNNING] Running' if st.session_state.bot_running else '[STOPPED] Stopped'}"
)

# Fetch data with caching
@st.cache_data(ttl=60)
def fetch_klines(symbol, timeframe, limit, demo):
    service = BinanceData(demo_mode=demo)
    return service.get_klines(symbol, timeframe, limit)

df = fetch_klines(selected_symbol, config.TIMEFRAME, config.KLINES_LIMIT, demo_mode)

if df is None:
    st.error("Failed to fetch market data. Check connection.")
    st.stop()

# Calculate indicators with caching
@st.cache_data(ttl=60)
def compute_indicators(df_json):
    df = pd.read_json(df_json)
    return calculate_indicators(df)

df_with_indicators = compute_indicators(df.to_json())

if df_with_indicators is None:
    st.error("Not enough data for indicators")
    st.stop()

# Check readiness
ready, ready_msg = is_ready(df_with_indicators)

if not ready:
    st.warning(f"Strategy not ready: {ready_msg}")
    st.stop()

# Get real-time price
current_price = data_service.get_current_price(selected_symbol)
if current_price is None:
    current_price = df_with_indicators.iloc[-1]["close"]
    st.warning("Using last candle close price (real-time fetch failed)")

# Check signal
signal, reason, signal_id = check_long_signal(df_with_indicators, selected_symbol)

# Main layout
col1, col2, col3 = st.columns(3)

current_rsi = df_with_indicators.iloc[-1]["rsi"]
current_adx = df_with_indicators.iloc[-1]["adx"]

col1.metric("Price", f"${current_price:.2f}")
col2.metric("RSI", f"{current_rsi:.1f}")
col3.metric("ADX", f"{current_adx:.1f}")

# Signal status
st.subheader("Signal Status")

# Load current position from database
open_positions = state_manager.get_open_positions()
current_position = open_positions[0] if open_positions else None

if signal:
    st.success(f"LONG SIGNAL - {reason}")
    st.write(f"Signal ID: `{signal_id}`")

    current_atr = df_with_indicators.iloc[-1]["atr"]
    stop_loss = calculate_stop_loss(current_price, current_atr)
    take_profit = calculate_take_profit(current_price, stop_loss)
    position_size = calculate_position_size(
        account_balance, risk_per_trade, current_price, stop_loss
    )

    st.write(f"Entry: ${current_price:.2f}")
    st.write(
        f"Stop Loss: ${stop_loss:.2f} ({((stop_loss / current_price - 1) * 100):.2f}%)"
    )
    st.write(
        f"Take Profit: ${take_profit:.2f} ({((take_profit / current_price - 1) * 100):.2f}%)"
    )
    st.write(
        f"Position Size: {position_size:.4f} {selected_symbol.replace('USDT', '')}"
    )

    # Execute trade if bot running, no position, and signal not executed
    if (
        st.session_state.bot_running
        and current_position is None
        and not position_manager.is_signal_executed(signal_id)
    ):
        valid, msg = validate_trade(selected_symbol, position_size, current_price)
        if valid:
            # Validate with exchange filters
            validation_result = validator.validate_order(
                selected_symbol,
                position_size,
                current_price
            )

            if validation_result['valid']:
                st.info("Paper trade executed")

                position_id = state_manager.open_position(
                    symbol=selected_symbol,
                    side='BUY',
                    entry_price=current_price,
                    quantity=position_size,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    metadata={'signal_id': signal_id}
                )

                state_manager.record_signal(
                    symbol=selected_symbol,
                    signal_type='LONG',
                    price=current_price,
                    indicators={
                        'rsi': float(current_rsi),
                        'adx': float(current_adx),
                        'atr': float(current_atr)
                    },
                    confidence=100.0
                )

                position_manager.mark_signal_executed(signal_id)
                execution_logger.info(f"Position opened: ID={position_id}")

                st.rerun()
            else:
                st.warning(f"Exchange validation failed: {validation_result['reason']}")
        else:
            st.warning(f"Trade validation failed: {msg}")
    elif position_manager.is_signal_executed(signal_id):
        st.info("Signal already executed")
else:
    st.info(f"No signal - {reason}")

# Current position
st.subheader("Current Position")
if current_position:
    pos = current_position
    entry_price = pos["entry_price"]
    quantity = pos["quantity"]
    pnl = (current_price - entry_price) * quantity
    pnl_pct = ((current_price / entry_price) - 1) * 100

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Symbol", pos["symbol"])
    col2.metric("Entry", f"${entry_price:.2f}")
    col3.metric("Quantity", f"{quantity:.4f}")
    col4.metric("PnL", f"${pnl:.2f}", f"{pnl_pct:.2f}%")

    # Check exit conditions
    if current_price <= pos["stop_loss"]:
        st.error("Stop loss hit!")

        pnl_final = (current_price - entry_price) * quantity

        state_manager.close_position(pos['id'], pnl=pnl_final)
        state_manager.record_trade(
            symbol=pos['symbol'],
            side='SELL',
            order_type='MARKET',
            price=current_price,
            quantity=quantity,
            status='FILLED',
            position_id=pos['id'],
            metadata={'exit_reason': 'Stop Loss'}
        )

        execution_logger.info(f"Position closed (SL): ID={pos['id']}, PnL={pnl_final}")

        position_manager.clear_position()
        time.sleep(1)
        st.rerun()

    elif current_price >= pos["take_profit"]:
        st.success("Take profit hit!")

        pnl_final = (current_price - entry_price) * quantity

        state_manager.close_position(pos['id'], pnl=pnl_final)
        state_manager.record_trade(
            symbol=pos['symbol'],
            side='SELL',
            order_type='MARKET',
            price=current_price,
            quantity=quantity,
            status='FILLED',
            position_id=pos['id'],
            metadata={'exit_reason': 'Take Profit'}
        )

        execution_logger.info(f"Position closed (TP): ID={pos['id']}, PnL={pnl_final}")

        position_manager.clear_position()
        time.sleep(1)
        st.rerun()
else:
    st.write("No open position")

# Chart with fragment for live updates
@st.fragment(run_every=3)
def render_chart():
    fig = go.Figure()

    fig.add_trace(
        go.Candlestick(
            x=df_with_indicators["timestamp"],
            open=df_with_indicators["open"],
            high=df_with_indicators["high"],
            low=df_with_indicators["low"],
            close=df_with_indicators["close"],
            name="Price",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=df_with_indicators["timestamp"],
            y=df_with_indicators["ema_50"],
            name="EMA 50",
            line=dict(color="blue", width=1),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=df_with_indicators["timestamp"],
            y=df_with_indicators["ema_200"],
            name="EMA 200",
            line=dict(color="red", width=1),
        )
    )

    fig.update_layout(
        xaxis_title="Time",
        yaxis_title="Price (USDT)",
        height=500,
        xaxis_rangeslider_visible=False,
    )

    st.plotly_chart(fig, use_container_width=True)

st.subheader("Price Chart")
render_chart()

# Trade log from database
st.subheader("Trade Log")
trades = state_manager.get_trade_history(limit=100)

if trades:
    trades_df = pd.DataFrame(trades)

    # Calculate PnL from trades
    closed_positions = {}
    for trade in trades:
        pos_id = trade.get('position_id')
        if pos_id:
            if pos_id not in closed_positions:
                closed_positions[pos_id] = {'entry': None, 'exit': None, 'quantity': 0}

            if trade['side'] == 'BUY':
                closed_positions[pos_id]['entry'] = trade['price']
                closed_positions[pos_id]['quantity'] = trade['quantity']
            elif trade['side'] == 'SELL':
                closed_positions[pos_id]['exit'] = trade['price']

    # Build display dataframe
    display_trades = []
    for pos_id, data in closed_positions.items():
        if data['entry'] and data['exit']:
            pnl = (data['exit'] - data['entry']) * data['quantity']
            display_trades.append({
                'position_id': pos_id,
                'entry': data['entry'],
                'exit': data['exit'],
                'quantity': data['quantity'],
                'pnl': pnl
            })

    if display_trades:
        display_df = pd.DataFrame(display_trades)
        st.dataframe(display_df, use_container_width=True)

        total_pnl = display_df["pnl"].sum()
        win_rate = (
            (display_df["pnl"] > 0).sum() / len(display_df) * 100
            if len(display_df) > 0
            else 0
        )

        winning_trades = display_df[display_df["pnl"] > 0]
        losing_trades = display_df[display_df["pnl"] < 0]

        avg_win = winning_trades["pnl"].mean() if len(winning_trades) > 0 else 0
        avg_loss = losing_trades["pnl"].mean() if len(losing_trades) > 0 else 0

        profit_factor = (
            abs(winning_trades["pnl"].sum() / losing_trades["pnl"].sum())
            if len(losing_trades) > 0 and losing_trades["pnl"].sum() != 0
            else 0
        )

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total PnL", f"${total_pnl:.2f}")
        col2.metric("Win Rate", f"{win_rate:.1f}%")
        col3.metric("Avg Win", f"${avg_win:.2f}")
        col4.metric("Profit Factor", f"{profit_factor:.2f}")
    else:
        st.write("No closed trades yet")
else:
    st.write("No trades yet")

# Health monitoring panel
st.sidebar.markdown("---")
st.sidebar.subheader("System Health")

if st.sidebar.button("Refresh Health"):
    health_report = health_monitor.get_comprehensive_health(
        data_service,
        validator,
        st.session_state.ws_manager,
        selected_symbol
    )

    with st.sidebar.expander("Health Details", expanded=False):
        st.json(health_report)

# Auto refresh
if st.session_state.bot_running:
    time.sleep(3)
    st.rerun()
