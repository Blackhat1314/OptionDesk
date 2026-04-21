"""
Analytics Processor
====================
Transforms raw Dhan API option chain responses into fully computed OptionChainResponse.

DHAN OPTION CHAIN RESPONSE FORMAT (per v2 docs):
  data.last_price          → index spot price
  data.expiry_list         → list of expiry strings (also: data.expiryList)
  data.oc.{strike}.CE/PE  → option leg data for each strike
    └── security_id        → string ID for WS subscription
    └── trading_symbol     → e.g. "NIFTY24DEC22000CE"
    └── last_price         → LTP (float)
    └── bid_price          → best bid
    └── ask_price          → best ask
    └── volume             → day volume
    └── oi                 → current open interest
    └── prev_oi            → previous day OI (use for OI change)
    └── implied_volatility → IV in PERCENT (e.g. 15.5 means 15.5%)
    └── delta              → pre-computed by Dhan
    └── theta              → pre-computed (per day, typically negative)
    └── gamma              → pre-computed
    └── vega               → pre-computed (per 1% IV change)

ZEROS ROOT CAUSE:
  1. LTP=0 when market is closed / instrument not traded → IV=0 → Greeks=0
  2. implied_volatility field might be missing or 0 → fallback to BS computation
  3. prev_oi missing → oi_change=0

FIXES:
  - Use Dhan's pre-computed Greeks when available (delta, gamma, theta, vega)
  - Fall back to BS-computed Greeks with estimated IV when Dhan Greeks are 0
  - Compute IV from BS when ltp > 0 and Dhan IV is missing/zero
  - Use mid-price (bid+ask)/2 as LTP fallback when last_price=0
  - Estimate IV from ATM vol for deep ITM/OTM where BS may not converge
  - Log diagnostic info when all values are zero
"""

import math
import time
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pytz

from calculations.black_scholes import (
    compute_all_greeks,
    implied_volatility,
    compute_pcr,
    compute_pcr_volume,
    compute_max_pain,
    compute_vwap,
    compute_gamma_exposure,
    compute_delta_exposure,
    find_gamma_flip,
    days_to_expiry,
)
from models.schemas import (
    OptionChainRow, OptionChainResponse,
    OptionLeg, Greeks,
    GreeksExposureResponse, ExposureByStrike,
    IVAnalyticsResponse, IVSmilePoint,
    MarketSummary,
)
from api.dhan_client import INDEX_LOT_SIZES
from features.regime import get_price_buffer
from config import get_settings
from core.strike_selector import select_strikes

settings = get_settings()
RISK_FREE_RATE = settings.RISK_FREE_RATE

# Min OI filter for exposure calculations
_MIN_OI = 500

# IV outlier bounds (per spec: cap at 300%, reject below 1%)
_IV_MIN_PCT = 1.0
_IV_MAX_PCT = 300.0

# Bid-ask spread threshold: if (ask - bid) / spot > this, strike is illiquid
_BID_ASK_SPREAD_THRESHOLD = 0.05

# Market-open EMA smoothing: first 5 minutes (9:15–9:20 IST) are noisy
_MARKET_OPEN_BUFFER_MINS = 5
_EMA_ALPHA = 0.3   # EMA smoothing factor for IV during open buffer

# Per-symbol EMA state for IV smoothing during market open
_iv_ema: Dict[str, float] = {}

# In-memory IV history (also persisted to Redis on each refresh)
_iv_history: Dict[str, deque] = {}


def _is_market_open_buffer() -> bool:
    """Returns True during the first 5 minutes of market open (9:15–9:20 IST)."""
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    mins_since_midnight = now.hour * 60 + now.minute
    market_open_start = 9 * 60 + 15   # 9:15
    market_open_end   = 9 * 60 + 20   # 9:20
    return market_open_start <= mins_since_midnight < market_open_end


