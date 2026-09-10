"""Fernet-based encryption for broker credentials at rest."""

from __future__ import annotations

import json

from cryptography.fernet import Fernet, InvalidToken

from .settings import get_settings


def _fernet() -> Fernet:
    key = get_settings().secrets_enc_key
    if not key:
        raise RuntimeError(
            "SECRETS_ENC_KEY is not set — cannot store broker credentials. "
            "Generate one: python -c \"from cryptography.fernet import Fernet;"
            "print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode())


def encrypt_json(data: dict) -> str:
    return _fernet().encrypt(json.dumps(data, separators=(",", ":")).encode()).decode()


def decrypt_json(token: str) -> dict:
    try:
        return json.loads(_fernet().decrypt(token.encode()))
    except (InvalidToken, ValueError) as e:  # noqa: BLE001
        raise RuntimeError("failed to decrypt broker credentials (wrong SECRETS_ENC_KEY?)") from e
