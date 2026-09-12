# stock-advisor

A personal, self-hosted daily briefing for the Indian equity market. It:

1. Pulls your **holdings, open positions and today's trades** from **Zerodha (Kite
   Connect)**, **Upstox** and **Angel One (SmartAPI)** — whichever you enable.
2. Reconstructs **realised P&L** from a `data/trades.csv` you import from broker
   statements (the broker APIs only expose the current day's tradebook).
3. Computes technical indicators (SMA/EMA, RSI, MACD, ATR, 20-day support &
   resistance) on daily candles for every held name **and** your watchlist.
4. Runs a **transparent rule engine** → per-stock call: `BUY_MORE`, `HOLD`,
   `TRIM`, `EXIT`, `STOPLOSS_HIT`, `ACCUMULATE`, `WATCH_BUY`, `AVOID` — each with
   its reasons.
5. Asks **Claude** (`claude-opus-5`) to write a short analyst note over those
   signals, using web search for recent India-market news.
6. **Emails** each user an HTML brief **three** times per trading day via Gmail SMTP:
   - **~08:45 IST** (pre-open) → calls for **today**
   - **~09:25 IST** (market-open) → previous day's highlights, index moves +
     today's trend read, and an F&O gap-up/gap-down scan (see below)
   - **~15:45 IST** (post-close) → calls for **tomorrow**

### The market-open brief

Runs ~10 minutes after NSE opens (09:15 IST), once opening prints exist. It adds:

- **Previous day highlights** — a short Claude-written recap of how the last
  session went and why (index moves, sectors, news), with web search.
- **Indices** — previous day's close/% change for the benchmarks in
  `market.indices` (config.yaml), plus today's open and gap, with a one-paragraph
  Claude "today's trend read" over that data.
- **F&O gap scan** — every symbol in `data/fno_stocks.txt` whose today's open
  differs from yesterday's close by at least `report.min_gap_pct`, split into
  gainers (opened higher) and losers (opened lower), each **sorted by
  descending price differential**. The top `report.max_gap_reason_rows` per
  side get an LLM-written probable reason (one batched call, not one per stock).

It's **multi-user**: a FastAPI JSON API handles sign-up / login (password **and**
Google), and each user stores their own broker keys (encrypted at rest). The
scheduler then runs the pipeline once per active user.

> ⚠️ **This is not investment advice.** It is a decision-support tool for your own
> review. Every email says so. Verify everything; consult a SEBI-registered
> adviser before you transact.

---

## Quick start

```bash
git clone <this repo> && cd stock-advisor
cp .env.example .env                # fill in secrets (see below)
cp config.example.yaml config.yaml  # tune thresholds + NSE holidays

# generate the two keys the API needs
python -c "import secrets;print('API_SECRET_KEY='+secrets.token_urlsafe(64))"
python -c "from cryptography.fernet import Fernet;print('SECRETS_ENC_KEY='+Fernet.generate_key().decode())"
# paste both into .env

docker compose build
docker compose up -d          # starts `api` (:8000) and `scheduler` (cron)
open http://localhost:8000/docs
```

### First run through the API

```bash
# 1. register
curl -sX POST localhost:8000/auth/register \
  -H 'content-type: application/json' \
  -d '{"email":"you@example.com","password":"a-good-password"}'
#   -> {"access_token":"...","refresh_token":"...", ...}

TOKEN=<access_token>

# 2. add a broker (Angel One runs unattended; Zerodha/Upstox also take access_token)
curl -sX PUT localhost:8000/brokers/angelone -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"fields":{"api_key":"...","client_id":"...","mpin":"...","totp_secret":"..."}}'

# 3. preview a brief (no email), or POST /me/brief?send_email=true to receive it
curl -sX POST "localhost:8000/me/brief?session=postmarket" -H "authorization: Bearer $TOKEN"
# session is one of: premarket | market_open | postmarket
```

Once a user has brokers configured, the **scheduler** container emails them
automatically at 08:45 / 15:45 IST on trading days.

### Run the API locally without Docker

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src uvicorn advisor.api.main:app --reload
```

### Run the pipeline once without Docker

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src python -m advisor --session premarket --dry-run              # shared-config mode
PYTHONPATH=src python -m advisor --session market_open --dry-run            # indices + F&O gap scan
PYTHONPATH=src python -m advisor --session premarket --all-users --force    # every API user
```

---

## Authentication (the API)