def _apply_iv_ema(symbol: str, strike: float, option_type: str, iv_pct: float) -> float:
    """
    Apply EMA smoothing to IV during market open buffer.
    Key: symbol:strike:type  →  smoothed IV value.
    """
    key = f"{symbol}:{strike}:{option_type}"
    prev = _iv_ema.get(key, iv_pct)
    smoothed = _EMA_ALPHA * iv_pct + (1 - _EMA_ALPHA) * prev
    _iv_ema[key] = smoothed
    return smoothed


# ─── Safe conversion helpers ──────────────────────────────────────────────────

def _f(val, default: float = 0.0) -> float:
    """Safe float conversion."""
    try:
        v = float(val)
        return v if v == v else default   # NaN guard
    except (TypeError, ValueError):
        return default

def _i(val, default: int = 0) -> int:
    """Safe int conversion."""
    try:
        return int(float(val)) if val is not None else default
    except (TypeError, ValueError):
        return default


# ─── OC data extraction (handles both Dhan field name variants) ──────────────

def _extract_oc(raw_data: Dict) -> Tuple[Dict, float, List[str]]:
    """
    Extract option chain dict, spot price, and expiry list from raw Dhan v2 response.

    Dhan v2 response shape:
      {"status": "success", "data": {"last_price": 25642.8, "oc": {"25650.000000": {"ce": {...}, "pe": {...}}}}}
    """
    data = raw_data.get("data", raw_data)

    spot = _f(data.get("last_price")) or _f(data.get("lastPrice")) or 0.0

    oc = data.get("oc") or {}

    # Dhan v2 option chain response does NOT include expiry_list
    # (that comes from the separate /optionchain/expirylist endpoint)
    expiries = data.get("expiry_list") or data.get("expiryList") or []

    if not oc:
        pass  # empty oc handled by caller

    return oc, spot, expiries


def _extract_leg_data(strike_entry: Dict, side: str) -> Dict:
    """
    Extract CE or PE leg dict from a strike entry.
    Dhan v2 uses lowercase keys: 'ce' and 'pe'.
    """
    # Dhan v2 response uses lowercase 'ce'/'pe'
    return (
        strike_entry.get(side.lower())
        or strike_entry.get(side.upper())
        or {}
    )


# ─── Main option chain processor ─────────────────────────────────────────────

