"""Check current state of all stocks."""
import asyncio
from core.redis_cache import get_cache
from stocks.database import get_db_stats, get_candle_count, init_db
from stocks.universe import STOCK_UNIVERSE


async def check():
    cache = get_cache()
    await cache.connect()
    init_db()

    stats = get_db_stats()
    print("DB Stats:", stats)

    missing = [s for s in STOCK_UNIVERSE if get_candle_count(s) < 252]
    print(f"Missing candles (<252): {len(missing)}")
    if missing:
        print("Missing:", missing[:15])

    summary = await cache.get("stocks:screener:summary")
    if summary:
        all_stocks = summary.get("all_stocks", [])
        print(f"\nRedis all_stocks: {len(all_stocks)}")

        # Check a few new stocks
        check_syms = ["BLUESTARCO", "DALBHARAT", "COFORGE", "ADANIGREEN",
                      "NATIONALUM", "HINDCOPPER", "RATNAMANI", "JKCEMENT"]
        for sym in check_syms:
            s = next((x for x in all_stocks if x.get("symbol") == sym), None)
            if s:
                mc = s.get("monte_carlo", {})
                bt = s.get("backtest", {})
                print(f"  {sym}: score={s.get('score')} signal={s.get('signal')} "
                      f"mc_prob={mc.get('prob_up') if mc else 'NONE'} "
                      f"bt_trades={bt.get('total_trades') if bt else 'NONE'} "
                      f"spark={len(s.get('sparkline', []))}")
            else:
                print(f"  {sym}: NOT IN REDIS")
    else:
        print("No Redis summary found")


asyncio.run(check())
