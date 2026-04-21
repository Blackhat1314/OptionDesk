"""
stocks/scheduler.py
Stock engine scheduler — BATCH MODE ONLY (market closed).

Startup logic:
  1. If Redis summary exists → skip (already fresh)
  2. If Redis empty but DB has data → recompute from DB immediately (fast, no API calls)
  3. If DB also empty → fetch from Dhan API then compute

Daily logic:
  After 15:30 IST on weekdays → fetch incremental + recompute
"""

import asyncio
import time
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional

import pytz

from core.redis_cache import get_cache
from stocks.market_timer import is_market_open
from stocks.universe import STOCK_UNIVERSE, NIFTY_SECURITY_ID, NIFTY_SEGMENT
from stocks.database import (
    init_db, get_candles, get_candle_count, get_db_stats,
    save_features, save_signals, save_monte_carlo, save_backtest,
    load_features, load_signals, load_monte_carlo, load_backtest,
    upsert_candles,
)
from stocks.stock_fetcher import fetch_all_full_history
from stocks.features import compute_features
from stocks.signals import compute_signal
from stocks.monte_carlo import run_multi_horizon_mc
from stocks.backtest import run_backtest
from stocks.ranking import rank_and_filter, build_stock_output

IST = pytz.timezone("Asia/Kolkata")

TTL_REDIS_RESULTS = 86400 * 3   # 3 days
TTL_REDIS_SUMMARY = 86400 * 3
KEY_STATUS  = "stocks:pipeline:status"
KEY_SUMMARY = "stocks:screener:summary"
KEY_GROUPED = "stocks:screener:grouped"


def _today_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


async def _set_status(cache, status: str, detail: str = ""):
    await cache.set(KEY_STATUS, {
        "status": status, "detail": detail, "updated_at": time.time(),
    }, ttl=86400)


async def _fetch_nifty_candles() -> List[Dict]:
    """Fetch NIFTY 50 index candles — try API first, fall back to DB."""
    from datetime import date, timedelta
    today     = date.today()
    from_date = (today - timedelta(days=365 * 5)).strftime("%Y-%m-%d")
    to_date   = today.strftime("%Y-%m-%d")
    try:
        from api.dhan_client import get_dhan_client
        from stocks.stock_fetcher import _parse_response
        dhan = get_dhan_client()
        resp = await dhan.get_historical_data(
            security_id      = str(NIFTY_SECURITY_ID),
            exchange_segment = NIFTY_SEGMENT,
            instrument_type  = "INDEX",
            expiry_code      = 0,
            from_date        = from_date,
            to_date          = to_date,
        )
        candles = _parse_response(resp)
        if candles:
            upsert_candles("__NIFTY__", candles)
        return candles
    except Exception:
        return get_candles("__NIFTY__")


async def _compute_symbol(cache, symbol: str, nifty_candles: List[Dict], market_regime: str = "MIXED") -> Dict:
    candles = get_candles(symbol)
    if len(candles) < 252:
        return {}

    feats = compute_features(candles, nifty_candles)
    if not feats:
        return {}
    save_features(symbol, feats)
    await cache.set(f"stock:{symbol}:features", feats, TTL_REDIS_RESULTS)

    closes  = np.array([c["close"] for c in candles], dtype=np.float64)
    log_ret = np.log(closes[1:] / closes[:-1])
    window  = log_ret

    # Pre-compute multi-horizon MC first so we can pass it to compute_signal
    multi_mc = run_multi_horizon_mc(symbol, feats["price"], window)
    await cache.set(f"stock:{symbol}:mc_horizons", multi_mc, TTL_REDIS_RESULTS)

    # Use 60-day MC for signal scoring
    mc_for_signal = multi_mc.get("63", multi_mc.get("60", {}))

    # Compute signal with market regime awareness and MC integration
    sig = compute_signal(feats, market_regime=market_regime, mc=mc_for_signal)
    save_signals(symbol, sig)
    await cache.set(f"stock:{symbol}:signals", sig, TTL_REDIS_RESULTS)

    mc = {}
    bt = {}
    if sig.get("signal") in ("BUY", "STRONG BUY"):
        mc = multi_mc.get("63", multi_mc.get("60", {}))
        save_monte_carlo(symbol, mc)
        await cache.set(f"stock:{symbol}:monte_carlo", mc, TTL_REDIS_RESULTS)

        cached_bt = load_backtest(symbol)
        if cached_bt:
            bt = cached_bt
        else:
            bt = run_backtest(symbol, candles)
            save_backtest(symbol, bt)
        await cache.set(f"stock:{symbol}:backtest", bt, TTL_REDIS_RESULTS)

    from stocks.universe import get_group, get_sector
    return {
        "symbol":      symbol,
        "group":       get_group(symbol),
        "sector":      get_sector(symbol),
        "price":       feats.get("price", 0),
        "signal":      sig.get("signal", "REJECT"),
        "score":       sig.get("score", 0),
        "roc_252":     feats.get("roc_252", 0),
        "rs":          feats.get("rs", 1.0),
        "features":    feats,
        "signals":     sig,
        "monte_carlo": mc,
        "backtest":    bt,
    }


