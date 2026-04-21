"""
Filter Engine — Layer 2: Universe -> Top 20
============================================
Vectorized NumPy. No ML.

Features:
  - Log returns: r_t = ln(P_t / P_{t-1})
  - Relative volume: rel_vol = volume / rolling_mean(volume, 20)
  - Volatility: sigma = std(r_t, 20) * sqrt(252)
    Fallback when prices static: sigma = (high - low) / close  (intraday range)
  - Momentum ROC: (P_t - P_{t-20}) / P_{t-20}
    Fallback when prices static: ROC = (close - open) / open

Rank score = norm(rel_vol) + norm(sigma) + norm(abs(ROC))
Select top 20 by rank_score.
"""

import numpy as np
from typing import Dict, List


def _safe_norm(arr: np.ndarray) -> np.ndarray:
    mn, mx = arr.min(), arr.max()
    if mx - mn < 1e-10:
        return np.zeros_like(arr)
    return (arr - mn) / (mx - mn)


def _is_static(prices: np.ndarray, threshold: float = 1e-8) -> bool:
    """True if all prices are identical (market closed / no movement)."""
    return float(prices.std()) < threshold


def compute_filter_features(histories: Dict[str, List[Dict]]) -> Dict[str, Dict]:
    """
    histories: {symbol: [{"price", "open", "high", "low", "close", "volume"}, ...]}
    Returns: {symbol: feature_dict}
    """
    results = {}

    for sym, candles in histories.items():
        if len(candles) < 5:
            continue

        prices  = np.array([c.get("price",  c.get("close", 0)) for c in candles], dtype=np.float64)
        opens   = np.array([c.get("open",   prices[i]) for i, c in enumerate(candles)], dtype=np.float64)
        highs   = np.array([c.get("high",   prices[i]) for i, c in enumerate(candles)], dtype=np.float64)
        lows    = np.array([c.get("low",    prices[i]) for i, c in enumerate(candles)], dtype=np.float64)
        volumes = np.array([c.get("volume", 0)         for c in candles], dtype=np.float64)

        if prices[-1] <= 0:
            continue

        static = _is_static(prices)

        # ── Relative volume ───────────────────────────────────────────────────
        n_vol = min(20, len(volumes) - 1)
        vol_mean = volumes[-n_vol-1:-1].mean() if n_vol > 0 else volumes.mean()
        rel_vol  = float(volumes[-1] / vol_mean) if vol_mean > 1 else 1.0

        # ── Volatility ────────────────────────────────────────────────────────
        if static or len(prices) < 3:
            # Use intraday OHLC range as volatility proxy
            ranges = (highs - lows) / np.where(lows > 0, lows, 1.0)
            sigma  = float(ranges.mean())
        else:
            log_ret = np.log(prices[1:] / prices[:-1])
            n_sig   = min(20, len(log_ret))
            sigma   = float(log_ret[-n_sig:].std() * np.sqrt(252))

        # ── Momentum ROC ──────────────────────────────────────────────────────
        if static:
            # Use open-to-close return as momentum proxy
            roc = float((prices[-1] - opens[-1]) / opens[-1]) if opens[-1] > 0 else 0.0
        else:
            n_roc = min(20, len(prices) - 1)
            roc   = float((prices[-1] - prices[-n_roc-1]) / prices[-n_roc-1]) if prices[-n_roc-1] > 0 else 0.0

        results[sym] = {
            "price":   float(prices[-1]),
            "open":    float(opens[-1]),
            "high":    float(highs[-1]),
            "low":     float(lows[-1]),
            "close":   float(prices[-1]),
            "volume":  float(volumes[-1]),
            "rel_vol": rel_vol,
            "sigma":   sigma,
            "roc":     roc,
            "static":  static,
        }

    if not results:
        return {}

    syms    = list(results.keys())
    rv_arr  = np.array([results[s]["rel_vol"]    for s in syms])
    sig_arr = np.array([results[s]["sigma"]      for s in syms])
    roc_arr = np.array([abs(results[s]["roc"])   for s in syms])

    scores = _safe_norm(rv_arr) + _safe_norm(sig_arr) + _safe_norm(roc_arr)

    for i, sym in enumerate(syms):
        results[sym]["filter_score"] = float(scores[i])

    return results


def select_top_n(features: Dict[str, Dict], n: int = 20) -> List[str]:
    if not features:
        return []
    ranked = sorted(features.keys(), key=lambda s: features[s].get("filter_score", 0), reverse=True)
    return ranked[:n]