`advisor.api.main:app` is a FastAPI app. Interactive docs at `/docs`.

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/auth/register` | email + password → token pair |
| `POST` | `/auth/login` | OAuth2 password form (`username`=email) → token pair |
| `POST` | `/auth/refresh` | rotate refresh token → new pair (reuse of a spent token revokes the whole family) |
| `POST` | `/auth/logout` / `/auth/logout-all` | revoke one / all refresh tokens |
| `GET` | `/auth/me` | current user |
| `GET` | `/auth/google/authorize` | → `{authorization_url}` to send the browser to Google |
| `GET` | `/auth/google/callback` | Google redirects here; verifies the OIDC ID token, links/creates the user, issues our tokens (302 to `FRONTEND_URL#access_token=…` if set, else JSON) |
| `GET/PUT/DELETE` | `/brokers[/{broker}]` | manage the caller's encrypted broker credentials |
| `GET` | `/me/portfolio` | live holdings + P&L across the caller's brokers |
| `POST` | `/me/brief?session=…&send_email=…` | run the pipeline for the caller now (`session`: `premarket` \| `market_open` \| `postmarket`) |

### Token model

- **Access token** — JWT (HS256, `API_SECRET_KEY`), `type:"access"`, 15 min default
  (`ACCESS_TOKEN_TTL_MIN`). Sent as `Authorization: Bearer …`.
- **Refresh token** — opaque random string, stored only as a SHA-256 hash,
  30-day default (`REFRESH_TOKEN_TTL_DAYS`). **Rotated on every use**; a replayed
  old token is treated as compromise and revokes every active session for that user.
- **Passwords** — bcrypt, pre-hashed with SHA-256 so the 72-byte bcrypt limit
  doesn't silently cap entropy. Google-only accounts have no password.

### Google Sign-In setup

1. Google Cloud Console → *APIs & Services → Credentials → Create OAuth client ID
   → Web application*.
2. Authorized redirect URI = your `GOOGLE_REDIRECT_URI`
   (e.g. `https://api.example.com/auth/google/callback`).
3. Put the client ID/secret in `.env`. The flow uses **authorization code + PKCE**
   and verifies the ID token against Google's JWKS (`aud`, `iss`, `exp`) — no
   Gmail scopes are requested, only `openid email profile`.

### Broker credentials at rest

Each `PUT /brokers/{broker}` body is JSON-encoded and **Fernet-encrypted** with
`SECRETS_ENC_KEY` before it touches the DB. `GET /brokers` only ever returns
masked values. Rotating `SECRETS_ENC_KEY` invalidates all stored credentials.

---

## Configuration

### `.env` (secrets — never commit)

