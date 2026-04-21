"""
stocks/routes.py
Stock engine API — reads Redis (fast) with DB fallback.
NEVER fetches live data inside API routes.
"""

import time
import datetime
import pytz
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import ORJSONResponse

from core.redis_cache import get_cache
from stocks.market_timer import is_market_open
from stocks.universe import STOCK_UNIVERSE, GROUPS
from stocks.database import (
    get_db_stats, get_candle_count, load_features, load_signals,
    load_monte_carlo, load_backtest,
)

stocks_router = APIRouter(tags=["Stocks"])

IST = pytz.timezone("Asia/Kolkata")


def _build_insights(stocks: list) -> dict:
    """Compute market-level insights from the stock list."""
    if not stocks:
        return {}

    sector_counts: dict = {}
    for s in stocks:
        sec = s.get("sector", "OTHER")
        sector_counts[sec] = sector_counts.get(sec, 0) + 1
    top_sector = max(sector_counts, key=lambda k: sector_counts[k]) if sector_counts else "—"

    rs_vals = [s.get("relative_strength", 1.0) for s in stocks if s.get("relative_strength")]
    avg_rs  = round(sum(rs_vals) / len(rs_vals), 2) if rs_vals else 1.0

    bullish = sum(1 for s in stocks if s.get("trend") == "BULLISH")
    regime  = "TRENDING" if len(stocks) > 0 and bullish / len(stocks) > 0.6 else "MIXED"

    conf_vals = [s.get("confidence", 0) for s in stocks]
    avg_conf  = round(sum(conf_vals) / len(conf_vals), 1) if conf_vals else 0.0

    score_dist = {"10": 0, "8-9": 0, "6-7": 0, "5": 0}
    for s in stocks:
        sc = s.get("score", 0)
        if sc == 10:
            score_dist["10"] += 1
        elif sc >= 8:
            score_dist["8-9"] += 1
        elif sc >= 6:
            score_dist["6-7"] += 1
        else:
            score_dist["5"] += 1

    return {
        "top_sector":         top_sector,
        "sector_counts":      sector_counts,
        "avg_rs":             avg_rs,
        "market_regime":      regime,
        "avg_confidence":     avg_conf,
        "score_distribution": score_dist,
        "bullish_pct":        round(bullish / len(stocks) * 100, 1) if stocks else 0,
    }


def _fmt_last_updated(computed_at: float) -> str:
    if not computed_at:
        return ""
    dt = datetime.datetime.fromtimestamp(computed_at, tz=IST)
    return dt.strftime("%d %b %H:%M IST")


