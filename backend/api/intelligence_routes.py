"""
Intelligence Analytics Engine
================================
Provides institutional-grade analytics:
  1. Time-Series Intelligence (delta GEX, delta OI, delta IV)
  2. OI Classification per strike
  3. Expected Move Engine
  4. IV Regime Classification
  5. Smart Signal Layer (independent of decision engine)
  6. Heatmap data (OI, IV, GEX by strike)
"""

import time
import math
from typing import Dict, List, Optional
from collections import deque
from fastapi import APIRouter, Query
from fastapi.responses import ORJSONResponse

from api.websocket_manager import get_market_state
from core.redis_cache import get_cache
from features.gex import get_gex_timeseries_response, get_gex_store
from features.oi_flow import get_oi_store, get_oi_flow
from features.vwap import get_vwap_response
from features.regime import get_regime, get_price_buffer
from features.volatility import get_iv_analysis, get_vol_surface
from services.alert_engine import get_alert_engine

intelligence_router = APIRouter(tags=["Intelligence"])

# ─── Rolling delta buffers (in-memory, per symbol) ───────────────────────────

class DeltaBuffer:
    """Tracks rolling deltas for GEX, OI, IV."""
    def __init__(self, maxlen: int = 500):
        self._buf: deque = deque(maxlen=maxlen)

    def push(self, entry: Dict):
        self._buf.append(entry)

    def get_all(self) -> List[Dict]:
        return list(self._buf)

    def latest(self) -> Optional[Dict]:
        return self._buf[-1] if self._buf else None


_delta_buffers: Dict[str, DeltaBuffer] = {}

def get_delta_buffer(symbol: str) -> DeltaBuffer:
    if symbol not in _delta_buffers:
        _delta_buffers[symbol] = DeltaBuffer()
    return _delta_buffers[symbol]


def record_intelligence_snapshot(symbol: str, exposure_dict: Dict, iv_dict: Dict, chain_dict: Dict):
    """
    Called from main.py on every chain refresh.
    Computes deltas vs previous snapshot and stores in rolling buffer.
    """
    buf = get_delta_buffer(symbol)
    prev = buf.latest()

    gex = exposure_dict.get("total_gex", 0.0) or 0.0
    dex = exposure_dict.get("total_dex", 0.0) or 0.0
    iv  = iv_dict.get("current_iv", 0.0) or 0.0

    # Compute total OI from chain rows
    rows = chain_dict.get("rows", [])
    total_call_oi = sum(r.get("call", {}).get("oi", 0) for r in rows)
    total_put_oi  = sum(r.get("put",  {}).get("oi", 0) for r in rows)
    total_oi = total_call_oi + total_put_oi

    delta_gex = round(gex - prev.get("gex", gex), 4) if prev else 0.0
    delta_oi  = total_oi - prev.get("total_oi", total_oi) if prev else 0
    delta_iv  = round(iv - prev.get("iv", iv), 2) if prev else 0.0

    buf.push({
        "ts":        time.time(),
        "gex":       gex,
        "dex":       dex,
        "iv":        iv,
        "total_oi":  total_oi,
        "call_oi":   total_call_oi,
        "put_oi":    total_put_oi,
        "delta_gex": delta_gex,
        "delta_oi":  delta_oi,
        "delta_iv":  delta_iv,
        "spot":      exposure_dict.get("spot_price", 0.0),
    })


# ─── Expected Move Engine ─────────────────────────────────────────────────────

def compute_expected_move(spot: float, iv_pct: float, dte: float) -> Dict:
    """
    Expected Move = Spot × IV × sqrt(DTE / 365)
    Returns upper/lower bands and probability cone.
    """
    if spot <= 0 or iv_pct <= 0 or dte <= 0:
        return {"status": "INSUFFICIENT_DATA"}

    iv_decimal = iv_pct / 100.0
    t_years    = dte / 365.0
    em         = spot * iv_decimal * math.sqrt(t_years)

    return {
        "spot":          round(spot, 2),
        "iv_pct":        round(iv_pct, 2),
        "dte":           round(dte, 1),
        "expected_move": round(em, 2),
        "upper_1sd":     round(spot + em, 2),
        "lower_1sd":     round(spot - em, 2),
        "upper_2sd":     round(spot + 2 * em, 2),
        "lower_2sd":     round(spot - 2 * em, 2),
        "upper_pct":     round(em / spot * 100, 2),
        "lower_pct":     round(-em / spot * 100, 2),
        "prob_in_range": 68.27,   # 1σ = 68.27% probability
    }


