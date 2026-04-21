"""
stocks/features.py
Vectorized feature computation — NumPy/Pandas only, no ML.
Includes Relative Strength vs NIFTY benchmark, ATR, overbought detection.
"""

import math
import numpy as np
import pandas as pd
from typing import Dict, List, Optional


def compute_features(
    candles: List[Dict],
    nifty_candles: Optional[List[Dict]] = None,
) -> Dict:
    if len(candles) < 252:
        return {}

    df = pd.DataFrame(candles).sort_values("ts").reset_index(drop=True)
    closes  = df["close"].values.astype(np.float64)
    volumes = df["volume"].values.astype(np.float64)
    highs   = df["high"].values.astype(np.float64)
    lows    = df["low"].values.astype(np.float64)

    price = float(closes[-1])
    if price <= 0:
        return {}

    # ── 1. Log returns ────────────────────────────────────────────────────────
    log_ret = np.log(closes[1:] / closes[:-1])

    # ── 2. Momentum ROC ───────────────────────────────────────────────────────
    roc_252 = float((closes[-1] - closes[-253]) / closes[-253]) if len(closes) >= 253 else 0.0
    roc_63  = float((closes[-1] - closes[-64])  / closes[-64])  if len(closes) >= 64  else 0.0
    roc_21  = float((closes[-1] - closes[-22])  / closes[-22])  if len(closes) >= 22  else 0.0

    # ── 3. Moving averages ────────────────────────────────────────────────────
    ma20  = float(closes[-20:].mean())  if len(closes) >= 20  else price
    ma50  = float(closes[-50:].mean())  if len(closes) >= 50  else price
    ma200 = float(closes[-200:].mean()) if len(closes) >= 200 else price

    # ── 4. Annualized volatility ──────────────────────────────────────────────
    n_vol      = min(252, len(log_ret))
    sigma      = float(log_ret[-n_vol:].std() * math.sqrt(252)) if n_vol >= 5 else 0.0
    sigma_20   = float(log_ret[-20:].std()  * math.sqrt(252)) if len(log_ret) >= 20  else sigma
    sigma_252  = float(log_ret[-252:].std() * math.sqrt(252)) if len(log_ret) >= 252 else sigma
    vol_stable = sigma_20 <= sigma_252 * 1.5

    # ── 5. ATR (14-day Average True Range) ───────────────────────────────────
    # ATR = mean of True Range over 14 days
    # TR = max(H-L, |H-prev_C|, |L-prev_C|)
    if len(closes) >= 15:
        tr_arr = np.maximum(
            highs[-14:] - lows[-14:],
            np.maximum(
                np.abs(highs[-14:] - closes[-15:-1]),
                np.abs(lows[-14:]  - closes[-15:-1]),
            )
        )
        atr_14 = float(tr_arr.mean())
        atr_pct = round(atr_14 / price * 100, 2) if price > 0 else 0.0
    else:
        atr_14  = float(highs[-1] - lows[-1])
        atr_pct = round(atr_14 / price * 100, 2) if price > 0 else 0.0

    # ── 6. Drawdown from 52-week high ─────────────────────────────────────────
    peak = float(closes[-252:].max()) if len(closes) >= 252 else float(closes.max())
    dd   = float((peak - price) / peak) if peak > 0 else 0.0

    # ── 7. Z-Score (20-day) — overbought/oversold ────────────────────────────
    p20     = closes[-20:]
    z_mean  = float(p20.mean())
    z_std   = float(p20.std())
    z_score = float((price - z_mean) / z_std) if z_std > 1e-6 else 0.0

    # Overbought: z_score > 2 (price > 2 std above 20-day mean)
    # Oversold:   z_score < -2
    overbought = z_score > 2.0
    oversold   = z_score < -2.0

    # ── 8. Relative Strength vs NIFTY ────────────────────────────────────────
    rs = 1.0
    if nifty_candles and len(nifty_candles) >= 253:
        ndf = pd.DataFrame(nifty_candles).sort_values("ts").reset_index(drop=True)
        nc  = ndf["close"].values.astype(np.float64)
        n_common = min(len(closes), len(nc), 253)
        stock_ret = float((closes[-1] - closes[-n_common]) / closes[-n_common]) if closes[-n_common] > 0 else 0.0
        nifty_ret = float((nc[-1]    - nc[-n_common])    / nc[-n_common])    if nc[-n_common]    > 0 else 0.0
        if abs(nifty_ret) > 1e-6:
            rs = round((1 + stock_ret) / (1 + nifty_ret), 4)
        else:
            rs = 1.0

    # ── 9. Shannon entropy ────────────────────────────────────────────────────
    ret_window = log_ret[-252:] if len(log_ret) >= 252 else log_ret
    counts, _  = np.histogram(ret_window, bins=10)
    total      = counts.sum()
    if total > 0:
        probs   = counts[counts > 0] / total
        raw_h   = -float(np.sum(probs * np.log2(probs)))
        entropy = raw_h / math.log2(10)
    else:
        entropy = 0.5

    # ── 10. Entry timing ──────────────────────────────────────────────────────
    near_ma50 = ma50 > 0 and price > ma50 and (price - ma50) / ma50 < 0.03
    high_20   = float(highs[-21:-1].max()) if len(highs) >= 21 else float(highs.max())
    breakout  = price > high_20

    if near_ma50:
        entry_type = "PULLBACK"
    elif breakout:
        entry_type = "BREAKOUT"
    else:
        entry_type = "NONE"

    # ── 11. VWAP (20-day) ─────────────────────────────────────────────────────
    typical = (highs[-20:] + lows[-20:] + closes[-20:]) / 3.0
    vol_20  = volumes[-20:]
    vwap    = float(np.sum(typical * vol_20) / np.sum(vol_20)) if np.sum(vol_20) > 0 else price

    # ── 12. 52-week high / low ────────────────────────────────────────────────
    w52_high = float(highs[-252:].max()) if len(highs) >= 252 else float(highs.max())
    w52_low  = float(lows[-252:].min())  if len(lows)  >= 252 else float(lows.min())

    # ── 13. Support / Resistance ──────────────────────────────────────────────
    support    = float(lows[-20:].min())
    resistance = float(highs[-20:].max())

    # ── 14. Sparkline ─────────────────────────────────────────────────────────
    hist_window = closes[-260:] if len(closes) >= 260 else closes
    sparkline   = [round(float(v), 2) for v in hist_window[::5]]

    # ── 15. Liquidity ─────────────────────────────────────────────────────────
    avg_vol_20d     = float(volumes[-20:].mean()) if len(volumes) >= 20 else float(volumes.mean())
    avg_turnover_cr = round(price * avg_vol_20d / 1e7, 2)
    is_liquid       = avg_turnover_cr >= 5.0

    # ── 16. Stop loss & target (ATR-based) ────────────────────────────────────
    # Stop loss: 1.5x ATR below entry (tighter than fixed %)
    # Target: 3x ATR above entry (1:2 R/R minimum)
    atr_stop_loss_pct  = round(1.5 * atr_pct, 2)   # % below entry
    atr_target_pct     = round(3.0 * atr_pct, 2)   # % above entry
    stop_loss_price    = round(price * (1 - atr_stop_loss_pct / 100), 2)
    target_price       = round(price * (1 + atr_target_pct   / 100), 2)
    risk_reward_ratio  = round(atr_target_pct / atr_stop_loss_pct, 2) if atr_stop_loss_pct > 0 else 2.0

    # ── 17. Trend alignment (MA50 > MA200 = golden cross) ────────────────────
    trend_aligned = bool(price > ma50 > ma200 and ma200 > 0)

    return {
        "price":             round(price, 2),
        "ma20":              round(ma20, 2),
        "ma50":              round(ma50, 2),
        "ma200":             round(ma200, 2),
        "roc_252":           round(roc_252 * 100, 2),
        "roc_63":            round(roc_63  * 100, 2),
        "roc_21":            round(roc_21  * 100, 2),
        "sigma":             round(sigma * 100, 2),
        "sigma_20":          round(sigma_20 * 100, 2),
        "vol_stable":        vol_stable,
        "atr_14":            round(atr_14, 2),
        "atr_pct":           atr_pct,
        "drawdown":          round(dd * 100, 2),
        "z_score":           round(z_score, 3),
        "overbought":        overbought,
        "oversold":          oversold,
        "entropy":           round(entropy, 4),
        "vwap":              round(vwap, 2),
        "rs":                round(rs, 4),
        "entry_type":        entry_type,
        "near_ma50":         near_ma50,
        "breakout":          breakout,
        "trend_aligned":     trend_aligned,
        "candles":           len(candles),
        "w52_high":          round(w52_high, 2),
        "w52_low":           round(w52_low, 2),
        "support":           round(support, 2),
        "resistance":        round(resistance, 2),
        "sparkline":         sparkline,
        "avg_vol_20d":       round(avg_vol_20d, 0),
        "avg_turnover_cr":   avg_turnover_cr,
        "is_liquid":         is_liquid,
        # Pre-computed trade levels
        "stop_loss_price":   stop_loss_price,
        "target_price":      target_price,
        "atr_stop_loss_pct": atr_stop_loss_pct,
        "atr_target_pct":    atr_target_pct,
        "risk_reward_ratio": risk_reward_ratio,
    }
