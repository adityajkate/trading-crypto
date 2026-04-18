def calculate_position_size(account_balance, risk_percent, entry_price, stop_loss):
    """Calculate position size based on risk per trade"""
    risk_amount = account_balance * (risk_percent / 100)
    price_risk = entry_price - stop_loss

    if price_risk <= 0:
        return 0

    position_size = risk_amount / price_risk
    return position_size

def validate_trade(symbol, quantity, price):
    """Validate trade meets exchange requirements"""
    # Binance min notional ~10 USDT
    notional = quantity * price
    if notional < 10:
        return False, "Notional value below minimum"

    return True, "Valid"