def process_option_chain(
    raw_data: Dict,
    symbol:   str,
    expiry:   str,
    spot_price: float,
) -> OptionChainResponse:
    """
    Normalise raw Dhan option chain response.
    - Uses Dhan's pre-computed Greeks when available
    - Falls back to Black-Scholes when Dhan values are 0
    - Mid-price fallback for LTP=0
    """
    lot_size = INDEX_LOT_SIZES.get(symbol, 50)
    T        = days_to_expiry(expiry)

    oc_data, api_spot, expiries = _extract_oc(raw_data)

    # Use API spot if caller-provided spot is missing
    if spot_price <= 0:
        spot_price = api_spot

    all_strikes = sorted([float(k) for k in oc_data.keys()]) if oc_data else []

    if not all_strikes:
        return OptionChainResponse(
            symbol=symbol, expiry=expiry, spot_price=spot_price,
            atm_strike=spot_price, rows=[], expiries=expiries,
        )

    atm_strike = _find_atm(all_strikes, spot_price)

    # Compute ATM IV for Greeks fallback (if many LTPs are 0 e.g. after close)
    atm_iv_fallback = _estimate_atm_iv(oc_data, atm_strike, all_strikes)

    rows: List[OptionChainRow] = []
    zero_ltp_count = 0

    for strike in all_strikes:
        # Dhan v2 uses float-string keys: "25650.000000"
        # Try multiple key formats to be safe
        strike_key = f"{strike:.6f}"
        strike_entry = (
            oc_data.get(strike_key)
            or oc_data.get(str(int(strike)))
            or oc_data.get(str(strike))
            or {}
        )

        ce_data = _extract_leg_data(strike_entry, "CE")
        pe_data = _extract_leg_data(strike_entry, "PE")

        call_leg = _build_option_leg(
            ce_data, strike, "CE", expiry, spot_price, T, atm_iv_fallback
        )
        put_leg = _build_option_leg(
            pe_data, strike, "PE", expiry, spot_price, T, atm_iv_fallback
        )

        if call_leg.ltp == 0 and put_leg.ltp == 0:
            zero_ltp_count += 1

        rows.append(OptionChainRow(
            strike=strike,
            is_atm=(strike == atm_strike),
            call=call_leg,
            put=put_leg,
            pcr_oi=round(compute_pcr(call_leg.oi, put_leg.oi), 4),
            pcr_volume=round(compute_pcr_volume(call_leg.volume, put_leg.volume), 4),
        ))

    if zero_ltp_count > len(rows) * 0.8:
        pass  # market closed — Greeks computed from BS fallback

    futures_price = _f(raw_data.get("data", {}).get("futurePrice") or raw_data.get("futurePrice", 0))

    # ── Apply strike selection: range filter + exact count ────────────────────
    # Per-index default counts — must be >= frontend max strikeRange*2+1 (15*2+1=31)
    # Set to 40 for all indices to give the frontend enough rows to slice from
    DEFAULT_COUNTS = {
        "NIFTY":      40,
        "BANKNIFTY":  40,
        "FINNIFTY":   40,
        "MIDCPNIFTY": 40,
        "SENSEX":     40,
    }
    target_count = DEFAULT_COUNTS.get(symbol, 20)

    if rows and spot_price > 0:
        # Build strike list directly from rows (avoids .dict() overhead)
        all_strikes = [r.strike for r in rows]
        result      = select_strikes(
            symbol      = symbol,
            spot        = spot_price,
            all_strikes = all_strikes,
            count       = target_count,
            mode        = "fixed",
        )
        # Use round() to avoid float precision mismatches in set lookup
        selected_set = {round(s, 2) for s in result["strikes"]}
        rows = [r for r in rows if round(r.strike, 2) in selected_set]

    return OptionChainResponse(
        symbol=symbol, expiry=expiry,
        spot_price=spot_price, atm_strike=atm_strike,
        futures_price=futures_price, timestamp=time.time(),
        rows=rows, expiries=expiries,
    )


def _estimate_atm_iv(oc_data: Dict, atm_strike: float, all_strikes: List[float]) -> float:
    """
    Estimate ATM IV from nearby strikes to use as fallback when LTP=0.
    Returns decimal (0.15 = 15%).
    Dhan v2 uses lowercase 'ce'/'pe' keys.
    """
    candidates = sorted(all_strikes, key=lambda s: abs(s - atm_strike))[:6]
    ivs = []
    for s in candidates:
        sk = str(int(s)) if s == int(s) else str(s)
        # Dhan v2 uses float-string keys like "25650.000000"
        entry = oc_data.get(sk) or oc_data.get(f"{s:.6f}") or {}
        for side in ("ce", "pe"):
            leg = entry.get(side, {})
            iv_pct = _f(leg.get("implied_volatility", 0))
            if iv_pct > 0.5:
                ivs.append(iv_pct / 100.0)
    if ivs:
        return sum(ivs) / len(ivs)
    return 0.15  # 15% default — reasonable for NIFTY


