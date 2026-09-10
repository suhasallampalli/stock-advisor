"""Configuration loading: config.yaml (tunables) + environment (secrets)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _env(name: str, default: str | None = None, required: bool = False) -> str | None:
    val = os.getenv(name, default)
    if required and not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


@dataclass
class SMTPConfig:
    host: str
    port: int
    user: str
    app_password: str
    email_from: str
    email_to: list[str]

    @classmethod
    def from_env(cls) -> "SMTPConfig":
        to = _env("EMAIL_TO", "") or ""
        return cls(
            host=_env("SMTP_HOST", "smtp.gmail.com"),
            port=int(_env("SMTP_PORT", "587")),
            user=_env("SMTP_USER", ""),
            app_password=_env("SMTP_APP_PASSWORD", ""),
            email_from=_env("EMAIL_FROM") or _env("SMTP_USER", ""),
            email_to=[a.strip() for a in to.split(",") if a.strip()],
        )


@dataclass
class BrokerCreds:
    zerodha: dict = field(default_factory=dict)
    upstox: dict = field(default_factory=dict)
    angelone: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "BrokerCreds":
        return cls(
            zerodha={
                "api_key": _env("KITE_API_KEY"),
                "api_secret": _env("KITE_API_SECRET"),
                "token_file": str(ROOT / "data" / "zerodha_token.json"),
            },
            upstox={
                "api_key": _env("UPSTOX_API_KEY"),
                "api_secret": _env("UPSTOX_API_SECRET"),
                "redirect_uri": _env("UPSTOX_REDIRECT_URI", "http://127.0.0.1:8550/callback"),
                "token_file": str(ROOT / "data" / "upstox_token.json"),
            },
            angelone={
                "api_key": _env("ANGEL_API_KEY"),
                "client_id": _env("ANGEL_CLIENT_ID"),
                "mpin": _env("ANGEL_MPIN"),
                "totp_secret": _env("ANGEL_TOTP_SECRET"),
            },
        )


@dataclass
class Config:
    raw: dict
    brokers: list[str]
    smtp: SMTPConfig
    creds: BrokerCreds
    llm_model: str

    # convenience accessors -------------------------------------------------
    @property
    def llm_enabled(self) -> bool:
        return bool(self.raw.get("llm", {}).get("enabled", True))

    @property
    def llm_web_search(self) -> bool:
        return bool(self.raw.get("llm", {}).get("use_web_search", True))

    @property
    def exchange_suffix(self) -> str:
        return self.raw.get("market", {}).get("exchange_suffix", ".NS")

    @property
    def lookback_days(self) -> int:
        return int(self.raw.get("market", {}).get("lookback_days", 400))

    @property
    def holidays(self) -> set[date]:
        out: set[date] = set()
        for item in self.raw.get("market", {}).get("holidays", []) or []:
            out.add(item if isinstance(item, date) else date.fromisoformat(str(item)))
        return out

    @property
    def indicators(self) -> dict:
        return self.raw.get("indicators", {})

    @property
    def signal_params(self) -> dict:
        return self.raw.get("signals", {})

    @property
    def watchlist(self) -> list[str]:
        rel = self.raw.get("watchlist_file", "data/watchlist.txt")
        path = ROOT / rel
        if not path.exists():
            return []
        syms = []
        for line in path.read_text().splitlines():
            line = line.split("#", 1)[0].strip().upper()
            if line:
                syms.append(line)
        return syms

    @property
    def max_rows(self) -> int:
        return int(self.raw.get("report", {}).get("max_rows", 40))


def load_config(path: str | Path | None = None) -> Config:
    cfg_path = Path(path) if path else (ROOT / "config.yaml")
    if not cfg_path.exists():
        cfg_path = ROOT / "config.example.yaml"
    raw = yaml.safe_load(cfg_path.read_text()) or {}

    brokers_env = _env("ADVISOR_BROKERS", "zerodha,upstox,angelone")
    brokers = [b.strip().lower() for b in brokers_env.split(",") if b.strip()]

    return Config(
        raw=raw,
        brokers=brokers,
        smtp=SMTPConfig.from_env(),
        creds=BrokerCreds.from_env(),
        llm_model=_env("ADVISOR_LLM_MODEL", "claude-opus-5"),
    )
