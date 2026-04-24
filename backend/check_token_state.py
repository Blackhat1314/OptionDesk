import asyncio, sys, json, base64, time
sys.path.insert(0, '/app')

async def test():
    from api.dhan_client import get_dhan_client, get_ws_client

    def decode(t):
        try:
            p = json.loads(base64.b64decode(t.split('.')[1]+'==').decode())
            typ = p.get('tokenConsumerType', '?')
            exp = p.get('exp', 0)
            expired = exp < time.time()
            exp_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(exp))
            return typ, expired, exp_str
        except Exception as e:
            return '?', True, str(e)

    rest = get_dhan_client()
    ws   = get_ws_client()

    rt, re, rs = decode(rest.access_token)
    wt, we, ws_exp = decode(ws.access_token)
    print(f'REST token: type={rt}, expired={re}, exp={rs}')
    print(f'WS   token: type={wt}, expired={we}, exp={ws_exp}')
    print(f'WS running: {ws._running}')
    print(f'WS connected: {ws._ws is not None}')

    from api.websocket_manager import get_market_state
    st = get_market_state()
    print(f'tick_count : {st.get_sync("_tick_count")}')
    print(f'raw_packets: {st.get_sync("_raw_packet_count")}')
    print(f'nifty_ltp  : {st.get_sync("ltp:13")}')
    print(f'disconnect : {st.get_sync("_ws_disconnect_reason")}')

asyncio.run(test())
