"""Fetch correct Dhan security IDs for NSE_EQ stocks."""
import urllib.request, csv, io

NEED = [
    "AUBANK", "KARURVYSYA", "MANAPPURAM", "SHRIRAMFIN", "ABCAPITAL",
    "HDFCAMC", "NIPPONLIFE", "ICICIGI", "ICICIPRULI", "SBICARD",
    "BAJAJHLDNG", "PNBHOUSING", "MPHASIS", "KPITTECH", "TANLA",
    "NYKAA", "DMART", "TRENT", "PAGEIND", "RVNL", "IRCON",
    "NATIONALUM", "HINDCOPPER", "RATNAMANI", "JKCEMENT", "MARICO",
    "EMAMILTD", "RALLIS", "NHPC", "SJVN", "AUROPHARMA", "LUPIN",
    "TORNTPHARM", "ALKEM", "IPCALAB", "LALPATHLAB", "METROPOLIS",
    "MOTHERSON", "BALKRISIND", "APOLLOTYRE", "PIDILITIND", "DEEPAKNTR",
    "AARTI", "NAVINFLUOR", "DLF", "GODREJPROP", "OBEROIRLTY",
    "PRESTIGE", "RITES", "NBCC", "HFCL", "SUZLON", "PCBL",
    "GRANULES", "STRIDES", "CAMS", "ANGELONE", "MFSL", "DABUR",
    "COCHINSHIP", "MAZAGON", "PHOENIXLTD", "INOXWIND",
]

url = "https://images.dhan.co/api-data/api-scrip-master.csv"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
resp = urllib.request.urlopen(req, timeout=20)
data = resp.read().decode("utf-8")

# Check actual column names
reader = csv.DictReader(io.StringIO(data))
headers = reader.fieldnames
print("Columns:", headers[:10])

# Find NSE EQ rows
found = {}
for row in reader:
    exch = row.get("SEM_EXM_EXCH_ID", "")
    seg  = row.get("SEM_SEGMENT", "")
    sym  = row.get("SEM_TRADING_SYMBOL", "").strip()
    sid  = row.get("SEM_SMST_SECURITY_ID", "").strip()
    inst = row.get("SEM_INSTRUMENT_NAME", "").strip()

    # NSE equity
    if exch == "NSE" and seg == "E" and inst == "EQUITY" and sym in NEED:
        if sym not in found:
            found[sym] = int(sid)

print(f"\nFound {len(found)}/{len(NEED)}")
for sym in sorted(NEED):
    if sym in found:
        print(f'    "{sym}": {found[sym]},')
    else:
        print(f'    # MISSING: {sym}')
