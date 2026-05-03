"""
api/demo_routes.py
==================
Demo mode API — serves frozen snapshot + rich synthetic data.
No authentication required. No live API calls.
"""

import json
import math
import time
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import ORJSONResponse

demo_router = APIRouter(prefix="/demo", tags=["Demo"])

# Load snapshot
_SNAPSHOT_FILE = Path(__file__).parent.parent / "demo_snapshot.json"
_snap: dict = {}

def _load():
    global _snap
    try:
        if _SNAPSHOT_FILE.exists():
            _snap = json.loads(_SNAPSHOT_FILE.read_text())
    except Exception:
        _snap = {}

_load()

def _s(key, default=None):
    return _snap.get(key, default)

# ── Synthetic data generators ─────────────────────────────────────────────────

SPOT = 24576.6
STRIKES = list(range(23500, 25600, 100))
ATM = 24600

def _make_exposures():
    """Generate realistic GEX/DEX/Vega/Theta per strike."""
    exps = []
    for s in STRIKES:
        dist = (s - ATM) / ATM
        gex  = round(800 * math.exp(-50 * dist**2) * (1 if s >= ATM else -0.6), 4)
        dex  = round(500 * math.exp(-30 * dist**2) * (1 if s >= ATM else -1), 3)
        vega = round(200 * math.exp(-40 * dist**2), 3)
        theta= round(-150 * math.exp(-40 * dist**2), 3)
        cg   = round(abs(gex) * 0.6, 4)
        pg   = round(abs(gex) * 0.4, 4)
        exps.append({
            "strike": s, "gex": gex, "dex": dex,
            "net_vega": vega, "net_theta": theta,
            "call_gamma": cg, "put_gamma": pg,
        })
    return exps

def _make_smile():
    """Generate IV smile curve."""
    smile = []
    for s in STRIKES:
        m = s / ATM
        call_iv = round(18.5 + 8 * (m - 1)**2 - 2 * (m - 1), 2)
        put_iv  = round(19.0 + 10 * (m - 1)**2 + 1 * (m - 1), 2)
        smile.append({
            "strike": s,
            "call_iv": max(8, call_iv),
            "put_iv":  max(8, put_iv),
            "moneyness": round(m, 4),
        })
    return smile

def _make_gex_history():
    """Generate GEX time series."""
    now = time.time()
    hist = []
    for i in range(60):
        t = now - (60 - i) * 60
        gex = round(1200 + 300 * math.sin(i * 0.2) + i * 5, 2)
        dex = round(350 + 100 * math.cos(i * 0.15), 2)
        hist.append({"ts": t, "gex": gex, "dex": dex, "spot": round(SPOT + i * 2, 2)})
    return hist

def _make_iv_history():
    """Generate IV time series."""
    now = time.time()
    hist = []
    for i in range(60):
        t = now - (60 - i) * 60
        iv = round(18.5 + 2 * math.sin(i * 0.3), 2)
        hist.append({"ts": t, "iv": iv})
    return hist

def _make_oi_flow():
    """Generate OI flow bars."""
    now = time.time()
    flow = []
    for i in range(30):
        t = now - (30 - i) * 300
        flow.append({
            "ts": t,
            "call_oi_change": int(50000 * math.sin(i * 0.4)),
            "put_oi_change":  int(40000 * math.cos(i * 0.3)),
            "net_flow": int(10000 * math.sin(i * 0.5)),
        })
    return flow

# ── Endpoints ─────────────────────────────────────────────────────────────────

@demo_router.get("/health")
async def demo_health():
    return ORJSONResponse({
        "status": "ok", "demo_mode": True,
        "feed_running": True, "feed_subscriptions": 7,
        "tick_count": 12345, "nifty_ltp_from_ws": SPOT,
        "redis": True, "connections": 1, "timestamp": time.time(),
    })


