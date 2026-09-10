"""Render a Report to HTML + plain text for email."""

from __future__ import annotations

from jinja2 import Environment, select_autoescape

from .models import Action, Report

_ACTION_STYLE = {
    Action.STOPLOSS_HIT: ("#b00020", "STOP-LOSS"),
    Action.EXIT: ("#b00020", "EXIT"),
    Action.TRIM: ("#c77700", "TRIM"),
    Action.BUY_MORE: ("#1a7f37", "ADD"),
    Action.ACCUMULATE: ("#1a7f37", "START"),
    Action.WATCH_BUY: ("#0969da", "NEAR BUY"),
    Action.HOLD: ("#57606a", "HOLD"),
    Action.WATCH: ("#57606a", "WATCH"),
    Action.AVOID: ("#8250df", "AVOID"),
}

_ENV = Environment(autoescape=select_autoescape(["html"]))

_HTML = _ENV.from_string("""\
<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:720px;margin:auto;color:#1f2328">
  <h2 style="margin-bottom:2px">{{ title }}</h2>
  <div style="color:#57606a;font-size:13px">{{ r.generated_at }} · recommendations for <b>{{ r.horizon_label }}</b></div>

  <div style="background:#f6f8fa;border-radius:8px;padding:12px 14px;margin:14px 0;font-size:14px">
    <b>Portfolio</b><br>
    Invested ₹{{ "{:,.0f}".format(p.total_invested) }} ·
    Value ₹{{ "{:,.0f}".format(p.total_value) }} ·
    Unrealised
    <span style="color:{{ '#1a7f37' if p.unrealised_pnl >= 0 else '#b00020' }}">
      {{ "{:+,.0f}".format(p.unrealised_pnl) }} ({{ "%+.1f"|format(p.unrealised_pnl_pct) }}%)
    </span>
    {% if p.realised %}· Realised (all-time) ₹{{ "{:+,.0f}".format(p.realised_pnl) }}{% endif %}
    {% if p.errors %}<br><span style="color:#b00020">data warnings: {{ p.errors|join('; ') }}</span>{% endif %}
  </div>

  <h3 style="margin:18px 0 6px">Action list</h3>
  {% if r.actionable %}
  <table style="border-collapse:collapse;width:100%;font-size:13px">
    <tr style="text-align:left;border-bottom:1px solid #d0d7de">
      <th style="padding:6px 4px">Stock</th><th>Call</th><th>Last</th><th>Stop</th><th>Conf.</th><th>Why</th>
    </tr>
    {% for s in r.actionable %}
    {% set style = action_style(s.action) %}
    <tr style="border-bottom:1px solid #eaeef2;vertical-align:top">
      <td style="padding:6px 4px"><b>{{ s.symbol }}</b>{% if s.held %} <span style="color:#57606a">·held</span>{% endif %}</td>
      <td><span style="background:{{ style[0] }};color:#fff;border-radius:4px;padding:1px 6px;font-size:11px">{{ style[1] }}</span></td>
      <td>₹{{ "%.1f"|format(s.last_price) }}</td>
      <td>{{ ("₹%.1f"|format(s.stop_level)) if s.stop_level else "—" }}</td>
      <td>{{ "%.0f"|format(s.confidence * 100) }}%</td>
      <td style="color:#424a53">{{ s.reasons[:2]|join(' ') }}</td>
    </tr>
    {% endfor %}
  </table>
  {% else %}
  <p style="color:#57606a">No actionable signals this session — hold steady.</p>
  {% endif %}

  {% if r.commentary %}
  <h3 style="margin:20px 0 6px">Analyst note</h3>
  <div style="font-size:14px;line-height:1.55;white-space:pre-wrap">{{ r.commentary }}</div>
  {% endif %}

  <h3 style="margin:20px 0 6px">All holdings</h3>
  <table style="border-collapse:collapse;width:100%;font-size:13px">
    <tr style="text-align:left;border-bottom:1px solid #d0d7de">
      <th style="padding:6px 4px">Stock</th><th>Qty</th><th>Avg</th><th>Last</th><th>P&L%</th><th>Model</th>
    </tr>
    {% for h in p.holdings %}
    {% set s = sig_for(h.symbol) %}
    <tr style="border-bottom:1px solid #eaeef2">
      <td style="padding:6px 4px">{{ h.symbol }}</td>
      <td>{{ "%g"|format(h.quantity) }}</td>
      <td>₹{{ "%.1f"|format(h.avg_price) }}</td>
      <td>₹{{ "%.1f"|format(h.last_price) }}</td>
      <td style="color:{{ '#1a7f37' if h.pnl >= 0 else '#b00020' }}">{{ "%+.1f"|format(h.pnl_pct) }}%</td>
      <td>{{ (action_style(s.action)[1]) if s else "—" }}</td>
    </tr>
    {% endfor %}
  </table>

  <p style="color:#8c959f;font-size:12px;margin-top:22px;border-top:1px solid #d0d7de;padding-top:10px">
    {{ r.disclaimer }}
  </p>
</div>
""")


def render_html(r: Report) -> str:
    sig_map = {s.symbol: s for s in r.signals}
    title = ("Pre-open market brief" if r.session == "premarket"
             else "Post-close market brief")
    return _HTML.render(
        r=r, p=r.portfolio, title=title,
        action_style=lambda a: _ACTION_STYLE.get(a, ("#57606a", a.value)),
        sig_for=sig_map.get,
    )


def render_text(r: Report) -> str:
    lines = [
        f"{'PRE-OPEN' if r.session == 'premarket' else 'POST-CLOSE'} BRIEF — {r.generated_at}",
        f"Recommendations for: {r.horizon_label}",
        "",
        f"Portfolio: invested Rs{r.portfolio.total_invested:,.0f}  value Rs{r.portfolio.total_value:,.0f}  "
        f"unrealised {r.portfolio.unrealised_pnl_pct:+.1f}%",
        "",
        "ACTION LIST",
    ]
    if not r.actionable:
        lines.append("  (none — hold steady)")
    for s in r.actionable:
        tag = _ACTION_STYLE.get(s.action, ("", s.action.value))[1]
        stop = f"  stop Rs{s.stop_level:.1f}" if s.stop_level else ""
        lines.append(f"  [{tag}] {s.symbol}  last Rs{s.last_price:.1f}{stop}  ({s.confidence*100:.0f}%)")
        for reason in s.reasons[:3]:
            lines.append(f"        - {reason}")
    if r.commentary:
        lines += ["", "ANALYST NOTE", r.commentary]
    lines += ["", r.disclaimer]
    return "\n".join(lines)
