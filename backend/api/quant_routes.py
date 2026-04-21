import time
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import ORJSONResponse

from features.regime   import get_regime, push_price
from features.volatility import get_iv_analysis, get_vol_surface
from features.gex      import get_gex_timeseries_response, build_gex_profile
from features.oi_flow  import get_oi_flow
from features.vwap     import get_vwap_response, get_vwap_engine
from services.alert_engine import get_alert_engine
from api.websocket_manager import get_market_state
from core.redis_cache import get_cache
from core.strike_selector import select_strikes, INDEX_CONFIG

quant_router = APIRouter(tags=["Quant Features"])


# ─── Feature 1: Market Regime ─────────────────────────────────────────────────

@quant_router.get("/regime")
async def get_market_regime(symbol: str = Query("NIFTY")):
    """
    Market regime classification.

    Returns:
      {
        "regime": "TRENDING" | "RANGE_BOUND" | "VOLATILE" | "CHAOTIC",
        "entropy": float,          # Shannon entropy (normalized 0–1)
        "volatility_20d": float,   # annualized realized vol %
        "trend_strength": float,   # |mean/std| of returns
        "hurst": float,            # H > 0.5 = trending, < 0.5 = reverting
        "signal": str,             # trading guidance
        "rolling_vol_20": [...],   # for chart
        "rolling_entropy": [...],
        "log_returns": [...]
      }
    """
    result = get_regime(symbol)
    return ORJSONResponse(result)


# ─── Feature 2: IV vs Realized Volatility ────────────────────────────────────

@quant_router.get("/iv-analysis")
async def iv_analysis(symbol: str = Query("NIFTY")):
    """IV vs Realized Volatility — uses Redis-persisted IV history for rank/percentile."""
    state      = get_market_state()
    cache      = get_cache()
    summary    = state.get_sync(f"summary:{symbol}")
    current_iv = summary.get("atm_iv", 0.0) if summary else 0.0

    # Seed VolSurface from Redis history if in-memory is sparse
    surf = get_vol_surface(symbol)
    if len(surf._iv_history) < 5:
        redis_iv = await cache.ts_get_all(cache.key_iv_history(symbol))
        for entry in redis_iv:
            iv_val = entry.get("iv", 0) if isinstance(entry, dict) else entry
            if iv_val > 0:
                surf.push(iv_val, entry.get("ts") if isinstance(entry, dict) else None)

    result = get_iv_analysis(symbol, current_iv)
    return ORJSONResponse(result)


# ─── Feature 3: GEX Time-Series ──────────────────────────────────────────────

@quant_router.get("/gex-timeseries")
async def gex_timeseries(symbol: str = Query("NIFTY")):
    """GEX/DEX time-series — merges Redis-persisted history with in-memory snapshots."""
    cache = get_cache()

    # Get Redis-persisted history (survives restarts)
    redis_history = await cache.ts_get_all(cache.key_gex_history(symbol))

    # Get in-memory snapshots (current session)
    in_memory = get_gex_timeseries_response(symbol)
    in_memory_ts = in_memory.get("timeseries", [])

    # Merge: Redis history + in-memory (deduplicate by ts)
    seen_ts = set()
    merged = []
    for snap in redis_history + in_memory_ts:
        ts = snap.get("ts", 0)
        if ts not in seen_ts:
            seen_ts.add(ts)
            merged.append(snap)
    merged.sort(key=lambda x: x.get("ts", 0))

    # Forward-fill: never let GEX/DEX drop to zero unless true value is zero
    last_valid_gex = 0.0
    last_valid_dex = 0.0
    for snap in merged:
        if snap.get("gex", 0) != 0:
            last_valid_gex = snap["gex"]
        elif last_valid_gex != 0:
            snap["gex"] = last_valid_gex
        if snap.get("dex", 0) != 0:
            last_valid_dex = snap["dex"]
        elif last_valid_dex != 0:
            snap["dex"] = last_valid_dex

    # Recompute stats from merged series
    import numpy as np
    if merged:
        gex_arr = [s.get("gex", 0) for s in merged[-20:]]
        dex_arr = [s.get("dex", 0) for s in merged[-20:]]
        stats = {
            "gex_mean": round(float(np.mean(gex_arr)), 4),
            "gex_std":  round(float(np.std(gex_arr)),  4),
            "gex_min":  round(float(np.min(gex_arr)),  4),
            "gex_max":  round(float(np.max(gex_arr)),  4),
            "net_dealer_bias": "LONG" if float(np.mean(dex_arr)) > 0 else "SHORT",
        }
    else:
        stats = in_memory.get("stats", {})

    return {
        "symbol":           symbol,
        "timeseries":       merged[-200:],   # last 200 snapshots
        "stats":            stats,
        "latest":           merged[-1] if merged else in_memory.get("latest", {}),
        "gamma_flip_event": in_memory.get("gamma_flip_event"),
        "gex_spike":        in_memory.get("gex_spike"),
        "timestamp":        time.time(),
    }


