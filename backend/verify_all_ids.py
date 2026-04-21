"""Verify ALL security IDs against Dhan instrument master."""
import urllib.request, csv, io
from stocks.universe import STOCK_UNIVERSE

url = "https://images.dhan.co/api-data/api-scrip-master.csv"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
data = urllib.request.urlopen(req, timeout=20).read().decode("utf-8")
reader = csv.DictReader(io.StringIO(data))

correct_ids = {}
for row in reader:
    sym  = row.get("SEM_TRADING_SYMBOL", "").strip()
    exch = row.get("SEM_EXM_EXCH_ID", "")
    seg  = row.get("SEM_SEGMENT", "")
    inst = row.get("SEM_INSTRUMENT_NAME", "").strip()
    sid  = row.get("SEM_SMST_SECURITY_ID", "").strip()
    if exch == "NSE" and seg == "E" and inst == "EQUITY" and sym in STOCK_UNIVERSE:
        if sym not in correct_ids:
            correct_ids[sym] = int(sid)

wrong = []
not_found = []
for sym, val in STOCK_UNIVERSE.items():
    our_id = val[0]
    if sym not in correct_ids:
        not_found.append(sym)
    elif our_id != correct_ids[sym]:
        wrong.append((sym, our_id, correct_ids[sym]))

print(f"Total symbols: {len(STOCK_UNIVERSE)}")
print(f"Verified: {len(correct_ids)}")
print(f"Wrong IDs: {len(wrong)}")
print(f"Not found in master: {len(not_found)}")

if wrong:
    print("\nWRONG IDs (symbol, our_id, correct_id):")
    for sym, ours, correct in wrong:
        print(f'    "{sym}": ({correct},  # was {ours}')

if not_found:
    print("\nNOT FOUND in instrument master:")
    for sym in not_found:
        print(f"  {sym}")

# Print all correct IDs for copy-paste
print("\n\nALL CORRECT IDs:")
for sym in STOCK_UNIVERSE:
    if sym in correct_ids:
        val = STOCK_UNIVERSE[sym]
        print(f'    "{sym}": ({correct_ids[sym]}, "{val[1]}", "{val[2]}", "{val[3]}"),')
    else:
        val = STOCK_UNIVERSE[sym]
        print(f'    # NOT FOUND: "{sym}": ({val[0]}, "{val[1]}", "{val[2]}", "{val[3]}"),')
