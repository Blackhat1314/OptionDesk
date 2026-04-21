"""
Alert Engine
=============
Rule-based alert system for:
  - Gamma flip crossed
  - IV spike
  - OI build-up at dominant strikes
  - Regime change
  - Price crossing VWAP
  - GEX spike
  - Extreme PCR

Alerts are stored in a ring buffer and emitted via WebSocket.
"""

import time
import asyncio
from typing import Dict, List, Optional, Callable, Set
from collections import deque
from dataclasses import dataclass, field, asdict
from enum import Enum



# ─── Alert Types ──────────────────────────────────────────────────────────────

class AlertType(str, Enum):
    GAMMA_FLIP        = "GAMMA_FLIP"
    IV_SPIKE          = "IV_SPIKE"
    IV_CRUSH          = "IV_CRUSH"
    OI_BUILDUP        = "OI_BUILDUP"
    OI_UNWINDING      = "OI_UNWINDING"
    REGIME_CHANGE     = "REGIME_CHANGE"
    VWAP_CROSS        = "VWAP_CROSS"
    GEX_SPIKE         = "GEX_SPIKE"
    EXTREME_PCR       = "EXTREME_PCR"
    MAX_PAIN_APPROACH = "MAX_PAIN_APPROACH"
    CALL_WALL_TEST    = "CALL_WALL_TEST"
    PUT_WALL_TEST     = "PUT_WALL_TEST"


class AlertSeverity(str, Enum):
    INFO    = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


# ─── Alert dataclass ──────────────────────────────────────────────────────────

@dataclass
class Alert:
    type:        AlertType
    severity:    AlertSeverity
    symbol:      str
    message:     str
    data:        Dict = field(default_factory=dict)
    timestamp:   float = field(default_factory=time.time)
    acknowledged: bool = False

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["type"]     = self.type.value
        d["severity"] = self.severity.value
        return d


# ─── Alert Rules ──────────────────────────────────────────────────────────────

