"""Daily OHLC history via yfinance (NSE/BSE)."""

from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)


def fetch_history(symbols: list[str], suffix: str = ".NS", lookback_days: int = 400) -> dict[str, pd.DataFrame]:
    """Return {symbol: DataFrame[Open,High,Low,Close,Volume]} indexed by date.
    Symbols are bare NSE tickers ('INFY'); the suffix is appended for yfinance.
    Missing/failed symbols are omitted (logged)."""
    import yfinance as yf

    if not symbols:
        return {}

    tickers = {s: f"{s}{suffix}" for s in dict.fromkeys(symbols)}
    period = f"{max(lookback_days, 60)}d"

    raw = yf.download(
        list(tickers.values()),
        period=period,
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        threads=True,
        progress=False,
    )

    out: dict[str, pd.DataFrame] = {}
    for sym, yts in tickers.items():
        try:
            df = raw[yts] if isinstance(raw.columns, pd.MultiIndex) else raw
            df = df.dropna(subset=["Close"]).copy()
            if len(df) < 30:
                log.warning("marketdata: %s has only %d rows, skipping", sym, len(df))
                continue
            out[sym] = df[["Open", "High", "Low", "Close", "Volume"]]
        except Exception as e:  # noqa: BLE001
            log.warning("marketdata: no data for %s (%s)", sym, e)
    return out
