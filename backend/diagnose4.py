"""Simulate the exact refresh loop to find the crash."""
import asyncio, time, traceback
from api.dhan_client import get_dhan_client
from api.websocket_manager import get_market_state, get_connection_manager
from core.redis_cache import get_cache
from core.analytics_processor import process_option_chain, compute_greeks_exposure, compute_iv_analytics, compute_market_summary
from core.redis_cache import TTL_OPTION_CHAIN, TTL_GREEKS, TTL_IV_ANALYTICS, TTL_MARKET_SUMMARY, TTL_EXPIRIES, TTL_IV_HISTORY, TTL_GEX_HISTORY
from features.regime import push_price
from features.gex import record_exposure_snapshot
from features.oi_flow import ingest_chain_for_oi
from features.vwap import push_vwap_tick, get_vwap_engine
from features.volatility import get_vol_surface
from services.alert_engine import get_alert_engine
from api.intelligence_routes import record_intelligence_snapshot


async def simulate_one_cycle():
    """Run exactly one refresh cycle with full error reporting."""
    dhan  = get_dhan_client()
    state = get_market_state()
    cache = get_cache()
    await cache.connect()

    print("Step 1: Get spot from WS cache...")
    spot = state.get_sync("ltp:13") or 0.0
    print(f"  WS spot = {spot}")

    if spot <= 0:
        print("  WS empty, fetching via LTP API...")
        ltp_resp = await dhan.get_ltp([13], "IDX_I")
        seg_data = ltp_resp.get("data", {}).get("IDX_I", {})
        q = seg_data.get("13") or seg_data.get(13) or {}
        spot = float(q.get("last_price") or 0)
        print(f"  API spot = {spot}")

    print(f"\nStep 2: Get expiry...")
    expiries = await dhan.get_option_expiries("NIFTY")
    expiry = expiries[0] if expiries else None
    print(f"  expiry = {expiry}")

    print(f"\nStep 3: Fetch option chain...")
    raw_chain = await dhan.get_option_chain("NIFTY", expiry)
    oc = raw_chain.get("data", {}).get("oc", {}) if raw_chain else {}
    print(f"  strikes = {len(oc)}")

    print(f"\nStep 4: process_option_chain...")
    chain = process_option_chain(raw_chain, "NIFTY", expiry, spot)
    print(f"  rows = {len(chain.rows)}")

    print(f"\nStep 5: compute analytics...")
    exposure     = compute_greeks_exposure(chain, "NIFTY")
    iv_analytics = compute_iv_analytics(chain, "NIFTY")
    summary      = compute_market_summary(chain, "NIFTY")
    print(f"  exposure OK, iv OK, summary OK")

    print(f"\nStep 6: dict conversion...")
    chain_dict    = chain.dict()
    exposure_dict = exposure.dict()
    iv_dict       = iv_analytics.dict()
    summary_dict  = summary.dict()
    print(f"  chain_dict keys: {list(chain_dict.keys())[:5]}")

    print(f"\nStep 7: write to state + Redis...")
    await state.set("chain:NIFTY",    chain_dict)
    await state.set("exposure:NIFTY", exposure_dict)
    await state.set("iv:NIFTY",       iv_dict)
    await state.set("summary:NIFTY",  summary_dict)
    await cache.set(cache.key_chain("NIFTY"),    chain_dict,    TTL_OPTION_CHAIN)
    await cache.set(cache.key_exposure("NIFTY"), exposure_dict, TTL_GREEKS)
    await cache.set(cache.key_iv("NIFTY"),       iv_dict,       TTL_IV_ANALYTICS)
    await cache.set(cache.key_summary("NIFTY"),  summary_dict,  TTL_MARKET_SUMMARY)
    print(f"  Written to Redis OK")

    print(f"\nStep 8: analytics engines...")
    push_price("NIFTY", spot)
    push_vwap_tick("NIFTY", spot, 100)
    record_exposure_snapshot("NIFTY", exposure_dict)
    ingest_chain_for_oi("NIFTY", chain_dict.get("rows", []), spot)
    print(f"  Analytics OK")

    print(f"\nStep 9: record_intelligence_snapshot...")
    try:
        from api.intelligence_routes import record_intelligence_snapshot as ris
        ris("NIFTY", exposure_dict, iv_dict, chain_dict)
        print(f"  Intelligence OK")
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
    print(f"\nStep 10: broadcast...")
    manager = get_connection_manager()
    await manager.broadcast({"type": "option_chain_update", "symbol": "NIFTY", "data": chain_dict, "timestamp": time.time()})
    print(f"  Broadcast OK (connections={manager.get_connection_count()})")

    print(f"\n✓ Full cycle completed successfully")
    await dhan.close()


try:
    asyncio.run(simulate_one_cycle())
except Exception as e:
    print(f"\n❌ CRASH: {type(e).__name__}: {e}")
    traceback.print_exc()
