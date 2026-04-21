"""Retry fetching missing stocks."""
import asyncio
from stocks.database import get_candle_count, init_db
from stocks.universe import STOCK_UNIVERSE
from stocks.stock_fetcher import fetch_full_history, FETCH_DELAY
from core.redis_cache import get_cache


async def run():
    init_db()
    cache = get_cache()
    await cache.connect()

    missing = [s for s in STOCK_UNIVERSE if get_candle_count(s) < 252]
    print(f"Retrying {len(missing)} missing stocks: {missing}")

    for sym in missing:
        try:
            count = await fetch_full_history(sym)
            print(f"  {sym}: {count} candles")
        except Exception as e:
            print(f"  {sym}: ERROR - {e}")
        await asyncio.sleep(FETCH_DELAY)

    # Final count
    still_missing = [s for s in STOCK_UNIVERSE if get_candle_count(s) < 252]
    print(f"\nDone. Still missing: {len(still_missing)}: {still_missing}")


asyncio.run(run())
