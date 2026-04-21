import asyncio
import json
from typing import Any, Dict, Optional
import redis.asyncio as aioredis
from config import get_settings

settings = get_settings()

TTL_OPTION_CHAIN = 360      # 6 min — covers 5-symbol market-closed cycle (5 * 60s = 300s) + buffer
TTL_GREEKS = 360
TTL_IV_ANALYTICS = 360
TTL_MARKET_SUMMARY = 360
TTL_EXPIRIES = 600          # 10 min — expiries rarely change
TTL_HISTORICAL = 3600
TTL_SPOT = 5
TTL_IV_HISTORY = 86400      # 24h — persist IV history across restarts
TTL_GEX_HISTORY = 86400     # 24h — persist GEX time-series across restarts


# class RedisCache:
#     """Async Redis wrapper with JSON serialization and silent failover."""

#     def __init__(self):
#         self._client: Optional[aioredis.Redis] = None
#         self._available = False

#     async def connect(self):
#         """Attempt Redis connection; sets _available=False if unreachable."""
#         try:
#             url = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"
#             if settings.REDIS_PASSWORD:
#                 url = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"

#             self._client = aioredis.from_url(
#                 url,
#                 encoding="utf-8",
#                 decode_responses=True,
#                 socket_connect_timeout=3,
#                 socket_timeout=3,
#                 retry_on_timeout=False,
#             )
#             await self._client.ping()
#             self._available = True
#             logger.info(f"Redis connected at {settings.REDIS_HOST}:{settings.REDIS_PORT}")
#         except Exception as e:
#             self._available = False
#             logger.warning(f"Redis unavailable ({e}). Running with in-memory cache only.")

#     async def disconnect(self):
#         if self._client:
#             await self._client.aclose()

#     @property
#     def available(self) -> bool:
#         return self._available

#     async def get(self, key: str) -> Optional[Any]:
#         """Get a JSON-serialized value. Returns None on miss or error."""
#         if not self._available or not self._client:
#             return None
#         try:
#             raw = await self._client.get(key)
#             if raw is None:
#                 return None
#             return json.loads(raw)
#         except Exception as e:
#             logger.debug(f"Redis GET error for {key}: {e}")
#             return None

#     async def set(self, key: str, value: Any, ttl: int = 60) -> bool:
#         """Serialize and store a value with TTL. Returns False on error."""
#         if not self._available or not self._client:
#             return False
#         try:
#             await self._client.setex(key, ttl, json.dumps(value, default=str))
#             return True
#         except Exception as e:
#             logger.debug(f"Redis SET error for {key}: {e}")
#             return False

#     async def delete(self, key: str) -> bool:
#         if not self._available or not self._client:
#             return False
#         try:
#             await self._client.delete(key)
#             return True
#         except Exception:
#             return False

#     async def exists(self, key: str) -> bool:
#         if not self._available or not self._client:
#             return False
#         try:
#             return bool(await self._client.exists(key))
#         except Exception:
#             return False

#     async def keys(self, pattern: str = "*") -> list:
#         if not self._available or not self._client:
#             return []
#         try:
#             return await self._client.keys(pattern)
#         except Exception:
#             return []

#     # ── Pub/Sub helpers ───────────────────────────────────────────────────────

#     async def publish(self, channel: str, message: Any) -> int:
#         """Publish a message to a Redis channel."""
#         if not self._available or not self._client:
#             return 0
#         try:
#             return await self._client.publish(channel, json.dumps(message, default=str))
#         except Exception:
#             return 0

#     # ── Composite helpers ─────────────────────────────────────────────────────

#     async def get_or_set(self, key: str, factory, ttl: int = 60) -> Any:
#         """
#         Get from cache; if miss, call factory() to produce value, cache it, return.
#         """
#         cached = await self.get(key)
#         if cached is not None:
#             return cached
#         value = await factory() if asyncio.iscoroutinefunction(factory) else factory()
#         if value is not None:
#             await self.set(key, value, ttl)
#         return value

#     # ── Cache key builders ────────────────────────────────────────────────────

#     @staticmethod
#     def key_chain(symbol: str, expiry: str = "") -> str:
#         return f"chain:{symbol}:{expiry}" if expiry else f"chain:{symbol}"

#     @staticmethod
#     def key_exposure(symbol: str) -> str:
#         return f"exposure:{symbol}"

#     @staticmethod
#     def key_iv(symbol: str) -> str:
#         return f"iv:{symbol}"

#     @staticmethod
#     def key_summary(symbol: str) -> str:
#         return f"summary:{symbol}"

#     @staticmethod
#     def key_spot(symbol: str) -> str:
#         return f"spot:{symbol}"

#     @staticmethod
#     def key_expiries(symbol: str) -> str:
#         return f"expiries:{symbol}"

#     @staticmethod
#     def key_historical(security_id: str, interval: int) -> str:
#         return f"hist:{security_id}:{interval}"


# # ─── Singleton ────────────────────────────────────────────────────────────────



