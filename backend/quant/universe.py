"""
NIFTY 50 + liquid F&O stock universe.
Dhan NSE_EQ security IDs — from Dhan instrument master CSV.
Each symbol must have a UNIQUE security_id.
"""

# Verified Dhan NSE_EQ security IDs (no duplicates)
UNIVERSE: dict = {
    "RELIANCE":    1333,
    "TCS":         11536,
    "HDFCBANK":    1330,
    "INFY":        1594,
    "ICICIBANK":   4963,
    "HINDUNILVR":  1394,
    "ITC":         1660,
    "SBIN":        3045,
    "BHARTIARTL":  10604,
    "KOTAKBANK":   1922,
    "LT":          11483,
    "AXISBANK":    5900,
    "ASIANPAINT":  236,
    "MARUTI":      10999,
    "SUNPHARMA":   3351,
    "TITAN":       3506,
    "BAJFINANCE":  317,
    "WIPRO":       3787,
    "ULTRACEMCO":  11532,
    "NESTLEIND":   17963,
    "POWERGRID":   14977,
    "NTPC":        11630,
    "TECHM":       13538,
    "HCLTECH":     7229,
    "ONGC":        11723,
    "JSWSTEEL":    14418,
    "TATAMOTORS":  3456,
    "TATASTEEL":   3499,
    "ADANIENT":    25,
    "ADANIPORTS":  15083,
    "COALINDIA":   20374,
    "BAJAJFINSV":  16675,
    "DRREDDY":     3001,
    "CIPLA":       694,
    "DIVISLAB":    10243,
    "EICHERMOT":   910,
    "HEROMOTOCO":  1348,
    "APOLLOHOSP":  157,
    "BPCL":        526,
    "GRASIM":      1232,
    "HINDALCO":    1363,
    "INDUSINDBK":  5258,
    "M&M":         2031,
    "SBILIFE":     21808,
    "HDFCLIFE":    119,
    "BRITANNIA":   547,
    "TATACONSUM":  3432,
    "UPL":         11287,
    "SHREECEM":    3103,
    "BAJAJ-AUTO":  16669,
}

UNIVERSE_SEGMENT = "NSE_EQ"

def get_security_ids() -> list:
    return list(UNIVERSE.values())

def get_symbols() -> list:
    return list(UNIVERSE.keys())

def get_symbol_by_id(sid: int) -> str:
    for sym, s in UNIVERSE.items():
        if s == sid:
            return sym
    return str(sid)
