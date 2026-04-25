"""
api/ml_routes.py
================
ML signal REST endpoint.
Follows the same pattern as api/intelligence_routes.py:
  - Check in-memory state first
  - Return empty but valid response if not ready
  - Never block on computation
"""

from fastapi import APIRouter, Query
from fastapi.responses import ORJSONResponse

from auth import require_auth
from fastapi import Depends

ml_router = APIRouter(tags=["ML Signals"])


@ml_router.get("/ml-signals")
async def get_ml_signals(
    symbol: str = Query("NIFTY"),
    _user: str = Depends(require_auth),
):
    """
    Returns current ML directional signals for ATM ±2 strikes.
    Signals are computed every 15 minutes from the option chain candle buffer.
    Only returns signals with confidence >= 0.65 (82% historical accuracy).
    """
    from features.ml_signals import get_ml_signals as _get, is_model_available

    if not is_model_available():
        return ORJSONResponse({
            "signals":      [],
            "model_loaded": False,
            "status":       "Model files not found. Copy model_v2/ to /app/data/ml_model/",
            "threshold":    0.65,
            "last_run":     0,
            "next_run_in":  0,
        })

    data = _get()
    return ORJSONResponse({**data, "symbol": symbol, "status": "ok"})
