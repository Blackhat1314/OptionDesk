"""
Signal Engine — Layer 3: Top 20 -> Final 5-10 candidates
==========================================================
Vectorized NumPy. No ML.

Handles both live market (tick-based) and market-closed (OHLC-based) modes.

Boolean signals:
  above_vwap        = price > vwap  (or close > open when static)
  momentum_positive = ROC > 0
  volume_spike      = rel_vol > 1.5  (or volume > median when static)
  low_entropy       = entropy < 0.5  (or range_pct > 0.5% when static)
  vol_expanding     = sigma > mean_sigma  (or high-low range expanding)

Score = count of True signals (max 5)
Regime = TREND if entropy < 0.5 else RANGE
min_score = 1 when market closed (static prices), 3 when live
"""

import numpy as np
from typing import Dict, List


def _shannon_entropy(arr: np.ndarray, bins: int = 10) -> float:
    if len(arr) < 3:
        return 0.5
    counts, _ = np.histogram(arr, bins=bins)
    total = counts.sum()
    if total == 0:
        return 0.5
    probs = counts[counts > 0] / total
    raw   = -float(np.sum(probs * np.log2(probs)))
    max_e = np.log2(bins)
    return float(raw / max_e) if max_e > 0 else 0.5


def compute_signal_features(
    histories: Dict[str, List[Dict]],
    filter_features: Dict[str, Dict],
) -> Dict[str, Dict]:
    results = {}

    for sym in filter_features:
        candles = histories.get(sym, [])
        if len(candles) < 5:
            continue

        ff     = filter_features[sym]
        static = ff.get("static", False)

        prices  = np.array([c.get("price",  c.get("close", 0)) for c in candles], dtype=np.float64)
        opens   = np.array([c.get("open",   prices[i]) for i, c in enumerate(candles)], dtype=np.float64)
        highs   = np.array([c.get("high",   prices[i]) for i, c in enumerate(candles)], dtype=np.float64)
        lows    = np.array([c.get("low",    prices[i]) for i, c in enumerate(candles)], dtype=np.float64)
        volumes = np.array([c.get("volume", 0)         for c in candles], dtype=np.float64)

        if prices[-1] <= 0:
            continue

        price = float(prices[-1])

        # ── VWAP ──────────────────────────────────────────────────────────────
        typical = (highs + lows + prices) / 3.0
        pv_sum  = float(np.sum(typical * volumes))
        v_sum   = float(np.sum(volumes))
        vwap    = pv_sum / v_sum if v_sum > 0 else price

        # ── Z-Score ───────────────────────────────────────────────────────────
        n_z    = min(20, len(prices))
        p_win  = prices[-n_z:]
        z_mean = float(p_win.mean())
        z_std  = float(p_win.std())
        z_score = (price - z_mean) / z_std if z_std > 1e-6 else 0.0

        # ── Entropy ───────────────────────────────────────────────────────────
        if static:
            # Use OHLC range distribution as entropy proxy
            ranges  = highs - lows
            entropy = _shannon_entropy(ranges)
        else:
            log_ret = np.log(prices[1:] / prices[:-1])
            n_e     = min(20, len(log_ret))
            entropy = _shannon_entropy(log_ret[-n_e:])

        # ── Volatility expanding ──────────────────────────────────────────────
        if static:
            ranges     = highs - lows
            n_r        = min(20, len(ranges))
            sigma_now  = float(ranges[-1])
            sigma_mean = float(ranges[-n_r:].mean())
            vol_expanding = sigma_now > sigma_mean
        else:
            log_ret    = np.log(prices[1:] / prices[:-1])
            n_s        = min(20, len(log_ret))
            n_l        = min(50, len(log_ret))
            sigma_now  = float(log_ret[-n_s:].std() * np.sqrt(252)) if n_s >= 2 else 0.0
            sigma_mean = float(log_ret[-n_l:].std() * np.sqrt(252)) if n_l >= 2 else sigma_now
            vol_expanding = sigma_now > sigma_mean

        rel_vol = ff.get("rel_vol", 1.0)
        roc     = ff.get("roc", 0.0)

        # ── Boolean signals ───────────────────────────────────────────────────
        if static:
            # Market closed: use OHLC-based signals
            above_vwap        = float(prices[-1]) > float(opens[-1])   # close > open (bullish candle)
            momentum_positive = roc > 0 or float(highs[-1]) > float(highs[-2]) if len(highs) > 1 else False
            volume_spike      = float(volumes[-1]) > float(np.median(volumes))
            range_pct         = (float(highs[-1]) - float(lows[-1])) / float(lows[-1]) if lows[-1] > 0 else 0
            low_entropy       = range_pct > 0.005   # range > 0.5% = meaningful move
            vol_exp_bool      = bool(vol_expanding)
        else:
            above_vwap        = price > vwap
            momentum_positive = roc > 0
            volume_spike      = rel_vol > 1.5
            low_entropy       = entropy < 0.5
            vol_exp_bool      = bool(vol_expanding)

        score  = sum([above_vwap, momentum_positive, volume_spike, low_entropy, vol_exp_bool])
        regime = "TREND" if entropy < 0.5 else "RANGE"

        if score >= 4:
            signal = "STRONG BUY" if roc >= 0 else "STRONG SELL"
        elif score == 3:
            signal = "BUY" if roc >= 0 else "SELL"
        elif score == 2:
            signal = "WATCH" if roc >= 0 else "CAUTION"
        elif score == 1:
            signal = "NEUTRAL"
        else:
            signal = "NEUTRAL"

        results[sym] = {
            "symbol":            sym,
            "price":             round(price, 2),
            "open":              round(float(opens[-1]), 2),
            "high":              round(float(highs[-1]), 2),
            "low":               round(float(lows[-1]), 2),
            "vwap":              round(vwap, 2),
            "z_score":           round(z_score, 3),
            "entropy":           round(entropy, 4),
            "sigma":             round(sigma_now * 100 if not static else sigma_now, 2),
            "rel_vol":           round(rel_vol, 3),
            "roc":               round(roc * 100, 2),
            "above_vwap":        above_vwap,
            "momentum_positive": momentum_positive,
            "volume_spike":      volume_spike,
            "low_entropy":       low_entropy,
            "vol_expanding":     vol_exp_bool,
            "score":             score,
            "regime":            regime,
            "signal":            signal,
            "filter_score":      round(ff.get("filter_score", 0), 4),
            "market_closed":     static,
        }

    return results


def select_final_candidates(
    signals: Dict[str, Dict],
    min_score: int = 3,
    top_n: int = 10,
    market_closed: bool = False,
) -> List[Dict]:
    """
    Return top_n candidates.
    When market is closed, lower threshold to 1 so we still show data.
    """
    effective_min = 1 if market_closed else min_score
    qualified = [v for v in signals.values() if v["score"] >= effective_min]
    qualified.sort(key=lambda x: (x["score"], x["filter_score"]), reverse=True)
    return qualified[:top_n]
