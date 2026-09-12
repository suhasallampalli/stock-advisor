from datetime import datetime

import numpy as np
import pandas as pd

from advisor.marketmovers import IST, fetch_fno_gaps, fetch_index_moves


def _daily_frame(closes, today_open=None, stale_nan_close=False):
    """A few finished days, optionally + one in-progress "today" row with only
    Open set. `stale_nan_close` appends an extra *past-dated* NaN-Close row
    (mimicking yfinance's adjusted-close backfill lag) to check it is NOT
    mistaken for today's live bar."""
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="B")
    df = pd.DataFrame({
        "Open": closes, "High": [c * 1.01 for c in closes],
        "Low": [c * 0.99 for c in closes], "Close": closes,
        "Volume": [1_000] * len(closes),
    }, index=idx)
    if stale_nan_close:
        extra_idx = pd.date_range(idx[-1] + pd.Timedelta(days=1), periods=1, freq="B")
        extra = pd.DataFrame({
            "Open": [closes[-1]], "High": [closes[-1]], "Low": [closes[-1]],
            "Close": [np.nan], "Volume": [1_000],
        }, index=extra_idx)
        df = pd.concat([df, extra])
    if today_open is not None:
        today = pd.Timestamp(datetime.now(IST).date())
        extra = pd.DataFrame({
            "Open": [today_open], "High": [today_open], "Low": [today_open],
            "Close": [np.nan], "Volume": [0],
        }, index=[today])
        df = pd.concat([df, extra])
    return df


def test_fetch_fno_gaps_sorts_by_descending_differential(monkeypatch):
    frames = {
        "UP_BIG.NS": _daily_frame([100, 101, 102], today_open=112),   # +9.8%
        "UP_SMALL.NS": _daily_frame([100, 101, 102], today_open=104), # +1.96%
        "DOWN_BIG.NS": _daily_frame([100, 101, 102], today_open=90),  # -11.8%
        "DOWN_SMALL.NS": _daily_frame([100, 101, 102], today_open=99),# -2.9%
        "FLAT.NS": _daily_frame([100, 101, 102], today_open=102.1),   # within threshold
    }
    raw = pd.concat(frames, axis=1)

    monkeypatch.setattr("advisor.marketmovers._download", lambda tickers: raw)

    gainers, losers = fetch_fno_gaps(
        ["UP_BIG", "UP_SMALL", "DOWN_BIG", "DOWN_SMALL", "FLAT"], ".NS", min_gap_pct=0.5,
    )

    assert [g.symbol for g in gainers] == ["UP_BIG", "UP_SMALL"]
    assert [g.gap_pct for g in gainers] == sorted((g.gap_pct for g in gainers), reverse=True)

    assert [g.symbol for g in losers] == ["DOWN_BIG", "DOWN_SMALL"]
    assert all(g.gap_pct < 0 for g in losers)
    # losers sorted by descending |differential| == most negative first
    assert [g.gap_pct for g in losers] == sorted((g.gap_pct for g in losers))


def test_fetch_index_moves_computes_prev_day_change_and_gap(monkeypatch):
    raw = _daily_frame([100, 110, 121], today_open=125)  # prev day +10%, gap +3.3%

    monkeypatch.setattr("advisor.marketmovers._download", lambda tickers: raw)

    out = fetch_index_moves([{"name": "NIFTY 50", "ticker": "^NSEI"}])
    assert len(out) == 1
    idx = out[0]
    assert idx.prev_close == 121
    assert round(idx.prev_change_pct, 2) == 10.0
    assert idx.today_open == 125
    assert round(idx.gap_pct, 2) == round((125 - 121) / 121 * 100, 2)


def test_stale_nan_close_on_a_past_row_is_not_mistaken_for_todays_open(monkeypatch):
    """Regression: yfinance's most recent SETTLED bar can show a NaN Close for a
    while (adjusted-close backfill lag). That row is dated in the past, not
    today, so it must not be reported as a live gap-up/gap-down."""
    raw = _daily_frame([100, 101, 1000], stale_nan_close=True)  # last real close pending

    monkeypatch.setattr("advisor.marketmovers._download", lambda tickers: raw)

    gainers, losers = fetch_fno_gaps(["WEIRD"], ".NS", min_gap_pct=0.5)
    assert gainers == []
    assert losers == []

    out = fetch_index_moves([{"name": "NIFTY 50", "ticker": "^NSEI"}])
    assert out[0].today_open is None
    assert out[0].gap_pct is None
