"""
stocks/universe.py
Complete F&O stock universe — ~210 stocks, all IDs verified from Dhan instrument master.

Groups: NIFTY50, BANKNIFTY, FINNIFTY, MIDCAP, SMALLCAP
"""

from typing import Dict, List, Tuple

STOCK_UNIVERSE: Dict[str, Tuple] = {

    # ══════════════════════════════════════════════════════════════════════════
    # NIFTY 50 — 49 constituents
    # ══════════════════════════════════════════════════════════════════════════
    "RELIANCE":    (2885,  "NSE_EQ", "NIFTY50", "ENERGY"),
    "TCS":         (11536, "NSE_EQ", "NIFTY50", "IT"),
    "HDFCBANK":    (1333,  "NSE_EQ", "NIFTY50", "BANKING"),
    "INFY":        (1594,  "NSE_EQ", "NIFTY50", "IT"),
    "ICICIBANK":   (4963,  "NSE_EQ", "NIFTY50", "BANKING"),
    "HINDUNILVR":  (1394,  "NSE_EQ", "NIFTY50", "FMCG"),
    "ITC":         (1660,  "NSE_EQ", "NIFTY50", "FMCG"),
    "SBIN":        (3045,  "NSE_EQ", "NIFTY50", "BANKING"),
    "BHARTIARTL":  (10604, "NSE_EQ", "NIFTY50", "TELECOM"),
    "KOTAKBANK":   (1922,  "NSE_EQ", "NIFTY50", "BANKING"),
    "LT":          (11483, "NSE_EQ", "NIFTY50", "INFRA"),
    "AXISBANK":    (5900,  "NSE_EQ", "NIFTY50", "BANKING"),
    "ASIANPAINT":  (236,   "NSE_EQ", "NIFTY50", "PAINTS"),
    "MARUTI":      (10999, "NSE_EQ", "NIFTY50", "AUTO"),
    "SUNPHARMA":   (3351,  "NSE_EQ", "NIFTY50", "PHARMA"),
    "TITAN":       (3506,  "NSE_EQ", "NIFTY50", "CONSUMER"),
    "BAJFINANCE":  (317,   "NSE_EQ", "NIFTY50", "NBFC"),
    "WIPRO":       (3787,  "NSE_EQ", "NIFTY50", "IT"),
    "ULTRACEMCO":  (11532, "NSE_EQ", "NIFTY50", "CEMENT"),
    "NESTLEIND":   (17963, "NSE_EQ", "NIFTY50", "FMCG"),
    "POWERGRID":   (14977, "NSE_EQ", "NIFTY50", "POWER"),
    "NTPC":        (11630, "NSE_EQ", "NIFTY50", "POWER"),
    "TECHM":       (13538, "NSE_EQ", "NIFTY50", "IT"),
    "HCLTECH":     (7229,  "NSE_EQ", "NIFTY50", "IT"),
    "ONGC":        (2475,  "NSE_EQ", "NIFTY50", "ENERGY"),
    "JSWSTEEL":    (11723, "NSE_EQ", "NIFTY50", "METALS"),
    "TATASTEEL":   (3499,  "NSE_EQ", "NIFTY50", "METALS"),
    "ADANIENT":    (25,    "NSE_EQ", "NIFTY50", "CONGLOMERATE"),
    "ADANIPORTS":  (15083, "NSE_EQ", "NIFTY50", "INFRA"),
    "COALINDIA":   (20374, "NSE_EQ", "NIFTY50", "ENERGY"),
    "BAJAJFINSV":  (16675, "NSE_EQ", "NIFTY50", "NBFC"),
    "DRREDDY":     (881,   "NSE_EQ", "NIFTY50", "PHARMA"),
    "CIPLA":       (694,   "NSE_EQ", "NIFTY50", "PHARMA"),
    "DIVISLAB":    (10940, "NSE_EQ", "NIFTY50", "PHARMA"),
    "EICHERMOT":   (910,   "NSE_EQ", "NIFTY50", "AUTO"),
    "HEROMOTOCO":  (1348,  "NSE_EQ", "NIFTY50", "AUTO"),
    "APOLLOHOSP":  (157,   "NSE_EQ", "NIFTY50", "HEALTHCARE"),
    "BPCL":        (526,   "NSE_EQ", "NIFTY50", "ENERGY"),
    "GRASIM":      (1232,  "NSE_EQ", "NIFTY50", "CEMENT"),
    "HINDALCO":    (1363,  "NSE_EQ", "NIFTY50", "METALS"),
    "INDUSINDBK":  (5258,  "NSE_EQ", "NIFTY50", "BANKING"),
    "M&M":         (2031,  "NSE_EQ", "NIFTY50", "AUTO"),
    "SBILIFE":     (21808, "NSE_EQ", "NIFTY50", "INSURANCE"),
    "HDFCLIFE":    (467,   "NSE_EQ", "NIFTY50", "INSURANCE"),
    "BRITANNIA":   (547,   "NSE_EQ", "NIFTY50", "FMCG"),
    "TATACONSUM":  (3432,  "NSE_EQ", "NIFTY50", "FMCG"),
    "UPL":         (11287, "NSE_EQ", "NIFTY50", "AGRO"),
    "SHREECEM":    (3103,  "NSE_EQ", "NIFTY50", "CEMENT"),
    "BAJAJ-AUTO":  (16669, "NSE_EQ", "NIFTY50", "AUTO"),

    # ══════════════════════════════════════════════════════════════════════════
    # BANKNIFTY — constituents not already in NIFTY50
    # ══════════════════════════════════════════════════════════════════════════
    "FEDERALBNK":  (1023,  "NSE_EQ", "BANKNIFTY", "BANKING"),
    "IDFCFIRSTB":  (11184, "NSE_EQ", "BANKNIFTY", "BANKING"),
    "BANDHANBNK":  (2263,  "NSE_EQ", "BANKNIFTY", "BANKING"),
    "PNB":         (10666, "NSE_EQ", "BANKNIFTY", "BANKING"),
    "BANKBARODA":  (4668,  "NSE_EQ", "BANKNIFTY", "BANKING"),
    "CANBK":       (10794, "NSE_EQ", "BANKNIFTY", "BANKING"),
    "RBLBANK":     (18391, "NSE_EQ", "BANKNIFTY", "BANKING"),
    "AUBANK":      (21238, "NSE_EQ", "BANKNIFTY", "BANKING"),
    "KARURVYSYA":  (1838,  "NSE_EQ", "BANKNIFTY", "BANKING"),
    "YESBANK":     (11915, "NSE_EQ", "BANKNIFTY", "BANKING"),
    "UNIONBANK":   (10753, "NSE_EQ", "BANKNIFTY", "BANKING"),
    "INDIANB":     (14309, "NSE_EQ", "BANKNIFTY", "BANKING"),
    "BANKINDIA":   (4745,  "NSE_EQ", "BANKNIFTY", "BANKING"),

    # ══════════════════════════════════════════════════════════════════════════
    # FINNIFTY — constituents not already in NIFTY50/BANKNIFTY
    # ══════════════════════════════════════════════════════════════════════════
    "MUTHOOTFIN":  (23650, "NSE_EQ", "FINNIFTY", "NBFC"),
    "CHOLAFIN":    (19257, "NSE_EQ", "FINNIFTY", "NBFC"),
    "LICHSGFIN":   (1997,  "NSE_EQ", "FINNIFTY", "NBFC"),
    "MANAPPURAM":  (19061, "NSE_EQ", "FINNIFTY", "NBFC"),
    "SHRIRAMFIN":  (4306,  "NSE_EQ", "FINNIFTY", "NBFC"),
    "ABCAPITAL":   (21614, "NSE_EQ", "FINNIFTY", "NBFC"),
    "HDFCAMC":     (4244,  "NSE_EQ", "FINNIFTY", "AMC"),
    "ICICIGI":     (21770, "NSE_EQ", "FINNIFTY", "INSURANCE"),
    "ICICIPRULI":  (18652, "NSE_EQ", "FINNIFTY", "INSURANCE"),
    "SBICARD":     (17971, "NSE_EQ", "FINNIFTY", "NBFC"),
    "BAJAJHLDNG":  (305,   "NSE_EQ", "FINNIFTY", "CONGLOMERATE"),
    "PNBHOUSING":  (18908, "NSE_EQ", "FINNIFTY", "NBFC"),
    "MFSL":        (2142,  "NSE_EQ", "FINNIFTY", "INSURANCE"),
    "LICI":        (9480,  "NSE_EQ", "FINNIFTY", "INSURANCE"),
    "JIOFIN":      (18143, "NSE_EQ", "FINNIFTY", "NBFC"),
    "LTF":         (24948, "NSE_EQ", "FINNIFTY", "NBFC"),

    # ══════════════════════════════════════════════════════════════════════════
    # MIDCAP — NIFTY MIDCAP 150 high-liquidity picks
    # ══════════════════════════════════════════════════════════════════════════

    # IT / Technology
    "PERSISTENT":  (18365, "NSE_EQ", "MIDCAP", "IT"),
    "COFORGE":     (11543, "NSE_EQ", "MIDCAP", "IT"),
    "TATAELXSI":   (3411,  "NSE_EQ", "MIDCAP", "IT"),
    "MPHASIS":     (4503,  "NSE_EQ", "MIDCAP", "IT"),
    "KPITTECH":    (9683,  "NSE_EQ", "MIDCAP", "IT"),
    "OFSS":        (10738, "NSE_EQ", "MIDCAP", "IT"),
    "LTM":         (17818, "NSE_EQ", "MIDCAP", "IT"),

    # Consumer / Retail
    "DMART":       (19913, "NSE_EQ", "MIDCAP", "CONSUMER"),
    "TRENT":       (1964,  "NSE_EQ", "MIDCAP", "CONSUMER"),
    "PAGEIND":     (14413, "NSE_EQ", "MIDCAP", "CONSUMER"),
    "VOLTAS":      (3718,  "NSE_EQ", "MIDCAP", "CONSUMER"),
    "HAVELLS":     (9819,  "NSE_EQ", "MIDCAP", "CONSUMER"),
    "POLYCAB":     (9590,  "NSE_EQ", "MIDCAP", "CONSUMER"),
    "BLUESTARCO":  (8311,  "NSE_EQ", "MIDCAP", "CONSUMER"),
    "CROMPTON":    (17094, "NSE_EQ", "MIDCAP", "CONSUMER"),
    "JUBLFOOD":    (18096, "NSE_EQ", "MIDCAP", "CONSUMER"),
    "UNITDSPR":    (10447, "NSE_EQ", "MIDCAP", "FMCG"),
    "VBL":         (18921, "NSE_EQ", "MIDCAP", "FMCG"),

    # Infra / Railways
    "IRCTC":       (13611, "NSE_EQ", "MIDCAP", "INFRA"),
    "IRFC":        (2029,  "NSE_EQ", "MIDCAP", "INFRA"),
    "RVNL":        (9552,  "NSE_EQ", "MIDCAP", "INFRA"),
    "CONCOR":      (4749,  "NSE_EQ", "MIDCAP", "INFRA"),
    "GMRAIRPORT":  (13528, "NSE_EQ", "MIDCAP", "INFRA"),
    "INDUSTOWER":  (29135, "NSE_EQ", "MIDCAP", "INFRA"),
    "HUDCO":       (20825, "NSE_EQ", "MIDCAP", "INFRA"),

    # Defence
    "HAL":         (2303,  "NSE_EQ", "MIDCAP", "DEFENCE"),
    "BEL":         (383,   "NSE_EQ", "MIDCAP", "DEFENCE"),
    "BHEL":        (438,   "NSE_EQ", "MIDCAP", "DEFENCE"),
    "COCHINSHIP":  (21508, "NSE_EQ", "MIDCAP", "DEFENCE"),
    "MAZDOCK":     (509,   "NSE_EQ", "MIDCAP", "DEFENCE"),
    "BDL":         (2144,  "NSE_EQ", "MIDCAP", "DEFENCE"),

    # Metals
    "SAIL":        (2963,  "NSE_EQ", "MIDCAP", "METALS"),
    "NMDC":        (15332, "NSE_EQ", "MIDCAP", "METALS"),
    "VEDL":        (3063,  "NSE_EQ", "MIDCAP", "METALS"),
    "JINDALSTEL":  (6733,  "NSE_EQ", "MIDCAP", "METALS"),
    "NATIONALUM":  (6364,  "NSE_EQ", "MIDCAP", "METALS"),
    "APLAPOLLO":   (25780, "NSE_EQ", "MIDCAP", "METALS"),
    "CGPOWER":     (760,   "NSE_EQ", "MIDCAP", "METALS"),

    # Cement
    "ACC":         (22,    "NSE_EQ", "MIDCAP", "CEMENT"),
    "AMBUJACEM":   (1270,  "NSE_EQ", "MIDCAP", "CEMENT"),
    "DALBHARAT":   (8075,  "NSE_EQ", "MIDCAP", "CEMENT"),

    # FMCG
    "GODREJCP":    (10099, "NSE_EQ", "MIDCAP", "FMCG"),
    "DABUR":       (772,   "NSE_EQ", "MIDCAP", "FMCG"),
    "COLPAL":      (15141, "NSE_EQ", "MIDCAP", "FMCG"),
    "MARICO":      (4067,  "NSE_EQ", "MIDCAP", "FMCG"),
    "PATANJALI":   (17029, "NSE_EQ", "MIDCAP", "FMCG"),

    # Power / Energy
    "TATAPOWER":   (3426,  "NSE_EQ", "MIDCAP", "POWER"),
    "ADANIGREEN":  (3563,  "NSE_EQ", "MIDCAP", "POWER"),
    "TORNTPOWER":  (13786, "NSE_EQ", "MIDCAP", "POWER"),
    "JSWENERGY":   (17869, "NSE_EQ", "MIDCAP", "POWER"),
    "RECLTD":      (15355, "NSE_EQ", "MIDCAP", "POWER"),
    "PFC":         (14299, "NSE_EQ", "MIDCAP", "POWER"),
    "POWERINDIA":  (18457, "NSE_EQ", "MIDCAP", "POWER"),
    "ADANIPOWER":  (17388, "NSE_EQ", "MIDCAP", "ENERGY"),
    "HINDPETRO":   (1406,  "NSE_EQ", "MIDCAP", "ENERGY"),
    "IOC":         (1624,  "NSE_EQ", "MIDCAP", "ENERGY"),
    "GAIL":        (4717,  "NSE_EQ", "MIDCAP", "ENERGY"),
    "OIL":         (17438, "NSE_EQ", "MIDCAP", "ENERGY"),
    "PETRONET":    (11351, "NSE_EQ", "MIDCAP", "ENERGY"),
    "HINDZINC":    (1424,  "NSE_EQ", "MIDCAP", "ENERGY"),

    # Pharma / Healthcare
    "AUROPHARMA":  (275,   "NSE_EQ", "MIDCAP", "PHARMA"),
    "LUPIN":       (10440, "NSE_EQ", "MIDCAP", "PHARMA"),
    "TORNTPHARM":  (3518,  "NSE_EQ", "MIDCAP", "PHARMA"),
    "ALKEM":       (11703, "NSE_EQ", "MIDCAP", "PHARMA"),
    "GLENMARK":    (7406,  "NSE_EQ", "MIDCAP", "PHARMA"),
    "LAURUSLABS":  (19234, "NSE_EQ", "MIDCAP", "PHARMA"),
    "BIOCON":      (11373, "NSE_EQ", "MIDCAP", "PHARMA"),
    "ZYDUSLIFE":   (7929,  "NSE_EQ", "MIDCAP", "PHARMA"),
    "MANKIND":     (15380, "NSE_EQ", "MIDCAP", "PHARMA"),
    "FORTIS":      (14592, "NSE_EQ", "MIDCAP", "HEALTHCARE"),
    "MAXHEALTH":   (22377, "NSE_EQ", "MIDCAP", "HEALTHCARE"),

    # Auto / Auto Ancillary
    "MOTHERSON":   (25510, "NSE_EQ", "MIDCAP", "AUTO"),
    "BOSCHLTD":    (2181,  "NSE_EQ", "MIDCAP", "AUTO"),
    "BHARATFORG":  (422,   "NSE_EQ", "MIDCAP", "AUTO"),
    "TIINDIA":     (312,   "NSE_EQ", "MIDCAP", "AUTO"),
    "TVSMOTOR":    (8479,  "NSE_EQ", "MIDCAP", "AUTO"),
    "EXIDEIND":    (676,   "NSE_EQ", "MIDCAP", "AUTO"),
    "UNOMINDA":    (14154, "NSE_EQ", "MIDCAP", "AUTO"),
    "SONACOMS":    (4684,  "NSE_EQ", "MIDCAP", "AUTO"),
    "ASHOKLEY":    (212,   "NSE_EQ", "MIDCAP", "AUTO"),
    "FORCEMOT":    (11573, "NSE_EQ", "MIDCAP", "AUTO"),

    # Chemicals
    "PIDILITIND":  (2664,  "NSE_EQ", "MIDCAP", "CHEMICALS"),
    "SRF":         (3273,  "NSE_EQ", "MIDCAP", "CHEMICALS"),
    "SUPREMEIND":  (3363,  "NSE_EQ", "MIDCAP", "CHEMICALS"),

    # Real Estate
    "DLF":         (14732, "NSE_EQ", "MIDCAP", "REALESTATE"),
    "GODREJPROP":  (17875, "NSE_EQ", "MIDCAP", "REALESTATE"),
    "OBEROIRLTY":  (20242, "NSE_EQ", "MIDCAP", "REALESTATE"),
    "PRESTIGE":    (20302, "NSE_EQ", "MIDCAP", "REALESTATE"),
    "PHOENIXLTD":  (14552, "NSE_EQ", "MIDCAP", "REALESTATE"),
    "LODHA":       (3220,  "NSE_EQ", "MIDCAP", "REALESTATE"),

    # Capital Goods
    "ABB":         (13,    "NSE_EQ", "MIDCAP", "CAPITAL_GOODS"),
    "SIEMENS":     (3150,  "NSE_EQ", "MIDCAP", "CAPITAL_GOODS"),
    "CUMMINSIND":  (1901,  "NSE_EQ", "MIDCAP", "CAPITAL_GOODS"),

    # AMC / Exchanges / Fintech
    "CAMS":        (342,   "NSE_EQ", "MIDCAP", "AMC"),
    "ANGELONE":    (324,   "NSE_EQ", "MIDCAP", "AMC"),
    "KFINTECH":    (13359, "NSE_EQ", "MIDCAP", "AMC"),
    "BSE":         (19585, "NSE_EQ", "MIDCAP", "AMC"),
    "MCX":         (31181, "NSE_EQ", "MIDCAP", "AMC"),
    "CDSL":        (21174, "NSE_EQ", "MIDCAP", "AMC"),
    "MOTILALOFS":  (14947, "NSE_EQ", "MIDCAP", "AMC"),
    "NUVAMA":      (18721, "NSE_EQ", "MIDCAP", "AMC"),

    # Hospitality / Leisure
    "INDHOTEL":    (1512,  "NSE_EQ", "MIDCAP", "HOSPITALITY"),

    # Logistics
    "DELHIVERY":   (9599,  "NSE_EQ", "MIDCAP", "LOGISTICS"),

    # Fintech / New-age
    "PAYTM":       (6705,  "NSE_EQ", "MIDCAP", "FINTECH"),
    "POLICYBZR":   (6656,  "NSE_EQ", "MIDCAP", "FINTECH"),
    "NAUKRI":      (13751, "NSE_EQ", "MIDCAP", "IT"),

    # Telecom
    "IDEA":        (14366, "NSE_EQ", "MIDCAP", "TELECOM"),

    # ══════════════════════════════════════════════════════════════════════════
    # SMALLCAP — smaller / newer / niche stocks
    # ══════════════════════════════════════════════════════════════════════════

    # Infra / PSU
    "IRCON":       (4986,  "NSE_EQ", "SMALLCAP", "INFRA"),
    "RITES":       (3761,  "NSE_EQ", "SMALLCAP", "INFRA"),
    "NBCC":        (31415, "NSE_EQ", "SMALLCAP", "INFRA"),

    # Power / Renewables
    "INOXWIND":    (7852,  "NSE_EQ", "SMALLCAP", "POWER"),
    "SUZLON":      (12018, "NSE_EQ", "SMALLCAP", "POWER"),
    "NHPC":        (17400, "NSE_EQ", "SMALLCAP", "POWER"),
    "SJVN":        (18883, "NSE_EQ", "SMALLCAP", "POWER"),
    "IREDA":       (20261, "NSE_EQ", "SMALLCAP", "POWER"),
    "WAAREEENER":  (25907, "NSE_EQ", "SMALLCAP", "POWER"),
    "CESC":        (628,   "NSE_EQ", "SMALLCAP", "POWER"),

    # Metals / Materials
    "HINDCOPPER":  (17939, "NSE_EQ", "SMALLCAP", "METALS"),
    "RATNAMANI":   (13451, "NSE_EQ", "SMALLCAP", "METALS"),

    # Cement
    "RAMCOCEM":    (2043,  "NSE_EQ", "SMALLCAP", "CEMENT"),
    "JKCEMENT":    (13270, "NSE_EQ", "SMALLCAP", "CEMENT"),

    # FMCG / Agro
    "EMAMILTD":    (13517, "NSE_EQ", "SMALLCAP", "FMCG"),
    "RALLIS":      (2816,  "NSE_EQ", "SMALLCAP", "AGRO"),
    "PIIND":       (24184, "NSE_EQ", "SMALLCAP", "AGRO"),

    # Pharma
    "IPCALAB":     (1633,  "NSE_EQ", "SMALLCAP", "PHARMA"),
    "GRANULES":    (11872, "NSE_EQ", "SMALLCAP", "PHARMA"),

    # Healthcare diagnostics
    "LALPATHLAB":  (11654, "NSE_EQ", "SMALLCAP", "HEALTHCARE"),
    "METROPOLIS":  (9581,  "NSE_EQ", "SMALLCAP", "HEALTHCARE"),

    # Auto Ancillary
    "BALKRISIND":  (335,   "NSE_EQ", "SMALLCAP", "AUTO"),
    "APOLLOTYRE":  (163,   "NSE_EQ", "SMALLCAP", "AUTO"),

    # Chemicals
    "DEEPAKNTR":   (19943, "NSE_EQ", "SMALLCAP", "CHEMICALS"),
    "NAVINFLUOR":  (14672, "NSE_EQ", "SMALLCAP", "CHEMICALS"),
    "PCBL":        (2649,  "NSE_EQ", "SMALLCAP", "CHEMICALS"),
    "SOLARINDS":   (13332, "NSE_EQ", "SMALLCAP", "CHEMICALS"),

    # Capital Goods / Electronics
    "KAYNES":      (12092, "NSE_EQ", "SMALLCAP", "CAPITAL_GOODS"),
    "KEI":         (13310, "NSE_EQ", "SMALLCAP", "CAPITAL_GOODS"),

    # Consumer Electronics / Durables
    "AMBER":       (1185,  "NSE_EQ", "SMALLCAP", "CONSUMER"),
    "DIXON":       (21690, "NSE_EQ", "SMALLCAP", "CONSUMER"),
    "KALYANKJIL":  (2955,  "NSE_EQ", "SMALLCAP", "CONSUMER"),

    # Telecom
    "HFCL":        (21951, "NSE_EQ", "SMALLCAP", "TELECOM"),

    # New-age / Consumer tech
    "SWIGGY":      (27066, "NSE_EQ", "SMALLCAP", "CONSUMER"),
    "ETERNAL":     (5097,  "NSE_EQ", "SMALLCAP", "CONSUMER"),
    "NYKAA":       (6545,  "NSE_EQ", "SMALLCAP", "CONSUMER"),

    # IT / Niche
    "TATATECH":    (20293, "NSE_EQ", "SMALLCAP", "IT"),

    # Auto / New entrant
    "HYUNDAI":     (25844, "NSE_EQ", "SMALLCAP", "AUTO"),

    # Finance / Misc
    "360ONE":      (13061, "NSE_EQ", "SMALLCAP", "AMC"),
    "ADANIENSOL":  (10217, "NSE_EQ", "SMALLCAP", "POWER"),
    "IEX":         (220,   "NSE_EQ", "SMALLCAP", "AMC"),

    # ══════════════════════════════════════════════════════════════════════════
    # EXTENDED UNIVERSE — High-volume underrated stocks
    # All security IDs verified from Dhan instrument master CSV
    # ══════════════════════════════════════════════════════════════════════════

    # ── FMCG / Consumer ───────────────────────────────────────────────────────
    "RADICO":      (10990, "NSE_EQ", "MIDCAP",   "FMCG"),
    "GODFRYPHLP":  (1181,  "NSE_EQ", "MIDCAP",   "FMCG"),
    "VSTIND":      (3724,  "NSE_EQ", "MIDCAP",   "FMCG"),
    "JYOTHYLAB":   (15146, "NSE_EQ", "SMALLCAP", "FMCG"),
    "HATSUN":      (3892,  "NSE_EQ", "SMALLCAP", "FMCG"),

    # ── IT / Tech ─────────────────────────────────────────────────────────────
    "CYIENT":      (5748,  "NSE_EQ", "MIDCAP",   "IT"),

    # ── Pharma / Healthcare ───────────────────────────────────────────────────
    "GABRIEL":     (1085,  "NSE_EQ", "SMALLCAP", "AUTO"),
    "SCHAEFFLER":  (1011,  "NSE_EQ", "MIDCAP",   "AUTO"),

    # ── Chemicals / Specialty ─────────────────────────────────────────────────
    "VINATI":      (17364, "NSE_EQ", "MIDCAP",   "CHEMICALS"),
    "FINEORG":     (3744,  "NSE_EQ", "MIDCAP",   "CHEMICALS"),
    "GALAXYSURF":  (1315,  "NSE_EQ", "MIDCAP",   "CHEMICALS"),
    "TATACHEM":    (3405,  "NSE_EQ", "MIDCAP",   "CHEMICALS"),
    "GHCL":        (1127,  "NSE_EQ", "SMALLCAP", "CHEMICALS"),
    "ALKYLAMINE":  (4487,  "NSE_EQ", "SMALLCAP", "CHEMICALS"),
    "ROSSARI":     (19410, "NSE_EQ", "SMALLCAP", "CHEMICALS"),

    # ── Metals / Mining ───────────────────────────────────────────────────────
    "WELCORP":     (11821, "NSE_EQ", "MIDCAP",   "METALS"),
    "MOIL":        (20830, "NSE_EQ", "SMALLCAP", "METALS"),
    "GMDC":        (5204,  "NSE_EQ", "SMALLCAP", "METALS"),
    "KIOCL":       (19126, "NSE_EQ", "SMALLCAP", "METALS"),

    # ── Power / Renewables ────────────────────────────────────────────────────
    "KPIL":        (1814,  "NSE_EQ", "MIDCAP",   "POWER"),
    "GPPL":        (19731, "NSE_EQ", "SMALLCAP", "POWER"),
    "RPOWER":      (15259, "NSE_EQ", "SMALLCAP", "POWER"),

    # ── Real Estate / Construction ────────────────────────────────────────────
    "SOBHA":       (13826, "NSE_EQ", "MIDCAP",   "REALESTATE"),
    "BRIGADE":     (15184, "NSE_EQ", "MIDCAP",   "REALESTATE"),
    "MAHLIFE":     (8050,  "NSE_EQ", "MIDCAP",   "REALESTATE"),
    "NCLIND":      (14490, "NSE_EQ", "SMALLCAP", "REALESTATE"),
    "AHLUCONT":    (17833, "NSE_EQ", "SMALLCAP", "REALESTATE"),

    # ── Logistics ─────────────────────────────────────────────────────────────
    "BLUEDART":    (495,   "NSE_EQ", "MIDCAP",   "LOGISTICS"),
    "AEGISLOG":    (40,    "NSE_EQ", "SMALLCAP", "LOGISTICS"),

    # ── Hospitality / Travel ──────────────────────────────────────────────────
    "LEMONTREE":   (2606,  "NSE_EQ", "MIDCAP",   "HOSPITALITY"),
    "CHALET":      (8546,  "NSE_EQ", "MIDCAP",   "HOSPITALITY"),
    "EIHOTEL":     (919,   "NSE_EQ", "MIDCAP",   "HOSPITALITY"),
    "TAJGVK":      (9354,  "NSE_EQ", "SMALLCAP", "HOSPITALITY"),

    # ── Retail / QSR ─────────────────────────────────────────────────────────
    "DEVYANI":     (5373,  "NSE_EQ", "MIDCAP",   "CONSUMER"),
    "SAPPHIRE":    (6718,  "NSE_EQ", "MIDCAP",   "CONSUMER"),
    "WESTLIFE":    (11580, "NSE_EQ", "MIDCAP",   "CONSUMER"),

    # ── Media / Entertainment ─────────────────────────────────────────────────
    "ZEEL":        (3812,  "NSE_EQ", "MIDCAP",   "MEDIA"),
    "SUNTV":       (13404, "NSE_EQ", "MIDCAP",   "MEDIA"),
    "PVRINOX":     (13147, "NSE_EQ", "MIDCAP",   "MEDIA"),
    "INOXGREEN":   (12188, "NSE_EQ", "SMALLCAP", "MEDIA"),

    # ── Agro / Fertilizers ────────────────────────────────────────────────────
    "COROMANDEL":  (739,   "NSE_EQ", "MIDCAP",   "AGRO"),
    "GNFC":        (1174,  "NSE_EQ", "MIDCAP",   "AGRO"),
    "GSFC":        (1247,  "NSE_EQ", "MIDCAP",   "AGRO"),
    "KSCL":        (14972, "NSE_EQ", "SMALLCAP", "AGRO"),
    "SUMICHEM":    (17105, "NSE_EQ", "MIDCAP",   "AGRO"),

    # ── Textiles ──────────────────────────────────────────────────────────────
    "RAYMOND":     (2859,  "NSE_EQ", "MIDCAP",   "CONSUMER"),
    "ARVIND":      (193,   "NSE_EQ", "MIDCAP",   "CONSUMER"),
    "TRIDENT":     (9685,  "NSE_EQ", "SMALLCAP", "CONSUMER"),

    # ── Insurance ─────────────────────────────────────────────────────────────
    "STARHEALTH":  (7083,  "NSE_EQ", "MIDCAP",   "INSURANCE"),
    "NIACL":       (399,   "NSE_EQ", "MIDCAP",   "INSURANCE"),
    "GICRE":       (277,   "NSE_EQ", "MIDCAP",   "INSURANCE"),

    # ── Fintech / NBFC / Small Banks ─────────────────────────────────────────
    "CREDITACC":   (4421,  "NSE_EQ", "MIDCAP",   "NBFC"),
    "SPANDANA":    (11435, "NSE_EQ", "MIDCAP",   "NBFC"),
    "UJJIVANSFB":  (15228, "NSE_EQ", "MIDCAP",   "BANKING"),
    "EQUITASBNK":  (913,   "NSE_EQ", "MIDCAP",   "BANKING"),
    "SURYODAY":    (2970,  "NSE_EQ", "SMALLCAP", "BANKING"),
    "ESAFSFB":     (19878, "NSE_EQ", "SMALLCAP", "BANKING"),
    "UTKARSHBNK":  (17358, "NSE_EQ", "SMALLCAP", "BANKING"),
}

# ── Index benchmark ──────────────────────────────────────────────────────────
NIFTY_SECURITY_ID = 13
NIFTY_SEGMENT     = "IDX_I"

# Index groups
GROUPS = ["NIFTY50", "BANKNIFTY", "FINNIFTY", "MIDCAP", "SMALLCAP"]

# Max stocks per sector in final screener output
MAX_PER_SECTOR = 2


# ── Helper functions ─────────────────────────────────────────────────────────

def get_all_symbols() -> List[str]:
    return list(STOCK_UNIVERSE.keys())


def get_security_id(symbol: str) -> int:
    e = STOCK_UNIVERSE.get(symbol)
    return e[0] if e else 0


def get_segment(symbol: str) -> str:
    e = STOCK_UNIVERSE.get(symbol)
    return e[1] if e else "NSE_EQ"


def get_group(symbol: str) -> str:
    e = STOCK_UNIVERSE.get(symbol)
    return e[2] if e else "OTHER"


def get_sector(symbol: str) -> str:
    e = STOCK_UNIVERSE.get(symbol)
    return e[3] if e else "OTHER"


def get_symbols_by_group(group: str) -> List[str]:
    return [s for s, v in STOCK_UNIVERSE.items() if v[2] == group]
