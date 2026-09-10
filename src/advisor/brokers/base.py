"""Common broker interface. Each concrete client returns normalised models."""

from __future__ import annotations

import abc

from ..models import Holding, Position, Trade


class BrokerError(RuntimeError):
    """Raised for auth or API failures; callers degrade gracefully."""


class BrokerClient(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def connect(self) -> None:
        """Authenticate. Raise BrokerError on failure."""

    @abc.abstractmethod
    def holdings(self) -> list[Holding]:
        ...

    @abc.abstractmethod
    def positions(self) -> list[Position]:
        ...

    @abc.abstractmethod
    def todays_trades(self) -> list[Trade]:
        """Executed trades for the current session. Broker APIs generally do
        not expose older history — import that via data/trades.csv instead."""

    # ---- helpers -------------------------------------------------------
    @staticmethod
    def _clean_symbol(sym: str) -> str:
        return sym.replace("-EQ", "").replace(".NS", "").replace(".BO", "").strip().upper()
