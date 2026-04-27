import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from config import get_settings
from api.dhan_client import (
    get_dhan_client,
    get_ws_client,
    DhanAPIClient,
    INDEX_SECURITY_IDS,
    INDEX_LOT_SIZES,
)
from api.websocket_manager import get_connection_manager, get_market_state
from core.redis_cache import (
    get_cache,
    TTL_OPTION_CHAIN, TTL_GREEKS, TTL_IV_ANALYTICS, TTL_MARKET_SUMMARY,
    TTL_EXPIRIES, TTL_IV_HISTORY, TTL_GEX_HISTORY,
)
from core.demo_data import generate_demo_option_chain, generate_demo_quote, is_demo_mode, _generate_expiries
from core.analytics_processor import (
    process_option_chain,
    compute_greeks_exposure,
    compute_iv_analytics,
    compute_market_summary,
    _iv_history,
)
from models.schemas import (
    OptionChainResponse,
    GreeksExposureResponse,
    IVAnalyticsResponse,
    MarketSummary,
    StrategyAnalysis,
    StrategyLeg,
    PayoffPoint,
    Greeks,
)

from api.quant_routes import quant_router
from api.news_routes import news_router
from api.intelligence_routes import intelligence_router, record_intelligence_snapshot
from api.livetv_routes import livetv_router
from api.guide_routes import guide_router
from api.screener_routes import screener_router
from api.demo_routes import demo_router
from api.ml_routes import ml_router
from stocks.routes import stocks_router
from stocks.scheduler import run_stock_scheduler
from stocks.live_prices import run_live_price_loop
from token_manager import run_token_refresh_loop
from features.regime   import push_price
from features.gex      import record_exposure_snapshot
from features.oi_flow  import ingest_chain_for_oi
from features.vwap     import push_vwap_tick, get_vwap_engine
from features.volatility import get_vol_surface
from features.ml_signals import ingest_chain_for_ml, run_ml_inference, should_run_inference, update_signals
from services.alert_engine import get_alert_engine
from auth import auth_router, require_auth, optional_auth

# Silence all third-party loggers — only show CRITICAL errors
logging.basicConfig(level=logging.CRITICAL)
for noisy in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi", "asyncio", "aiohttp"):
    logging.getLogger(noisy).setLevel(logging.CRITICAL)

settings = get_settings()
RISK_FREE_RATE = settings.RISK_FREE_RATE

# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    cache = get_cache()
    await cache.connect()

    # Flush stale cached exposure/IV data that may have wrong normalization
    # This forces fresh computation on first refresh
    if cache.available:
        for sym in ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"]:
            await cache.delete(cache.key_exposure(sym))
            await cache.delete(cache.key_iv(sym))
            await cache.delete(cache.key_summary(sym))

    # Restore IV history from Redis so IV Rank works immediately after restart
    for sym in ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"]:
        stored = await cache.ts_get_all(cache.key_iv_history(sym))
        if stored:
            from collections import deque as _deque
            # Stored entries are {"ts": float, "iv": float} — extract just the IV values
            iv_vals = [
                e["iv"] if isinstance(e, dict) else float(e)
                for e in stored
                if (e["iv"] if isinstance(e, dict) else float(e)) > 0
            ]
            if iv_vals:
                _iv_history[sym] = _deque(iv_vals, maxlen=252)

    demo = is_demo_mode()
    if not demo:
        # ── Token: fetch fresh token BEFORE starting WS ───────────────────────
        # Both APP and SELF tokens work for WS + REST.
        # Fetch synchronously here so WS always starts with a valid token.
        # token_manager background loop handles auto-refresh every ~23.5h.
        from token_manager import get_access_token as _get_token, _inject_token
        try:
            _token = await _get_token()
            _inject_token(_token)
        except Exception:
            # Fallback: use whatever is in .env
            _inject_token(settings.DHAN_ACCESS_TOKEN)

        # Start background token refresh loop (handles expiry + WS reconnect)
        asyncio.create_task(run_token_refresh_loop())

    if not demo:
        ws_client = get_ws_client()
        ws_client.add_callback(_handle_dhan_feed)
        from api.dhan_client import INDEX_SECURITY_IDS_INT, FeedRequestCode, ExchangeSegment

        # Subscribe all 7 indices with QUOTE mode (RequestCode=17)
        ws_client.subscribe(
            instruments=[
                {"exchange_segment": ExchangeSegment.IDX_I, "security_id": str(sid)}
                for sid in INDEX_SECURITY_IDS_INT.values()
            ],
            request_code=FeedRequestCode.QUOTE,
        )

        asyncio.create_task(ws_client.connect_and_stream())

    alert_engine = get_alert_engine()
    alert_engine.add_callback(_broadcast_alert)

    # Wrap refresh task in a watchdog — restarts if it crashes
    async def _refresh_watchdog():
        while True:
            try:
                await _periodic_option_chain_refresh()
            except Exception:
                await asyncio.sleep(2)

    asyncio.create_task(_refresh_watchdog())

    # NOTE: Quant screener workers are disabled to avoid competing with
    # the option chain API rate limits. The screener tab will show
    # "Pipeline computing" until workers are re-enabled.
    # To re-enable: uncomment the lines below and rebuild.
    # if not is_demo_mode():
    #     from quant.instrument_loader import load_instrument_ids
    #     from quant.data_worker import run_quant_data_worker
    #     from quant.pipeline_worker import run_pipeline_worker
    #     asyncio.create_task(load_instrument_ids())
    #     asyncio.create_task(run_quant_data_worker())
    #     asyncio.create_task(run_pipeline_worker())

    # Stock engine — BATCH MODE ONLY (runs after market close)
    # Completely isolated from options pipeline — no shared rate limits
    if not is_demo_mode():
        asyncio.create_task(run_stock_scheduler())
        # Live stock prices during market hours (1 batch call/60s for all 226 stocks)
        asyncio.create_task(run_live_price_loop())

    # Pre-warm: fetch NIFTY chain + populate prev_close for all indices
    async def _prewarm():
        # Fetch NIFTY chain
        await _refresh_option_chain("NIFTY", spot_override=None)
        # Fetch OHLC for all indices to populate prev_close (for correct day change)
        try:
            dhan = get_dhan_client()
            state = get_market_state()
            from api.dhan_client import INDEX_SECURITY_IDS_INT
            for sym, sid in INDEX_SECURITY_IDS_INT.items():
                try:
                    quote_resp = await dhan.get_market_quote([sid], "IDX_I")
                    quote_data = quote_resp.get("data", {}).get("IDX_I", {})
                    q_full     = quote_data.get(str(sid)) or quote_data.get(sid) or {}
                    ohlc       = q_full.get("ohlc") or {}
                    prev_close = float(ohlc.get("close") or 0)
                    if prev_close > 0:
                        state.set_sync(f"prev_close:{sym}", prev_close)
                except Exception:
                    pass
        except Exception:
            pass
    asyncio.create_task(_prewarm())

    yield

    if not demo:
        get_ws_client().stop()
    await get_dhan_client().close()
    await cache.disconnect()


# ─── App Setup ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Options Analytics Platform",
    version="2.0.0",
    description="Bloomberg Terminal-grade Options Analytics for Indian Markets",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

cors_origins = settings.CORS_ORIGINS.split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount quant feature routes
app.include_router(quant_router, prefix="/api")
# Mount auth routes (public — no auth required)
app.include_router(auth_router, prefix="/api")
# Mount news routes (public — no auth required for news)
app.include_router(news_router, prefix="/api")
# Mount intelligence routes
app.include_router(intelligence_router, prefix="/api")
# Mount live TV routes (public — no auth required)
app.include_router(livetv_router, prefix="/api")
# Mount guide routes (public — no auth required)
app.include_router(guide_router, prefix="/api")
# Mount screener routes (requires auth)
app.include_router(screener_router, prefix="/api")
# Mount stock engine routes (public — no auth for long-term analysis)
app.include_router(stocks_router, prefix="/api")
# Mount demo routes (public — no auth, serves frozen snapshot data)
app.include_router(demo_router, prefix="/api")
# Mount ML signal routes (requires auth)
app.include_router(ml_router, prefix="/api")
# Mount admin routes (separate auth, separate prefix)
from admin.admin_auth import admin_auth_router
from admin.admin_routes import admin_router as _admin_router
app.include_router(admin_auth_router)
app.include_router(_admin_router)