def _build_option_leg(
    leg_data: Dict,
    strike:      float,
    option_type: str,
    expiry:      str,
    spot_price:  float,
    T:           float,
    atm_iv_fallback: float = 0.15,
) -> OptionLeg:
    """
    Build a single OptionLeg from Dhan v2 option chain response.

    Dhan v2 field mapping (per official docs):
      last_price          → ltp
      top_bid_price       → bid  (NOT bid_price)
      top_ask_price       → ask  (NOT ask_price)
      top_bid_quantity    → bid_qty
      top_ask_quantity    → ask_qty
      oi                  → oi
      previous_oi         → prev_oi  (NOT prev_oi or oi_prev)
      volume              → volume
      average_price       → vwap
      implied_volatility  → iv (already in percent, e.g. 9.79)
      greeks.delta        → delta  (nested dict, NOT flat)
      greeks.gamma        → gamma
      greeks.theta        → theta
      greeks.vega         → vega
      security_id         → security_id (int in response)
      previous_close_price → close
    """
    if not leg_data:
        return OptionLeg(strike=strike, option_type=option_type, expiry=expiry)

    # ── Price data ────────────────────────────────────────────────────────────
    last_price = _f(leg_data.get("last_price"))
    bid_price  = _f(leg_data.get("top_bid_price"))
    ask_price  = _f(leg_data.get("top_ask_price"))
    mid_price  = (bid_price + ask_price) / 2.0 if bid_price > 0 and ask_price > 0 else 0.0

    oi        = _i(leg_data.get("oi"))
    prev_oi   = _i(leg_data.get("previous_oi"))
    oi_change = oi - prev_oi if prev_oi > 0 else 0
    volume    = _i(leg_data.get("volume"))

    # ── Liquidity filters ─────────────────────────────────────────────────────
    # 1. Stale data: volume == 0 means no trades today — use mid-price only
    stale = (volume == 0)

    # 2. Bid-ask spread check: wide spread = illiquid, fall back to mid-price
    spread_ratio = (ask_price - bid_price) / spot_price if spot_price > 0 and ask_price > bid_price else 0.0
    illiquid = spread_ratio > _BID_ASK_SPREAD_THRESHOLD

    # Use LTP if liquid and fresh; otherwise fall back to mid-price
    if last_price > 0 and not illiquid and not stale:
        ltp = last_price
    elif mid_price > 0:
        ltp = mid_price
    else:
        ltp = last_price  # last resort

    # ── Implied Volatility ────────────────────────────────────────────────────
    # Dhan returns IV as percent (e.g. 9.789 means 9.789%)
    dhan_iv_pct = _f(leg_data.get("implied_volatility"))

    # Outlier rejection: IV < 1% or IV > 300% is a math error from bad ticks
    if dhan_iv_pct >= _IV_MIN_PCT and dhan_iv_pct <= _IV_MAX_PCT:
        iv_decimal = dhan_iv_pct / 100.0
    elif ltp > 0 and spot_price > 0 and strike > 0 and T > 0 and not illiquid:
        # Compute IV from market price — only if strike is liquid
        iv_decimal = implied_volatility(ltp, spot_price, strike, RISK_FREE_RATE, T, option_type)
        if iv_decimal <= 0 or iv_decimal > 3.0:
            iv_decimal = atm_iv_fallback
    else:
        iv_decimal = atm_iv_fallback

    # Market-open buffer: apply EMA smoothing to dampen opening noise
    if _is_market_open_buffer() and iv_decimal > 0:
        smoothed_pct = _apply_iv_ema(
            symbol if hasattr(leg_data, '_symbol') else "UNK",
            strike, option_type, iv_decimal * 100
        )
        iv_decimal = smoothed_pct / 100.0

    # ── Greeks — nested dict in Dhan v2 ──────────────────────────────────────
    greeks_dict = leg_data.get("greeks") or {}
    dhan_delta  = _f(greeks_dict.get("delta"))
    dhan_gamma  = _f(greeks_dict.get("gamma"))
    dhan_theta  = _f(greeks_dict.get("theta"))
    dhan_vega   = _f(greeks_dict.get("vega"))

    if abs(dhan_delta) > 0.0001 or abs(dhan_gamma) > 1e-8:
        greek_delta = dhan_delta
        greek_gamma = dhan_gamma
        greek_theta = dhan_theta
        greek_vega  = dhan_vega
        greek_rho   = 0.0
    else:
        sigma = iv_decimal if iv_decimal > 0.001 else atm_iv_fallback
        if spot_price > 0 and strike > 0 and T > 0:
            g = compute_all_greeks(spot_price, strike, RISK_FREE_RATE, sigma, T, option_type)
            greek_delta = g.delta
            greek_gamma = g.gamma
            greek_theta = g.theta
            greek_vega  = g.vega
            greek_rho   = g.rho
        else:
            greek_delta = greek_gamma = greek_theta = greek_vega = greek_rho = 0.0

    oi_change_pct = round(oi_change / prev_oi * 100, 2) if prev_oi > 0 else 0.0

    return OptionLeg(
        security_id    = str(leg_data.get("security_id", "")),
        trading_symbol = str(leg_data.get("trading_symbol", "")),
        strike=strike, option_type=option_type, expiry=expiry,
        ltp   = round(ltp, 2),
        open  = _f(leg_data.get("open")),
        high  = _f(leg_data.get("high")),
        low   = _f(leg_data.get("low")),
        close = _f(leg_data.get("previous_close_price")),
        volume=volume, oi=oi,
        oi_change=oi_change, oi_change_pct=oi_change_pct,
        bid    = round(bid_price, 2),
        ask    = round(ask_price, 2),
        bid_qty= _i(leg_data.get("top_bid_quantity")),
        ask_qty= _i(leg_data.get("top_ask_quantity")),
        iv=round(iv_decimal * 100, 2),   # store as percent
        greeks=Greeks(
            delta=round(greek_delta, 4),
            gamma=round(greek_gamma, 6),
            theta=round(greek_theta, 4),
            vega =round(greek_vega,  4),
            rho  =round(greek_rho,   4),
        ),
        bid_ask_spread=round(ask_price - bid_price, 2),
        vwap=_f(leg_data.get("average_price")),
    )