@quant_router.get("/gex-profile")
async def gex_profile(symbol: str = Query("NIFTY")):
    """GEX profile sorted by strike for bar chart."""
    state = get_market_state()
    exposure = state.get_sync(f"exposure:{symbol}")
    if not exposure:
        raise HTTPException(404, "No exposure data — trigger a chain refresh first")
    exposures = exposure.get("exposures", [])
    profile = build_gex_profile(exposures)
    return ORJSONResponse({
        "symbol":  symbol,
        "profile": profile,
        "spot":    exposure.get("spot_price", 0),
        "gamma_flip": exposure.get("gamma_flip_level", 0),
        "call_wall":  exposure.get("call_wall", 0),
        "put_wall":   exposure.get("put_wall", 0),
    })


# ─── Feature 4: OI Flow Intelligence ─────────────────────────────────────────

@quant_router.get("/oi-flow")
async def oi_flow(symbol: str = Query("NIFTY")):
    """
    OI flow intelligence per strike.

    Returns:
      {
        "flows": [{"strike", "option_type", "flow", "color", "oi", "oi_change", "price"}],
        "dominant_strikes": [...top 10 by abs OI change...],
        "flow_counts": {"LONG_BUILDUP": N, "SHORT_BUILDUP": N, ...},
        "heatmap": [{"ts", "spot", "22500": {"oi_change", "flow", "color"}, ...}]
      }

    Flow types:
      LONG_BUILDUP:   Price↑ & OI↑ (bullish accumulation)
      SHORT_BUILDUP:  Price↓ & OI↑ (bearish accumulation)
      SHORT_COVERING: Price↑ & OI↓ (short squeeze)
      LONG_UNWINDING: Price↓ & OI↓ (profit booking)
    """
    result = get_oi_flow(symbol)
    return ORJSONResponse(result)


# ─── Feature 5: VWAP System ──────────────────────────────────────────────────

@quant_router.get("/vwap")
async def vwap(symbol: str = Query("NIFTY")):
    """
    Intraday VWAP with ±1σ/±2σ bands and price bias signal.

    Returns:
      {
        "vwap": float,
        "upper_band_1std": float,
        "lower_band_1std": float,
        "upper_band_2std": float,
        "lower_band_2std": float,
        "bias": {"signal": "BULLISH"|"BEARISH"|"AT_VWAP", "z_score": float},
        "signal": str,
        "chart_series": [{"ts", "price", "vwap", "upper1", "lower1", ...}]
      }
    """
    state   = get_market_state()
    summary = state.get_sync(f"summary:{symbol}")
    current = summary.get("spot_price", 0.0) if summary else 0.0
    result  = get_vwap_response(symbol, current)
    return ORJSONResponse(result)


# ─── Feature 6: Alert Engine ──────────────────────────────────────────────────

