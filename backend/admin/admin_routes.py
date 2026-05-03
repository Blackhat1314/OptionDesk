"""
admin/admin_routes.py
Complete admin API — users, sessions, metrics, system health.
All endpoints require admin JWT.
"""

import time
import random
import string
import hashlib
from typing import Optional, List
from datetime import datetime

import pytz
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel
from passlib.context import CryptContext
import redis.asyncio as aioredis

from config import get_settings
from admin.admin_auth import require_admin
from core.redis_cache import get_cache
from api.websocket_manager import get_connection_manager

settings   = get_settings()
admin_router = APIRouter(prefix="/admin-api", tags=["Admin"])
pwd_context  = CryptContext(schemes=["sha256_crypt"], deprecated="auto")
IST          = pytz.timezone("Asia/Kolkata")

_redis: Optional[aioredis.Redis] = None


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        url = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"
        _redis = aioredis.from_url(url, encoding="utf-8", decode_responses=True)
    return _redis


def _now_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")


def _ts_to_ist(ts: float) -> str:
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts, tz=IST).strftime("%d %b %H:%M:%S")


# ── Models ────────────────────────────────────────────────────────────────────

class CreateUserRequest(BaseModel):
    username: Optional[str] = None   # auto-generated if not provided
    password: Optional[str] = None   # auto-generated if not provided
    count: int = 1                   # batch create N users
    expiry_days: int = 30            # account expiry in days (0 = never)


class DeleteUserRequest(BaseModel):
    username: str


class KickUserRequest(BaseModel):
    username: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _gen_username(length: int = 6) -> str:
    """Generate a random 6-char alphanumeric username."""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def _gen_password(length: int = 10) -> str:
    """Generate a random readable password."""
    chars = string.ascii_letters + string.digits + "!@#$"
    return "".join(random.choices(chars, k=length))


async def _get_all_users(r: aioredis.Redis) -> List[dict]:
    """Scan Redis for all user keys."""
    users = []
    cursor = 0
    while True:
        cursor, keys = await r.scan(cursor, match="users:*", count=200)
        for key in keys:
            username = key.split(":", 1)[1]
            data = await r.hgetall(key)
            session = await r.hgetall(f"session:{username}")
            expires_at = float(data.get("expires_at", 0))
            now = time.time()
            is_expired = expires_at > 0 and now > expires_at
            days_left = round((expires_at - now) / 86400, 1) if expires_at > 0 else None
            users.append({
                "username":    username,
                "created_at":  _ts_to_ist(float(data.get("created_at", 0))),
                "created_ip":  data.get("ip", "—"),
                "online":      bool(session) and not is_expired,
                "session_ip":  session.get("ip", "—") if session else "—",
                "last_seen":   _ts_to_ist(float(session.get("last_seen", 0))) if session else "—",
                "last_seen_ts": float(session.get("last_seen", 0)) if session else 0,
                "expires_at":  _ts_to_ist(expires_at) if expires_at > 0 else "Never",
                "expires_at_ts": expires_at,
                "days_left":   days_left,
                "is_expired":  is_expired,
            })
        if cursor == 0:
            break
    return sorted(users, key=lambda u: u["last_seen_ts"], reverse=True)


# ── Dashboard / Overview ──────────────────────────────────────────────────────

