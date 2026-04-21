"""
Build complete universe from Dhan instrument master.
Outputs universe.py content with all F&O stocks + selected smallcaps.
"""
import urllib.request, csv, io
from collections import defaultdict

print("Fetching Dhan instrument master...")
url = "https://images.dhan.co/api-data/api-scrip-master.csv"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
data = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
reader = csv.DictReader(io.StringIO(data))

equity_map   = {}   # symbol -> security_id
futures_syms = set()

for row in reader:
    exch = row.get("SEM_EXM_EXCH_ID", "")
    seg  = row.get("SEM_SEGMENT", "")
    inst = row.get("SEM_INSTRUMENT_NAME", "").strip()
    sym  = row.get("SEM_TRADING_SYMBOL", "").strip()
    sid  = row.get("SEM_SMST_SECURITY_ID", "").strip()
    if not sym or not sid:
        continue
    if exch == "NSE" and seg == "E" and inst == "EQUITY":
        if sym not in equity_map:
            equity_map[sym] = int(sid)
    if exch == "NSE" and inst == "FUTSTK":
        base = sym.split("-")[0].strip()
        futures_syms.add(base)

fo_equity = {s: equity_map[s] for s in futures_syms if s in equity_map}
print(f"F&O stocks with equity entry: {len(fo_equity)}")

# Print all F&O symbols for manual review
print("\nAll F&O symbols:")
for sym in sorted(fo_equity.keys()):
    print(f"  {sym}: {fo_equity[sym]}")
