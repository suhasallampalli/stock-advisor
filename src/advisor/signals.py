"""Deterministic rule engine: indicators + portfolio state -> SymbolSignal.

Every signal carries its reasons so the email (and you) can see *why*.
Scoring is a transparent weighted tally, not a black box.
"""

from __future__ import annotations

import logging

import pandas as pd

from .indicators import compute
from .models import Action, Holding, SymbolSignal

log = logging.getLogger(__name__)


def _score_to_conf(score: float) -> float:
    # squash a roughly [-6, 6] tally into 0..1
    return max(0.0, min(1.0, 0.5 + score / 12.0))


def evaluate_symbol(
    symbol: str,
    df: pd.DataFrame,
    ind_params: dict,
    sig_params: dict,
    holding: Holding | None,
) -> SymbolSignal:
    ind = compute(df, ind_params)
    held = holding is not None
    reasons: list[str] = []
    score = 0.0  # positive = bullish/add, negative = bearish/reduce

    rsi = ind["rsi"]
    oversold = sig_params.get("rsi_oversold", ind_params.get("rsi_oversold", 32))
    overbought = ind_params.get("rsi_overbought", 70)

    # --- trend -------------------------------------------------------------
    if ind["uptrend"]:
        score += 1.5
        reasons.append("Price above 50 & 200-day averages (uptrend).")
    elif ind["downtrend"]:
        score -= 1.5
        reasons.append("Price below 50 & 200-day averages (downtrend).")

    if ind["golden_cross"]:
        score += 1.5
        reasons.append("20-day average just crossed above the 50-day (bullish).")
    if ind["death_cross"]:
        score -= 1.5
        reasons.append("20-day average just crossed below the 50-day (bearish).")

    # --- momentum --------------------------------------------------------
    if rsi <= oversold:
        score += 1.0
        reasons.append(f"RSI {rsi:.0f} — oversold.")
    elif rsi >= overbought:
        score -= 1.0
        reasons.append(f"RSI {rsi:.0f} — overbought / extended.")

    if ind["macd_cross_up"]:
        score += 1.0
        reasons.append("MACD crossed up through its signal line.")
    if ind["macd_cross_down"]:
        score -= 1.0
        reasons.append("MACD crossed down through its signal line.")

    # --- location -------------------------------------------------------
    if ind["near_high"] and ind["uptrend"]:
        score += 0.5
        reasons.append("Breaking to a 20-day high within an uptrend.")
    if ind["near_low"] and ind["downtrend"]:
        score -= 0.5
        reasons.append("Breaking to a 20-day low within a downtrend.")

    last = ind["last"]
    stop = ind["chandelier_stop"]
    action = Action.WATCH
    target_hint = None

    # --- holding-specific overrides ------------------------------------
    if held:
        gain_pct = holding.pnl_pct
        hard_stop_pct = sig_params.get("hard_stop_pct", 12)
        profit_take_pct = sig_params.get("profit_take_pct", 30)

        if stop and last < stop:
            action = Action.STOPLOSS_HIT
            reasons.insert(0, f"Price {last:.1f} is below the trailing ATR stop {stop:.1f}.")
        elif gain_pct <= -hard_stop_pct:
            action = Action.STOPLOSS_HIT
            reasons.insert(0, f"Down {gain_pct:.1f}% vs your avg cost (hard stop {hard_stop_pct}%).")
        elif ind["death_cross"] or ind["downtrend"]:
            action = Action.EXIT
            reasons.insert(0, "Trend has turned down on a position you hold.")
        elif gain_pct >= profit_take_pct and (rsi >= overbought or ind["macd_cross_down"]):
            action = Action.TRIM
            target_hint = last
            reasons.insert(0, f"Up {gain_pct:.1f}% and momentum fading — consider booking part.")
        elif score >= 2.5 and ind["uptrend"]:
            action = Action.BUY_MORE
            reasons.insert(0, "Held name still in a strong uptrend — candidate to add.")
        else:
            action = Action.HOLD
    else:
        if score >= 3.0 and ind["uptrend"]:
            action = Action.ACCUMULATE
            reasons.insert(0, "Watchlist name: trend + momentum both constructive.")
        elif score >= 1.5:
            action = Action.WATCH_BUY
            reasons.insert(0, "Watchlist name approaching a buy setup.")
        elif score <= -2.0:
            action = Action.AVOID
            reasons.insert(0, "Watchlist name technically weak right now.")
        else:
            action = Action.WATCH

    return SymbolSignal(
        symbol=symbol,
        action=action,
        confidence=_score_to_conf(score),
        reasons=reasons,
        held=held,
        last_price=last,
        prev_close=ind["prev_close"],
        stop_level=stop,
        target_hint=target_hint,
        indicators={k: ind[k] for k in (
            "rsi", "macd_hist", "sma_slow", "sma_trend", "atr_pct", "change_pct",
        )},
    )


_ACTIONABLE = frozenset({
    Action.STOPLOSS_HIT, Action.EXIT, Action.TRIM, Action.BUY_MORE,
    Action.ACCUMULATE, Action.WATCH_BUY,
})
_ACTION_RANK = {  # display priority within the action list
    Action.STOPLOSS_HIT: 0, Action.EXIT: 1, Action.TRIM: 2,
    Action.BUY_MORE: 3, Action.ACCUMULATE: 4, Action.WATCH_BUY: 5,
}


def generate_signals(
    history: dict[str, pd.DataFrame],
    holdings: list[Holding],
    ind_params: dict,
    sig_params: dict,
) -> tuple[list[SymbolSignal], list[SymbolSignal]]:
    by_sym = {h.symbol: h for h in holdings}
    concentration_trim = sig_params.get("concentration_trim_pct", 22)
    total_value = sum(h.current_value for h in holdings) or 1.0
    gap_alert = sig_params.get("gap_alert_pct", 4)

    signals: list[SymbolSignal] = []
    for sym, df in history.items():
        try:
            sig = evaluate_symbol(sym, df, ind_params, sig_params, by_sym.get(sym))
        except Exception as e:  # noqa: BLE001
            log.warning("signal failed for %s: %s", sym, e)
            continue

        # portfolio-level overlays
        if sig.held:
            conc = by_sym[sym].current_value / total_value * 100.0
            if conc >= concentration_trim and sig.action in (Action.HOLD, Action.BUY_MORE):
                sig.action = Action.TRIM
                sig.reasons.insert(0, f"{conc:.0f}% of your book is in this one name — consider trimming.")
            if abs(sig.gap_pct) >= gap_alert:
                sig.reasons.append(f"Overnight gap {sig.gap_pct:+.1f}% — check before acting.")

        signals.append(sig)

    signals.sort(key=lambda s: (_ACTION_RANK.get(s.action, 9), -s.confidence))
    actionable = [s for s in signals if s.action in _ACTIONABLE]
    return signals, actionable