# ─── IV Regime Engine ─────────────────────────────────────────────────────────

def classify_iv_regime(iv_pct: float, hv_pct: float, iv_rank: float) -> Dict:
    """
    Classify IV regime based on IV vs HV and IV Rank.
    When HV is 0 (insufficient price history), classify based on IV Rank alone.
    """
    if iv_pct <= 0:
        return {
            "regime": "INSUFFICIENT_DATA", "signal": "NEUTRAL",
            "description": "No IV data available",
            "color": "#607d8b", "iv_pct": 0, "hv_pct": 0, "iv_rank": 0, "iv_hv_ratio": 1.0,
        }

    iv_hv_ratio = iv_pct / hv_pct if hv_pct > 0 else 1.0
    hv_available = hv_pct > 0

    # When HV not available, classify purely on IV Rank
    if not hv_available:
        if iv_rank >= 70:
            regime, signal = "HIGH_IV", "SELL_PREMIUM"
            desc  = f"IV {iv_pct:.1f}% elevated (rank {iv_rank:.0f}) — HV accumulating"
            color = "#ff1744"
        elif iv_rank <= 30:
            regime, signal = "LOW_IV", "BUY_OPTIONS"
            desc  = f"IV {iv_pct:.1f}% depressed (rank {iv_rank:.0f}) — HV accumulating"
            color = "#00c853"
        else:
            regime, signal = "NORMAL_IV", "NEUTRAL"
            desc  = f"IV {iv_pct:.1f}% (rank {iv_rank:.0f}) — HV accumulating, need more data"
            color = "#00d4ff"
    elif iv_rank >= 70 and iv_hv_ratio >= 1.2:
        regime, signal = "HIGH_IV", "SELL_PREMIUM"
        desc  = f"IV {iv_pct:.1f}% elevated (rank {iv_rank:.0f}, IV/HV={iv_hv_ratio:.2f}) — options expensive"
        color = "#ff1744"
    elif iv_rank <= 30 and iv_hv_ratio <= 0.85:
        regime, signal = "LOW_IV", "BUY_OPTIONS"
        desc  = f"IV {iv_pct:.1f}% depressed (rank {iv_rank:.0f}, IV/HV={iv_hv_ratio:.2f}) — options cheap"
        color = "#00c853"
    elif iv_rank >= 50:
        regime, signal = "ELEVATED_IV", "NEUTRAL_SELL_BIAS"
        desc  = f"IV {iv_pct:.1f}% above median (rank {iv_rank:.0f}) — slight sell bias"
        color = "#ff9100"
    else:
        regime, signal = "NORMAL_IV", "NEUTRAL"
        desc  = f"IV {iv_pct:.1f}% near fair value (rank {iv_rank:.0f})"
        color = "#00d4ff"

    return {
        "regime":      regime,
        "signal":      signal,
        "description": desc,
        "color":       color,
        "iv_pct":      round(iv_pct, 2),
        "hv_pct":      round(hv_pct, 2),
        "iv_rank":     round(iv_rank, 1),
        "iv_hv_ratio": round(iv_hv_ratio, 3),
    }


# ─── Smart Signal Layer ───────────────────────────────────────────────────────

