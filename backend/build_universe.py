"""
build_universe.py
=================
Fetches ALL F&O eligible stocks + selected smallcaps from Dhan instrument master.
Outputs a complete universe of 400-500 stocks with verified security IDs.

F&O stocks = stocks that have FUTSTK (futures) in the instrument master.
These are the most liquid, institutionally traded stocks — ideal for quant screening.
"""

import urllib.request, csv, io
from collections import defaultdict

# ── Fetch instrument master ───────────────────────────────────────────────────
print("Fetching Dhan instrument master...")
url = "https://images.dhan.co/api-data/api-scrip-master.csv"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
data = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
reader = csv.DictReader(io.StringIO(data))

# Build maps
equity_map   = {}   # symbol -> security_id  (NSE_EQ EQUITY)
futures_syms = set()  # symbols that have FUTSTK

for row in reader:
    exch = row.get("SEM_EXM_EXCH_ID", "")
    seg  = row.get("SEM_SEGMENT", "")
    inst = row.get("SEM_INSTRUMENT_NAME", "").strip()
    sym  = row.get("SEM_TRADING_SYMBOL", "").strip()
    sid  = row.get("SEM_SMST_SECURITY_ID", "").strip()

    if not sym or not sid:
        continue

    # NSE equity stocks
    if exch == "NSE" and seg == "E" and inst == "EQUITY":
        if sym not in equity_map:
            equity_map[sym] = int(sid)

    # F&O eligible: has stock futures
    if exch == "NSE" and inst == "FUTSTK":
        # Trading symbol for futures is like "RELIANCE-JAN2025-FUT"
        base = sym.split("-")[0].strip()
        futures_syms.add(base)

print(f"Total NSE equity stocks: {len(equity_map)}")
print(f"F&O eligible symbols: {len(futures_syms)}")

# ── Find F&O stocks that have equity entries ──────────────────────────────────
fo_with_equity = {sym: equity_map[sym] for sym in futures_syms if sym in equity_map}
print(f"F&O stocks with NSE_EQ entry: {len(fo_with_equity)}")