@admin_router.get("/dashboard")
async def get_dashboard(_: str = Depends(require_admin)):
    """Main dashboard — all metrics in one call."""
    r       = await _get_redis()
    cache   = get_cache()
    manager = get_connection_manager()

    # Users
    users        = await _get_all_users(r)
    online_users = [u for u in users if u["online"]]

    # WebSocket connections
    ws_count = manager.get_connection_count()

    # Redis info
    redis_info = {}
    try:
        info = await r.info()
        redis_info = {
            "used_memory_human": info.get("used_memory_human", "—"),
            "connected_clients": info.get("connected_clients", 0),
            "total_commands":    info.get("total_commands_processed", 0),
            "uptime_days":       info.get("uptime_in_days", 0),
            "keyspace_hits":     info.get("keyspace_hits", 0),
            "keyspace_misses":   info.get("keyspace_misses", 0),
            "hit_rate":          round(
                info.get("keyspace_hits", 0) /
                max(info.get("keyspace_hits", 0) + info.get("keyspace_misses", 1), 1) * 100, 1
            ),
        }
    except Exception:
        pass

    # Stock pipeline
    pipeline_status = await cache.get("stocks:pipeline:status") or {}
    stock_summary   = await cache.get("stocks:screener:summary")

    # API health
    from stocks.database import get_db_stats
    from stocks.database import init_db
    init_db()
    db_stats = get_db_stats()

    # Redis key counts
    key_counts = {}
    try:
        for pattern, label in [
            ("stock:*:features", "stock_features"),
            ("stock:*:mc_horizons", "mc_horizons"),
            ("chain:*", "option_chains"),
            ("session:*", "active_sessions"),
            ("users:*", "total_users"),
        ]:
            cursor, keys = await r.scan(0, match=pattern, count=1000)
            count = len(keys)
            while cursor != 0:
                cursor, more = await r.scan(cursor, match=pattern, count=1000)
                count += len(more)
            key_counts[label] = count
    except Exception:
        pass

    return ORJSONResponse({
        "timestamp":      _now_ist(),
        "users": {
            "total":       len(users),
            "online":      len(online_users),
            "online_list": online_users,
        },
        "websocket": {
            "connections": ws_count,
        },
        "redis":    redis_info,
        "redis_keys": key_counts,
        "stock_pipeline": {
            "status":        pipeline_status.get("status", "IDLE"),
            "detail":        pipeline_status.get("detail", ""),
            "updated_at":    _ts_to_ist(float(pipeline_status.get("updated_at", 0))),
            "total_stocks":  stock_summary.get("total_stocks", 0) if stock_summary else 0,
            "buy_signals":   stock_summary.get("buy_signals", 0) if stock_summary else 0,
            "computed_at":   _ts_to_ist(float(stock_summary.get("computed_at", 0))) if stock_summary else "—",
        },
        "database": db_stats,
        "system_time": _now_ist(),
    })


# ── Users ─────────────────────────────────────────────────────────────────────

@admin_router.get("/users")
async def list_users(_: str = Depends(require_admin)):
    r     = await _get_redis()
    users = await _get_all_users(r)
    return ORJSONResponse({"users": users, "total": len(users)})


@admin_router.post("/users/create")
async def create_users(body: CreateUserRequest, _: str = Depends(require_admin)):
    """
    Create one or more users.
    If username/password not provided, auto-generates them.
    Returns credentials for all created users.
    """
    r       = await _get_redis()
    created = []
    errors  = []

    count = max(1, min(body.count, 50))   # max 50 at once

    for _ in range(count):
        username = (body.username or _gen_username()).strip().lower()
        password = body.password or _gen_password()

        # Ensure unique username
        attempts = 0
        while await r.exists(f"users:{username}") and attempts < 10:
            username = _gen_username()
            attempts += 1

        if await r.exists(f"users:{username}"):
            errors.append(f"{username}: already exists")
            continue

        hashed = pwd_context.hash(password)
        expires_at = (time.time() + body.expiry_days * 24 * 3600) if body.expiry_days > 0 else 0
        await r.hset(f"users:{username}", mapping={
            "password":   hashed,
            "created_at": str(time.time()),
            "ip":         "admin-created",
            "expires_at": str(expires_at),
        })
        created.append({
            "username":  username,
            "password":  password,
            "expires_in": f"{body.expiry_days} days" if body.expiry_days > 0 else "Never",
        })

    return ORJSONResponse({
        "created": created,
        "errors":  errors,
        "count":   len(created),
    })


@admin_router.delete("/users/{username}")
async def delete_user(username: str, _: str = Depends(require_admin)):
    r = await _get_redis()
    username = username.lower()
    if not await r.exists(f"users:{username}"):
        raise HTTPException(404, f"User {username} not found")
    await r.delete(f"users:{username}")
    await r.delete(f"session:{username}")
    return ORJSONResponse({"status": "deleted", "username": username})


@admin_router.post("/users/{username}/kick")
async def kick_user(username: str, _: str = Depends(require_admin)):
    """Force logout a user by deleting their session."""
    r = await _get_redis()
    username = username.lower()
    deleted = await r.delete(f"session:{username}")
    return ORJSONResponse({
        "status":   "kicked" if deleted else "no_session",
        "username": username,
    })