# ─── Background Tasks ─────────────────────────────────────────────────────────

async def _broadcast_alert(alert):
    """Broadcast alert to all connected WebSocket clients."""
    manager = get_connection_manager()
    await manager.broadcast({
        "type":    "alert",
        "data":    alert.to_dict(),
        "timestamp": time.time(),
    })


async def _handle_dhan_feed(tick_data: dict):
    """
    Process Dhan v2 binary feed packets.

    Packet types handled:
      type=ticker    (code 2): LTP only — stocks
      type=quote     (code 4): LTP + open/high/low/close/volume/ATP — indices (QUOTE mode)
      type=prev_close(code 6): previous day close — auto-sent on subscribe (FREE!)
      type=oi        (code 5): open interest

    IMPORTANT: SID numbers overlap between segments.
    SID=13 is NIFTY in IDX_I but ABB in NSE_EQ. Always check exchange_segment.
    """
    manager = get_connection_manager()
    state   = get_market_state()

    security_id  = str(tick_data.get("security_id", ""))
    ltp          = float(tick_data.get("LTP", tick_data.get("ltp", 0)) or 0)
    volume       = int(tick_data.get("volume", 0))
    oi           = int(tick_data.get("OI", tick_data.get("oi", 0)))
    xch_code     = tick_data.get("exchange_segment", -1)
    packet_type  = tick_data.get("type", "ticker")

    # Track tick count for debugging
    tick_count = state.get_sync("_tick_count") or 0
    state.set_sync("_tick_count", tick_count + 1)
    state.set_sync("_last_tick_ts", time.time())
    state.set_sync("_last_tick_raw", {
        "sid": security_id, "ltp": ltp,
        "xch": xch_code, "type": packet_type,
    })

    from api.dhan_client import INDEX_SECURITY_IDS_INT, EXCHANGE_CODE_TO_STR
    xch_str  = EXCHANGE_CODE_TO_STR.get(xch_code, "")
    is_index = (xch_str == "IDX_I" or xch_code == 0)

    # ── Prev Close packet (code 6) — auto-sent by Dhan on subscribe ───────────
    # Gives previous day close for FREE — no REST call needed
    if packet_type == "prev_close":
        prev_close_val = float(tick_data.get("prev_close", 0) or 0)
        if prev_close_val > 0 and is_index and security_id:
            for idx_sym, idx_sid in INDEX_SECURITY_IDS_INT.items():
                if security_id == str(idx_sid):
                    state.set_sync(f"prev_close:{idx_sym}", prev_close_val)
                    break
        return   # no broadcast needed

    if not security_id or ltp <= 0:
        return

    # ── Index ticks (IDX_I segment) ───────────────────────────────────────────
    sym = None
    if is_index:
        state.set_sync(f"ltp:{security_id}", ltp)
        for idx_sym, idx_sid in INDEX_SECURITY_IDS_INT.items():
            if security_id == str(idx_sid):
                sym = idx_sym
                push_vwap_tick(sym, ltp, volume or 100)
                push_price(sym, ltp)
                engine   = get_vwap_engine(sym)
                prev_ltp = state.get_sync(f"prev_ltp:{sym}")
                if prev_ltp and engine.vwap > 0:
                    await get_alert_engine().check_vwap_cross(sym, prev_ltp, ltp, engine.vwap)
                state.set_sync(f"prev_ltp:{sym}", ltp)

                # Quote packet (code 4) — extract OHLC for day change
                if packet_type == "quote":
                    day_open = float(tick_data.get("open",  0) or 0)
                    day_high = float(tick_data.get("high",  0) or 0)
                    day_low  = float(tick_data.get("low",   0) or 0)
                    atp      = float(tick_data.get("avg_price", 0) or 0)
                    if day_open > 0:
                        state.set_sync(f"ohlc:{sym}", {
                            "open": day_open, "high": day_high,
                            "low": day_low, "ltp": ltp,
                            "volume": volume, "atp": atp,
                        })
                    # Update summary with live day change
                    prev_close = state.get_sync(f"prev_close:{sym}") or 0
                    if prev_close > 0:
                        day_change     = round(ltp - prev_close, 2)
                        day_change_pct = round(day_change / prev_close * 100, 2)
                        existing = state.get_sync(f"summary:{sym}") or {}
                        if isinstance(existing, dict):
                            existing.update({
                                "spot_price":     ltp,
                                "day_change":     day_change,
                                "day_change_pct": day_change_pct,
                            })
                            state.set_sync(f"summary:{sym}", existing)
                break

    # ── Stock ticks (NSE_EQ segment) ──────────────────────────────────────────
    # Stocks are NOT subscribed to WS — this branch never runs.
    # Stock prices come from REST batch every 30s via run_live_price_loop().
    else:
        pass   # no-op — stocks use REST batch, not WS

    # ── Broadcast to all frontend WebSocket clients ───────────────────────────
    tick_msg: dict = {
        "type":        "tick",
        "security_id": security_id,
        "ltp":         ltp,
        "volume":      volume,
        "oi":          oi,
        "timestamp":   time.time(),
    }
    # Include OHLC + day change for index quote ticks — frontend uses directly
    if is_index and packet_type == "quote" and sym:
        tick_msg["open"] = float(tick_data.get("open", 0) or 0)
        tick_msg["high"] = float(tick_data.get("high", 0) or 0)
        tick_msg["low"]  = float(tick_data.get("low",  0) or 0)
        tick_msg["atp"]  = float(tick_data.get("avg_price", 0) or 0)
        prev_close = state.get_sync(f"prev_close:{sym}") or 0
        if prev_close > 0:
            tick_msg["prev_close"]     = prev_close
            tick_msg["day_change"]     = round(ltp - prev_close, 2)
            tick_msg["day_change_pct"] = round((ltp - prev_close) / prev_close * 100, 2)

    # Only broadcast index ticks — stock prices come from REST batch
    if is_index:
        await manager.broadcast(tick_msg)


def _redis_set_sync(key: str, value: str, ttl: int = 60) -> bool:
    """
    Synchronous Redis SET using raw socket — bypasses aioredis entirely.
    Used in thread pool to avoid blocking the event loop on broken connections.
    """
    import socket as _sock
    try:
        s = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect(("redis", 6379))
        # RESP protocol: SETEX key ttl value
        cmd = f"*4\r\n$5\r\nSETEX\r\n${len(key)}\r\n{key}\r\n${len(str(ttl))}\r\n{ttl}\r\n${len(value)}\r\n{value}\r\n"
        s.sendall(cmd.encode())
        resp = s.recv(64)
        s.close()
        return resp.startswith(b"+OK")
    except Exception:
        return False


