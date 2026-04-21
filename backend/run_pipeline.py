"""Trigger full stock pipeline — fetches new stocks and recomputes all."""
import asyncio
from stocks.scheduler import run_stock_pipeline
from stocks.database import init_db
from core.redis_cache import get_cache


async def run():
    cache = get_cache()
    await cache.connect()
    print("Redis connected:", cache.available)
    init_db()
    print("Starting pipeline for all stocks...")
    print("Will fetch missing stocks from Dhan API (~3-4 min for new ones)")
    summary = await run_stock_pipeline(force_fetch=False)
    total = summary.get("total_stocks", 0)
    buys  = summary.get("buy_signals", 0)
    picks = summary.get("top_picks", [])
    print(f"Done: {total} stocks computed, {buys} BUY signals")
    if picks:
        print("Top picks:")
        for p in picks:
            print(f"  #{p['rank']} {p['symbol']} RS={p['rs']:.2f} prob={p['prob_up']:.0f}%")


asyncio.run(run())
