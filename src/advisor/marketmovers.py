"""Index moves and F&O gap-up/gap-down scans, via yfinance.

Both use the same trick as marketdata.fetch_history: yfinance's "current day"
daily bar is populated intraday once the session opens (Open fills first;
High/Low/Close keep updating until the close print lands). So a 5-day daily
download made any time after 09:15 IST already carries today's Open.

A NaN Close alone isn't proof of that, though — yfinance's most recent
settled bar can also show a NaN Close for a while after the market has fully
closed (its adjusted-close backfill lags). So "is this row today's live
bar" is gated on the row's date actually being today (IST), not just on
Close being missing.
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from .models import GapMover, IndexMove

log = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")


def _download(tickers: list[str]) -> pd.DataFrame:
    import yfinance as yf

    return yf.download(
        tickers,
        period="5d",
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        threads=True,
        progress=False,
    )


def _todays_open(df: pd.DataFrame) -> float | None:
    """The Open of today's (IST) live bar, if the download already has one."""
    last_row = df.iloc[-1]
    if df.index[-1].date() != datetime.now(IST).date():
        return None  # most recent row is a past session, however it's filled in
    if pd.notna(last_row["Open"]):
        return float(last_row["Open"])
    return None


def fetch_index_moves(indices: list[dict]) -> list[IndexMove]:
    """indices: [{"name": "NIFTY 50", "ticker": "^NSEI"}, ...]"""
    if not indices:
        return []
    tickers = [i["ticker"] for i in indices]
    raw = _download(tickers)

    out: list[IndexMove] = []
    for idx in indices:
        name, ticker = idx["name"], idx["ticker"]
        try:
            df = raw[ticker] if isinstance(raw.columns, pd.MultiIndex) else raw
            closes = df["Close"].dropna()
            if len(closes) < 2:
                log.warning("marketmovers: not enough history for index %s (%s)", name, ticker)
                continue
            prev_close = float(closes.iloc[-1])
            prev_prev_close = float(closes.iloc[-2])
            prev_change_pct = (prev_close - prev_prev_close) / prev_prev_close * 100.0

            today_open = _todays_open(df)
            gap_pct = ((today_open - prev_close) / prev_close * 100.0) if today_open else None

            out.append(IndexMove(
                name=name, ticker=ticker,
                prev_close=prev_close, prev_change_pct=prev_change_pct,
                today_open=today_open, gap_pct=gap_pct,
            ))
        except Exception as e:  # noqa: BLE001
            log.warning("marketmovers: no data for index %s (%s): %s", name, ticker, e)
    return out


def fetch_fno_gaps(
    symbols: list[str], suffix: str = ".NS", min_gap_pct: float = 0.5,
) -> tuple[list[GapMover], list[GapMover]]:
    """Return (gainers, losers): F&O stocks whose today's open differs from
    yesterday's close by at least min_gap_pct, sorted by descending
    differential (gainers by +gap, losers by |gap|)."""
    if not symbols:
        return [], []
    tickers = {s: f"{s}{suffix}" for s in dict.fromkeys(symbols)}
    raw = _download(list(tickers.values()))

    gainers: list[GapMover] = []
    losers: list[GapMover] = []
    for sym, yts in tickers.items():
        try:
            df = raw[yts] if isinstance(raw.columns, pd.MultiIndex) else raw
            closes = df["Close"].dropna()
            if len(closes) < 1:
                continue
            prev_close = float(closes.iloc[-1])
            open_price = _todays_open(df)
            if open_price is None:
                continue  # no live bar for today yet — nothing to report
            gap_pct = (open_price - prev_close) / prev_close * 100.0
            if gap_pct >= min_gap_pct:
                gainers.append(GapMover(sym, prev_close, open_price, gap_pct))
            elif gap_pct <= -min_gap_pct:
                losers.append(GapMover(sym, prev_close, open_price, gap_pct))
        except Exception as e:  # noqa: BLE001
            log.warning("marketmovers: no data for %s (%s)", sym, e)

    gainers.sort(key=lambda g: -g.gap_pct)
    losers.sort(key=lambda g: g.gap_pct)  # most negative first
    return gainers, losers
