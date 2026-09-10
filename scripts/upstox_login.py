#!/usr/bin/env python3
"""Refresh the daily Upstox access token via the OAuth2 auth-code flow.

Run once each morning (Upstox tokens expire ~03:30 IST). Requires the redirect
URI registered on your Upstox app to match UPSTOX_REDIRECT_URI.

Usage:
    python scripts/upstox_login.py
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import webbrowser
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from advisor.config import BrokerCreds  # noqa: E402

AUTH = "https://api.upstox.com/v2/login/authorization/dialog"
TOKEN = "https://api.upstox.com/v2/login/authorization/token"


def main() -> int:
    c = BrokerCreds.from_env().upstox
    if not c["api_key"] or not c["api_secret"]:
        print("Set UPSTOX_API_KEY and UPSTOX_API_SECRET in .env", file=sys.stderr)
        return 1

    q = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": c["api_key"],
        "redirect_uri": c["redirect_uri"],
    })
    print(f"Open and authorise:\n{AUTH}?{q}\n")
    try:
        webbrowser.open(f"{AUTH}?{q}")
    except Exception:
        pass

    code = input("Paste the `code` query param from the redirect URL: ").strip()
    resp = requests.post(TOKEN, headers={"accept": "application/json"}, data={
        "code": code,
        "client_id": c["api_key"],
        "client_secret": c["api_secret"],
        "redirect_uri": c["redirect_uri"],
        "grant_type": "authorization_code",
    }, timeout=30)
    resp.raise_for_status()
    body = resp.json()

    out = Path(c["token_file"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "access_token": body["access_token"],
        "date": date.today().isoformat(),
    }, indent=2))
    print(f"Saved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
