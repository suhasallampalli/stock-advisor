"""Claude-written daily commentary over the rule signals.

Uses the Messages API with the server-side web_search tool so the note can
reference recent headlines for names you hold or watch. Output is framed as
personal analysis, never as advice.
"""

from __future__ import annotations

import json
import logging

from .models import Action, Report, SymbolSignal

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
