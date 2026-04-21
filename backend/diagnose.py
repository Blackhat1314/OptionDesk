"""Diagnose spot price and option chain refresh issues."""
import asyncio, time
from core.redis_cache import get_cache
from api.websocket_manager import get_market_state


async def check():
    cache = get_cache()
    await cache.connect()
    state = get_market_state()

    print("=== WEBSOCKET TICK CACHE ===")
    ltp_13 = state.get_sync("ltp:13")
    print(f"ltp:13 (NIFTY from WS) = {ltp_13}")
    # Check all index ticks
    for sid, sym in [("13","NIFTY"),("25","BANKNIFTY"),("27","FINNIFTY"),("442","MIDCPNIFTY"),("51","SENSEX")]:
        v = state.get_sync(f"ltp:{sid}")
        print(f"  ltp:{sid} ({sym}) = {v}")

    print()
    print("=== OPTION CHAIN IN REDIS ===")
    chain = await cache.get("chain:NIFTY")
    if chain:
        ts   = chain.get("timestamp", 0)
        age  = round(time.time() - ts, 1)
        spot = chain.get("spot_price", 0)
        rows = len(chain.get("rows", []))
        print(f"Age: {age}s | Spot: {spot} | Rows: {rows}")
        if rows > 0:
            r  = chain["rows"][0]
            ce = r.get("call", {})
            pe = r.get("put", {})
            print(f"First row: strike={r.get('strike')} CE_ltp={ce.get('ltp')} PE_ltp={pe.get('ltp')}")
    else:
        print("NO CHAIN IN REDIS")

    print()
    print("=== CHAIN REFRESH RATE (3 samples x 3s) ===")
    prev_ts = 0
    for i in range(3):
        chain = await cache.get("chain:NIFTY")
        ts    = chain.get("timestamp", 0) if chain else 0
        age   = round(time.time() - ts, 1)
        spot  = chain.get("spot_price", 0) if chain else 0
        delta = round(ts - prev_ts, 2) if prev_ts > 0 else 0
        print(f"  [{i+1}] age={age}s spot={spot} delta_since_last={delta}s")
        prev_ts = ts
        if i < 2:
            await asyncio.sleep(3)

    print()
    print("=== PIPELINE STATUS ===")
    status = await cache.get("stocks:pipeline:status")
    print(f"Pipeline: {status}")

    print()
    print("=== WEBSOCKET CONNECTIONS ===")
    from api.websocket_manager import get_connection_manager
    mgr = get_connection_manager()
    print(f"Active WS connections: {mgr.get_connection_count()}")

    print()
    print("=== DHAN WS CLIENT STATUS ===")
    from api.dhan_client import get_ws_client
    ws = get_ws_client()
    print(f"WS running: {ws._running}")
    print(f"WS subscriptions: {len(ws._subscriptions)}")
    print(f"WS callbacks: {len(ws._callbacks)}")


asyncio.run(check())
