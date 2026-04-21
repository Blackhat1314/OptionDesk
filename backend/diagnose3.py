"""Test the option chain fetch directly to find the error."""
import asyncio, time
from api.dhan_client import get_dhan_client
from core.analytics_processor import process_option_chain, compute_greeks_exposure, compute_iv_analytics, compute_market_summary
from api.websocket_manager import get_market_state


async def test():
    dhan  = get_dhan_client()
    state = get_market_state()

    print("1. Testing LTP fetch...")
    try:
        ltp_resp = await dhan.get_ltp([13], "IDX_I")
        seg_data = ltp_resp.get("data", {}).get("IDX_I", {})
        q = seg_data.get("13") or seg_data.get(13) or {}
        spot = float(q.get("last_price") or 0)
        print(f"   NIFTY spot = {spot}")
    except Exception as e:
        print(f"   ERROR: {type(e).__name__}: {e}")
        spot = 0

    print("2. Testing expiry fetch...")
    try:
        expiries = await dhan.get_option_expiries("NIFTY")
        print(f"   Expiries: {expiries[:3]}")
        expiry = expiries[0] if expiries else None
    except Exception as e:
        print(f"   ERROR: {type(e).__name__}: {e}")
        expiry = None

    if not expiry:
        print("   No expiry — cannot test chain")
        await dhan.close()
        return

    print(f"3. Testing option chain fetch (expiry={expiry})...")
    try:
        t0 = time.time()
        raw_chain = await dhan.get_option_chain("NIFTY", expiry)
        elapsed = round(time.time() - t0, 2)
        print(f"   Fetched in {elapsed}s")
        if raw_chain:
            oc = raw_chain.get("data", {}).get("oc", {})
            print(f"   Strikes: {len(oc)}")
            if oc:
                sample = list(oc.items())[0]
                print(f"   Sample strike {sample[0]}: CE_ltp={sample[1].get('ce',{}).get('last_price')} PE_ltp={sample[1].get('pe',{}).get('last_price')}")
        else:
            print("   EMPTY RESPONSE")
    except Exception as e:
        import traceback
        print(f"   ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        await dhan.close()
        return

    print("4. Testing process_option_chain...")
    try:
        chain = process_option_chain(raw_chain, "NIFTY", expiry, spot)
        print(f"   Rows: {len(chain.rows)}")
    except Exception as e:
        import traceback
        print(f"   ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()

    await dhan.close()
    print("\nDone.")


asyncio.run(test())
