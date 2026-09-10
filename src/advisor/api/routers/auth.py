"""Local auth: register, login, refresh (with rotation + reuse detection), logout."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db, utcnow
from ..deps import get_current_user
from ..models_db import RefreshToken, User
from ..schemas import LogoutIn, RefreshIn, RegisterIn, TokenPair, UserOut
from ..security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)
from ..settings import Settings, get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_pair(db: Session, user: User, settings: Settings) -> TokenPair:
    raw, digest = new_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=digest,
            expires_at=utcnow() + timedelta(days=settings.refresh_ttl_days),
        )
    )
    db.commit()
    return TokenPair(
        access_token=create_access_token(user.id, settings, {"email": user.email}),
        refresh_token=raw,
        expires_in=settings.access_ttl_min * 60,
    )


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
def register(
    body: RegisterIn,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenPair:
    if not settings.allow_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Registration is disabled")
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(
        email=email,
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        auth_provider="local",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _issue_pair(db, user, settings)


@router.post("/login", response_model=TokenPair)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenPair:
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    if not user or not user.hashed_password or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")
    return _issue_pair(db, user, settings)


@router.post("/refresh", response_model=TokenPair)
def refresh(
    body: RefreshIn,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenPair:
    digest = hash_refresh_token(body.refresh_token)
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == digest))
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

    if token.revoked_at is not None:
        # Re-use of an already-rotated token => likely theft. Nuke the family.
        db.query(RefreshToken).filter(
            RefreshToken.user_id == token.user_id, RefreshToken.revoked_at.is_(None)
        ).update({RefreshToken.revoked_at: utcnow()})
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token reuse detected — all sessions revoked")

    if token.expires_at <= utcnow():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token expired")

    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account unavailable")

    token.revoked_at = utcnow()
    pair = _issue_pair(db, user, settings)
    token.replaced_by = hash_refresh_token(pair.refresh_token)
    db.commit()
    return pair


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: LogoutIn, db: Session = Depends(get_db)) -> None:
    digest = hash_refresh_token(body.refresh_token)
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == digest))
    if token and token.revoked_at is None:
        token.revoked_at = utcnow()
        db.commit()


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)
    ).update({RefreshToken.revoked_at: utcnow()})
    db.commit()


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
