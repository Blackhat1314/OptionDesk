"""Test all new stocks: fundamentals, simulator, quant data."""
import asyncio
import urllib.request, json
from stocks.screener_scraper import fetch_fundamentals
from stocks.database import get_candle_count, init_db


async def test():
    init_db()

    # Test stocks that were problematic
    test_syms = [
        "BLUESTARCO", "DALBHARAT", "COFORGE", "ADANIGREEN",
        "NATIONALUM", "HINDCOPPER", "RATNAMANI", "JKCEMENT",
        "SWIGGY", "ETERNAL", "HYUNDAI", "TATATECH",
        "JIOFIN", "LTM", "ADANIENSOL", "WAAREEENER",
    ]

    print("=" * 60)
    print("CANDLE DATA CHECK")
    print("=" * 60)
    for sym in test_syms:
        count = get_candle_count(sym)
        print(f"  {sym:15}: {count} candles {'✓' if count >= 252 else '✗ MISSING'}")

    print("\n" + "=" * 60)
    print("FUNDAMENTALS CHECK (screener.in)")
    print("=" * 60)
    for sym in test_syms[:8]:  # test first 8 to save time
        try:
            result = await fetch_fundamentals(sym)
            status = result.get("status")
            if status == "OK":
                r = result.get("ratios", {})
                q = result.get("quarterly", [])
                print(f"  {sym:15}: ✓ PE={r.get('pe_ratio')} ROE={r.get('roe')} Q={len(q)}")
            else:
                print(f"  {sym:15}: ✗ {result.get('message', 'ERROR')[:60]}")
        except Exception as e:
            print(f"  {sym:15}: ✗ Exception: {str(e)[:60]}")

    print("\n" + "=" * 60)
    print("SIMULATOR CHECK (via HTTP API)")
    print("=" * 60)
    for sym in test_syms[:6]:
        try:
            url = f"http://localhost:8000/api/stock/{sym}/simulate?investment=100000&horizon=126"
            resp = urllib.request.urlopen(url, timeout=10)
            data = json.loads(resp.read())
            if data.get("status") == "OK":
                print(f"  {sym:15}: ✓ expected={data.get('expected_value'):.0f} prob={data.get('prob_profit'):.1f}%")
            else:
                print(f"  {sym:15}: ✗ {data.get('status')}")
        except Exception as e:
            print(f"  {sym:15}: ✗ {str(e)[:60]}")


asyncio.run(test())
