"""Pydantic request/response models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    full_name: str | None = Field(default=None, max_length=200)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # access token lifetime, seconds


class RefreshIn(BaseModel):
    refresh_token: str


class LogoutIn(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str | None
    auth_provider: str
    is_active: bool
    is_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class GoogleAuthURL(BaseModel):
    authorization_url: str


# --- brokers ---------------------------------------------------------
class BrokerCredIn(BaseModel):
    """Free-form per-broker fields; validated against BROKER_FIELDS in the router."""

    fields: dict[str, str]


class BrokerCredOut(BaseModel):
    broker: str
    fields_set: list[str]
    masked: dict[str, str]
    updated_at: datetime


# --- portfolio / brief ---------------------------------------------
class HoldingOut(BaseModel):
    symbol: str
    quantity: float
    avg_price: float
    last_price: float
    pnl: float
    pnl_pct: float
    broker: str


class PortfolioOut(BaseModel):
    total_invested: float
    total_value: float
    unrealised_pnl: float
    unrealised_pnl_pct: float
    realised_pnl: float
    holdings: list[HoldingOut]
    errors: list[str]


class BriefOut(BaseModel):
    session: str
    horizon: str
    emailed: bool
    text: str
