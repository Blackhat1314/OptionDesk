"""Force ML inference and save to Redis."""
import sys, asyncio
sys.path.insert(0, '/app')

async def run():
    from core.redis_cache import get_cache
    import features.ml_signals as ml
    cache = get_cache()
    await cache.connect()
    chain = await cache.get('chain:NIFTY')
    if not chain:
        print('No chain in Redis')
        return
    spot = chain.get('spot_price', 0)
    print('Spot:', spot, 'ATM:', chain.get('atm_strike'))

    ml._last_inference_ts = 0  # force run
    sigs = ml.run_ml_inference(chain, spot)
    ml.update_signals(sigs)
    print('Signals generated:', len(sigs))

    if sigs:
        await cache.set('ml:signals:NIFTY', sigs, ttl=900)
        print('Saved to Redis OK')
        for s in sigs[:5]:
            strike = s['strike']
            typ    = s['type']
            dirn   = s['direction']
            conf   = s['confidence'] * 100
            strong = s.get('strong', False)
            print(f'  {strike} {typ}: {dirn} {conf:.0f}% {"STRONG" if strong else ""}')
    else:
        print('No signals — model may need more candle history')

asyncio.run(run())
