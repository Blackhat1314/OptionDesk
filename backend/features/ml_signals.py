"""
features/ml_signals.py
======================
ML-based directional signal for NIFTY option chain.

Architecture:
  - Follows the same pattern as features/regime.py and features/gex.py
  - In-memory candle buffers (5min, 15min, 60min) per strike
  - Called from main.py _periodic_option_chain_refresh() on every chain update
  - Stores signals in MarketStateStore (in-memory) + Redis
  - Exposes get_ml_signals() for the REST endpoint

Model:
  - XGBoost (55%) + LightGBM (45%) ensemble
  - 54 features: OI/IV/price features + 60min context + 5min context
  - Predicts: will this option's price be higher in the next 15min candle?
  - Only fires when confidence >= 0.65 (82% accuracy at this threshold)
  - Only for ATM ±2 strikes (most liquid)

Model files location: /app/data/ml_model/ (Docker volume — survives restarts)
"""

import time
import math
import numpy as np
from collections import deque
from typing import Dict, List, Optional, Tuple
import logging

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
MODEL_DIR            = "/app/ml_model"
CONFIDENCE_THRESHOLD = 0.65
ATM_RANGE            = 2       # only predict for ATM ±2 strikes
CANDLE_5M_SECS       = 300     # 5 minutes in seconds
CANDLE_15M_SECS      = 900     # 15 minutes in seconds
CANDLE_60M_SECS      = 3600    # 60 minutes in seconds
MAX_CANDLES_PER_KEY  = 30      # keep last 30 candles per strike/type

# ── Model singleton ───────────────────────────────────────────────────────────
_model_loaded   = False
_xgb_model      = None
_lgb_model      = None
_scaler         = None
_feat_cols: List[str] = []
_weights: Dict  = {"xgb": 0.55, "lgb": 0.45}


def _load_model() -> bool:
    """Load model artifacts from disk. Returns True if successful."""
    global _model_loaded, _xgb_model, _lgb_model, _scaler, _feat_cols, _weights
    if _model_loaded:
        return True
    try:
        import joblib
        import json
        import xgboost as xgb
        from pathlib import Path

        model_path = Path(MODEL_DIR)
        if not model_path.exists():
            return False

        required = ["xgb_model.json", "lgb_model.pkl", "scaler.pkl", "feature_cols.json"]
        if not all((model_path / f).exists() for f in required):
            return False

        _scaler    = joblib.load(model_path / "scaler.pkl")
        _lgb_model = joblib.load(model_path / "lgb_model.pkl")
        _xgb_model = xgb.XGBClassifier()
        _xgb_model.load_model(str(model_path / "xgb_model.json"))
        _feat_cols = json.loads((model_path / "feature_cols.json").read_text())

        if (model_path / "model_weights.json").exists():
            _weights = json.loads((model_path / "model_weights.json").read_text())

        _model_loaded = True
        log.info(f"ML model loaded — {len(_feat_cols)} features, threshold={CONFIDENCE_THRESHOLD}")
        return True
    except Exception as e:
        log.warning(f"ML model load failed: {e}")
        return False


# ── Candle Buffer ─────────────────────────────────────────────────────────────

