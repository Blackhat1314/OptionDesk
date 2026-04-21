"""Verify security IDs for missing stocks against Dhan instrument master."""
import urllib.request, csv, io

MISSING = [
    "HDFCBANK", "HDFCLIFE", "PNB", "BANKBARODA", "MUTHOOTFIN",
    "COFORGE", "TATAELXSI", "ZOMATO", "POLYCAB", "BLUESTAR",
    "IRFC", "JINDALSTEL", "DALMIACEME", "RAMCOCEM", "COLPAL",
    "PIIND", "ADANIGREEN", "CESC",
]

url = "https://images.dhan.co/api-data/api-scrip-master.csv"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
data = urllib.request.urlopen(req, timeout=20).read().decode("utf-8")
reader = csv.DictReader(io.StringIO(data))

found = {}
for row in reader:
    sym  = row.get("SEM_TRADING_SYMBOL", "").strip()
    exch = row.get("SEM_EXM_EXCH_ID", "")
    seg  = row.get("SEM_SEGMENT", "")
    inst = row.get("SEM_INSTRUMENT_NAME", "").strip()
    sid  = row.get("SEM_SMST_SECURITY_ID", "").strip()
    if sym in MISSING and exch == "NSE" and seg == "E" and inst == "EQUITY":
        if sym not in found:
            found[sym] = int(sid)

from stocks.universe import STOCK_UNIVERSE
print("Symbol | Our ID | Correct ID | Match?")
for sym in MISSING:
    our_id = STOCK_UNIVERSE.get(sym, (0,))[0]
    correct = found.get(sym, "NOT FOUND")
    match = "✓" if str(our_id) == str(correct) else "✗ WRONG"
    print(f"  {sym:15} | {our_id:6} | {correct:10} | {match}")
