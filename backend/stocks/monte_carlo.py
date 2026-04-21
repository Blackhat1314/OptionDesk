"""
stocks/monte_carlo.py
GBM Monte Carlo - vectorized NumPy, no ML.

Improvements over naive GBM:
  1. Hybrid mu   : 0.7 * mean(1Y) + 0.3 * mean(3Y)  - adaptive, stable
  2. Hybrid sigma: 0.6 * std(6M)  + 0.4 * std(1Y)   - recent-weighted, less noisy
  3. Drift adj   : (mu - 0.5*sigma^2) - Ito correction, prevents return overestimation
  4. Regime      : vol-regime scales sigma; trend-regime nudges mu
  5. Horizons    : 60 days (2M) and 252 days (1Y) only
"""

import math
import numpy as np
from typing import Dict, Optional

N_SIMS = 5000
SEED   = 42

# Standard horizons pre-computed during pipeline
STANDARD_HORIZONS = [63, 126, 252]   # 3M, 6M, 1Y

# Window sizes (trading days)
W_6M = 126
W_1Y = 252
W_3Y = 756

# Horizon labels
HORIZON_LABELS = {63: "3M", 126: "6M", 252: "1Y"}


# ── Hybrid mu / sigma estimation ──────────────────────────────────────────────

def _estimate_params(log_returns: np.ndarray):
    """
    Compute hybrid mu and sigma with regime awareness.

    mu    = 0.7 * mean(1Y) + 0.3 * mean(3Y)
    sigma = 0.6 * std(6M)  + 0.4 * std(1Y)

    Regime adjustments (pure statistical, no ML):
      HIGH_VOL : recent 6M vol > 1.5x 1Y vol  -> scale sigma up 10%
      LOW_VOL  : recent 6M vol < 0.7x 1Y vol  -> scale sigma down 5%
      TRENDING : |mean(1Y)| > 1.5x |mean(3Y)| -> weight mu more to 1Y
    """
    n = len(log_returns)

    # mu: hybrid 1Y + 3Y
    mu_1y = float(log_returns[-W_1Y:].mean()) if n >= W_1Y else float(log_returns.mean())
    mu_3y = float(log_returns[-W_3Y:].mean()) if n >= W_3Y else mu_1y
    mu    = 0.7 * mu_1y + 0.3 * mu_3y

    # sigma: hybrid 6M + 1Y
    sig_6m = float(log_returns[-W_6M:].std()) if n >= W_6M else float(log_returns.std())
    sig_1y = float(log_returns[-W_1Y:].std()) if n >= W_1Y else sig_6m
    sigma  = 0.6 * sig_6m + 0.4 * sig_1y

    if sigma < 1e-8:
        return mu, sigma, "FLAT"

    # Regime detection
    vol_ratio   = sig_6m / sig_1y if sig_1y > 1e-8 else 1.0
    trend_ratio = abs(mu_1y) / abs(mu_3y) if abs(mu_3y) > 1e-8 else 1.0

    regime = "NORMAL"

    if vol_ratio > 1.5:
        sigma  *= 1.10
        regime  = "HIGH_VOL"
    elif vol_ratio < 0.7:
        sigma  *= 0.95
        regime  = "LOW_VOL"

    if trend_ratio > 1.5:
        mu = 0.85 * mu_1y + 0.15 * mu_3y
        if regime == "NORMAL":
            regime = "TRENDING"
        else:
            regime += "+TRENDING"

    return mu, sigma, regime


# ── Single-horizon MC ─────────────────────────────────────────────────────────

def run_monte_carlo(
    symbol:      str,
    price:       float,
    log_returns: np.ndarray,
    horizon:     int = 60,
) -> Dict:
    """
    GBM with hybrid params and Ito drift correction.
    S_t = S0 * exp((mu - 0.5*sigma^2)*t + sigma*sqrt(t)*Z)
    """
    if len(log_returns) < 10 or price <= 0:
        return _empty(symbol, price, horizon)

    mu, sigma, regime = _estimate_params(log_returns)

    if sigma < 1e-8:
        return _empty(symbol, price, horizon)

    rng = np.random.default_rng(SEED)
    Z   = rng.standard_normal((N_SIMS, horizon))

    drift     = (mu - 0.5 * sigma ** 2)
    diffusion = sigma * Z
    log_paths = np.cumsum(drift + diffusion, axis=1)
    S_T       = price * np.exp(log_paths[:, -1])

    return _build_result(symbol, price, horizon, S_T, regime)


# ── Multi-horizon MC (pipeline entry point) ───────────────────────────────────

