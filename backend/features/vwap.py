"""
VWAP System
============
Intraday VWAP, VWAP bands (±1σ, ±2σ), anchored VWAP, and price-bias signal.

VWAP = Σ(P × V) / ΣV   where P = (H+L+C)/3 (typical price)
Band = VWAP ± n × std(P - VWAP, rolling)
"""

import math
import time
import numpy as np
from typing import Dict, List, Optional, Tuple
from collections import deque
from datetime import datetime, date
import pytz


IST = pytz.timezone("Asia/Kolkata")


# ─── OHLCV Bar ────────────────────────────────────────────────────────────────

class OHLCVBar:
    __slots__ = ("ts", "open", "high", "low", "close", "volume", "typical_price")

    def __init__(self, ts: float, open_: float, high: float, low: float, close: float, volume: int):
        self.ts            = ts
        self.open          = open_
        self.high          = high
        self.low           = low
        self.close         = close
        self.volume        = volume
        self.typical_price = (high + low + close) / 3.0  # HLC/3


# ─── VWAP Engine ─────────────────────────────────────────────────────────────

class VWAPEngine:
    """
    Intraday VWAP with ±1σ/±2σ bands.
    Resets at market open each day (9:15 AM IST).
    """

    MARKET_OPEN_HOUR   = 9
    MARKET_OPEN_MINUTE = 15

    def __init__(self, symbol: str, maxlen: int = 500):
        self.symbol      = symbol
        self._bars: deque = deque(maxlen=maxlen)
        self._last_reset: Optional[date] = None

        # Running accumulators (reset daily)
        self._cum_pv  = 0.0   # Σ(P × V)
        self._cum_v   = 0.0   # ΣV
        self._cum_pv2 = 0.0   # Σ(P² × V)  for variance

    def _should_reset(self) -> bool:
        now   = datetime.now(IST)
        today = now.date()
        # Always initialize on first push (when _last_reset is None)
        if self._last_reset is None:
            return True
        if self._last_reset != today:
            # Reset at or after market open
            open_time = now.replace(hour=self.MARKET_OPEN_HOUR, minute=self.MARKET_OPEN_MINUTE, second=0)
            if now >= open_time:
                return True
        return False

    def _reset(self):
        self._bars.clear()
        self._cum_pv  = 0.0
        self._cum_v   = 0.0
        self._cum_pv2 = 0.0
        self._last_reset = datetime.now(IST).date()

    def push_bar(self, bar: OHLCVBar):
        """Add a new OHLCV bar and update running totals."""
        if self._should_reset():
            self._reset()

        if bar.volume <= 0:
            return

        self._bars.append(bar)
        self._cum_pv  += bar.typical_price * bar.volume
        self._cum_v   += bar.volume
        self._cum_pv2 += bar.typical_price ** 2 * bar.volume

    def push_tick(self, price: float, volume: int, ts: Optional[float] = None):
        """Push a tick as a synthetic bar."""
        if self._should_reset():
            self._reset()
        bar = OHLCVBar(ts or time.time(), price, price, price, price, max(volume, 1))
        self.push_bar(bar)

    @property
    def vwap(self) -> float:
        if self._cum_v <= 0:
            return 0.0
        return self._cum_pv / self._cum_v

    @property
    def vwap_std(self) -> float:
        """Standard deviation of price from VWAP (using running variance)."""
        if self._cum_v <= 0 or len(self._bars) < 3:
            return 0.0
        # Var(P) = E[P²] - E[P]² where weights are volume
        mean_p2 = self._cum_pv2 / self._cum_v
        mean_p  = self.vwap
        variance = mean_p2 - mean_p ** 2
        return math.sqrt(max(variance, 0.0))

    def bands(self, n_std: float = 1.0) -> Tuple[float, float]:
        """Returns (lower_band, upper_band) at n_std deviations."""
        v    = self.vwap
        std  = self.vwap_std
        return (v - n_std * std, v + n_std * std)

    def price_bias(self, current_price: float) -> Dict:
        """
        Signal based on price vs VWAP position.
        """
        v    = self.vwap
        if v <= 0 or current_price <= 0:
            return {"signal": "NEUTRAL", "strength": 0.0, "distance_pct": 0.0}

        dist_pct = (current_price - v) / v * 100
        std      = self.vwap_std
        z_score  = (current_price - v) / (std + 1e-6)

        if dist_pct > 0.5:
            signal   = "BULLISH"
            strength = min(abs(z_score) / 2.0, 1.0)
        elif dist_pct < -0.5:
            signal   = "BEARISH"
            strength = min(abs(z_score) / 2.0, 1.0)
        else:
            signal   = "AT_VWAP"
            strength = 0.0

        return {
            "signal":       signal,
            "strength":     round(strength, 3),
            "distance_pct": round(dist_pct, 3),
            "z_score":      round(z_score, 3),
        }

    def to_chart_series(self) -> List[Dict]:
        """Full VWAP series for chart rendering."""
        result = []
        cum_pv  = 0.0
        cum_v   = 0.0
        cum_pv2 = 0.0

        for bar in self._bars:
            cum_pv  += bar.typical_price * bar.volume
            cum_v   += bar.volume
            cum_pv2 += bar.typical_price ** 2 * bar.volume

            if cum_v <= 0:
                continue

            vwap_val = cum_pv / cum_v
            mean_p2  = cum_pv2 / cum_v
            variance = max(mean_p2 - vwap_val ** 2, 0)
            std_val  = math.sqrt(variance)

            result.append({
                "ts":     round(bar.ts, 0),
                "price":  round(bar.close, 2),
                "vwap":   round(vwap_val, 2),
                "upper1": round(vwap_val + std_val, 2),
                "lower1": round(vwap_val - std_val, 2),
                "upper2": round(vwap_val + 2 * std_val, 2),
                "lower2": round(vwap_val - 2 * std_val, 2),
                "volume": bar.volume,
            })
        return result


