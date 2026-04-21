"""
Instrument Loader — fetches Dhan NSE_EQ security IDs for NIFTY 50 stocks.
Dhan provides a compact instrument master at:
  https://images.dhan.co/api-data/api-scrip-master.csv

This runs once on startup to populate the universe with correct IDs.
Falls back to hardcoded IDs if the download fails.
"""

import asyncio
import csv
import io
from typing import Dict, Optional

import aiohttp

# NIFTY 50 symbols to look up
NIFTY50_SYMBOLS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK",
    "LT", "AXISBANK", "ASIANPAINT", "MARUTI", "SUNPHARMA",
    "TITAN", "BAJFINANCE", "WIPRO", "ULTRACEMCO", "NESTLEIND",
    "POWERGRID", "NTPC", "TECHM", "HCLTECH", "ONGC",
    "JSWSTEEL", "TATAMOTORS", "TATASTEEL", "ADANIENT", "ADANIPORTS",
    "COALINDIA", "BAJAJFINSV", "DRREDDY", "CIPLA", "DIVISLAB",
    "EICHERMOT", "HEROMOTOCO", "APOLLOHOSP", "BPCL", "GRASIM",
    "HINDALCO", "INDUSINDBK", "M&M", "SBILIFE", "HDFCLIFE",
    "BRITANNIA", "TATACONSUM", "UPL", "SHREECEM", "BAJAJ-AUTO",
]

INSTRUMENT_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"

# Fallback hardcoded IDs (from Dhan instrument master, NSE_EQ segment)
FALLBACK_IDS: Dict[str, int] = {
    "RELIANCE":    1333,
    "TCS":         11536,
    "HDFCBANK":    1333,
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
    "JSWSTEEL":    11723,
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
    "BAJAJ-AUTO":  317,
}

_loaded_ids: Optional[Dict[str, int]] = None


async def load_instrument_ids() -> Dict[str, int]:
    """
    Download Dhan instrument master CSV and extract NSE_EQ security IDs
    for NIFTY 50 symbols. Returns {symbol: security_id}.
    Falls back to FALLBACK_IDS on any error.
    """
    global _loaded_ids
    if _loaded_ids is not None:
        return _loaded_ids

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(INSTRUMENT_MASTER_URL, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    _loaded_ids = FALLBACK_IDS.copy()
                    return _loaded_ids

                text = await resp.text(encoding="utf-8", errors="ignore")

        result: Dict[str, int] = {}
        reader = csv.DictReader(io.StringIO(text))

        for row in reader:
            # Dhan CSV columns: SEM_EXM_EXCH_ID, SEM_SEGMENT, SEM_SMST_SECURITY_ID,
            #                   SEM_TRADING_SYMBOL, SEM_INSTRUMENT_NAME, ...
            seg    = (row.get("SEM_SEGMENT") or row.get("ExchId") or "").strip().upper()
            sym    = (row.get("SEM_TRADING_SYMBOL") or row.get("TradingSymbol") or "").strip().upper()
            sid_s  = (row.get("SEM_SMST_SECURITY_ID") or row.get("ScrCode") or "0").strip()

            if seg not in ("NSE_EQ", "NSE EQ", "1") :
                continue
            if sym not in NIFTY50_SYMBOLS:
                continue

            try:
                result[sym] = int(sid_s)
            except ValueError:
                pass

        # Fill missing with fallback
        for sym in NIFTY50_SYMBOLS:
            if sym not in result and sym in FALLBACK_IDS:
                result[sym] = FALLBACK_IDS[sym]

        _loaded_ids = result if result else FALLBACK_IDS.copy()
        return _loaded_ids

    except Exception:
        _loaded_ids = FALLBACK_IDS.copy()
        return _loaded_ids


def get_loaded_ids() -> Dict[str, int]:
    """Synchronous accessor — returns loaded IDs or fallback."""
    return _loaded_ids or FALLBACK_IDS.copy()
