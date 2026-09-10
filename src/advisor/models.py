"""Plain data structures shared across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


@dataclass
class Holding:
    """A settled equity position (delivery) in one broker account."""

    symbol: str                 # NSE trading symbol, e.g. "TATAMOTORS"
    quantity: float
    avg_price: float            # average buy price
    last_price: float
    broker: str
    isin: str | None = None

    @property
    def invested(self) -> float:
        return self.quantity * self.avg_price

    @property
    def current_value(self) -> float:
        return self.quantity * self.last_price

    @property
    def pnl(self) -> float:
        return self.current_value - self.invested

    @property
    def pnl_pct(self) -> float:
        return (self.pnl / self.invested * 100.0) if self.invested else 0.0


@dataclass
class Position:
    """An intraday / F&O / not-yet-settled position."""

    symbol: str
    quantity: float             # net; negative = short
    avg_price: float
    last_price: float
    broker: str
    product: str = "MIS"        # MIS / CNC / NRML


@dataclass
class Trade:
    """A single executed buy or sell. Sourced from broker tradebook (today)
    or from data/trades.csv (history you import from broker statements)."""

    symbol: str
    side: str                   # "BUY" or "SELL"
    quantity: float
    price: float
    trade_date: date
    broker: str
    charges: float = 0.0

    @property
    def value(self) -> float:
        return self.quantity * self.price


@dataclass
class RealisedLot:
    """A closed round-trip produced by FIFO matching of Trades."""

    symbol: str
    quantity: float
    buy_price: float
    sell_price: float
    buy_date: date
    sell_date: date
    broker: str

    @property
    def pnl(self) -> float:
        return (self.sell_price - self.buy_price) * self.quantity

    @property
    def pnl_pct(self) -> float:
        cost = self.buy_price * self.quantity
        return (self.pnl / cost * 100.0) if cost else 0.0

    @property
    def holding_days(self) -> int:
        return (self.sell_date - self.buy_date).days


class Action(str, Enum):
    BUY_MORE = "BUY_MORE"          # held, add on strength/dip within uptrend
    ACCUMULATE = "ACCUMULATE"      # watchlist, conditions favourable to start
    HOLD = "HOLD"
    TRIM = "TRIM"                  # reduce size (concentration or partial profit)
    EXIT = "EXIT"                  # trend broken, close the position
    STOPLOSS_HIT = "STOPLOSS_HIT"  # price breached your stop -> act now
    WATCH_BUY = "WATCH_BUY"        # watchlist, close to a buy trigger
    WATCH = "WATCH"                # watchlist, nothing actionable
    AVOID = "AVOID"               # watchlist, technically weak


@dataclass
class SymbolSignal:
    symbol: str
    action: Action
    confidence: float             # 0..1, blended rule score
    reasons: list[str] = field(default_factory=list)
    held: bool = False
    last_price: float = 0.0
    prev_close: float = 0.0
    stop_level: float | None = None
    target_hint: float | None = None
    indicators: dict = field(default_factory=dict)

    @property
    def gap_pct(self) -> float:
        return ((self.last_price - self.prev_close) / self.prev_close * 100.0) if self.prev_close else 0.0


@dataclass
class PortfolioSummary:
    total_invested: float
    total_value: float
    day_pnl: float
    holdings: list[Holding]
    positions: list[Position]
    realised: list[RealisedLot]
    concentration: dict[str, float]   # symbol -> % of book
    errors: list[str] = field(default_factory=list)

    @property
    def unrealised_pnl(self) -> float:
        return self.total_value - self.total_invested

    @property
    def unrealised_pnl_pct(self) -> float:
        return (self.unrealised_pnl / self.total_invested * 100.0) if self.total_invested else 0.0

    @property
    def realised_pnl(self) -> float:
        return sum(l.pnl for l in self.realised)


@dataclass
class Report:
    session: str                  # "premarket" | "postmarket"
    generated_at: str
    horizon_label: str            # "today" | "tomorrow"
    portfolio: PortfolioSummary
    signals: list[SymbolSignal]
    actionable: list[SymbolSignal]
    commentary: str = ""
    disclaimer: str = (
        "Automated rule-based output plus AI commentary for your personal review. "
        "This is NOT investment advice or a recommendation to transact. Markets are "
        "risky; verify everything and consult a SEBI-registered adviser before acting."
    )
