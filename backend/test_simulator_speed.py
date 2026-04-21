"""Test simulator speed — should be instant for all stocks now."""
import asyncio, time, urllib.request, json


async def test():
    test_syms = [
        # Old stocks (previously fast)
        "RELIANCE", "TCS", "NATIONALUM",
        # New stocks (previously slow)
        "BLUESTARCO", "DALBHARAT", "COFORGE", "RATNAMANI",
        "JKCEMENT", "HINDCOPPER", "ADANIGREEN",
        # REJECT stocks (never had MC before)
        "YESBANK", "IDEA", "PAYTM",
    ]

    print(f"{'SYMBOL':15} {'TIME':8} {'STATUS':8} {'EXPECTED':12} {'PROB':8} {'CACHED':8}")
    print("-" * 65)

    for sym in test_syms:
        try:
            url = f"http://localhost:8000/api/stock/{sym}/simulate?investment=100000&horizon=126"
            t0  = time.time()
            resp = urllib.request.urlopen(url, timeout=10)
            ms  = (time.time() - t0) * 1000
            data = json.loads(resp.read())
            if data.get("status") == "OK":
                cached = "YES" if data.get("from_cache") else "NO (computed)"
                print(f"{sym:15} {ms:6.0f}ms {'OK':8} "
                      f"₹{data.get('expected_value',0):>10,.0f} "
                      f"{data.get('prob_profit',0):5.1f}%  {cached}")
            else:
                print(f"{sym:15} {ms:6.0f}ms {data.get('status','?'):8}")
        except Exception as e:
            print(f"{sym:15} ERROR: {str(e)[:50]}")


asyncio.run(test())
