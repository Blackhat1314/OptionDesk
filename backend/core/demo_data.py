"""
Demo Data Generator
====================
Generates realistic synthetic NIFTY/BANKNIFTY option chain data
when Dhan API credentials are not configured or unavailable.
Useful for UI development, demos, and testing.

Replicates real market behavior:
- Realistic IV smile (higher on wings, lower at ATM)
- Correlated OI / volume distributions
- Proper Greeks via Black-Scholes
- Time-decaying state on each call
"""

import math
import random
import time
from datetime import date, timedelta
from typing import Dict, List, Tuple

from calculations.black_scholes import (
    bs_call_price,
    bs_put_price,
    compute_all_greeks,
    implied_volatility,
)

# ─── Spot Price State (simulated brownian motion) ─────────────────────────────

_SPOT_STATE: Dict[str, float] = {
    "NIFTY": 22500.0,
    "BANKNIFTY": 48000.0,
    "FINNIFTY": 21500.0,
    "MIDCPNIFTY": 10500.0,
}

_SPOT_DRIFT: Dict[str, float] = {k: 0.0 for k in _SPOT_STATE}


def _tick_spot(symbol: str) -> float:
    """Random walk with mean reversion for demo spot price."""
    mu = 0.0
    sigma = {"NIFTY": 30, "BANKNIFTY": 80, "FINNIFTY": 40, "MIDCPNIFTY": 20}.get(symbol, 30)
    dt = 5 / (252 * 6.5 * 3600)  # 5-second interval

    current = _SPOT_STATE.get(symbol, 22500.0)
    # Brownian motion + mild mean reversion toward starting price
    base = {"NIFTY": 22500, "BANKNIFTY": 48000, "FINNIFTY": 21500, "MIDCPNIFTY": 10500}[symbol]
    reversion = -0.001 * (current - base)
    shock = sigma * math.sqrt(dt) * random.gauss(0, 1)
    new_spot = current + reversion + shock
    _SPOT_STATE[symbol] = round(new_spot, 2)
    return _SPOT_STATE[symbol]


# ─── Expiry Generation ────────────────────────────────────────────────────────

def _generate_expiries(symbol: str) -> List[str]:
    """Generate realistic weekly/monthly expiry list."""
    today = date.today()
    expiries = []

    # Next 4 weekly Thursdays
    days_to_thursday = (3 - today.weekday()) % 7
    if days_to_thursday == 0:
        days_to_thursday = 7
    current = today + timedelta(days=days_to_thursday)
    for _ in range(4):
        expiries.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=7)

    # Next 3 monthly last-Thursday expiries
    for m_offset in range(1, 4):
        y, m = today.year, today.month + m_offset
        if m > 12:
            y += 1
            m -= 12
        # Last Thursday of month
        last_day = date(y, m, 28) + timedelta(days=4 - (date(y, m, 28).weekday() + 7) % 7)
        if last_day not in [date.fromisoformat(e) for e in expiries]:
            expiries.append(last_day.strftime("%Y-%m-%d"))

    return sorted(set(expiries))


# ─── Strike Generation ────────────────────────────────────────────────────────

def _get_strike_step(symbol: str) -> int:
    return {"NIFTY": 50, "BANKNIFTY": 100, "FINNIFTY": 50, "MIDCPNIFTY": 25}.get(symbol, 50)


def _get_atm_strike(spot: float, step: int) -> float:
    return round(spot / step) * step


# ─── IV Smile Model ───────────────────────────────────────────────────────────

def _iv_smile(moneyness: float, base_iv: float = 0.17) -> float:
    """
    Realistic IV smile: higher wings, lower ATM.
    moneyness = strike / spot
    """
    skew = -0.04 * (moneyness - 1.0)          # negative skew (put wing higher)
    smile = 0.12 * (moneyness - 1.0) ** 2     # convexity
    iv = base_iv + skew + smile
    return max(0.05, min(iv, 0.80))


# ─── OI Distribution ─────────────────────────────────────────────────────────

def _oi_distribution(strike: float, atm: float, step: int, base_oi: int = 1_000_000) -> Tuple[int, int]:
    """
    Calls: OI peaks above ATM (resistance)
    Puts: OI peaks below ATM (support)
    """
    call_dist = math.exp(-0.5 * ((strike - (atm + 2 * step)) / (4 * step)) ** 2)
    put_dist = math.exp(-0.5 * ((strike - (atm - 2 * step)) / (4 * step)) ** 2)

    call_oi = int(base_oi * call_dist * random.uniform(0.7, 1.3))
    put_oi = int(base_oi * put_dist * random.uniform(0.7, 1.3))
    return max(call_oi, 100), max(put_oi, 100)


# ─── Main Generator ───────────────────────────────────────────────────────────

