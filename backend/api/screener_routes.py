"""
Screener API Routes
====================
GET /api/screener  — returns pre-computed pipeline result from Redis.
GET /api/screener/stock/{symbol} — returns latest data for one stock.
NEVER fetches data. Reads Redis only.
"""

import time
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import ORJSONResponse

from core.redis_cache import get_cache

screener_router = APIRouter(tags=["Screener"])


@screener_router.get("/screener")
async def get_screener():
    """
    Returns the latest quant pipeline result.
    Computed every 10s by the background pipeline worker.
    Returns 503 if no data available yet.
    """
    cache  = get_cache()
    result = await cache.get("quant:screener:result")

    if not result:
        return ORJSONResponse({
            "status": "LOADING",
            "message": "Intraday screener runs during market hours only. No live data available.",
            "pipeline_stats": {"universe_size": 0, "filtered_layer2": 0, "final_candidates": 0},
            "top_candidates": [],
            "layer2_ranked":  [],
        })

    return ORJSONResponse(result)


@screener_router.get("/screener/stock/{symbol}")
async def get_stock_latest(symbol: str):
    """Returns latest price data for a single stock from the data worker."""
    cache  = get_cache()
    latest = await cache.get(f"stock:{symbol.upper()}:latest")

    if not latest:
        raise HTTPException(404, f"No data for {symbol}. Market may be closed or symbol not in universe.")

    history = await cache.ts_get_last(f"stock:{symbol.upper()}:history", n=50)

    return ORJSONResponse({
        "symbol":  symbol.upper(),
        "latest":  latest,
        "history": history,
        "count":   len(history),
    })


@screener_router.get("/screener/status")
async def get_screener_status():
    """Returns pipeline health — how many stocks have data."""
    cache = get_cache()
    from quant.instrument_loader import get_loaded_ids
    syms  = list(get_loaded_ids().keys())
    count = 0
    for sym in syms:
        d = await cache.get(f"stock:{sym}:latest")
        if d:
            count += 1
    result = await cache.get("quant:screener:result")
    return ORJSONResponse({
        "stocks_with_data": count,
        "universe_size":    len(syms),
        "pipeline_ready":   result is not None,
        "timestamp":        time.time(),
    })
