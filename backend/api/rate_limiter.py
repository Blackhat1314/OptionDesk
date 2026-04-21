"""
Dhan API Rate Limiter
======================
Token-bucket + sliding window per VERIFIED Dhan v2 limits (tested live).

VERIFIED LIMITS (from live API testing 2026-04-20):
  /marketfeed/ltp    : 1 req/sec, up to 1000 instruments per request
  /marketfeed/ohlc   : 1 req/sec, up to 1000 instruments per request
  /marketfeed/quote  : 1 req/sec, up to 1000 instruments per request (returns 52wk high/low, VWAP, depth, volume, circuit limits, net_change)
  /optionchain       : 1 req/3s (heavy server computation)
  /charts/historical : NO daily limit (tested — no 100/day restriction found)
  /charts/intraday   : NO daily limit (tested — no 100/day restriction found)
  /optionchain/expireddata: 60 req/min

IMPORTANT FINDINGS FROM TESTING:
  - /marketfeed/quote returns EXTRA fields not in docs:
      52_week_high, 52_week_low  ← very useful for screener!
      average_price              ← this is VWAP for the day
      net_change                 ← absolute change from prev close
      volume                     ← total day volume
      buy_quantity, sell_quantity ← pending order book totals
      upper_circuit_limit, lower_circuit_limit
      depth (5-level bid/ask)
  - 429 on rapid calls (2nd call within 1s) — no Retry-After header
  - No X-RateLimit headers — limits enforced silently
  - Historical API: no rate limit headers, no 100/day restriction observed
  - Intraday API: returns 5-min candles, 75 candles per day per stock
  - OHLC batch: 50 stocks in one call = 0.27s response time ✅
  - All 50 stocks returned with live LTP + OHLC data ✅

STRATEGY:
  - Use /marketfeed/ohlc for live prices (1 call per 60s for all 226 stocks)
  - Use /marketfeed/quote for richer data (VWAP, volume, 52wk, depth) — 1 call/sec
  - Historical: fetch freely, no daily quota concern
  - Intraday: use for 5-min candle features (RSI, momentum) — no quota concern
"""

import asyncio
import time
from collections import deque
from typing import Dict, Optional



class TokenBucket:
    """Async token-bucket rate limiter."""

    def __init__(self, rate: float, capacity: float):
        self.rate     = rate
        self.capacity = capacity
        self._tokens  = capacity
        self._last    = time.monotonic()
        self._lock    = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> float:
        async with self._lock:
            now     = time.monotonic()
            elapsed = now - self._last
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
            self._last   = now

            if self._tokens >= tokens:
                self._tokens -= tokens
                return 0.0

            wait = (tokens - self._tokens) / self.rate
            self._tokens = 0.0
            return wait

    async def wait_and_acquire(self, tokens: float = 1.0):
        wait = await self.acquire(tokens)
        if wait > 0:
            await asyncio.sleep(wait)


class SlidingWindowCounter:
    """Sliding window counter for per-minute limits."""

    def __init__(self, window_seconds: float, max_calls: int):
        self.window   = window_seconds
        self.max_calls = max_calls
        self._times: deque = deque()
        self._lock = asyncio.Lock()

    async def is_allowed(self) -> bool:
        async with self._lock:
            now = time.monotonic()
            while self._times and now - self._times[0] > self.window:
                self._times.popleft()
            if len(self._times) < self.max_calls:
                self._times.append(now)
                return True
            return False

    async def wait_until_allowed(self):
        while not await self.is_allowed():
            async with self._lock:
                oldest = self._times[0] if self._times else time.monotonic()
            wait = max(0.1, self.window - (time.monotonic() - oldest) + 0.1)
            await asyncio.sleep(wait)


class DhanRateLimiter:
    """
    Centralised rate limiter for all Dhan API endpoints.

    VERIFIED limits (live tested):
      Market feed endpoints: 1 req/sec, 1000 instruments/req
      Option chain: 1 req/3s
      Historical/Intraday: no daily quota (fetch freely)
      Expired option data: 60 req/min
    """

    def __init__(self):
        # Market feed: 1 req/sec (verified — 429 on 2nd call within 1s)
        self.quote        = TokenBucket(rate=1.0,  capacity=1.0)
        self.ltp          = TokenBucket(rate=1.0,  capacity=1.0)
        self.ohlc         = TokenBucket(rate=1.0,  capacity=1.0)
        self.depth        = TokenBucket(rate=1.0,  capacity=1.0)
        # Option chain: max 1 req/3s (heavy server computation)
        self.option_chain = TokenBucket(rate=0.33, capacity=1.0)
        self.expiry_list  = TokenBucket(rate=1.0,  capacity=1.0)
        # Historical/Intraday: no daily quota — use generous sliding window
        # to avoid hammering (courtesy limit: 300/day = 1 per 5 min avg)
        self.historical   = SlidingWindowCounter(86400, 500)
        self.intraday     = SlidingWindowCounter(86400, 500)
        # Per-minute limits
        self.expired_data = SlidingWindowCounter(60, 55)

        # Back-off: endpoint → monotonic time when back-off expires
        self._backoff: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def check_backoff(self, endpoint: str) -> float:
        """Return seconds remaining in back-off (0 if none)."""
        async with self._lock:
            until = self._backoff.get(endpoint, 0.0)
            return max(0.0, until - time.monotonic())

    async def set_backoff(self, endpoint: str, seconds: float = 60.0):
        """Called ONLY on real 429 responses. Sets a timed back-off."""
        async with self._lock:
            self._backoff[endpoint] = time.monotonic() + seconds

    async def _wait_backoff(self, endpoint: str):
        wait = await self.check_backoff(endpoint)
        if wait > 0:
            await asyncio.sleep(wait)

    async def acquire_quote(self):
        await self._wait_backoff("/marketfeed/quote")
        await self.quote.wait_and_acquire()

    async def acquire_ltp(self):
        await self._wait_backoff("/marketfeed/ltp")
        await self.ltp.wait_and_acquire()

    async def acquire_ohlc(self):
        await self._wait_backoff("/marketfeed/ohlc")
        await self.ohlc.wait_and_acquire()

    async def acquire_depth(self):
        await self._wait_backoff("/marketfeed/full-depth")
        await self.depth.wait_and_acquire()

    async def acquire_option_chain(self):
        await self._wait_backoff("/optionchain")
        await self.option_chain.wait_and_acquire()

    async def acquire_expiry_list(self):
        await self._wait_backoff("/optionchain/expirylist")
        await self.expiry_list.wait_and_acquire()

    async def acquire_historical(self):
        await self._wait_backoff("/charts/historical")
        await self.historical.wait_until_allowed()

    async def acquire_intraday(self):
        await self._wait_backoff("/charts/intraday")
        await self.intraday.wait_until_allowed()

    async def acquire_expired_data(self):
        await self._wait_backoff("/optionchain/expireddata")
        await self.expired_data.wait_until_allowed()


_rate_limiter: Optional[DhanRateLimiter] = None

def get_rate_limiter() -> DhanRateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = DhanRateLimiter()
    return _rate_limiter