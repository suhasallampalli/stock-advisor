"""Technical indicators computed with pandas/numpy (no TA-Lib dependency)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def compute(df: pd.DataFrame, p: dict) -> dict:
    """Return a flat dict of the latest indicator readings + a few derived flags."""
    close = df["Close"]
    last = float(close.iloc[-1])
    prev_close = float(close.iloc[-2]) if len(close) > 1 else last

    sma_f = sma(close, p.get("sma_fast", 20))
    sma_s = sma(close, p.get("sma_slow", 50))
    sma_t = sma(close, p.get("sma_trend", 200))
    r = rsi(close, p.get("rsi_period", 14))
    macd_line, macd_sig, macd_hist = macd(
        close, p.get("macd_fast", 12), p.get("macd_slow", 26), p.get("macd_signal", 9)
    )
    a = atr(df, p.get("atr_period", 14))
    win = p.get("breakout_window", 20)
    hi = float(df["High"].rolling(win).max().iloc[-1])
    lo = float(df["Low"].rolling(win).min().iloc[-1])
    recent_high = float(df["High"].tail(66).max())  # ~3 months for chandelier stop

    def f(series: pd.Series, i: int = -1) -> float:
        v = series.iloc[i]
        return float(v) if pd.notna(v) else float("nan")

    golden_cross = (
        len(sma_f) > 2
        and pd.notna(sma_f.iloc[-2])
        and pd.notna(sma_s.iloc[-2])
        and sma_f.iloc[-2] <= sma_s.iloc[-2]
        and sma_f.iloc[-1] > sma_s.iloc[-1]
    )
    death_cross = (
        len(sma_f) > 2
        and pd.notna(sma_f.iloc[-2])
        and pd.notna(sma_s.iloc[-2])
        and sma_f.iloc[-2] >= sma_s.iloc[-2]
        and sma_f.iloc[-1] < sma_s.iloc[-1]
    )
    macd_cross_up = (
        len(macd_hist) > 2 and macd_hist.iloc[-2] <= 0 < macd_hist.iloc[-1]
    )
    macd_cross_down = (
        len(macd_hist) > 2 and macd_hist.iloc[-2] >= 0 > macd_hist.iloc[-1]
    )

    atr_last = f(a)
    chandelier_stop = recent_high - p.get("atr_stop_mult", 3.0) * atr_last if atr_last == atr_last else None

    return {
        "last": last,
        "prev_close": prev_close,
        "change_pct": (last - prev_close) / prev_close * 100.0 if prev_close else 0.0,
        "sma_fast": f(sma_f),
        "sma_slow": f(sma_s),
        "sma_trend": f(sma_t),
        "above_trend": last > f(sma_t) if f(sma_t) == f(sma_t) else None,
        "rsi": f(r),
        "macd": f(macd_line),
        "macd_signal": f(macd_sig),
        "macd_hist": f(macd_hist),
        "atr": atr_last,
        "atr_pct": (atr_last / last * 100.0) if last and atr_last == atr_last else float("nan"),
        f"high_{win}d": hi,
        f"low_{win}d": lo,
        "near_high": last >= hi * 0.985,
        "near_low": last <= lo * 1.015,
        "chandelier_stop": chandelier_stop,
        "golden_cross": bool(golden_cross),
        "death_cross": bool(death_cross),
        "macd_cross_up": bool(macd_cross_up),
        "macd_cross_down": bool(macd_cross_down),
        "uptrend": last > f(sma_s) > f(sma_t) if f(sma_t) == f(sma_t) else last > f(sma_s),
        "downtrend": last < f(sma_s) < f(sma_t) if f(sma_t) == f(sma_t) else last < f(sma_s),
    }
