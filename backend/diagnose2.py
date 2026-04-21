"""Check chain refresh via HTTP API and check if market is open."""
import urllib.request, json, time
from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")
now = datetime.now(IST)
mins = now.hour * 60 + now.minute
market_open = now.weekday() < 5 and 9 * 60 + 15 <= mins <= 15 * 60 + 30

print(f"Current IST time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Market open: {market_open}")
print(f"Day of week: {now.strftime('%A')}")
print()

# Check chain via HTTP (goes through FastAPI in-memory state)
print("=== CHAIN VIA HTTP API (3 samples x 3s) ===")
prev_ts = 0
for i in range(3):
    try:
        r = urllib.request.urlopen("http://localhost:8000/api/health", timeout=3)
        health = json.loads(r.read())
        print(f"  [{i+1}] health: {health}")
    except Exception as e:
        print(f"  [{i+1}] health error: {e}")
    if i < 2:
        time.sleep(3)

print()
# Check if the background task is actually running by looking at chain timestamps
print("=== CHECKING CHAIN TIMESTAMP CHANGES ===")
import asyncio
from core.redis_cache import get_cache

async def check_ts():
    cache = get_cache()
    await cache.connect()
    timestamps = []
    for i in range(4):
        chain = await cache.get("chain:NIFTY")
        ts = chain.get("timestamp", 0) if chain else 0
        spot = chain.get("spot_price", 0) if chain else 0
        timestamps.append(ts)
        print(f"  [{i+1}] ts={ts:.1f} spot={spot} age={round(time.time()-ts,1)}s")
        if i < 3:
            await asyncio.sleep(3)
    
    # Check if timestamps changed
    unique = len(set(round(t, 0) for t in timestamps if t > 0))
    if unique == 1:
        print(f"\n  ❌ CHAIN NOT REFRESHING — same timestamp across 12s")
        print(f"  → Background task may be stuck or market is closed")
    else:
        print(f"\n  ✓ Chain refreshed {unique-1} times in 12s")

asyncio.run(check_ts())