async def _periodic_option_chain_refresh():
    """
    Refresh NIFTY option chain at maximum allowed rate — 1 req/3s per Dhan docs.
    The rate limiter's token bucket (rate=0.33) enforces the 3s minimum.
    No artificial sleep — the rate limiter IS the throttle.

    Optimisations to minimise latency per cycle:
      - Spot price: use WebSocket tick cache (no extra API call)
      - Expiries: cached after first fetch, refreshed every 5 min
      - Day change: cached after first fetch, refreshed every 60s
      - Only the option chain call itself hits the API each cycle
    """
    import pytz
    from datetime import datetime

    _expiry_cache: dict = {}
    _expiry_fetched_at: float = 0.0
    _prev_close_fetched_at: float = 0.0
    _cycle: int = 0

    # Dedicated Redis connection for the refresh loop — avoids shared connection issues
    import redis.asyncio as _aioredis
    from config import get_settings as _gs
    _s = _gs()
    _redis_url = f"redis://{_s.REDIS_HOST}:{_s.REDIS_PORT}/{_s.REDIS_DB}"
    _loop_redis: Optional[_aioredis.Redis] = None

    async def _get_loop_redis():
        nonlocal _loop_redis
        try:
            if _loop_redis is None:
                _loop_redis = _aioredis.from_url(
                    _redis_url, encoding="utf-8", decode_responses=True,
                    socket_timeout=2, socket_connect_timeout=2,
                )
            await _loop_redis.ping()
            return _loop_redis
        except Exception:
            try:
                if _loop_redis:
                    await _loop_redis.aclose()
            except Exception:
                pass
            _loop_redis = _aioredis.from_url(
                _redis_url, encoding="utf-8", decode_responses=True,
                socket_timeout=2, socket_connect_timeout=2,
            )
            return _loop_redis

    while True:
        _cycle += 1
        # Heartbeat — use thread pool to avoid blocking event loop on Redis hang
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _redis_set_sync, "chain:NIFTY:heartbeat",
                                       f'{{"cycle":{_cycle},"ts":{time.time():.3f}}}', 30)
        except Exception:
            pass

        try:
            ist = pytz.timezone("Asia/Kolkata")
            now = datetime.now(ist)
            mins = now.hour * 60 + now.minute
            market_open = now.weekday() < 5 and 9 * 60 + 15 <= mins <= 15 * 60 + 30

            if not market_open:
                # Market closed — serve cached data, refresh TTL every 60s
                cache   = get_cache()
                state   = get_market_state()
                manager = get_connection_manager()

                cached_chain   = await state.get("chain:NIFTY")
                cached_summary = await state.get("summary:NIFTY")

                if cached_chain:
                    await cache.set(cache.key_chain("NIFTY"), cached_chain, TTL_OPTION_CHAIN)
                    await manager.broadcast({"type": "option_chain_update", "symbol": "NIFTY", "data": cached_chain, "timestamp": time.time(), "market_closed": True})
                if cached_summary:
                    await cache.set(cache.key_summary("NIFTY"), cached_summary, TTL_MARKET_SUMMARY)
                    await manager.broadcast({"type": "market_summary", "symbol": "NIFTY", "data": cached_summary, "timestamp": time.time(), "market_closed": True})

                if not cached_chain:
                    redis_chain = await cache.get(cache.key_chain("NIFTY"))
                    if redis_chain:
                        await state.set("chain:NIFTY", redis_chain)
                        await manager.broadcast({"type": "option_chain_update", "symbol": "NIFTY", "data": redis_chain, "timestamp": time.time(), "market_closed": True})

                await asyncio.sleep(60)
                continue

            if is_demo_mode():
                await _refresh_option_chain("NIFTY", spot_override=None)
                await asyncio.sleep(3)
                continue

            dhan  = get_dhan_client()
            state = get_market_state()
            cache = get_cache()

            # ── 1. Spot price — use WebSocket tick cache (free, no API call) ──
            # Dhan WebSocket sends NIFTY ticks with security_id=13
            spot = state.get_sync("ltp:13") or 0.0

            # Fallback: use last known spot from cached chain (no API call — avoids hanging)
            if spot <= 0:
                _cached_for_spot = state.get_sync("chain:NIFTY") or {}
                if isinstance(_cached_for_spot, dict):
                    spot = float(_cached_for_spot.get("spot_price", 0) or 0)

            if spot <= 0:
                await asyncio.sleep(1)
                continue

            # ── 2. Expiries — cache for 5 minutes ─────────────────────────────
            now_ts = time.time()
            if not _expiry_cache.get("NIFTY") or now_ts - _expiry_fetched_at > 300:
                try:
                    expiries = await dhan.get_option_expiries("NIFTY")
                    if expiries:
                        _expiry_cache["NIFTY"] = expiries[0]
                        _expiry_fetched_at = now_ts
                        await state.set("expiries:NIFTY", expiries)
                        await cache.set(cache.key_expiries("NIFTY"), expiries, TTL_EXPIRIES)
                except Exception:
                    pass

            # Use cached expiry or fall back to state
            expiry = _expiry_cache.get("NIFTY")
            if not expiry:
                cached_exp = await state.get("expiries:NIFTY")
                expiry = cached_exp[0] if cached_exp else None
            if not expiry:
                await asyncio.sleep(1)
                continue

            # ── 3. Option chain — THE main call, rate-limited to 1/3s ─────────
            # The rate limiter token bucket (rate=0.33) enforces the 3s gap.
            # No sleep needed — acquire() blocks until the token is available.
            raw_chain = await dhan.get_option_chain("NIFTY", expiry)

            if not raw_chain:
                await asyncio.sleep(3)
                continue

            oc = raw_chain.get("data", {}).get("oc", {})
            if not oc:
                await asyncio.sleep(3)
                continue

            # ── 4. Process and cache ───────────────────────────────────────────
            chain        = process_option_chain(raw_chain, "NIFTY", expiry, spot)
            exposure     = compute_greeks_exposure(chain, "NIFTY")
            iv_analytics = compute_iv_analytics(chain, "NIFTY")
            summary      = compute_market_summary(chain, "NIFTY")

            # Day change — use cached prev_close only, skip OHLC API call to avoid hanging
            try:
                cached_close = state.get_sync("prev_close:NIFTY")
                if cached_close and cached_close > 0:
                    summary.day_change     = round(spot - cached_close, 2)
                    summary.day_change_pct = round((spot - cached_close) / cached_close * 100, 2)
                elif now_ts - _prev_close_fetched_at > 300:
                    # Fetch OHLC with strict 5s timeout — only once every 5 min
                    from api.dhan_client import INDEX_SECURITY_IDS_INT
                    sid_int = INDEX_SECURITY_IDS_INT.get("NIFTY", 13)
                    try:
                        ohlc_resp = await asyncio.wait_for(dhan.get_ohlc([sid_int], "IDX_I"), timeout=5.0)
                        ohlc_data = ohlc_resp.get("data", {}).get("IDX_I", {})
                        q_ohlc    = ohlc_data.get(str(sid_int)) or ohlc_data.get(sid_int) or {}
                        ohlc      = q_ohlc.get("ohlc") or {}
                        # Use previous day's CLOSE (not today's open) — matches Dhan website
                        prev_close = float(ohlc.get("close") or 0)
                        if prev_close > 0:
                            summary.day_change     = round(spot - prev_close, 2)
                            summary.day_change_pct = round((spot - prev_close) / prev_close * 100, 2)
                            state.set_sync("prev_close:NIFTY", prev_close)
                            _prev_close_fetched_at = now_ts
                    except Exception:
                        pass
            except Exception:
                pass

            chain_dict    = chain.dict()
            exposure_dict = exposure.dict()
            iv_dict       = iv_analytics.dict()
            summary_dict  = summary.dict()

            if not _is_valid_chain(chain_dict):
                continue

            # Write to in-memory state (instant for REST API reads)
            await state.set("chain:NIFTY",    chain_dict)
            await state.set("exposure:NIFTY", exposure_dict)
            await state.set("iv:NIFTY",       iv_dict)
            await state.set("summary:NIFTY",  summary_dict)

            # Write to Redis — use thread pool with sync socket (bypasses broken aioredis)
            import json as _json
            loop = asyncio.get_event_loop()
            _writes = [
                (cache.key_chain("NIFTY"),    _json.dumps(chain_dict,    default=str), TTL_OPTION_CHAIN),
                (cache.key_exposure("NIFTY"), _json.dumps(exposure_dict, default=str), TTL_GREEKS),
                (cache.key_iv("NIFTY"),       _json.dumps(iv_dict,       default=str), TTL_IV_ANALYTICS),
                (cache.key_summary("NIFTY"),  _json.dumps(summary_dict,  default=str), TTL_MARKET_SUMMARY),
                ("chain:NIFTY:cycle",         _json.dumps({"cycle": _cycle, "ts": time.time(), "spot": spot}), 60),
            ]
            for _k, _v, _t in _writes:
                try:
                    await loop.run_in_executor(None, _redis_set_sync, _k, _v, _t)
                except Exception:
                    pass

            # Feed analytics engines — each step marked for debugging
            push_price("NIFTY", spot)
            push_vwap_tick("NIFTY", spot, 100)
            prev_exposure = state.get_sync("exposure_prev:NIFTY")
            record_exposure_snapshot("NIFTY", exposure_dict)
            state.set_sync("exposure_prev:NIFTY", exposure_dict)
            ingest_chain_for_oi("NIFTY", chain_dict.get("rows", []), spot)
            record_intelligence_snapshot("NIFTY", exposure_dict, iv_dict, chain_dict)

            # ── ML signals — feed candle buffer every cycle, infer every 15min ──
            try:
                ingest_chain_for_ml(chain_dict, spot)
                # Track buffer size in Redis for debugging
                from features.ml_signals import _buffers as _ml_bufs
                import json as _j
                loop.run_in_executor(None, _redis_set_sync,
                    "ml:debug", _j.dumps({"buffers": len(_ml_bufs), "cycle": _cycle, "rows": len(chain_dict.get("rows",[]))}), 60)
                if should_run_inference():
                    ml_sigs = run_ml_inference(chain_dict, spot)
                    update_signals(ml_sigs)
                    # Persist to Redis so REST endpoint serves fresh data on page load
                    loop.run_in_executor(None, _redis_set_sync,
                        "ml:signals:NIFTY", _j.dumps(ml_sigs, default=str), 900)
                    if ml_sigs:
                        asyncio.create_task(manager.broadcast({
                            "type":      "ml_signals",
                            "symbol":    "NIFTY",
                            "data":      ml_sigs,
                            "timestamp": time.time(),
                        }))
            except Exception as _ml_e:
                loop.run_in_executor(None, _redis_set_sync, "ml:error", str(_ml_e)[:200], 300)

            atm_iv = summary_dict.get("atm_iv", 0.0)
            if atm_iv > 0:
                get_vol_surface("NIFTY").push(atm_iv)
                # ts_push is optional — skip if it would block
                asyncio.create_task(cache.ts_push(cache.key_iv_history("NIFTY"), {"ts": time.time(), "iv": atm_iv}, maxlen=252, ttl=TTL_IV_HISTORY))

            _last_gex = state.get_sync("last_gex:NIFTY") or {}
            gex_val   = exposure_dict.get("total_gex", 0) or _last_gex.get("gex", 0)
            dex_val   = exposure_dict.get("total_dex", 0) or _last_gex.get("dex", 0)
            if gex_val != 0 or dex_val != 0:
                snap = {"ts": time.time(), "gex": gex_val, "dex": dex_val, "spot": spot,
                        "gamma_flip": exposure_dict.get("gamma_flip_level", 0),
                        "call_wall":  exposure_dict.get("call_wall", 0),
                        "put_wall":   exposure_dict.get("put_wall", 0)}
                state.set_sync("last_gex:NIFTY", snap)
                # ts_push is optional — skip if it would block
                asyncio.create_task(cache.ts_push(cache.key_gex_history("NIFTY"), snap, maxlen=500, ttl=TTL_GEX_HISTORY))

            # Alert checks — all wrapped with timeout to prevent blocking
            try:
                eng = get_alert_engine()
                if prev_exposure:
                    await asyncio.wait_for(eng.check_gamma_flip("NIFTY", prev_exposure.get("total_gex", 0.0), exposure_dict.get("total_gex", 0.0), spot), timeout=1.0)
                prev_summary = state.get_sync("summary_prev:NIFTY")
                if prev_summary and atm_iv > 0:
                    await asyncio.wait_for(eng.check_iv_spike("NIFTY", prev_summary.get("atm_iv", 0.0), atm_iv), timeout=1.0)
                state.set_sync("summary_prev:NIFTY", summary_dict)
                await asyncio.wait_for(eng.check_extreme_pcr("NIFTY", summary_dict.get("pcr_oi", 1.0)), timeout=1.0)
                await asyncio.wait_for(eng.check_wall_test("NIFTY", spot, exposure_dict.get("call_wall", 0.0), exposure_dict.get("put_wall", 0.0)), timeout=1.0)
                from features.oi_flow import get_oi_store
                await asyncio.wait_for(eng.check_oi_flow("NIFTY", get_oi_store("NIFTY").get_dominant_strikes(10)), timeout=1.0)
            except Exception:
                pass

            # Broadcast to all connected WebSocket clients — with timeout
            try:
                manager = get_connection_manager()
                await asyncio.wait_for(manager.broadcast({"type": "option_chain_update", "symbol": "NIFTY", "data": chain_dict,    "timestamp": time.time()}), timeout=2.0)
                await asyncio.wait_for(manager.broadcast({"type": "greeks_update",       "symbol": "NIFTY", "data": exposure_dict, "timestamp": time.time()}), timeout=2.0)
                await asyncio.wait_for(manager.broadcast({"type": "iv_update",           "symbol": "NIFTY", "data": iv_dict,       "timestamp": time.time()}), timeout=2.0)
                await asyncio.wait_for(manager.broadcast({"type": "market_summary",      "symbol": "NIFTY", "data": summary_dict,  "timestamp": time.time()}), timeout=2.0)
            except Exception:
                pass

            # Explicit sleep to enforce 3s minimum between cycles
            await asyncio.sleep(3)

        except Exception as e:
            import traceback as _tb
            # Log the error to Redis so we can see it
            try:
                _err_cache = get_cache()
                await _err_cache.set("chain:NIFTY:last_error", {
                    "error": str(e),
                    "type": type(e).__name__,
                    "ts": time.time(),
                }, ttl=3600)
            except Exception:
                pass
            await asyncio.sleep(1)


