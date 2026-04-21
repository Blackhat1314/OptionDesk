"""
Black-Scholes Option Pricing Engine
====================================
Implements BS model, all Greeks, Implied Volatility (Newton-Raphson),
GEX, DEX, Max Pain, VWAP, PCR calculations.
"""

import math
import numpy as np
from scipy.stats import norm
from typing import Optional, Tuple
from dataclasses import dataclass


# ─── Core BS Engine ───────────────────────────────────────────────────────────

def _d1_d2(S: float, K: float, r: float, sigma: float, T: float) -> Tuple[float, float]:
    """Compute d1, d2 for Black-Scholes."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0, 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return d1, d2


def bs_call_price(S: float, K: float, r: float, sigma: float, T: float) -> float:
    """Black-Scholes call option price."""
    if T <= 0:
        return max(S - K, 0.0)
    d1, d2 = _d1_d2(S, K, r, sigma, T)
    return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)


def bs_put_price(S: float, K: float, r: float, sigma: float, T: float) -> float:
    """Black-Scholes put option price."""
    if T <= 0:
        return max(K - S, 0.0)
    d1, d2 = _d1_d2(S, K, r, sigma, T)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


# ─── Greeks ───────────────────────────────────────────────────────────────────

def delta(S: float, K: float, r: float, sigma: float, T: float, option_type: str = "CE") -> float:
    """Delta: dV/dS"""
    if T <= 0 or sigma <= 0:
        intrinsic = 1.0 if (option_type == "CE" and S > K) else -1.0 if (option_type == "PE" and S < K) else 0.0
        return intrinsic
    d1, _ = _d1_d2(S, K, r, sigma, T)
    if option_type == "CE":
        return norm.cdf(d1)
    else:
        return norm.cdf(d1) - 1.0


def gamma(S: float, K: float, r: float, sigma: float, T: float) -> float:
    """Gamma: d²V/dS² (same for calls and puts)"""
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    d1, _ = _d1_d2(S, K, r, sigma, T)
    return norm.pdf(d1) / (S * sigma * math.sqrt(T))


def theta(S: float, K: float, r: float, sigma: float, T: float, option_type: str = "CE") -> float:
    """Theta: dV/dT (expressed per calendar day)"""
    if T <= 0 or sigma <= 0:
        return 0.0
    d1, d2 = _d1_d2(S, K, r, sigma, T)
    term1 = -(S * norm.pdf(d1) * sigma) / (2 * math.sqrt(T))
    if option_type == "CE":
        term2 = -r * K * math.exp(-r * T) * norm.cdf(d2)
    else:
        term2 = r * K * math.exp(-r * T) * norm.cdf(-d2)
    return (term1 + term2) / 365.0


def vega(S: float, K: float, r: float, sigma: float, T: float) -> float:
    """Vega: dV/dσ (expressed per 1% change in vol)"""
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    d1, _ = _d1_d2(S, K, r, sigma, T)
    return S * norm.pdf(d1) * math.sqrt(T) / 100.0


def rho(S: float, K: float, r: float, sigma: float, T: float, option_type: str = "CE") -> float:
    """Rho: dV/dr"""
    if T <= 0 or sigma <= 0:
        return 0.0
    _, d2 = _d1_d2(S, K, r, sigma, T)
    if option_type == "CE":
        return K * T * math.exp(-r * T) * norm.cdf(d2) / 100.0
    else:
        return -K * T * math.exp(-r * T) * norm.cdf(-d2) / 100.0


@dataclass
class OptionGreeks:
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    rho: float = 0.0


def compute_all_greeks(
    S: float, K: float, r: float, sigma: float, T: float, option_type: str = "CE"
) -> OptionGreeks:
    """Compute all Greeks in one pass (avoids redundant d1/d2 calc)."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        if T <= 0:
            if option_type == "CE":
                d = 1.0 if S > K else 0.0
            else:
                d = -1.0 if S < K else 0.0
            return OptionGreeks(delta=d)
        return OptionGreeks()

    d1, d2 = _d1_d2(S, K, r, sigma, T)
    sqrt_T = math.sqrt(T)
    Nd1 = norm.cdf(d1)
    nd1 = norm.pdf(d1)
    exp_rT = math.exp(-r * T)

    _delta = Nd1 if option_type == "CE" else Nd1 - 1.0
    _gamma = nd1 / (S * sigma * sqrt_T)
    _theta_term1 = -(S * nd1 * sigma) / (2 * sqrt_T)
    if option_type == "CE":
        _theta = (_theta_term1 - r * K * exp_rT * norm.cdf(d2)) / 365.0
    else:
        _theta = (_theta_term1 + r * K * exp_rT * norm.cdf(-d2)) / 365.0
    _vega = S * nd1 * sqrt_T / 100.0
    if option_type == "CE":
        _rho = K * T * exp_rT * norm.cdf(d2) / 100.0
    else:
        _rho = -K * T * exp_rT * norm.cdf(-d2) / 100.0

    return OptionGreeks(delta=_delta, gamma=_gamma, theta=_theta, vega=_vega, rho=_rho)


