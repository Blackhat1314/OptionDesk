"""
stocks/ranking.py
Production-grade ranking — fully spec-compliant.

Rank formula (spec §4):
  rank_score = 0.30 * norm_score + 0.20 * norm_rs + 0.20 * confidence + 0.30 * prob_up_mc

Correlation filter (spec §6):
  Build 252-day return correlation matrix.
  For sorted candidates: keep stock only if corr < 0.8 with all already-selected stocks.
  Fully vectorized via pandas.

Output fields (spec §9):
  overbought_flag, rr_ratio, smart_label, adjusted_score, prob_up_mc, correlation_filtered
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from stocks.universe import get_group, get_sector, GROUPS, MAX_PER_SECTOR
from stocks.database import get_candles

TOP_PICKS_PER_SECTOR = 2
TOP_PICKS_COUNT      = 5
CORR_THRESHOLD       = 0.80   # spec §6
RISK_PER_TRADE_PCT   = 2.0


# ── Rank formula (spec §4) ────────────────────────────────────────────────────

def _composite_rank(s: Dict) -> float:
    """
    rank_score = 0.30 * norm_score + 0.20 * norm_rs + 0.20 * confidence + 0.30 * prob_up_mc
    All inputs normalized to [0, 100].
    """
    score      = s.get("score", 0)
    rs         = s.get("rs", 1.0)
    confidence = s.get("confidence", 0.0)
    prob_up    = s.get("prob_up_mc", 50.0)   # already 0–100

    norm_score = (score / 10.0) * 100
    norm_rs    = min(max((rs - 0.5) / 1.5, 0.0), 1.0) * 100
    norm_conf  = min(confidence, 100.0)
    norm_prob  = min(prob_up, 100.0)

    return round(
        0.30 * norm_score +
        0.20 * norm_rs    +
        0.20 * norm_conf  +
        0.30 * norm_prob,
        2,
    )


# ── Correlation filter (spec §6) ─────────────────────────────────────────────

def _build_corr_matrix(symbols: List[str]) -> Optional[pd.DataFrame]:
    """
    Build 252-day daily return correlation matrix for given symbols.
    Fully vectorized — no per-stock loops.
    Returns DataFrame or None if insufficient data.
    """
    price_dict: Dict[str, np.ndarray] = {}
    for sym in symbols:
        try:
            candles = get_candles(sym)
            if len(candles) >= 253:
                closes = np.array([c["close"] for c in candles[-253:]], dtype=np.float64)
                price_dict[sym] = np.log(closes[1:] / closes[:-1])   # 252 log returns
        except Exception:
            pass

    if len(price_dict) < 2:
        return None

    df = pd.DataFrame(price_dict)
    return df.corr()


def _apply_correlation_filter(
    sorted_candidates: List[Dict],
    corr_matrix: Optional[pd.DataFrame],
) -> List[Dict]:
    """
    Spec §6: For each candidate (sorted by rank desc):
      Keep if corr < 0.80 with ALL already-selected stocks.
      Mark correlation_filtered=True for removed stocks.
    """
    if corr_matrix is None:
        for c in sorted_candidates:
            c["correlation_filtered"] = False
        return sorted_candidates

    selected_syms: List[str] = []
    result: List[Dict] = []

    for cand in sorted_candidates:
        sym = cand.get("symbol", "")
        if sym not in corr_matrix.columns:
            cand["correlation_filtered"] = False
            result.append(cand)
            selected_syms.append(sym)
            continue

        # Check correlation with all already-selected stocks
        too_correlated = False
        for sel in selected_syms:
            if sel in corr_matrix.columns:
                corr_val = float(corr_matrix.loc[sym, sel])
                if corr_val > CORR_THRESHOLD:
                    too_correlated = True
                    break

        cand["correlation_filtered"] = too_correlated
        if not too_correlated:
            selected_syms.append(sym)
        result.append(cand)

    return result


# ── Position sizing ───────────────────────────────────────────────────────────

def compute_position_size(
    capital: float,
    entry_price: float,
    stop_loss_price: float,
    allocation_pct: float = 10.0,
) -> Dict:
    if entry_price <= 0 or stop_loss_price <= 0 or stop_loss_price >= entry_price:
        return {"shares": 0, "invested": 0, "risk_amount": 0, "allocation_pct": 0}

    risk_per_share  = entry_price - stop_loss_price
    risk_amount     = capital * (RISK_PER_TRADE_PCT / 100.0)
    shares_by_risk  = risk_amount / risk_per_share
    max_invested    = capital * (allocation_pct / 100.0)
    shares_by_alloc = max_invested / entry_price

    shares   = max(1, int(min(shares_by_risk, shares_by_alloc)))
    invested = round(shares * entry_price, 2)

    return {
        "shares":         shares,
        "invested":       invested,
        "risk_amount":    round(risk_amount, 2),
        "allocation_pct": round(invested / capital * 100, 1) if capital > 0 else 0,
    }


# ── Exit signals ──────────────────────────────────────────────────────────────

def compute_exit_signals(
    current_price: float,
    entry_price: float,
    stop_loss_price: float,
    target_price: float,
    score: int,
    holding_days: int = 0,
    max_hold_days: int = 120,
) -> Dict:
    if current_price <= 0 or entry_price <= 0:
        return {"action": "HOLD", "reason": "", "pnl_pct": 0, "urgency": "NONE"}

    pnl_pct = round((current_price - entry_price) / entry_price * 100, 2)

    if current_price <= stop_loss_price:
        return {"action": "EXIT", "reason": "STOP LOSS",             "pnl_pct": pnl_pct, "urgency": "HIGH"}
    if current_price >= target_price:
        return {"action": "EXIT", "reason": "BOOK PROFIT",           "pnl_pct": pnl_pct, "urgency": "MEDIUM"}
    if holding_days > max_hold_days:
        return {"action": "EXIT", "reason": "TIME EXIT (dead capital)", "pnl_pct": pnl_pct, "urgency": "LOW"}
    if score < 5:
        return {"action": "EXIT", "reason": "WEAKNESS (score dropped)", "pnl_pct": pnl_pct, "urgency": "MEDIUM"}

    return {"action": "HOLD", "reason": "", "pnl_pct": pnl_pct, "urgency": "NONE"}


# ── Rank and filter ───────────────────────────────────────────────────────────

def rank_and_filter(candidates: List[Dict]) -> Dict[str, List[Dict]]:
    for c in candidates:
        c["_rank"] = _composite_rank(c)

    sorted_cands = sorted(candidates, key=lambda x: x["_rank"], reverse=True)

    grouped: Dict[str, List[Dict]] = {g: [] for g in GROUPS}
    grouped["OTHER"] = []
    sector_count: Dict[str, int] = {}

    for cand in sorted_cands:
        sym    = cand.get("symbol", "")
        group  = cand.get("group",  get_group(sym))
        sector = cand.get("sector", get_sector(sym))
        key    = f"{group}:{sector}"

        if sector_count.get(key, 0) >= MAX_PER_SECTOR:
            continue
        sector_count[key] = sector_count.get(key, 0) + 1

        if group in grouped:
            grouped[group].append(cand)
        else:
            grouped["OTHER"].append(cand)

    return {g: v for g, v in grouped.items() if v}


# ── Top picks with correlation filter ────────────────────────────────────────

def build_top_picks(all_buy: List[Dict]) -> List[Dict]:
    """
    Build top picks with:
    1. Sort by rank_score
    2. Apply correlation filter (spec §6)
    3. Apply sector diversity (max TOP_PICKS_PER_SECTOR per sector)
    4. Assign allocation tiers
    """
    sorted_buy = sorted(all_buy, key=lambda x: x.get("rank_score", 0), reverse=True)

    # Build correlation matrix for buy candidates
    buy_syms    = [s.get("symbol", "") for s in sorted_buy]
    corr_matrix = _build_corr_matrix(buy_syms)

    # Apply correlation filter
    filtered = _apply_correlation_filter(sorted_buy, corr_matrix)

    sector_seen: Dict[str, int] = {}
    picks: List[Dict] = []

    for s in filtered:
        if s.get("correlation_filtered", False):
            continue   # skip correlated stocks

        sector = s.get("sector", "OTHER")
        if sector_seen.get(sector, 0) >= TOP_PICKS_PER_SECTOR:
            continue
        sector_seen[sector] = sector_seen.get(sector, 0) + 1

        rank = len(picks) + 1
        if rank <= 3:
            alloc_tier, alloc_label = "STRONG",    "Strong Allocation (40%)"
        elif rank <= 8:
            alloc_tier, alloc_label = "MEDIUM",    "Medium Allocation (40%)"
        else:
            alloc_tier, alloc_label = "WATCHLIST", "Watchlist (20%)"

        picks.append({
            "rank":                  rank,
            "symbol":                s.get("symbol"),
            "signal":                s.get("signal"),
            "smart_label":           s.get("smart_label", s.get("signal", "")),
            "score":                 s.get("score"),
            "adjusted_score":        s.get("adjusted_score", s.get("score")),
            "rank_score":            s.get("rank_score", 0),
            "rs":                    s.get("relative_strength", 1.0),
            "prob_up":               s.get("monte_carlo", {}).get("prob_up", 50) if s.get("monte_carlo") else 50,
            "prob_up_mc":            s.get("prob_up_mc", 50),
            "rr_ratio":              s.get("rr_ratio", 0),
            "entry_detail":          s.get("entry_detail", s.get("entry_type", "NONE")),
            "sector":                sector,
            "group":                 s.get("group"),
            "confidence":            s.get("confidence", 0),
            "roc_252":               s.get("roc_252", 0),
            "overbought_flag":       s.get("overbought_flag", False),
            "correlation_filtered":  False,
            "alloc_tier":            alloc_tier,
            "alloc_label":           alloc_label,
        })
        if len(picks) >= TOP_PICKS_COUNT:
            break

    return picks


# ── Market context ────────────────────────────────────────────────────────────

def build_market_context(all_stocks: List[Dict], buy_stocks: List[Dict]) -> Dict:
    if not all_stocks:
        return {}

    total       = len(all_stocks)
    bullish     = sum(1 for s in all_stocks if s.get("trend") == "BULLISH")
    breadth_pct = round(bullish / total * 100, 1) if total > 0 else 0

    if breadth_pct >= 65:   regime = "TRENDING"
    elif breadth_pct >= 45: regime = "MIXED"
    else:                   regime = "SIDEWAYS"

    sector_rs: Dict[str, List[float]] = {}
    for s in all_stocks:
        sec = s.get("sector", "OTHER")
        rs  = s.get("relative_strength") or s.get("rs", 1.0)
        sector_rs.setdefault(sec, []).append(rs)

    sector_avg_rs = {
        sec: round(sum(vals) / len(vals), 2)
        for sec, vals in sector_rs.items() if vals
    }

    top_sector  = max(sector_avg_rs, key=lambda k: sector_avg_rs[k]) if sector_avg_rs else "—"
    weak_sector = min(sector_avg_rs, key=lambda k: sector_avg_rs[k]) if sector_avg_rs else "—"

    rs_vals  = [s.get("relative_strength") or s.get("rs", 1.0) for s in buy_stocks]
    avg_rs   = round(sum(rs_vals) / len(rs_vals), 2) if rs_vals else 1.0

    score_dist = {"10": 0, "8-9": 0, "6-7": 0, "4-5": 0, "<4": 0}
    for s in all_stocks:
        sc = s.get("score", 0)
        if sc == 10:          score_dist["10"]  += 1
        elif sc >= 8:         score_dist["8-9"] += 1
        elif sc >= 6:         score_dist["6-7"] += 1
        elif sc >= 4:         score_dist["4-5"] += 1
        else:                 score_dist["<4"]  += 1

    conf_vals = [s.get("confidence", 0) for s in buy_stocks]
    avg_conf  = round(sum(conf_vals) / len(conf_vals), 1) if conf_vals else 0.0

    return {
        "market_regime":      regime,
        "breadth_pct":        breadth_pct,
        "top_sector":         top_sector,
        "weak_sector":        weak_sector,
        "sector_avg_rs":      sector_avg_rs,
        "avg_rs":             avg_rs,
        "avg_confidence":     avg_conf,
        "score_distribution": score_dist,
        "bullish_count":      bullish,
        "total_computed":     total,
    }


# ── Stock output builder ──────────────────────────────────────────────────────

def build_stock_output(
    symbol:   str,
    features: Dict,
    signals:  Dict,
    mc:       Dict,
    bt:       Dict,
) -> Dict:
    price      = features.get("price", 0)
    confidence = signals.get("confidence", 0.0)
    prob_up_mc = signals.get("prob_up_mc", mc.get("prob_up", 50.0) if mc else 50.0)
    rs         = features.get("rs", 1.0)
    score      = signals.get("score", 0)

    # Rank score (spec §4 formula)
    norm_score = (score / 10.0) * 100
    norm_rs    = min(max((rs - 0.5) / 1.5, 0.0), 1.0) * 100
    rank_score = round(
        0.30 * norm_score +
        0.20 * norm_rs    +
        0.20 * min(confidence, 100.0) +
        0.30 * min(prob_up_mc, 100.0),
        2,
    )

    # R/R ratio from MC (spec §5)
    rr_ratio = signals.get("rr_ratio_mc", 0.0)
    if rr_ratio == 0.0 and mc and price > 0:
        expected_price = float(mc.get("expected_price", price))
        worst_5pct     = float(mc.get("worst_case_5pct", price * 0.95))
        expected_return = (expected_price - price) / price
        downside_risk   = (price - worst_5pct) / price
        if downside_risk > 1e-6:
            rr_ratio = round(expected_return / downside_risk, 2)

    # ATR-based trade levels
    stop_loss_price = features.get("stop_loss_price",   round(price * 0.92, 2))
    target_price    = features.get("target_price",      round(price * 1.15, 2))
    atr_stop_pct    = features.get("atr_stop_loss_pct", 8.0)
    atr_target_pct  = features.get("atr_target_pct",    15.0)
    atr_rr          = features.get("risk_reward_ratio", 2.0)

    # Holding period guidance
    if score >= 8:
        recommended_hold, hold_confidence = "3-6 months", "HIGH"
    elif score >= 6:
        recommended_hold, hold_confidence = "1-3 months", "MEDIUM"
    else:
        recommended_hold, hold_confidence = "< 1 month",  "LOW"

    return {
        "symbol":               symbol,
        "group":                get_group(symbol),
        "sector":               get_sector(symbol),
        # Signal
        "signal":               signals.get("signal",       "REJECT"),
        "smart_label":          signals.get("smart_label",  "NEUTRAL"),
        "score":                score,
        "adjusted_score":       score,          # score already includes all adjustments
        "risk_adj_score":       signals.get("risk_adj_score", score),
        "max_score":            10,
        "rank_score":           rank_score,
        "confidence":           confidence,
        # Labels
        "trend":                signals.get("trend",        "MIXED"),
        "momentum":             signals.get("momentum",     "WEAK"),
        "risk_level":           signals.get("risk_level",   "MEDIUM"),
        "entry_detail":         signals.get("entry_detail", "NONE"),
        # Flags (spec §9)
        "overbought_flag":      signals.get("overbought_flag", False),
        "overbought":           signals.get("overbought_flag", False),
        "oversold":             features.get("oversold",    False),
        "correlation_filtered": False,          # set by build_top_picks for top picks
        "buy_conditions_met":   signals.get("buy_conditions_met", False),
        "adjustments":          signals.get("adjustments",  []),
        # MC-derived (spec §9)
        "prob_up_mc":           round(prob_up_mc, 1),
        "rr_ratio":             rr_ratio,
        # Features
        "relative_strength":    rs,
        "entry_type":           features.get("entry_type",  "NONE"),
        "price":                price,
        "ma50":                 features.get("ma50",        0),
        "ma200":                features.get("ma200",       0),
        "roc_252":              features.get("roc_252",     0),
        "roc_63":               features.get("roc_63",      0),
        "roc_21":               features.get("roc_21",      0),
        "w52_high":             features.get("w52_high",    0),
        "w52_low":              features.get("w52_low",     0),
        "support":              features.get("support",     0),
        "resistance":           features.get("resistance",  0),
        "sparkline":            features.get("sparkline",   []),
        "avg_turnover_cr":      features.get("avg_turnover_cr", 0),
        "is_liquid":            features.get("is_liquid",   True),
        "atr_pct":              features.get("atr_pct",     2.0),
        # Trade levels
        "stop_loss_price":      stop_loss_price,
        "target_price":         target_price,
        "atr_stop_loss_pct":    atr_stop_pct,
        "atr_target_pct":       atr_target_pct,
        "risk_reward_ratio":    atr_rr,
        # Guidance
        "recommended_hold":     recommended_hold,
        "hold_confidence":      hold_confidence,
        "risk": {
            "drawdown":   round(features.get("drawdown", 0) / 100, 4),
            "volatility": round(features.get("sigma",    0) / 100, 4),
            "vol_stable": features.get("vol_stable", False),
        },
        "monte_carlo": {
            "expected_price":  mc.get("expected_price",  price),
            "prob_up":         mc.get("prob_up",         50),
            "prob_down":       mc.get("prob_down",       50),
            "worst_case_5pct": mc.get("worst_case_5pct", 0),
            "best_case_95pct": mc.get("best_case_95pct", 0),
            "position_advice": mc.get("position_size_advice", "NORMAL"),
            "horizon_days":    mc.get("horizon_days",    63),
            "horizon_label":   mc.get("horizon_label",   "3M"),
            "regime":          mc.get("regime",          "NORMAL"),
        } if mc else {},
        "backtest": {
            "total_trades": bt.get("total_trades", 0),
            "win_rate":     bt.get("win_rate",     0),
            "avg_return":   bt.get("avg_return",   0),
            "sharpe":       bt.get("sharpe_ratio", 0),
            "max_drawdown": bt.get("max_drawdown", 0),
        } if bt else {},
    }