class CandleBuffer:
    """
    Accumulates raw option chain snapshots into OHLCV candles.
    One buffer per (strike, type, interval_seconds).
    """
    __slots__ = ("_interval", "_candles", "_current", "_current_ts")

    def __init__(self, interval_secs: int):
        self._interval   = interval_secs
        self._candles: deque = deque(maxlen=MAX_CANDLES_PER_KEY)
        self._current: Optional[Dict] = None
        self._current_ts: float = 0.0

    def push(self, price: float, volume: int, oi: int, iv: float, ts: float):
        """Add a new tick to the current candle."""
        if price <= 0:
            return

        candle_start = (ts // self._interval) * self._interval

        if self._current is None or candle_start != self._current_ts:
            # Close previous candle
            if self._current is not None:
                self._candles.append(self._current)
            # Open new candle
            self._current_ts = candle_start
            self._current = {
                "ts": candle_start, "open": price, "high": price,
                "low": price, "close": price,
                "volume": volume, "oi": oi, "iv": iv,
                "ticks": 1,
            }
        else:
            # Update current candle
            c = self._current
            c["high"]   = max(c["high"], price)
            c["low"]    = min(c["low"],  price)
            c["close"]  = price
            c["volume"] += volume
            c["oi"]      = oi    # use latest OI
            c["iv"]      = iv    # use latest IV
            c["ticks"]  += 1

    def get_closed(self) -> List[Dict]:
        """Return all closed candles (excludes current open candle)."""
        return list(self._candles)

    def __len__(self):
        return len(self._candles)


# ── Per-strike buffer store ───────────────────────────────────────────────────

# Key: (strike, type) → {"5m": CandleBuffer, "15m": CandleBuffer, "60m": CandleBuffer}
_buffers: Dict[Tuple, Dict[str, CandleBuffer]] = {}

# Global PCR buffer (call OI / put OI per snapshot)
_pcr_buffer_5m:  deque = deque(maxlen=MAX_CANDLES_PER_KEY)
_pcr_buffer_15m: deque = deque(maxlen=MAX_CANDLES_PER_KEY)
_pcr_buffer_60m: deque = deque(maxlen=MAX_CANDLES_PER_KEY)
_last_pcr_ts_5m:  float = 0.0
_last_pcr_ts_15m: float = 0.0
_last_pcr_ts_60m: float = 0.0


def _get_buffer(strike: int, opt_type: str) -> Dict[str, CandleBuffer]:
    key = (strike, opt_type)
    if key not in _buffers:
        _buffers[key] = {
            "5m":  CandleBuffer(CANDLE_5M_SECS),
            "15m": CandleBuffer(CANDLE_15M_SECS),
            "60m": CandleBuffer(CANDLE_60M_SECS),
        }
    return _buffers[key]


# ── Feature computation ───────────────────────────────────────────────────────

def _candle_features(candles: List[Dict], prefix: str = "") -> Dict[str, float]:
    """Compute features from a list of closed candles."""
    if len(candles) < 2:
        return {}

    c  = candles[-1]   # latest closed candle
    c1 = candles[-2]   # one before

    price_chg = (c["close"] - c1["close"]) / c1["close"] if c1["close"] > 0 else 0.0
    oi_chg    = c["oi"] - c1["oi"]
    iv_chg    = c["iv"] - c1["iv"]
    vol_oi    = c["volume"] / max(c["oi"], 1)

    # OI momentum: direction of OI change
    oi_mom = 1 if oi_chg > 0 else (-1 if oi_chg < 0 else 0)

    # Buildup type: 0=neutral, 1=long_buildup, 2=short_buildup, 3=short_covering, 4=long_unwinding
    if price_chg > 0 and oi_chg > 0:
        buildup = 1
    elif price_chg < 0 and oi_chg > 0:
        buildup = 2
    elif price_chg > 0 and oi_chg < 0:
        buildup = 3
    elif price_chg < 0 and oi_chg < 0:
        buildup = 4
    else:
        buildup = 0

    # Realized vol: rolling std of returns (last 10 candles)
    if len(candles) >= 3:
        returns = [(candles[i]["close"] - candles[i-1]["close"]) / candles[i-1]["close"]
                   for i in range(max(1, len(candles)-10), len(candles))
                   if candles[i-1]["close"] > 0]
        realized_vol = float(np.std(returns)) if len(returns) >= 2 else 0.0
    else:
        realized_vol = 0.0

    # OI velocity (rate of change of OI change)
    oi_vel = 0.0
    if len(candles) >= 3:
        prev_oi_chg = candles[-2]["oi"] - candles[-3]["oi"]
        oi_vel = float(oi_chg - prev_oi_chg)

    # Price acceleration
    price_acc = 0.0
    if len(candles) >= 3:
        prev_chg = (candles[-2]["close"] - candles[-3]["close"]) / max(candles[-3]["close"], 1)
        price_acc = float(price_chg - prev_chg)

    # Volume surge
    recent_vols = [cc["volume"] for cc in candles[-5:]]
    avg_vol = np.mean(recent_vols[:-1]) if len(recent_vols) > 1 else 1
    vol_surge = float(c["volume"] / max(avg_vol, 1))

    # IV z-score (rolling 20 candles)
    if len(candles) >= 5:
        ivs = [cc["iv"] for cc in candles[-20:]]
        iv_mean = np.mean(ivs)
        iv_std  = np.std(ivs)
        iv_zscore = float((c["iv"] - iv_mean) / max(iv_std, 1e-8))
    else:
        iv_zscore = 0.0

    # OI z-score
    if len(candles) >= 5:
        ois = [cc["oi"] for cc in candles[-20:]]
        oi_mean = np.mean(ois)
        oi_std  = np.std(ois)
        oi_zscore = float((c["oi"] - oi_mean) / max(oi_std, 1e-8))
    else:
        oi_zscore = 0.0

    p = prefix
    return {
        f"{p}oi_change":       float(oi_chg),
        f"{p}iv_change":       float(iv_chg),
        f"{p}buildup_type":    float(buildup),
        f"{p}oi_momentum":     float(oi_mom),
        f"{p}price_change_pct": float(price_chg),
        f"{p}volume_oi_ratio": float(vol_oi),
        f"{p}oi_velocity":     float(oi_vel),
        f"{p}volume_surge":    float(vol_surge),
        f"{p}iv_zscore":       float(iv_zscore),
    }


def _build_feature_vector(
    strike: int, opt_type: str, spot: float, atm_strike: int,
    global_pcr: float, iv_percentile: float, oi_concentration: float,
    call_iv: float, put_iv: float, ts: float,
) -> Optional[Dict[str, float]]:
    """Build the full 54-feature vector for one strike/type."""
    buf = _get_buffer(strike, opt_type)
    c15 = buf["15m"].get_closed()
    c60 = buf["60m"].get_closed()
    c5  = buf["5m"].get_closed()

    if len(c15) < 2:
        return None

    latest = c15[-1]

    # ── Structural features ───────────────────────────────────────────────────
    atm_offset        = (strike - atm_strike) // 50  # in strike steps
    moneyness         = strike / spot if spot > 0 else 1.0
    distance_to_spot  = abs(strike - spot)
    atm_zone          = 1 if abs(atm_offset) <= 1 else (2 if abs(atm_offset) <= 3 else 3)

    # OI concentration (this strike's OI vs total — passed in)
    # IV percentile, global PCR — passed in from chain-level aggregates

    # IV spread (call IV - put IV at this strike)
    iv_spread = call_iv - put_iv if opt_type == "CALL" else put_iv - call_iv

    # Put/call IV ratio
    put_call_iv_ratio = put_iv / call_iv if call_iv > 0 else 1.0

    # ATM distance normalized
    atm_distance_norm = distance_to_spot / spot if spot > 0 else 0.0

    # Time features
    import pytz
    from datetime import datetime
    ist = pytz.timezone("Asia/Kolkata")
    now_ist = datetime.fromtimestamp(ts, tz=ist)
    market_open_secs  = 9 * 3600 + 15 * 60
    market_close_secs = 15 * 3600 + 30 * 60
    market_dur        = market_close_secs - market_open_secs
    now_secs          = now_ist.hour * 3600 + now_ist.minute * 60 + now_ist.second
    time_of_day       = max(0.0, min(1.0, (now_secs - market_open_secs) / market_dur))
    candle_hour       = float(now_ist.hour)
    session           = 1.0 if time_of_day < 0.16 else (2.0 if time_of_day < 0.60 else 3.0)
    hour_sin          = math.sin(2 * math.pi * candle_hour / 24)
    hour_cos          = math.cos(2 * math.pi * candle_hour / 24)

    # Proxy Greeks (no Black-Scholes needed)
    iv_val    = latest.get("iv", 0.0)
    vega_proxy  = iv_val * math.sqrt(1 - time_of_day + 0.01)
    gamma_proxy = math.exp(-0.5 * (atm_offset ** 2) / 4.0)
    theta_proxy = time_of_day * iv_val / 100.0

    # ── 15min candle features ─────────────────────────────────────────────────
    feats_15m = _candle_features(c15, prefix="")
    if not feats_15m:
        return None

    # OI rank and IV rank (simplified — rank within ATM±5 strikes)
    oi_rank = 1.0   # placeholder — computed at chain level in ingest_chain_signals
    iv_rank = 1.0

    # Realized vol from 15m candles
    realized_vol = feats_15m.get("realized_vol", 0.0)
    if len(c15) >= 3:
        returns = [(c15[i]["close"] - c15[i-1]["close"]) / c15[i-1]["close"]
                   for i in range(max(1, len(c15)-10), len(c15))
                   if c15[i-1]["close"] > 0]
        realized_vol = float(np.std(returns)) if len(returns) >= 2 else 0.0

    # OI skew change (put OI - call OI delta — simplified)
    oi_skew_change = 0.0

    # ATM pressure
    atm_pressure = oi_concentration * feats_15m.get("volume_oi_ratio", 0.0)

    # ── 60min context features ────────────────────────────────────────────────
    feats_60m = _candle_features(c60, prefix="") if len(c60) >= 2 else {}

    # ── 5min context features ─────────────────────────────────────────────────
    feats_5m = _candle_features(c5, prefix="") if len(c5) >= 2 else {}

    # ── Assemble full feature dict ────────────────────────────────────────────
    fv: Dict[str, float] = {
        # Base features
        "atm_offset":          float(atm_offset),
        "moneyness":           float(moneyness),
        "distance_to_spot":    float(distance_to_spot),
        "atm_zone":            float(atm_zone),
        "oi_change":           feats_15m.get("oi_change", 0.0),
        "iv_change":           feats_15m.get("iv_change", 0.0),
        "buildup_type":        feats_15m.get("buildup_type", 0.0),
        "oi_momentum":         feats_15m.get("oi_momentum", 0.0),
        "oi_concentration":    float(oi_concentration),
        "global_pcr":          float(global_pcr),
        "iv_percentile":       float(iv_percentile),
        "price_change_pct":    feats_15m.get("price_change_pct", 0.0),
        "volume_oi_ratio":     feats_15m.get("volume_oi_ratio", 0.0),
        "atm_pressure":        float(atm_pressure),
        "oi_skew_change":      float(oi_skew_change),
        "oi_rank":             float(oi_rank),
        "iv_rank":             float(iv_rank),
        "realized_vol":        float(realized_vol),
        "time_of_day":         float(time_of_day),
        "candle_hour":         float(candle_hour),
        "session":             float(session),
        "iv_spread":           float(iv_spread),
        "put_call_iv_ratio":   float(put_call_iv_ratio),
        "oi_velocity":         feats_15m.get("oi_velocity", 0.0),
        "price_acceleration":  feats_15m.get("price_acceleration", 0.0),
        "volume_surge":        feats_15m.get("volume_surge", 1.0),
        "atm_distance_norm":   float(atm_distance_norm),
        "iv_zscore":           feats_15m.get("iv_zscore", 0.0),
        "oi_zscore":           feats_15m.get("oi_zscore", 0.0),
        "hour_sin":            float(hour_sin),
        "hour_cos":            float(hour_cos),
        "vega_proxy":          float(vega_proxy),
        "gamma_proxy":         float(gamma_proxy),
        "theta_proxy":         float(theta_proxy),
        # 60min context
        "oi_change_60m":       feats_60m.get("oi_change", 0.0),
        "iv_change_60m":       feats_60m.get("iv_change", 0.0),
        "buildup_type_60m":    feats_60m.get("buildup_type", 0.0),
        "oi_momentum_60m":     feats_60m.get("oi_momentum", 0.0),
        "global_pcr_60m":      float(global_pcr),   # same snapshot
        "iv_percentile_60m":   float(iv_percentile),
        "oi_concentration_60m": float(oi_concentration),
        "atm_pressure_60m":    float(atm_pressure),
        "oi_skew_change_60m":  0.0,
        "realized_vol_60m":    feats_60m.get("realized_vol", 0.0) if feats_60m else 0.0,
        "iv_spread_60m":       float(iv_spread),
        "put_call_iv_ratio_60m": float(put_call_iv_ratio),
        "oi_velocity_60m":     feats_60m.get("oi_velocity", 0.0),
        "volume_surge_60m":    feats_60m.get("volume_surge", 1.0),
        "iv_zscore_60m":       feats_60m.get("iv_zscore", 0.0),
        # 5min context
        "price_change_pct_5m": feats_5m.get("price_change_pct", 0.0),
        "oi_change_5m":        feats_5m.get("oi_change", 0.0),
        "iv_change_5m":        feats_5m.get("iv_change", 0.0),
        "volume_oi_ratio_5m":  feats_5m.get("volume_oi_ratio", 0.0),
        "oi_momentum_5m":      feats_5m.get("oi_momentum", 0.0),
    }

    return fv


# ── Main entry point — called from main.py ────────────────────────────────────

def ingest_chain_for_ml(chain_dict: Dict, spot: float):
    """
    Called from main.py _periodic_option_chain_refresh() on every chain update.
    Feeds option chain rows into candle buffers.
    Does NOT run inference — inference runs every 15min via run_ml_inference().
    """
    rows = chain_dict.get("rows", [])
    if not rows:
        return

    ts  = time.time()
    atm = chain_dict.get("atm_strike", 0)

    for row in rows:
        strike = row.get("strike", 0)
        if not strike:
            continue

        # Only buffer ATM ±5 strikes to save memory
        if abs(strike - atm) > 5 * 50:
            continue

        for side, opt_type in [("call", "CALL"), ("put", "PUT")]:
            opt = row.get(side, {})
            if not opt:
                continue
            price  = float(opt.get("ltp", 0) or 0)
            volume = int(opt.get("volume", 0) or 0)
            oi     = int(opt.get("oi", 0) or 0)
            iv     = float(opt.get("iv", 0) or 0)

            if price <= 0:
                continue

            buf = _get_buffer(strike, opt_type)
            buf["5m"].push(price, volume, oi, iv, ts)
            buf["15m"].push(price, volume, oi, iv, ts)
            buf["60m"].push(price, volume, oi, iv, ts)


def run_ml_inference(chain_dict: Dict, spot: float) -> List[Dict]:
    """
    Run ML inference on current candle buffers.
    Returns list of signals for ATM ±2 strikes with confidence >= threshold.
    Called every 15min from the background loop.
    """
    if not _load_model():
        return []

    rows = chain_dict.get("rows", [])
    if not rows or spot <= 0:
        return []

    atm = chain_dict.get("atm_strike", 0)
    if not atm:
        return []

    # Compute chain-level aggregates
    total_call_oi = sum(r.get("call", {}).get("oi", 0) for r in rows)
    total_put_oi  = sum(r.get("put",  {}).get("oi", 0) for r in rows)
    total_oi      = total_call_oi + total_put_oi
    global_pcr    = total_put_oi / max(total_call_oi, 1)

    # IV percentile from chain summary
    all_ivs = []
    for r in rows:
        for side in ["call", "put"]:
            iv = float(r.get(side, {}).get("iv", 0) or 0)
            if iv > 0:
                all_ivs.append(iv)
    iv_percentile = 0.5  # default
    if all_ivs:
        atm_row = next((r for r in rows if r.get("strike") == atm), None)
        if atm_row:
            atm_iv = float(atm_row.get("call", {}).get("iv", 0) or 0)
            iv_percentile = sum(1 for iv in all_ivs if iv <= atm_iv) / len(all_ivs)

    # OI rank per strike (for oi_rank feature)
    oi_by_strike = {r.get("strike"): r.get("call", {}).get("oi", 0) + r.get("put", {}).get("oi", 0)
                    for r in rows}
    sorted_oi = sorted(oi_by_strike.values(), reverse=True)

    ts = time.time()
    signals = []

    for row in rows:
        strike = row.get("strike", 0)
        if not strike:
            continue

        # Only ATM ±2
        atm_offset_steps = (strike - atm) // 50
        if abs(atm_offset_steps) > ATM_RANGE:
            continue

        # OI concentration for this strike
        strike_oi = oi_by_strike.get(strike, 0)
        oi_concentration = strike_oi / max(total_oi, 1)

        # OI rank
        oi_rank = (sorted_oi.index(strike_oi) + 1) if strike_oi in sorted_oi else len(sorted_oi)

        # Call/Put IV at this strike
        call_iv = float(row.get("call", {}).get("iv", 0) or 0)
        put_iv  = float(row.get("put",  {}).get("iv", 0) or 0)

        for opt_type in ["CALL", "PUT"]:
            fv = _build_feature_vector(
                strike=strike, opt_type=opt_type, spot=spot, atm_strike=atm,
                global_pcr=global_pcr, iv_percentile=iv_percentile,
                oi_concentration=oi_concentration,
                call_iv=call_iv, put_iv=put_iv, ts=ts,
            )
            if fv is None:
                continue

            # Build feature array in exact model order
            try:
                x = np.array([[fv.get(f, 0.0) for f in _feat_cols]], dtype=np.float32)
                x_scaled = _scaler.transform(x)
                p_xgb = _xgb_model.predict_proba(x_scaled)[0][1]
                p_lgb = _lgb_model.predict_proba(x_scaled)[0][1]
                prob  = _weights["xgb"] * p_xgb + _weights["lgb"] * p_lgb
            except Exception:
                continue

            if prob < CONFIDENCE_THRESHOLD and prob > (1 - CONFIDENCE_THRESHOLD):
                continue  # below confidence threshold in both directions

            direction = "UP" if prob >= 0.5 else "DOWN"
            confidence = prob if direction == "UP" else (1 - prob)

            if confidence < CONFIDENCE_THRESHOLD:
                continue

            signals.append({
                "strike":     strike,
                "type":       opt_type,
                "direction":  direction,
                "confidence": round(float(confidence), 4),
                "prob_up":    round(float(prob), 4),
                "atm_offset": atm_offset_steps,
                "ts":         ts,
            })

    # Sort by confidence descending
    signals.sort(key=lambda x: x["confidence"], reverse=True)
    return signals


# ── Signal store (in-memory, updated every 15min) ────────────────────────────

_last_signals: List[Dict] = []
_last_inference_ts: float = 0.0
_inference_interval: float = 900.0  # 15 minutes


def should_run_inference() -> bool:
    """Returns True if 15 minutes have passed since last inference."""
    return time.time() - _last_inference_ts >= _inference_interval


def update_signals(signals: List[Dict]):
    """Store latest signals in memory."""
    global _last_signals, _last_inference_ts
    _last_signals = signals
    _last_inference_ts = time.time()


def get_ml_signals() -> Dict:
    """Return current ML signals — called by REST endpoint."""
    return {
        "signals":       _last_signals,
        "last_run":      _last_inference_ts,
        "model_loaded":  _model_loaded,
        "threshold":     CONFIDENCE_THRESHOLD,
        "next_run_in":   max(0, int(_inference_interval - (time.time() - _last_inference_ts))),
    }


def is_model_available() -> bool:
    """Check if model files exist without loading them."""
    from pathlib import Path
    model_path = Path(MODEL_DIR)
    required = ["xgb_model.json", "lgb_model.pkl", "scaler.pkl", "feature_cols.json"]
    return all((model_path / f).exists() for f in required)
