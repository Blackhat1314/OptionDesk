"""
Dhan API v2 Client — Strictly per official documentation
==========================================================

FIXES APPLIED:
  WS HTTP 400 : v2 requires auth in URL query string, NO post-connect auth packet
  Binary format: Dhan uses LITTLE-ENDIAN (<), not big-endian (>)
  Full packet  : v2 uses RequestCode 21 for Full (NOT 19)
  Subscription : v2 uses JSON {"RequestCode":21,"InstrumentList":[{"ExchangeSegment":"IDX_I","SecurityId":"13"}]}
  Market quote : Request body {"IDX_I": [13]} — INTEGER IDs, multiple symbols in ONE call

Rate limits per Dhan docs v2:
  /marketfeed/quote        1 req/sec, max 1000 instruments per request
  /marketfeed/ltp          1 req/sec, max 1000 instruments per request
  /marketfeed/ohlc         1 req/sec, max 1000 instruments per request
  /marketfeed/full-depth   1 req/sec, max 1 instrument per request
  /optionchain             1 req/3s (expensive server-side computation)
  /charts/historical       100 req/day
  /charts/intraday         100 req/day
  /optionchain/expireddata 60 req/min

WebSocket v2 spec:
  URL  : wss://api-feed.dhan.co?version=2&token={access_token}&clientId={client_id}&authType=2
  Auth : embedded in URL — do NOT send auth packet after connect
  Sub  : JSON {"RequestCode": 15|17|21, "InstrumentCount": N, "InstrumentList": [...]}
  Recv : Binary little-endian packets
         first_byte=2  → Ticker   : struct '<BHBIfI' (16 bytes)
         first_byte=4  → Quote    : struct '<BHBIfHIfIIIffff' (50 bytes)
         first_byte=5  → OI       : struct '<BHBII' (12 bytes)
         first_byte=8  → Full     : struct '<BHBIfHIfIIIIIIffff100s' (162 bytes)
         first_byte=50 → Disconnect error
"""

import asyncio
import json
import struct
import time
from typing import Callable, Dict, List, Optional
from urllib.parse import urlencode

import aiohttp
import websockets

from config import get_settings
from api.rate_limiter import get_rate_limiter

settings = get_settings()


# ─── Exchange segment constants ───────────────────────────────────────────────

class ExchangeSegment:
    IDX_I       = "IDX_I"
    NSE_EQ      = "NSE_EQ"
    NSE_FNO     = "NSE_FNO"
    NSE_CURR    = "NSE_CURRENCY"
    BSE_EQ      = "BSE_EQ"
    BSE_FNO     = "BSE_FNO"
    MCX_COMM    = "MCX_COMM"
    BSE_CURR    = "BSE_CURRENCY"


# Exchange numeric code → string (used in WS subscription InstrumentList)
EXCHANGE_CODE_TO_STR = {
    0: "IDX_I",
    1: "NSE_EQ",
    2: "NSE_FNO",
    3: "NSE_CURRENCY",
    4: "BSE_EQ",
    5: "MCX_COMM",
    7: "BSE_CURRENCY",
    8: "BSE_FNO",
}

# v2 RequestCode values
class FeedRequestCode:
    TICKER    = 15   # LTP only
    QUOTE     = 17   # OHLC + Volume
    FULL      = 21   # Full with OI + Depth  (NOT 19 — v2 specific)
    UNSUB_TICKER = 16
    UNSUB_QUOTE  = 18
    UNSUB_FULL   = 22
    DISCONNECT   = 12


# Index security IDs (string for option chain API, int for market feed)
INDEX_SECURITY_IDS = {
    "NIFTY":      "13",
    "BANKNIFTY":  "25",
    "FINNIFTY":   "27",
    "MIDCPNIFTY": "442",
    "SENSEX":     "51",
    "INDIAVIX":   "21",
    "GIFTNIFTY":  "5024",
}

INDEX_SECURITY_IDS_INT = {
    "NIFTY":      13,
    "BANKNIFTY":  25,
    "FINNIFTY":   27,
    "MIDCPNIFTY": 442,
    "SENSEX":     51,
    "INDIAVIX":   21,    # India VIX — IDX_I
    "GIFTNIFTY":  5024,  # GIFT NIFTY — IDX_I
}

