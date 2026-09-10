"""Angel One SmartAPI.

Fully automatable: the session is generated from the client id, MPIN and a
live TOTP derived from ANGEL_TOTP_SECRET, so no daily manual login is needed.
"""

from __future__ import annotations

from datetime import date

from ..models import Holding, Position, Trade
from .base import BrokerClient, BrokerError


class AngelOneClient(BrokerClient):
    name = "angelone"

    def __init__(self, api_key: str, client_id: str, mpin: str, totp_secret: str):
        self.api_key = api_key
        self.client_id = client_id
        self.mpin = mpin
        self.totp_secret = totp_secret
        self.smart = None

    def connect(self) -> None:
        if not (self.api_key and self.client_id and self.totp_secret):
            raise BrokerError("angelone: ANGEL_API_KEY / ANGEL_CLIENT_ID / ANGEL_TOTP_SECRET missing")
        try:
            import pyotp
            from SmartApi import SmartConnect
        except ImportError as e:  # pragma: no cover
            raise BrokerError(f"angelone: smartapi-python not installed ({e})")

        self.smart = SmartConnect(api_key=self.api_key)
        otp = pyotp.TOTP(self.totp_secret).now()
        try:
            resp = self.smart.generateSession(self.client_id, self.mpin, otp)
        except Exception as e:  # noqa: BLE001
            raise BrokerError(f"angelone: generateSession failed ({e})")
        if not resp or not resp.get("status"):
            raise BrokerError(f"angelone: login rejected — {resp}")

    def holdings(self) -> list[Holding]:
        resp = self.smart.holding()
        rows = (resp or {}).get("data") or []
        out: list[Holding] = []
        for h in rows:
            qty = float(h.get("quantity", 0))
            if qty <= 0:
                continue
            out.append(
                Holding(
                    symbol=self._clean_symbol(h.get("tradingsymbol", "")),
                    quantity=qty,
                    avg_price=float(h.get("averageprice", 0)),
                    last_price=float(h.get("ltp", 0) or h.get("averageprice", 0)),
                    broker=self.name,
                    isin=h.get("isin"),
                )
            )
        return out

    def positions(self) -> list[Position]:
        resp = self.smart.position()
        rows = (resp or {}).get("data") or []
        out: list[Position] = []
        for p in rows:
            qty = float(p.get("netqty", 0))
            if qty == 0:
                continue
            out.append(
                Position(
                    symbol=self._clean_symbol(p.get("tradingsymbol", "")),
                    quantity=qty,
                    avg_price=float(p.get("netprice", 0) or p.get("avgnetprice", 0)),
                    last_price=float(p.get("ltp", 0) or p.get("netprice", 0)),
                    broker=self.name,
                    product=p.get("producttype", "INTRADAY"),
                )
            )
        return out

    def todays_trades(self) -> list[Trade]:
        resp = self.smart.tradeBook()
        rows = (resp or {}).get("data") or []
        out: list[Trade] = []
        for t in rows:
            qty = float(t.get("fillsize", 0) or t.get("filledshares", 0))
            if qty <= 0:
                continue
            out.append(
                Trade(
                    symbol=self._clean_symbol(t.get("tradingsymbol", "")),
                    side=str(t.get("transactiontype", "")).upper(),
                    quantity=qty,
                    price=float(t.get("fillprice", 0) or t.get("tradevalue", 0)),
                    trade_date=date.today(),
                    broker=self.name,
                )
            )
        return out