def compute_greeks_exposure(chain: OptionChainResponse, symbol: str) -> GreeksExposureResponse:
    """
    Compute GEX, DEX, Vega, Theta exposure per strike.

    Formulas:
      GEX  = gamma * OI * lot_size * spot   (calls +, puts -)
      DEX  = delta * OI * lot_size * spot   (calls +, puts -)
      VEGA = vega  * OI * lot_size          (per 1% IV move)
      THETA= theta * OI * lot_size          (per day)

    Normalization:
      GEX  → Crores  (/1e7)
      DEX  → Crores  (/1e7)
      VEGA → Lakhs   (/1e5)
      THETA→ Lakhs   (/1e5)

    Filters:
      - OI < 500 → skip
      - IV > 80% or IV < 1% → skip
      - |strike - spot| > 1500 → skip (absolute points)
    """
    lot_size = INDEX_LOT_SIZES.get(symbol, 50)
    S = chain.spot_price
    T = days_to_expiry(chain.expiry)

    if S <= 0:
        return GreeksExposureResponse(symbol=symbol, expiry=chain.expiry, spot_price=S)

    exposures:     List[ExposureByStrike] = []
    gex_by_strike: Dict[float, float] = {}
    call_oi_map:   Dict[float, int]   = {}
    put_oi_map:    Dict[float, int]   = {}
    total_gex = total_dex = total_vega = total_theta = 0.0

    MIN_OI   = 500
    MAX_DIST = min(S * 0.10, 2000)   # ±10% of spot, capped at 2000 pts

    for row in chain.rows:
        K = row.strike

        if abs(K - S) > MAX_DIST:
            continue

        # ── Call leg ──────────────────────────────────────────────────────────
        iv_c    = row.call.iv / 100.0
        call_oi = row.call.oi
        call_gex = call_dex = call_vega_raw = call_theta_raw = 0.0

        if call_oi >= MIN_OI and _IV_MIN_PCT / 100 <= iv_c <= _IV_MAX_PCT / 100 and T > 0:
            call_gex       = compute_gamma_exposure(S, K, RISK_FREE_RATE, iv_c, T, call_oi, "CE", lot_size)
            call_dex       = compute_delta_exposure(S, K, RISK_FREE_RATE, iv_c, T, call_oi, "CE", lot_size)
            call_vega_raw  = row.call.greeks.vega  * call_oi * lot_size
            call_theta_raw = row.call.greeks.theta * call_oi * lot_size

        # ── Put leg ───────────────────────────────────────────────────────────
        iv_p   = row.put.iv / 100.0
        put_oi = row.put.oi
        put_gex = put_dex = put_vega_raw = put_theta_raw = 0.0

        if put_oi >= MIN_OI and _IV_MIN_PCT / 100 <= iv_p <= _IV_MAX_PCT / 100 and T > 0:
            put_gex        = compute_gamma_exposure(S, K, RISK_FREE_RATE, iv_p, T, put_oi, "PE", lot_size)
            put_dex        = compute_delta_exposure(S, K, RISK_FREE_RATE, iv_p, T, put_oi, "PE", lot_size)
            put_vega_raw   = row.put.greeks.vega  * put_oi * lot_size
            put_theta_raw  = row.put.greeks.theta * put_oi * lot_size

        # GEX: call_gex is +, put_gex is - (sign applied in compute_gamma_exposure)
        net_gex   = call_gex + put_gex
        # DEX: net delta exposure (calls positive, puts negative)
        net_dex   = call_dex + put_dex
        net_vega  = call_vega_raw  + put_vega_raw
        net_theta = call_theta_raw + put_theta_raw

        gex_by_strike[K] = net_gex
        total_gex   += net_gex
        total_dex   += net_dex
        total_vega  += net_vega
        total_theta += net_theta

        call_oi_map[K] = call_oi
        put_oi_map[K]  = put_oi

        # Per-strike values normalized
        # GEX raw = gamma * OI * lot * S² * 0.01  → divide by 1e9 for Crores
        # DEX raw = delta * OI * lot * S           → divide by 1e9 for Crores
        # VEGA raw = vega * OI * lot               → divide by 1e5 for Lakhs
        # THETA raw = theta * OI * lot             → divide by 1e5 for Lakhs
        exposures.append(ExposureByStrike(
            strike     = K,
            call_delta = round(row.call.greeks.delta * call_oi * lot_size * S / 1e9, 4),
            put_delta  = round(row.put.greeks.delta  * put_oi  * lot_size * S / 1e9, 4),
            net_delta  = round((row.call.greeks.delta * call_oi + row.put.greeks.delta * put_oi) * lot_size * S / 1e9, 4),
            call_gamma = round(call_gex / 1e9, 6),
            put_gamma  = round(put_gex  / 1e9, 6),
            net_gamma  = round(net_gex  / 1e9, 6),
            gex        = round(net_gex  / 1e9, 6),
            dex        = round(net_dex  / 1e9, 4),
            call_vega  = round(call_vega_raw  / 1e7, 4),
            put_vega   = round(put_vega_raw   / 1e7, 4),
            net_vega   = round(net_vega       / 1e7, 4),
            call_theta = round(call_theta_raw / 1e7, 4),
            put_theta  = round(put_theta_raw  / 1e7, 4),
            net_theta  = round(net_theta      / 1e7, 4),
        ))

    gamma_flip = find_gamma_flip(gex_by_strike)
    sorted_k   = sorted(call_oi_map.keys())
    call_wall  = max(sorted_k, key=lambda k: call_oi_map[k], default=0.0) if sorted_k else 0.0
    put_wall   = max(sorted_k, key=lambda k: put_oi_map[k],  default=0.0) if sorted_k else 0.0

    # GEX raw = gamma * OI * lot * S² * 0.01  → /1e9 for Crores
    # DEX raw = delta * OI * lot * S           → /1e9 for Crores
    # VEGA raw = vega_per_share * OI * lot     → /1e7 for Crores
    # THETA raw = theta_per_share * OI * lot   → /1e7 for Crores
    total_gex_cr   = round(total_gex   / 1e9, 4)
    total_dex_cr   = round(total_dex   / 1e9, 4)
    total_vega_cr  = round(total_vega  / 1e7, 4)
    total_theta_cr = round(total_theta / 1e7, 4)

    return GreeksExposureResponse(
        symbol=symbol, expiry=chain.expiry, spot_price=S,
        timestamp=time.time(), exposures=exposures,
        total_gex   = total_gex_cr,
        total_dex   = total_dex_cr,
        total_vega  = total_vega_cr,
        total_theta = total_theta_cr,
        gamma_flip_level = round(gamma_flip, 2),
        call_wall=call_wall, put_wall=put_wall,
    )