# ─── Anchored VWAP ────────────────────────────────────────────────────────────

class AnchoredVWAP:
    """
    VWAP anchored to a specific timestamp (e.g., major swing high/low).
    """

    def __init__(self, anchor_ts: float, anchor_price: float):
        self.anchor_ts    = anchor_ts
        self.anchor_price = anchor_price
        self._bars: List[OHLCVBar] = []
        self._cum_pv = 0.0
        self._cum_v  = 0.0

    def push(self, bar: OHLCVBar):
        if bar.ts >= self.anchor_ts and bar.volume > 0:
            self._bars.append(bar)
            self._cum_pv += bar.typical_price * bar.volume
            self._cum_v  += bar.volume

    @property
    def vwap(self) -> float:
        return self._cum_pv / self._cum_v if self._cum_v > 0 else 0.0

    def to_chart(self) -> List[Dict]:
        result = []
        cpv, cv = 0.0, 0.0
        for bar in self._bars:
            cpv += bar.typical_price * bar.volume
            cv  += bar.volume
            if cv > 0:
                result.append({"ts": round(bar.ts, 0), "avwap": round(cpv / cv, 2)})
        return result


# ─── Singletons ───────────────────────────────────────────────────────────────

_vwap_engines: Dict[str, VWAPEngine] = {}

def get_vwap_engine(symbol: str) -> VWAPEngine:
    if symbol not in _vwap_engines:
        _vwap_engines[symbol] = VWAPEngine(symbol)
    return _vwap_engines[symbol]


def push_vwap_tick(symbol: str, price: float, volume: int, ts: Optional[float] = None):
    get_vwap_engine(symbol).push_tick(price, volume, ts)


def get_vwap_response(symbol: str, current_price: float) -> Dict:
    engine = get_vwap_engine(symbol)
    v      = engine.vwap
    lb1, ub1 = engine.bands(1.0)
    lb2, ub2 = engine.bands(2.0)
    bias      = engine.price_bias(current_price)

    return {
        "symbol":          symbol,
        "current_price":   round(current_price, 2),
        "vwap":            round(v, 2),
        "upper_band_1std": round(ub1, 2),
        "lower_band_1std": round(lb1, 2),
        "upper_band_2std": round(ub2, 2),
        "lower_band_2std": round(lb2, 2),
        "std":             round(engine.vwap_std, 2),
        "bias":            bias,
        "signal":          bias["signal"],
        "chart_series":    engine.to_chart_series()[-100:],  # last 100 bars
        "timestamp":       time.time(),
    }
