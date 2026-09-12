"""FastAPI application entrypoint.

Run:  uvicorn advisor.api.main:app --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import init_db
from .routers import auth, brokers, google, portfolio
from .settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
for noisy in ("yfinance", "peewee", "urllib3", "httpx", "httpcore"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

log = logging.getLogger("advisor.api")
_FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings().validate()
    init_db()
    yield


app = FastAPI(
    title="stock-advisor API",
    version="0.1.0",
    summary="Multi-user auth + per-user portfolio briefs for the Indian market.",
    lifespan=lifespan,
)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(google.router)
app.include_router(brokers.router)
app.include_router(portfolio.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "google_login": _settings.google_configured}


# --- serve the built React SPA (frontend/dist), if it's been built ---------
# Registered last so it never shadows the API routes above, /docs, or /openapi.json.
if _FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        return FileResponse(_FRONTEND_DIST / "index.html")
else:
    log.info("frontend/dist not found — serving API only (run `npm run build` in frontend/ to add the UI)")