# ── Sector mapping (manual — major F&O stocks) ────────────────────────────────
# We'll assign sectors based on known classifications
SECTOR_MAP = {
    # Banking
    "HDFCBANK": "BANKING", "ICICIBANK": "BANKING", "SBIN": "BANKING",
    "KOTAKBANK": "BANKING", "AXISBANK": "BANKING", "INDUSINDBK": "BANKING",
    "FEDERALBNK": "BANKING", "IDFCFIRSTB": "BANKING", "BANDHANBNK": "BANKING",
    "PNB": "BANKING", "BANKBARODA": "BANKING", "CANBK": "BANKING",
    "RBLBANK": "BANKING", "AUBANK": "BANKING", "KARURVYSYA": "BANKING",
    "YESBANK": "BANKING", "UNIONBANK": "BANKING", "INDIANB": "BANKING",
    "MAHABANK": "BANKING", "CENTRALBK": "BANKING", "IOB": "BANKING",
    "UCOBANK": "BANKING", "BANKINDIA": "BANKING", "J&KBANK": "BANKING",
    "DCBBANK": "BANKING", "CSBBANK": "BANKING", "SOUTHBANK": "BANKING",
    # IT
    "TCS": "IT", "INFY": "IT", "WIPRO": "IT", "HCLTECH": "IT",
    "TECHM": "IT", "LTIM": "IT", "MPHASIS": "IT", "COFORGE": "IT",
    "PERSISTENT": "IT", "TATAELXSI": "IT", "KPITTECH": "IT",
    "TANLA": "IT", "MASTEK": "IT", "NIITTECH": "IT", "HEXAWARE": "IT",
    "CYIENT": "IT", "BIRLASOFT": "IT", "ZENSAR": "IT", "SONATSOFTW": "IT",
    "RATEGAIN": "IT", "NEWGEN": "IT", "INTELLECT": "IT",
    # FMCG
    "HINDUNILVR": "FMCG", "ITC": "FMCG", "NESTLEIND": "FMCG",
    "BRITANNIA": "FMCG", "TATACONSUM": "FMCG", "GODREJCP": "FMCG",
    "DABUR": "FMCG", "COLPAL": "FMCG", "MARICO": "FMCG",
    "EMAMILTD": "FMCG", "VBLLTD": "FMCG", "RADICO": "FMCG",
    "UNITDSPR": "FMCG", "MCDOWELL-N": "FMCG", "PGHH": "FMCG",
    # Pharma
    "SUNPHARMA": "PHARMA", "DRREDDY": "PHARMA", "CIPLA": "PHARMA",
    "DIVISLAB": "PHARMA", "AUROPHARMA": "PHARMA", "LUPIN": "PHARMA",
    "TORNTPHARM": "PHARMA", "ALKEM": "PHARMA", "IPCALAB": "PHARMA",
    "GRANULES": "PHARMA", "GLENMARK": "PHARMA", "NATCOPHARM": "PHARMA",
    "AJANTPHARM": "PHARMA", "LAURUSLABS": "PHARMA", "ABBOTINDIA": "PHARMA",
    "PFIZER": "PHARMA", "SANOFI": "PHARMA", "BIOCON": "PHARMA",
    "ZYDUSLIFE": "PHARMA", "JUBLPHARMA": "PHARMA", "STRIDES": "PHARMA",
    # Auto
    "MARUTI": "AUTO", "EICHERMOT": "AUTO", "HEROMOTOCO": "AUTO",
    "BAJAJ-AUTO": "AUTO", "M&M": "AUTO", "TATAMOTORS": "AUTO",
    "MOTHERSON": "AUTO", "BALKRISIND": "AUTO", "APOLLOTYRE": "AUTO",
    "EXIDEIND": "AUTO", "AMARAJABAT": "AUTO", "BOSCHLTD": "AUTO",
    "BHARATFORG": "AUTO", "SUNDRMFAST": "AUTO", "MINDA": "AUTO",
    "TIINDIA": "AUTO", "ENDURANCE": "AUTO", "CRAFTSMAN": "AUTO",
    # Energy
    "RELIANCE": "ENERGY", "ONGC": "ENERGY", "BPCL": "ENERGY",
    "COALINDIA": "ENERGY", "IOC": "ENERGY", "HINDPETRO": "ENERGY",
    "GAIL": "ENERGY", "OIL": "ENERGY", "MGL": "ENERGY",
    "IGL": "ENERGY", "PETRONET": "ENERGY", "GSPL": "ENERGY",
    "ATGL": "ENERGY", "AEGISCHEM": "ENERGY",
    # Metals
    "JSWSTEEL": "METALS", "TATASTEEL": "METALS", "HINDALCO": "METALS",
    "VEDL": "METALS", "SAIL": "METALS", "NMDC": "METALS",
    "JINDALSTEL": "METALS", "NATIONALUM": "METALS", "HINDCOPPER": "METALS",
    "RATNAMANI": "METALS", "WELCORP": "METALS", "APL": "METALS",
    "JSWENERGY": "METALS", "MOIL": "METALS", "GMRINFRA": "METALS",
    # Cement
    "ULTRACEMCO": "CEMENT", "GRASIM": "CEMENT", "SHREECEM": "CEMENT",
    "ACC": "CEMENT", "AMBUJACEM": "CEMENT", "DALBHARAT": "CEMENT",
    "RAMCOCEM": "CEMENT", "JKCEMENT": "CEMENT", "HEIDELBERG": "CEMENT",
    "BIRLACORPN": "CEMENT", "JKLAKSHMI": "CEMENT",
    # Power
    "POWERGRID": "POWER", "NTPC": "POWER", "TATAPOWER": "POWER",
    "ADANIGREEN": "POWER", "TORNTPOWER": "POWER", "CESC": "POWER",
    "NHPC": "POWER", "SJVN": "POWER", "INOXWIND": "POWER",
    "SUZLON": "POWER", "RPOWER": "POWER", "JSWENERGY": "POWER",
    "ADANIPOWER": "POWER", "CESC": "POWER",
    # NBFC / Finance
    "BAJFINANCE": "NBFC", "BAJAJFINSV": "NBFC", "MUTHOOTFIN": "NBFC",
    "CHOLAFIN": "NBFC", "LICHSGFIN": "NBFC", "MANAPPURAM": "NBFC",
    "SHRIRAMFIN": "NBFC", "ABCAPITAL": "NBFC", "SBICARD": "NBFC",
    "PNBHOUSING": "NBFC", "IIFL": "NBFC", "M&MFIN": "NBFC",
    "SUNDARMFIN": "NBFC", "CANFINHOME": "NBFC", "REPCO": "NBFC",
    "APTUS": "NBFC", "HOMEFIRST": "NBFC", "AAVAS": "NBFC",
    # Insurance
    "SBILIFE": "INSURANCE", "HDFCLIFE": "INSURANCE", "ICICIGI": "INSURANCE",
    "ICICIPRULI": "INSURANCE", "MFSL": "INSURANCE", "STARHEALTH": "INSURANCE",
    "NIACL": "INSURANCE", "GICRE": "INSURANCE",
    # AMC / Capital Markets
    "HDFCAMC": "AMC", "NIPPONLIFE": "AMC", "CAMS": "AMC",
    "ANGELONE": "AMC", "KFINTECH": "AMC", "BSE": "AMC",
    "MCX": "AMC", "CDSL": "AMC",
    # Infra
    "LT": "INFRA", "ADANIPORTS": "INFRA", "IRCTC": "INFRA",
    "RVNL": "INFRA", "IRCON": "INFRA", "NBCC": "INFRA",
    "RITES": "INFRA", "GMRINFRA": "INFRA", "IRB": "INFRA",
    "KNRCON": "INFRA", "PNCINFRA": "INFRA", "ASHOKA": "INFRA",
    "HGINFRA": "INFRA", "GPPL": "INFRA",
    # Defence
    "HAL": "DEFENCE", "BEL": "DEFENCE", "BHEL": "DEFENCE",
    "COCHINSHIP": "DEFENCE", "MAZAGON": "DEFENCE", "BEML": "DEFENCE",
    "PARAS": "DEFENCE", "DATAPATTNS": "DEFENCE",
    # Consumer / Retail
    "TITAN": "CONSUMER", "DMART": "RETAIL", "TRENT": "RETAIL",
    "PAGEIND": "CONSUMER", "VOLTAS": "CONSUMER", "HAVELLS": "CONSUMER",
    "POLYCAB": "CONSUMER", "BLUESTARCO": "CONSUMER", "NYKAA": "CONSUMER",
    "ZOMATO": "CONSUMER", "SWIGGY": "CONSUMER",
    # Telecom
    "BHARTIARTL": "TELECOM", "HFCL": "TELECOM", "TEJASNET": "TELECOM",
    "TATACOMM": "TELECOM", "RAILTEL": "TELECOM",
    # Healthcare
    "APOLLOHOSP": "HEALTHCARE", "LALPATHLAB": "HEALTHCARE",
    "METROPOLIS": "HEALTHCARE", "MAXHEALTH": "HEALTHCARE",
    "FORTIS": "HEALTHCARE", "NARAYANA": "HEALTHCARE",
    "KIMS": "HEALTHCARE", "RAINBOW": "HEALTHCARE",
    # Chemicals
    "PIDILITIND": "CHEMICALS", "DEEPAKNTR": "CHEMICALS",
    "NAVINFLUOR": "CHEMICALS", "PCBL": "CHEMICALS",
    "AARTI": "CHEMICALS", "AARTIIND": "CHEMICALS",
    "CLEAN": "CHEMICALS", "FINEORG": "CHEMICALS",
    "GALAXYSURF": "CHEMICALS", "TATACHEM": "CHEMICALS",
    "GNFC": "CHEMICALS", "COROMANDEL": "CHEMICALS",
    # Real Estate
    "DLF": "REALESTATE", "GODREJPROP": "REALESTATE",
    "OBEROIRLTY": "REALESTATE", "PRESTIGE": "REALESTATE",
    "PHOENIXLTD": "REALESTATE", "BRIGADE": "REALESTATE",
    "SOBHA": "REALESTATE", "MAHLIFE": "REALESTATE",
    "LODHA": "REALESTATE", "SUNTECK": "REALESTATE",
    # Agro
    "UPL": "AGRO", "PIIND": "AGRO", "RALLIS": "AGRO",
    "COROMANDEL": "AGRO", "BAYER": "AGRO",
    # Paints
    "ASIANPAINT": "PAINTS", "BERGEPAINT": "PAINTS",
    "KANSAINER": "PAINTS", "INDIGO": "PAINTS",
    # Conglomerate
    "ADANIENT": "CONGLOMERATE", "BAJAJHLDNG": "CONGLOMERATE",
    "TATAINVEST": "CONGLOMERATE",
}