async def _refresh_option_chain(symbol: str, spot_override: float = None):
    """
    Refresh option chain for one symbol.
    spot_override: pre-fetched spot price from the shared LTP batch call.
    If not provided (e.g. direct REST call), falls back to a single LTP call.
    """
    manager = get_connection_manager()
    state   = get_market_state()
    cache   = get_cache()
    demo    = is_demo_mode()

    try:
        if demo:
            # Demo mode: only used during development, never in production
            # Returns real-looking data for UI testing without Dhan credentials
            expiries  = _generate_expiries(symbol)[:3]
            expiry    = expiries[0] if expiries else ""
            quote     = generate_demo_quote(symbol)
            spot      = float(quote["last_price"])
            raw_chain = generate_demo_option_chain(symbol, expiry)
        else:
            dhan = get_dhan_client()

            # Use pre-fetched spot if available, otherwise do a single LTP call
            if spot_override and spot_override > 0:
                spot = spot_override
            else:
                from api.dhan_client import INDEX_SECURITY_IDS_INT
                sid_int  = INDEX_SECURITY_IDS_INT.get(symbol, 13)
                ltp_resp = await dhan.get_ltp([sid_int], "IDX_I")
                seg_data = ltp_resp.get("data", {}).get("IDX_I", {})
                q        = seg_data.get(str(sid_int)) or seg_data.get(sid_int) or {}
                spot     = float(q.get("last_price") or 0)

            if spot <= 0:
                return

            expiries = await dhan.get_option_expiries(symbol)
            if not expiries:
                # Fall back to cached expiries (market may be closed or API rate-limited)
                cached_exp = await state.get(f"expiries:{symbol}")
                if not cached_exp:
                    cached_exp = await cache.get(cache.key_expiries(symbol))
                if cached_exp:
                    expiries = cached_exp
                else:
                    # Generate approximate expiries (next few Thursdays)
                    from datetime import date, timedelta
                    today = date.today()
                    # Find next Thursday
                    days_ahead = (3 - today.weekday()) % 7  # 3 = Thursday
                    if days_ahead == 0: days_ahead = 7
                    next_thu = today + timedelta(days=days_ahead)
                    expiries = [
                        next_thu.strftime("%Y-%m-%d"),
                        (next_thu + timedelta(days=7)).strftime("%Y-%m-%d"),
                        (next_thu + timedelta(days=14)).strftime("%Y-%m-%d"),
                    ]
            expiry = expiries[0]

            raw_chain = await dhan.get_option_chain(symbol, expiry)

            if not raw_chain:
                return

            data = raw_chain.get("data", {})
            oc   = data.get("oc", {})

            if not oc:
                return

            non_zero = sum(
                1 for v in oc.values()
                if float((v.get("ce") or {}).get("last_price") or 0) > 0
                or float((v.get("pe") or {}).get("last_price") or 0) > 0
            )
            # When market is closed, LTP=0 but OI is still valid — don't skip
            if non_zero == 0:
                # Check if OI data exists (market closed but data valid)
                non_zero_oi = sum(
                    1 for v in oc.values()
                    if int((v.get("ce") or {}).get("oi") or 0) > 0
                    or int((v.get("pe") or {}).get("oi") or 0) > 0
                )
                if non_zero_oi == 0:
                    # Truly empty — serve last valid cache
                    existing = await cache.get(cache.key_chain(symbol))
                    if existing and _is_valid_cached_chain(existing):
                        return

        chain        = process_option_chain(raw_chain, symbol, expiry, spot)
        exposure     = compute_greeks_exposure(chain, symbol)
        iv_analytics = compute_iv_analytics(chain, symbol)
        summary      = compute_market_summary(chain, symbol)

        # Fetch day change using open price as proxy for previous close
        if not demo:
            try:
                from api.dhan_client import INDEX_SECURITY_IDS_INT
                sid_int = INDEX_SECURITY_IDS_INT.get(symbol, 13)

                # Check if we have a cached prev_close from today
                cached_close = state.get_sync(f"prev_close:{symbol}")
                if cached_close and cached_close > 0 and spot > 0:
                    summary.day_change     = round(spot - cached_close, 2)
                    summary.day_change_pct = round((spot - cached_close) / cached_close * 100, 2)
                else:
                    # Use previous day's CLOSE from OHLC — matches Dhan website
                    ohlc_resp = await dhan.get_ohlc([sid_int], "IDX_I")
                    ohlc_data = ohlc_resp.get("data", {}).get("IDX_I", {})
                    q_ohlc    = ohlc_data.get(str(sid_int)) or ohlc_data.get(sid_int) or {}
                    ohlc      = q_ohlc.get("ohlc") or {}
                    prev_close = float(ohlc.get("close") or 0)
                    if prev_close > 0 and spot > 0:
                        summary.day_change     = round(spot - prev_close, 2)
                        summary.day_change_pct = round((spot - prev_close) / prev_close * 100, 2)
                        state.set_sync(f"prev_close:{symbol}", prev_close)
            except Exception:
                pass

        chain_dict    = chain.dict()
        exposure_dict = exposure.dict()
        iv_dict       = iv_analytics.dict()
        summary_dict  = summary.dict()

        # ── Validate processed chain before caching ──────────────────────
        if not _is_valid_chain(chain_dict):
            return

        await state.set(f"chain:{symbol}",    chain_dict)
        await state.set(f"exposure:{symbol}", exposure_dict)
        await state.set(f"iv:{symbol}",       iv_dict)
        await state.set(f"summary:{symbol}",  summary_dict)
        # Store expiries separately so /api/expiries can serve them without an extra API call
        if expiries:
            await state.set(f"expiries:{symbol}", expiries)
            await cache.set(cache.key_expiries(symbol), expiries, TTL_EXPIRIES)

        await cache.set(cache.key_chain(symbol),    chain_dict,    TTL_OPTION_CHAIN)
        await cache.set(cache.key_exposure(symbol), exposure_dict, TTL_GREEKS)
        await cache.set(cache.key_iv(symbol),       iv_dict,       TTL_IV_ANALYTICS)
        await cache.set(cache.key_summary(symbol),  summary_dict,  TTL_MARKET_SUMMARY)

        push_price(symbol, spot)
        push_vwap_tick(symbol, spot, 100)
        prev_exposure = state.get_sync(f"exposure_prev:{symbol}")
        record_exposure_snapshot(symbol, exposure_dict)
        state.set_sync(f"exposure_prev:{symbol}", exposure_dict)
        ingest_chain_for_oi(symbol, chain_dict.get("rows", []), spot)
        # Record intelligence snapshot (deltas)
        record_intelligence_snapshot(symbol, exposure_dict, iv_dict, chain_dict)
        atm_iv = summary_dict.get("atm_iv", 0.0)
        if atm_iv > 0:
            get_vol_surface(symbol).push(atm_iv)

        # Persist IV history to Redis (survives restarts)
        if atm_iv > 0:
            await cache.ts_push(
                cache.key_iv_history(symbol),
                {"ts": time.time(), "iv": atm_iv},
                maxlen=252,
                ttl=TTL_IV_HISTORY,
            )

        # Persist GEX snapshot to Redis time-series — always push (use last valid if current is 0)
        _last_gex = state.get_sync(f"last_gex:{symbol}") or {}
        gex_val   = exposure_dict.get("total_gex", 0) or _last_gex.get("gex", 0)
        dex_val   = exposure_dict.get("total_dex", 0) or _last_gex.get("dex", 0)
        if gex_val != 0 or dex_val != 0:
            snap = {
                "ts":         time.time(),
                "gex":        gex_val,
                "dex":        dex_val,
                "spot":       spot,
                "gamma_flip": exposure_dict.get("gamma_flip_level", 0),
                "call_wall":  exposure_dict.get("call_wall", 0),
                "put_wall":   exposure_dict.get("put_wall", 0),
            }
            state.set_sync(f"last_gex:{symbol}", snap)
            await cache.ts_push(
                cache.key_gex_history(symbol),
                snap,
                maxlen=500,
                ttl=TTL_GEX_HISTORY,
            )

        eng = get_alert_engine()
        if prev_exposure:
            await eng.check_gamma_flip(symbol, prev_exposure.get("total_gex", 0.0), exposure_dict.get("total_gex", 0.0), spot)
        prev_summary = state.get_sync(f"summary_prev:{symbol}")
        if prev_summary and atm_iv > 0:
            await eng.check_iv_spike(symbol, prev_summary.get("atm_iv", 0.0), atm_iv)
        state.set_sync(f"summary_prev:{symbol}", summary_dict)
        await eng.check_extreme_pcr(symbol, summary_dict.get("pcr_oi", 1.0))
        await eng.check_wall_test(symbol, spot, exposure_dict.get("call_wall", 0.0), exposure_dict.get("put_wall", 0.0))
        from features.oi_flow import get_oi_store
        await eng.check_oi_flow(symbol, get_oi_store(symbol).get_dominant_strikes(10))

        await manager.broadcast({"type": "option_chain_update", "symbol": symbol, "data": chain_dict,    "timestamp": time.time()})
        await manager.broadcast({"type": "greeks_update",       "symbol": symbol, "data": exposure_dict, "timestamp": time.time()})
        await manager.broadcast({"type": "iv_update",           "symbol": symbol, "data": iv_dict,       "timestamp": time.time()})
        await manager.broadcast({"type": "market_summary",      "symbol": symbol, "data": summary_dict,  "timestamp": time.time()})

    except Exception:
        pass


