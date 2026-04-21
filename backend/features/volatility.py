"""
IV vs Realized Volatility Engine
==================================
Computes IV spread, generates SELL/BUY signals, tracks term premium.
"""

import math
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from collections import deque
import time

from features.regime import get_price_buffer, compute_log_returns


# ─── Realized Vol computations ────────────────────────────────────────────────

def realized_vol_close_to_close(prices: List[float], window: int = 30) -> float:
    """
    Close-to-close annualized HV using sqrt(252) annualization.
    Each price observation is treated as a daily-equivalent sample
    so HV is on the same scale as IV for meaningful comparison.
    """
    if len(prices) < window + 1:
        return 0.0
    series  = pd.Series(prices, dtype=float)
    returns = compute_log_returns(series).tail(window).dropna()
    if len(returns) < 5:
        return 0.0
    return float(returns.std() * math.sqrt(252) * 100)  # as %


def realized_vol_parkinson(high: List[float], low: List[float], window: int = 20) -> float:
    """
    Parkinson estimator — uses high-low range, more efficient than C2C.
    sigma_p = sqrt(1/(4*ln(2)*N) * sum(ln(H/L)^2)) * sqrt(252)
    """
    if len(high) < window or len(low) < window:
        return 0.0
    factor = 1.0 / (4.0 * math.log(2.0) * window)
    h = np.array(high[-window:], dtype=float)
    lo = np.array(low[-window:], dtype=float)
    valid = lo > 0
    if not valid.all():
        return 0.0
    log_hl = np.log(h[valid] / lo[valid]) ** 2
    return float(math.sqrt(factor * log_hl.sum()) * math.sqrt(252) * 100)


def realized_vol_garman_klass(
    open_: List[float], high: List[float], low: List[float], close: List[float],
    window: int = 20,
) -> float:
    """
    Garman-Klass estimator — most efficient single-period estimator.
    Uses OHLC data. Preferred when available.
    """
    n = min(len(open_), len(high), len(low), len(close), window)
    if n < 3:
        return 0.0
    o = np.array(open_[-n:],  dtype=float)
    h = np.array(high[-n:],   dtype=float)
    l = np.array(low[-n:],    dtype=float)
    c = np.array(close[-n:],  dtype=float)
    valid = (o > 0) & (h > 0) & (l > 0) & (c > 0)
    if valid.sum() < 3:
        return 0.0
    term1 = 0.5 * np.log(h[valid] / l[valid]) ** 2
    term2 = (2 * math.log(2) - 1) * np.log(c[valid] / o[valid]) ** 2
    var   = float(np.mean(term1 - term2))
    return float(math.sqrt(max(var, 0) * 252) * 100)


# ─── IV Spread Analysis ───────────────────────────────────────────────────────

def compute_iv_rv_spread(iv_pct: float, rv_pct: float) -> Dict:
    """
    IV Spread = IV - RV
    Positive → options overpriced (sell premium)
    Negative → options underpriced (buy premium)
    """
    spread = iv_pct - rv_pct
    ratio  = iv_pct / rv_pct if rv_pct > 0 else 1.0

    if spread > 3.0:
        signal    = "SELL_OPTIONS"
        signal_strength = min(abs(spread) / 5.0, 1.0)
        rationale = f"IV {iv_pct:.1f}% >> RV {rv_pct:.1f}% — premium elevated, favour sellers"
    elif spread < -3.0:
        signal    = "BUY_OPTIONS"
        signal_strength = min(abs(spread) / 5.0, 1.0)
        rationale = f"IV {iv_pct:.1f}% << RV {rv_pct:.1f}% — options cheap, favour buyers"
    else:
        signal    = "NEUTRAL"
        signal_strength = 0.0
        rationale = f"IV {iv_pct:.1f}% ≈ RV {rv_pct:.1f}% — fair value"

    return {
        "iv":              round(iv_pct, 2),
        "rv_30d":          round(rv_pct, 2),
        "spread":          round(spread, 2),
        "ratio":           round(ratio, 3),
        "signal":          signal,
        "signal_strength": round(signal_strength, 3),
        "rationale":       rationale,
    }