@quant_router.get("/alerts")
async def get_alerts(
    symbol:   Optional[str] = Query(None),
    limit:    int = Query(50, ge=1, le=200),
    severity: Optional[str] = Query(None),
):
    """
    Get recent alerts.

    Returns list of:
      {
        "type": "GAMMA_FLIP" | "IV_SPIKE" | "OI_BUILDUP" | ...,
        "severity": "INFO" | "WARNING" | "CRITICAL",
        "symbol": str,
        "message": str,
        "data": {...},
        "timestamp": float,
        "acknowledged": bool
      }
    """
    engine = get_alert_engine()
    alerts = engine.get_alerts(symbol=symbol, limit=limit, severity=severity)
    return ORJSONResponse({
        "alerts":    alerts,
        "total":     len(alerts),
        "timestamp": time.time(),
    })


@quant_router.get("/alerts/unread")
async def get_unread_alerts():
    engine = get_alert_engine()
    return ORJSONResponse({"alerts": engine.get_unacknowledged()})


@quant_router.post("/alerts/acknowledge/{idx}")
async def acknowledge_alert(idx: int):
    get_alert_engine().acknowledge(idx)
    return {"status": "ok"}


# ─── Combined Decision Engine Snapshot ───────────────────────────────────────

@quant_router.get("/decision-engine")
async def decision_engine(symbol: str = Query("NIFTY")):
    """
    Structured signal matrix per spec:

    1. INSUFFICIENT_DATA  → if HV == 0 or IV Rank missing or regime is INSUFFICIENT_DATA
    2. SELL_OPTIONS       → IV > HV AND IV_Rank > 50 AND GEX > 0
    3. BUY_OPTIONS        → IV < HV AND IV_Rank < 20 AND GEX < 0
    4. NO_TRADE           → all other conditions (including market closed)
    """
    import pytz
    from datetime import datetime as _dt

    state      = get_market_state()
    summary    = state.get_sync(f"summary:{symbol}") or {}
    iv_cache   = state.get_sync(f"iv:{symbol}") or {}
    current_iv = summary.get("atm_iv", 0.0)
    spot       = summary.get("spot_price", 0.0)

    iv_rank = iv_cache.get("iv_rank", 0.0)
    hv_30d  = iv_cache.get("historical_vol_30d", 0.0)

    # Market closed check
    ist  = pytz.timezone("Asia/Kolkata")
    now  = _dt.now(ist)
    mins = now.hour * 60 + now.minute
    market_closed = not (now.weekday() < 5 and 9 * 60 + 15 <= mins <= 15 * 60 + 30)

    regime    = get_regime(symbol)
    iv_data   = get_iv_analysis(symbol, current_iv)
    gex_ts    = get_gex_timeseries_response(symbol)
    oi_data   = get_oi_flow(symbol)
    vwap_data = get_vwap_response(symbol, spot)
    alerts    = get_alert_engine().get_alerts(symbol=symbol, limit=10)

    total_gex = gex_ts.get("latest", {}).get("gex", 0.0) or 0.0

    # ── Condition 1: INSUFFICIENT_DATA ───────────────────────────────────────
    regime_status = regime.get("regime", "INSUFFICIENT_DATA")
    if (
        hv_30d == 0
        or current_iv <= 0
        or spot <= 0
        or regime_status == "INSUFFICIENT_DATA"
    ):
        return ORJSONResponse({
            "symbol":        symbol,
            "status":        "INSUFFICIENT_DATA",
            "signal":        "NO_TRADE",
            "confidence":    0,
            "reason":        "Insufficient historical data — HV or IV not yet available",
            "market_closed": market_closed,
            "spot":          spot,
            "iv":            iv_data,
            "gex":           {},
            "vwap":          vwap_data,
            "pcr":           summary.get("pcr_oi", 0),
            "max_pain":      summary.get("max_pain", 0),
            "alerts":        alerts[:5],
            "timestamp":     time.time(),
        })

    # ── Market closed: NO_TRADE regardless of signal ──────────────────────────
    if market_closed:
        return ORJSONResponse({
            "symbol":        symbol,
            "status":        "MARKET_CLOSED",
            "signal":        "NO_TRADE",
            "confidence":    0,
            "reason":        "Market is closed — signals disabled outside trading hours",
            "market_closed": True,
            "spot":          spot,
            "iv":            iv_data,
            "gex":           {"total_gex": total_gex},
            "vwap":          vwap_data,
            "pcr":           summary.get("pcr_oi", 0),
            "max_pain":      summary.get("max_pain", 0),
            "alerts":        alerts[:5],
            "timestamp":     time.time(),
        })

    # ── Signal matrix ─────────────────────────────────────────────────────────
    # Condition 2: High IV + Stabilizing Market → SELL_OPTIONS
    if current_iv > hv_30d and iv_rank > 50 and total_gex > 0:
        signal     = "SELL_OPTIONS"
        confidence = _compute_confidence(current_iv, hv_30d, iv_rank, total_gex, vwap_data, summary)
        reason     = f"High IV Premium ({current_iv:.1f}% > HV {hv_30d:.1f}%) with Positive Gamma (GEX={total_gex:.3f}Cr)"

    # Condition 3: Low IV + Chaotic Market → BUY_OPTIONS
    elif current_iv < hv_30d and iv_rank < 20 and total_gex < 0:
        signal     = "BUY_OPTIONS"
        confidence = _compute_confidence(current_iv, hv_30d, iv_rank, total_gex, vwap_data, summary)
        reason     = f"Volatility Expansion Expected ({current_iv:.1f}% < HV {hv_30d:.1f}%) with Negative Gamma (GEX={total_gex:.3f}Cr)"

    # Default: conditions not met
    else:
        signal     = "NO_TRADE"
        confidence = 0
        reason     = f"Signal conditions not met — IV={current_iv:.1f}% HV={hv_30d:.1f}% IVR={iv_rank:.0f} GEX={total_gex:.3f}Cr"

    return ORJSONResponse({
        "symbol":        symbol,
        "status":        "OK",
        "signal":        signal,
        "confidence":    confidence,
        "reason":        reason,
        "market_closed": market_closed,
        "spot":          spot,
        "score":      _compute_composite_score(regime, iv_data, gex_ts, vwap_data, summary),
        "bias":       "BULLISH" if signal == "BUY_OPTIONS" else ("BEARISH" if signal == "SELL_OPTIONS" else "NEUTRAL"),
        "regime":     {
            "regime":     regime.get("regime"),
            "volatility": regime.get("volatility_20d"),
            "entropy":    regime.get("entropy"),
            "signal":     regime.get("signal"),
        },
        "iv": {
            "current_iv": current_iv,
            "hv_30d":     hv_30d,
            "rv_30d":     iv_data.get("rv_30d"),
            "spread":     round(current_iv - hv_30d, 2),
            "signal":     iv_data.get("signal"),
            "iv_rank":    iv_rank,
            "iv_percentile": iv_cache.get("iv_percentile", 0.0),
        },
        "gex": {
            "total_gex":   total_gex,
            "gamma_flip":  gex_ts.get("latest", {}).get("gamma_flip"),
            "dealer_bias": gex_ts.get("stats", {}).get("net_dealer_bias"),
            "flip_event":  gex_ts.get("gamma_flip_event"),
        },
        "oi_flow": {
            "dominant":    oi_data.get("dominant_strikes", [])[:5],
            "flow_counts": oi_data.get("flow_counts"),
        },
        "vwap": {
            "vwap":    vwap_data.get("vwap"),
            "signal":  vwap_data.get("signal"),
            "z_score": vwap_data.get("bias", {}).get("z_score"),
        },
        "pcr":      summary.get("pcr_oi"),
        "max_pain": summary.get("max_pain"),
        "alerts":   alerts[:5],
        "timestamp": time.time(),
    })