def _is_valid_chain(chain_dict: dict) -> bool:
    """
    Returns True if the processed chain has at least some rows with non-zero LTP or OI.
    Prevents caching empty/all-zero chains.
    """
    rows = chain_dict.get("rows", [])
    if not rows:
        return False
    non_zero = sum(
        1 for row in rows
        if row.get("call", {}).get("ltp", 0) > 0
        or row.get("put",  {}).get("ltp", 0) > 0
        or row.get("call", {}).get("oi",  0) > 0
        or row.get("put",  {}).get("oi",  0) > 0
    )
    return non_zero > 0


def _is_valid_cached_chain(chain_dict: dict) -> bool:
    """Same as _is_valid_chain — used to check if a cached chain is worth serving."""
    return _is_valid_chain(chain_dict)


# ─── REST API Routes ──────────────────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    cache = get_cache()
    state = get_market_state()
    ws_client = get_ws_client()
    return {
        "status": "ok",
        "timestamp": time.time(),
        "connections": get_connection_manager().get_connection_count(),
        "redis": cache.available,
        "demo_mode": is_demo_mode(),
        "feed_running": ws_client._running,
        "feed_subscriptions": len(ws_client._subscriptions),
        "feed_callbacks": len(ws_client._callbacks),
        "nifty_ltp_from_ws": state.get_sync("ltp:13"),
        "tick_count": state.get_sync("_tick_count"),
        "last_tick_ts": state.get_sync("_last_tick_ts"),
        "last_tick_raw": state.get_sync("_last_tick_raw"),
        "raw_packet_count": state.get_sync("_raw_packet_count"),
        "raw_last_byte": state.get_sync("_raw_last_byte"),
        "ws_disconnect_code": state.get_sync("_ws_disconnect_code"),
        "ws_disconnect_reason": state.get_sync("_ws_disconnect_reason"),
    }