@demo_router.get("/option-chain")
async def demo_option_chain(symbol: str = "NIFTY", expiry: str = None):
    # Always use synthetic data for demo — snapshot structure may differ from component expectations
    rows = []
    for s in STRIKES[5:-5]:
        dist = abs(s - ATM) / 100
        moneyness = s / ATM
        # Call delta: ~0.5 at ATM, approaches 1 deep ITM, 0 far OTM
        call_delta = round(max(0.01, min(0.99, 0.5 + (ATM - s) / (ATM * 0.15))), 3)
        put_delta  = round(call_delta - 1, 3)
        call_ltp   = round(max(0.5, 200 * math.exp(-0.15 * dist)), 2)
        put_ltp    = round(max(0.5, 200 * math.exp(-0.15 * dist)), 2)
        gamma      = round(0.002 * math.exp(-0.1 * dist), 4)
        theta      = round(-8 * math.exp(-0.1 * dist), 2)
        vega       = round(15 * math.exp(-0.1 * dist), 2)
        call_iv    = round(18 + dist * 0.5, 2)
        put_iv     = round(19 + dist * 0.6, 2)

        rows.append({
            "strike": s, "is_atm": s == ATM,
            "call": {
                "ltp": call_ltp, "oi": int(500000 * math.exp(-0.1*dist)),
                "oi_change": int(10000 * math.sin(dist)),
                "oi_change_pct": round(2.0 * math.sin(dist), 2),
                "volume": int(50000 * math.exp(-0.1*dist)),
                "iv": call_iv,
                "greeks": {"delta": call_delta, "gamma": gamma, "theta": theta, "vega": vega, "rho": 0.01},
                "delta": call_delta, "gamma": gamma, "theta": theta, "vega": vega,
                "security_id": str(40000 + s), "option_type": "CE",
                "trading_symbol": f"NIFTY{s}CE", "expiry": "2026-04-24",
                "open": round(call_ltp*0.95, 2), "high": round(call_ltp*1.1, 2),
                "low": round(call_ltp*0.9, 2), "close": round(call_ltp*0.98, 2),
                "prev_close": round(call_ltp*0.98, 2),
                "bid": round(call_ltp-0.5, 2), "ask": round(call_ltp+0.5, 2),
                "bid_qty": 150, "ask_qty": 200,
                "top_bid_price": round(call_ltp-0.5, 2), "top_ask_price": round(call_ltp+0.5, 2),
                "top_bid_quantity": 150, "top_ask_quantity": 200,
                "bid_ask_spread": 1.0, "vwap": round(call_ltp*1.01, 2),
            },
            "put": {
                "ltp": put_ltp, "oi": int(600000 * math.exp(-0.1*dist)),
                "oi_change": int(-8000 * math.sin(dist)),
                "oi_change_pct": round(-1.5 * math.sin(dist), 2),
                "volume": int(45000 * math.exp(-0.1*dist)),
                "iv": put_iv,
                "greeks": {"delta": put_delta, "gamma": gamma, "theta": theta, "vega": vega, "rho": -0.01},
                "delta": put_delta, "gamma": gamma, "theta": theta, "vega": vega,
                "security_id": str(50000 + s), "option_type": "PE",
                "trading_symbol": f"NIFTY{s}PE", "expiry": "2026-04-24",
                "open": round(put_ltp*0.95, 2), "high": round(put_ltp*1.1, 2),
                "low": round(put_ltp*0.9, 2), "close": round(put_ltp*0.98, 2),
                "prev_close": round(put_ltp*0.98, 2),
                "bid": round(put_ltp-0.5, 2), "ask": round(put_ltp+0.5, 2),
                "bid_qty": 180, "ask_qty": 220,
                "top_bid_price": round(put_ltp-0.5, 2), "top_ask_price": round(put_ltp+0.5, 2),
                "top_bid_quantity": 180, "top_ask_quantity": 220,
                "bid_ask_spread": 1.0, "vwap": round(put_ltp*1.01, 2),
            },
            "pcr_oi": round(600000 / max(500000, 1), 3),
            "pcr_volume": round(45000 / max(50000, 1), 3),
        })
    return ORJSONResponse({
        "symbol": "NIFTY", "expiry": "2026-04-24",
        "spot_price": SPOT, "atm_strike": ATM,
        "futures_price": round(SPOT + 45, 2),
        "rows": rows,
        "expiries": ["2026-04-24", "2026-05-01", "2026-05-29"],
    })


