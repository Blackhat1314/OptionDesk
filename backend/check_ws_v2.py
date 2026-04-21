"""
Test Dhan WS v2 with exact format from docs.
Tests both Ticker (15) and Full (21) request codes.
"""
import asyncio, struct, json, time
from urllib.parse import urlencode
import websockets
from config import get_settings

settings = get_settings()


def parse_header(data: bytes):
    """Parse 8-byte response header."""
    if len(data) < 8:
        return None
    # Bytes: 1=code, 2-3=length(int16), 4=exchange, 5-8=security_id(int32)
    code = data[0]
    msg_len = struct.unpack('<H', data[1:3])[0]
    exchange = data[3]
    security_id = struct.unpack('<I', data[4:8])[0]
    return code, msg_len, exchange, security_id


async def test():
    params = urlencode({
        "version":  "2",
        "token":    settings.DHAN_ACCESS_TOKEN,
        "clientId": settings.DHAN_CLIENT_ID,
        "authType": "2",
    })
    url = f"wss://api-feed.dhan.co?{params}"
    print(f"Connecting to: {url[:80]}...")

    try:
        async with websockets.connect(
            url,
            ping_interval=25,
            ping_timeout=10,
            close_timeout=5,
            open_timeout=10,
        ) as ws:
            print("✓ Connected!")

            # Test 1: Subscribe with Ticker (RequestCode=15) for NIFTY index
            sub1 = {
                "RequestCode": 15,
                "InstrumentCount": 1,
                "InstrumentList": [
                    {"ExchangeSegment": "IDX_I", "SecurityId": "13"}
                ]
            }
            await ws.send(json.dumps(sub1))
            print(f"Sent Ticker subscription: {sub1}")

            # Wait 5s for ticker packets
            print("Waiting 5s for Ticker packets...")
            deadline = time.time() + 5
            count = 0
            while time.time() < deadline:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    count += 1
                    if isinstance(msg, bytes):
                        print(f"  [{count}] Binary {len(msg)} bytes: {msg[:16].hex()}")
                        if len(msg) >= 8:
                            hdr = parse_header(msg)
                            print(f"       Header: code={hdr[0]} len={hdr[1]} exchange={hdr[2]} security_id={hdr[3]}")
                        if len(msg) >= 16 and msg[0] == 2:
                            ltp = struct.unpack('<f', msg[8:12])[0]
                            ltt = struct.unpack('<I', msg[12:16])[0]
                            print(f"       TICKER: LTP={ltp:.2f} LTT={ltt}")
                        elif len(msg) >= 16 and msg[0] == 6:
                            prev_close = struct.unpack('<f', msg[8:12])[0]
                            print(f"       PREV_CLOSE: {prev_close:.2f}")
                    else:
                        print(f"  [{count}] Text: {msg[:100]}")
                except asyncio.TimeoutError:
                    print("  (no packet)")

            print(f"\nTicker test: {count} packets in 5s")

            # Test 2: Upgrade to Full (RequestCode=21)
            sub2 = {
                "RequestCode": 21,
                "InstrumentCount": 1,
                "InstrumentList": [
                    {"ExchangeSegment": "IDX_I", "SecurityId": "13"}
                ]
            }
            await ws.send(json.dumps(sub2))
            print(f"\nSent Full subscription: {sub2}")

            print("Waiting 5s for Full packets...")
            deadline = time.time() + 5
            count2 = 0
            while time.time() < deadline:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    count2 += 1
                    if isinstance(msg, bytes):
                        print(f"  [{count2}] Binary {len(msg)} bytes: {msg[:16].hex()}")
                        if len(msg) >= 8:
                            hdr = parse_header(msg)
                            print(f"       Header: code={hdr[0]} len={hdr[1]} exchange={hdr[2]} security_id={hdr[3]}")
                        if len(msg) >= 12 and msg[0] in (2, 4, 8):
                            ltp = struct.unpack('<f', msg[8:12])[0]
                            print(f"       LTP={ltp:.2f}")
                    else:
                        print(f"  [{count2}] Text: {msg[:100]}")
                except asyncio.TimeoutError:
                    print("  (no packet)")

            print(f"\nFull test: {count2} packets in 5s")

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


asyncio.run(test())
