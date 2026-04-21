"""
Pipeline Worker — orchestrates all quant layers every 10s.
Reads from Redis only. Writes result to Redis.
NEVER called from API endpoints.
"""

import asyncio
import time
from typing import Dict, List

import pytz
from datetime import datetime

from core.redis_cache import get_cache
from quant.instrument_loader import get_loaded_ids
from quant.filter_engine import compute_filter_features, select_top_n
from quant.signal_engine import compute_signal_features, select_final_candidates
from quant.risk_engine import run_risk_for_candidates

PIPELINE_INTERVAL = 10
RESULT_TTL        = 60   # 60s TTL — covers pipeline interval with buffer


def _is_market_open() -> bool:
    ist  = pytz.timezone("Asia/Kolkata")
    now  = datetime.now(ist)
    mins = now.hour * 60 + now.minute
    return now.weekday() < 5 and 9 * 60 + 15 <= mins <= 15 * 60 + 30


async def _load_histories(cache, symbols: List[str]) -> Dict[str, List[Dict]]:
    histories = {}
    for sym in symbols:
        candles = await cache.ts_get_all(f"stock:{sym}:history")
        if candles:
            histories[sym] = candles
    return histories


async def run_pipeline_worker():
    cache = get_cache()

    while True:
        try:
            ts_start      = time.time()
            market_open   = _is_market_open()
            all_syms      = list(get_loaded_ids().keys())

            # Layer 1: Load histories from Redis
            histories = await _load_histories(cache, all_syms)

            if len(histories) < 5:
                await asyncio.sleep(PIPELINE_INTERVAL)
                continue

            # Detect if prices are static (market closed)
            static_count = 0
            for sym, candles in list(histories.items())[:10]:
                if len(candles) >= 3:
                    prices = [c.get("price", 0) for c in candles[-3:]]
                    if len(set(prices)) == 1:
                        static_count += 1
            market_closed = static_count >= 5

            # Layer 2: Filter engine — always runs
            filter_features = compute_filter_features(histories)
            top20_syms      = select_top_n(filter_features, n=20)
            top20_histories = {s: histories[s] for s in top20_syms if s in histories}
            top20_features  = {s: filter_features[s] for s in top20_syms if s in filter_features}

            # Layer 3: Signal engine
            signals    = compute_signal_features(top20_histories, top20_features)
            candidates = select_final_candidates(
                signals,
                min_score=3,
                top_n=10,
                market_closed=market_closed,
            )

            # Layer 4: Risk engine (only for candidates)
            enriched = run_risk_for_candidates(candidates, top20_histories)

            # Build result
            result = {
                "market_open":   market_open,
                "market_closed": market_closed,
                "pipeline_stats": {
                    "universe_size":    len(all_syms),
                    "data_loaded":      len(histories),
                    "filtered_layer2":  len(top20_syms),
                    "final_candidates": len(enriched),
                    "computed_at":      time.time(),
                    "market_open":      market_open,
                },
                "top_candidates": [
                    {
                        "symbol":        c["symbol"],
                        "price":         c["price"],
                        "open":          c.get("open", c["price"]),
                        "high":          c.get("high", c["price"]),
                        "low":           c.get("low",  c["price"]),
                        "signal":        c["signal"],
                        "score":         c["score"],
                        "regime":        c["regime"],
                        "vwap":          c["vwap"],
                        "z_score":       c["z_score"],
                        "roc_pct":       c["roc"],
                        "rel_vol":       c["rel_vol"],
                        "sigma_pct":     c["sigma"],
                        "market_closed": c.get("market_closed", False),
                        "signals": {
                            "above_vwap":        c["above_vwap"],
                            "momentum_positive": c["momentum_positive"],
                            "volume_spike":      c["volume_spike"],
                            "low_entropy":       c["low_entropy"],
                            "vol_expanding":     c["vol_expanding"],
                        },
                        "risk_metrics": {
                            "expected_price":       c["risk_metrics"]["expected_price"],
                            "prob_up":              c["risk_metrics"]["prob_up"],
                            "prob_down":            c["risk_metrics"]["prob_down"],
                            "worst_case_5pct":      c["risk_metrics"]["worst_case_5pct"],
                            "best_case_95pct":      c["risk_metrics"]["best_case_95pct"],
                            "worst_case_drop_pct":  c["risk_metrics"]["worst_case_drop_pct"],
                            "position_size_advice": c["risk_metrics"]["position_size_advice"],
                        },
                    }
                    for c in enriched
                ],
                "layer2_ranked": [
                    {
                        "symbol":       s,
                        "price":        round(filter_features[s]["price"], 2),
                        "filter_score": round(filter_features[s]["filter_score"], 4),
                        "rel_vol":      round(filter_features[s]["rel_vol"], 3),
                        "sigma_pct":    round(filter_features[s]["sigma"] * 100, 2),
                        "roc_pct":      round(filter_features[s]["roc"] * 100, 2),
                        "high":         round(filter_features[s].get("high", filter_features[s]["price"]), 2),
                        "low":          round(filter_features[s].get("low",  filter_features[s]["price"]), 2),
                    }
                    for s in top20_syms if s in filter_features
                ],
            }

            await cache.set("quant:screener:result", result, RESULT_TTL)

            elapsed = time.time() - ts_start
            await asyncio.sleep(max(0.5, PIPELINE_INTERVAL - elapsed))

        except Exception:
            await asyncio.sleep(PIPELINE_INTERVAL)