def compute_smart_signal(
    iv_regime: Dict,
    gex: float,
    delta_gex: float,
    oi_flow_counts: Dict,
    vwap_signal: str,
    pcr: float,
) -> Dict:
    """
    Independent signal layer — does NOT modify the decision engine.
    Combines IV regime + GEX + OI flow + VWAP + PCR.
    """
    score = 0.0
    reasons = []

    # IV regime (weight 35%)
    iv_sig = iv_regime.get("signal", "NEUTRAL")
    if iv_sig == "SELL_PREMIUM":
        score += 35
        reasons.append("High IV — sell premium")
    elif iv_sig == "BUY_OPTIONS":
        score -= 35
        reasons.append("Low IV — buy options")
    elif iv_sig == "NEUTRAL_SELL_BIAS":
        score += 15
        reasons.append("Elevated IV — mild sell bias")

    # GEX sign (weight 25%)
    if gex > 0:
        score += 20
        reasons.append(f"Positive GEX ({gex:.2f}Cr) — dealers long gamma, market stabilizing")
    elif gex < 0:
        score -= 20
        reasons.append(f"Negative GEX ({gex:.2f}Cr) — dealers short gamma, volatility amplified")

    # GEX momentum (weight 10%)
    if delta_gex > 0:
        score += 8
        reasons.append("GEX increasing — gamma building")
    elif delta_gex < 0:
        score -= 8
        reasons.append("GEX decreasing — gamma unwinding")

    # OI flow (weight 15%)
    lb = oi_flow_counts.get("LONG_BUILDUP", 0)
    sb = oi_flow_counts.get("SHORT_BUILDUP", 0)
    sc = oi_flow_counts.get("SHORT_COVERING", 0)
    lu = oi_flow_counts.get("LONG_UNWINDING", 0)
    oi_bull = lb + sc
    oi_bear = sb + lu
    if oi_bull > oi_bear:
        score += 10
        reasons.append(f"OI flow bullish ({lb} long buildup, {sc} short covering)")
    elif oi_bear > oi_bull:
        score -= 10
        reasons.append(f"OI flow bearish ({sb} short buildup, {lu} long unwinding)")

    # VWAP (weight 10%)
    if vwap_signal == "BULLISH":
        score += 8
        reasons.append("Price above VWAP — bullish bias")
    elif vwap_signal == "BEARISH":
        score -= 8
        reasons.append("Price below VWAP — bearish bias")

    # PCR (weight 5%)
    if pcr > 1.3:
        score += 5
        reasons.append(f"High PCR ({pcr:.2f}) — contrarian bullish")
    elif pcr < 0.7:
        score -= 5
        reasons.append(f"Low PCR ({pcr:.2f}) — contrarian bearish")

    # Determine signal
    confidence = min(abs(int(score)), 100)
    if score >= 30:
        signal = "SELL_PREMIUM"
        signal_color = "#ff9100"
    elif score <= -30:
        signal = "BUY_OPTIONS"
        signal_color = "#00c853"
    elif score >= 15:
        signal = "MILD_SELL_BIAS"
        signal_color = "#ff9100"
    elif score <= -15:
        signal = "MILD_BUY_BIAS"
        signal_color = "#00c853"
    else:
        signal = "NEUTRAL"
        signal_color = "#607d8b"

    return {
        "signal":       signal,
        "signal_color": signal_color,
        "confidence":   confidence,
        "score":        round(score, 1),
        "reasons":      reasons[:5],
    }


# ─── Heatmap Builder ──────────────────────────────────────────────────────────

def build_heatmap(chain_rows: List[Dict], spot: float) -> Dict:
    """
    Build OI, IV, and GEX heatmap data per strike.
    Only includes strikes within ±10% of spot with valid OI.
    Filters illiquid deep OTM strikes with bad IV (>80%).
    """
    if not chain_rows:
        return {"status": "INSUFFICIENT_DATA", "strikes": []}

    MAX_DIST_PCT = 10.0   # only show ±10% from spot
    IV_MAX       = 80.0   # cap IV display at 80% — above this is illiquid noise

    # Filter to liquid strikes near spot
    liquid_rows = []
    for row in chain_rows:
        k = row.get("strike", 0)
        if spot > 0 and abs(k - spot) / spot * 100 > MAX_DIST_PCT:
            continue
        c_oi = row.get("call", {}).get("oi", 0)
        p_oi = row.get("put",  {}).get("oi", 0)
        if c_oi == 0 and p_oi == 0:
            continue
        liquid_rows.append(row)

    if not liquid_rows:
        return {"status": "INSUFFICIENT_DATA", "strikes": []}

    max_oi = max(
        (max(r.get("call", {}).get("oi", 0), r.get("put", {}).get("oi", 0)) for r in liquid_rows),
        default=1,
    ) or 1

    strikes = []
    for row in liquid_rows:
        k    = row.get("strike", 0)
        call = row.get("call", {})
        put  = row.get("put",  {})
        c_oi = call.get("oi", 0)
        p_oi = put.get("oi", 0)

        # Cap IV at 80% to avoid illiquid noise in display
        c_iv = min(call.get("iv", 0.0), IV_MAX)
        p_iv = min(put.get("iv",  0.0), IV_MAX)

        # IV skew only meaningful when both sides have valid IV
        iv_skew = round(p_iv - c_iv, 2) if c_iv > 0 and p_iv > 0 else 0.0

        dist_pct = abs(k - spot) / spot * 100 if spot > 0 else 0

        strikes.append({
            "strike":      k,
            "dist_pct":    round(dist_pct, 2),
            "is_atm":      row.get("is_atm", False),
            "call_oi":     c_oi,
            "put_oi":      p_oi,
            "call_oi_pct": round(c_oi / max_oi * 100, 1),
            "put_oi_pct":  round(p_oi / max_oi * 100, 1),
            "call_iv":     round(c_iv, 2),
            "put_iv":      round(p_iv, 2),
            "iv_skew":     iv_skew,
            "pcr":         round(p_oi / c_oi, 3) if c_oi > 0 else 0,
        })

    return {
        "strikes": sorted(strikes, key=lambda x: x["strike"]),
        "spot":    spot,
        "max_oi":  max_oi,
        "count":   len(strikes),
    }