def run_multi_horizon_mc(
    symbol:      str,
    price:       float,
    log_returns: np.ndarray,
) -> Dict:
    """
    Run MC for 2M (60d) and 1Y (252d) using shared hybrid params.
    Single param estimation ensures consistency across horizons.
    """
    if len(log_returns) < 10 or price <= 0:
        return {str(h): _empty(symbol, price, h) for h in STANDARD_HORIZONS}

    mu, sigma, regime = _estimate_params(log_returns)

    if sigma < 1e-8:
        return {str(h): _empty(symbol, price, h) for h in STANDARD_HORIZONS}

    results = {}
    for horizon in STANDARD_HORIZONS:
        rng = np.random.default_rng(SEED)
        Z   = rng.standard_normal((N_SIMS, horizon))

        drift     = (mu - 0.5 * sigma ** 2)
        diffusion = sigma * Z
        log_paths = np.cumsum(drift + diffusion, axis=1)
        S_T       = price * np.exp(log_paths[:, -1])

        results[str(horizon)] = _build_result(symbol, price, horizon, S_T, regime)

    return results


# ── Result builder ────────────────────────────────────────────────────────────

def _build_result(symbol: str, price: float, horizon: int, S_T: np.ndarray, regime: str) -> Dict:
    expected   = float(S_T.mean())
    prob_up    = float((S_T > price).mean() * 100)
    prob_down  = float((S_T < price).mean() * 100)
    worst_5pct = float(np.percentile(S_T, 5))
    best_95pct = float(np.percentile(S_T, 95))
    median     = float(np.percentile(S_T, 50))
    drop_pct   = (price - worst_5pct) / price if price > 0 else 0.0

    return_pcts = {
        "p5":      round(float(np.percentile(S_T, 5))  / price, 6),
        "p10":     round(float(np.percentile(S_T, 10)) / price, 6),
        "p25":     round(float(np.percentile(S_T, 25)) / price, 6),
        "p50":     round(median / price, 6),
        "p75":     round(float(np.percentile(S_T, 75)) / price, 6),
        "p90":     round(float(np.percentile(S_T, 90)) / price, 6),
        "p95":     round(float(np.percentile(S_T, 95)) / price, 6),
        "mean":    round(expected / price, 6),
        "prob_up": round(prob_up, 1),
    }

    return {
        "symbol":               symbol,
        "current_price":        round(price, 2),
        "horizon_days":         horizon,
        "horizon_label":        HORIZON_LABELS.get(horizon, f"{horizon}D"),
        "regime":               regime,
        "expected_price":       round(expected, 2),
        "median_price":         round(median, 2),
        "worst_case_5pct":      round(worst_5pct, 2),
        "best_case_95pct":      round(best_95pct, 2),
        "return_expected":      round((expected   - price) / price * 100, 2),
        "return_median":        round((median     - price) / price * 100, 2),
        "return_worst_5pct":    round((worst_5pct - price) / price * 100, 2),
        "return_best_95pct":    round((best_95pct - price) / price * 100, 2),
        "prob_up":              round(prob_up, 1),
        "prob_down":            round(prob_down, 1),
        "worst_case_drop_pct":  round(drop_pct * 100, 2),
        "position_size_advice": "REDUCED" if drop_pct > 0.05 else "NORMAL",
        "simulations":          N_SIMS,
        "return_pcts":          return_pcts,
    }


# ── Investment simulator (instant O(1)) ───────────────────────────────────────

def simulate_from_cache(cached_mc: Dict, price: float, investment: float, horizon: int) -> Dict:
    """
    Instant investment simulation using pre-cached return percentiles.
    No simulation needed - multiply cached multipliers by investment amount.
    """
    horizon_key = str(horizon)

    mc = None
    if horizon_key in cached_mc:
        mc = cached_mc[horizon_key]
    elif "return_pcts" in cached_mc:
        mc = cached_mc
    else:
        available = [int(k) for k in cached_mc.keys() if k.isdigit()]
        if available:
            closest = min(available, key=lambda h: abs(h - horizon))
            mc = cached_mc[str(closest)]

    if not mc or "return_pcts" not in mc:
        return None

    rp           = mc["return_pcts"]
    shares       = investment / price if price > 0 else 0
    expected_val = investment * rp["mean"]
    worst_case   = investment * rp["p5"]
    best_case    = investment * rp["p95"]
    median_val   = investment * rp["p50"]
    prob_profit  = rp["prob_up"]

    return {
        "investment":      round(investment, 0),
        "horizon_days":    horizon,
        "horizon_label":   mc.get("horizon_label", HORIZON_LABELS.get(horizon, f"{horizon}D")),
        "regime":          mc.get("regime", "NORMAL"),
        "shares":          round(shares, 4),
        "expected_value":  round(expected_val, 0),
        "median_value":    round(median_val, 0),
        "best_case":       round(best_case, 0),
        "worst_case":      round(worst_case, 0),
        "prob_profit":     round(prob_profit, 1),
        "expected_return": round((expected_val - investment) / investment * 100, 2),
        "median_return":   round((median_val   - investment) / investment * 100, 2),
        "best_return":     round((best_case    - investment) / investment * 100, 2),
        "worst_return":    round((worst_case   - investment) / investment * 100, 2),
        "from_cache":      True,
    }