@demo_router.get("/expiries")
async def demo_expiries(symbol: str = "NIFTY"):
    return ORJSONResponse({"symbol": symbol, "expiries": ["2026-04-24", "2026-05-01", "2026-05-29"]})


@demo_router.get("/greeks-exposure")
async def demo_greeks(symbol: str = "NIFTY"):
    exps = _make_exposures()
    return ORJSONResponse({
        "symbol": "NIFTY", "expiry": "2026-04-24", "spot_price": SPOT,
        "exposures": exps,
        "total_gex": 1533.97, "total_dex": 172.52,
        "total_vega": 4701.73, "total_theta": -43869.42,
        "gamma_flip_level": 24300, "call_wall": 25000, "put_wall": 24000,
    })


@demo_router.get("/iv-analytics")
async def demo_iv(symbol: str = "NIFTY"):
    smile = _make_smile()
    return ORJSONResponse({
        "symbol": "NIFTY", "expiry": "2026-04-24", "spot_price": SPOT,
        "smile": smile,
        "current_iv": 23.46, "avg_iv": 26.72,
        "iv_rank": 97.5, "iv_percentile": 89.3,
        "historical_vol_30d": 0.04, "historical_vol_7d": 0.02,
        "iv_rv_spread": 23.42,
        "term_structure": [
            {"dte": 3, "atm_iv": 23.46},
            {"dte": 10, "atm_iv": 21.2},
            {"dte": 30, "atm_iv": 19.8},
            {"dte": 60, "atm_iv": 18.5},
        ],
    })


@demo_router.get("/market-summary")
async def demo_summary(symbol: str = "NIFTY"):
    summary = _s("summary_nifty")
    if summary and summary.get("spot_price"):
        return ORJSONResponse(summary)
    return ORJSONResponse({
        "symbol": "NIFTY", "spot_price": SPOT,
        "day_change": 45.5, "day_change_pct": 0.19,
        "pcr_oi": 0.99, "pcr_volume": 0.88,
        "max_pain": 24400, "atm_iv": 23.46,
        "total_call_oi": 74800000, "total_put_oi": 78600000,
        "timestamp": time.time(),
    })


@demo_router.get("/indices")
async def demo_indices():
    indices = _s("indices")
    if indices and len(indices) >= 4:
        return ORJSONResponse(indices)
    return ORJSONResponse([
        {"symbol": "BANKNIFTY",  "ltp": 56582.35, "change": 382.0,  "change_pct": 0.68},
        {"symbol": "FINNIFTY",   "ltp": 26537.10, "change": -45.0,  "change_pct": -0.17},
        {"symbol": "MIDCPNIFTY", "ltp": 13807.25, "change": 30.0,   "change_pct": 0.22},
        {"symbol": "SENSEX",     "ltp": 78520.30, "change": 200.0,  "change_pct": 0.26},
        {"symbol": "INDIAVIX",   "ltp": 18.79,    "change": -0.3,   "change_pct": -1.57},
        {"symbol": "GIFTNIFTY",  "ltp": 24702.50, "change": 55.0,   "change_pct": 0.22},
    ])


@demo_router.get("/quote")
async def demo_quote(symbol: str = "NIFTY"):
    return ORJSONResponse({
        "symbol": symbol, "ltp": SPOT,
        "change": 45.5, "change_pct": 0.19,
        "open": 24531.0, "high": 24612.0, "low": 24498.0, "close": 24531.1,
        "timestamp": time.time(),
    })


