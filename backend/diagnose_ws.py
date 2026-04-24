"""
WS Tick Diagnostic — run inside the backend container:
  docker exec optionsdesk_backend python3 /app/diagnose_ws.py
"""
import asyncio
import json
import sys
import time
import struct
from urllib.parse import urlencode

sys.path.insert(0, '/app')

async def main():
    from config import get_settings
    s = get_settings()

    print("=" * 60)
    print("STEP 1: Token info")
    print("=" * 60)
    token = s.DHAN_ACCESS_TOKEN
    print(f"  Client ID : {s.DHAN_CLIENT_ID}")
    print(f"  Token len : {len(token)}")
    print(f"  Token start: {token[:40]}...")

    # Decode JWT to check expiry
    try:
        import base64
        parts = token.split(".")
        payload_b64 = parts[1] + "=="
        payload = json.loads(base64.b64decode(payload_b64).decode())
        exp = payload.get("exp", 0)
        token_type = payload.get("tokenConsumerType", "?")
        exp_dt = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(exp))
        now = time.time()
        if exp < now:
            print(f"  ❌ TOKEN EXPIRED at {exp_dt} ({int((now-exp)/3600)}h ago)")
        else:
            print(f"  ✅ Token valid until {exp_dt} ({int((exp-now)/3600)}h left)")
        print(f"  Token type: {token_type}")
        if token_type == "APP":
            print("  ⚠️  APP token — WS feed requires SELF token!")
            print("     Get SELF token from: https://web.dhan.co → Profile → API Access")
    except Exception as e:
        print(f"  Could not decode token: {e}")

    print()
    print("=" * 60)
    print("STEP 2: REST API test (NIFTY LTP)")
    print("=" * 60)
    try:
        from api.dhan_client import get_dhan_client
        dhan = get_dhan_client()
        resp = await asyncio.wait_for(dhan.get_ltp([13], 'IDX_I'), timeout=10.0)
        ltp = resp.get('data', {}).get('IDX_I', {}).get('13', {}).get('last_price', None)
        if ltp:
            print(f"  ✅ REST API works — NIFTY LTP: {ltp}")
        else:
            print(f"  ❌ REST API returned no data: {resp}")
    except Exception as e:
        print(f"  ❌ REST API failed: {type(e).__name__}: {e}")

    print()
    print("=" * 60)
    print("STEP 3: Raw WebSocket connection test")
    print("=" * 60)
    try:
        import websockets
        params = urlencode({
            'version': '2',
            'token': token,
            'clientId': s.DHAN_CLIENT_ID,
            'authType': '2',
        })
        url = f"wss://api-feed.dhan.co?{params}"
        print(f"  Connecting to: wss://api-feed.dhan.co?version=2&clientId={s.DHAN_CLIENT_ID}&...")

        async with websockets.connect(url, ping_interval=None, close_timeout=5) as ws:
            print("  ✅ WebSocket connected!")

            # Send subscription for NIFTY (IDX_I, security_id=13, QUOTE mode)
            sub_msg = json.dumps({
                "RequestCode": 17,
                "InstrumentCount": 1,
                "InstrumentList": [{"ExchangeSegment": "IDX_I", "SecurityId": "13"}]
            })
            await ws.send(sub_msg)
            print(f"  Sent subscription: {sub_msg}")
            print("  Waiting for packets (10s timeout)...")

            packet_count = 0
            start = time.time()
            while time.time() - start < 10:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    packet_count += 1
                    if isinstance(msg, bytes):
                        first_byte = msg[0] if msg else -1
                        type_names = {2: "Ticker", 4: "Quote", 5: "OI", 6: "PrevClose", 8: "Full", 50: "Disconnect"}
                        type_name = type_names.get(first_byte, f"Unknown({first_byte})")
                        print(f"  ✅ Packet #{packet_count}: {len(msg)} bytes, type={type_name}")

                        # Try to parse Quote packet
                        if first_byte == 4 and len(msg) >= 50:
                            _, _, xch, sid, ltp, *_ = struct.unpack('<BHBIfHIfIIIffff', msg[0:50])
                            print(f"     → SID={sid}, LTP={ltp:.2f}, exchange={xch}")
                        elif first_byte == 2 and len(msg) >= 16:
                            _, _, xch, sid, ltp, ltt = struct.unpack('<BHBIfI', msg[0:16])
                            print(f"     → SID={sid}, LTP={ltp:.2f}, exchange={xch}")
                        elif first_byte == 50 and len(msg) >= 10:
                            _, _, _, _, code = struct.unpack('<BHBIH', msg[0:10])
                            codes = {805: "Max connections", 806: "Subscribe to Data APIs",
                                     807: "Token expired", 808: "Invalid Client ID", 809: "Auth failed"}
                            print(f"  ❌ DISCONNECT code={code}: {codes.get(code, 'Unknown')}")
                    else:
                        print(f"  Text message: {msg[:200]}")
                except asyncio.TimeoutError:
                    if packet_count == 0:
                        print("  ⏳ No packets yet...")
                    continue

            if packet_count == 0:
                print("  ❌ No packets received in 10 seconds!")
                print("     Possible causes:")
                print("     1. Token is APP type (needs SELF token for WS)")
                print("     2. Outbound port 443 blocked on VM")
                print("     3. Market is closed (no ticks outside 9:15-15:30 IST)")
            else:
                print(f"  ✅ Received {packet_count} packets total")

    except Exception as e:
        status = getattr(e, 'status_code', None)
        print(f"  ❌ WS connection failed: {type(e).__name__}: {e}")
        if status == 429:
            print("     → HTTP 429: Dhan is rate-limiting — too many reconnect attempts")
            print("     → Wait 5 minutes then restart backend: docker compose restart backend")
        elif status == 401:
            print("     → HTTP 401: Token invalid or expired")
        elif status == 403:
            print("     → HTTP 403: Token doesn't have WS feed access (APP token?)")

    print()
    print("=" * 60)
    print("STEP 4: Check current market state")
    print("=" * 60)
    from api.websocket_manager import get_market_state
    state = get_market_state()
    print(f"  tick_count      : {state.get_sync('_tick_count')}")
    print(f"  raw_packet_count: {state.get_sync('_raw_packet_count')}")
    print(f"  nifty_ltp (ltp:13): {state.get_sync('ltp:13')}")
    print(f"  disconnect_reason: {state.get_sync('_ws_disconnect_reason')}")
    print(f"  last_tick_raw   : {state.get_sync('_last_tick_raw')}")

    print()
    print("=" * 60)
    print("STEP 5: Market hours check")
    print("=" * 60)
    import pytz
    from datetime import datetime
    ist = pytz.timezone("Asia/Kolkata")
    now_ist = datetime.now(ist)
    mins = now_ist.hour * 60 + now_ist.minute
    is_open = now_ist.weekday() < 5 and 9 * 60 + 15 <= mins <= 15 * 60 + 30
    print(f"  Current IST time: {now_ist.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"  Market open: {'✅ YES' if is_open else '❌ NO (outside 9:15-15:30 Mon-Fri)'}")
    if not is_open:
        print("  ℹ️  Ticks only flow during market hours — this is expected!")

asyncio.run(main())
