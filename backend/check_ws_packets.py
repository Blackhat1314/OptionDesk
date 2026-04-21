"""
Test Dhan WebSocket directly — connect and print raw packets for 10 seconds.
"""
import asyncio, struct, json, time, sys
from urllib.parse import urlencode
import websockets
from config import get_settings

settings = get_settings()

async def test():
    params = urlencode({
        "version":  "2",
        "token":    settings.DHAN_ACCESS_TOKEN,
        "clientId": settings.DHAN_CLIENT_ID,
        "authType": "2",
    })
    url = f"wss://api-feed.dhan.co?{params}"
    print(f"Connecting...", flush=True)

    try:
        async with websockets.connect(url, ping_interval=25, ping_timeout=10, close_timeout=5,
                                       open_timeout=10) as ws:
            print("Connected!", flush=True)

            sub_msg = json.dumps({
                "RequestCode": 21,
                "InstrumentCount": 1,
                "InstrumentList": [{"ExchangeSegment": "IDX_I", "SecurityId": "13"}]
            })
            await ws.send(sub_msg)
            print(f"Subscribed to NIFTY (IDX_I:13)", flush=True)

            deadline = time.time() + 10
            count = 0

            while time.time() < deadline:
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    count += 1
                    if isinstance(message, bytes):
                        fb = message[0] if message else 0
                        print(f"[{count}] bytes len={len(message)} type={fb}", flush=True)
                        if fb == 2 and len(message) >= 16:
                            _, _, xch, sid, ltp, ltt = struct.unpack('<BHBIfI', message[0:16])
                            print(f"  TICKER sid={sid} LTP={ltp:.2f}", flush=True)
                        elif fb == 8 and len(message) >= 162:
                            v = struct.unpack('<BHBIfHIfIIIIIIffff100s', message[0:162])
                            print(f"  FULL sid={v[3]} LTP={v[4]:.2f}", flush=True)
                        elif fb == 50:
                            print(f"  DISCONNECT: {message.hex()}", flush=True)
                    else:
                        print(f"[{count}] text: {message[:100]}", flush=True)
                except asyncio.TimeoutError:
                    print(".", end="", flush=True)

            print(f"\nDone. Total packets: {count}", flush=True)

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", flush=True)

asyncio.run(test())