@demo_router.get("/long-term-stocks")
async def demo_screener(min_score: int = 0, limit: int = 200):
    screener = _s("screener_summary", {})
    all_stocks = screener.get("all_stocks", [])
    if not all_stocks:
        all_stocks = screener.get("top_stocks", [])
    filtered = [s for s in all_stocks if (s.get("score") or 0) >= min_score]
    return ORJSONResponse({
        "computing": False, "waiting": False,
        "stocks": filtered[:limit],
        "grouped": screener.get("grouped", {}),
        "insights": screener.get("insights", {}),
        "top_picks": screener.get("top_picks", []),
        "market_context": screener.get("market_context", {
            "market_regime": "SIDEWAYS", "breadth_pct": 35.8,
            "top_sector": "METALS", "weak_sector": "HOSPITALITY",
            "avg_rs": 1.53, "avg_confidence": 77.0,
        }),
        "pipeline_status": {"status": "DONE", "stage": "Demo snapshot", "message": "", "progress": 100},
        "db_stats": {"total_stocks": 284, "buy_signals": 49, "candles_cached": 340000},
        "last_updated": "Demo Data",
        "total_stocks": len(all_stocks),
        "buy_signals": screener.get("buy_signals", 49),
        "live_prices_available": True,
        "timestamp": time.time(),
    })


@demo_router.get("/stocks/live-prices")
async def demo_live_prices():
    live = _s("live_prices", {})
    return ORJSONResponse({
        "available": True, "market_open": False,
        "prices": live, "fetched_at": time.time(), "count": len(live),
    })


@demo_router.get("/stock/{symbol}/simulate")
async def demo_simulate(symbol: str, investment: float = 100000, horizon: int = 126):
    price = 1000.0
    exp_ret = 0.12
    return ORJSONResponse({
        "symbol": symbol, "investment": investment, "horizon_days": horizon,
        "horizon_label": "6M" if horizon == 126 else "3M" if horizon == 63 else "1Y",
        "shares": round(investment / price, 2),
        "expected_value": round(investment * (1 + exp_ret), 0),
        "median_value": round(investment * (1 + exp_ret * 0.9), 0),
        "best_case": round(investment * 1.35, 0),
        "worst_case": round(investment * 0.88, 0),
        "prob_profit": 72.5,
        "expected_return": round(exp_ret * 100, 2),
        "median_return": round(exp_ret * 90, 2),
        "best_return": 35.0, "worst_return": -12.0,
        "regime": "TRENDING", "from_cache": True, "status": "OK",
    })


@demo_router.get("/stock/{symbol}/fundamentals")
async def demo_fundamentals(symbol: str):
    return ORJSONResponse({
        "symbol": symbol, "status": "OK",
        "fetched_at": time.time(),
        "info": {"name": symbol, "sector": "Diversified", "industry": "Large Cap"},
        "ratios": {"pe_ratio": 22.5, "pb_ratio": 3.2, "roce": 18.5, "roe": 15.2,
                   "debt_equity": 0.3, "dividend_yield": 1.2, "market_cap_cr": 85000},
        "growth": {"revenue_growth_yoy": 12.5, "profit_growth_yoy": 18.3,
                   "revenue_cagr_3y": 14.2, "profit_cagr_3y": 16.8},
        "quarterly": [
            {"period": "Mar 2026", "revenue": 12500, "net_profit": 1850, "opm_pct": 22},
            {"period": "Dec 2025", "revenue": 11800, "net_profit": 1720, "opm_pct": 21},
            {"period": "Sep 2025", "revenue": 11200, "net_profit": 1650, "opm_pct": 20},
        ],
        "annual": [
            {"year": "FY2026", "revenue": 48000, "net_profit": 7200, "opm_pct": 22},
            {"year": "FY2025", "revenue": 42000, "net_profit": 6100, "opm_pct": 20},
            {"year": "FY2024", "revenue": 37000, "net_profit": 5200, "opm_pct": 19},
        ],
    })