# ─── Implied Volatility (Newton-Raphson) ──────────────────────────────────────

def implied_volatility(
    market_price: float,
    S: float,
    K: float,
    r: float,
    T: float,
    option_type: str = "CE",
    tol: float = 1e-6,
    max_iter: int = 200,
    initial_sigma: float = 0.3,
) -> float:
    """
    Compute Implied Volatility using Newton-Raphson method.
    Returns 0.0 if convergence fails or inputs are invalid.
    """
    if T <= 0 or market_price <= 0 or S <= 0 or K <= 0:
        return 0.0

    # Intrinsic value check
    intrinsic = max(S - K, 0.0) if option_type == "CE" else max(K - S, 0.0)
    if market_price < intrinsic - 0.01:
        return 0.0

    sigma = initial_sigma

    for _ in range(max_iter):
        if option_type == "CE":
            price = bs_call_price(S, K, r, sigma, T)
        else:
            price = bs_put_price(S, K, r, sigma, T)

        price_diff = market_price - price

        if abs(price_diff) < tol:
            return sigma

        # Vega (not divided by 100 here, raw)
        d1, _ = _d1_d2(S, K, r, sigma, T)
        vega_raw = S * norm.pdf(d1) * math.sqrt(T)

        if abs(vega_raw) < 1e-10:
            break

        sigma += price_diff / vega_raw
        sigma = max(0.001, min(sigma, 20.0))  # clamp

    # Fallback: bisection for robustness
    return _iv_bisection(market_price, S, K, r, T, option_type)


def _iv_bisection(
    market_price: float,
    S: float,
    K: float,
    r: float,
    T: float,
    option_type: str,
    low: float = 0.001,
    high: float = 10.0,
    tol: float = 1e-5,
    max_iter: int = 100,
) -> float:
    """Bisection method as fallback for IV calculation."""
    price_fn = bs_call_price if option_type == "CE" else bs_put_price

    for _ in range(max_iter):
        mid = (low + high) / 2.0
        price = price_fn(S, K, r, mid, T)
        diff = price - market_price

        if abs(diff) < tol:
            return mid

        if diff > 0:
            high = mid
        else:
            low = mid

        if high - low < tol:
            return (low + high) / 2.0

    return (low + high) / 2.0


# ─── Market Analytics ─────────────────────────────────────────────────────────

def compute_pcr(call_oi: int, put_oi: int) -> float:
    """Put-Call Ratio by Open Interest."""
    if call_oi <= 0:
        return 0.0
    return put_oi / call_oi


def compute_pcr_volume(call_vol: int, put_vol: int) -> float:
    """Put-Call Ratio by Volume."""
    if call_vol <= 0:
        return 0.0
    return put_vol / call_vol


def compute_max_pain(strikes: list, call_oi: list, put_oi: list) -> float:
    """
    Max Pain = strike where total option buyers lose the most.
    For each strike K, compute total payout if expiry = K:
      - Call writers pay max(K - strike, 0) * OI for all strikes < K
      - Put writers pay max(strike - K, 0) * OI for all strikes > K
    The max pain is the strike minimizing total payout to buyers.
    """
    if not strikes:
        return 0.0

    min_pain = float("inf")
    max_pain_strike = strikes[0]

    for test_strike in strikes:
        total_pain = 0.0
        for i, k in enumerate(strikes):
            # Call payoff at expiry test_strike
            total_pain += max(test_strike - k, 0.0) * call_oi[i]
            # Put payoff at expiry test_strike
            total_pain += max(k - test_strike, 0.0) * put_oi[i]

        if total_pain < min_pain:
            min_pain = total_pain
            max_pain_strike = test_strike

    return max_pain_strike


