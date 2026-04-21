"""
stocks/stock_fetcher.py
========================
Fetches OHLCV from Dhan /charts/historical and stores in SQLite.

Per Dhan API docs (https://dhanhq.co/docs/v2/historical-data/):
  POST /v2/charts/historical
  Body: {securityId, exchangeSegment, instrument, expiryCode, oi, fromDate, toDate}
  Response: {open[], high[], low[], close[], volume[], timestamp[]}
  No documented rate limit — use a small courtesy delay to avoid hammering.

Strategy:
  - First run: fetch 5 years of daily data for each stock
  - Subsequent runs: fetch only from last stored date to today
  - Store in SQLite — survives restarts, no Redis quota used for historical data
  - Concurrent fetches: up to CONCURRENCY stocks in parallel
"""

import asyncio
import time
from datetime import date, timedelta, datetime
from typing import Dict, List, Optional

from api.dhan_client import get_dhan_client
from stocks.universe import STOCK_UNIVERSE, get_security_id, get_segment
from stocks.database import (
    upsert_candles, get_latest_ts, get_candle_count,
    get_all_symbols_with_data, set_meta, get_meta,
)

YEARS_BACK   = 5
FETCH_DELAY  = 0.3    # 300ms between requests — no documented rate limit
CONCURRENCY  = 5      # fetch up to 5 stocks in parallel


def _parse_response(resp: Dict) -> List[Dict]:
    """
    Parse Dhan historical API response into list of candle dicts.
    Response format per docs:
      {open[], high[], low[], close[], volume[], timestamp[]}
    """
    timestamps = resp.get("timestamp", [])
    opens      = resp.get("open",      [])
    highs      = resp.get("high",      [])
    lows       = resp.get("low",       [])
    closes     = resp.get("close",     [])
    volumes    = resp.get("volume",    [])

    if not timestamps or not closes:
        return []

    candles = []
    for i in range(len(timestamps)):
        try:
            candles.append({
                "ts":     int(timestamps[i]),
                "open":   float(opens[i])   if i < len(opens)   else 0.0,
                "high":   float(highs[i])   if i < len(highs)   else 0.0,
                "low":    float(lows[i])    if i < len(lows)    else 0.0,
                "close":  float(closes[i]),
                "volume": int(volumes[i])   if i < len(volumes) else 0,
            })
        except (ValueError, TypeError, IndexError):
            continue

    candles.sort(key=lambda x: x["ts"])
    return candles


async def _fetch_range(symbol: str, from_date: str, to_date: str) -> List[Dict]:
    """Fetch daily candles for a symbol between two dates."""
    dhan = get_dhan_client()
    sid  = get_security_id(symbol)
    seg  = get_segment(symbol)

    if sid == 0:
        return []

    resp = await dhan.get_historical_data(
        security_id      = str(sid),
        exchange_segment = seg,
        instrument_type  = "EQUITY",
        expiry_code      = 0,
        from_date        = from_date,
        to_date          = to_date,
    )

    return _parse_response(resp)


async def fetch_full_history(symbol: str) -> int:
    """
    Fetch 5-year daily history for a stock and store in SQLite.
    Returns number of candles stored.
    """
    today     = date.today()
    from_date = (today - timedelta(days=365 * YEARS_BACK)).strftime("%Y-%m-%d")
    to_date   = today.strftime("%Y-%m-%d")

    candles = await _fetch_range(symbol, from_date, to_date)
    if candles:
        upsert_candles(symbol, candles)
    return len(candles)


async def fetch_incremental(symbol: str) -> int:
    """
    Fetch only new candles since the last stored date.
    Used for daily updates after market close.
    Returns number of new candles added.
    """
    latest_ts = get_latest_ts(symbol)
    today     = date.today()

    if latest_ts:
        # Start from day after last stored candle
        last_date = datetime.fromtimestamp(latest_ts).date()
        from_date = (last_date + timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        # No data — fetch full history
        return await fetch_full_history(symbol)

    # Nothing to fetch if already up to date
    if from_date > today.strftime("%Y-%m-%d"):
        return 0

    to_date = today.strftime("%Y-%m-%d")
    candles = await _fetch_range(symbol, from_date, to_date)
    if candles:
        upsert_candles(symbol, candles)
    return len(candles)


async def fetch_all_full_history(
    symbols: Optional[List[str]] = None,
    progress_callback=None,
) -> Dict[str, int]:
    """
    Fetch 5-year history for all symbols that don't have data yet.
    Skips symbols that already have 252+ candles in DB.
    Uses concurrent fetching (CONCURRENCY stocks at a time).
    Returns {symbol: candle_count}.
    """
    syms    = symbols or list(STOCK_UNIVERSE.keys())
    missing = [s for s in syms if get_candle_count(s) < 252]
    results = {s: get_candle_count(s) for s in syms if get_candle_count(s) >= 252}

    if not missing:
        return results

    semaphore = asyncio.Semaphore(CONCURRENCY)
    total     = len(missing)
    done      = [0]

    async def _fetch_one(sym: str):
        async with semaphore:
            try:
                count = await fetch_full_history(sym)
                results[sym] = count
                done[0] += 1
                if progress_callback:
                    progress_callback(sym, done[0], total, count)
            except Exception:
                results[sym] = get_candle_count(sym)
            await asyncio.sleep(FETCH_DELAY)

    await asyncio.gather(*[_fetch_one(s) for s in missing])
    return results


async def fetch_all_incremental(
    symbols: Optional[List[str]] = None,
    progress_callback=None,
) -> Dict[str, int]:
    """
    Fetch today's candle for all symbols (daily update after market close).
    Uses concurrent fetching.
    Returns {symbol: new_candles_added}.
    """
    syms      = symbols or list(STOCK_UNIVERSE.keys())
    results   = {}
    semaphore = asyncio.Semaphore(CONCURRENCY)
    total     = len(syms)
    done      = [0]

    async def _fetch_one(sym: str):
        async with semaphore:
            try:
                count = await fetch_incremental(sym)
                results[sym] = count
                done[0] += 1
                if progress_callback:
                    progress_callback(sym, done[0], total, count)
            except Exception:
                results[sym] = 0
            await asyncio.sleep(FETCH_DELAY)

    await asyncio.gather(*[_fetch_one(s) for s in syms])
    return results
