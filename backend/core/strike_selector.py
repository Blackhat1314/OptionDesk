"""
Strike Selection Utility
=========================
Centralised, index-aware strike selection with:
  - Exact count enforcement (never returns more than requested)
  - Per-index range filtering (removes deep OTM/ITM before selection)
  - Fixed mode: symmetric window around ATM
  - Smart mode: score-based selection (OI + volume + ATM proximity)
  - Cache: recompute only when spot moves > threshold
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

# ─── Per-index configuration ──────────────────────────────────────────────────

INDEX_CONFIG: Dict[str, Dict] = {
    "NIFTY":      {"range": 1000, "step": 50,  "lot": 50},
    "BANKNIFTY":  {"range": 2000, "step": 100, "lot": 15},
    "FINNIFTY":   {"range": 600,  "step": 50,  "lot": 40},
    "MIDCPNIFTY": {"range": 500,  "step": 25,  "lot": 75},
    "SENSEX":     {"range": 1000, "step": 100, "lot": 10},
}

# Spot movement threshold to trigger recompute (in points)
_RECOMPUTE_THRESHOLD: Dict[str, float] = {
    "NIFTY":      25.0,
    "BANKNIFTY":  50.0,
    "FINNIFTY":   25.0,
    "MIDCPNIFTY": 15.0,
    "SENSEX":     50.0,
}

# ─── Cache ────────────────────────────────────────────────────────────────────

_cache: Dict[str, Dict] = {}   # symbol → {spot, strikes, ts}


def _cache_valid(symbol: str, spot: float) -> bool:
    entry = _cache.get(symbol)
    if not entry:
        return False
    threshold = _RECOMPUTE_THRESHOLD.get(symbol, 25.0)
    return abs(entry["spot"] - spot) < threshold


def _cache_set(symbol: str, spot: float, strikes: List[float]):
    _cache[symbol] = {"spot": spot, "strikes": strikes, "ts": time.time()}


# ─── Core selection logic ─────────────────────────────────────────────────────

def _find_atm_index(strikes: List[float], spot: float) -> int:
    """Return index of the strike closest to spot."""
    return min(range(len(strikes)), key=lambda i: abs(strikes[i] - spot))


def _select_fixed(strikes: List[float], spot: float, count: int) -> List[float]:
    """
    Select exactly `count` strikes symmetrically around ATM.
    Adjusts window if ATM is near the boundary.
    """
    n = len(strikes)
    if n == 0:
        return []
    count = min(count, n)

    atm_idx = _find_atm_index(strikes, spot)
    half    = count // 2
    start   = atm_idx - half
    end     = start + count

    # Boundary adjustment
    if start < 0:
        start = 0
        end   = count
    if end > n:
        end   = n
        start = max(0, n - count)

    return strikes[start:end]


def _select_smart(
    strikes: List[float],
    spot: float,
    count: int,
    rows: Optional[List[Dict]] = None,
    w_oi: float = 0.4,
    w_vol: float = 0.3,
    w_prox: float = 0.3,
) -> List[float]:
    """
    Score-based selection.
    Score = w_oi * norm(OI) + w_vol * norm(volume) + w_prox * proximity_score
    Returns top `count` strikes sorted by strike price.
    Falls back to fixed mode if no row data available.
    """
    if not rows:
        return _select_fixed(strikes, spot, count)

    # Build lookup: strike → {oi, volume}
    row_map: Dict[float, Dict] = {}
    for row in rows:
        k = float(row.get("strike", 0))
        c = row.get("call", {})
        p = row.get("put",  {})
        row_map[k] = {
            "oi":     (c.get("oi", 0) or 0) + (p.get("oi", 0) or 0),
            "volume": (c.get("volume", 0) or 0) + (p.get("volume", 0) or 0),
        }

    # Compute raw scores
    oi_vals  = [row_map.get(k, {}).get("oi",     0) for k in strikes]
    vol_vals = [row_map.get(k, {}).get("volume", 0) for k in strikes]
    max_oi   = max(oi_vals)  or 1
    max_vol  = max(vol_vals) or 1
    max_dist = max(abs(k - spot) for k in strikes) or 1

    scored: List[Tuple[float, float]] = []
    for i, k in enumerate(strikes):
        norm_oi   = oi_vals[i]  / max_oi
        norm_vol  = vol_vals[i] / max_vol
        proximity = 1.0 - abs(k - spot) / max_dist   # 1 = ATM, 0 = furthest
        score     = w_oi * norm_oi + w_vol * norm_vol + w_prox * proximity
        scored.append((k, score))

    # Top N by score, then sort by strike for display
    top = sorted(scored, key=lambda x: x[1], reverse=True)[:count]
    return sorted(k for k, _ in top)


# ─── Public API ───────────────────────────────────────────────────────────────

def select_strikes(
    symbol:  str,
    spot:    float,
    all_strikes: List[float],
    count:   int = 20,
    mode:    str = "fixed",
    rows:    Optional[List[Dict]] = None,
) -> Dict:
    """
    Main entry point.

    Args:
        symbol:      Index name (NIFTY, BANKNIFTY, etc.)
        spot:        Current spot price
        all_strikes: All available strikes from the option chain
        count:       Exact number of strikes to return
        mode:        "fixed" | "smart"
        rows:        Option chain rows (needed for smart mode scoring)

    Returns:
        {
            "index":   symbol,
            "spot":    spot,
            "atm":     atm_strike,
            "strikes": [list of selected strikes],
            "count":   len(strikes),
            "mode":    mode,
        }
    """
    cfg   = INDEX_CONFIG.get(symbol, {"range": 1000, "step": 50, "lot": 50})
    rng   = cfg["range"]

    # Step 1: sort all strikes
    sorted_strikes = sorted(set(float(s) for s in all_strikes))

    # Step 2: range filter — remove deep OTM/ITM BEFORE selection
    filtered = [s for s in sorted_strikes if abs(s - spot) <= rng]

    # Fallback: if filter removes everything, use all strikes
    if not filtered:
        filtered = sorted_strikes

    # Step 3: select
    if mode == "smart":
        selected = _select_smart(filtered, spot, count, rows)
    else:
        selected = _select_fixed(filtered, spot, count)

    # Guarantee exact count (never exceed)
    selected = selected[:count]

    # ATM from selected set
    atm = min(selected, key=lambda k: abs(k - spot)) if selected else spot

    return {
        "index":   symbol,
        "spot":    round(spot, 2),
        "atm":     atm,
        "strikes": selected,
        "count":   len(selected),
        "mode":    mode,
    }


def filter_chain_rows(
    rows: List[Dict],
    symbol: str,
    spot: float,
    count: int = 20,
    mode: str = "fixed",
) -> List[Dict]:
    """
    Filter option chain rows to exactly `count` strikes using select_strikes.
    Preserves original row dicts — only filters which rows to include.
    """
    all_strikes = [float(r.get("strike", 0)) for r in rows if r.get("strike")]
    result      = select_strikes(symbol, spot, all_strikes, count, mode, rows)
    selected_set = set(result["strikes"])
    return [r for r in rows if float(r.get("strike", 0)) in selected_set]