# ── Full simulation fallback ──────────────────────────────────────────────────

def simulate_investment(price: float, log_returns: np.ndarray, investment: float, horizon: int = 252) -> Dict:
    """
    Full investment simulation (N_SIMS GBM paths).
    Fallback when no cached data is available. Uses same hybrid params as pipeline.
    """
    if len(log_returns) < 10 or price <= 0 or investment <= 0:
        return _empty_sim(investment, horizon)

    mu, sigma, regime = _estimate_params(log_returns)

    if sigma < 1e-8:
        shares = investment / price
        return {
            "investment": investment, "horizon_days": horizon,
            "horizon_label": HORIZON_LABELS.get(horizon, f"{horizon}D"),
            "shares": round(shares, 4), "expected_value": round(investment, 2),
            "median_value": round(investment, 2), "best_case": round(investment, 2),
            "worst_case": round(investment, 2), "prob_profit": 50.0,
            "expected_return": 0.0, "median_return": 0.0,
            "best_return": 0.0, "worst_return": 0.0,
            "regime": regime, "from_cache": False,
        }

    shares = investment / price
    rng    = np.random.default_rng(SEED + 1)
    Z      = rng.standard_normal((N_SIMS, horizon))

    drift     = (mu - 0.5 * sigma ** 2)
    diffusion = sigma * Z
    log_paths = np.cumsum(drift + diffusion, axis=1)
    S_T       = price * np.exp(log_paths[:, -1])

    portfolio_values = shares * S_T
    expected_val = float(portfolio_values.mean())
    median_val   = float(np.percentile(portfolio_values, 50))
    worst_case   = float(np.percentile(portfolio_values, 5))
    best_case    = float(np.percentile(portfolio_values, 95))
    prob_profit  = float((portfolio_values > investment).mean() * 100)

    return {
        "investment":      round(investment, 0),
        "horizon_days":    horizon,
        "horizon_label":   HORIZON_LABELS.get(horizon, f"{horizon}D"),
        "regime":          regime,
        "shares":          round(shares, 4),
        "expected_value":  round(expected_val, 0),
        "median_value":    round(median_val, 0),
        "best_case":       round(best_case, 0),
        "worst_case":      round(worst_case, 0),
        "prob_profit":     round(prob_profit, 1),
        "expected_return": round((expected_val - investment) / investment * 100, 2),
        "median_return":   round((median_val   - investment) / investment * 100, 2),
        "best_return":     round((best_case    - investment) / investment * 100, 2),
        "worst_return":    round((worst_case   - investment) / investment * 100, 2),
        "from_cache":      False,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _empty(symbol: str, price: float, horizon: int) -> Dict:
    return {
        "symbol":               symbol,
        "current_price":        round(price, 2),
        "horizon_days":         horizon,
        "horizon_label":        HORIZON_LABELS.get(horizon, f"{horizon}D"),
        "regime":               "INSUFFICIENT_DATA",
        "expected_price":       round(price, 2),
        "median_price":         round(price, 2),
        "worst_case_5pct":      round(price * 0.95, 2),
        "best_case_95pct":      round(price * 1.05, 2),
        "return_expected":      0.0,
        "return_median":        0.0,
        "return_worst_5pct":    -5.0,
        "return_best_95pct":    5.0,
        "prob_up":              50.0,
        "prob_down":            50.0,
        "worst_case_drop_pct":  5.0,
        "position_size_advice": "NORMAL",
        "simulations":          0,
        "return_pcts": {
            "p5": 0.95, "p10": 0.96, "p25": 0.98,
            "p50": 1.0, "p75": 1.02, "p90": 1.04, "p95": 1.05,
            "mean": 1.0, "prob_up": 50.0,
        },
    }


def _empty_sim(investment: float, horizon: int) -> Dict:
    return {
        "investment": investment, "horizon_days": horizon,
        "horizon_label": HORIZON_LABELS.get(horizon, f"{horizon}D"),
        "regime": "INSUFFICIENT_DATA",
        "shares": 0, "expected_value": investment,
        "median_value": investment, "best_case": investment, "worst_case": investment,
        "prob_profit": 50.0, "expected_return": 0.0,
        "median_return": 0.0, "best_return": 0.0, "worst_return": 0.0,
        "from_cache": False,
    }