# ─── Per-Strike IV-RV enrichment ─────────────────────────────────────────────

def enrich_chain_with_rv_signal(
    chain_rows: List[Dict],
    rv_pct: float,
) -> List[Dict]:
    """
    Annotate each option chain row with IV-RV spread and signal.
    Mutates in place; also returns modified list.
    """
    for row in chain_rows:
        call_iv = row.get("call", {}).get("iv", 0.0)
        put_iv  = row.get("put",  {}).get("iv", 0.0)
        if call_iv > 0:
            row["call"]["iv_rv_spread"] = round(call_iv - rv_pct, 2)
            row["call"]["iv_signal"]    = "SELL" if call_iv - rv_pct > 3 else ("BUY" if call_iv - rv_pct < -3 else "NEUTRAL")
        if put_iv > 0:
            row["put"]["iv_rv_spread"] = round(put_iv - rv_pct, 2)
            row["put"]["iv_signal"]    = "SELL" if put_iv - rv_pct > 3 else ("BUY" if put_iv - rv_pct < -3 else "NEUTRAL")
    return chain_rows


# ─── Vol surface snapshot ─────────────────────────────────────────────────────

class VolSurface:
    """Tracks rolling IV history for term premium and vol-of-vol."""

    def __init__(self, maxlen: int = 100):
        self._iv_history: deque = deque(maxlen=maxlen)
        self._timestamps: deque = deque(maxlen=maxlen)

    def push(self, atm_iv: float, ts: Optional[float] = None):
        if atm_iv > 0:
            self._iv_history.append(atm_iv)
            self._timestamps.append(ts or time.time())

    def iv_rank(self, current_iv: float) -> float:
        if len(self._iv_history) < 2:
            return 50.0 if len(self._iv_history) == 1 else 0.0
        lo = min(self._iv_history)
        hi = max(self._iv_history)
        if hi == lo:
            return 50.0
        return round((current_iv - lo) / (hi - lo) * 100, 1)

    def iv_percentile(self, current_iv: float) -> float:
        if len(self._iv_history) < 2:
            return 50.0 if len(self._iv_history) == 1 else 0.0
        below = sum(1 for iv in self._iv_history if iv < current_iv)
        return round(below / len(self._iv_history) * 100, 1)

    def vol_of_vol(self) -> float:
        if len(self._iv_history) < 10:
            return 0.0
        arr = np.array(self._iv_history, dtype=float)
        return round(float(np.std(arr)), 2)

    def to_chart_series(self) -> List[Dict]:
        return [
            {"ts": round(t, 0), "iv": round(iv, 2)}
            for t, iv in zip(self._timestamps, self._iv_history)
        ]


_vol_surfaces: Dict[str, VolSurface] = {}

def get_vol_surface(symbol: str) -> VolSurface:
    if symbol not in _vol_surfaces:
        _vol_surfaces[symbol] = VolSurface()
    return _vol_surfaces[symbol]


def get_iv_analysis(symbol: str, current_iv: float) -> Dict:
    """Full IV analysis for API endpoint."""
    buf     = get_price_buffer(symbol)
    prices  = buf.to_series().tolist()
    rv_30   = realized_vol_close_to_close(prices, 30)
    rv_10   = realized_vol_close_to_close(prices, 10)
    surf    = get_vol_surface(symbol)
    surf.push(current_iv)

    return {
        "symbol":       symbol,
        "current_iv":   round(current_iv, 2),
        "rv_30d":       round(rv_30, 2),
        "rv_10d":       round(rv_10, 2),
        "iv_rv_spread": round(current_iv - rv_30, 2),
        "iv_rank":      surf.iv_rank(current_iv),
        "iv_percentile": surf.iv_percentile(current_iv),
        "vol_of_vol":   surf.vol_of_vol(),
        "signal":       compute_iv_rv_spread(current_iv, rv_30)["signal"],
        "signal_strength": compute_iv_rv_spread(current_iv, rv_30)["signal_strength"],
        "rationale":    compute_iv_rv_spread(current_iv, rv_30)["rationale"],
        "iv_history":   surf.to_chart_series(),
        "timestamp":    time.time(),
    }