class AlertEngine:
    """
    Stateful alert engine. Maintains cooldown timers to prevent alert spam.
    """

    # Cooldown in seconds per alert type (prevent duplicate flooding)
    COOLDOWNS: Dict[AlertType, float] = {
        AlertType.GAMMA_FLIP:        300,   # 5 min
        AlertType.IV_SPIKE:          180,
        AlertType.IV_CRUSH:          180,
        AlertType.OI_BUILDUP:        120,
        AlertType.OI_UNWINDING:      120,
        AlertType.REGIME_CHANGE:     300,
        AlertType.VWAP_CROSS:         60,
        AlertType.GEX_SPIKE:         120,
        AlertType.EXTREME_PCR:       300,
        AlertType.MAX_PAIN_APPROACH: 600,
        AlertType.CALL_WALL_TEST:     90,
        AlertType.PUT_WALL_TEST:      90,
    }

    def __init__(self):
        self._history: deque = deque(maxlen=500)
        self._last_fired: Dict[str, float] = {}    # key = f"{symbol}:{type}"
        self._callbacks: List[Callable] = []
        self._lock = asyncio.Lock()

    def add_callback(self, fn: Callable):
        """Register async callback: async def fn(alert: Alert)"""
        self._callbacks.append(fn)

    def _cooldown_key(self, symbol: str, alert_type: AlertType) -> str:
        return f"{symbol}:{alert_type.value}"

    def _in_cooldown(self, symbol: str, alert_type: AlertType) -> bool:
        key      = self._cooldown_key(symbol, alert_type)
        last     = self._last_fired.get(key, 0.0)
        cooldown = self.COOLDOWNS.get(alert_type, 60.0)
        return (time.time() - last) < cooldown

    async def _fire(self, alert: Alert):
        key = self._cooldown_key(alert.symbol, alert.type)
        if self._in_cooldown(alert.symbol, alert.type):
            return
        self._last_fired[key] = time.time()
        self._history.append(alert)
        for cb in self._callbacks:
            try:
                await cb(alert)
            except Exception:
                pass

    # ── Rule checks ───────────────────────────────────────────────────────────

    async def check_gamma_flip(self, symbol: str, prev_gex: float, curr_gex: float, spot: float):
        if prev_gex * curr_gex < 0:
            direction = "positive→negative" if prev_gex > 0 else "negative→positive"
            await self._fire(Alert(
                type     = AlertType.GAMMA_FLIP,
                severity = AlertSeverity.CRITICAL,
                symbol   = symbol,
                message  = f"Gamma flip {direction} near {spot:.0f}",
                data     = {"prev_gex": prev_gex, "curr_gex": curr_gex, "spot": spot, "direction": direction},
            ))

    async def check_iv_spike(self, symbol: str, prev_iv: float, curr_iv: float, threshold_pct: float = 15.0):
        if prev_iv <= 0:
            return
        change_pct = (curr_iv - prev_iv) / prev_iv * 100
        if change_pct > threshold_pct:
            await self._fire(Alert(
                type     = AlertType.IV_SPIKE,
                severity = AlertSeverity.WARNING,
                symbol   = symbol,
                message  = f"IV spike +{change_pct:.1f}% ({prev_iv:.1f}% → {curr_iv:.1f}%)",
                data     = {"prev_iv": prev_iv, "curr_iv": curr_iv, "change_pct": round(change_pct, 1)},
            ))
        elif change_pct < -threshold_pct:
            await self._fire(Alert(
                type     = AlertType.IV_CRUSH,
                severity = AlertSeverity.INFO,
                symbol   = symbol,
                message  = f"IV crush {change_pct:.1f}% ({prev_iv:.1f}% → {curr_iv:.1f}%)",
                data     = {"prev_iv": prev_iv, "curr_iv": curr_iv, "change_pct": round(change_pct, 1)},
            ))

    async def check_oi_flow(self, symbol: str, dominant_flows: List[Dict]):
        for flow in dominant_flows[:3]:
            ft = flow.get("flow", "NEUTRAL")
            if ft in ("LONG_BUILDUP", "SHORT_BUILDUP") and abs(flow.get("oi_change", 0)) > 100_000:
                alert_type = AlertType.OI_BUILDUP if ft == "LONG_BUILDUP" else AlertType.OI_BUILDUP
                await self._fire(Alert(
                    type     = alert_type,
                    severity = AlertSeverity.INFO,
                    symbol   = symbol,
                    message  = f"{ft} at {flow['option_type']} {flow['strike']:.0f} | ΔOI {flow['oi_change']:+,}",
                    data     = flow,
                ))

    async def check_regime_change(self, symbol: str, prev_regime: str, curr_regime: str):
        if prev_regime and prev_regime != curr_regime:
            await self._fire(Alert(
                type     = AlertType.REGIME_CHANGE,
                severity = AlertSeverity.WARNING,
                symbol   = symbol,
                message  = f"Market regime: {prev_regime} → {curr_regime}",
                data     = {"from": prev_regime, "to": curr_regime},
            ))

    async def check_vwap_cross(self, symbol: str, prev_price: float, curr_price: float, vwap: float):
        if vwap <= 0:
            return
        crossed_above = prev_price <= vwap < curr_price
        crossed_below = prev_price >= vwap > curr_price
        if crossed_above:
            await self._fire(Alert(
                type     = AlertType.VWAP_CROSS,
                severity = AlertSeverity.INFO,
                symbol   = symbol,
                message  = f"Price crossed ABOVE VWAP ({vwap:.2f}) — bullish bias",
                data     = {"price": curr_price, "vwap": vwap, "direction": "UP"},
            ))
        elif crossed_below:
            await self._fire(Alert(
                type     = AlertType.VWAP_CROSS,
                severity = AlertSeverity.INFO,
                symbol   = symbol,
                message  = f"Price crossed BELOW VWAP ({vwap:.2f}) — bearish bias",
                data     = {"price": curr_price, "vwap": vwap, "direction": "DOWN"},
            ))

    async def check_gex_spike(self, symbol: str, gex_spike_event: Optional[Dict]):
        if gex_spike_event:
            pct = gex_spike_event.get("pct_change", 0)
            await self._fire(Alert(
                type     = AlertType.GEX_SPIKE,
                severity = AlertSeverity.WARNING,
                symbol   = symbol,
                message  = f"GEX spike {pct:+.1f}% ({gex_spike_event.get('gex_from', 0):.3f}B → {gex_spike_event.get('gex_to', 0):.3f}B)",
                data     = gex_spike_event,
            ))

    async def check_extreme_pcr(self, symbol: str, pcr: float):
        if pcr > 1.5:
            await self._fire(Alert(
                type     = AlertType.EXTREME_PCR,
                severity = AlertSeverity.WARNING,
                symbol   = symbol,
                message  = f"Extreme bullish PCR = {pcr:.2f} (>1.5) — contrarian bearish signal",
                data     = {"pcr": pcr},
            ))
        elif pcr < 0.5:
            await self._fire(Alert(
                type     = AlertType.EXTREME_PCR,
                severity = AlertSeverity.WARNING,
                symbol   = symbol,
                message  = f"Extreme bearish PCR = {pcr:.2f} (<0.5) — contrarian bullish signal",
                data     = {"pcr": pcr},
            ))

    async def check_wall_test(
        self, symbol: str, spot: float,
        call_wall: float, put_wall: float, threshold_pct: float = 0.003,
    ):
        if call_wall > 0 and abs(spot - call_wall) / call_wall < threshold_pct:
            await self._fire(Alert(
                type     = AlertType.CALL_WALL_TEST,
                severity = AlertSeverity.INFO,
                symbol   = symbol,
                message  = f"Price testing Call Wall at {call_wall:.0f} — expect resistance",
                data     = {"spot": spot, "call_wall": call_wall},
            ))
        if put_wall > 0 and abs(spot - put_wall) / put_wall < threshold_pct:
            await self._fire(Alert(
                type     = AlertType.PUT_WALL_TEST,
                severity = AlertSeverity.INFO,
                symbol   = symbol,
                message  = f"Price testing Put Wall at {put_wall:.0f} — expect support",
                data     = {"spot": spot, "put_wall": put_wall},
            ))

    # ── History access ────────────────────────────────────────────────────────

    def get_alerts(
        self,
        symbol: Optional[str] = None,
        limit: int = 50,
        severity: Optional[str] = None,
    ) -> List[Dict]:
        alerts = list(self._history)
        if symbol:
            alerts = [a for a in alerts if a.symbol == symbol]
        if severity:
            alerts = [a for a in alerts if a.severity.value == severity.upper()]
        return [a.to_dict() for a in reversed(alerts[-limit:])]

    def get_unacknowledged(self) -> List[Dict]:
        return [a.to_dict() for a in self._history if not a.acknowledged]

    def acknowledge(self, idx: int):
        alerts = list(self._history)
        if 0 <= idx < len(alerts):
            alerts[-(idx + 1)].acknowledged = True


# ─── Singleton ────────────────────────────────────────────────────────────────

_alert_engine: Optional[AlertEngine] = None

def get_alert_engine() -> AlertEngine:
    global _alert_engine
    if _alert_engine is None:
        _alert_engine = AlertEngine()
    return _alert_engine