def compute_vwap(prices: list, volumes: list) -> float:
    """Volume-Weighted Average Price."""
    if not prices or not volumes:
        return 0.0
    total_vol = sum(volumes)
    if total_vol == 0:
        return 0.0
    return sum(p * v for p, v in zip(prices, volumes)) / total_vol


def compute_gamma_exposure(
    S: float,
    K: float,
    r: float,
    sigma: float,
    T: float,
    oi: int,
    option_type: str,
    lot_size: int = 50,
) -> float:
    """
    GEX per 1% spot move = Gamma * OI * LotSize * Spot² * 0.01
    Sign: Calls → +GEX (dealers long gamma), Puts → -GEX (dealers short gamma)
    Result in raw rupees. Normalize to Crores at display layer (/1e7).
    """
    g = gamma(S, K, r, sigma, T)
    sign = 1.0 if option_type == "CE" else -1.0
    return sign * g * oi * lot_size * (S * S) * 0.01


def compute_delta_exposure(
    S: float,
    K: float,
    r: float,
    sigma: float,
    T: float,
    oi: int,
    option_type: str,
    lot_size: int = 50,
) -> float:
    """
    DEX (Notional Delta) = Delta * OI * LotSize * Spot
    Calls → positive, Puts → negative (delta is already negative for puts).
    Result in raw rupees. Normalize to Crores at display layer (/1e7).
    """
    d = delta(S, K, r, sigma, T, option_type)
    return d * oi * lot_size * S


def find_gamma_flip(gex_by_strike: dict) -> float:
    """
    Gamma Flip Level: Strike where cumulative GEX crosses zero.
    Below flip → negative GEX (destabilizing), above → positive (stabilizing).
    """
    if not gex_by_strike:
        return 0.0

    strikes = sorted(gex_by_strike.keys())
    cumulative = 0.0
    prev_strike = None
    prev_gex = 0.0

    for s in strikes:
        cumulative += gex_by_strike[s]
        if prev_strike is not None and prev_gex * cumulative < 0:
            # Linear interpolation
            frac = abs(prev_gex) / (abs(prev_gex) + abs(cumulative))
            return prev_strike + frac * (s - prev_strike)
        prev_gex = cumulative
        prev_strike = s

    return 0.0


def days_to_expiry(expiry_str: str) -> float:
    """Convert expiry date string (YYYY-MM-DD) to years as float."""
    from datetime import datetime
    import pytz

    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)

    try:
        expiry_dt = datetime.strptime(expiry_str, "%Y-%m-%d")
        expiry_dt = ist.localize(expiry_dt.replace(hour=15, minute=30))
        diff = (expiry_dt - now).total_seconds()
        return max(diff / (365.25 * 24 * 3600), 0.0)
    except Exception:
        return 0.0


def compute_iv_rank(current_iv: float, iv_history: list) -> float:
    """IV Rank = (current_iv - 52w_low) / (52w_high - 52w_low)"""
    if not iv_history:
        return 0.0
    iv_low = min(iv_history)
    iv_high = max(iv_history)
    if iv_high == iv_low:
        return 0.0
    return (current_iv - iv_low) / (iv_high - iv_low) * 100.0


def compute_iv_percentile(current_iv: float, iv_history: list) -> float:
    """IV Percentile = % of days where IV was below current IV."""
    if not iv_history:
        return 0.0
    below = sum(1 for iv in iv_history if iv < current_iv)
    return (below / len(iv_history)) * 100.0


def compute_historical_volatility(prices: list, window: int = 30, intraday: bool = False) -> float:
    """
    Historical Volatility (Close-to-Close).
    Returns annualized HV as a decimal (e.g., 0.18 = 18%).

    annualization_factor:
      - Daily data:   sqrt(252)
      - 5-min intraday: sqrt(252 * 75)  — 75 five-minute bars per trading day
    """
    if len(prices) < window + 1:
        return 0.0

    returns = []
    for i in range(1, len(prices)):
        if prices[i - 1] > 0:
            returns.append(math.log(prices[i] / prices[i - 1]))

    if len(returns) < window:
        return 0.0

    recent = returns[-window:]
    mean_r = sum(recent) / len(recent)
    variance = sum((r - mean_r) ** 2 for r in recent) / (len(recent) - 1)

    # Annualize: daily → 252 trading days; 5-min intraday → 252 * 75 bars/year
    ann_factor = math.sqrt(252 * 75) if intraday else math.sqrt(252)
    return math.sqrt(variance) * ann_factor
