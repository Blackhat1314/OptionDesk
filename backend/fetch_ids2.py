import urllib.request, csv, io
NEED = ["RBLBANK", "MPHASIS", "TORNTPOWER", "TORNTPHARM"]
url = "https://images.dhan.co/api-data/api-scrip-master.csv"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
data = urllib.request.urlopen(req, timeout=20).read().decode("utf-8")
reader = csv.DictReader(io.StringIO(data))
for row in reader:
    sym = row.get("SEM_TRADING_SYMBOL", "").strip()
    if sym in NEED and row.get("SEM_EXM_EXCH_ID") == "NSE" and row.get("SEM_SEGMENT") == "E" and row.get("SEM_INSTRUMENT_NAME") == "EQUITY":
        print(f"{sym}: {row['SEM_SMST_SECURITY_ID']}")
