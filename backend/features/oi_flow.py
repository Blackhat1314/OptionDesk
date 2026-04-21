"""
OI Flow Intelligence
======================
Classifies OI changes per strike into:
  Long Build-up    | Price ↑ & OI ↑
  Short Build-up   | Price ↓ & OI ↑
  Short Covering   | Price ↑ & OI ↓
  Long Unwinding   | Price ↓ & OI ↓

Also tracks cumulative OI changes over time (flow heatmap).
"""

import time
import numpy as np
from typing import Dict, List, Optional, Tuple
from collections import defaultdict, deque


# ─── OI Flow Classification ───────────────────────────────────────────────────

OI_FLOW_TYPES = {
    "LONG_BUILDUP":   {"price": "+", "oi": "+", "color": "#00c853", "desc": "Bullish — new longs being added"},
    "SHORT_BUILDUP":  {"price": "-", "oi": "+", "color": "#ff1744", "desc": "Bearish — new shorts being added"},
    "SHORT_COVERING": {"price": "+", "oi": "-", "color": "#00e5ff", "desc": "Bullish unwinding — shorts exiting"},
    "LONG_UNWINDING": {"price": "-", "oi": "-", "color": "#ff9100", "desc": "Bearish unwinding — longs exiting"},
    "NEUTRAL":        {"price": "=", "oi": "=", "color": "#607d8b", "desc": "No significant change"},
}

def classify_oi_flow(
    price_change: float,
    oi_change: float,
    price_threshold: float = 0.001,
    oi_threshold: float = 0.01,
) -> str:
    """
    Classify OI flow based on price and OI direction.
    thresholds: min % change to be considered "significant"
    """
    price_up = price_change >  price_threshold
    price_dn = price_change < -price_threshold
    oi_up    = oi_change    >  oi_threshold
    oi_dn    = oi_change    < -oi_threshold

    if price_up and oi_up:   return "LONG_BUILDUP"
    if price_dn and oi_up:   return "SHORT_BUILDUP"
    if price_up and oi_dn:   return "SHORT_COVERING"
    if price_dn and oi_dn:   return "LONG_UNWINDING"
    return "NEUTRAL"


# ─── Per-strike OI tracker ────────────────────────────────────────────────────

class StrikeOIRecord:
    """Tracks price and OI history for one strike+type."""
    __slots__ = ("strike", "option_type", "_prices", "_ois", "_times")

    def __init__(self, strike: float, option_type: str, maxlen: int = 60):
        self.strike      = strike
        self.option_type = option_type
        self._prices: deque = deque(maxlen=maxlen)
        self._ois:    deque = deque(maxlen=maxlen)
        self._times:  deque = deque(maxlen=maxlen)

    def push(self, price: float, oi: int, ts: Optional[float] = None):
        self._prices.append(price)
        self._ois.append(oi)
        self._times.append(ts or time.time())

    def flow_classification(self) -> str:
        if len(self._prices) < 2:
            return "NEUTRAL"
        price_change = (self._prices[-1] - self._prices[-2]) / (self._prices[-2] + 1e-6)
        oi_change    = (self._ois[-1]    - self._ois[-2])    / (self._ois[-2]    + 1e-6)
        return classify_oi_flow(price_change, oi_change)

    def cumulative_oi_change(self) -> int:
        if len(self._ois) < 2:
            return 0
        return int(self._ois[-1] - self._ois[0])

    def latest_oi(self) -> int:
        return int(self._ois[-1]) if self._ois else 0

    def latest_price(self) -> float:
        return float(self._prices[-1]) if self._prices else 0.0


# ─── Symbol-level OI Flow store ──────────────────────────────────────────────

