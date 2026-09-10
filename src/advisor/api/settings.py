"""API configuration, read from the environment (.env)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env")


class Settings:
    def __init__(self) -> None:
        self.secret_key: str = os.getenv("API_SECRET_KEY", "")
        self.algorithm = "HS256"
        self.access_ttl_min = int(os.getenv("ACCESS_TOKEN_TTL_MIN", "15"))
        self.refresh_ttl_days = int(os.getenv("REFRESH_TOKEN_TTL_DAYS", "30"))

        default_db = f"sqlite:///{ROOT / 'data' / 'advisor.db'}"
        self.database_url: str = os.getenv("DATABASE_URL", default_db)
        self.secrets_enc_key: str = os.getenv("SECRETS_ENC_KEY", "")

        self.allow_registration = os.getenv("ALLOW_REGISTRATION", "true").lower() == "true"
        self.cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
        self.frontend_url = os.getenv("FRONTEND_URL", "").rstrip("/")

        self.google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        self.google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
        self.google_redirect_uri = os.getenv(
            "GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback"
        )

    @property
    def google_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    def validate(self) -> None:
        if not self.secret_key:
            raise RuntimeError("API_SECRET_KEY is not set")
        if len(self.secret_key) < 32:
            raise RuntimeError("API_SECRET_KEY should be at least 32 chars")


@lru_cache
def get_settings() -> Settings:
    return Settings()