# ─── IV Analytics ─────────────────────────────────────────────────────────────

def compute_iv_analytics(chain: OptionChainResponse, symbol: str) -> IVAnalyticsResponse:
    """
    Build IV smile, compute IV Rank/Percentile from rolling history, and HV.

    IV smile filtering:
      - Only include strikes within 1500 pts of spot
      - Only include IV between 1% and 80%
      - Smooth smile with 3-point moving average to remove spikes
    """
    spot = chain.spot_price
    step = _get_strike_step(chain.rows)
    smile_raw: List[IVSmilePoint] = []
    iv_values: List[float] = []

    for row in chain.rows:
        # Distance filter for smile — keep ±30 strikes from ATM
        if abs(row.strike - chain.atm_strike) > 30 * step:
            continue

        call_iv = row.call.iv
        put_iv  = row.put.iv

        # IV validity filter — reject outliers per spec (< 1% or > 300%)
        call_valid = _IV_MIN_PCT <= call_iv <= _IV_MAX_PCT and row.call.oi >= _MIN_OI
        put_valid  = _IV_MIN_PCT <= put_iv  <= _IV_MAX_PCT and row.put.oi  >= _MIN_OI

        if not call_valid and not put_valid:
            continue

        moneyness = row.strike / spot if spot > 0 else 1.0
        smile_raw.append(IVSmilePoint(
            strike    = row.strike,
            call_iv   = round(call_iv, 2) if call_valid else 0.0,
            put_iv    = round(put_iv,  2) if put_valid  else 0.0,
            moneyness = round(moneyness, 4),
        ))

        # Collect near-ATM IVs (±3 strikes) for ATM IV
        if abs(row.strike - chain.atm_strike) <= 3 * step:
            if call_valid: iv_values.append(call_iv)
            if put_valid:  iv_values.append(put_iv)

    # 3-point moving average to smooth smile spikes
    smile = _smooth_smile(smile_raw)

    atm_iv  = sum(iv_values) / len(iv_values) if iv_values else 0.0
    valid_ivs = [p.call_iv for p in smile if p.call_iv > 0] + [p.put_iv for p in smile if p.put_iv > 0]
    avg_iv  = sum(valid_ivs) / len(valid_ivs) if valid_ivs else 0.0

    # ── IV Rank & Percentile — rolling in-memory history ─────────────────────
    if symbol not in _iv_history:
        _iv_history[symbol] = deque(maxlen=252)
    if atm_iv > 0:
        _iv_history[symbol].append(atm_iv)

    history = list(_iv_history[symbol])
    # Need at least 5 data points; require meaningful spread (>0.5%) for rank
    if len(history) >= 5:
        iv_min = min(history)
        iv_max = max(history)
        spread = iv_max - iv_min
        if spread >= 0.5:   # at least 0.5% IV range for meaningful rank
            iv_rank       = round((atm_iv - iv_min) / spread * 100, 2)
            iv_percentile = round(sum(1 for v in history if v < atm_iv) / len(history) * 100, 2)
        else:
            # All values nearly identical — rank is meaningless, return 50
            iv_rank = 50.0
            iv_percentile = 50.0
    elif len(history) >= 2:
        iv_rank = 50.0
        iv_percentile = 50.0
    else:
        iv_rank = iv_percentile = 0.0

    # ── Historical Volatility from price buffer ───────────────────────────────
    # Price buffer is fed by spot price on each chain refresh (~5s intervals).
    # Each "tick" represents ~5 seconds of real time.
    # Annualization: we need to scale std(log_returns) to annual.
    # With ~5s ticks: ticks_per_year = 252 trading days × 6.25h × 3600/5 = 1,134,000
    # But this gives unrealistically high HV for intraday noise.
    # Better approach: use sqrt(252) and treat the buffer as "daily-equivalent" samples
    # since each tick captures the same market information as a daily close.
    # This gives HV comparable to IV (both annualized on 252-day basis).
    price_buf = get_price_buffer(symbol)
    prices = list(price_buf._prices)
    historical_vol_30d = 0.0
    if len(prices) >= 5:
        log_returns = [
            math.log(prices[i] / prices[i - 1])
            for i in range(1, len(prices))
            if prices[i - 1] > 0 and prices[i] > 0
        ]
        window = min(30, len(log_returns))
        recent = log_returns[-window:]
        if len(recent) >= 3:
            mean_r   = sum(recent) / len(recent)
            variance = sum((r - mean_r) ** 2 for r in recent) / max(len(recent) - 1, 1)
            # Use sqrt(252) — treat each refresh tick as a daily observation
            # This keeps HV on the same scale as IV for meaningful comparison
            historical_vol_30d = round(math.sqrt(variance * 252) * 100, 2)
    elif len(prices) >= 2:
        pct_range = abs(prices[-1] - prices[0]) / prices[0] * 100
        historical_vol_30d = round(pct_range * 2, 2)

    iv_rv_spread = round(atm_iv - historical_vol_30d, 2)

    return IVAnalyticsResponse(
        symbol=symbol, expiry=chain.expiry, spot_price=spot,
        timestamp=time.time(), smile=smile,
        current_iv        = round(atm_iv, 2),
        avg_iv            = round(avg_iv, 2),
        iv_rank           = iv_rank,
        iv_percentile     = iv_percentile,
        historical_vol_30d= historical_vol_30d,
        iv_rv_spread      = iv_rv_spread,
    )


