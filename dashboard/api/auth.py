"""
Authentication system — JWT + session-based auth for dashboard.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from dashboard.config import settings

log = logging.getLogger("dashboard.auth")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)


class TokenData(BaseModel):
    username: str
    exp: datetime


class LoginRequest(BaseModel):
    username: str
    password: str


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> Optional[TokenData]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        username = payload.get("sub")
        exp = payload.get("exp")
        if username is None:
            return None
        return TokenData(username=username, exp=datetime.fromtimestamp(exp, tz=timezone.utc))
    except JWTError:
        return None


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """Validate JWT from header or cookie."""
    token = None

    # Check Authorization header
    if credentials:
        token = credentials.credentials

    # Check cookie fallback
    if not token:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    data = decode_token(token)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return data.username


def authenticate_user(username: str, password: str) -> bool:
    """Check credentials against configured admin user."""
    if username != settings.admin_user:
        return False
    # Support plain-text comparison for .env simplicity
    if password == settings.admin_password:
        return True
    # Also support bcrypt-hashed passwords
    try:
        return verify_password(password, settings.admin_password)
    except Exception:
        return False
