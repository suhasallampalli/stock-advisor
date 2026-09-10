import numpy as np
import pandas as pd

from advisor.models import Action, Holding
from advisor.signals import evaluate_symbol, generate_signals

IND = {"sma_fast": 20, "sma_slow": 50, "sma_trend": 200, "rsi_period": 14,
       "rsi_overbought": 70, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
       "atr_period": 14, "breakout_window": 20}
SIG = {"rsi_oversold": 32, "concentration_trim_pct": 22, "profit_take_pct": 30,
       "atr_stop_mult": 3.0, "hard_stop_pct": 12, "gap_alert_pct": 4}


def _frame(closes):
    idx = pd.date_range("2022-01-01", periods=len(closes), freq="B")
    return pd.DataFrame({
        "Open": closes, "High": [c * 1.015 for c in closes],
        "Low": [c * 0.985 for c in closes], "Close": closes,
        "Volume": [1_000] * len(closes),
    }, index=idx)


def test_downtrend_holding_flags_exit_or_stop():
    closes = list(np.linspace(200, 120, 260))
    df = _frame(closes)
    h = Holding("ABC", 10, 210.0, closes[-1], "zerodha")
    sig = evaluate_symbol("ABC", df, IND, SIG, h)
    assert sig.action in (Action.EXIT, Action.STOPLOSS_HIT)


def test_uptrend_with_pullback_is_constructive():
    # long uptrend, then a modest pullback that cools RSI without breaking trend
    closes = list(np.linspace(100, 190, 240)) + list(np.linspace(190, 172, 20))
    df = _frame(closes)
    sig = evaluate_symbol("XYZ", df, IND, SIG, None)
    assert sig.action in (Action.ACCUMULATE, Action.WATCH_BUY, Action.WATCH)
    assert sig.indicators["sma_trend"] < sig.last_price  # still above the 200-day


def test_concentration_overlay_forces_trim():
    closes = list(np.linspace(100, 180, 260))
    hist = {"BIG": _frame(closes), "SMALL": _frame(closes)}
    holds = [
        Holding("BIG", 100, 100.0, closes[-1], "zerodha"),   # ~dominant
        Holding("SMALL", 1, 100.0, closes[-1], "zerodha"),
    ]
    _, actionable = generate_signals(hist, holds, IND, SIG)
    big = next(s for s in actionable if s.symbol == "BIG")
    assert big.action == Action.TRIM