@demo_router.get("/intelligence")
async def demo_intelligence(symbol: str = "NIFTY"):
    gex_hist = _make_gex_history()
    iv_hist  = _make_iv_history()

    # Build timeseries matching IntelData.TSSnapshot exactly
    timeseries = []
    for i, (g, iv) in enumerate(zip(gex_hist, iv_hist)):
        timeseries.append({
            "ts": g["ts"], "gex": g["gex"], "dex": g["dex"],
            "iv": iv["iv"], "total_oi": int(8500000 + i * 10000),
            "delta_gex": round(g["gex"] * 0.01, 4),
            "delta_oi": int(50000 * math.sin(i * 0.3)),
            "delta_iv": round(0.1 * math.sin(i * 0.2), 3),
            "spot": g["spot"],
        })

    # OI classification table
    oi_table = []
    for s in STRIKES[8:18]:
        dist = abs(s - ATM) / 100
        oi_table.append({
            "strike": s, "type": "CE" if s >= ATM else "PE",
            "classification": "LONG_BUILDUP" if s >= ATM else "SHORT_BUILDUP",
            "color": "#00c853" if s >= ATM else "#ff1744",
            "oi": int(500000 * math.exp(-0.1 * dist)),
            "oi_change": int(50000 * math.sin(dist)),
            "ltp": round(max(0.5, 150 * math.exp(-0.15 * dist)), 2),
            "iv": round(18 + dist * 0.5, 2),
            "delta": round(0.5 - dist * 0.05, 3),
            "volume": int(30000 * math.exp(-0.1 * dist)),
        })

    # Heatmap strikes
    heatmap_strikes = []
    max_oi = 800000
    for s in STRIKES[5:-5]:
        dist = abs(s - ATM) / 100
        call_oi = int(500000 * math.exp(-0.08 * dist))
        put_oi  = int(600000 * math.exp(-0.08 * dist))
        heatmap_strikes.append({
            "strike": s, "dist_pct": round((s - SPOT) / SPOT * 100, 2),
            "is_atm": s == ATM,
            "call_oi": call_oi, "put_oi": put_oi,
            "call_oi_pct": round(call_oi / max_oi * 100, 1),
            "put_oi_pct":  round(put_oi  / max_oi * 100, 1),
            "call_iv": round(18 + dist * 0.5, 2),
            "put_iv":  round(19 + dist * 0.6, 2),
            "iv_skew": round(1 + dist * 0.1, 3),
            "pcr": round(put_oi / call_oi, 3) if call_oi > 0 else 1.0,
        })

    return ORJSONResponse({
        "symbol": "NIFTY",
        "spot": SPOT,
        "timestamp": time.time(),
        "timeseries": timeseries,
        "oi_classification": {
            "table": oi_table,
            "flow_counts": {"LONG_BUILDUP": 8, "SHORT_BUILDUP": 5, "SHORT_COVERING": 3, "LONG_UNWINDING": 2, "NEUTRAL": 4},
            "dominant": oi_table[:3],
        },
        "expected_move": {
            "spot": SPOT, "iv_pct": 18.5, "dte": 3,
            "expected_move": 350.0,
            "upper_1sd": round(SPOT + 350, 2), "lower_1sd": round(SPOT - 350, 2),
            "upper_2sd": round(SPOT + 700, 2), "lower_2sd": round(SPOT - 700, 2),
            "upper_pct": 1.42, "lower_pct": -1.42,
            "prob_in_range": 68.2, "status": "ok",
        },
        "iv_regime": {
            "regime": "HIGH_IV", "signal": "SELL PREMIUM",
            "description": "IV Rank 97.5 — options are expensive. Favor selling strategies.",
            "color": "#ff9100",
            "iv_pct": 23.46, "hv_pct": 14.2,
            "iv_rank": 97.5, "iv_hv_ratio": 1.65,
        },
        "smart_signal": {
            "signal": "RANGE_BOUND", "signal_color": "#ffcc00",
            "confidence": 72, "score": 6.5,
            "reasons": [
                "GEX positive — dealers long gamma (stabilizing)",
                "Spot between put wall (24,000) and call wall (25,000)",
                "IV elevated — sell premium bias",
                "PCR 0.99 — neutral positioning",
            ],
        },
        "alerts": [
            {"ts": time.time() - 3600, "type": "GEX_ROLLUP", "symbol": "NIFTY",
             "message": "GEX crossed above 0 at 24,500 — Stabilizing", "severity": "INFO"},
            {"ts": time.time() - 7200, "type": "VWAP_CROSS", "symbol": "NIFTY",
             "message": "Price crossed VWAP (24,390) — Bearish bias", "severity": "WARNING"},
            {"ts": time.time() - 10800, "type": "OI_BUILDUP", "symbol": "NIFTY",
             "message": "Heavy PUT writing at 24,000 — Strong support", "severity": "INFO"},
        ],
        "heatmap": {
            "strikes": heatmap_strikes,
            "spot": SPOT, "max_oi": max_oi,
            "count": len(heatmap_strikes), "status": "ok",
        },
        "summary": {
            "gex": 1533.97, "delta_gex": 0.042,
            "iv": 23.46, "hv": 14.2,
            "iv_rank": 97.5, "pcr": 0.99,
            "max_pain": 24400, "call_wall": 25000, "put_wall": 24000,
        },
    })