# Exchange segment per index (most are IDX_I, SENSEX is BSE_EQ)
INDEX_EXCHANGE_SEGMENT = {
    "NIFTY":      "IDX_I",
    "BANKNIFTY":  "IDX_I",
    "FINNIFTY":   "IDX_I",
    "MIDCPNIFTY": "IDX_I",
    "SENSEX":     "IDX_I",   # Dhan exposes SENSEX under IDX_I as well
}

INDEX_LOT_SIZES = {
    "NIFTY":      50,
    "BANKNIFTY":  15,
    "FINNIFTY":   40,
    "MIDCPNIFTY": 75,
    "SENSEX":     10,
}


# ─── HTTP Client ──────────────────────────────────────────────────────────────

class DhanAPIClient:
    """
    Async HTTP client for all Dhan REST APIs.
    Strictly follows v2 request/response formats.
    """

    def __init__(self):
        self.base_url     = settings.DHAN_BASE_URL
        self.client_id    = settings.DHAN_CLIENT_ID
        self.access_token = settings.DHAN_ACCESS_TOKEN
        self._session: Optional[aiohttp.ClientSession] = None
        self._rl = get_rate_limiter()

    def _headers(self) -> Dict[str, str]:
        # Always read access_token from instance (may be updated by token_manager)
        return {
            "client-id":    self.client_id,
            "access-token": self.access_token,
            "Content-Type": "application/json",
            "Accept":       "application/json",
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout   = aiohttp.ClientTimeout(total=20, connect=5)
            connector = aiohttp.TCPConnector(limit=10, enable_cleanup_closed=True)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _get(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        for attempt in range(3):
            try:
                async with session.get(url, params=params, headers=self._headers()) as resp:
                    if resp.status == 200:
                        return await resp.json(content_type=None)
                    if resp.status == 429:
                        retry_after = float(resp.headers.get("Retry-After", 60))
                        await self._rl.set_backoff(endpoint, retry_after)
                        if attempt < 2:
                            await asyncio.sleep(min(retry_after, 5))
                            continue
                        return {}
                    if resp.status == 400:
                        body = await resp.text()
                        return {}
                    if resp.status == 401:
                        return {}
                    body = await resp.text()
                    return {}
            except aiohttp.ClientError as e:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
            except asyncio.TimeoutError:
                if attempt < 2:
                    await asyncio.sleep(1)
        return {}

    async def _post(self, endpoint: str, body: Dict) -> Dict:
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        for attempt in range(3):
            try:
                async with session.post(url, json=body, headers=self._headers()) as resp:
                    if resp.status == 200:
                        return await resp.json(content_type=None)
                    if resp.status == 429:
                        retry_after = float(resp.headers.get("Retry-After", 60))
                        await self._rl.set_backoff(endpoint, retry_after)
                        if attempt < 2:
                            await asyncio.sleep(min(retry_after, 5))
                            continue
                        return {}
                    if resp.status == 400:
                        rb = await resp.text()
                        return {}
                    if resp.status == 401:
                        return {}
                    rb = await resp.text()
                    return {}
            except aiohttp.ClientError as e:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
            except asyncio.TimeoutError:
                if attempt < 2:
                    await asyncio.sleep(1)
        return {}

    # ── Option Chain ──────────────────────────────────────────────────────────

    async def get_option_chain(self, symbol: str, expiry: str) -> Dict:
        """
        POST /v2/optionchain — confirmed POST per Dhan v2 docs.
        Body: {UnderlyingScrip: int, UnderlyingSeg: str, Expiry: YYYY-MM-DD}

        Response keys (per docs):
          data.oc.{strike}.ce / .pe  ← lowercase
          greeks nested: {delta, theta, gamma, vega}
          top_bid_price, top_ask_price, top_bid_quantity, top_ask_quantity
          previous_oi, previous_volume, previous_close_price
          security_id is int
        """
        await self._rl.acquire_option_chain()
        body = {
            "UnderlyingScrip": INDEX_SECURITY_IDS_INT.get(symbol, 13),
            "UnderlyingSeg":   "IDX_I",
            "Expiry":          expiry,
        }
        result = await self._post("/optionchain", body)
        return result

    async def get_option_expiries(self, symbol: str) -> List[str]:
        """
        POST /v2/optionchain/expirylist — confirmed POST per Dhan v2 docs.
        Body: {UnderlyingScrip: int, UnderlyingSeg: str}
        Response: data[] — list of YYYY-MM-DD strings
        """
        await self._rl.acquire_expiry_list()
        body = {
            "UnderlyingScrip": INDEX_SECURITY_IDS_INT.get(symbol, 13),
            "UnderlyingSeg":   "IDX_I",
        }
        data = await self._post("/optionchain/expirylist", body)
        expiries = data.get("data", [])
        return expiries[:3] if expiries else []

    # ── Market Quote (per docs: body must use INTEGER security IDs) ───────────

    async def get_market_quote(self, security_ids: List, exchange_segment: str = "IDX_I") -> Dict:
        """
        POST /v2/marketfeed/quote
        Body: {"IDX_I": [13, 25]}   ← integer IDs, NOT strings
        Max 1000 instruments per request.

        Response:
          {"status":"success","data":{"IDX_I":{"13":{"last_price":22500,...}}}}
        """
        await self._rl.acquire_quote()
        # Enforce integer IDs — string IDs cause HTTP 400
        int_ids = [int(sid) for sid in security_ids][:1000]
        return await self._post("/marketfeed/quote", {exchange_segment: int_ids})

    async def get_ltp(self, security_ids: List, exchange_segment: str = "IDX_I") -> Dict:
        """POST /v2/marketfeed/ltp — lighter endpoint, same format rules."""
        await self._rl.acquire_ltp()
        int_ids = [int(sid) for sid in security_ids][:1000]
        return await self._post("/marketfeed/ltp", {exchange_segment: int_ids})

    async def get_ohlc(self, security_ids: List, exchange_segment: str = "IDX_I") -> Dict:
        """POST /v2/marketfeed/ohlc"""
        await self._rl.acquire_ohlc()
        int_ids = [int(sid) for sid in security_ids][:1000]
        return await self._post("/marketfeed/ohlc", {exchange_segment: int_ids})

    async def get_full_market_depth(self, security_id, exchange_segment: str = "NSE_FNO") -> Dict:
        """
        POST /v2/marketfeed/full-depth
        Per docs: max 1 instrument per request.
        """
        await self._rl.acquire_depth()
        return await self._post("/marketfeed/full-depth", {exchange_segment: [int(security_id)]})

    async def get_index_quote(self, symbol: str) -> Dict:
        """
        Get a single index spot quote. Parses the nested Dhan response correctly.
        Returns the inner quote dict or {}.
        """
        sid_int = INDEX_SECURITY_IDS_INT.get(symbol, 13)
        data    = await self.get_market_quote([sid_int], "IDX_I")
        # Response: {"status":"success","data":{"IDX_I":{"13":{...}}}}
        seg_data = data.get("data", {}).get("IDX_I", {})
        quote = seg_data.get(str(sid_int)) or seg_data.get(sid_int) or {}
        return quote

    async def get_multi_index_quote(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        Fetch quotes for multiple indices in a SINGLE API call.
        Returns {symbol: quote_dict, ...}
        """
        sid_map   = {INDEX_SECURITY_IDS_INT[s]: s for s in symbols if s in INDEX_SECURITY_IDS_INT}
        int_ids   = list(sid_map.keys())
        data      = await self.get_market_quote(int_ids, "IDX_I")
        seg_data  = data.get("data", {}).get("IDX_I", {})
        result    = {}
        for sid_int, sym in sid_map.items():
            q = seg_data.get(str(sid_int)) or seg_data.get(sid_int) or {}
            result[sym] = q
        return result

    # ── Historical Data ───────────────────────────────────────────────────────

    async def get_historical_data(
        self,
        security_id: str,
        exchange_segment: str,
        instrument_type: str,
        expiry_code: int,
        from_date: str,
        to_date: str,
        interval: str = "60",
    ) -> Dict:
        """
        POST /v2/charts/historical
        Per Dhan v2 docs:
          - oi: boolean (NOT string "1")
          - interval only for intraday; omit for daily
          - instrument: "INDEX", "EQUITY", "OPTIDX", etc.
        Daily quota: 100 requests/day.
        """
        await self._rl.acquire_historical()
        body = {
            "securityId":      str(security_id),
            "exchangeSegment": exchange_segment,
            "instrument":      instrument_type,
            "expiryCode":      expiry_code,
            "oi":              True,   # boolean per docs
            "fromDate":        from_date,
            "toDate":          to_date,
        }
        return await self._post("/charts/historical", body)

    async def get_intraday_data(
        self,
        security_id: str,
        exchange_segment: str,
        instrument_type: str,
        interval: str = "5",
        from_date: Optional[str] = None,
        to_date:   Optional[str] = None,
    ) -> Dict:
        """
        POST /v2/charts/intraday
        Per Dhan v2 docs:
          - interval: "1", "5", "15", "25", "60" (string)
          - oi: boolean
          - fromDate/toDate: "YYYY-MM-DD HH:MM:SS" format for intraday
        Daily quota: 100 requests/day.
        """
        await self._rl.acquire_intraday()
        body = {
            "securityId":      str(security_id),
            "exchangeSegment": exchange_segment,
            "instrument":      instrument_type,
            "interval":        str(interval),
            "oi":              True,   # boolean per docs
        }
        if from_date:
            body["fromDate"] = from_date if " " in from_date else f"{from_date} 09:15:00"
        if to_date:
            body["toDate"]   = to_date   if " " in to_date   else f"{to_date} 15:30:00"
        return await self._post("/charts/intraday", body)

    async def get_expired_option_data(
        self, symbol: str, expiry: str, strike: float, option_type: str,
    ) -> Dict:
        """POST /v2/optionchain/expireddata — 60 req/min limit."""
        await self._rl.acquire_expired_data()
        body = {
            "UnderlyingScrip": INDEX_SECURITY_IDS_INT.get(symbol, 13),
            "UnderlyingSeg":   "IDX_I",
            "Expiry":          expiry,
            "StrikePrice":     str(int(strike)),
            "OptionType":      option_type,
        }
        return await self._post("/optionchain/expireddata", body)


# ─── WebSocket Feed Client ────────────────────────────────────────────────────

class DhanWebSocketClient:
    """
    Dhan Live Market Feed — WebSocket v2.

    KEY DIFFERENCES v1 vs v2:
      v1: connect to bare URL, then send binary auth packet, RequestCode 15/17/19
      v2: connect with token/clientId in URL query string, NO auth packet,
          subscribe with JSON, RequestCode 15/17/21, binary LITTLE-ENDIAN responses

    Packet types (first byte, little-endian):
      2  → Ticker     '<BHBIfI'           16 bytes
      3  → Market Depth
      4  → Quote      '<BHBIfHIfIIIffff'  50 bytes
      5  → OI         '<BHBII'            12 bytes
      6  → Prev Close '<BHBIfI'           16 bytes
      7  → Status
      8  → Full       '<BHBIfHIfIIIIIIffff100s'  162 bytes
      50 → Server disconnect
    """

    WS_BASE = "wss://api-feed.dhan.co"

    def __init__(self, client_id: str, access_token: str):
        self.client_id    = client_id
        self.access_token = access_token
        self._ws          = None
        # List of {"exchange_segment": "IDX_I", "security_id": "13", "request_code": 21}
        self._subscriptions: List[Dict] = []
        self._callbacks:     List[Callable] = []
        self._running          = False
        self._reconnect_delay  = 1
        self._max_reconnect_delay = 60

    def _ws_url(self) -> str:
        """v2 URL — credentials embedded as query params, no post-connect auth."""
        params = urlencode({
            "version":  "2",
            "token":    self.access_token,
            "clientId": self.client_id,
            "authType": "2",
        })
        return f"{self.WS_BASE}?{params}"

    def add_callback(self, fn: Callable):
        self._callbacks.append(fn)

    def subscribe(
        self,
        instruments: List[Dict],
        request_code: int = FeedRequestCode.FULL,
    ):
        """
        Queue instruments for subscription.
        instruments: [{"exchange_segment": "IDX_I", "security_id": "13"}, ...]
        """
        for instr in instruments:
            instr["request_code"] = request_code
        self._subscriptions.extend(instruments)

    def _build_subscription_msg(
        self, instruments: List[Dict], request_code: int,
    ) -> str:
        """
        v2 JSON subscription message per Dhan docs.
        {
          "RequestCode": 21,
          "InstrumentCount": 2,
          "InstrumentList": [
            {"ExchangeSegment": "IDX_I", "SecurityId": "13"},
            {"ExchangeSegment": "NSE_FNO", "SecurityId": "43214"}
          ]
        }
        """
        return json.dumps({
            "RequestCode":     request_code,
            "InstrumentCount": len(instruments),
            "InstrumentList": [
                {
                    "ExchangeSegment": str(i.get("exchange_segment", "IDX_I")),
                    "SecurityId":      str(i.get("security_id", "")),
                }
                for i in instruments
            ],
        })

    def _parse_packet(self, data: bytes) -> Optional[Dict]:
        """
        Parse Dhan binary feed packet (little-endian).
        Returns normalised dict or None.
        """
        try:
            if len(data) < 8:
                return None

            first_byte = struct.unpack('<B', data[0:1])[0]

            # ── Ticker (type 2) ────────────────────────────────────────────
            if first_byte == 2 and len(data) >= 16:
                _, _, xch, sid, ltp, ltt = struct.unpack('<BHBIfI', data[0:16])
                return {
                    "type":             "ticker",
                    "exchange_segment": xch,
                    "security_id":      str(sid),
                    "LTP":              round(ltp, 2),
                    "LTT":              ltt,
                }

            # ── Prev Close (type 6) — auto-sent on subscribe ───────────────
            # Gives previous day close for FREE — parse it!
            if first_byte == 6 and len(data) >= 16:
                _, _, xch, sid, prev_close, prev_oi = struct.unpack('<BHBIfI', data[0:16])
                return {
                    "type":             "prev_close",
                    "exchange_segment": xch,
                    "security_id":      str(sid),
                    "prev_close":       round(prev_close, 2),
                    "prev_oi":          prev_oi,
                }

            # ── Quote (type 4) ─────────────────────────────────────────────
            if first_byte == 4 and len(data) >= 50:
                _, _, xch, sid, ltp, ltq, ltt, avg, vol, sell_q, buy_q, op, cl, hi, lo = \
                    struct.unpack('<BHBIfHIfIIIffff', data[0:50])
                return {
                    "type":              "quote",
                    "exchange_segment":  xch,
                    "security_id":       str(sid),
                    "LTP":               round(ltp, 2),
                    "LTQ":               ltq,
                    "LTT":               ltt,
                    "avg_price":         round(avg, 2),   # ATP / VWAP
                    "volume":            vol,
                    "total_sell_quantity": sell_q,
                    "total_buy_quantity":  buy_q,
                    "open":              round(op, 2),    # day open
                    "close":             round(cl, 2),    # prev close (post-market only)
                    "high":              round(hi, 2),    # day high
                    "low":               round(lo, 2),    # day low
                }

            # ── OI packet (type 5) ─────────────────────────────────────────
            if first_byte == 5 and len(data) >= 12:
                _, _, xch, sid, oi = struct.unpack('<BHBII', data[0:12])
                return {
                    "type":             "oi",
                    "exchange_segment": xch,
                    "security_id":      str(sid),
                    "OI":               oi,
                }

            # ── Full packet (type 8) ───────────────────────────────────────
            if first_byte == 8 and len(data) >= 162:
                unpacked = struct.unpack('<BHBIfHIfIIIIIIffff100s', data[0:162])
                return {
                    "type":              "full",
                    "exchange_segment":  unpacked[2],
                    "security_id":       str(unpacked[3]),
                    "LTP":               round(unpacked[4], 2),
                    "LTQ":               unpacked[5],
                    "LTT":               unpacked[6],
                    "avg_price":         round(unpacked[7], 2),
                    "volume":            unpacked[8],
                    "total_sell_quantity": unpacked[9],
                    "total_buy_quantity":  unpacked[10],
                    "OI":                unpacked[11],
                    "oi_day_high":       unpacked[12],
                    "oi_day_low":        unpacked[13],
                    "open":              round(unpacked[14], 2),
                    "close":             round(unpacked[15], 2),
                    "high":              round(unpacked[16], 2),
                    "low":               round(unpacked[17], 2),
                }

            # ── Server disconnect (type 50) ────────────────────────────────
            if first_byte == 50 and len(data) >= 10:
                _, _, _, _, code = struct.unpack('<BHBIH', data[0:10])
                disconnect_reasons = {
                    805: "Max WebSocket connections exceeded",
                    806: "Subscribe to Data APIs to continue",
                    807: "Access Token expired",
                    808: "Invalid Client ID",
                    809: "Authentication failed",
                }
                reason = disconnect_reasons.get(code, f"Unknown code {code}")
                return {"type": "disconnect", "code": code, "reason": reason}

        except (struct.error, IndexError):
            pass

        return None

    async def connect_and_stream(self):
        """
        Main WebSocket loop with exponential back-off reconnect.
        Uses v2 URL with credentials in query string.
        """
        self._running = True

        while self._running:
            try:
                url = self._ws_url()

                async with websockets.connect(
                    url,
                    ping_interval=25,
                    ping_timeout=10,
                    close_timeout=5,
                    max_size=2 ** 23,
                ) as ws:
                    self._ws = ws
                    self._reconnect_delay = 1

                    # Subscribe — group by request_code
                    await self._send_subscriptions(ws)

                    # Stream packets
                    async for message in ws:
                        if isinstance(message, bytes):
                            # Raw packet counter — bypasses all parsing
                            from api.websocket_manager import get_market_state as _gms
                            _st = _gms()
                            _cnt = _st.get_sync("_raw_packet_count") or 0
                            _st.set_sync("_raw_packet_count", _cnt + 1)
                            _st.set_sync("_raw_last_byte", message[0] if message else -1)

                            parsed = self._parse_packet(message)
                            if parsed:
                                if parsed.get("type") == "disconnect":
                                    # Log disconnect reason
                                    _st.set_sync("_ws_disconnect_code", parsed.get("code"))
                                    _st.set_sync("_ws_disconnect_reason", parsed.get("reason"))
                                    break
                                for cb in self._callbacks:
                                    try:
                                        await cb(parsed)
                                    except Exception:
                                        pass
                        elif isinstance(message, str):
                            try:
                                d = json.loads(message)
                            except json.JSONDecodeError:
                                pass

            except websockets.exceptions.InvalidStatusCode:
                pass
            except websockets.exceptions.ConnectionClosed:
                pass
            except Exception:
                pass

            if self._running:
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, self._max_reconnect_delay
                )

    async def _send_subscriptions(self, ws):
        """Group subscriptions by request_code and send as batched JSON messages."""
        groups: Dict[int, List[Dict]] = {}
        for instr in self._subscriptions:
            rc = instr.get("request_code", FeedRequestCode.FULL)
            groups.setdefault(rc, []).append(instr)

        for rc, instruments in groups.items():
            # Dhan recommends max 100 instruments per subscription message
            batch_size = 100
            for i in range(0, len(instruments), batch_size):
                batch = instruments[i:i + batch_size]
                msg = self._build_subscription_msg(batch, rc)
                await ws.send(msg)
                await asyncio.sleep(0.1)  # small gap between batches

    def stop(self):
        self._running = False


# ─── Singletons ───────────────────────────────────────────────────────────────

_dhan_client: Optional[DhanAPIClient] = None
_ws_client:   Optional[DhanWebSocketClient] = None


def get_dhan_client() -> DhanAPIClient:
    global _dhan_client
    if _dhan_client is None:
        _dhan_client = DhanAPIClient()
    return _dhan_client


def get_ws_client() -> DhanWebSocketClient:
    global _ws_client
    if _ws_client is None:
        s = get_settings()
        _ws_client = DhanWebSocketClient(s.DHAN_CLIENT_ID, s.DHAN_ACCESS_TOKEN)
    return _ws_client