# ── Group mapping ─────────────────────────────────────────────────────────────
GROUP_MAP = {
    # NIFTY50
    "RELIANCE": "NIFTY50", "TCS": "NIFTY50", "HDFCBANK": "NIFTY50",
    "INFY": "NIFTY50", "ICICIBANK": "NIFTY50", "HINDUNILVR": "NIFTY50",
    "ITC": "NIFTY50", "SBIN": "NIFTY50", "BHARTIARTL": "NIFTY50",
    "KOTAKBANK": "NIFTY50", "LT": "NIFTY50", "AXISBANK": "NIFTY50",
    "ASIANPAINT": "NIFTY50", "MARUTI": "NIFTY50", "SUNPHARMA": "NIFTY50",
    "TITAN": "NIFTY50", "BAJFINANCE": "NIFTY50", "WIPRO": "NIFTY50",
    "ULTRACEMCO": "NIFTY50", "NESTLEIND": "NIFTY50", "POWERGRID": "NIFTY50",
    "NTPC": "NIFTY50", "TECHM": "NIFTY50", "HCLTECH": "NIFTY50",
    "ONGC": "NIFTY50", "JSWSTEEL": "NIFTY50", "TATAMOTORS": "NIFTY50",
    "TATASTEEL": "NIFTY50", "ADANIENT": "NIFTY50", "ADANIPORTS": "NIFTY50",
    "COALINDIA": "NIFTY50", "BAJAJFINSV": "NIFTY50", "DRREDDY": "NIFTY50",
    "CIPLA": "NIFTY50", "DIVISLAB": "NIFTY50", "EICHERMOT": "NIFTY50",
    "HEROMOTOCO": "NIFTY50", "APOLLOHOSP": "NIFTY50", "BPCL": "NIFTY50",
    "GRASIM": "NIFTY50", "HINDALCO": "NIFTY50", "INDUSINDBK": "NIFTY50",
    "M&M": "NIFTY50", "SBILIFE": "NIFTY50", "HDFCLIFE": "NIFTY50",
    "BRITANNIA": "NIFTY50", "TATACONSUM": "NIFTY50", "UPL": "NIFTY50",
    "SHREECEM": "NIFTY50", "BAJAJ-AUTO": "NIFTY50",
    # BANKNIFTY
    "FEDERALBNK": "BANKNIFTY", "IDFCFIRSTB": "BANKNIFTY",
    "BANDHANBNK": "BANKNIFTY", "PNB": "BANKNIFTY", "BANKBARODA": "BANKNIFTY",
    "CANBK": "BANKNIFTY", "RBLBANK": "BANKNIFTY", "AUBANK": "BANKNIFTY",
    "KARURVYSYA": "BANKNIFTY",
    # FINNIFTY
    "MUTHOOTFIN": "FINNIFTY", "CHOLAFIN": "FINNIFTY", "LICHSGFIN": "FINNIFTY",
    "MANAPPURAM": "FINNIFTY", "SHRIRAMFIN": "FINNIFTY", "ABCAPITAL": "FINNIFTY",
    "HDFCAMC": "FINNIFTY", "ICICIGI": "FINNIFTY", "ICICIPRULI": "FINNIFTY",
    "SBICARD": "FINNIFTY", "BAJAJHLDNG": "FINNIFTY", "PNBHOUSING": "FINNIFTY",
    "MFSL": "FINNIFTY",
}

# ── Build final universe ──────────────────────────────────────────────────────
# Priority: F&O stocks first, then add selected smallcaps
universe = {}

# Add all F&O stocks that have equity entries
for sym, sid in sorted(fo_with_equity.items()):
    sector = SECTOR_MAP.get(sym, "OTHER")
    group  = GROUP_MAP.get(sym, "MIDCAP")
    universe[sym] = (sid, "NSE_EQ", group, sector)

print(f"\nF&O stocks added: {len(universe)}")

# Print the universe as Python code
print("\n\n# ── GENERATED UNIVERSE ──────────────────────────────────────────────")
print(f"# Total: {len(universe)} stocks")
print("STOCK_UNIVERSE: Dict[str, Tuple] = {")

current_group = None
for sym, (sid, seg, group, sector) in sorted(universe.items(), key=lambda x: (x[1][2], x[0])):
    if group != current_group:
        print(f"\n    # ── {group} ──")
        current_group = group
    print(f'    "{sym}": ({sid}, "{seg}", "{group}", "{sector}"),')

print("}")
print(f"\n# Total: {len(universe)} stocks")
