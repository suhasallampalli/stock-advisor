"""Shared FastAPI dependencies."""

from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .db import get_db
from .models_db import User
from .security import decode_access_token
from .settings import Settings, get_settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

_CRED_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    try:
        payload = decode_access_token(token, settings)
    except jwt.PyJWTError:
        raise _CRED_EXC
    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise _CRED_EXC
    return user
