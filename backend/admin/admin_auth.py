"""
admin/admin_auth.py
Admin authentication — completely separate from user auth.
Admin credentials stored in .env (ADMIN_USERNAME, ADMIN_PASSWORD).
Uses a separate JWT secret.
"""

import time
import secrets
import hashlib
from typing import Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from jose import JWTError, jwt

from config import get_settings

settings = get_settings()

admin_auth_router = APIRouter(prefix="/admin-api/auth", tags=["Admin Auth"])
bearer_scheme     = HTTPBearer(auto_error=False)

ADMIN_JWT_SECRET    = settings.ADMIN_JWT_SECRET
ADMIN_JWT_ALGORITHM = "HS256"
ADMIN_JWT_EXPIRE    = 60 * 8   # 8 hours


class AdminLoginRequest(BaseModel):
    username: str
    password: str


def _create_admin_token() -> str:
    expire = datetime.utcnow() + timedelta(minutes=ADMIN_JWT_EXPIRE)
    return jwt.encode(
        {"sub": "admin", "exp": expire, "jti": secrets.token_hex(8)},
        ADMIN_JWT_SECRET,
        algorithm=ADMIN_JWT_ALGORITHM,
    )


def _verify_admin_token(token: str) -> bool:
    try:
        payload = jwt.decode(token, ADMIN_JWT_SECRET, algorithms=[ADMIN_JWT_ALGORITHM])
        return payload.get("sub") == "admin"
    except JWTError:
        return False


async def require_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> str:
    if not credentials:
        raise HTTPException(status_code=401, detail="Admin auth required")
    if not _verify_admin_token(credentials.credentials):
        raise HTTPException(status_code=401, detail="Invalid or expired admin token")
    return "admin"


@admin_auth_router.post("/login")
async def admin_login(body: AdminLoginRequest, request: Request):
    if (body.username != settings.ADMIN_USERNAME or
            body.password != settings.ADMIN_PASSWORD):
        raise HTTPException(status_code=401, detail="Invalid admin credentials")
    token = _create_admin_token()
    return {"access_token": token, "expires_in": ADMIN_JWT_EXPIRE * 60}
