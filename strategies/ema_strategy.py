# ================================================
# FILE: strategies/ema_strategy.py
# PURPOSE: EMA Crossover Strategy
#          Fast EMA(9) crosses Slow EMA(21)
#          Better signal quality than simple MA
# ================================================

import pandas as pd
import yfinance as yf

# ── Strategy Settings ─────────────────────────────
FAST_EMA_PERIOD = 9    # Reacts quickly to price
SLOW_EMA_PERIOD = 21   # Shows bigger trend
SIGNAL_PERIOD   = 9    # Signal line smoothing


def calculate_ema(data, period, column='Close'):
    """
    Calculate Exponential Moving Average.
    EMA gives more weight to recent prices.
    """
    data[f'EMA{period}'] = data[column].ewm(
        span=period,
        adjust=False    # Standard EMA calculation
    ).mean().round(2)
    return data


def calculate_ema_signals(data):
    """
    Calculate both EMAs and generate
    crossover signals.
    """
    # Calculate fast and slow EMAs
    data = calculate_ema(data, FAST_EMA_PERIOD)
    data = calculate_ema(data, SLOW_EMA_PERIOD)

    # ── Detect crossovers ─────────────────────────
    # Previous day values
    data['Prev_Fast'] = data[f'EMA{FAST_EMA_PERIOD}'].shift(1)
    data['Prev_Slow'] = data[f'EMA{SLOW_EMA_PERIOD}'].shift(1)

    # Current values
    fast = data[f'EMA{FAST_EMA_PERIOD}']
    slow = data[f'EMA{SLOW_EMA_PERIOD}']
    prev_fast = data['Prev_Fast']
    prev_slow = data['Prev_Slow']

    # ── Generate signals ──────────────────────────
    # BUY: Fast crosses ABOVE slow
    # Yesterday fast was below slow
    # Today fast is above slow
    data['EMA_Signal'] = 'HOLD 🟡'

    buy_condition = (
        (prev_fast <= prev_slow) &  # Was below
        (fast > slow)                # Now above
    )

    sell_condition = (
        (prev_fast >= prev_slow) &  # Was above
        (fast < slow)                # Now below
    )

    data.loc[buy_condition,  'EMA_Signal'] = 'BUY 🟢'
    data.loc[sell_condition, 'EMA_Signal'] = 'SELL 🔴'

    # ── Trend direction ───────────────────────────
    # Even when no crossover — tell us the trend
    data['EMA_Trend'] = 'NEUTRAL ↔️'
    data.loc[fast > slow, 'EMA_Trend'] = 'UPTREND 📈'
    data.loc[fast < slow, 'EMA_Trend'] = 'DOWNTREND 📉'

    # ── Crossover strength ────────────────────────
    # How far apart are the two EMAs?
    # Bigger gap = stronger trend
    data['EMA_Gap'] = (
        ((fast - slow) / slow) * 100
    ).round(3)

    # Clean up helper columns
    data = data.drop(['Prev_Fast', 'Prev_Slow'], axis=1)

    return data


def get_ema_summary(data):
    """
    Get latest EMA signal summary.
    Returns a clean dictionary for dashboard.
    """
    latest = data.iloc[-1]
    prev   = data.iloc[-2]

    fast_ema = round(float(latest[f'EMA{FAST_EMA_PERIOD}']), 2)
    slow_ema = round(float(latest[f'EMA{SLOW_EMA_PERIOD}']), 2)
    gap      = round(float(latest['EMA_Gap']), 3)
    signal   = latest['EMA_Signal']
    trend    = latest['EMA_Trend']

    # Count how many days since last crossover
    signals      = data['EMA_Signal']
    cross_signals= signals[signals != 'HOLD 🟡']
    days_since   = 0

    if not cross_signals.empty:
        last_cross_idx = cross_signals.index[-1]
        days_since     = len(data) - data.index.get_loc(last_cross_idx) - 1

    return {
        "Fast EMA":        f"₹{fast_ema}",
        "Slow EMA":        f"₹{slow_ema}",
        "EMA Gap":         f"{gap}%",
        "Signal":          signal,
        "Trend":           trend,
        "Days Since Cross":days_since,
    }


