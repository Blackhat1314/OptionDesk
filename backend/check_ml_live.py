"""Check ML buffers in the main process and run inference."""
import sys, asyncio
sys.path.insert(0, '/app')

async def check():
    from features.ml_signals import _buffers, run_ml_inference
    import features.ml_signals as ml
    from core.redis_cache import get_cache

    cache = get_cache()
    await cache.connect()
    chain = await cache.get('chain:NIFTY')
    if not chain:
        print('No chain in Redis')
        return

    spot = chain.get('spot_price', 0)
    atm  = chain.get('atm_strike', 0)
    print(f'Spot: {spot}  ATM: {atm}')
    print(f'Buffers in main process: {len(_buffers)}')

    for k, v in list(_buffers.items())[:6]:
        closed  = v['15m'].get_closed()
        current = v['15m']._current
        print(f'  {k[0]} {k[1]}: 15m_closed={len(closed)}, has_current={current is not None}')

    if not _buffers:
        print('No buffers — backend was just restarted, needs time to accumulate')
        return

    # Force inference
    ml._last_inference_ts = 0
    sigs = run_ml_inference(chain, spot)
    print(f'Signals: {len(sigs)}')
    for s in sigs[:5]:
        strike = s['strike']
        typ    = s['type']
        dirn   = s['direction']
        conf   = round(s['confidence'] * 100)
        strong = s.get('strong', False)
        print(f'  {strike} {typ}: {dirn} {conf}% {"STRONG" if strong else ""}')

    if sigs:
        await cache.set('ml:signals:NIFTY', sigs, ttl=900)
        print('Saved to Redis OK')
    else:
        print('No signals yet — need 2+ closed 15min candles per strike')

asyncio.run(check())
