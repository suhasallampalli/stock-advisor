"""Orchestration for one session (premarket or postmarket)."""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from .brokers import build_brokers
from .config import Config, load_config
from .llm import build_commentary, build_gap_reasons, build_market_outlook
from .marketdata import fetch_history
from .marketmovers import fetch_fno_gaps, fetch_index_moves
from .models import Report
from .notifier import send_email
from .portfolio import build_portfolio
from .report import render_html, render_text
from .signals import generate_signals

IST = ZoneInfo("Asia/Kolkata")
log = logging.getLogger("advisor")


def is_trading_day(cfg: Config, now: datetime | None = None) -> bool:
    now = now or datetime.now(IST)
    if now.weekday() >= 5:
        return False
    return now.date() not in cfg.holidays


def build_report(
    session: str,
    cfg: Config,
    *,
    creds_override: dict[str, dict] | None = None,
    extra_watchlist: list[str] | None = None,
) -> Report:
    """Run the full pipeline and return a Report (no delivery)."""
    now = datetime.now(IST)
    horizon = "today" if session in ("premarket", "market_open") else "tomorrow"

    brokers = build_brokers(cfg, creds_override=creds_override)
    if not brokers:
        log.warning("no brokers connected — holdings will be empty")
    portfolio = build_portfolio(brokers)

    universe = sorted(
        {h.symbol for h in portfolio.holdings}
        | set(cfg.watchlist)
        | set(extra_watchlist or [])
    )
    if not universe:
        raise RuntimeError("empty universe (no holdings, no watchlist)")

    history = fetch_history(universe, cfg.exchange_suffix, cfg.lookback_days)
    signals, actionable = generate_signals(
        history, portfolio.holdings, cfg.indicators, cfg.signal_params
    )

    report = Report(
        session=session,
        generated_at=now.strftime("%a %d %b %Y, %H:%M IST"),
        horizon_label=horizon,
        portfolio=portfolio,
        signals=signals[: cfg.max_rows],
        actionable=actionable[: cfg.max_rows],
    )
    if cfg.llm_enabled:
        report.commentary = build_commentary(report, cfg.llm_model, cfg.llm_web_search)

    if session == "market_open":
        _add_market_open_sections(report, cfg)
    return report


def _add_market_open_sections(report: Report, cfg: Config) -> None:
    """Previous-day index recap + today's F&O gap-up/gap-down scan."""
    report.indices = fetch_index_moves(cfg.indices)

    gainers, losers = fetch_fno_gaps(cfg.fno_symbols, cfg.exchange_suffix, cfg.min_gap_pct)
    report.gainers = gainers[: cfg.max_rows]
    report.losers = losers[: cfg.max_rows]

    if cfg.llm_enabled:
        report.market_highlights, report.index_outlook = build_market_outlook(
            report, cfg.llm_model, cfg.llm_web_search
        )
        reasoned = report.gainers[: cfg.max_gap_reason_rows] + report.losers[: cfg.max_gap_reason_rows]
        reasons = build_gap_reasons(reasoned, cfg.llm_model, cfg.llm_web_search)
        for mover in report.gainers + report.losers:
            mover.reason = reasons.get(mover.symbol, "")


def deliver(report: Report, cfg: Config, *, recipients: list[str] | None = None,
            dry_run: bool = False) -> bool:
    """Render + email a report. Returns True if an email was sent."""
    now = datetime.now(IST)
    session_label = {
        "premarket": "Pre-open", "market_open": "Market-open", "postmarket": "Post-close",
    }.get(report.session, report.session)
    subject = (
        f"[{session_label}] "
        f"{len(report.actionable)} calls · portfolio "
        f"{report.portfolio.unrealised_pnl_pct:+.1f}% · {now.strftime('%d %b')}"
    )
    html, text = render_html(report), render_text(report)
    if dry_run:
        print(text)
        with open("/tmp/advisor_preview.html", "w") as f:
            f.write(html)
        print("\n--- HTML written to /tmp/advisor_preview.html ---")
        return False

    smtp = cfg.smtp
    if recipients:
        smtp = dataclasses.replace(smtp, email_to=recipients)
    send_email(smtp, subject, html, text)
    return True


def run_session(session: str, *, force: bool = False, dry_run: bool = False,
                config_path: str | None = None) -> int:
    cfg = load_config(config_path)
    if not force and not is_trading_day(cfg):
        log.info("%s: not an NSE trading day — skipping", datetime.now(IST).date())
        return 0
    try:
        report = build_report(session, cfg)
    except RuntimeError as e:
        log.error("%s", e)
        return 1
    deliver(report, cfg, dry_run=dry_run)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="advisor")
    ap.add_argument("--session", choices=["premarket", "market_open", "postmarket"], required=True)
    ap.add_argument("--force", action="store_true", help="run even on a holiday/weekend")
    ap.add_argument("--dry-run", action="store_true", help="print instead of emailing")
    ap.add_argument("--all-users", action="store_true",
                    help="multi-user mode: email every active API user their own brief")
    ap.add_argument("--config", default=None)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    for noisy in ("yfinance", "peewee", "urllib3", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    try:
        if args.all_users:
            from .api.service import run_all_users
            return run_all_users(args.session, force=args.force)
        return run_session(args.session, force=args.force, dry_run=args.dry_run,
                           config_path=args.config)
    except Exception:  # noqa: BLE001
        log.exception("session failed")
        return 2


if __name__ == "__main__":
    sys.exit(main())
