#!/usr/bin/env python3
"""Refresh the daily Zerodha Kite access token.

Kite has no unattended login — you must approve in the browser once per day.
Run this before the pre-open session (a cron at ~08:30 IST that pauses for
input won't work; instead run it manually, or use Kite's TOTP-based flow with
a tool like `kiteconnect`'s login URL + a headless approver you maintain).

Usage:
    python scripts/zerodha_login.py
    # opens/prints the login URL -> after redirect, paste the `request_token`
"""

from __future__ import annotations

import json
import sys
import webbrowser
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from advisor.config import BrokerCreds  # noqa: E402


def main() -> int:
    from kiteconnect import KiteConnect

    creds = BrokerCreds.from_env().zerodha
    if not creds["api_key"] or not creds["api_secret"]:
        print("Set KITE_API_KEY and KITE_API_SECRET in .env", file=sys.stderr)
        return 1

    kite = KiteConnect(api_key=creds["api_key"])
    url = kite.login_url()
    print("Open this URL, log in, and copy the request_token from the redirect:\n", url)
    try:
        webbrowser.open(url)
    except Exception:
        pass

    request_token = input("\nrequest_token: ").strip()
    data = kite.generate_session(request_token, api_secret=creds["api_secret"])

    out = Path(creds["token_file"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "access_token": data["access_token"],
        "public_token": data.get("public_token"),
        "user_id": data.get("user_id"),
        "date": date.today().isoformat(),
    }, indent=2))
    print(f"\nSaved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
