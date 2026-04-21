import urllib.request, csv, io

url = "https://images.dhan.co/api-data/api-scrip-master.csv"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
data = urllib.request.urlopen(req, timeout=20).read().decode("utf-8")
reader = csv.DictReader(io.StringIO(data))

for row in reader:
    sym  = row.get("SEM_TRADING_SYMBOL","").strip()
    sid  = row.get("SEM_SMST_SECURITY_ID","").strip()
    exch = row.get("SEM_EXM_EXCH_ID","")
    seg  = row.get("SEM_SEGMENT","")
    inst = row.get("SEM_INSTRUMENT_NAME","").strip()
    name = row.get("SEM_CUSTOM_SYMBOL","").strip()

    if sym in ("LTIM","ZOMATO","TATAMOTORS","DALMIACEME") and exch == "NSE":
        print(f"{sym:15} seg={seg} inst={inst:10} ID:{sid:8} {name[:40]}")