@admin_router.post("/users/{username}/reset-password")
async def reset_password(username: str, _: str = Depends(require_admin)):
    """Generate a new random password for a user."""
    r = await _get_redis()
    username = username.lower()
    if not await r.exists(f"users:{username}"):
        raise HTTPException(404, f"User {username} not found")
    new_password = _gen_password()
    hashed = pwd_context.hash(new_password)
    await r.hset(f"users:{username}", "password", hashed)
    await r.delete(f"session:{username}")   # force re-login
    return ORJSONResponse({
        "username":     username,
        "new_password": new_password,
        "status":       "password reset, session invalidated",
    })


@admin_router.post("/users/{username}/extend")
async def extend_user_expiry(
    username: str,
    days: int = Query(30, ge=1, le=365, description="Days to extend from today"),
    _: str = Depends(require_admin),
):
    """Extend a user's account expiry by N days from today."""
    r = await _get_redis()
    username = username.lower()
    if not await r.exists(f"users:{username}"):
        raise HTTPException(404, f"User {username} not found")

    new_expiry = time.time() + (days * 24 * 3600)
    await r.hset(f"users:{username}", "expires_at", str(new_expiry))

    return ORJSONResponse({
        "username":    username,
        "extended_by": f"{days} days",
        "new_expiry":  _ts_to_ist(new_expiry),
        "status":      "extended",
    })


@admin_router.post("/users/{username}/set-expiry")
async def set_user_expiry(
    username: str,
    days: int = Query(30, ge=0, le=3650, description="Days from now (0 = never expires)"),
    _: str = Depends(require_admin),
):
    """Set exact expiry for a user. days=0 means never expires."""
    r = await _get_redis()
    username = username.lower()
    if not await r.exists(f"users:{username}"):
        raise HTTPException(404, f"User {username} not found")

    if days == 0:
        await r.hset(f"users:{username}", "expires_at", "0")
        return ORJSONResponse({"username": username, "expiry": "Never", "status": "set"})

    new_expiry = time.time() + (days * 24 * 3600)
    await r.hset(f"users:{username}", "expires_at", str(new_expiry))
    return ORJSONResponse({
        "username": username,
        "expiry":   _ts_to_ist(new_expiry),
        "status":   "set",
    })


# ── Sessions ──────────────────────────────────────────────────────────────────

@admin_router.get("/sessions")
async def list_sessions(_: str = Depends(require_admin)):
    """List all active sessions."""
    r       = await _get_redis()
    sessions = []
    cursor   = 0
    while True:
        cursor, keys = await r.scan(cursor, match="session:*", count=200)
        for key in keys:
            username = key.split(":", 1)[1]
            data     = await r.hgetall(key)
            ttl      = await r.ttl(key)
            sessions.append({
                "username":  username,
                "ip":        data.get("ip", "—"),
                "last_seen": _ts_to_ist(float(data.get("last_seen", 0))),
                "created_at": _ts_to_ist(float(data.get("created_at", 0))),
                "expires_in_min": round(ttl / 60) if ttl > 0 else 0,
            })
        if cursor == 0:
            break
    sessions.sort(key=lambda s: s["last_seen"], reverse=True)
    return ORJSONResponse({"sessions": sessions, "count": len(sessions)})


@admin_router.delete("/sessions/all")
async def kick_all_users(_: str = Depends(require_admin)):
    """Force logout ALL users."""
    r      = await _get_redis()
    cursor = 0
    count  = 0
    while True:
        cursor, keys = await r.scan(cursor, match="session:*", count=200)
        for key in keys:
            await r.delete(key)
            count += 1
        if cursor == 0:
            break
    return ORJSONResponse({"status": "all sessions cleared", "count": count})


# ── API Health ────────────────────────────────────────────────────────────────