@app.get("/api/option-chain", response_model=OptionChainResponse)
async def get_option_chain(
    symbol: str = Query("NIFTY", description="Index symbol"),
    expiry: Optional[str] = Query(None, description="Expiry date YYYY-MM-DD"),
    dhan: DhanAPIClient = Depends(get_dhan_client),
    _user: str = Depends(require_auth),
):
    """
    Fetch option chain.
    Serves from in-memory state or Redis cache first (instant).
    Only falls back to live API if no cache exists at all.
    """
    state = get_market_state()
    cache = get_cache()
    demo  = is_demo_mode()

    # 1. In-memory state (freshest, set by background worker)
    cached = await state.get(f"chain:{symbol}")
    if cached and expiry is None:
        return ORJSONResponse(cached)

    # 2. Redis cache
    redis_cached = await cache.get(cache.key_chain(symbol, expiry or ""))
    if redis_cached:
        return ORJSONResponse(redis_cached)

    # 3. No cache at all — trigger ONE background refresh and wait briefly
    # This only happens on first load before the background worker has run
    if demo:
        expiries = _generate_expiries(symbol)
        expiry   = expiry or (expiries[0] if expiries else "")
        quote    = generate_demo_quote(symbol)
        spot     = float(quote["last_price"])
        raw      = generate_demo_option_chain(symbol, expiry)
        chain    = process_option_chain(raw, symbol, expiry, spot)
        result   = chain.dict()
        if _is_valid_chain(result):
            await state.set(f"chain:{symbol}", result)
            await cache.set(cache.key_chain(symbol), result, TTL_OPTION_CHAIN)
        return chain

    # Live mode: kick off background refresh (non-blocking) and wait up to 20s
    # The background pre-warm task may already be fetching this symbol
    asyncio.create_task(_refresh_option_chain(symbol, spot_override=None))
    for _ in range(40):   # poll every 0.5s for up to 20s
        await asyncio.sleep(0.5)
        # Check in-memory state
        cached = await state.get(f"chain:{symbol}")
        if cached:
            return ORJSONResponse(cached)
        # Also check Redis (background task writes there too)
        redis_cached = await cache.get(cache.key_chain(symbol))
        if redis_cached:
            return ORJSONResponse(redis_cached)

    raise HTTPException(503, f"Data for {symbol} not yet ready. The server is still loading.")


@app.get("/api/expiries")
async def get_expiries(
    symbol: str = Query("NIFTY"),
    dhan: DhanAPIClient = Depends(get_dhan_client),
    _user: str = Depends(require_auth)
):
    """Get available expiry dates — served from cache when available."""
    if is_demo_mode():
        return {"symbol": symbol, "expiries": _generate_expiries(symbol)}

    # Check in-memory state first (populated by periodic refresh)
    state = get_market_state()
    cached_expiries = await state.get(f"expiries:{symbol}")
    if cached_expiries:
        return {"symbol": symbol, "expiries": cached_expiries}

    # Check Redis
    cache = get_cache()
    redis_expiries = await cache.get(cache.key_expiries(symbol))
    if redis_expiries:
        return {"symbol": symbol, "expiries": redis_expiries}

    # Fall back to live API call
    expiries = await dhan.get_option_expiries(symbol)
    if expiries:
        await state.set(f"expiries:{symbol}", expiries)
        await cache.set(cache.key_expiries(symbol), expiries, TTL_EXPIRIES)
    return {"symbol": symbol, "expiries": expiries}


@app.get("/api/greeks-exposure", response_model=GreeksExposureResponse)
async def get_greeks_exposure(
    symbol: str = Query("NIFTY"),
    expiry: Optional[str] = Query(None),
    _user: str = Depends(require_auth)
):
    """Get Greeks & GEX/DEX exposure — served from cache only, never blocks."""
    state = get_market_state()
    cached = await state.get(f"exposure:{symbol}")
    if cached:
        return ORJSONResponse(cached)
    # Check Redis as fallback
    cache = get_cache()
    redis_cached = await cache.get(cache.key_exposure(symbol))
    if redis_cached:
        return ORJSONResponse(redis_cached)
    # Return empty but valid response — background worker will populate soon
    return ORJSONResponse(GreeksExposureResponse(
        symbol=symbol, expiry="", spot_price=0,
        exposures=[], total_gex=0, total_dex=0,
        total_vega=0, total_theta=0,
        gamma_flip_level=0, call_wall=0, put_wall=0,
    ).dict())


@app.get("/api/iv-analytics", response_model=IVAnalyticsResponse)
async def get_iv_analytics(
    symbol: str = Query("NIFTY"),
    _user: str = Depends(require_auth)
):
    """Get IV analytics — served from cache only, never blocks."""
    state = get_market_state()
    cached = await state.get(f"iv:{symbol}")
    if cached:
        return ORJSONResponse(cached)
    cache = get_cache()
    redis_cached = await cache.get(cache.key_iv(symbol))
    if redis_cached:
        return ORJSONResponse(redis_cached)
    return ORJSONResponse(IVAnalyticsResponse(
        symbol=symbol, expiry="", spot_price=0,
        smile=[], current_iv=0, avg_iv=0,
        iv_rank=0, iv_percentile=0,
        historical_vol_30d=0, iv_rv_spread=0,
    ).dict())


@app.get("/api/market-summary", response_model=MarketSummary)
async def get_market_summary(symbol: str = Query("NIFTY"),
    _user: str = Depends(require_auth)
):
    """Get market summary — served from cache only, never blocks."""
    state = get_market_state()
    cached = await state.get(f"summary:{symbol}")
    if cached:
        return ORJSONResponse(cached)
    cache = get_cache()
    redis_cached = await cache.get(cache.key_summary(symbol))
    if redis_cached:
        return ORJSONResponse(redis_cached)
    return ORJSONResponse(MarketSummary(symbol=symbol).dict())


