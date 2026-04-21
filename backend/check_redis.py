import asyncio, json
from core.redis_cache import get_cache


async def check():
    cache = get_cache()
    await cache.connect()
    print("Redis connected:", cache.available)
    summary = await cache.get("stocks:screener:summary")
    if summary:
        print("Keys in summary:", list(summary.keys()))
        print("all_stocks count:", len(summary.get("all_stocks", [])))
        print("top_stocks count:", len(summary.get("top_stocks", [])))
        stocks = summary.get("all_stocks") or summary.get("top_stocks", [])
        if stocks:
            s = stocks[0]
            print("First stock keys:", list(s.keys()))
            print("risk_level:", s.get("risk_level"))
            print("sparkline len:", len(s.get("sparkline", [])))
            print("confidence:", s.get("confidence"))
    else:
        print("SUMMARY: NONE")


asyncio.run(check())