@admin_router.get("/health")
async def system_health(_: str = Depends(require_admin)):
    """Detailed system health check."""
    cache   = get_cache()
    manager = get_connection_manager()

    # Redis ping
    redis_ok = False
    redis_latency_ms = 0
    try:
        r  = await _get_redis()
        t0 = time.time()
        await r.ping()
        redis_latency_ms = round((time.time() - t0) * 1000, 2)
        redis_ok = True
    except Exception:
        pass

    # Check option chain cache freshness
    chain_status = {}
    for sym in ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"]:
        cached = await cache.get(f"chain:{sym}")
        if cached:
            ts = cached.get("timestamp", 0)
            age_s = round(time.time() - ts) if ts else 9999
            chain_status[sym] = {"cached": True, "age_seconds": age_s}
        else:
            chain_status[sym] = {"cached": False, "age_seconds": 9999}

    # Stock pipeline
    pipeline = await cache.get("stocks:pipeline:status") or {}
    summary  = await cache.get("stocks:screener:summary")

    # WebSocket
    ws_count = manager.get_connection_count()

    return ORJSONResponse({
        "timestamp": _now_ist(),
        "redis": {
            "ok":         redis_ok,
            "latency_ms": redis_latency_ms,
        },
        "websocket": {
            "connections": ws_count,
            "status":      "ok" if ws_count >= 0 else "error",
        },
        "option_chains": chain_status,
        "stock_pipeline": {
            "status":  pipeline.get("status", "IDLE"),
            "detail":  pipeline.get("detail", ""),
            "ready":   summary is not None,
            "stocks":  summary.get("total_stocks", 0) if summary else 0,
        },
    })


# ── Redis Explorer ────────────────────────────────────────────────────────────

@admin_router.get("/redis/keys")
async def redis_keys(
    pattern: str = Query("*", description="Redis key pattern"),
    limit:   int = Query(100, ge=1, le=500),
    _: str = Depends(require_admin),
):
    """Browse Redis keys by pattern."""
    r      = await _get_redis()
    cursor = 0
    keys   = []
    while len(keys) < limit:
        cursor, batch = await r.scan(cursor, match=pattern, count=200)
        keys.extend(batch)
        if cursor == 0:
            break
    keys = keys[:limit]

    result = []
    for key in keys:
        key_type = await r.type(key)
        ttl      = await r.ttl(key)
        result.append({"key": key, "type": key_type, "ttl": ttl})

    return ORJSONResponse({"keys": result, "count": len(result)})


@admin_router.get("/redis/stats")
async def redis_stats(_: str = Depends(require_admin)):
    """Redis server statistics."""
    r = await _get_redis()
    try:
        info = await r.info()
        return ORJSONResponse({
            "version":           info.get("redis_version"),
            "uptime_days":       info.get("uptime_in_days"),
            "used_memory_human": info.get("used_memory_human"),
            "peak_memory_human": info.get("used_memory_peak_human"),
            "connected_clients": info.get("connected_clients"),
            "total_connections": info.get("total_connections_received"),
            "total_commands":    info.get("total_commands_processed"),
            "keyspace_hits":     info.get("keyspace_hits"),
            "keyspace_misses":   info.get("keyspace_misses"),
            "evicted_keys":      info.get("evicted_keys"),
            "expired_keys":      info.get("expired_keys"),
        })
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Logs / Activity ───────────────────────────────────────────────────────────

@admin_router.get("/activity")
async def recent_activity(_: str = Depends(require_admin)):
    """Recent user activity from sessions."""
    r       = await _get_redis()
    users   = await _get_all_users(r)
    active  = [u for u in users if u["last_seen_ts"] > time.time() - 3600]
    return ORJSONResponse({
        "active_last_hour": active,
        "count": len(active),
    })

# ── Diagnostics ───────────────────────────────────────────────────────────────

@admin_router.get("/diagnostics/token")
async def diag_token(_: str = Depends(require_admin)):
    """Check Dhan token status."""
    import json as _j, base64 as _b64, time as _t
    from config import get_settings as _gs
    s = _gs()
    token = s.DHAN_ACCESS_TOKEN
    try:
        parts   = token.split(".")
        payload = _j.loads(_b64.b64decode(parts[1] + "==").decode())
        exp     = payload.get("exp", 0)
        tok_type = payload.get("tokenConsumerType", "?")
        expired  = exp < _t.time()
        mins_left = int((exp - _t.time()) / 60) if not expired else 0
        return ORJSONResponse({
            "token_type":  tok_type,
            "expired":     expired,
            "expires_at":  _ts_to_ist(exp),
            "mins_left":   mins_left,
            "token_len":   len(token),
            "status":      "❌ EXPIRED" if expired else f"✅ Valid ({mins_left} min left)",
        })
    except Exception as e:
        return ORJSONResponse({"error": str(e), "status": "❌ Cannot decode token"})


