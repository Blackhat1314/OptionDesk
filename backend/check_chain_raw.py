"""Check raw option chain data structure."""
import asyncio, json
from api.dhan_client import get_dhan_client


async def check():
    dhan = get_dhan_client()
    expiries = await dhan.get_option_expiries("NIFTY")
    print("Expiries:", expiries)

    for exp in expiries[:2]:
        raw = await dhan.get_option_chain("NIFTY", exp)
        oc = raw.get("data", {}).get("oc", {})
        print(f"\nExpiry {exp}: {len(oc)} strikes")
        if oc:
            sample_key = list(oc.keys())[0]
            sample_val = oc[sample_key]
            print(f"  Sample strike: {sample_key}")
            print(f"  Keys: {list(sample_val.keys())}")
            ce = sample_val.get("ce", {})
            pe = sample_val.get("pe", {})
            print(f"  CE keys: {list(ce.keys())[:12]}")
            print(f"  CE last_price: {ce.get('last_price')}")
            print(f"  CE implied_volatility: {ce.get('implied_volatility')}")
            print(f"  CE oi: {ce.get('oi')}")
            print(f"  CE greeks: {ce.get('greeks')}")
            print(f"  CE security_id: {ce.get('security_id')}")

            # Check ATM strike
            ltp_resp = await dhan.get_ltp([13], "IDX_I")
            seg = ltp_resp.get("data", {}).get("IDX_I", {})
            q = seg.get("13") or seg.get(13) or {}
            spot = float(q.get("last_price") or 0)
            print(f"\n  Spot: {spot}")

            # Find ATM
            strikes = sorted([float(k) for k in oc.keys()])
            atm = min(strikes, key=lambda s: abs(s - spot))
            print(f"  ATM strike: {atm}")

            atm_key = f"{atm:.6f}"
            atm_entry = oc.get(atm_key) or oc.get(str(int(atm))) or {}
            atm_ce = atm_entry.get("ce", {})
            print(f"\n  ATM CE:")
            print(f"    last_price: {atm_ce.get('last_price')}")
            print(f"    implied_volatility: {atm_ce.get('implied_volatility')}")
            print(f"    oi: {atm_ce.get('oi')}")
            print(f"    greeks: {atm_ce.get('greeks')}")
            break

    await dhan.close()


asyncio.run(check())
