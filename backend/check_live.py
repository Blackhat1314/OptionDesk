"""Check live market data fetch."""
import asyncio, json, urllib.request, time


async def check():
    # 1. Health check
    r = urllib.request.urlopen("http://localhost:8000/api/health", timeout=5)
    health = json.loads(r.read())
    print("Health:", health)

    # 2. Try fetching option chain directly
    from api.dhan_client import get_dhan_client
    from config import get_settings
    settings = get_settings()
    print(f"\nDhan Client ID: {settings.DHAN_CLIENT_ID}")
    print(f"Access Token (first 30): {settings.DHAN_ACCESS_TOKEN[:30]}...")

    dhan = get_dhan_client()

    # 3. Test LTP fetch for NIFTY
    print("\nFetching NIFTY LTP...")
    try:
        from api.dhan_client import INDEX_SECURITY_IDS_INT
        sid = INDEX_SECURITY_IDS_INT.get("NIFTY", 13)
        ltp_resp = await dhan.get_ltp([sid], "IDX_I")
        print("LTP response:", json.dumps(ltp_resp, indent=2)[:500])
    except Exception as e:
        print(f"LTP ERROR: {e}")

    # 4. Test expiries
    print("\nFetching NIFTY expiries...")
    try:
        expiries = await dhan.get_option_expiries("NIFTY")
        print("Expiries:", expiries[:3] if expiries else "NONE")
    except Exception as e:
        print(f"Expiries ERROR: {e}")

    # 5. Test option chain
    print("\nFetching NIFTY option chain...")
    try:
        from datetime import date, timedelta
        today = date.today()
        days_ahead = (3 - today.weekday()) % 7
        if days_ahead == 0: days_ahead = 7
        expiry = (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        print(f"Using expiry: {expiry}")
        chain = await dhan.get_option_chain("NIFTY", expiry)
        if chain:
            oc = chain.get("data", {}).get("oc", {})
            print(f"Option chain strikes: {len(oc)}")
            if oc:
                sample_strike = list(oc.keys())[0]
                print(f"Sample strike {sample_strike}: {json.dumps(oc[sample_strike])[:200]}")
        else:
            print("Option chain: EMPTY RESPONSE")
    except Exception as e:
        print(f"Option chain ERROR: {type(e).__name__}: {e}")

    await dhan.close()


asyncio.run(check())
