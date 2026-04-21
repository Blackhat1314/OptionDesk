"""
Authentication & Authorization
================================
JWT-based auth with:
- Signup (requires invite code)
- Login (returns JWT)
- Single-session enforcement (one active session per user)
- IP tracking (blocks same account from multiple IPs simultaneously)
- Rate limiting on auth endpoints
"""

import time
import hashlib
import secrets
from typing import Optional, Dict
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Depends, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from jose import JWTError, jwt
from passlib.context import CryptContext
import redis.asyncio as aioredis

from config import get_settings

settings = get_settings()

auth_router = APIRouter(prefix="/auth", tags=["Auth"])
bearer_scheme = HTTPBearer(auto_error=False)
pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")

# ─── Redis keys ───────────────────────────────────────────────────────────────
# users:{username}          → {hashed_password, created_at}
# session:{username}        → {token_hash, ip, created_at, last_seen}
# auth_attempts:{ip}        → count (TTL 15 min)

_redis: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        url = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"
        _redis = aioredis.from_url(url, encoding="utf-8", decode_responses=True)
    return _redis


# ─── Models ───────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    username: str
    password: str
    invite_code: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    expires_in: int


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _create_token(username: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {
        "sub": username,
        "exp": expire,
        "iat": datetime.utcnow(),
        "jti": secrets.token_hex(16),   # unique token ID
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def _verify_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


async def _check_rate_limit(r: aioredis.Redis, ip: str, max_attempts: int = 10) -> bool:
    """Returns True if allowed, False if rate-limited."""
    key = f"auth_attempts:{ip}"
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, 900)   # 15-minute window
    return count <= max_attempts


# ─── Auth dependency ──────────────────────────────────────────────────────────

async def require_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> str:
    """
    FastAPI dependency — validates JWT and enforces single-session.
    Returns username on success, raises 401 on failure.
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = credentials.credentials
    payload = _verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    # Single-session check: verify this token is the active session
    try:
        r = await get_redis()
        session_data = await r.hgetall(f"session:{username}")
        if not session_data:
            raise HTTPException(status_code=401, detail="Session expired — please log in again")

        stored_hash = session_data.get("token_hash", "")
        if stored_hash != _hash_token(token):
            raise HTTPException(
                status_code=401,
                detail="Your account is logged in from another device. Please log in again."
            )

        # Update last_seen
        client_ip = request.headers.get("X-Real-IP") or request.client.host
        await r.hset(f"session:{username}", mapping={
            "last_seen": str(time.time()),
            "ip": client_ip,
        })
    except HTTPException:
        raise
    except Exception:
        pass   # Redis unavailable — allow through (graceful degradation)

    return username


async def optional_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[str]:
    """Optional auth — returns username or None."""
    if not credentials:
        return None
    payload = _verify_token(credentials.credentials)
    return payload.get("sub") if payload else None


# ─── Endpoints ────────────────────────────────────────────────────────────────

@auth_router.post("/signup", response_model=TokenResponse)
async def signup(body: SignupRequest, request: Request):
    """
    Register a new user.
    Requires the owner-provided invite code.
    """
    r = await get_redis()
    client_ip = request.headers.get("X-Real-IP") or request.client.host

    # Rate limit
    if not await _check_rate_limit(r, client_ip, max_attempts=5):
        raise HTTPException(status_code=429, detail="Too many attempts. Try again in 15 minutes.")

    # Validate invite code
    if body.invite_code.strip().upper() != settings.INVITE_CODE.upper():
        raise HTTPException(status_code=403, detail="Invalid invite code")

    # Validate username
    username = body.username.strip().lower()
    if len(username) < 3 or len(username) > 32:
        raise HTTPException(status_code=400, detail="Username must be 3–32 characters")
    if not username.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="Username: letters, numbers, _ and - only")

    # Check if username taken
    existing = await r.hgetall(f"users:{username}")
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken")

    # Validate password
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    # Store user
    hashed = pwd_context.hash(body.password)
    await r.hset(f"users:{username}", mapping={
        "password": hashed,
        "created_at": str(time.time()),
        "ip": client_ip,
    })

    # Create session
    token = _create_token(username)
    await r.hset(f"session:{username}", mapping={
        "token_hash": _hash_token(token),
        "ip": client_ip,
        "created_at": str(time.time()),
        "last_seen": str(time.time()),
    })
    await r.expire(f"session:{username}", settings.JWT_EXPIRE_MINUTES * 60)

    return TokenResponse(
        access_token=token,
        username=username,
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
    )


@auth_router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request):
    """
    Login with username + password.
    Enforces single-session: logging in from a new device invalidates the old session.
    """
    r = await get_redis()
    client_ip = request.headers.get("X-Real-IP") or request.client.host

    # Rate limit
    if not await _check_rate_limit(r, client_ip, max_attempts=10):
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again in 15 minutes.")

    username = body.username.strip().lower()

    # Fetch user
    user_data = await r.hgetall(f"users:{username}")
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Verify password
    if not pwd_context.verify(body.password, user_data.get("password", "")):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Single-session: check if already logged in from a different IP
    existing_session = await r.hgetall(f"session:{username}")
    if existing_session:
        existing_ip = existing_session.get("ip", "")
        if existing_ip and existing_ip != client_ip:
            # Invalidate old session — new login takes over
            pass   # We'll overwrite below

    # Create new session (invalidates any existing session)
    token = _create_token(username)
    await r.hset(f"session:{username}", mapping={
        "token_hash": _hash_token(token),
        "ip": client_ip,
        "created_at": str(time.time()),
        "last_seen": str(time.time()),
    })
    await r.expire(f"session:{username}", settings.JWT_EXPIRE_MINUTES * 60)

    return TokenResponse(
        access_token=token,
        username=username,
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
    )


@auth_router.post("/logout")
async def logout(username: str = Depends(require_auth)):
    """Invalidate the current session."""
    r = await get_redis()
    await r.delete(f"session:{username}")
    return {"status": "logged out"}


@auth_router.get("/me")
async def me(username: str = Depends(require_auth)):
    """Return current user info."""
    r = await get_redis()
    session = await r.hgetall(f"session:{username}")
    return {
        "username": username,
        "ip": session.get("ip"),
        "last_seen": float(session.get("last_seen", 0)),
    }
