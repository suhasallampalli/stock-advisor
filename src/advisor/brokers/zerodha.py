"""Zerodha Kite Connect.

Kite access tokens expire daily (~06:00 IST reset). Run
``python scripts/zerodha_login.py`` once each morning (or wire it to a
cron before the premarket session) to refresh data/zerodha_token.json.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from ..models import Holding, Position, Trade
from .base import BrokerClient, BrokerError


class ZerodhaClient(BrokerClient):
    name = "zerodha"

    def __init__(self, api_key: str, api_secret: str = "", token_file: str | None = None,
                 access_token: str | None = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.token_file = Path(token_file) if token_file else None
        self.access_token = access_token  # set directly in multi-user (DB) mode
        self.kite = None

    def _resolve_token(self) -> str:
        if self.access_token:
            return self.access_token
        if self.token_file and self.token_file.exists():
            blob = json.loads(self.token_file.read_text())
            token_day = blob.get("date")
            if token_day and token_day != date.today().isoformat():
                raise BrokerError(
                    f"zerodha: access token is stale (dated {token_day}) — re-run "
                    "scripts/zerodha_login.py"
                )
            return blob["access_token"]
        raise BrokerError("zerodha: no access token — run scripts/zerodha_login.py or set one via the API")

    def connect(self) -> None:
        if not self.api_key:
            raise BrokerError("zerodha: api_key not set")
        try:
            from kiteconnect import KiteConnect
        except ImportError as e:  # pragma: no cover
            raise BrokerError(f"zerodha: kiteconnect not installed ({e})")

        self.kite = KiteConnect(api_key=self.api_key)
        self.kite.set_access_token(self._resolve_token())
        try:
            self.kite.profile()
        except Exception as e:  # noqa: BLE001
            raise BrokerError(f"zerodha: token rejected ({e})")

    def holdings(self) -> list[Holding]:
        out: list[Holding] = []
        for h in self.kite.holdings():
            qty = float(h.get("quantity", 0)) + float(h.get("t1_quantity", 0))
            if qty <= 0:
                continue
            out.append(
                Holding(
                    symbol=self._clean_symbol(h["tradingsymbol"]),
                    quantity=qty,
                    avg_price=float(h["average_price"]),
                    last_price=float(h.get("last_price") or h["average_price"]),
                    broker=self.name,
                    isin=h.get("isin"),
                )
            )
        return out

    def positions(self) -> list[Position]:
        out: list[Position] = []
        for p in self.kite.positions().get("net", []):
            if float(p.get("quantity", 0)) == 0:
                continue
            out.append(
                Position(
                    symbol=self._clean_symbol(p["tradingsymbol"]),
                    quantity=float(p["quantity"]),
                    avg_price=float(p["average_price"]),
                    last_price=float(p.get("last_price") or p["average_price"]),
                    broker=self.name,
                    product=p.get("product", "MIS"),
                )
            )
        return out

    def todays_trades(self) -> list[Trade]:
        out: list[Trade] = []
        for t in self.kite.trades():
            ts = t.get("fill_timestamp") or t.get("order_timestamp")
            d = ts.date() if isinstance(ts, datetime) else date.today()
            out.append(
                Trade(
                    symbol=self._clean_symbol(t["tradingsymbol"]),
                    side=t["transaction_type"].upper(),
                    quantity=float(t["quantity"]),
                    price=float(t["average_price"]),
                    trade_date=d,
                    broker=self.name,
                )
            )
        return out