@stocks_router.get("/long-term-stocks")
async def get_long_term_stocks(
    min_score: int = Query(0, ge=0, le=10),
    limit:     int = Query(200, ge=1, le=500),
):
    """
    Returns computed stocks sorted by score.
    min_score=0 returns ALL computed stocks (frontend filters client-side).
    """
    cache        = get_cache()
    summary      = await cache.get("stocks:screener:summary")
    status       = await cache.get("stocks:pipeline:status") or {}
    db_stats_raw = get_db_stats()

    db_stats = {
        "total_stocks":   db_stats_raw.get("symbols_with_data", 0),
        "buy_signals":    0,
        "candles_cached": db_stats_raw.get("total_candles", 0),
        "last_run":       "",
    }

    pipeline_status = {
        "status":   status.get("status", "IDLE"),
        "stage":    status.get("detail", ""),
        "message":  "",
        "progress": 0,
    }

    if not summary:
        return ORJSONResponse({
            "computing":       not is_market_open(),
            "waiting":         is_market_open(),
            "stocks":          [],
            "insights":        {},
            "top_picks":       [],
            "market_context":  {},
            "pipeline_status": pipeline_status,
            "db_stats":        db_stats,
            "last_updated":    "",
            "timestamp":       time.time(),
        })

    # Use all_stocks if available (includes REJECT), else fall back to top_stocks
    all_stocks = summary.get("all_stocks") or summary.get("top_stocks", [])
    db_stats["buy_signals"] = summary.get("buy_signals", 0)

    # Apply min_score filter
    filtered = [s for s in all_stocks if s.get("score", 0) >= min_score] if min_score > 0 else all_stocks
    insights = _build_insights([s for s in filtered if s.get("signal") in ("BUY", "STRONG BUY")])

    computed_at  = summary.get("computed_at", 0)
    last_updated = _fmt_last_updated(computed_at)

    # ── Merge live market data into stock output ─────────────────────────────
    # Architecture:
    #   price (LTP)     → WS tick (real-time) — frontend applies from stockLtps store
    #   day context     → /marketfeed/quote batch (every 30s) — merged here server-side
    #   calculations    → historical pipeline — already in all_stocks
    #
    # We merge day context here so the REST response is complete.
    # The frontend additionally overrides price with WS tick for real-time updates.
    from stocks.live_prices import get_cached_live_prices
    live_prices = await get_cached_live_prices()

    if live_prices:
        merged = []
        for s in filtered[:limit]:
            sym = s.get("symbol", "")
            lp  = live_prices.get(sym)
            if lp and lp.get("ltp", 0) > 0:
                s = dict(s)   # never mutate cached object
                # Price from REST batch (WS tick will override this on frontend)
                s["price"]               = lp["ltp"]
                # Day context from /marketfeed/quote
                s["day_change"]          = lp.get("day_change", 0)
                s["day_change_pct"]      = lp.get("day_change_pct", 0)
                s["intraday_change_pct"] = lp.get("intraday_change_pct", 0)
                s["range_position"]      = lp.get("range_position", 50)
                s["live_open"]           = lp.get("open", 0)
                s["live_high"]           = lp.get("high", 0)
                s["live_low"]            = lp.get("low", 0)
                s["vwap"]                = lp.get("vwap", 0)
                s["volume"]              = lp.get("volume", 0)
                s["upper_circuit"]       = lp.get("upper_circuit", 0)
                s["lower_circuit"]       = lp.get("lower_circuit", 0)
                s["buy_pressure"]        = lp.get("buy_pressure", 50)
                s["live_price"]          = True
            merged.append(s)
        filtered_out = merged
    else:
        filtered_out = filtered[:limit]

    return ORJSONResponse({
        "computing":       False,
        "waiting":         False,
        "stocks":          filtered_out,
        "grouped":         summary.get("grouped", {}),
        "insights":        insights,
        "top_picks":       summary.get("top_picks", []),
        "market_context":  summary.get("market_context", {}),
        "pipeline_status": pipeline_status,
        "db_stats":        db_stats,
        "last_updated":    last_updated,
        "computed_at":     computed_at,
        "total_stocks":    summary.get("total_stocks", 0),
        "buy_signals":     summary.get("buy_signals", 0),
        "live_prices_available": bool(live_prices),
        "timestamp":       time.time(),
    })


@stocks_router.get("/stocks/group/{group_name}")
async def get_stocks_by_group(
    group_name: str,
    min_score:  int = Query(5, ge=1, le=10),
):
    group = group_name.upper()
    cache = get_cache()

    grouped = await cache.get("stocks:screener:grouped")
    if not grouped:
        summary = await cache.get("stocks:screener:summary")
        grouped = summary.get("grouped", {}) if summary else {}

    stocks   = grouped.get(group, [])
    filtered = [s for s in stocks if s.get("score", 0) >= min_score]

    return ORJSONResponse({
        "group":       group,
        "count":       len(filtered),
        "stocks":      filtered,
        "market_open": is_market_open(),
        "timestamp":   time.time(),
    })