# ─── Main Intelligence Endpoint ───────────────────────────────────────────────

@intelligence_router.get("/intelligence")
async def get_intelligence(symbol: str = Query("NIFTY")):
    """
    Full institutional analytics snapshot.
    Returns all intelligence layers in one call.
    """
    state   = get_market_state()
    cache   = get_cache()

    summary    = state.get_sync(f"summary:{symbol}") or {}
    iv_cache   = state.get_sync(f"iv:{symbol}") or {}
    exposure   = state.get_sync(f"exposure:{symbol}") or {}
    chain_dict = state.get_sync(f"chain:{symbol}") or {}

    spot       = summary.get("spot_price", 0.0)
    current_iv = summary.get("atm_iv", 0.0)
    # hv and iv_rank come from iv_cache (set by compute_iv_analytics)
    hv_30d     = iv_cache.get("historical_vol_30d", 0.0)
    iv_rank    = iv_cache.get("iv_rank", 0.0)
    pcr        = summary.get("pcr_oi", 1.0)

    # If iv_rank is 0 but we have IV data, it means insufficient history — show 50 (neutral)
    if iv_rank == 0.0 and current_iv > 0:
        iv_rank = 50.0

    # 1. Time-series intelligence
    delta_buf  = get_delta_buffer(symbol)
    ts_data    = delta_buf.get_all()

    # Also merge Redis GEX history for persistence
    redis_gex  = await cache.ts_get_all(cache.key_gex_history(symbol))
    # Build merged time-series with deltas
    merged_ts  = _build_merged_timeseries(ts_data, redis_gex)

    # 2. OI Classification
    oi_data    = get_oi_flow(symbol)
    oi_flows   = oi_data.get("flows", [])
    flow_counts = oi_data.get("flow_counts", {})

    # 3. Expected Move
    expiry = chain_dict.get("expiry", "")
    dte    = _days_to_expiry(expiry)
    em     = compute_expected_move(spot, current_iv, dte)

    # 4. IV Regime
    iv_regime  = classify_iv_regime(current_iv, hv_30d, iv_rank)

    # 5. Smart Signal
    gex_ts     = get_gex_timeseries_response(symbol)
    latest_gex = gex_ts.get("latest", {}).get("gex", 0.0) or 0.0
    latest_delta_gex = ts_data[-1].get("delta_gex", 0.0) if ts_data else 0.0
    vwap_data  = get_vwap_response(symbol, spot)
    vwap_sig   = vwap_data.get("signal", "NEUTRAL")

    smart_signal = compute_smart_signal(
        iv_regime, latest_gex, latest_delta_gex,
        flow_counts, vwap_sig, pcr,
    )

    # 6. Alerts
    alerts = get_alert_engine().get_alerts(symbol=symbol, limit=20)

    # 7. Heatmap
    chain_rows = chain_dict.get("rows", [])
    heatmap    = build_heatmap(chain_rows, spot)

    # 8. OI Classification table (top 20 strikes by OI)
    oi_table = _build_oi_classification_table(oi_flows, chain_rows)

    return ORJSONResponse({
        "symbol":       symbol,
        "spot":         spot,
        "timestamp":    time.time(),

        "timeseries":   merged_ts[-200:],

        "oi_classification": {
            "table":        oi_table,
            "flow_counts":  flow_counts,
            "dominant":     oi_data.get("dominant_strikes", [])[:10],
        },

        "expected_move": em,

        "iv_regime":    iv_regime,

        "smart_signal": smart_signal,

        "alerts":       alerts[:10],

        "heatmap":      heatmap,

        "summary": {
            "gex":      latest_gex,
            "delta_gex": latest_delta_gex,
            "iv":       current_iv,
            "hv":       hv_30d,
            "iv_rank":  iv_rank,
            "pcr":      pcr,
            "max_pain": summary.get("max_pain", 0),
            "call_wall": exposure.get("call_wall", 0),
            "put_wall":  exposure.get("put_wall", 0),
        },
    })


