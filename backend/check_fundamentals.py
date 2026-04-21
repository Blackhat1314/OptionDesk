"""Check fundamentals fetch for new stocks."""
import asyncio
from stocks.screener_scraper import fetch_fundamentals


async def test():
    # Test a few new stocks
    for sym in ["BLUESTARCO", "DALBHARAT", "COFORGE", "NATIONALUM", "HINDCOPPER"]:
        print(f"\nTesting {sym}...")
        result = await fetch_fundamentals(sym)
        print(f"  Status: {result.get('status')}")
        if result.get("status") == "OK":
            r = result.get("ratios", {})
            print(f"  PE: {r.get('pe_ratio')} ROE: {r.get('roe')} ROCE: {r.get('roce')}")
            q = result.get("quarterly", [])
            print(f"  Quarterly periods: {len(q)}")
        else:
            print(f"  Error: {result.get('message', '')[:100]}")


asyncio.run(test())