class RedisCache:
    """Async Redis wrapper — JSON serialization, silent failover, stampede protection."""

    def __init__(self):
        self._client: Optional[aioredis.Redis] = None
        self._available = False
        self._locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def _get_lock(self, key: str) -> asyncio.Lock:
        async with self._global_lock:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            return self._locks[key]

    async def connect(self):
        try:
            url = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"
            if settings.REDIS_PASSWORD:
                url = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"
            self._client = aioredis.from_url(
                url, encoding="utf-8", decode_responses=True,
                socket_connect_timeout=3, socket_timeout=3, retry_on_timeout=False,
            )
            await self._client.ping()
            self._available = True
        except Exception:
            self._available = False

    async def disconnect(self):
        if self._client:
            await self._client.aclose()

    @property
    def available(self) -> bool:
        return self._available

    async def get(self, key: str) -> Optional[Any]:
        if not self._available or not self._client:
            return None
        try:
            raw = await asyncio.wait_for(self._client.get(key), timeout=3.0)
            return json.loads(raw) if raw is not None else None
        except asyncio.TimeoutError:
            self._available = False
            asyncio.create_task(self.connect())
            return None
        except Exception:
            return None

    async def set(self, key: str, value: Any, ttl: int = 60) -> bool:
        if not self._available or not self._client:
            return False
        try:
            await asyncio.wait_for(
                self._client.setex(key, ttl, json.dumps(value, default=str)),
                timeout=3.0
            )
            return True
        except asyncio.TimeoutError:
            # Connection hung — mark unavailable and reconnect in background
            self._available = False
            asyncio.create_task(self.connect())
            return False
        except Exception:
            return False

    async def delete(self, key: str) -> bool:
        if not self._available or not self._client:
            return False
        try:
            await self._client.delete(key)
            return True
        except Exception:
            return False

    async def exists(self, key: str) -> bool:
        if not self._available or not self._client:
            return False
        try:
            return bool(await self._client.exists(key))
        except Exception:
            return False

    async def keys(self, pattern: str = "*") -> list:
        if not self._available or not self._client:
            return []
        try:
            return await self._client.keys(pattern)
        except Exception:
            return []

    async def publish(self, channel: str, message: Any) -> int:
        if not self._available or not self._client:
            return 0
        try:
            return await self._client.publish(channel, json.dumps(message, default=str))
        except Exception:
            return 0

    # ── Time-series helpers (Redis List — LPUSH + LTRIM) ─────────────────────

    async def ts_push(self, key: str, value: Any, maxlen: int = 500, ttl: int = 86400) -> bool:
        """Push a value to a Redis list time-series. Trims to maxlen. Sets TTL."""
        if not self._available or not self._client:
            return False
        try:
            serialized = json.dumps(value, default=str)
            pipe = self._client.pipeline()
            pipe.rpush(key, serialized)
            pipe.ltrim(key, -maxlen, -1)
            pipe.expire(key, ttl)
            # Run in thread pool with timeout — prevents blocking event loop on broken connections
            loop = asyncio.get_event_loop()
            await asyncio.wait_for(
                loop.run_in_executor(None, lambda: None),  # yield to event loop first
                timeout=0.001
            )
            await asyncio.wait_for(pipe.execute(), timeout=3.0)
            return True
        except (asyncio.TimeoutError, Exception):
            return False

    async def ts_get_all(self, key: str) -> list:
        """Get all values from a Redis list time-series."""
        if not self._available or not self._client:
            return []
        try:
            raw_list = await self._client.lrange(key, 0, -1)
            return [json.loads(r) for r in raw_list]
        except Exception:
            return []

    async def ts_get_last(self, key: str, n: int = 1) -> list:
        """Get last n values from a Redis list time-series."""
        if not self._available or not self._client:
            return []
        try:
            raw_list = await self._client.lrange(key, -n, -1)
            return [json.loads(r) for r in raw_list]
        except Exception:
            return []

    # ── Stampede-safe get_or_set ──────────────────────────────────────────────

    async def get_or_set(self, key: str, factory, ttl: int = 60) -> Any:
        cached = await self.get(key)
        if cached is not None:
            return cached
        lock = await self._get_lock(key)
        async with lock:
            cached = await self.get(key)
            if cached is not None:
                return cached
            value = await factory() if asyncio.iscoroutinefunction(factory) else factory()
            if value is not None and value != {} and value != []:
                await self.set(key, value, ttl)
            return value

    # ── Cache key builders ────────────────────────────────────────────────────

    @staticmethod
    def key_chain(symbol: str, expiry: str = "") -> str:
        return f"chain:{symbol}:{expiry}" if expiry else f"chain:{symbol}"

    @staticmethod
    def key_exposure(symbol: str) -> str:
        return f"exposure:{symbol}"

    @staticmethod
    def key_iv(symbol: str) -> str:
        return f"iv:{symbol}"

    @staticmethod
    def key_summary(symbol: str) -> str:
        return f"summary:{symbol}"

    @staticmethod
    def key_spot(symbol: str) -> str:
        return f"spot:{symbol}"

    @staticmethod
    def key_expiries(symbol: str) -> str:
        return f"expiries:{symbol}"

    @staticmethod
    def key_historical(security_id: str, interval: int) -> str:
        return f"hist:{security_id}:{interval}"

    @staticmethod
    def key_iv_history(symbol: str) -> str:
        return f"iv_history:{symbol}"

    @staticmethod
    def key_gex_history(symbol: str) -> str:
        return f"gex_history:{symbol}"

    @staticmethod
    def key_oi_history(symbol: str) -> str:
        return f"oi_history:{symbol}"


_cache: Optional[RedisCache] = None


def get_cache() -> RedisCache:
    global _cache
    if _cache is None:
        _cache = RedisCache()
    return _cache