@intelligence_router.get("/intelligence/timeseries")
async def get_intelligence_timeseries(symbol: str = Query("NIFTY")):
    """Time-series deltas only — lightweight for chart polling."""
    cache    = get_cache()
    delta_buf = get_delta_buffer(symbol)
    ts_data  = delta_buf.get_all()
    redis_gex = await cache.ts_get_all(cache.key_gex_history(symbol))
    merged   = _build_merged_timeseries(ts_data, redis_gex)
    return ORJSONResponse({"symbol": symbol, "timeseries": merged[-200:], "timestamp": time.time()})


@intelligence_router.get("/intelligence/heatmap")
async def get_intelligence_heatmap(symbol: str = Query("NIFTY")):
    """Heatmap data only."""
    state      = get_market_state()
    chain_dict = state.get_sync(f"chain:{symbol}") or {}
    summary    = state.get_sync(f"summary:{symbol}") or {}
    spot       = summary.get("spot_price", 0.0)
    heatmap    = build_heatmap(chain_dict.get("rows", []), spot)
    return ORJSONResponse({"symbol": symbol, "heatmap": heatmap, "timestamp": time.time()})


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _days_to_expiry(expiry: str) -> float:
    if not expiry:
        return 7.0
    try:
        from datetime import date
        exp = date.fromisoformat(expiry)
        delta = (exp - date.today()).days
        return max(float(delta), 0.5)
    except Exception:
        return 7.0


def _build_merged_timeseries(ts_data: List[Dict], redis_gex: List[Dict]) -> List[Dict]:
    """Merge in-memory delta buffer with Redis GEX history."""
    seen = set()
    merged = []

    # From Redis GEX history (has gex, dex, spot but no deltas)
    for snap in redis_gex:
        ts = snap.get("ts", 0)
        if ts not in seen:
            seen.add(ts)
            merged.append({
                "ts":        ts,
                "gex":       snap.get("gex", 0),
                "dex":       snap.get("dex", 0),
                "spot":      snap.get("spot", 0),
                "iv":        0,
                "total_oi":  0,
                "delta_gex": 0,
                "delta_oi":  0,
                "delta_iv":  0,
            })

    # From in-memory delta buffer (has deltas)
    for snap in ts_data:
        ts = round(snap.get("ts", 0))
        if ts not in seen:
            seen.add(ts)
            merged.append(snap)
        else:
            # Update existing entry with delta data
            for item in merged:
                if round(item.get("ts", 0)) == ts:
                    item.update({k: v for k, v in snap.items() if k not in ("ts",)})
                    break

    merged.sort(key=lambda x: x.get("ts", 0))

    # Forward-fill zeros
    last_gex = 0.0
    last_dex = 0.0
    last_iv  = 0.0
    for snap in merged:
        if snap.get("gex", 0) != 0:
            last_gex = snap["gex"]
        elif last_gex:
            snap["gex"] = last_gex
        if snap.get("dex", 0) != 0:
            last_dex = snap["dex"]
        elif last_dex:
            snap["dex"] = last_dex
        if snap.get("iv", 0) != 0:
            last_iv = snap["iv"]
        elif last_iv:
            snap["iv"] = last_iv

    return merged


def _build_oi_classification_table(oi_flows: List[Dict], chain_rows: List[Dict]) -> List[Dict]:
    """Build enriched OI classification table combining flow data with chain data."""
    # Index chain rows by strike
    chain_by_strike: Dict[float, Dict] = {}
    for row in chain_rows:
        chain_by_strike[row.get("strike", 0)] = row

    table = []
    seen = set()
    for flow in oi_flows:
        strike = flow.get("strike", 0)
        otype  = flow.get("option_type", "")
        key    = (strike, otype)
        if key in seen:
            continue
        seen.add(key)

        row = chain_by_strike.get(strike, {})
        leg = row.get("call" if otype == "CE" else "put", {})

        table.append({
            "strike":         strike,
            "type":           otype,
            "classification": flow.get("flow", "NEUTRAL"),
            "color":          flow.get("color", "#607d8b"),
            "oi":             flow.get("oi", 0),
            "oi_change":      flow.get("oi_change", 0),
            "ltp":            leg.get("ltp", 0),
            "iv":             leg.get("iv", 0),
            "delta":          (leg.get("greeks") or {}).get("delta", 0),
            "volume":         leg.get("volume", 0),
        })

    # Sort by abs OI change descending
    return sorted(table, key=lambda x: abs(x["oi_change"]), reverse=True)[:30]
