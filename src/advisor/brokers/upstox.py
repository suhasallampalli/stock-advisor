"""Upstox API v2.

Access tokens expire daily (~03:30 IST). Run
``python scripts/upstox_login.py`` each morning to refresh
data/upstox_token.json.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from ..models import Holding, Position, Trade
from .base import BrokerClient, BrokerError


class UpstoxClient(BrokerClient):
    name = "upstox"

    def __init__(self, api_key: str, api_secret: str = "", redirect_uri: str = "",
                 token_file: str | None = None, access_token: str | None = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.redirect_uri = redirect_uri
        self.token_file = Path(token_file) if token_file else None
        self.access_token = access_token

    def _resolve_token(self) -> str:
        if self.access_token:
            return self.access_token
        if self.token_file and self.token_file.exists():
            blob = json.loads(self.token_file.read_text())
            if blob.get("date") and blob["date"] != date.today().isoformat():
                raise BrokerError(
                    f"upstox: token stale (dated {blob['date']}) — re-run scripts/upstox_login.py"
                )
            return blob["access_token"]
        raise BrokerError("upstox: no access token — run scripts/upstox_login.py or set one via the API")

    def connect(self) -> None:
        if not self.api_key:
            raise BrokerError("upstox: api_key not set")
        try:
            import upstox_client
        except ImportError as e:  # pragma: no cover
            raise BrokerError(f"upstox: upstox-python-sdk not installed ({e})")

        cfg = upstox_client.Configuration()
        cfg.access_token = self._resolve_token()
        self._client = upstox_client.ApiClient(cfg)
        self._portfolio = upstox_client.PortfolioApi(self._client)
        self._order = upstox_client.OrderApi(self._client)
        self._version = "2.0"
        try:
            upstox_client.UserApi(self._client).get_profile(self._version)
        except Exception as e:  # noqa: BLE001
            raise BrokerError(f"upstox: token rejected ({e})")

    def holdings(self) -> list[Holding]:
        out: list[Holding] = []
        data = self._portfolio.get_holdings(self._version).data or []
        for h in data:
            qty = float(getattr(h, "quantity", 0))
            if qty <= 0:
                continue
            out.append(
                Holding(
                    symbol=self._clean_symbol(getattr(h, "trading_symbol", "") or getattr(h, "tradingsymbol", "")),
                    quantity=qty,
                    avg_price=float(getattr(h, "average_price", 0)),
                    last_price=float(getattr(h, "last_price", 0) or getattr(h, "average_price", 0)),
                    broker=self.name,
                    isin=getattr(h, "isin", None),
                )
            )
        return out

    def positions(self) -> list[Position]:
        out: list[Position] = []
        data = self._portfolio.get_positions(self._version).data or []
        for p in data:
            qty = float(getattr(p, "quantity", 0))
            if qty == 0:
                continue
            out.append(
                Position(
                    symbol=self._clean_symbol(getattr(p, "trading_symbol", "") or getattr(p, "tradingsymbol", "")),
                    quantity=qty,
                    avg_price=float(getattr(p, "average_price", 0)),
                    last_price=float(getattr(p, "last_price", 0) or getattr(p, "average_price", 0)),
                    broker=self.name,
                    product=getattr(p, "product", "I"),
                )
            )
        return out

    def todays_trades(self) -> list[Trade]:
        out: list[Trade] = []
        try:
            data = self._order.get_trade_history(self._version).data or []
        except Exception:  # noqa: BLE001
            data = self._order.get_order_book(self._version).data or []
        for t in data:
            status = str(getattr(t, "status", "")).lower()
            if status and status != "complete":
                continue
            qty = float(getattr(t, "filled_quantity", 0) or getattr(t, "quantity", 0))
            if qty <= 0:
                continue
            out.append(
                Trade(
                    symbol=self._clean_symbol(getattr(t, "trading_symbol", "") or getattr(t, "tradingsymbol", "")),
                    side=str(getattr(t, "transaction_type", "")).upper(),
                    quantity=qty,
                    price=float(getattr(t, "average_price", 0) or getattr(t, "price", 0)),
                    trade_date=date.today(),
                    broker=self.name,
                )
            )
        return out