async def _recompute_from_db(cache, symbols: List[str], nifty_candles: List[Dict]) -> Dict:
    """
    Fast path: recompute features+signals from existing DB candles.
    No API calls. Used when Redis is empty but DB has data.
    """
    # First pass: compute all features to determine market regime
    # This ensures regime-aware scoring is consistent across all stocks
    all_features = []
    for sym in symbols:
        try:
            from stocks.database import get_candles as _gc
            candles = _gc(sym)
            if len(candles) >= 252:
                feats = compute_features(candles, nifty_candles)
                if feats:
                    all_features.append(feats)
        except Exception:
            pass

    # Compute market regime from breadth (% stocks above MA200)
    if all_features:
        above_ma200 = sum(1 for f in all_features if f.get("price", 0) > f.get("ma200", 0) and f.get("ma200", 0) > 0)
        breadth_pct = above_ma200 / len(all_features) * 100
        if breadth_pct >= 65:
            market_regime = "TRENDING"
        elif breadth_pct >= 45:
            market_regime = "MIXED"
        else:
            market_regime = "SIDEWAYS"
    else:
        market_regime = "MIXED"

    results = []
    for sym in symbols:
        try:
            r = await _compute_symbol(cache, sym, nifty_candles, market_regime=market_regime)
            if r:
                results.append(r)
        except Exception:
            pass
        await asyncio.sleep(0.01)

    return await _build_and_cache_summary(cache, results)


async def _build_and_cache_summary(cache, results: List[Dict]) -> Dict:
    """Build grouped output, flat list, top picks, market context and cache everything."""
    buy_candidates = [r for r in results if r.get("signal") in ("BUY", "STRONG BUY", "WATCH")]
    strong_buy     = [r for r in results if r.get("signal") in ("BUY", "STRONG BUY")]

    # Attach prob_up from MC for composite ranking
    for r in results:
        mc = r.get("monte_carlo", {})
        r["prob_up_mc"] = mc.get("prob_up", 50.0) if mc else 50.0

    grouped_ranked = rank_and_filter(strong_buy)

    grouped_output: Dict[str, List] = {}
    for group, stocks in grouped_ranked.items():
        grouped_output[group] = [
            build_stock_output(
                s["symbol"], s["features"], s["signals"],
                s.get("monte_carlo", {}), s.get("backtest", {}),
            )
            for s in stocks
        ]

    # Full flat list sorted by rank_score desc — NO cap
    all_buy_output = [
        build_stock_output(
            s["symbol"], s["features"], s["signals"],
            s.get("monte_carlo", {}), s.get("backtest", {}),
        )
        for s in sorted(
            strong_buy,
            key=lambda x: (
                x.get("signals", {}).get("rank_score", 0) if x.get("signals") else 0
            ),
            reverse=True,
        )
    ]

    # All computed stocks (including REJECT/WATCH)
    all_stocks_output = [
        build_stock_output(
            s["symbol"], s["features"], s["signals"],
            s.get("monte_carlo", {}), s.get("backtest", {}),
        )
        for s in sorted(
            results,
            key=lambda x: (
                x.get("signals", {}).get("rank_score", 0) if x.get("signals") else 0
            ),
            reverse=True,
        )
    ]

    # Top picks (sector-diverse, rank-sorted)
    from stocks.ranking import build_top_picks, build_market_context
    top_picks      = build_top_picks(all_buy_output)
    market_context = build_market_context(all_stocks_output, all_buy_output)

    summary = {
        "computed_at":    time.time(),
        "total_stocks":   len(results),
        "buy_signals":    len(strong_buy),
        "top_stocks":     all_buy_output,
        "all_stocks":     all_stocks_output,
        "grouped":        grouped_output,
        "top_picks":      top_picks,
        "market_context": market_context,
    }

    await cache.set(KEY_SUMMARY, summary, TTL_REDIS_SUMMARY)
    await cache.set(KEY_GROUPED, grouped_output, TTL_REDIS_SUMMARY)
    return summary