| Var | Notes |
|---|---|
| `API_SECRET_KEY` | JWT signing key (≥32 chars) — **required** |
| `SECRETS_ENC_KEY` | Fernet key for broker creds at rest — **required** to use brokers |
| `DATABASE_URL` | `sqlite:///./data/advisor.db` by default; use Postgres for real multi-user |
| `ACCESS_TOKEN_TTL_MIN` / `REFRESH_TOKEN_TTL_DAYS` | token lifetimes (15 / 30) |
| `ALLOW_REGISTRATION` | set `false` to lock signups |
| `CORS_ORIGINS` / `FRONTEND_URL` | browser origins; post-Google-login redirect target |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` | Sign in with Google |
| `ANTHROPIC_API_KEY` | for the daily commentary |
| `SMTP_USER` / `SMTP_APP_PASSWORD` | Gmail address + [App Password](https://myaccount.google.com/apppasswords) (needs 2FA) |
| `EMAIL_TO` | fallback recipient for shared-config mode (multi-user emails go to each user's own address) |
| `ADVISOR_BROKERS` | shared-config mode only: subset of `zerodha,upstox,angelone` |
| `KITE_*` / `UPSTOX_*` / `ANGEL_*` | shared-config mode broker creds (per-user creds go through the API instead) |

### `config.yaml` (tunables)

Indicator periods, signal thresholds (`concentration_trim_pct`, `hard_stop_pct`,
`profit_take_pct`, `atr_stop_mult`, `gap_alert_pct`), the `.NS`/`.BO` exchange
suffix, the **NSE holiday list** — update that once a year from the NSE
calendar so sessions are skipped correctly — plus the **benchmark index list**
(`market.indices`) and gap-scan thresholds (`report.min_gap_pct`,
`report.max_gap_reason_rows`) used by the market-open brief.

### `data/fno_stocks.txt`

One NSE symbol per line — the F&O universe scanned for gap-ups/gap-downs at
market open. Copy `data/fno_stocks.example.txt` to start; NSE revises the
official F&O underlying list roughly quarterly, so refresh this file
periodically from their published list.

---

## Daily broker tokens

Broker session tokens expire every day. **Angel One is fully automated** (the API
holds only the TOTP secret and mints a fresh code each run). Zerodha and Upstox
need a daily browser approval — each user re-submits a fresh `access_token`:

```
PUT /brokers/zerodha  {"fields": {"api_key": "...", "api_secret": "...", "access_token": "<today's>"}}
```

In **shared-config mode** the helper scripts write a token file instead:

```bash
python scripts/zerodha_login.py   # -> data/zerodha_token.json
python scripts/upstox_login.py    # -> data/upstox_token.json
```

If a token is missing or stale, that broker is skipped for the run (logged) and
the brief still goes out from whatever else connected. Automating the Zerodha /
Upstox daily approval (headless TOTP login) is the main open task; Angel One
already runs unattended.

---

## How the rule engine decides

Per symbol it tallies a bullish/bearish score from: trend (price vs 50 & 200-day
SMA), 20/50 SMA crossovers, RSI (oversold/overbought), MACD signal-line crosses,
and position relative to the 20-day range. For names you **hold** it then
overrides with risk rules: a breached **chandelier stop** (recent high − 3×ATR)
or a hard stop (−12% vs your average cost) → `STOPLOSS_HIT`; a broken trend →
`EXIT`; up ≥30% with fading momentum → `TRIM`; >22% of the book in one name →
`TRIM`. Everything shows its reasons in the email so you can judge it yourself.

`src/advisor/signals.py` is ~120 readable lines — tune it to your style.

---

## Tests

```bash
pip install -r requirements.txt pytest
PYTHONPATH=src pytest -q
```

Covers FIFO realised-P&L matching, cross-broker holding merges, the indicator +
signal logic, password hashing / credential encryption, and the full auth flow
(register → login → `/me` → refresh rotation → reuse detection → logout) plus
broker-credential CRUD via `TestClient`.

---

## Layout

```
src/advisor/
  api/
    main.py       FastAPI app
    settings.py   env-driven config      db.py  engine/session/Base
    models_db.py  User, RefreshToken, OAuthState, BrokerCredential
    security.py   bcrypt + JWT + refresh-token primitives
    crypto.py     Fernet for broker creds at rest
    deps.py       get_current_user
    routers/      auth.py  google.py  brokers.py  portfolio.py
    service.py    glue: decrypt creds -> run pipeline per user
  brokers/      zerodha.py  upstox.py  angelone.py  (+ base, factory)
  portfolio.py  merge accounts, FIFO realised P&L, concentration
  marketdata.py yfinance daily OHLC
  marketmovers.py index moves + F&O gap-up/gap-down scan
  indicators.py SMA/EMA/RSI/MACD/ATR/support-resistance
  signals.py    rule engine -> SymbolSignal
  llm.py        Claude commentary + market-open outlook + gap reasons (web search)
  notifier.py   Gmail SMTP
  report.py     HTML + text rendering
  run.py        build_report / deliver / run_session / --all-users
scripts/        shared-config daily token refresh helpers
crontab         08:45, 09:25 & 15:45 IST, Mon–Fri
```

---

## Known limits

- **No intraday alerts.** Two scheduled briefs per day by design. Add cron lines
  in `crontab` if you want more.
- **Realised P&L history is only as complete as `data/trades.csv`.** Broker APIs
  don't backfill it.
- **yfinance** is an unofficial data source; occasional gaps/misses are logged
  and that symbol is skipped for the day. Swap `marketdata.py` for a broker
  historical-candle API if you need higher reliability.
- **The market-open gap scan depends on yfinance's intraday-updated daily bar**
  for today's open. That row can lag the real opening print by several
  minutes on Yahoo's free feed; a symbol with no fresh row yet is silently
  skipped that run rather than reported stale. Cross-check the gap list
  against your broker terminal before acting on it, and swap in a broker
  quote API in `marketmovers.py` if you need tighter timing.
- **SQLite is the default DB.** Fine for a handful of users; the `api` and
  `scheduler` containers both write to it via the shared `./data` volume. For
  real multi-user load set `DATABASE_URL` to Postgres.
- **No email verification / password reset yet.** Registration issues tokens
  immediately. Add SMTP-based verification before opening signups publicly, or
  set `ALLOW_REGISTRATION=false` and create users yourself.
- **Schema is created with `create_all`.** No Alembic migrations bundled — add
  them before you evolve the models in production.
- **Not advice, no auto-trading.** It never places orders.
