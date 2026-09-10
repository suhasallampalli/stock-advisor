"""Glue between API users and the advisor pipeline."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import load_config
from ..portfolio import build_portfolio
from ..brokers import build_brokers
from ..run import build_report, deliver, is_trading_day
from .crypto import decrypt_json
from .models_db import BrokerCredential, User

log = logging.getLogger("advisor.api")


def user_creds(db: Session, user: User) -> dict[str, dict]:
    """Decrypt the user's stored broker credentials into build_brokers() form."""
    rows = db.scalars(
        select(BrokerCredential).where(BrokerCredential.user_id == user.id)
    ).all()
    return {r.broker: decrypt_json(r.enc_payload) for r in rows}


def portfolio_for(db: Session, user: User):
    cfg = load_config()
    creds = user_creds(db, user)
    if not creds:
        raise RuntimeError("no broker credentials configured")
    brokers = build_brokers(cfg, creds_override=creds)
    if not brokers:
        raise RuntimeError("could not connect to any configured broker")
    return build_portfolio(brokers)


def brief_for(db: Session, user: User, session: str, *, dry_run: bool = True):
    cfg = load_config()
    creds = user_creds(db, user)
    report = build_report(session, cfg, creds_override=creds or None)
    emailed = deliver(report, cfg, recipients=[user.email], dry_run=dry_run)
    return report, emailed


def run_all_users(session: str, *, force: bool = False) -> int:
    """Cron entrypoint for multi-user mode: email every active user their brief."""
    from .db import SessionLocal, init_db

    init_db()
    cfg = load_config()
    if not force and not is_trading_day(cfg):
        log.info("not an NSE trading day — skipping")
        return 0

    sent = 0
    with SessionLocal() as db:
        users = db.scalars(select(User).where(User.is_active.is_(True))).all()
        for user in users:
            try:
                _, emailed = brief_for(db, user, session, dry_run=False)
                sent += int(emailed)
            except Exception as e:  # noqa: BLE001
                log.error("brief failed for %s: %s", user.email, e)
    log.info("%s: sent %d/%d briefs", session, sent, len(users))
    return 0