@stocks_router.get("/stock/{symbol}")
async def get_stock(symbol: str):
    sym   = symbol.upper()
    cache = get_cache()

    if sym not in STOCK_UNIVERSE:
        raise HTTPException(404, f"{sym} not in universe")

    feats = await cache.get(f"stock:{sym}:features") or load_features(sym)
    sigs  = await cache.get(f"stock:{sym}:signals")  or load_signals(sym)
    mc    = await cache.get(f"stock:{sym}:monte_carlo") or load_monte_carlo(sym)
    bt    = await cache.get(f"stock:{sym}:backtest")    or load_backtest(sym)

    if not feats:
        return ORJSONResponse({
            "symbol":       sym,
            "status":       "NO_DATA",
            "candle_count": get_candle_count(sym),
            "message":      "Features not yet computed. Pipeline runs after market close.",
        })

    from stocks.universe import get_group, get_sector
    from stocks.ranking import build_stock_output
    output = build_stock_output(sym, feats, sigs or {}, mc or {}, bt or {})

    return ORJSONResponse({
        **output,
        "status":       "OK",
        "candle_count": get_candle_count(sym),
        "timestamp":    time.time(),
    })


@stocks_router.get("/stock/{symbol}/fundamentals")
async def get_stock_fundamentals(symbol: str):
    """
    Fetch fundamental data from screener.in.
    Cached in Redis for 24h.
    """
    sym   = symbol.upper()
    cache = get_cache()

    if sym not in STOCK_UNIVERSE:
        raise HTTPException(404, f"{sym} not in universe")

    cache_key = f"stock:{sym}:fundamentals"
    cached    = await cache.get(cache_key)
    if cached:
        return ORJSONResponse(cached)

    try:
        from stocks.screener_scraper import fetch_fundamentals
        result = await fetch_fundamentals(sym)
        if result.get("status") == "OK":
            await cache.set(cache_key, result, ttl=86400)
        return ORJSONResponse(result)
    except Exception as e:
        return ORJSONResponse({
            "symbol":  sym,
            "status":  "ERROR",
            "message": str(e),
        })


@stocks_router.get("/stock/{symbol}/simulate")
async def simulate_stock_investment(
    symbol:     str,
    investment: float = Query(100000, ge=1000, le=100000000),
    horizon:    int   = Query(252, ge=5, le=504),
):
    """
    Investment simulator — instant when MC is pre-cached, fast fallback otherwise.
    horizon: 60=2M, 252=1Y
    """
    sym   = symbol.upper()
    cache = get_cache()

    if sym not in STOCK_UNIVERSE:
        raise HTTPException(404, f"{sym} not in universe")

    from stocks.database import get_candles, load_features
    from stocks.monte_carlo import simulate_from_cache, simulate_investment, run_multi_horizon_mc
    import numpy as np

    # ── 1. Try instant path: use pre-cached multi-horizon MC ─────────────────
    cached_horizons = await cache.get(f"stock:{sym}:mc_horizons")
    if cached_horizons:
        feats = await cache.get(f"stock:{sym}:features") or load_features(sym)
        price = feats.get("price", 0) if feats else 0
        if price > 0:
            result = simulate_from_cache(cached_horizons, price, investment, horizon)
            if result:
                result["symbol"] = sym
                result["status"] = "OK"
                return ORJSONResponse(result)

    # ── 2. Try single-horizon cached MC ──────────────────────────────────────
    cached_mc = await cache.get(f"stock:{sym}:monte_carlo")
    if cached_mc and "return_pcts" in cached_mc:
        feats = await cache.get(f"stock:{sym}:features") or load_features(sym)
        price = feats.get("price", 0) if feats else 0
        if price > 0:
            result = simulate_from_cache(cached_mc, price, investment, horizon)
            if result:
                result["symbol"] = sym
                result["status"] = "OK"
                return ORJSONResponse(result)

    # ── 3. Full simulation fallback (first time for this stock) ───────────────
    candles = get_candles(sym)
    if len(candles) < 60:
        return ORJSONResponse({"symbol": sym, "status": "NO_DATA"})

    closes  = np.array([c["close"] for c in candles], dtype=np.float64)
    price   = float(closes[-1])
    log_ret = np.log(closes[1:] / closes[:-1])
    window  = log_ret  # pass full history — _estimate_params slices internally

    # Pre-compute and cache multi-horizon MC so next call is instant
    multi_mc = run_multi_horizon_mc(sym, price, window)
    await cache.set(f"stock:{sym}:mc_horizons", multi_mc, ttl=86400 * 3)

    # Use cached result for this request
    result = simulate_from_cache(multi_mc, price, investment, horizon)
    if result:
        result["symbol"] = sym
        result["status"] = "OK"
        return ORJSONResponse(result)

    # Absolute fallback: full simulation
    result = simulate_investment(price, window, investment, horizon)
    result["symbol"] = sym
    result["status"] = "OK"
    return ORJSONResponse(result)


