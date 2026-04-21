"""
Market Regime Detection
========================
Classifies market into: TRENDING / RANGE_BOUND / VOLATILE / CHOPPY
using log returns, rolling volatility, and Shannon entropy.
"""

import math
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from collections import deque
import time

# ─── Config ───────────────────────────────────────────────────────────────────

WINDOW_SHORT = 20
WINDOW_LONG  = 50
MIN_BARS     = 5           # minimum bars required — lowered so regime works sooner
BINS         = 10          # histogram bins for entropy


# ─── Rolling Price Buffer ─────────────────────────────────────────────────────

class PriceBuffer:
    """Thread-safe rolling price buffer backed by a deque."""

    def __init__(self, maxlen: int = 300):
        self._prices: deque = deque(maxlen=maxlen)
        self._times:  deque = deque(maxlen=maxlen)

    def push(self, price: float, ts: Optional[float] = None):
        if price > 0:
            self._prices.append(price)
            self._times.append(ts or time.time())

    def to_series(self) -> pd.Series:
        return pd.Series(list(self._prices), dtype=float)

    def __len__(self):
        return len(self._prices)


# ─── Core Calculations ────────────────────────────────────────────────────────

def compute_log_returns(prices: pd.Series) -> pd.Series:
    """r_t = ln(P_t / P_{t-1})"""
    return np.log(prices / prices.shift(1)).dropna()


def compute_rolling_volatility(returns: pd.Series, window: int = WINDOW_SHORT) -> float:
    """
    sigma = std(r_t, window) * sqrt(252)
    Returns annualized volatility as a decimal (0.18 = 18%).
    """
    if len(returns) < window:
        return 0.0
    return float(returns.tail(window).std() * math.sqrt(252))


def compute_shannon_entropy(returns: pd.Series, bins: int = BINS, window: int = WINDOW_SHORT) -> float:
    """
    H(X) = -sum(p(x) * log2(p(x)))
    Normalized to [0, 1] by dividing by log2(bins).
    Higher entropy → more disorder / randomness.
    """
    if len(returns) < window:
        return 0.0

    data = returns.tail(window).dropna()
    if len(data) < 3:
        return 0.0

    counts, _ = np.histogram(data, bins=bins)
    total = counts.sum()
    if total == 0:
        return 0.0

    probs = counts[counts > 0] / total
    raw_entropy = -float(np.sum(probs * np.log2(probs)))
    max_entropy  = math.log2(bins)
    return raw_entropy / max_entropy if max_entropy > 0 else 0.0


def classify_regime(volatility: float, entropy: float) -> str:
    """
    Regime classification matrix:

    Low entropy  + Low vol  → TRENDING      (directional, low noise)
    Low entropy  + High vol → VOLATILE      (strong trend with big moves)
    High entropy + Low vol  → RANGE_BOUND   (choppy, small range)
    High entropy + High vol → CHAOTIC       (no direction, high noise)

    Thresholds calibrated for NSE indices (NIFTY annualized vol ~10-25%).
    """
    vol_hi  = volatility > 0.20   # 20% annualized
    ent_hi  = entropy    > 0.65   # 65% of max entropy

    if not ent_hi and not vol_hi:
        return "TRENDING"
    if not ent_hi and vol_hi:
        return "VOLATILE"
    if ent_hi and not vol_hi:
        return "RANGE_BOUND"
    return "CHAOTIC"


def compute_trend_strength(returns: pd.Series, window: int = WINDOW_SHORT) -> float:
    """
    Trend strength = |mean(returns)| / std(returns)
    Similar to Sharpe ratio of returns (t-statistic).
    High value → strong directional trend.
    """
    if len(returns) < window:
        return 0.0
    tail = returns.tail(window).dropna()
    std  = tail.std()
    if std == 0:
        return 0.0
    return abs(float(tail.mean()) / std)