def run_ema_backtest(data, starting_capital=100000):
    """
    Backtest EMA crossover strategy.
    Simulates trades based on crossover signals.
    Returns trades and equity curve.
    """
    capital      = starting_capital
    position     = None
    trades       = []
    equity_curve = []

    brokerage    = 0.001   # 0.1% per trade
    stop_loss    = 0.03    # 3% stop loss
    target       = 0.06    # 6% profit target
    max_position = 0.10    # 10% per trade

    for date, row in data.iterrows():
        price  = float(row['Close'])
        signal = row['EMA_Signal']
        trend  = row['EMA_Trend']

        # ── BUY on crossover ──────────────────────
        if signal == 'BUY 🟢' and position is None:
            spend    = capital * max_position
            quantity = int(spend // price)

            if quantity > 0:
                cost      = round(quantity * price * (1 + brokerage), 2)
                capital  -= cost
                position  = {
                    "buy_date":  date,
                    "buy_price": price,
                    "quantity":  quantity,
                    "cost":      cost
                }

        # ── Check exits ───────────────────────────
        elif position is not None:
            buy_price  = position['buy_price']
            quantity   = position['quantity']
            cost       = position['cost']
            change_pct = (price - buy_price) / buy_price

            exit_reason = None

            # Stop loss hit
            if change_pct <= -stop_loss:
                exit_reason = "STOP LOSS"

            # Target hit
            elif change_pct >= target:
                exit_reason = "TARGET HIT"

            # Sell signal — trend reversed
            elif signal == 'SELL 🔴':
                exit_reason = "EMA CROSSOVER"

            # Downtrend — exit to protect capital
            elif trend == 'DOWNTREND 📉' and change_pct < 0:
                exit_reason = "DOWNTREND EXIT"

            # ── Execute sell ──────────────────────
            if exit_reason:
                proceeds  = round(quantity * price * (1 - brokerage), 2)
                pnl       = round(proceeds - cost, 2)
                pnl_pct   = round((pnl / cost) * 100, 2)
                capital  += proceeds

                trades.append({
                    "Buy Date":    position['buy_date'].strftime('%Y-%m-%d'),
                    "Sell Date":   date.strftime('%Y-%m-%d'),
                    "Buy Price":   round(buy_price, 2),
                    "Sell Price":  round(price, 2),
                    "Quantity":    quantity,
                    "P&L":         pnl,
                    "P&L %":       pnl_pct,
                    "Exit Reason": exit_reason,
                    "Result":      "WIN 🟢" if pnl >= 0 else "LOSS 🔴"
                })
                position = None

        # ── Track equity ──────────────────────────
        if position is not None:
            total = capital + (position['quantity'] * price)
        else:
            total = capital

        equity_curve.append({
            "Date":   date,
            "Equity": round(total, 2)
        })

    # ── Performance summary ───────────────────────
    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame(equity_curve).set_index("Date")

    if trades_df.empty:
        return {
            "Total Trades": 0,
            "Win Rate":     "0%",
            "Total P&L":    "₹0",
            "Final Capital":"₹0",
            "Max Drawdown": "N/A"
        }, equity_df, trades_df

    wins       = trades_df[trades_df['P&L'] >= 0]
    win_rate   = round((len(wins) / len(trades_df)) * 100, 2)
    total_pnl  = round(trades_df['P&L'].sum(), 2)
    total_ret  = round(((capital - starting_capital) / starting_capital) * 100, 2)

    equity_df['Peak']     = equity_df['Equity'].cummax()
    equity_df['Drawdown'] = ((equity_df['Equity'] - equity_df['Peak']) / equity_df['Peak'] * 100)
    max_dd     = round(equity_df['Drawdown'].min(), 2)

    best  = trades_df.loc[trades_df['P&L'].idxmax()]
    worst = trades_df.loc[trades_df['P&L'].idxmin()]

    summary = {
        "Total Trades":  len(trades_df),
        "Win Rate":      f"{win_rate}%",
        "Total P&L":     f"₹{total_pnl:,}",
        "Total Return":  f"{total_ret}%",
        "Best Trade":    f"₹{best['P&L']} ({best['P&L %']}%)",
        "Worst Trade":   f"₹{worst['P&L']} ({worst['P&L %']}%)",
        "Max Drawdown":  f"{max_dd}%",
        "Final Capital": f"₹{round(capital):,}",
    }

    return summary, equity_df, trades_df