def _compute_confidence(
    current_iv: float, hv: float, iv_rank: float,
    total_gex: float, vwap: dict, summary: dict,
) -> int:
    """
    Compute signal confidence score 0–100.
    Factors: IV/HV spread magnitude, IV Rank extremity, GEX magnitude, PCR.
    """
    score = 0.0

    # IV/HV spread (max 40 pts)
    if hv > 0:
        spread_ratio = abs(current_iv - hv) / hv
        score += min(spread_ratio * 40, 40)

    # IV Rank extremity (max 30 pts): rank near 0 or 100 = high confidence
    rank_extremity = abs(iv_rank - 50) / 50   # 0 at rank=50, 1 at rank=0 or 100
    score += rank_extremity * 30

    # GEX magnitude (max 20 pts)
    gex_score = min(abs(total_gex) * 2, 20)
    score += gex_score

    # VWAP alignment (max 10 pts)
    vwap_sig = vwap.get("signal", "NEUTRAL")
    if vwap_sig in ("BULLISH", "BEARISH"):
        score += 10

    return min(int(round(score)), 100)


def _compute_composite_score(
    regime: dict, iv: dict, gex: dict, vwap: dict, summary: dict,
) -> float:
    """
    Composite directional score: -1 (bearish) to +1 (bullish).
    Blends: VWAP signal + GEX sign + IV signal + PCR + regime.
    """
    score = 0.0

    # VWAP bias (weight 0.30)
    vwap_sig = vwap.get("signal", "NEUTRAL")
    if vwap_sig == "BULLISH":   score += 0.30
    elif vwap_sig == "BEARISH": score -= 0.30

    # GEX sign (positive GEX = stabilizing = slight bullish, weight 0.20)
    latest_gex = gex.get("latest", {}).get("gex", 0.0) or 0.0
    if latest_gex > 0:   score += 0.15
    elif latest_gex < 0: score -= 0.15

    # IV signal (sell signal = market complacent → slight bearish contrarian, weight 0.20)
    iv_sig = iv.get("signal", "NEUTRAL")
    if iv_sig == "SELL_OPTIONS":  score -= 0.10   # elevated IV = fear
    elif iv_sig == "BUY_OPTIONS": score += 0.10   # low IV = calm

    # PCR (weight 0.20)
    pcr = float(summary.get("pcr_oi") or 0)
    if pcr > 1.3:   score += 0.15   # high put buying = contrarian bullish
    elif pcr < 0.7: score -= 0.15   # low put buying = contrarian bearish

    # Regime (weight 0.10)
    reg = regime.get("regime", "")
    if reg == "TRENDING":    score += 0.05
    elif reg == "CHAOTIC":   score -= 0.10

    return round(max(-1.0, min(1.0, score)), 3)