@demo_router.get("/guide")
async def demo_guide():
    import urllib.request
    try:
        resp = urllib.request.urlopen("http://localhost:8000/api/guide", timeout=3)
        return ORJSONResponse(json.loads(resp.read()))
    except Exception:
        return ORJSONResponse({"sections": []})


@demo_router.get("/news")
async def demo_news(category: str = None, sentiment: str = None):
    return ORJSONResponse({
        "articles": [
            {"title": "Nifty closes above 24,500 for third consecutive session",
             "sentiment": "POSITIVE", "category": "MARKET", "source": "Demo",
             "published_at": time.time() - 1800,
             "summary": "Indian benchmark indices closed higher led by IT and banking stocks amid positive global cues."},
            {"title": "RBI holds repo rate at 6.5%, maintains accommodative stance",
             "sentiment": "NEUTRAL", "category": "ECONOMY", "source": "Demo",
             "published_at": time.time() - 5400,
             "summary": "Reserve Bank of India kept interest rates unchanged for the sixth consecutive meeting."},
            {"title": "FII net buyers for 8th straight session, pump ₹4,200 Cr",
             "sentiment": "POSITIVE", "category": "MARKET", "source": "Demo",
             "published_at": time.time() - 9000,
             "summary": "Foreign institutional investors continue to show confidence in Indian equities."},
            {"title": "Crude oil falls 2% on demand concerns, positive for India",
             "sentiment": "POSITIVE", "category": "COMMODITY", "source": "Demo",
             "published_at": time.time() - 14400,
             "summary": "Brent crude dropped below $82/barrel, easing inflation concerns for oil-importing nations."},
            {"title": "IT sector faces headwinds from US slowdown fears",
             "sentiment": "NEGATIVE", "category": "SECTOR", "source": "Demo",
             "published_at": time.time() - 18000,
             "summary": "Technology stocks under pressure as US recession fears weigh on outsourcing demand outlook."},
        ]
    })


@demo_router.get("/historical")
async def demo_historical(security_id: str = "13", exchange_segment: str = "IDX_I", interval: int = 60):
    n = 60
    base = SPOT
    closes = [round(base + 300 * math.sin(i * 0.15) + i * 1.5, 2) for i in range(n)]
    opens  = [round(c - 12, 2) for c in closes]
    highs  = [round(c + 22, 2) for c in closes]
    lows   = [round(c - 22, 2) for c in closes]
    vols   = [int(80000 + 20000 * abs(math.sin(i * 0.4))) for i in range(n)]
    now    = int(time.time())
    step   = interval * 60
    timestamps = [now - (n - i) * step for i in range(n)]
    return ORJSONResponse({
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": vols, "timestamp": timestamps,
    })


@demo_router.post("/strategy/analyze")
async def demo_strategy(legs: list = None):
    return ORJSONResponse({
        "net_premium": -185.0, "net_delta": 0.08,
        "net_gamma": 0.001, "net_theta": -12.5, "net_vega": 38.0,
        "payoff_curve": [{"spot": 23800 + i*100, "pnl": round((i-8)*120 - 185, 2)} for i in range(17)],
        "max_profit": 1815.0, "max_loss": -2185.0,
        "breakeven": [24185.0, 24815.0],
    })


@demo_router.get("/screener")
async def demo_screener_old():
    return ORJSONResponse({"computing": False, "stocks": []})
