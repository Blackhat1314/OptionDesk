"""
stocks/live_prices.py
=====================
Centralised live market data for all stocks.

Architecture (exactly as requested):
  - Price (LTP)          → Dhan WebSocket ticks (real-time, every ~1s)
  - Day change, volume,
    circuit limits, VWAP → /marketfeed/quote batch (every 30s during market hours)
  - Calculations         → historical daily candles (pipeline, runs after close)

Single Dhan API connection serves ALL frontend users via Redis cache.
Frontend never hits Dhan directly.

Flow:
  Dhan WS  → _handle_dhan_feed() → state.stock_ltp:{sid} → WS broadcast → frontend
  Dhan API → fetch_live_stock_prices() → Redis stocks:live_prices → /api/stocks/live-prices → frontend
"""

import asyncio
import time
import logging
from typing import Dict, List

import pytz
from datetime import datetime

from core.redis_cache import get_cache
from stocks.universe import STOCK_UNIVERSE, get_security_id, get_segment

log = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")

KEY_LIVE_PRICES    = "stocks:live_prices"
KEY_LIVE_PRICES_TS = "stocks:live_prices_ts"
TTL_LIVE_PRICES    = 300   # 5 min TTL — keep last fetch available after close
BATCH_SIZE         = 500   # Dhan allows 1000/request, use 500 to be safe


def _is_market_open() -> bool:
    now  = datetime.now(IST)
    mins = now.hour * 60 + now.minute
    return now.weekday() < 5 and 9 * 60 + 15 <= mins <= 15 * 60 + 30


def _is_market_day() -> bool:
    """True on weekdays (market may be open or just closed today)."""
    return datetime.now(IST).weekday() < 5


async def fetch_live_stock_prices() -> Dict[str, Dict]:
    """
    Single /marketfeed/quote call for all 226 stocks.
    Returns day change, volume, VWAP, circuit limits, OHLC.
    LTP here is used as fallback only — WS ticks are the primary price source.
    """
    from api.dhan_client import get_dhan_client

    dhan       = get_dhan_client()
    seg_map:    Dict[str, List[int]] = {}
    sid_to_sym: Dict[str, str]       = {}

    for sym in STOCK_UNIVERSE.keys():
        sid = get_security_id(sym)
        seg = get_segment(sym)
        if sid == 0:
            continue
        seg_map.setdefault(seg, []).append(sid)
        sid_to_sym[f"{seg}:{sid}"] = sym

    results: Dict[str, Dict] = {}

    for seg, sids in seg_map.items():
        for i in range(0, len(sids), BATCH_SIZE):
            batch = sids[i:i + BATCH_SIZE]
            try:
                resp     = await dhan.get_market_quote(batch, seg)
                seg_data = resp.get("data", {}).get(seg, {})

                for sid in batch:
                    sym = sid_to_sym.get(f"{seg}:{sid}")
                    if not sym:
                        continue

                    q = seg_data.get(str(sid)) or seg_data.get(sid) or {}
                    if not q:
                        continue

                    ltp        = float(q.get("last_price")         or 0)
                    ohlc       = q.get("ohlc") or {}
                    day_open   = float(ohlc.get("open")            or 0)
                    day_high   = float(ohlc.get("high")            or 0)
                    day_low    = float(ohlc.get("low")             or 0)
                    prev_close = float(ohlc.get("close")           or 0)
                    vwap       = float(q.get("average_price")      or 0)
                    volume     = int(q.get("volume")               or 0)
                    net_change = float(q.get("net_change")         or 0)
                    buy_qty    = int(q.get("buy_quantity")         or 0)
                    sell_qty   = int(q.get("sell_quantity")        or 0)
                    upper_ckt  = float(q.get("upper_circuit_limit") or 0)
                    lower_ckt  = float(q.get("lower_circuit_limit") or 0)
                    w52_high   = float(q.get("52_week_high")       or 0)
                    w52_low    = float(q.get("52_week_low")        or 0)

                    if ltp <= 0:
                        continue

                    # Dhan's net_change is most accurate (pre-computed from prev close)
                    if net_change != 0 and prev_close <= 0:
                        prev_close = ltp - net_change

                    day_change     = round(net_change if net_change != 0 else (ltp - prev_close), 2) if prev_close > 0 else 0.0
                    day_change_pct = round(day_change / prev_close * 100, 2) if prev_close > 0 else 0.0

                    intraday_chg     = round(ltp - day_open, 2) if day_open > 0 else 0.0
                    intraday_chg_pct = round(intraday_chg / day_open * 100, 2) if day_open > 0 else 0.0

                    day_range = day_high - day_low
                    range_pos = round((ltp - day_low) / day_range * 100, 1) if day_range > 0 else 50.0

                    total_qty    = buy_qty + sell_qty
                    buy_pressure = round(buy_qty / total_qty * 100, 1) if total_qty > 0 else 50.0

                    results[sym] = {
                        # LTP from REST (used as fallback when WS tick not yet received)
                        "ltp":                  ltp,
                        # Day context — from /marketfeed/quote
                        "open":                 day_open,
                        "high":                 day_high,
                        "low":                  day_low,
                        "prev_close":           prev_close,
                        "vwap":                 vwap,
                        "volume":               volume,
                        "day_change":           day_change,
                        "day_change_pct":       day_change_pct,
                        "intraday_change":      intraday_chg,
                        "intraday_change_pct":  intraday_chg_pct,
                        "range_position":       range_pos,
                        "buy_pressure":         buy_pressure,
                        "upper_circuit":        upper_ckt,
                        "lower_circuit":        lower_ckt,
                        "w52_high_live":        w52_high,
                        "w52_low_live":         w52_low,
                        "ts":                   time.time(),
                    }

            except Exception as e:
                log.warning(f"Live price fetch error ({seg} batch): {e}")

            await asyncio.sleep(1.1)   # 1 req/sec limit

    return results


