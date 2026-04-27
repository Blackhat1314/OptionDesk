import sys, json, asyncio
sys.path.insert(0, '/app')

async def main():
    from core.redis_cache import get_cache
    cache = get_cache()
    await cache.connect()
    raw = await cache.get('chain:NIFTY')
    if not raw:
        print('No chain in Redis')
        return

    d = raw if isinstance(raw, dict) else json.loads(raw)
    atm = d.get('atm_strike', 0)
    rows = d.get('rows', [])
    spot = d.get('spot_price', 0)
    print('ATM:', atm)
    print('Spot:', spot)
    print('Total rows:', len(rows))
    strikes = sorted([r['strike'] for r in rows])
    print('All strikes:', strikes)
    atm_rows = [r for r in rows if abs(r['strike'] - atm) <= 250]
    print('ATM+-5 strikes:', sorted([r['strike'] for r in atm_rows]))

    from features.ml_signals import ingest_chain_for_ml, _buffers
    ingest_chain_for_ml(d, spot)
    print('Buffers after ingest:', len(_buffers))
    for k, v in list(_buffers.items())[:5]:
        closed = v['15m'].get_closed()
        print(f'  Strike={k[0]} {k[1]}: 15m closed={len(closed)}')

asyncio.run(main())
