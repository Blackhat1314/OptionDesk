"""Full live check with correct expiry."""
import asyncio, json
from api.dhan_client import get_dhan_client


async def check():
    dhan = get_dhan_client()

    # Get expiries first
    expiries = await dhan.get_option_expiries("NIFTY")
    print(f"NIFTY expiries: {expiries[:5]}")

    if not expiries:
        print("No expiries — API issue")
        await dhan.close()
        return

    expiry = expiries[0]
    print(f"\nFetching option chain for expiry: {expiry}")

    chain = await dhan.get_option_chain("NIFTY", expiry)
    if not chain:
        print("Empty chain response")
        await dhan.close()
        return

    oc = chain.get("data", {}).get("oc", {})
    print(f"Strikes returned: {len(oc)}")

    if oc:
        # Show a few strikes near ATM
        strikes = sorted([float(k) for k in oc.keys()])
        print(f"Strike range: {strikes[0]} to {strikes[-1]}")
        # Show middle strike
        mid = strikes[len(strikes)//2]
        mid_data = oc.get(str(int(mid)), oc.get(str(mid), {}))
        print(f"\nSample strike {mid}:")
        ce = mid_data.get("ce", {})
        pe = mid_data.get("pe", {})
        print(f"  CE: ltp={ce.get('last_price')} oi={ce.get('oi')} iv={ce.get('implied_volatility')}")
        print(f"  PE: ltp={pe.get('last_price')} oi={pe.get('oi')} iv={pe.get('implied_volatility')}")
        print("\n✓ Option chain data is LIVE and working!")
    else:
        print("Chain returned but no strikes in 'oc' key")
        print("Keys in data:", list(chain.get("data", {}).keys()))

    await dhan.close()


asyncio.run(check())
