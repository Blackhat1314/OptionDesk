"""
Risk Engine — Monte Carlo simulation for position sizing.
==========================================================
Vectorized NumPy. No ML. GBM model only.

Model: S_t = S0 * exp((mu - 0.5*sigma^2)*t + sigma*sqrt(t)*Z)
  Z ~ N(0,1), t = 1 (1-day horizon)
  Simulations: 2000
  Inputs: last 50 log returns

Outputs per stock:
  expected_price    : mean of simulated end prices
  prob_up           : % simulations ending above S0
  prob_down         : % simulations ending below S0
  worst_case_5pct   : 5th percentile of simulated prices
  best_case_95pct   : 95th percentile
  position_size_advice: REDUCED if worst_case drop > 5%, else NORMAL
"""

import numpy as np
from typing import Dict, List


N_SIMS = 2000
T      = 1.0          # 1-day horizon
SEED   = 42
REDUCED_THRESHOLD = 0.05   # 5% worst-case drop triggers REDUCED sizing


def run_monte_carlo(symbol: str, price: float, log_returns: np.ndarray) -> Dict:
    """
    Run GBM Monte Carlo for a single stock.
    log_returns: array of recent log returns (last 50 preferred)
    """
    if len(log_returns) < 5 or price <= 0:
        return _empty_result(symbol, price)

    mu    = float(log_returns.mean())
    sigma = float(log_returns.std())

    if sigma < 1e-8:
        return _empty_result(symbol, price)

    rng = np.random.default_rng(SEED)
    Z   = rng.standard_normal(N_SIMS)

    # GBM terminal prices
    S_T = price * np.exp((mu - 0.5 * sigma ** 2) * T + sigma * np.sqrt(T) * Z)

    expected   = float(S_T.mean())
    prob_up    = float((S_T > price).mean() * 100)
    prob_down  = float((S_T < price).mean() * 100)
    worst_5pct = float(np.percentile(S_T, 5))
    best_95pct = float(np.percentile(S_T, 95))

    drop_pct = (price - worst_5pct) / price if price > 0 else 0
    position_advice = "REDUCED" if drop_pct > REDUCED_THRESHOLD else "NORMAL"

    return {
        "symbol":              symbol,
        "current_price":       round(price, 2),
        "expected_price":      round(expected, 2),
        "prob_up":             round(prob_up, 1),
        "prob_down":           round(prob_down, 1),
        "worst_case_5pct":     round(worst_5pct, 2),
        "best_case_95pct":     round(best_95pct, 2),
        "worst_case_drop_pct": round(drop_pct * 100, 2),
        "position_size_advice": position_advice,
        "simulations":         N_SIMS,
    }


def run_risk_for_candidates(
    candidates: List[Dict],
    histories:  Dict[str, List[Dict]],
) -> List[Dict]:
    """
    Run Monte Carlo for each candidate. Merges risk metrics into candidate dict.
    Returns enriched candidate list.
    """
    enriched = []
    for cand in candidates:
        sym     = cand["symbol"]
        price   = cand["price"]
        candles = histories.get(sym, [])

        if len(candles) >= 6:
            prices   = np.array([c["price"] for c in candles], dtype=np.float64)
            log_ret  = np.log(prices[1:] / prices[:-1])
            window   = log_ret[-50:] if len(log_ret) >= 50 else log_ret
            risk     = run_monte_carlo(sym, price, window)
        else:
            risk = _empty_result(sym, price)

        enriched.append({**cand, "risk_metrics": risk})

    return enriched


def _empty_result(symbol: str, price: float) -> Dict:
    return {
        "symbol":               symbol,
        "current_price":        round(price, 2),
        "expected_price":       round(price, 2),
        "prob_up":              50.0,
        "prob_down":            50.0,
        "worst_case_5pct":      round(price * 0.95, 2),
        "best_case_95pct":      round(price * 1.05, 2),
        "worst_case_drop_pct":  5.0,
        "position_size_advice": "NORMAL",
        "simulations":          0,
    }
