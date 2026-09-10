"""Aggregate holdings/positions/trades from all brokers into one view."""

from __future__ import annotations

import csv
import logging
from collections import defaultdict, deque
from datetime import date
from pathlib import Path

from .brokers.base import BrokerClient
from .models import Holding, Position, PortfolioSummary, RealisedLot, Trade

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]


def _merge_holdings(rows: list[Holding]) -> list[Holding]:
    """Same symbol held in two brokers -> one blended line."""
    by_sym: dict[str, list[Holding]] = defaultdict(list)
    for h in rows:
        by_sym[h.symbol].append(h)
    merged: list[Holding] = []
    for sym, group in by_sym.items():
        qty = sum(g.quantity for g in group)
        if qty <= 0:
            continue
        cost = sum(g.invested for g in group)
        last = next((g.last_price for g in group if g.last_price), group[0].avg_price)
        merged.append(
            Holding(
                symbol=sym,
                quantity=qty,
                avg_price=cost / qty,
                last_price=last,
                broker="+".join(sorted({g.broker for g in group})),
                isin=next((g.isin for g in group if g.isin), None),
            )
        )
    return sorted(merged, key=lambda h: h.current_value, reverse=True)


def load_csv_trades(path: Path | None = None) -> list[Trade]:
    """Optional history file. Columns: date,symbol,side,quantity,price,broker[,charges]
    date as YYYY-MM-DD, side BUY/SELL. Used for realised P&L the broker APIs
    don't return."""
    path = path or (ROOT / "data" / "trades.csv")
    if not path.exists():
        return []
    out: list[Trade] = []
    with path.open() as f:
        for row in csv.DictReader(f):
            try:
                out.append(
                    Trade(
                        symbol=row["symbol"].strip().upper(),
                        side=row["side"].strip().upper(),
                        quantity=float(row["quantity"]),
                        price=float(row["price"]),
                        trade_date=date.fromisoformat(row["date"].strip()),
                        broker=row.get("broker", "csv").strip() or "csv",
                        charges=float(row.get("charges", 0) or 0),
                    )
                )
            except (KeyError, ValueError) as e:
                log.warning("trades.csv: skipping bad row %s (%s)", row, e)
    return out


def fifo_realised(trades: list[Trade]) -> list[RealisedLot]:
    """FIFO-match buys against sells per symbol to produce closed round-trips."""
    lots: list[RealisedLot] = []
    books: dict[str, deque[list]] = defaultdict(deque)  # symbol -> deque of [qty, price, date, broker]
    for t in sorted(trades, key=lambda x: x.trade_date):
        book = books[t.symbol]
        if t.side == "BUY":
            book.append([t.quantity, t.price, t.trade_date, t.broker])
        elif t.side == "SELL":
            remaining = t.quantity
            while remaining > 1e-9 and book:
                lot = book[0]
                take = min(remaining, lot[0])
                lots.append(
                    RealisedLot(
                        symbol=t.symbol,
                        quantity=take,
                        buy_price=lot[1],
                        sell_price=t.price,
                        buy_date=lot[2],
                        sell_date=t.trade_date,
                        broker=t.broker,
                    )
                )
                lot[0] -= take
                remaining -= take
                if lot[0] <= 1e-9:
                    book.popleft()
    return lots


def build_portfolio(brokers: list[BrokerClient]) -> PortfolioSummary:
    all_holdings: list[Holding] = []
    all_positions: list[Position] = []
    all_trades: list[Trade] = []
    errors: list[str] = []

    for b in brokers:
        for label, fn in (("holdings", b.holdings), ("positions", b.positions), ("trades", b.todays_trades)):
            try:
                res = fn()
                if label == "holdings":
                    all_holdings += res
                elif label == "positions":
                    all_positions += res
                else:
                    all_trades += res
            except Exception as e:  # noqa: BLE001
                msg = f"{b.name}.{label}: {e}"
                errors.append(msg)
                log.error(msg)

    all_trades += load_csv_trades()
    realised = fifo_realised(all_trades)

    holdings = _merge_holdings(all_holdings)
    total_invested = sum(h.invested for h in holdings)
    total_value = sum(h.current_value for h in holdings)
    day_pnl = sum(h.pnl for h in holdings)  # replaced with true day P&L when prev close is known

    concentration = {
        h.symbol: (h.current_value / total_value * 100.0) if total_value else 0.0
        for h in holdings
    }

    return PortfolioSummary(
        total_invested=total_invested,
        total_value=total_value,
        day_pnl=day_pnl,
        holdings=holdings,
        positions=all_positions,
        realised=realised,
        concentration=concentration,
        errors=errors,
    )
