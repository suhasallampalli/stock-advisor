import numpy as np
import pandas as pd

from advisor.indicators import rsi, sma, macd, compute


def _frame(closes):
    idx = pd.date_range("2023-01-01", periods=len(closes), freq="B")
    return pd.DataFrame({
        "Open": closes, "High": [c * 1.01 for c in closes],
        "Low": [c * 0.99 for c in closes], "Close": closes,
        "Volume": [1_000] * len(closes),
    }, index=idx)


def test_rsi_bounds():
    up = _frame(list(np.linspace(100, 200, 120)))
    val = rsi(up["Close"], 14).iloc[-1]
    assert 60 < val <= 100


def test_sma_value():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    assert sma(s, 5).iloc[-1] == 3.0


def test_compute_keys_present():
    df = _frame(list(np.linspace(100, 130, 260)) )
    out = compute(df, {"sma_fast": 20, "sma_slow": 50, "sma_trend": 200,
                       "rsi_period": 14, "atr_period": 14, "breakout_window": 20})
    for k in ("last", "rsi", "macd_hist", "chandelier_stop", "uptrend", "golden_cross"):
        assert k in out
    assert out["uptrend"] is True