@app.get("/api/indices")
async def get_extra_indices(
    dhan: DhanAPIClient = Depends(get_dhan_client),
    _user: str = Depends(require_auth),
):
    """
    Batch fetch all 7 indices in 1-2 API calls.
    Returns: BANKNIFTY, FINNIFTY, MIDCPNIFTY, SENSEX, INDIAVIX, GIFTNIFTY
    Uses /marketfeed/quote for OHLC + net_change in a single call.
    Cached in Redis for 30s to avoid hammering the API.
    """
    if is_demo_mode():
        return [
            {"symbol": "BANKNIFTY",  "ltp": 56000.0, "change": 120.0,  "change_pct": 0.21},
            {"symbol": "FINNIFTY",   "ltp": 26500.0, "change": -45.0,  "change_pct": -0.17},
            {"symbol": "MIDCPNIFTY", "ltp": 13800.0, "change": 30.0,   "change_pct": 0.22},
            {"symbol": "SENSEX",     "ltp": 80500.0, "change": 200.0,  "change_pct": 0.25},
            {"symbol": "INDIAVIX",   "ltp": 18.5,    "change": -0.3,   "change_pct": -1.6},
            {"symbol": "GIFTNIFTY",  "ltp": 24380.0, "change": 30.0,   "change_pct": 0.12},
        ]

    # Check Redis cache first (30s TTL)
    cache = get_cache()
    cached = await cache.get("indices:batch")
    if cached:
        return ORJSONResponse(cached)

    from api.dhan_client import INDEX_SECURITY_IDS_INT
    state = get_market_state()

    # Fetch all IDX_I indices in ONE batch call
    # BANKNIFTY=25, FINNIFTY=27, MIDCPNIFTY=442, SENSEX=51, INDIAVIX=21, GIFTNIFTY=5024
    idx_sids = [25, 27, 442, 51, 21, 5024]
    sid_to_sym = {25: "BANKNIFTY", 27: "FINNIFTY", 442: "MIDCPNIFTY",
                  51: "SENSEX", 21: "INDIAVIX", 5024: "GIFTNIFTY"}

    results = []
    try:
        resp     = await dhan.get_market_quote(idx_sids, "IDX_I")
        seg_data = resp.get("data", {}).get("IDX_I", {})

        for sid, sym in sid_to_sym.items():
            q = seg_data.get(str(sid)) or seg_data.get(sid) or {}
            if not q:
                continue
            ltp        = float(q.get("last_price") or 0)
            net_change = float(q.get("net_change") or 0)
            ohlc       = q.get("ohlc") or {}
            prev_close = float(ohlc.get("close") or 0)

            if ltp <= 0:
                continue

            # Use net_change from Dhan (most accurate)
            if net_change != 0:
                change = round(net_change, 2)
            elif prev_close > 0:
                change = round(ltp - prev_close, 2)
            else:
                change = 0.0

            change_pct = round(change / (ltp - change) * 100, 2) if (ltp - change) > 0 else 0.0

            # Cache prev_close for WS tick day-change calculation
            if prev_close > 0:
                state.set_sync(f"prev_close:{sym}", prev_close)

            results.append({
                "symbol":     sym,
                "ltp":        ltp,
                "change":     change,
                "change_pct": change_pct,
            })
    except Exception:
        pass

    if results:
        await cache.set("indices:batch", results, ttl=30)

    return ORJSONResponse(results)


@app.get("/api/quote")
async def get_quote(
    symbol: str = Query("NIFTY"),
    dhan: DhanAPIClient = Depends(get_dhan_client),
    _user: str = Depends(require_auth)
):
    """Get spot price quote — uses LTP endpoint (lighter, 1 req/sec)."""
    if is_demo_mode():
        q = generate_demo_quote(symbol)
        return {
            "symbol": symbol,
            "ltp": q["last_price"],
            "change": q["net_change"],
            "change_pct": q["percentage_change"],
            "open": q["open"],
            "high": q["high"],
            "low": q["low"],
            "close": q["close"],
            "timestamp": time.time(),
            "demo": True,
        }

    # Serve from in-memory state first (updated by periodic refresh every 3s)
    state = get_market_state()
    summary = state.get_sync(f"summary:{symbol}")
    if not summary:
        # Fall back to Redis (in-memory state may not be populated yet)
        cache = get_cache()
        summary = await cache.get(f"summary:{symbol}")
    if summary and summary.get("spot_price", 0) > 0:
        return {
            "symbol":     symbol,
            "ltp":        summary["spot_price"],
            "change":     summary.get("day_change", 0),
            "change_pct": summary.get("day_change_pct", 0),
            "open":       0.0,
            "high":       0.0,
            "low":        0.0,
            "close":      0.0,
            "timestamp":  summary.get("timestamp", time.time()),
        }

    # Fall back to LTP API (cheaper than quote)
    from api.dhan_client import INDEX_SECURITY_IDS_INT
    sid_int  = INDEX_SECURITY_IDS_INT.get(symbol, 13)
    ltp_resp = await dhan.get_ltp([sid_int], "IDX_I")
    seg_data = ltp_resp.get("data", {}).get("IDX_I", {})
    q        = seg_data.get(str(sid_int)) or seg_data.get(sid_int) or {}
    ltp      = float(q.get("last_price") or 0)

    # Use previous day's CLOSE for day change — matches Dhan website
    change = 0.0
    change_pct = 0.0
    try:
        state2 = get_market_state()
        cached_close = state2.get_sync(f"prev_close:{symbol}")
        if cached_close and cached_close > 0 and ltp > 0:
            change     = round(ltp - cached_close, 2)
            change_pct = round((ltp - cached_close) / cached_close * 100, 2)
        else:
            # Use full market quote which includes net_change directly from Dhan
            quote_resp = await dhan.get_market_quote([sid_int], "IDX_I")
            quote_data = quote_resp.get("data", {}).get("IDX_I", {})
            q_full     = quote_data.get(str(sid_int)) or quote_data.get(sid_int) or {}
            # net_change is Dhan's pre-computed change from prev close
            net_change = float(q_full.get("net_change") or 0)
            ohlc       = q_full.get("ohlc") or {}
            prev_close = float(ohlc.get("close") or 0)
            if net_change != 0 and ltp > 0:
                change     = round(net_change, 2)
                change_pct = round(net_change / (ltp - net_change) * 100, 2) if (ltp - net_change) > 0 else 0.0
                if prev_close > 0:
                    state2.set_sync(f"prev_close:{symbol}", prev_close)
            elif prev_close > 0 and ltp > 0:
                change     = round(ltp - prev_close, 2)
                change_pct = round((ltp - prev_close) / prev_close * 100, 2)
                state2.set_sync(f"prev_close:{symbol}", prev_close)
    except Exception:
        pass

    return {
        "symbol":     symbol,
        "ltp":        ltp,
        "change":     change,
        "change_pct": change_pct,
        "open":       0.0,
        "high":       0.0,
        "low":        0.0,
        "close":      0.0,
        "timestamp":  time.time(),
    }


