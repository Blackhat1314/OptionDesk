"""
Quant Data Worker
==================
Background task that fetches OHLCV for all universe stocks every 5s.
Uses Dhan /marketfeed/quote (batch, 1 req/sec, max 1000 instruments).
Stores in Redis:
  stock:{symbol}:latest  -> {price, open, high, low, close, volume, ts}
  stock:{symbol}:history -> list of last 100 candles (LPUSH + LTRIM)

STRICT: Never called from API endpoints. Only runs as background task.
"""

import asyncio
import json
import time
from typing import Dict, List

from api.dhan_client import get_dhan_client
from core.redis_cache import get_cache
from quant.universe import UNIVERSE, UNIVERSE_SEGMENT
from quant.instrument_loader import load_instrument_ids

FETCH_INTERVAL   = 5      # seconds between fetches
HISTORY_MAXLEN   = 100    # rolling candle history per stock
BATCH_SIZE       = 200    # Dhan allows 1000 per call; use 200 for safety
TTL_LATEST       = 30     # 30s TTL for latest price
TTL_HISTORY      = 3600   # 1h TTL for history


async def _fetch_batch(dhan, sids: List[int], segment: str) -> Dict[int, Dict]:
    """Fetch quote for a batch of security IDs. Returns {sid: quote_dict}."""
    try:
        resp = await dhan._post("/marketfeed/quote", {segment: sids})
        seg_data = resp.get("data", {}).get(segment, {})
        result = {}
        for sid in sids:
            q = seg_data.get(str(sid)) or seg_data.get(sid) or {}
            if q:
                result[int(sid)] = q
        return result
    except Exception:
        return {}


async def run_quant_data_worker():
    """
    Main loop. Runs forever, fetching all universe stocks every FETCH_INTERVAL seconds.
    Writes to Redis. Never raises — silently continues on error.
    """
    dhan  = get_dhan_client()
    cache = get_cache()

    # Load correct security IDs from Dhan instrument master
    universe_ids = await load_instrument_ids()

    # Build reverse map: security_id -> symbol
    id_to_sym = {v: k for k, v in universe_ids.items()}
    all_sids  = list(set(universe_ids.values()))  # deduplicate

    while True:
        try:
            ts_start = time.time()

            # Fetch in batches to stay within Dhan limits
            all_quotes: Dict[int, Dict] = {}
            for i in range(0, len(all_sids), BATCH_SIZE):
                batch = all_sids[i:i + BATCH_SIZE]
                quotes = await _fetch_batch(dhan, batch, UNIVERSE_SEGMENT)
                all_quotes.update(quotes)
                if i + BATCH_SIZE < len(all_sids):
                    await asyncio.sleep(1.1)  # respect 1 req/sec rate limit

            # Write to Redis
            pipe_ops = []
            for sid, q in all_quotes.items():
                sym = id_to_sym.get(sid)
                if not sym:
                    continue

                price  = float(q.get("last_price") or 0)
                open_  = float((q.get("ohlc") or {}).get("open")  or price)
                high   = float((q.get("ohlc") or {}).get("high")  or price)
                low    = float((q.get("ohlc") or {}).get("low")   or price)
                close  = float((q.get("ohlc") or {}).get("close") or price)
                volume = int(q.get("volume") or 0)

                if price <= 0:
                    continue

                latest = {
                    "symbol": sym,
                    "price":  price,
                    "open":   open_,
                    "high":   high,
                    "low":    low,
                    "close":  close,
                    "volume": volume,
                    "ts":     time.time(),
                }

                # Write latest
                await cache.set(f"stock:{sym}:latest", latest, TTL_LATEST)

                # Append to history (Redis list)
                await cache.ts_push(
                    f"stock:{sym}:history",
                    latest,
                    maxlen=HISTORY_MAXLEN,
                    ttl=TTL_HISTORY,
                )

            # Sleep for remainder of interval
            elapsed = time.time() - ts_start
            sleep_for = max(0.1, FETCH_INTERVAL - elapsed)
            await asyncio.sleep(sleep_for)

        except Exception:
            await asyncio.sleep(FETCH_INTERVAL)
