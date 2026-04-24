"""
token_manager.py
================
Fully automatic Dhan token manager.

- Fetches a fresh token on startup via PIN + TOTP
- Injects into both REST client and WebSocket client
- Reconnects WebSocket automatically when token is refreshed
- Refreshes 30 min before expiry (every ~23.5h)
- Falls back to DHAN_ACCESS_TOKEN from .env if auto-fetch fails

.env requirements:
  DHAN_PIN=<6-digit PIN>
  DHAN_TOTP_SECRET=<base32 TOTP secret>
  DHAN_ACCESS_TOKEN=<fallback token — used if PIN/TOTP not set>
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

GENERATE_TOKEN_URL = "https://auth.dhan.co/app/generateAccessToken"
RATE_LIMIT_SECS    = 125   # 2 min + 5s buffer
REFRESH_BEFORE_MIN = 30
TOKEN_CACHE_FILE   = Path("/app/data/.dhan_token.json")
RATE_LIMIT_FILE    = Path("/app/data/.dhan_last_fetch.txt")

_cached_token:  Optional[str]      = None
_token_expiry:  Optional[datetime] = None
_last_fetch_ts: float              = 0.0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generate_totp(secret: str) -> str:
    return pyotp.TOTP(secret).now()


def _rate_limit_ok() -> bool:
    global _last_fetch_ts
    if time.time() - _last_fetch_ts < RATE_LIMIT_SECS:
        return False
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
    try:
        if TOKEN_CACHE_FILE.exists():
            data   = json.loads(TOKEN_CACHE_FILE.read_text())
            expiry = datetime.fromisoformat(data["expiryTime"])
            if expiry > datetime.now() + timedelta(minutes=REFRESH_BEFORE_MIN):
                return data
    except Exception:
        pass
    return None


def _save_file_cache(data: dict) -> None:
    try:
        TOKEN_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_CACHE_FILE.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


def _token_needs_refresh() -> bool:
    if not _cached_token or not _token_expiry:
        return True
    return datetime.now() + timedelta(minutes=REFRESH_BEFORE_MIN) >= _token_expiry


def _decode_expiry(token: str) -> Optional[datetime]:
    try:
        import base64 as _b64
        payload = json.loads(_b64.b64decode(token.split(".")[1] + "==").decode())
        exp = payload.get("exp", 0)
        return datetime.fromtimestamp(exp) if exp else None
    except Exception:
        return None


# ── Core fetch ────────────────────────────────────────────────────────────────

async def _fetch_new_token(client_id: str, pin: str, totp_secret: str) -> dict:
    """Fetch fresh token via PIN + TOTP. Respects 2-min rate limit."""
    if not _rate_limit_ok():
        elapsed = int(time.time() - _last_fetch_ts)
        raise RuntimeError(f"Rate limited — wait {RATE_LIMIT_SECS - elapsed}s")

    params = {
        "dhanClientId": client_id,
        "pin":          pin,
        "totp":         _generate_totp(totp_secret),
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(GENERATE_TOKEN_URL, params=params) as resp:
            body = await resp.text()
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}: {body[:200]}")
            data = json.loads(body)
            if data.get("status") == "error":
                raise RuntimeError(f"Dhan error: {data.get('message', data)}")
            if "accessToken" not in data:
                raise RuntimeError(f"Unexpected response: {data}")
            _save_rate_limit_ts()
            _save_file_cache(data)
            return data


# ── Injection ─────────────────────────────────────────────────────────────────

def _inject_token(token: str) -> None:
    """Inject token into both REST and WS clients."""
    try:
        from api.dhan_client import get_dhan_client, get_ws_client

        # REST client
        rest = get_dhan_client()
        rest.access_token = token
        if rest._session and not rest._session.closed:
            rest._session._default_headers.update({"access-token": token})

        # WS client — update token so next reconnect uses the new one
        ws = get_ws_client()
        ws.access_token = token

        log.info("Token injected into REST + WS clients")
    except Exception as e:
        log.warning(f"Token injection failed: {e}")


async def _reconnect_ws() -> None:
    """Stop and restart the WS connection so it picks up the new token."""
    try:
        from api.dhan_client import get_ws_client
        ws = get_ws_client()
        # Close current connection — connect_and_stream loop will reconnect automatically
        if ws._ws:
            await ws._ws.close()
        log.info("WS reconnect triggered (new token)")
    except Exception as e:
        log.warning(f"WS reconnect failed: {e}")


# ── Public API ────────────────────────────────────────────────────────────────

async def get_access_token() -> str:
    """
    Returns a valid token. Priority:
      1. In-memory cache
      2. File cache (survives restarts)
      3. Fresh fetch via PIN + TOTP
      4. Fallback to .env DHAN_ACCESS_TOKEN
    """
    global _cached_token, _token_expiry

    from config import get_settings
    s = get_settings()

    if not _token_needs_refresh():
        return _cached_token  # type: ignore

    # File cache
    cached = _load_file_cache()
    if cached:
        _cached_token = cached["accessToken"]
        _token_expiry = datetime.fromisoformat(cached["expiryTime"])
        return _cached_token

    # Fresh fetch
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
            # Rate limited — try stale file cache
            try:
                if TOKEN_CACHE_FILE.exists():
                    stale = json.loads(TOKEN_CACHE_FILE.read_text())
                    if "accessToken" in stale:
                        return stale["accessToken"]
            except Exception:
                pass

    # Fallback to .env
    if s.DHAN_ACCESS_TOKEN:
        _cached_token = s.DHAN_ACCESS_TOKEN
        _token_expiry = _decode_expiry(s.DHAN_ACCESS_TOKEN) or \
                        datetime.now() + timedelta(hours=24)
        return _cached_token

    raise RuntimeError("No Dhan access token available.")


async def run_token_refresh_loop():
    """
    Background loop:
      1. Startup — fetch fresh token, inject into REST + WS
      2. Every 10 min — check if token needs refresh
      3. On refresh — inject new token + reconnect WS
    """
    from config import get_settings
    s = get_settings()

    if not s.DHAN_PIN or not s.DHAN_TOTP_SECRET:
        # No auto-refresh — just inject whatever is in .env into both clients
        if s.DHAN_ACCESS_TOKEN:
            _inject_token(s.DHAN_ACCESS_TOKEN)
            expiry = _decode_expiry(s.DHAN_ACCESS_TOKEN)
            if expiry:
                mins = int((expiry - datetime.now()).total_seconds() / 60)
                log.info(f"Using .env token (valid {mins} min) — set DHAN_PIN+DHAN_TOTP_SECRET for auto-refresh")
            else:
                log.info("Using .env token — set DHAN_PIN+DHAN_TOTP_SECRET for auto-refresh")
        return

    log.info("Token auto-refresh enabled (PIN + TOTP)")

    # ── Startup fetch ─────────────────────────────────────────────────────────
    for attempt in range(5):
        try:
            # Wait for a fresh TOTP window if near the end of one
            remaining = 30 - int(time.time() % 30)
            if remaining < 8:
                log.info(f"Waiting {remaining}s for fresh TOTP window...")
                await asyncio.sleep(remaining + 1)

            token = await get_access_token()
            _inject_token(token)
            expiry = _decode_expiry(token)
            mins = int((expiry - datetime.now()).total_seconds() / 60) if expiry else 0
            log.info(f"Startup token OK — valid {mins} min")
            break

        except RuntimeError as e:
            wait = 35 if "Invalid TOTP" in str(e) else (RATE_LIMIT_SECS if "Rate limited" in str(e) else 10)
            log.warning(f"Startup attempt {attempt+1}/5 failed: {e} — retrying in {wait}s")
            await asyncio.sleep(wait)
        except Exception as e:
            log.warning(f"Startup attempt {attempt+1}/5 error: {e}")
            await asyncio.sleep(10)

    # ── Main loop ─────────────────────────────────────────────────────────────
    while True:
        try:
            await asyncio.sleep(600)  # check every 10 min

            if _token_needs_refresh():
                log.info("Token expiring soon — refreshing...")

                remaining = 30 - int(time.time() % 30)
                if remaining < 8:
                    await asyncio.sleep(remaining + 1)

                token = await get_access_token()
                _inject_token(token)
                # Reconnect WS so it uses the new token immediately
                await _reconnect_ws()
                log.info("Token refreshed + WS reconnected")

        except Exception as e:
            log.warning(f"Token refresh loop error: {e}")
            await asyncio.sleep(60)