@admin_router.post("/diagnostics/token/refresh")
async def diag_refresh_token(_: str = Depends(require_admin)):
    """Force fetch a fresh token via PIN+TOTP."""
    try:
        from pathlib import Path
        Path("/app/data/.dhan_token.json").unlink(missing_ok=True)
        Path("/app/data/.dhan_last_fetch.txt").unlink(missing_ok=True)
        from token_manager import get_access_token, _inject_token
        import features.ml_signals  # reset model loaded flag if needed
        token = await get_access_token()
        _inject_token(token)
        return ORJSONResponse({"status": "✅ Token refreshed", "token_len": len(token)})
    except Exception as e:
        return ORJSONResponse({"status": f"❌ Failed: {str(e)}"})


@admin_router.get("/diagnostics/ws")
async def diag_ws(_: str = Depends(require_admin)):
    """Check WebSocket feed status."""
    from api.websocket_manager import get_market_state
    from api.dhan_client import get_ws_client
    state = get_market_state()
    ws    = get_ws_client()
    return ORJSONResponse({
        "feed_running":    ws._running,
        "subscriptions":   len(ws._subscriptions),
        "nifty_ltp":       state.get_sync("ltp:13"),
        "tick_count":      state.get_sync("_tick_count"),
        "raw_packets":     state.get_sync("_raw_packet_count"),
        "last_tick_ts":    _ts_to_ist(state.get_sync("_last_tick_ts") or 0),
        "disconnect_code": state.get_sync("_ws_disconnect_code"),
        "disconnect_reason": state.get_sync("_ws_disconnect_reason"),
        "status": "✅ Receiving ticks" if state.get_sync("_tick_count") else "⚠️ No ticks yet",
    })


@admin_router.post("/diagnostics/ws/reconnect")
async def diag_ws_reconnect(_: str = Depends(require_admin)):
    """Force WS reconnect with fresh token."""
    try:
        from token_manager import _reconnect_ws, get_access_token, _inject_token
        token = await get_access_token()
        _inject_token(token)
        await _reconnect_ws()
        return ORJSONResponse({"status": "✅ WS reconnect triggered"})
    except Exception as e:
        return ORJSONResponse({"status": f"❌ Failed: {str(e)}"})


@admin_router.get("/diagnostics/ml")
async def diag_ml(_: str = Depends(require_admin)):
    """Check ML signals status."""
    from features.ml_signals import (
        is_model_available, _model_loaded, _last_inference_ts,
        _last_signals, _buffers, CONFIDENCE_THRESHOLD
    )
    import time as _t
    cache = get_cache()
    redis_sigs = await cache.get("ml:signals:NIFTY")
    return ORJSONResponse({
        "model_available":  is_model_available(),
        "model_loaded":     _model_loaded,
        "buffers":          len(_buffers),
        "last_inference":   _ts_to_ist(_last_inference_ts) if _last_inference_ts else "Never",
        "last_inference_ago": int(_t.time() - _last_inference_ts) if _last_inference_ts else -1,
        "signals_in_memory": len(_last_signals),
        "signals_in_redis":  len(redis_sigs) if redis_sigs else 0,
        "threshold":         CONFIDENCE_THRESHOLD,
        "top_signals":       (redis_sigs or [])[:5],
        "status": "✅ Active" if redis_sigs else "⚠️ No signals yet",
    })


@admin_router.post("/diagnostics/ml/force")
async def diag_ml_force(_: str = Depends(require_admin)):
    """Force ML inference now."""
    try:
        from features.ml_signals import run_ml_inference, update_signals, _buffers
        import features.ml_signals as ml
        cache = get_cache()
        chain = await cache.get("chain:NIFTY")
        if not chain:
            return ORJSONResponse({"status": "❌ No chain data in Redis"})
        spot = chain.get("spot_price", 0)
        ml._last_inference_ts = 0  # force
        sigs = run_ml_inference(chain, spot)
        update_signals(sigs)
        if sigs:
            await cache.set("ml:signals:NIFTY", sigs, ttl=900)
        return ORJSONResponse({
            "status": f"✅ Inference complete — {len(sigs)} signals",
            "signals": sigs[:5],
        })
    except Exception as e:
        return ORJSONResponse({"status": f"❌ Failed: {str(e)}"})
