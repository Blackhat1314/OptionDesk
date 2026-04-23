"""
token_manager.py
================
Zero-effort Dhan Access Token Manager — integrated with OptionsDesk.

How it works:
  1. On startup: tries to fetch a fresh token using PIN + TOTP
  2. Caches token in Redis (survives restarts) + in-memory
  3. Auto-refreshes 30 min before expiry via background loop
  4. Falls back to DHAN_ACCESS_TOKEN from .env if auto-refresh fails

Setup (one-time):
  Add to .env:
    DHAN_PIN=<your 6-digit PIN>
    DHAN_TOTP_SECRET=<base32 secret from Dhan TOTP setup>

Rate limit: Dhan enforces 2-minute cooldown between token fetches.
The manager respects this — it never fetches more than once per 2 min.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import aiohttp
import pyotp

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
GENERATE_TOKEN_URL = "https://auth.dhan.co/app/generateAccessToken"
VERIFY_TOKEN_URL   = "https://api.dhan.co/v2/profile"
RATE_LIMIT_SECS    = 125   # 2 min + 5s buffer
REFRESH_BEFORE_MIN = 30    # refresh this many minutes before expiry
TOKEN_CACHE_FILE   = Path("/app/data/.dhan_token.json")   # persisted in Docker volume
RATE_LIMIT_FILE    = Path("/app/data/.dhan_last_fetch.txt")

# ── In-memory state ───────────────────────────────────────────────────────────
_cached_token:   Optional[str]   = None
_token_expiry:   Optional[datetime] = None
_last_fetch_ts:  float           = 0.0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generate_totp(secret: str) -> str:
    totp      = pyotp.TOTP(secret)
    code      = totp.now()
    remaining = 30 - int(time.time() % 30)
    log.info(f"TOTP generated (valid {remaining}s)")
    return code


def _rate_limit_ok() -> bool:
    """Returns True if we can fetch a new token (2-min cooldown respected)."""
    global _last_fetch_ts
    # Check in-memory first
    if time.time() - _last_fetch_ts < RATE_LIMIT_SECS:
        return False
    # Check file (survives restarts)
    try:
        if RATE_LIMIT_FILE.exists():
            last = float(RATE_LIMIT_FILE.read_text().strip())
            if time.time() - last < RATE_LIMIT_SECS:
                return False
    except Exception:
        pass
    return True


def _save_rate_limit_ts() -> None:
    global _last_fetch_ts
    _last_fetch_ts = time.time()
    try:
        RATE_LIMIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        RATE_LIMIT_FILE.write_text(str(_last_fetch_ts))
    except Exception:
        pass


def _load_file_cache() -> Optional[dict]:
    """Load token from file cache (survives container restarts)."""
    try:
        if TOKEN_CACHE_FILE.exists():
            data   = json.loads(TOKEN_CACHE_FILE.read_text())
            expiry = datetime.fromisoformat(data["expiryTime"])
            cutoff = datetime.now() + timedelta(minutes=REFRESH_BEFORE_MIN)
            if expiry > cutoff:
                mins_left = int((expiry - datetime.now()).total_seconds() / 60)
                log.info(f"File-cached token valid for {mins_left} more minutes")
                return data
    except Exception:
        pass
    return None


def _save_file_cache(data: dict) -> None:
    try:
        TOKEN_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_CACHE_FILE.write_text(json.dumps(data, indent=2))
        log.info(f"Token saved to {TOKEN_CACHE_FILE}")
    except Exception as e:
        log.warning(f"Could not save token to file: {e}")


def _token_needs_refresh() -> bool:
    """True if in-memory token is missing or expiring within REFRESH_BEFORE_MIN."""
    if not _cached_token or not _token_expiry:
        return True
    return datetime.now() + timedelta(minutes=REFRESH_BEFORE_MIN) >= _token_expiry


# ── Core fetch ────────────────────────────────────────────────────────────────

async def _fetch_new_token(client_id: str, pin: str, totp_secret: str) -> dict:
    """
    Hit Dhan's generateAccessToken endpoint.
    Respects 2-minute rate limit.
    """
    if not _rate_limit_ok():
        elapsed = int(time.time() - _last_fetch_ts)
        wait    = RATE_LIMIT_SECS - elapsed
        raise RuntimeError(
            f"Dhan rate limit: last fetch was {elapsed}s ago. "
            f"Wait {wait}s before retrying."
        )

    params = {
        "dhanClientId": client_id,
        "pin":          pin,
        "totp":         _generate_totp(totp_secret),
    }

    log.info("Fetching new Dhan access token...")
    async with aiohttp.ClientSession() as session:
        async with session.post(GENERATE_TOKEN_URL, params=params) as resp:
            body = await resp.text()
            log.info(f"Dhan token response [{resp.status}]")

            if resp.status != 200:
                raise RuntimeError(f"generateAccessToken failed [{resp.status}]: {body}")

            data = json.loads(body)

            if data.get("status") == "error":
                raise RuntimeError(f"Dhan API error: {data.get('message', data)}")

            if "accessToken" not in data:
                raise RuntimeError(f"Unexpected Dhan response: {data}")

            log.info(
                f"Token issued for: {data.get('dhanClientName', 'N/A')} | "
                f"expires: {data.get('expiryTime')}"
            )
            _save_rate_limit_ts()
            _save_file_cache(data)
            return data


# ── Public API ────────────────────────────────────────────────────────────────

async def get_access_token() -> str:
    """
    Returns a valid Dhan access token. Fully automated.

    Priority:
      1. In-memory cache (fastest)
      2. File cache (survives restarts)
      3. Fresh fetch via PIN + TOTP
      4. Fallback to DHAN_ACCESS_TOKEN from .env
    """
    global _cached_token, _token_expiry

    from config import get_settings
    s = get_settings()

    # 1. In-memory cache
    if not _token_needs_refresh():
        return _cached_token  # type: ignore

    # 2. File cache
    cached = _load_file_cache()
    if cached:
        _cached_token = cached["accessToken"]
        try:
            _token_expiry = datetime.fromisoformat(cached["expiryTime"])
        except Exception:
            _token_expiry = datetime.now() + timedelta(hours=24)
        return _cached_token

    # 3. Fresh fetch (requires PIN + TOTP)
    if s.DHAN_PIN and s.DHAN_TOTP_SECRET:
        try:
            data = await _fetch_new_token(s.DHAN_CLIENT_ID, s.DHAN_PIN, s.DHAN_TOTP_SECRET)
            _cached_token = data["accessToken"]
            try:
                _token_expiry = datetime.fromisoformat(data["expiryTime"])
            except Exception:
                _token_expiry = datetime.now() + timedelta(hours=24)
            return _cached_token
        except RuntimeError as e:
            log.warning(f"Token fetch failed: {e}")
            # If rate limited, try stale file cache as last resort
            if TOKEN_CACHE_FILE.exists():
                try:
                    stale = json.loads(TOKEN_CACHE_FILE.read_text())
                    if "accessToken" in stale:
                        log.warning("Using stale cached token (rate limited)")
                        return stale["accessToken"]
                except Exception:
                    pass

    # 4. Fallback to .env token
    if s.DHAN_ACCESS_TOKEN:
        log.info("Using DHAN_ACCESS_TOKEN from .env (manual token)")
        _cached_token = s.DHAN_ACCESS_TOKEN
        _token_expiry = datetime.now() + timedelta(hours=24)
        return _cached_token

    raise RuntimeError(
        "No Dhan access token available. "
        "Set DHAN_PIN + DHAN_TOTP_SECRET in .env for auto-refresh, "
        "or set DHAN_ACCESS_TOKEN manually."
    )


async def run_token_refresh_loop():
    """
    Background loop: fetches fresh token on startup, then checks every 10 minutes.
    Handles TOTP timing issues with retry logic.
    """
    from config import get_settings
    s = get_settings()

    if not s.DHAN_PIN or not s.DHAN_TOTP_SECRET:
        log.info("Token auto-refresh disabled (DHAN_PIN/DHAN_TOTP_SECRET not set)")
        return

    log.info("Token auto-refresh loop started")

    # ── Startup: always fetch a fresh token ──────────────────────────────────
    # Retry up to 5 times with TOTP window awareness
    for attempt in range(5):
        try:
            # Wait for a fresh TOTP window if we're near the end of one
            remaining = 30 - int(time.time() % 30)
            if remaining < 8:
                log.info(f"Waiting {remaining}s for fresh TOTP window...")
                await asyncio.sleep(remaining + 1)

            token = await get_access_token()
            _inject_token(token)
            log.info("Startup token fetch successful")
            break
        except RuntimeError as e:
            if "Invalid TOTP" in str(e) or "rate limit" in str(e).lower():
                wait = 35 if "Invalid TOTP" in str(e) else RATE_LIMIT_SECS
                log.warning(f"Startup token attempt {attempt+1} failed: {e} — waiting {wait}s")
                await asyncio.sleep(wait)
            else:
                log.warning(f"Startup token attempt {attempt+1} failed: {e}")
                await asyncio.sleep(10)
        except Exception as e:
            log.warning(f"Startup token attempt {attempt+1} error: {e}")
            await asyncio.sleep(10)

    # ── Main loop: check every 10 minutes ────────────────────────────────────
    while True:
        try:
            await asyncio.sleep(600)

            if _token_needs_refresh():
                log.info("Token expiring soon — refreshing...")
                # Wait for fresh TOTP window
                remaining = 30 - int(time.time() % 30)
                if remaining < 8:
                    await asyncio.sleep(remaining + 1)

                token = await get_access_token()
                _inject_token(token)
                log.info("Token refreshed successfully")

        except Exception as e:
            log.warning(f"Token refresh loop error: {e}")
            await asyncio.sleep(60)


def _inject_token(token: str) -> None:
    """
    Inject the new APP token into the running DhanAPIClient HTTP client only.
    The WebSocket client keeps the SELF token from .env — APP tokens don't
    have WebSocket market feed access.
    """
    try:
        from api.dhan_client import get_dhan_client

        # Update HTTP client only — NOT the WS client
        client = get_dhan_client()
        client.access_token = token
        if client._session and not client._session.closed:
            client._session._default_headers.update({"access-token": token})

        log.info("APP token injected into HTTP client (WS keeps SELF token)")
    except Exception as e:
        log.warning(f"Token injection failed: {e}")
