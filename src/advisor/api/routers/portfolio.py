"""Read the current user's portfolio and trigger an on-demand brief."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ...report import render_text
from ..db import get_db
from ..deps import get_current_user
from ..models_db import User
from ..schemas import BriefOut, HoldingOut, PortfolioOut
from ..service import brief_for, portfolio_for

router = APIRouter(prefix="/me", tags=["portfolio"])


@router.get("/portfolio", response_model=PortfolioOut)
def my_portfolio(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PortfolioOut:
    try:
        p = portfolio_for(db, user)
    except RuntimeError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    return PortfolioOut(
        total_invested=round(p.total_invested, 2),
        total_value=round(p.total_value, 2),
        unrealised_pnl=round(p.unrealised_pnl, 2),
        unrealised_pnl_pct=round(p.unrealised_pnl_pct, 2),
        realised_pnl=round(p.realised_pnl, 2),
        holdings=[
            HoldingOut(
                symbol=h.symbol, quantity=h.quantity, avg_price=round(h.avg_price, 2),
                last_price=round(h.last_price, 2), pnl=round(h.pnl, 2),
                pnl_pct=round(h.pnl_pct, 2), broker=h.broker,
            )
            for h in p.holdings
        ],
        errors=p.errors,
    )


@router.post("/brief", response_model=BriefOut)
def my_brief(
    session: str = Query(pattern="^(premarket|market_open|postmarket)$"),
    send_email: bool = Query(default=False, description="also email it (default: preview only)"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BriefOut:
    try:
        report, emailed = brief_for(db, user, session, dry_run=not send_email)
    except RuntimeError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    return BriefOut(
        session=report.session,
        horizon=report.horizon_label,
        emailed=emailed,
        text=render_text(report),
    )
