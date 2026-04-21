"""One-shot script to warm Redis from existing DB data."""
import asyncio
from stocks.scheduler import _recompute_from_db, _fetch_nifty_candles
from stocks.universe import STOCK_UNIVERSE
from stocks.database import init_db
from core.redis_cache import get_cache


async def run():
    # Must connect Redis first
    cache = get_cache()
    await cache.connect()
    print(f"Redis connected: {cache.available}")

    init_db()
    print("Fetching NIFTY candles...")
    nifty = await _fetch_nifty_candles()
    print(f"NIFTY candles: {len(nifty)}")
    symbols = list(STOCK_UNIVERSE.keys())
    print(f"Computing {len(symbols)} symbols from DB...")
    summary = await _recompute_from_db(cache, symbols, nifty)
    stocks = summary.get("all_stocks") or summary.get("top_stocks", [])
    print(f"Done! {len(stocks)} stocks, {summary['buy_signals']} BUY signals")
    if stocks:
        s = stocks[0]
        print(f"Sample: {s.get('symbol')} {s.get('signal')} score={s.get('score')} risk={s.get('risk_level')} spark={len(s.get('sparkline', []))}")


asyncio.run(run())
