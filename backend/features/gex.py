"""
Time-Series GEX / DEX Tracker
================================
Stores historical snapshots of Gamma Exposure and Delta Exposure.
Detects gamma flips, sudden spikes, and tracks dealer positioning over time.
"""

import time
import math
from typing import Dict, List, Optional, Tuple
from collections import deque
import numpy as np


# ─── Snapshot types ───────────────────────────────────────────────────────────

class GEXSnapshot:
    __slots__ = ("ts", "gex", "dex", "vega", "theta", "spot", "gamma_flip", "call_wall", "put_wall")

    def __init__(
        self, ts: float, gex: float, dex: float, vega: float, theta: float,
        spot: float, gamma_flip: float, call_wall: float, put_wall: float,
    ):
        self.ts          = ts
        self.gex         = gex
        self.dex         = dex
        self.vega        = vega
        self.theta       = theta
        self.spot        = spot
        self.gamma_flip  = gamma_flip
        self.call_wall   = call_wall
        self.put_wall    = put_wall

    def to_dict(self) -> Dict:
        return {
            "ts":          round(self.ts, 0),
            "gex":         round(self.gex, 4),
            "dex":         round(self.dex, 4),
            "vega":        round(self.vega, 4),
            "theta":       round(self.theta, 4),
            "spot":        round(self.spot, 2),
            "gamma_flip":  round(self.gamma_flip, 2),
            "call_wall":   round(self.call_wall, 0),
            "put_wall":    round(self.put_wall, 0),
        }


# ─── Per-symbol GEX time-series store ────────────────────────────────────────

class GEXTimeSeries:
    """Rolling in-memory store for GEX/DEX snapshots."""

    MAXLEN = 200   # ~16 hours at 5-min intervals

    def __init__(self, symbol: str):
        self.symbol    = symbol
        self._history: deque = deque(maxlen=self.MAXLEN)

    def push(self, snap: GEXSnapshot):
        self._history.append(snap)

    def latest(self) -> Optional[GEXSnapshot]:
        return self._history[-1] if self._history else None

    def to_chart(self) -> List[Dict]:
        return [s.to_dict() for s in self._history]

    def detect_gamma_flip(self) -> Optional[Dict]:
        """
        Detect if GEX just crossed zero (gamma flip event).
        Returns event dict if flip detected in the last two snapshots.
        """
        h = list(self._history)
        if len(h) < 2:
            return None
        prev, curr = h[-2], h[-1]
        if prev.gex * curr.gex < 0:  # sign change
            direction = "POSITIVE_TO_NEGATIVE" if prev.gex > 0 else "NEGATIVE_TO_POSITIVE"
            return {
                "event":     "GAMMA_FLIP",
                "direction": direction,
                "level":     round(curr.spot, 2),
                "gex_from":  round(prev.gex, 4),
                "gex_to":    round(curr.gex, 4),
                "ts":        curr.ts,
            }
        return None

    def detect_gex_spike(self, threshold_pct: float = 0.30) -> Optional[Dict]:
        """
        Detect a sudden GEX spike (>threshold_pct change from last snapshot).
        """
        h = list(self._history)
        if len(h) < 2:
            return None
        prev, curr = h[-2], h[-1]
        if abs(prev.gex) < 1e-6:
            return None
        chg_pct = abs(curr.gex - prev.gex) / abs(prev.gex)
        if chg_pct > threshold_pct:
            return {
                "event":     "GEX_SPIKE",
                "pct_change": round(chg_pct * 100, 1),
                "gex_from":  round(prev.gex, 4),
                "gex_to":    round(curr.gex, 4),
                "ts":        curr.ts,
            }
        return None

    def rolling_stats(self, window: int = 20) -> Dict:
        """Compute rolling statistics over the last `window` snapshots."""
        h = [s.to_dict() for s in list(self._history)[-window:]]
        if not h:
            return {}
        gex_arr = np.array([s["gex"] for s in h])
        dex_arr = np.array([s["dex"] for s in h])
        return {
            "gex_mean":   round(float(np.mean(gex_arr)), 4),
            "gex_std":    round(float(np.std(gex_arr)),  4),
            "gex_min":    round(float(np.min(gex_arr)),  4),
            "gex_max":    round(float(np.max(gex_arr)),  4),
            "dex_mean":   round(float(np.mean(dex_arr)), 4),
            "net_dealer_bias": "LONG" if float(np.mean(dex_arr)) > 0 else "SHORT",
        }


# ─── Per-strike GEX bar (for heatmap-style chart) ────────────────────────────

def build_gex_profile(exposures: List[Dict]) -> List[Dict]:
    """
    Build a sorted GEX profile by strike for bar/heatmap rendering.
    Input: list of ExposureByStrike dicts from analytics_processor.
    """
    result = []
    for exp in exposures:
        result.append({
            "strike":     exp.get("strike", 0),
            "gex":        exp.get("gex", 0.0),
            "dex":        exp.get("dex", 0.0),
            "call_gamma": exp.get("call_gamma", 0.0),
            "put_gamma":  exp.get("put_gamma", 0.0),
            "net_vega":   exp.get("net_vega", 0.0),
        })
    return sorted(result, key=lambda x: x["strike"])


# ─── Singletons ───────────────────────────────────────────────────────────────

_gex_stores: Dict[str, GEXTimeSeries] = {}

def get_gex_store(symbol: str) -> GEXTimeSeries:
    if symbol not in _gex_stores:
        _gex_stores[symbol] = GEXTimeSeries(symbol)
    return _gex_stores[symbol]


def record_exposure_snapshot(symbol: str, exposure_dict: Dict):
    """Called whenever a fresh GreeksExposureResponse is computed."""
    snap = GEXSnapshot(
        ts         = time.time(),
        gex        = exposure_dict.get("total_gex",      0.0),
        dex        = exposure_dict.get("total_dex",      0.0),
        vega       = exposure_dict.get("total_vega",     0.0),
        theta      = exposure_dict.get("total_theta",    0.0),
        spot       = exposure_dict.get("spot_price",     0.0),
        gamma_flip = exposure_dict.get("gamma_flip_level", 0.0),
        call_wall  = exposure_dict.get("call_wall",      0.0),
        put_wall   = exposure_dict.get("put_wall",       0.0),
    )
    get_gex_store(symbol).push(snap)


def get_gex_timeseries_response(symbol: str) -> Dict:
    store = get_gex_store(symbol)
    latest = store.latest()
    return {
        "symbol":      symbol,
        "timeseries":  store.to_chart(),
        "stats":       store.rolling_stats(),
        "latest":      latest.to_dict() if latest else {},
        "gamma_flip_event": store.detect_gamma_flip(),
        "gex_spike":   store.detect_gex_spike(),
        "timestamp":   time.time(),
    }