async def run_live_price_loop():
    """
    Background loop — fetches /marketfeed/quote for all stocks.

    Schedule:
      - Startup:         fetch immediately (shows latest prices even after close)
      - Market open:     every 30s
      - Market close:    once at 15:31 to capture final EOD values
      - After 16:00:     sleep until next market day

    The WS tick handler updates LTP in real-time separately.
    This loop provides day context (change, volume, circuits, VWAP).
    """
    cache = get_cache()
    await asyncio.sleep(8)   # let app finish starting

    _fetched_eod_today = False
    _last_date         = ""

    # ── Startup fetch — always run once regardless of market hours ────────────
    # Retry up to 5 times in case Redis/network isn't ready yet
    for attempt in range(5):
        try:
            prices = await fetch_live_stock_prices()
            if prices:
                await cache.set(KEY_LIVE_PRICES, prices, ttl=86400)
                await cache.set(KEY_LIVE_PRICES_TS, {
                    "ts": time.time(), "count": len(prices),
                    "elapsed": 0, "market_open": _is_market_open(),
                }, ttl=86400)
                break   # success
            await asyncio.sleep(5)
        except Exception as e:
            log.warning(f"Startup live price fetch attempt {attempt+1} failed: {e}")
            await asyncio.sleep(5)

    while True:
        try:
            now  = datetime.now(IST)
            date = now.strftime("%Y-%m-%d")
            mins = now.hour * 60 + now.minute

            # Reset daily EOD flag on new day
            if date != _last_date:
                _fetched_eod_today = False
                _last_date         = date

            market_open = _is_market_open()
            just_closed = _is_market_day() and 15 * 60 + 30 <= mins <= 16 * 60

            if market_open:
                # During market hours: fetch every 30s
                t0      = time.time()
                prices  = await fetch_live_stock_prices()
                elapsed = time.time() - t0
                if prices:
                    await cache.set(KEY_LIVE_PRICES, prices, ttl=TTL_LIVE_PRICES)
                    await cache.set(KEY_LIVE_PRICES_TS, {
                        "ts": time.time(), "count": len(prices),
                        "elapsed": round(elapsed, 2), "market_open": True,
                    }, ttl=TTL_LIVE_PRICES)
                await asyncio.sleep(30)

            elif just_closed and not _fetched_eod_today:
                # Market just closed — fetch final EOD values
                await asyncio.sleep(90)   # wait 90s for Dhan to settle
                prices = await fetch_live_stock_prices()
                if prices:
                    await cache.set(KEY_LIVE_PRICES, prices, ttl=86400)
                    await cache.set(KEY_LIVE_PRICES_TS, {
                        "ts": time.time(), "count": len(prices),
                        "elapsed": 0, "market_open": False, "eod": True,
                    }, ttl=86400)
                _fetched_eod_today = True
                await asyncio.sleep(300)

            else:
                await asyncio.sleep(60)

        except Exception as e:
            log.warning(f"Live price loop error: {e}")
            await asyncio.sleep(30)


async def get_cached_live_prices() -> Dict[str, Dict]:
    """Get cached live prices from Redis. Returns {} if not available."""
    cache = get_cache()
    return await cache.get(KEY_LIVE_PRICES) or {}