def generate_demo_option_chain(symbol: str, expiry: str) -> Dict:
    """
    Generate a realistic full option chain dict in Dhan API format.
    Called when DHAN_ACCESS_TOKEN is empty/demo.
    """
    spot = _tick_spot(symbol)
    step = _get_strike_step(symbol)
    atm = _get_atm_strike(spot, step)
    rf = 0.065

    # Days to expiry
    try:
        exp_date = date.fromisoformat(expiry)
        T = max((exp_date - date.today()).days / 365.0, 1 / 365.0)
    except Exception:
        T = 7 / 365.0

    # 25 strikes either side of ATM
    num_strikes = 25
    strikes = [atm + (i - num_strikes // 2) * step for i in range(num_strikes + 1)]

    base_iv = {"NIFTY": 0.14, "BANKNIFTY": 0.17, "FINNIFTY": 0.15, "MIDCPNIFTY": 0.18}.get(symbol, 0.15)

    oc: Dict[str, Dict] = {}
    for strike in strikes:
        moneyness = strike / spot
        iv = _iv_smile(moneyness, base_iv)

        call_price = bs_call_price(spot, strike, rf, iv, T)
        put_price = bs_put_price(spot, strike, rf, iv, T)

        call_greeks = compute_all_greeks(spot, strike, rf, iv, T, "CE")
        put_greeks = compute_all_greeks(spot, strike, rf, iv, T, "PE")

        call_oi, put_oi = _oi_distribution(strike, atm, step)

        # Volumes: correlated with OI
        call_vol = int(call_oi * random.uniform(0.05, 0.25))
        put_vol = int(put_oi * random.uniform(0.05, 0.25))

        # OI change: positive on high OI strikes
        call_oi_chg = int(call_oi * random.gauss(0.02, 0.08))
        put_oi_chg = int(put_oi * random.gauss(0.02, 0.08))

        # Bid/ask spread: tighter near ATM
        ba_spread_pct = 0.01 + 0.04 * abs(moneyness - 1.0)

        strike_key = str(int(strike))
        oc[strike_key] = {
            "CE": {
                "security_id": f"CE{int(strike)}",
                "tradingSymbol": f"{symbol}{expiry.replace('-', '')}{int(strike)}CE",
                "last_price": round(call_price, 2),
                "oi": call_oi,
                "oi_day_change": call_oi_chg,
                "volume": call_vol,
                "implied_volatility": round(iv * 100, 2),
                "bid_price": round(call_price * (1 - ba_spread_pct), 2),
                "ask_price": round(call_price * (1 + ba_spread_pct), 2),
                "delta": round(call_greeks.delta, 4),
                "gamma": round(call_greeks.gamma, 6),
                "theta": round(call_greeks.theta, 4),
                "vega": round(call_greeks.vega, 4),
                "open": round(call_price * random.uniform(0.9, 1.1), 2),
                "high": round(call_price * random.uniform(1.0, 1.2), 2),
                "low": round(call_price * random.uniform(0.8, 1.0), 2),
                "close": round(call_price * random.uniform(0.95, 1.05), 2),
            },
            "PE": {
                "security_id": f"PE{int(strike)}",
                "tradingSymbol": f"{symbol}{expiry.replace('-', '')}{int(strike)}PE",
                "last_price": round(put_price, 2),
                "oi": put_oi,
                "oi_day_change": put_oi_chg,
                "volume": put_vol,
                "implied_volatility": round((_iv_smile(1 / moneyness, base_iv) if moneyness > 0 else iv) * 100, 2),
                "bid_price": round(put_price * (1 - ba_spread_pct), 2),
                "ask_price": round(put_price * (1 + ba_spread_pct), 2),
                "delta": round(put_greeks.delta, 4),
                "gamma": round(put_greeks.gamma, 6),
                "theta": round(put_greeks.theta, 4),
                "vega": round(put_greeks.vega, 4),
                "open": round(put_price * random.uniform(0.9, 1.1), 2),
                "high": round(put_price * random.uniform(1.0, 1.2), 2),
                "low": round(put_price * random.uniform(0.8, 1.0), 2),
                "close": round(put_price * random.uniform(0.95, 1.05), 2),
            },
        }

    return {
        "data": {
            "oc": oc,
            "futurePrice": round(spot + random.uniform(-10, 30), 2),
            "expiryList": _generate_expiries(symbol),
        }
    }


def generate_demo_quote(symbol: str) -> Dict:
    """Generate a realistic spot quote."""
    spot = _tick_spot(symbol)
    base = {"NIFTY": 22500, "BANKNIFTY": 48000, "FINNIFTY": 21500, "MIDCPNIFTY": 10500}[symbol]
    change = round(spot - base, 2)
    return {
        "last_price": spot,
        "net_change": change,
        "percentage_change": round(change / base * 100, 2),
        "open": round(base * random.uniform(0.995, 1.005), 2),
        "high": round(max(spot, base) * random.uniform(1.001, 1.01), 2),
        "low": round(min(spot, base) * random.uniform(0.99, 0.999), 2),
        "close": round(base * 0.998, 2),
        "volume": random.randint(10_000_000, 50_000_000),
    }


def is_demo_mode() -> bool:
    """
    Return True ONLY if Dhan credentials are not configured.
    In production, this must always return False.
    Demo mode generates synthetic data — never use in live trading.
    """
    from config import get_settings
    s = get_settings()
    return not s.DHAN_CLIENT_ID or s.DHAN_CLIENT_ID in ("your_client_id_here", "demo", "")
