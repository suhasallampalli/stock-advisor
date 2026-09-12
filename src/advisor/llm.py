"""Claude-written daily commentary over the rule signals.

Uses the Messages API with the server-side web_search tool so the note can
reference recent headlines for names you hold or watch. Output is framed as
personal analysis, never as advice.
"""

from __future__ import annotations

import json
import logging

from .models import Action, GapMover, Report, SymbolSignal

log = logging.getLogger(__name__)

_SYSTEM = """You are a markets analyst writing a short private note to ONE retail \
investor in India about THEIR OWN portfolio. You are not a registered adviser and \
you must not phrase anything as a recommendation, tip, or instruction to buy or \
sell. Describe what the rule-based signals say, add relevant context (recent news, \
sector backdrop, events, results, index trend), flag risks, and note what to watch. \

Rules:
- Refer to the deterministic signals as the "model"; you may agree, disagree, or \
add nuance, but explain your reasoning.
- Be concrete about levels (support/resistance/stop) already in the data.
- Call out anything time-sensitive for the given session (pre-open in India, or \
post-close looking to the next day).
- 250-400 words. Plain prose, a few short paragraphs. No preamble, no sign-off.
- End with one line: "Not investment advice — verify independently."
"""


def _signal_digest(signals: list[SymbolSignal], limit: int = 25) -> list[dict]:
    out = []
    for s in signals[:limit]:
        out.append({
            "symbol": s.symbol,
            "held": s.held,
            "model_action": s.action.value,
            "confidence": round(s.confidence, 2),
            "last": round(s.last_price, 2),
            "gap_pct": round(s.gap_pct, 2),
            "stop_level": round(s.stop_level, 2) if s.stop_level else None,
            "rsi": round(s.indicators.get("rsi", 0), 1),
            "reasons": s.reasons[:4],
        })
    return out


