"""Sign in with Google — OAuth2 authorization-code flow with PKCE, OIDC ID-token
verification against Google's JWKS. Creates or links a local user, then issues
this API's own JWT pair (same tokens as password login)."""

from __future__ import annotations

import base64
import hashlib
import secrets
import urllib.parse
from datetime import timedelta

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db, utcnow
from ..models_db import OAuthState, User
from ..schemas import GoogleAuthURL, TokenPair
from ..settings import Settings, get_settings
from .auth import _issue_pair

router = APIRouter(prefix="/auth/google", tags=["auth"])

_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}

_jwks_client = jwt.PyJWKClient(_JWKS_URL)


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    return verifier, challenge


@router.get("/authorize", response_model=GoogleAuthURL)
def authorize(
    redirect_after: str | None = Query(default=None, description="URL to bounce the browser to after login"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> GoogleAuthURL:
    if not settings.google_configured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Google login is not configured")

    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(32)
    db.add(
        OAuthState(
            state=state,
            code_verifier=verifier,
            redirect_after=redirect_after,
            expires_at=utcnow() + timedelta(minutes=10),
        )
    )
    db.commit()

    params = {
        "client_id": settings.google_client_id,
        "response_type": "code",
        "scope": "openid email profile",
        "redirect_uri": settings.google_redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "online",
        "prompt": "select_account",
    }
    return GoogleAuthURL(authorization_url=f"{_AUTH_URL}?{urllib.parse.urlencode(params)}")


@router.get("/callback")
def callback(
    state: str,
    code: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    st = db.get(OAuthState, state)
    if st is not None:
        db.delete(st)
        db.commit()
    if error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Google returned an error: {error}")
    if st is None or st.expires_at <= utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired state")
    if not code:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing authorization code")

    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(
                _TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": settings.google_redirect_uri,
                    "code_verifier": st.code_verifier,
                },
                headers={"Accept": "application/json"},
            )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Token exchange with Google failed: {e}")

    id_token = resp.json().get("id_token")
    if not id_token:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Google response had no id_token")

    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.google_client_id,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid Google ID token: {e}")

    if claims.get("iss") not in _ISSUERS:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unexpected token issuer")
    if not claims.get("email"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google account has no email")

    sub = claims["sub"]
    email = claims["email"].lower()

    user = db.scalar(select(User).where(User.google_sub == sub))
    if user is None:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                email=email,
                full_name=claims.get("name"),
                google_sub=sub,
                auth_provider="google",
                is_verified=bool(claims.get("email_verified", False)),
            )
            db.add(user)
        else:  # link Google to an existing password account
            user.google_sub = sub
            user.auth_provider = "both" if user.hashed_password else "google"
            user.is_verified = user.is_verified or bool(claims.get("email_verified", False))
        db.commit()
        db.refresh(user)

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")

    pair = _issue_pair(db, user, settings)

    target = st.redirect_after or settings.frontend_url
    if target:
        frag = urllib.parse.urlencode(
            {"access_token": pair.access_token, "refresh_token": pair.refresh_token,
             "expires_in": pair.expires_in}
        )
        return RedirectResponse(url=f"{target}#{frag}", status_code=status.HTTP_302_FOUND)
    return TokenPair.model_validate(pair.model_dump())
