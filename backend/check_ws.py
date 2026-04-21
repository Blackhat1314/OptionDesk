"""Check WebSocket status in the running FastAPI process via shared state."""
import asyncio, time
from core.redis_cache import get_cache
from api.websocket_manager import get_market_state


async def check():
    cache = get_cache()
    await cache.connect()
    state = get_market_state()

    print("=== WEBSOCKET TICK CACHE (in-memory state) ===")
    for sid, sym in [("13","NIFTY"),("25","BANKNIFTY"),("27","FINNIFTY")]:
        v = state.get_sync(f"ltp:{sid}")
        print(f"  ltp:{sid} ({sym}) = {v}")

    print()
    print("=== DHAN WS CLIENT (this process) ===")
    from api.dhan_client import get_ws_client
    ws = get_ws_client()
    print(f"  running:       {ws._running}")
    print(f"  subscriptions: {len(ws._subscriptions)}")
    print(f"  callbacks:     {len(ws._callbacks)}")
    print(f"  ws object:     {ws._ws}")

    print()
    print("=== CHAIN SPOT vs TICK CACHE ===")
    chain = await cache.get("chain:NIFTY")
    if chain:
        chain_spot = chain.get("spot_price", 0)
        tick_spot  = state.get_sync("ltp:13")
        ts         = chain.get("timestamp", 0)
        age        = round(time.time() - ts, 1)
        print(f"  chain spot:  {chain_spot} (age {age}s)")
        print(f"  tick spot:   {tick_spot}")
        print(f"  match:       {chain_spot == tick_spot}")
    else:
        print("  No chain in Redis")

    print()
    print("=== FRONTEND WS CONNECTIONS ===")
    from api.websocket_manager import get_connection_manager
    mgr = get_connection_manager()
    print(f"  Active connections: {mgr.get_connection_count()}")


asyncio.run(check())