@stocks_router.get("/stock/{symbol}/backtest")
async def get_stock_backtest(symbol: str):
    sym   = symbol.upper()
    cache = get_cache()
    if sym not in STOCK_UNIVERSE:
        raise HTTPException(404, f"{sym} not in universe")
    bt = await cache.get(f"stock:{sym}:backtest") or load_backtest(sym)
    if not bt:
        return ORJSONResponse({"symbol": sym, "status": "NO_DATA"})
    return ORJSONResponse({"symbol": sym, "status": "OK", "backtest": bt, "timestamp": time.time()})


@stocks_router.get("/stock/{symbol}/monte-carlo")
async def get_stock_monte_carlo(symbol: str, horizon: int = Query(30, ge=5, le=90)):
    sym   = symbol.upper()
    cache = get_cache()
    if sym not in STOCK_UNIVERSE:
        raise HTTPException(404, f"{sym} not in universe")
    mc = await cache.get(f"stock:{sym}:monte_carlo") or load_monte_carlo(sym)
    if not mc:
        return ORJSONResponse({"symbol": sym, "status": "NO_DATA"})
    return ORJSONResponse({"symbol": sym, "status": "OK", "monte_carlo": mc, "timestamp": time.time()})


@stocks_router.get("/stocks/status")
async def get_stocks_status():
    cache    = get_cache()
    summary  = await cache.get("stocks:screener:summary")
    status   = await cache.get("stocks:pipeline:status") or {}
    db_stats = get_db_stats()
    return ORJSONResponse({
        "market_open":      is_market_open(),
        "pipeline_status":  status.get("status", "IDLE"),
        "pipeline_detail":  status.get("detail", ""),
        "pipeline_ready":   summary is not None,
        "db_stats":         db_stats,
        "buy_signals":      summary.get("buy_signals", 0) if summary else 0,
        "computed_at":      summary.get("computed_at", 0) if summary else 0,
        "groups_available": list(summary.get("grouped", {}).keys()) if summary else [],
        "timestamp":        time.time(),
    })


@stocks_router.get("/stocks/live-prices")
async def get_live_stock_prices():
    """
    Returns live prices for all stocks fetched from Dhan.
    Backend fetches from Dhan every 30s and caches in Redis.
    Frontend reads from here — never hits Dhan directly.

    Returns:
      {
        available: bool,
        market_open: bool,
        prices: { SYMBOL: { ltp, day_change, day_change_pct, vwap, volume, ... } },
        fetched_at: timestamp,
        count: int,
      }
    """
    from stocks.live_prices import get_cached_live_prices, KEY_LIVE_PRICES_TS
    cache  = get_cache()
    prices = await get_cached_live_prices()
    meta   = await cache.get(KEY_LIVE_PRICES_TS) or {}

    return ORJSONResponse({
        "available":   bool(prices),
        "market_open": is_market_open(),
        "prices":      prices,
        "fetched_at":  meta.get("ts", 0) if isinstance(meta, dict) else meta,
        "count":       meta.get("count", len(prices)) if isinstance(meta, dict) else len(prices),
        "elapsed_s":   meta.get("elapsed", 0) if isinstance(meta, dict) else 0,
        "timestamp":   time.time(),
    })
