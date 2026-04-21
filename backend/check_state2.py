"""Check in-memory state via HTTP API."""
import urllib.request, json, time

# Check the quote endpoint (requires auth token)
# Instead, check via a custom debug endpoint we'll add
# For now, check Redis which is updated by the refresh loop

import asyncio
from core.redis_cache import get_cache


async def check():
    cache = get_cache()
    await cache.connect()

    # Check summary in Redis
    summary = await cache.get("summary:NIFTY")
    if summary:
        print("Summary from Redis:")
        print(f"  spot_price: {summary.get('spot_price')}")
        print(f"  day_change: {summary.get('day_change')}")
        print(f"  day_change_pct: {summary.get('day_change_pct')}")
        print(f"  atm_iv: {summary.get('atm_iv')}")
        ts = summary.get('timestamp', 0)
        print(f"  age: {round(time.time() - ts, 1)}s")
    else:
        print("No summary in Redis")

    # Check chain
    chain = await cache.get("chain:NIFTY")
    if chain:
        print(f"\nChain spot_price: {chain.get('spot_price')}")
        print(f"Chain age: {round(time.time() - chain.get('timestamp', 0), 1)}s")


asyncio.run(check())