@app.post("/api/strategy/analyze", response_model=StrategyAnalysis)
async def analyze_strategy(legs: List[StrategyLeg],
    _user: str = Depends(require_auth)
):
    """Analyze a multi-leg options strategy."""
    from calculations.black_scholes import (
        bs_call_price, bs_put_price, compute_all_greeks, days_to_expiry
    )

    if not legs:
        raise HTTPException(400, "No legs provided")

    net_premium = 0.0
    net_delta = 0.0
    net_gamma = 0.0
    net_theta = 0.0
    net_vega = 0.0

    for leg in legs:
        sign = 1 if leg.action == "BUY" else -1
        net_premium += sign * leg.premium * leg.quantity
        net_delta += sign * leg.greeks.delta * leg.quantity
        net_gamma += sign * leg.greeks.gamma * leg.quantity
        net_theta += sign * leg.greeks.theta * leg.quantity
        net_vega += sign * leg.greeks.vega * leg.quantity

    # Build payoff curve
    if legs:
        spot = legs[0].strike  # use first strike as center
        min_spot = spot * 0.85
        max_spot = spot * 1.15
        num_points = 100
        payoff_curve = []

        for i in range(num_points + 1):
            s = min_spot + (max_spot - min_spot) * i / num_points
            pnl = -net_premium  # net cost to enter

            for leg in legs:
                sign = 1 if leg.action == "BUY" else -1
                T = days_to_expiry(leg.expiry)
                if T <= 0:
                    # At expiry
                    if leg.option_type == "CE":
                        intrinsic = max(s - leg.strike, 0)
                    else:
                        intrinsic = max(leg.strike - s, 0)
                    pnl += sign * intrinsic * leg.quantity
                else:
                    iv = leg.iv / 100.0 if leg.iv > 0 else 0.2
                    if leg.option_type == "CE":
                        price = bs_call_price(s, leg.strike, RISK_FREE_RATE, iv, T)
                    else:
                        price = bs_put_price(s, leg.strike, RISK_FREE_RATE, iv, T)
                    pnl += sign * (price - leg.premium) * leg.quantity

            payoff_curve.append(PayoffPoint(spot=round(s, 2), pnl=round(pnl, 2)))

    pnl_values = [p.pnl for p in payoff_curve]
    max_profit = max(pnl_values) if pnl_values else 0.0
    max_loss = min(pnl_values) if pnl_values else 0.0

    # Breakevens: zero crossings
    breakevens = []
    for i in range(1, len(payoff_curve)):
        p1, p2 = payoff_curve[i - 1], payoff_curve[i]
        if p1.pnl * p2.pnl < 0:
            frac = abs(p1.pnl) / (abs(p1.pnl) + abs(p2.pnl))
            be = p1.spot + frac * (p2.spot - p1.spot)
            breakevens.append(round(be, 2))

    # Guess strategy name
    strategy_name = _identify_strategy(legs)

    return StrategyAnalysis(
        strategy_name=strategy_name,
        legs=legs,
        net_premium=round(net_premium, 2),
        max_profit=round(max_profit, 2),
        max_loss=round(max_loss, 2),
        breakevens=breakevens,
        payoff_curve=payoff_curve,
        net_delta=round(net_delta, 4),
        net_gamma=round(net_gamma, 6),
        net_theta=round(net_theta, 4),
        net_vega=round(net_vega, 4),
    )


def _identify_strategy(legs: List[StrategyLeg]) -> str:
    """Heuristically identify strategy name from legs."""
    if len(legs) == 1:
        a = "Long" if legs[0].action == "BUY" else "Short"
        t = "Call" if legs[0].option_type == "CE" else "Put"
        return f"{a} {t}"

    if len(legs) == 2:
        types = [l.option_type for l in legs]
        strikes = [l.strike for l in legs]
        actions = [l.action for l in legs]

        has_call = "CE" in types
        has_put = "PE" in types
        same_strike = len(set(strikes)) == 1
        all_buy = all(a == "BUY" for a in actions)
        all_sell = all(a == "SELL" for a in actions)

        if has_call and has_put:
            if same_strike:
                return "Long Straddle" if all_buy else "Short Straddle"
            else:
                return "Long Strangle" if all_buy else "Short Strangle"

        # Both same type — spread
        if len(set(types)) == 1:
            opt = types[0]
            # Bull: buy lower strike call, or sell lower strike put
            lower_idx = 0 if strikes[0] <= strikes[1] else 1
            higher_idx = 1 - lower_idx
            if opt == "CE":
                if actions[lower_idx] == "BUY":
                    return "Bull Call Spread"
                else:
                    return "Bear Call Spread"
            else:
                if actions[lower_idx] == "BUY":
                    return "Bull Put Spread"
                else:
                    return "Bear Put Spread"

    if len(legs) == 3:
        types = [l.option_type for l in legs]
        if types.count("CE") == 2 or types.count("PE") == 2:
            return "Butterfly Spread"
        return "Custom 3-Leg Strategy"

    if len(legs) == 4:
        types = sorted([l.option_type for l in legs])
        actions = [l.action for l in legs]
        if types == ["CE", "CE", "PE", "PE"]:
            buys = sum(1 for a in actions if a == "BUY")
            sells = sum(1 for a in actions if a == "SELL")
            if buys == 2 and sells == 2:
                strikes = sorted([l.strike for l in legs])
                # Iron condor: outer buy, inner sell
                inner_legs = [l for l in legs if l.strike in strikes[1:3]]
                if all(l.action == "SELL" for l in inner_legs):
                    return "Iron Condor"
                return "Iron Butterfly"
        return "Custom 4-Leg Strategy"

    return "Custom Strategy"


@app.get("/api/historical")
async def get_historical(
    security_id: str = Query(...),
    exchange_segment: str = Query("IDX_I"),
    interval: int = Query(60),
    dhan: DhanAPIClient = Depends(get_dhan_client),
    _user: str = Depends(require_auth)
):
    """
    Get OHLCV historical data for indices and equities.
    Indices use IDX_I segment + INDEX instrument type.
    interval: 5/15/25/60 = intraday, 1440 = daily
    """
    from datetime import date, timedelta
    today     = date.today()
    from_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    to_date   = today.strftime("%Y-%m-%d")

    # All index security IDs — always use IDX_I + INDEX
    INDEX_SIDS = {"13", "25", "27", "442", "51", "21", "5024"}
    if security_id in INDEX_SIDS:
        exchange_segment = "IDX_I"
        instrument       = "INDEX"
    else:
        instrument_map = {
            "IDX_I":    "INDEX",
            "NSE_EQ":   "EQUITY",
            "BSE_EQ":   "EQUITY",
            "NSE_FNO":  "OPTIDX",
            "BSE_FNO":  "OPTIDX",
            "MCX_COMM": "FUTCOM",
        }
        instrument = instrument_map.get(exchange_segment, "EQUITY")

    if interval >= 1440:
        data = await dhan.get_historical_data(
            security_id=security_id,
            exchange_segment=exchange_segment,
            instrument_type=instrument,
            expiry_code=0,
            from_date=(today - timedelta(days=365)).strftime("%Y-%m-%d"),
            to_date=to_date,
        )
    else:
        data = await dhan.get_intraday_data(
            security_id=security_id,
            exchange_segment=exchange_segment,
            instrument_type=instrument,
            interval=str(interval),
            from_date=from_date,
            to_date=to_date,
        )

    if not data or not data.get("close"):
        raise HTTPException(503, f"No historical data available for this instrument")
    return data


# ─── WebSocket Endpoint ───────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = Query(None)):
    """Main WebSocket endpoint — requires JWT token as query param: /ws?token=<jwt>"""
    from auth import _verify_token, _hash_token, get_redis as _get_auth_redis

    # Validate JWT
    if not token:
        await websocket.close(code=4001, reason="Authentication required")
        return

    payload = _verify_token(token)
    if not payload:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    username = payload.get("sub", "")

    # Single-session check
    try:
        r = await _get_auth_redis()
        session = await r.hgetall(f"session:{username}")
        if not session or session.get("token_hash") != _hash_token(token):
            await websocket.close(code=4001, reason="Session invalidated — please log in again")
            return
    except Exception:
        pass   # Redis unavailable — allow through

    manager = get_connection_manager()
    state = get_market_state()
    client_id = str(uuid.uuid4())

    await manager.connect(websocket, client_id)

    # Send current state immediately
    current = await state.get_all()
    for key, val in current.items():
        key_type = key.split(":")[0]
        await manager.send_to_client(client_id, {
            "type": f"{key_type}_snapshot",
            "key": key,
            "data": val,
            "timestamp": time.time(),
        })

    try:
        while True:
            msg = await websocket.receive_json()
            action = msg.get("action", "")

            if action == "subscribe":
                channels = msg.get("channels", [])
                for ch in channels:
                    manager.subscribe(client_id, ch)
                await manager.send_to_client(client_id, {
                    "type": "subscribe_ok",
                    "channels": channels,
                })

            elif action == "unsubscribe":
                channels = msg.get("channels", [])
                for ch in channels:
                    manager.unsubscribe(client_id, ch)

            elif action == "get_chain":
                symbol = msg.get("symbol", "NIFTY")
                await _refresh_option_chain(symbol, spot_override=None)

            elif action == "ping":
                await manager.send_to_client(client_id, {"type": "pong", "timestamp": time.time()})

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await manager.disconnect(client_id)


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        workers=1,  # Must be 1 for WebSocket state sharing
        log_level="info",
    )