def _smooth_smile(points: List[IVSmilePoint]) -> List[IVSmilePoint]:
    """3-point moving average to remove IV smile spikes."""
    if len(points) < 3:
        return points
    smoothed = []
    for i, p in enumerate(points):
        neighbors = points[max(0, i-1):i+2]
        call_vals = [n.call_iv for n in neighbors if n.call_iv > 0]
        put_vals  = [n.put_iv  for n in neighbors if n.put_iv  > 0]
        smoothed.append(IVSmilePoint(
            strike    = p.strike,
            call_iv   = round(sum(call_vals) / len(call_vals), 2) if call_vals else 0.0,
            put_iv    = round(sum(put_vals)  / len(put_vals),  2) if put_vals  else 0.0,
            moneyness = p.moneyness,
        ))
    return smoothed


def _get_strike_step(rows: List) -> float:
    """Infer strike step size from chain rows."""
    if len(rows) < 2:
        return 50.0
    steps = [abs(rows[i+1].strike - rows[i].strike) for i in range(min(5, len(rows)-1))]
    return min(steps) if steps else 50.0


# ─── Market Summary ───────────────────────────────────────────────────────────

def compute_market_summary(chain: OptionChainResponse, symbol: str) -> MarketSummary:
    strikes   = [row.strike for row in chain.rows]
    call_ois  = [row.call.oi for row in chain.rows]
    put_ois   = [row.put.oi  for row in chain.rows]

    total_call_oi  = sum(call_ois)
    total_put_oi   = sum(put_ois)
    total_call_vol = sum(row.call.volume for row in chain.rows)
    total_put_vol  = sum(row.put.volume  for row in chain.rows)

    max_pain = compute_max_pain(strikes, call_ois, put_ois)
    pcr_oi   = compute_pcr(total_call_oi, total_put_oi)
    pcr_vol  = compute_pcr_volume(total_call_vol, total_put_vol)

    atm_row = next((r for r in chain.rows if r.is_atm), None)
    atm_iv  = 0.0
    if atm_row:
        atm_iv = atm_row.call.iv if atm_row.call.iv > 0.5 else atm_row.put.iv

    return MarketSummary(
        symbol=symbol, spot_price=chain.spot_price,
        pcr_oi=round(pcr_oi, 4), pcr_volume=round(pcr_vol, 4),
        max_pain=max_pain, atm_iv=round(atm_iv, 2),
        total_call_oi=total_call_oi, total_put_oi=total_put_oi,
        total_call_vol=total_call_vol, total_put_vol=total_put_vol,
        timestamp=time.time(),
    )


def _find_atm(strikes: List[float], spot: float) -> float:
    if not strikes:
        return spot
    return min(strikes, key=lambda k: abs(k - spot))