def build_commentary(report: Report, model: str, use_web_search: bool) -> str:
    try:
        import anthropic
    except ImportError:
        log.warning("anthropic SDK not installed; skipping commentary")
        return ""

    p = report.portfolio
    payload = {
        "session": report.session,
        "horizon": report.horizon_label,
        "generated_at": report.generated_at,
        "portfolio": {
            "invested": round(p.total_invested, 0),
            "market_value": round(p.total_value, 0),
            "unrealised_pnl_pct": round(p.unrealised_pnl_pct, 2),
            "realised_pnl_total": round(p.realised_pnl, 0),
            "top_concentration": dict(sorted(p.concentration.items(), key=lambda kv: -kv[1])[:6]),
            "holdings": [
                {"symbol": h.symbol, "qty": h.quantity, "avg": round(h.avg_price, 2),
                 "last": round(h.last_price, 2), "pnl_pct": round(h.pnl_pct, 1)}
                for h in p.holdings
            ],
        },
        "actionable_signals": _signal_digest(report.actionable),
        "other_signals": _signal_digest(
            [s for s in report.signals if s not in report.actionable], limit=15
        ),
    }

    watch_names = sorted({s.symbol for s in report.actionable} |
                         {h.symbol for h in p.holdings})[:12]
    user_msg = (
        "Here is today's portfolio + rule-model output as JSON. Write the note.\n\n"
        f"```json\n{json.dumps(payload, default=str, indent=2)}\n```\n\n"
        + (f"If useful, search for very recent (last 3 days) India-market news on: "
           f"{', '.join(watch_names)}, and the Nifty 50 trend." if use_web_search else "")
    )

    tools = []
    if use_web_search:
        tools = [{
            "type": "web_search_20260209",
            "name": "web_search",
            "max_uses": 5,
            "user_location": {"type": "approximate", "country": "IN"},
        }]

    client = anthropic.Anthropic()
    kwargs = dict(
        model=model,
        max_tokens=4000,
        thinking={"type": "adaptive"},
        system=_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    if tools:
        kwargs["tools"] = tools
    try:
        resp = client.messages.create(**kwargs)
    except anthropic.APIStatusError as e:
        log.error("commentary API error %s: %s", e.status_code, e.message)
        return ""
    except Exception as e:  # noqa: BLE001
        log.error("commentary failed: %s", e)
        return ""

    if resp.stop_reason == "refusal":
        log.warning("commentary refused: %s", getattr(resp, "stop_details", None))
        return ""

    return "\n\n".join(b.text for b in resp.content if b.type == "text").strip()


_MARKET_SYSTEM = """You are a markets analyst writing a short pre-open note for a retail \
investor in India. You are not a registered adviser and must not phrase anything as a \
recommendation, tip, or instruction to buy or sell.

Write two parts, clearly separated by a line containing exactly "---":

1. PREVIOUS DAY HIGHLIGHTS: 2-3 short paragraphs on how the previous trading day went — \
key index moves (use the figures given), the sectors/stocks that drove it, and any major \
news, results, macro data or global cues behind it. Search the web for the previous day's \
India market recap if it helps ground this.

2. TODAY'S OUTLOOK: 1 short paragraph reading on likely trend for today given the previous \
day's action, overnight global cues (US markets, Asian markets, crude, dollar/rupee, \
SGX/GIFT Nifty if you can find it) and today's index opens (given). Frame it as "what the \
data suggests", not as a call to act.

Plain prose, no headers other than the "---" separator, no preamble, no sign-off. Under 350 \
words total.
"""


def build_market_outlook(report: Report, model: str, use_web_search: bool) -> tuple[str, str]:
    """Returns (previous_day_highlights, todays_outlook). Empty strings if the
    LLM is unavailable/fails or there's no index data to reason over."""
    if not report.indices:
        return "", ""
    try:
        import anthropic
    except ImportError:
        log.warning("anthropic SDK not installed; skipping market outlook")
        return "", ""

    payload = {
        "as_of": report.generated_at,
        "indices": [
            {
                "name": i.name,
                "prev_close": round(i.prev_close, 2),
                "prev_day_change_pct": round(i.prev_change_pct, 2),
                "today_open": round(i.today_open, 2) if i.today_open else None,
                "today_gap_pct": round(i.gap_pct, 2) if i.gap_pct is not None else None,
            }
            for i in report.indices
        ],
    }
    user_msg = (
        "Here is yesterday's close and today's open for the major Indian indices, as JSON. "
        "Write the two-part note.\n\n"
        f"```json\n{json.dumps(payload, default=str, indent=2)}\n```\n"
    )

    tools = []
    if use_web_search:
        tools = [{
            "type": "web_search_20260209",
            "name": "web_search",
            "max_uses": 5,
            "user_location": {"type": "approximate", "country": "IN"},
        }]

    client = anthropic.Anthropic()
    kwargs = dict(
        model=model, max_tokens=2000, thinking={"type": "adaptive"},
        system=_MARKET_SYSTEM, messages=[{"role": "user", "content": user_msg}],
    )
    if tools:
        kwargs["tools"] = tools
    try:
        resp = client.messages.create(**kwargs)
    except anthropic.APIStatusError as e:
        log.error("market outlook API error %s: %s", e.status_code, e.message)
        return "", ""
    except Exception as e:  # noqa: BLE001
        log.error("market outlook failed: %s", e)
        return "", ""

    if resp.stop_reason == "refusal":
        log.warning("market outlook refused: %s", getattr(resp, "stop_details", None))
        return "", ""

    text = "\n\n".join(b.text for b in resp.content if b.type == "text").strip()
    if "---" in text:
        highlights, _, outlook = text.partition("---")
        return highlights.strip(), outlook.strip()
    return text, ""


_GAP_SYSTEM = """You are a markets analyst. You are given a list of NSE F&O stocks that \
gapped up or down at today's open versus yesterday's close. For each symbol, give the single \
most likely driver in under 15 words (e.g. "Q2 results beat estimates", "block deal reported", \
"tracking weak IT sector", "no distinct news — broad market move"). Search the web for very \
recent (last 1-2 days) India stock news on the biggest movers if it helps; for smaller movers \
without distinct news, a brief general reason (sector/index-linked, broad market) is fine — \
do not invent specific news you're not reasonably confident about.

Respond with ONLY a JSON array, no prose, no markdown fences:
[{"symbol": "...", "reason": "..."}, ...]
One entry per symbol given, same order not required.
"""


def build_gap_reasons(
    movers: list[GapMover], model: str, use_web_search: bool,
) -> dict[str, str]:
    """One batched call covering all given movers -> {symbol: reason}."""
    if not movers:
        return {}
    try:
        import anthropic
    except ImportError:
        log.warning("anthropic SDK not installed; skipping gap reasons")
        return {}

    payload = [
        {"symbol": m.symbol, "gap_pct": round(m.gap_pct, 2),
         "prev_close": round(m.prev_close, 2), "open": round(m.open_price, 2)}
        for m in movers
    ]
    user_msg = f"```json\n{json.dumps(payload, indent=2)}\n```"

    tools = []
    if use_web_search:
        tools = [{
            "type": "web_search_20260209",
            "name": "web_search",
            "max_uses": 8,
            "user_location": {"type": "approximate", "country": "IN"},
        }]

    client = anthropic.Anthropic()
    kwargs = dict(
        model=model, max_tokens=3000, thinking={"type": "adaptive"},
        system=_GAP_SYSTEM, messages=[{"role": "user", "content": user_msg}],
    )
    if tools:
        kwargs["tools"] = tools
    try:
        resp = client.messages.create(**kwargs)
    except anthropic.APIStatusError as e:
        log.error("gap reasons API error %s: %s", e.status_code, e.message)
        return {}
    except Exception as e:  # noqa: BLE001
        log.error("gap reasons failed: %s", e)
        return {}

    if resp.stop_reason == "refusal":
        log.warning("gap reasons refused: %s", getattr(resp, "stop_details", None))
        return {}

    text = "\n\n".join(b.text for b in resp.content if b.type == "text").strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        items = json.loads(text)
        return {i["symbol"]: i["reason"] for i in items if i.get("symbol") and i.get("reason")}
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        log.warning("gap reasons: could not parse LLM response (%s)", e)
        return {}
