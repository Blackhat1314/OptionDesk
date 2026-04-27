"""
api/ml_routes.py
================
ML signal REST endpoint — serves from Redis cache so page refresh works.
"""

from fastapi import APIRouter, Query, Depends
from fastapi.responses import ORJSONResponse
from auth import require_auth

ml_router = APIRouter(tags=["ML Signals"])


@ml_router.get("/ml-signals")
async def get_ml_signals(
    symbol: str = Query("NIFTY"),
    _user: str = Depends(require_auth),
):
    from features.ml_signals import get_ml_signals as _get, is_model_available
    from core.redis_cache import get_cache

    if not is_model_available():
        return ORJSONResponse({
            "signals": [], "model_loaded": False,
            "status": "Model files not found",
            "threshold": 0.65, "last_run": 0, "next_run_in": 0,
        })

    # Serve from Redis (persisted from last inference — survives page refresh)
    cache = get_cache()
    redis_sigs = await cache.get(f"ml:signals:{symbol}")
    if redis_sigs:
        data = _get()
        return ORJSONResponse({
            "signals":      redis_sigs,
            "model_loaded": True,
            "status":       "ok",
            "symbol":       symbol,
            "last_run":     data.get("last_run", 0),
            "next_run_in":  data.get("next_run_in", 0),
            "threshold":    0.65,
        })

    # Fall back to in-memory
    data = _get()
    return ORJSONResponse({**data, "symbol": symbol, "status": "ok"})
