"""
stocks/signals.py
Production-grade signal engine — fully spec-compliant.

Base scoring (max 10):
  c1: price > MA200                    +2
  c2: MA50 > MA200 (golden cross)      +2
  c3: ROC_252 > 25%   [stricter]       +2
  c4: RS > 1.2        [stricter]       +2
  c5: drawdown < 15%                   +1
  c6: vol_stable AND sigma < 30%       +1  [stricter]

Market regime adjustment (applied to base score):
  TRENDING  → +1
  MIXED     → -1
  SIDEWAYS  → -2
  BEARISH   → -3

Additional penalties:
  z_score > 2 (overbought)  → -2
  turnover < 5Cr            → -2
  price below MA50          → -1

Score clamped to [0, 10].

Risk-adjusted score:
  risk_adj = score * prob_up * (expected_return / downside_risk)
  Normalized to [0, 10].
"""

from typing import Dict, Optional


def compute_signal(
    features:       Dict,
    market_regime:  str = "MIXED",
    mc:             Optional[Dict] = None,
) -> Dict:
    """
    Args:
        features:      output of compute_features()
        market_regime: "TRENDING" | "MIXED" | "SIDEWAYS" | "BEARISH"
        mc:            Monte Carlo result dict (optional)
    """
    if not features:
        return {"signal": "INSUFFICIENT_DATA", "score": 0, "overbought_flag": False}

    price        = features.get("price",          0.0)
    ma50         = features.get("ma50",           0.0)
    ma200        = features.get("ma200",          0.0)
    roc_252      = features.get("roc_252",        0.0)
    drawdown     = features.get("drawdown",       100.0)
    vol_stable   = features.get("vol_stable",     False)
    rs           = features.get("rs",             1.0)
    sigma        = features.get("sigma",          50.0)
    z_score      = features.get("z_score",        0.0)
    avg_turnover = features.get("avg_turnover_cr", 0.0)
    trend_aligned = features.get("trend_aligned", False)
    entry_type   = features.get("entry_type",     "NONE")
    near_ma50    = features.get("near_ma50",      False)
    breakout     = features.get("breakout",       False)

    # ── 1. Base conditions (stricter thresholds per spec) ─────────────────────
    c1 = price > ma200 and ma200 > 0           # +2: long-term uptrend
    c2 = ma50  > ma200 and ma200 > 0           # +2: golden cross
    c3 = roc_252 > 25.0                        # +2: ROC > 25% (was 15%)
    c4 = rs > 1.2                              # +2: RS > 1.2  (was 1.1)
    c5 = drawdown < 15.0                       # +1: near highs
    c6 = bool(vol_stable) and sigma < 30.0     # +1: sigma < 30% (was 35%)

    base_score = 0
    if c1: base_score += 2
    if c2: base_score += 2
    if c3: base_score += 2
    if c4: base_score += 2
    if c5: base_score += 1
    if c6: base_score += 1

    # ── 2. Market regime adjustment (spec §1) ─────────────────────────────────
    regime = (market_regime or "MIXED").upper()
    if regime == "TRENDING":
        base_score += 1
    elif regime == "MIXED":
        base_score -= 1
    elif regime == "SIDEWAYS":
        base_score -= 2
    elif regime == "BEARISH":
        base_score -= 3

    # ── 3. Overbought filter (spec §2) ────────────────────────────────────────
    overbought_flag = z_score > 2.0
    if overbought_flag:
        base_score -= 2

    # ── 4. Additional penalties ───────────────────────────────────────────────
    adjustments = []
    if overbought_flag:
        adjustments.append("OVERBOUGHT:-2")

    if regime == "TRENDING":
        adjustments.append("TRENDING:+1")
    elif regime == "MIXED":
        adjustments.append("MIXED:-1")
    elif regime == "SIDEWAYS":
        adjustments.append("SIDEWAYS:-2")
    elif regime == "BEARISH":
        adjustments.append("BEARISH:-3")

    if avg_turnover < 5.0 and avg_turnover > 0:
        base_score -= 2
        adjustments.append("LOW_LIQUIDITY:-2")

    if not trend_aligned and c1:
        base_score -= 1
        adjustments.append("BELOW_MA50:-1")

    # ── 5. Clamp to [0, 10] ───────────────────────────────────────────────────
    score = int(min(10, max(0, base_score)))

    # ── 6. Risk-adjusted score (spec §2 / previous session) ──────────────────
    risk_adj_score = float(score)
    rr_ratio_mc    = 0.0

    if mc and price > 0:
        prob_up_raw    = float(mc.get("prob_up", 50.0))
        prob_up        = prob_up_raw / 100.0                       # 0–1
        expected_price = float(mc.get("expected_price", price))
        worst_5pct     = float(mc.get("worst_case_5pct", price * 0.95))

        expected_return = (expected_price - price) / price         # e.g. 0.12
        downside_risk   = (price - worst_5pct) / price             # e.g. 0.08

        # rr_ratio from MC (spec §5)
        if downside_risk > 1e-6:
            rr_ratio_mc = round(expected_return / downside_risk, 2)

        if downside_risk > 1e-6 and expected_return > 0:
            raw = score * prob_up * (expected_return / downside_risk)
            risk_adj_score = round(min(10.0, raw / 2.0), 2)
        elif expected_return <= 0:
            risk_adj_score = round(max(0.0, score * prob_up - 1.0), 2)
    else:
        prob_up_raw = 50.0

    # ── 7. Signal label ───────────────────────────────────────────────────────
    if score >= 8:
        signal = "STRONG BUY"
    elif score >= 6:
        signal = "BUY"
    elif score >= 4:
        signal = "WATCH"
    else:
        signal = "REJECT"

    # ── 8. Smart label (spec §8) ──────────────────────────────────────────────
    smart_label = _compute_smart_label(
        score, roc_252, z_score, overbought_flag,
        entry_type, breakout, near_ma50, trend_aligned, rs, regime,
    )

    # ── 9. Trend / momentum / risk labels ─────────────────────────────────────
    if c1 and c2:
        trend = "BULLISH"
    elif not c1 and not c2:
        trend = "BEARISH"
    else:
        trend = "MIXED"

    if roc_252 > 40:   momentum = "STRONG"
    elif roc_252 > 25: momentum = "POSITIVE"
    elif roc_252 > 0:  momentum = "WEAK"
    elif roc_252 > -15: momentum = "NEGATIVE"
    else:              momentum = "BEARISH"

    if drawdown < 8.0 and sigma < 22.0:
        risk_level = "LOW"
    elif drawdown >= 20.0 or sigma >= 45.0:
        risk_level = "HIGH"
    else:
        risk_level = "MEDIUM"

    # ── 10. Entry classification ──────────────────────────────────────────────
    if entry_type == "PULLBACK":
        entry_detail = "PULLBACK (IDEAL)" if z_score < 0.5 and drawdown < 10.0 else "PULLBACK (WEAK)"
    elif entry_type == "BREAKOUT":
        entry_detail = "BREAKOUT (FRESH)" if z_score < 2.0 else "BREAKOUT (EXTENDED)"
    else:
        entry_detail = "NONE"

    # ── 11. Confidence (0–100) ────────────────────────────────────────────────
    score_pct    = (score / 10.0) * 35.0
    rs_norm      = min(max((rs - 0.8) / 0.7, 0.0), 1.0)
    rs_pct       = rs_norm * 25.0
    roc_norm     = min(max((roc_252 + 20) / 80.0, 0.0), 1.0)
    momentum_pct = roc_norm * 20.0
    risk_pct     = 20.0 if risk_level == "LOW" else 12.0 if risk_level == "MEDIUM" else 4.0
    confidence   = round(score_pct + rs_pct + momentum_pct + risk_pct, 1)

    # ── 12. Composite rank score (updated in ranking.py, kept here for compat) ─
    prob_up_mc = prob_up_raw
    norm_score = (score / 10.0) * 100
    norm_rs    = min(max((rs - 0.5) / 1.5, 0.0), 1.0) * 100
    rank_score = round(
        0.30 * norm_score +
        0.20 * norm_rs    +
        0.20 * min(confidence, 100.0) +
        0.30 * min(prob_up_mc, 100.0),
        2,
    )

    buy_conditions_met = (
        score >= 8
        and prob_up_mc > 70
        and trend_aligned
        and not overbought_flag
    )

    return {
        # Core
        "signal":              signal,
        "smart_label":         smart_label,
        "score":               score,
        "adjusted_score":      score,          # alias — score already includes all adjustments
        "risk_adj_score":      round(risk_adj_score, 2),
        "max_score":           10,
        # Labels
        "trend":               trend,
        "momentum":            momentum,
        "risk_level":          risk_level,
        "confidence":          confidence,
        "rank_score":          rank_score,
        "entry_detail":        entry_detail,
        # Flags (spec §9)
        "overbought_flag":     overbought_flag,
        "overbought":          overbought_flag,   # alias for frontend compat
        "trend_aligned":       trend_aligned,
        "liquidity_ok":        avg_turnover >= 5.0,
        "buy_conditions_met":  buy_conditions_met,
        # Adjustments log
        "adjustments":         adjustments,
        "market_regime_used":  regime,
        # MC-derived
        "prob_up_mc":          round(prob_up_mc, 1),
        "rr_ratio_mc":         rr_ratio_mc,
        # Individual conditions
        "price_above_ma200":   c1,
        "ma50_above_ma200":    c2,
        "roc_positive":        c3,
        "rs_outperforming":    c4,
        "low_drawdown":        c5,
        "vol_stable":          c6,
    }


def _compute_smart_label(
    score: int, roc_252: float, z_score: float, overbought: bool,
    entry_type: str, breakout: bool, near_ma50: bool,
    trend_aligned: bool, rs: float, regime: str,
) -> str:
    """Smart label per spec §8."""
    if score < 4:
        return "AVOID"

    # Spec §8 exact rules
    if breakout and score >= 8:
        return "BREAKOUT CONFIRMED"

    if near_ma50 and score >= 8:
        return "PULLBACK OPPORTUNITY"

    if z_score > 2:
        return "OVERBOUGHT"

    if score >= 8:
        return "TREND CONTINUATION"

    # Extended labels for context
    if overbought and roc_252 > 50:
        return "MOMENTUM PEAK"

    if roc_252 < 5 and score >= 6 and rs > 1.0:
        return "EARLY TREND"

    if roc_252 > 30 and score >= 8 and not overbought:
        return "STRONG MOMENTUM"

    if regime == "SIDEWAYS" and score >= 6:
        return "RANGE TRADE"

    if score >= 6:
        return "BUY"

    return "NEUTRAL"