# ─── Strike Selection Endpoint ────────────────────────────────────────────────

@quant_router.get("/strikes")
async def get_strikes(
    index: str = Query("NIFTY", description="Index symbol"),
    count: int = Query(20, ge=5, le=100, description="Exact number of strikes to return"),
    mode:  str = Query("fixed", description="Selection mode: fixed | smart"),
):
    """
    GET /api/strikes

    Returns exactly `count` strikes around ATM for the given index.

    Fixed mode: symmetric window around ATM after range filter.
    Smart mode: score-based (OI + volume + ATM proximity), top N by score.

    Response:
      {
        "index":   "FINNIFTY",
        "spot":    21500.0,
        "atm":     21500.0,
        "strikes": [21200, 21250, ...],
        "count":   10,
        "mode":    "fixed",
        "range":   600,
        "config":  {...}
      }
    """
    state = get_market_state()

    # Get current spot from cached summary
    summary = state.get_sync(f"summary:{index}") or {}
    spot    = summary.get("spot_price", 0.0)

    if spot <= 0:
        raise HTTPException(404, f"No spot price available for {index}. Wait for data to load.")

    # Get chain rows for smart mode scoring
    chain_dict = state.get_sync(f"chain:{index}") or {}
    rows       = chain_dict.get("rows", [])

    # All strikes from cached chain
    all_strikes = [float(r.get("strike", 0)) for r in rows if r.get("strike")]

    if not all_strikes:
        raise HTTPException(404, f"No option chain data for {index}. Wait for data to load.")

    cfg    = INDEX_CONFIG.get(index, {"range": 1000, "step": 50, "lot": 50})
    result = select_strikes(
        symbol      = index,
        spot        = spot,
        all_strikes = all_strikes,
        count       = count,
        mode        = mode,
        rows        = rows if mode == "smart" else None,
    )

    return {
        **result,
        "range":  cfg["range"],
        "step":   cfg.get("step", 50),
        "config": cfg,
        "timestamp": time.time(),
    }