class OIFlowStore:
    def __init__(self, symbol: str):
        self.symbol = symbol
        # key: (strike, option_type)
        self._records: Dict[Tuple[float, str], StrikeOIRecord] = {}
        # Cumulative daily OI flow per strike (for heatmap)
        self._cumulative_flow: Dict[float, Dict] = {}
        self._history: deque = deque(maxlen=100)  # snapshots for time-series

    def update(self, strike: float, option_type: str, price: float, oi: int):
        key = (strike, option_type)
        if key not in self._records:
            self._records[key] = StrikeOIRecord(strike, option_type)
        self._records[key].push(price, oi)

    def snapshot_from_chain(self, chain_rows: List[Dict], spot: float):
        """Ingest a full option chain update."""
        ts = time.time()
        for row in chain_rows:
            strike = row.get("strike", 0.0)
            call   = row.get("call", {})
            put    = row.get("put",  {})

            # Use OI > 0 as the condition (not LTP — LTP is 0 when market is closed)
            if call.get("oi", 0) > 0:
                self.update(strike, "CE", call.get("ltp", 0) or call.get("bid", 0), call.get("oi", 0))
            if put.get("oi", 0) > 0:
                self.update(strike, "PE", put.get("ltp", 0) or put.get("bid", 0), put.get("oi", 0))

        # Save heatmap snapshot
        self._history.append({
            "ts":   round(ts, 0),
            "spot": round(spot, 2),
            "flows": self._build_flow_summary(),
        })

    def _build_flow_summary(self) -> List[Dict]:
        result = []
        seen_strikes = set()
        for (strike, otype), rec in sorted(self._records.items()):
            flow = rec.flow_classification()
            cum  = rec.cumulative_oi_change()
            result.append({
                "strike":      strike,
                "option_type": otype,
                "flow":        flow,
                "color":       OI_FLOW_TYPES[flow]["color"],
                "oi":          rec.latest_oi(),
                "oi_change":   cum,
                "price":       rec.latest_price(),
            })
            seen_strikes.add(strike)
        return result

    def get_dominant_strikes(self, top_n: int = 10) -> List[Dict]:
        """Top N strikes by absolute cumulative OI change."""
        summary = self._build_flow_summary()
        return sorted(summary, key=lambda x: abs(x["oi_change"]), reverse=True)[:top_n]

    def get_heatmap_data(self) -> List[Dict]:
        """Structured heatmap: strikes × time → OI change intensity."""
        all_strikes = sorted(set(s for (s, _) in self._records.keys()))
        if not all_strikes or not self._history:
            return []

        heatmap = []
        for snap in list(self._history)[-20:]:  # last 20 snapshots
            row = {"ts": snap["ts"], "spot": snap["spot"]}
            flows_by_strike = {
                f["strike"]: f for f in snap.get("flows", []) if f["option_type"] == "CE"
            }
            for strike in all_strikes:
                f = flows_by_strike.get(strike, {})
                row[str(int(strike))] = {
                    "oi_change": f.get("oi_change", 0),
                    "flow":      f.get("flow", "NEUTRAL"),
                    "color":     f.get("color", "#607d8b"),
                }
            heatmap.append(row)
        return heatmap

    def get_flow_response(self) -> Dict:
        flows    = self._build_flow_summary()
        dominant = self.get_dominant_strikes()

        # Aggregate by flow type
        flow_counts: Dict[str, int] = {k: 0 for k in OI_FLOW_TYPES}
        for f in flows:
            flow_counts[f["flow"]] = flow_counts.get(f["flow"], 0) + 1

        return {
            "symbol":           self.symbol,
            "flows":            flows,
            "dominant_strikes": dominant,
            "flow_counts":      flow_counts,
            "heatmap":          self.get_heatmap_data(),
            "timestamp":        time.time(),
        }


# ─── Singletons ───────────────────────────────────────────────────────────────

_oi_stores: Dict[str, OIFlowStore] = {}

def get_oi_store(symbol: str) -> OIFlowStore:
    if symbol not in _oi_stores:
        _oi_stores[symbol] = OIFlowStore(symbol)
    return _oi_stores[symbol]


def ingest_chain_for_oi(symbol: str, chain_rows: List[Dict], spot: float):
    get_oi_store(symbol).snapshot_from_chain(chain_rows, spot)


def get_oi_flow(symbol: str) -> Dict:
    return get_oi_store(symbol).get_flow_response()