def compute_hurst_exponent(prices: pd.Series, min_window: int = 10) -> float:
    """
    Hurst Exponent via rescaled range (R/S) analysis.
    H > 0.5 → trending (persistent)
    H = 0.5 → random walk
    H < 0.5 → mean-reverting
    """
    if len(prices) < 20:
        return 0.5

    lags  = range(2, min(20, len(prices) // 2))
    tau   = []
    lagv  = []

    for lag in lags:
        try:
            sub = np.log(prices.values[-lag*2:])
            sub_lag = sub[:lag]
            mean_s  = np.mean(sub_lag)
            devs    = np.cumsum(sub_lag - mean_s)
            r_s     = (np.max(devs) - np.min(devs)) / (np.std(sub_lag) + 1e-10)
            tau.append(r_s)
            lagv.append(lag)
        except Exception:
            pass

    if len(tau) < 3:
        return 0.5

    try:
        m = np.polyfit(np.log(lagv), np.log(tau), 1)
        return float(np.clip(m[0], 0.0, 1.0))
    except Exception:
        return 0.5


# ─── Full Regime Analysis ─────────────────────────────────────────────────────

def full_regime_analysis(prices: List[float]) -> Dict:
    """
    Run complete regime analysis on a price series.
    Returns dict compatible with /api/regime response.
    """
    if len(prices) < MIN_BARS:
        return {
            "regime":            "INSUFFICIENT_DATA",
            "entropy":           0.0,
            "entropy_normalized": 0.0,
            "volatility_20d":    0.0,
            "volatility_50d":    0.0,
            "trend_strength":    0.0,
            "hurst":             0.5,
            "log_returns":       [],
            "rolling_vol_20":    [],
            "rolling_entropy":   [],
            "signal":            "NEUTRAL",
        }

    series = pd.Series(prices, dtype=float)
    returns = compute_log_returns(series)

    # Use available data even if less than WINDOW_SHORT
    w_short = min(WINDOW_SHORT, len(returns))
    w_long  = min(WINDOW_LONG,  len(returns))

    vol_20  = compute_rolling_volatility(returns, w_short)
    vol_50  = compute_rolling_volatility(returns, w_long)
    entropy = compute_shannon_entropy(returns, BINS, w_short)
    trend_s = compute_trend_strength(returns, w_short)
    hurst   = compute_hurst_exponent(series)
    regime  = classify_regime(vol_20, entropy)

    # Rolling series for charting (last 100 points)
    rolling_vol   = [
        float(returns.iloc[:i+w_short].tail(w_short).std() * math.sqrt(252))
        for i in range(0, min(100, len(returns) - w_short + 1), 2)
    ] if len(returns) >= w_short else []

    rolling_entropy = [
        compute_shannon_entropy(returns.iloc[:i+w_short], BINS, w_short)
        for i in range(0, min(100, len(returns) - w_short + 1), 2)
    ] if len(returns) >= w_short else []

    # Trading signal from regime
    signal_map = {
        "TRENDING":    "FOLLOW_TREND",
        "VOLATILE":    "USE_OPTIONS_STRATEGIES",
        "RANGE_BOUND": "SELL_PREMIUM",
        "CHAOTIC":     "REDUCE_POSITION",
    }

    return {
        "regime":             regime,
        "entropy":            round(entropy, 4),
        "entropy_normalized": round(entropy, 4),
        "volatility_20d":     round(vol_20 * 100, 2),
        "volatility_50d":     round(vol_50 * 100, 2),
        "trend_strength":     round(trend_s, 4),
        "hurst":              round(hurst, 4),
        "log_returns":        [round(r, 6) for r in returns.tail(50).tolist()],
        "rolling_vol_20":     [round(v, 4) for v in rolling_vol],
        "rolling_entropy":    [round(e, 4) for e in rolling_entropy],
        "signal":             signal_map.get(regime, "NEUTRAL"),
        "timestamp":          time.time(),
    }


# ─── In-memory price store for each symbol ───────────────────────────────────

_price_buffers: Dict[str, PriceBuffer] = {}

def get_price_buffer(symbol: str) -> PriceBuffer:
    if symbol not in _price_buffers:
        _price_buffers[symbol] = PriceBuffer(maxlen=400)
    return _price_buffers[symbol]

def push_price(symbol: str, price: float, ts: Optional[float] = None):
    get_price_buffer(symbol).push(price, ts)

def get_regime(symbol: str) -> Dict:
    buf    = get_price_buffer(symbol)
    series = buf.to_series()
    return full_regime_analysis(series.tolist())