async def run_stock_pipeline(force_fetch: bool = False):
    """Full pipeline: optionally fetch from API, then compute everything."""
    cache   = get_cache()
    symbols = list(STOCK_UNIVERSE.keys())

    await _set_status(cache, "STARTING", "Initializing stock database")

    # Fetch NIFTY benchmark
    await _set_status(cache, "FETCHING", "Fetching NIFTY benchmark candles")
    nifty_candles = await _fetch_nifty_candles()

    # Fetch stock history if needed
    missing = [s for s in symbols if get_candle_count(s) < 252]
    if missing or force_fetch:
        await _set_status(cache, "FETCHING",
            f"Fetching 5-year history for {len(missing)} stocks "
            f"({len(symbols) - len(missing)} already in DB)")
        await fetch_all_full_history(symbols)

    # Compute
    await _set_status(cache, "COMPUTING",
        f"Computing features + signals + MC + backtest for {len(symbols)} stocks")
    summary = await _recompute_from_db(cache, symbols, nifty_candles)

    await _set_status(cache, "DONE",
        f"Pipeline complete — {summary['buy_signals']} BUY signals | "
        f"{summary['total_stocks']} stocks computed")
    return summary


async def run_stock_scheduler():
    """
    Main scheduler loop.
    On startup:
      - If Redis has data → nothing to do
      - If Redis empty but DB has data → recompute from DB (fast, no API)
      - If DB empty → run full pipeline (fetch + compute)
    Daily:
      - After 15:30 IST on weekdays → full pipeline with incremental fetch
    """
    cache = get_cache()
    init_db()

    last_run_date: Optional[str] = None

    # ── Startup: warm Redis from DB if needed ─────────────────────────────────
    await asyncio.sleep(3)   # let FastAPI finish starting

    # Restore last_run_date from Redis (survives container restarts)
    persisted_run_date = await cache.get("stocks:last_run_date")
    if persisted_run_date:
        last_run_date = persisted_run_date

    existing_summary = await cache.get(KEY_SUMMARY)
    if existing_summary:
        # Redis already warm — but don't mark as run today
        # so the 15:35 trigger still fires to fetch today's fresh candles
        pass
    else:
        # Redis is empty — check if DB has data
        db_stats = get_db_stats()
        symbols_in_db = db_stats.get("symbols_with_data", 0)

        if symbols_in_db >= 10:
            # DB has data — fast recompute (no API calls)
            await _set_status(cache, "COMPUTING",
                f"Warming Redis from DB ({symbols_in_db} stocks)...")
            try:
                nifty_candles = await _fetch_nifty_candles()
                symbols = list(STOCK_UNIVERSE.keys())
                summary = await _recompute_from_db(cache, symbols, nifty_candles)
                await _set_status(cache, "DONE",
                    f"Ready — {summary['buy_signals']} BUY signals from {summary['total_stocks']} stocks")
                last_run_date = _today_ist()
            except Exception as e:
                await _set_status(cache, "ERROR", str(e))
        else:
            # DB empty — only run full pipeline if market is closed
            if not is_market_open():
                try:
                    await run_stock_pipeline(force_fetch=False)
                    last_run_date = _today_ist()
                except Exception as e:
                    await _set_status(cache, "ERROR", str(e))

    # ── Main loop ─────────────────────────────────────────────────────────────
    while True:
        try:
            now   = datetime.now(IST)
            today = now.strftime("%Y-%m-%d")
            mins  = now.hour * 60 + now.minute

            # During market hours — do nothing
            if is_market_open():
                await asyncio.sleep(60)
                continue

            # Already ran today
            if last_run_date == today:
                # Sleep until next day's 15:35
                next_run = now.replace(hour=15, minute=35, second=0, microsecond=0)
                if next_run <= now:
                    # Already past today's close — sleep 23h
                    await asyncio.sleep(23 * 3600)
                else:
                    await asyncio.sleep(max(60, (next_run - now).total_seconds()))
                continue

            # Weekday after 15:30 — run full pipeline
            if now.weekday() < 5 and mins >= 15 * 60 + 35:
                await run_stock_pipeline(force_fetch=True)
                last_run_date = today
                # Persist so a restart within the same day doesn't re-run
                await cache.set("stocks:last_run_date", today, ttl=86400)
                await asyncio.sleep(3600)
                continue

            # Weekend or before market close — just sleep
            await asyncio.sleep(300)

        except Exception:
            await asyncio.sleep(300)
