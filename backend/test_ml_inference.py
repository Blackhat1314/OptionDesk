"""Force ML inference with simulated candle history."""
import sys, asyncio, time
sys.path.insert(0, '/app')

async def test():
    from core.redis_cache import get_cache
    cache = get_cache()
    await cache.connect()
    chain = await cache.get('chain:NIFTY')
    if not chain:
        print('No chain in Redis')
        return

    spot = chain.get('spot_price', 0)
    atm  = chain.get('atm_strike', 0)
    rows = chain.get('rows', [])
    print(f'Spot: {spot}  ATM: {atm}  Rows: {len(rows)}')

    from features.ml_signals import _get_buffer, _buffers, run_ml_inference
    import features.ml_signals as ml

    # Simulate 25 snapshots 60s apart to create closed 15min candles
    now = time.time()
    for i in range(25):
        fake_ts = now - (25 - i) * 60
        for row in rows:
            strike = row.get('strike', 0)
            if abs(strike - atm) > 5 * 50:
                continue
            for side, opt_type in [('call', 'CALL'), ('put', 'PUT')]:
                opt = row.get(side, {})
                price  = float(opt.get('ltp', 0) or 0)
                volume = int(opt.get('volume', 0) or 0)
                oi     = int(opt.get('oi', 0) or 0)
                iv     = float(opt.get('iv', 0) or 0)
                if price <= 0:
                    continue
                buf = _get_buffer(strike, opt_type)
                buf['15m'].push(price, volume, oi, iv, fake_ts)
                buf['60m'].push(price, volume, oi, iv, fake_ts)
                buf['5m'].push(price, volume, oi, iv, fake_ts)

    print(f'Buffers populated: {len(_buffers)}')
    for k, v in list(_buffers.items())[:3]:
        closed = v['15m'].get_closed()
        print(f'  {k[0]} {k[1]}: 15m closed={len(closed)}')

    # Force inference
    ml._last_inference_ts = 0
    sigs = run_ml_inference(chain, spot)
    print(f'\nSignals: {len(sigs)}')
    for s in sigs:
        print(f"  {s['strike']} {s['type']}: {s['direction']} {s['confidence']*100:.0f}% conf")

    if not sigs:
        print('No signals — checking why...')
        # Check one strike manually
        from features.ml_signals import _build_feature_vector, _feat_cols, _scaler, _xgb_model, _lgb_model, _weights
        import numpy as np
        strike = atm
        opt_type = 'CALL'
        row = next((r for r in rows if r.get('strike') == strike), None)
        if row:
            call_iv = float(row.get('call', {}).get('iv', 0) or 0)
            put_iv  = float(row.get('put',  {}).get('iv', 0) or 0)
            fv = _build_feature_vector(
                strike=strike, opt_type=opt_type, spot=spot, atm_strike=atm,
                global_pcr=1.0, iv_percentile=0.5, oi_concentration=0.1,
                call_iv=call_iv, put_iv=put_iv, ts=time.time()
            )
            if fv is None:
                print('Feature vector is None — not enough candles')
            else:
                print(f'Feature vector built: {len(fv)} features')
                x = np.array([[fv.get(f, 0.0) for f in _feat_cols]], dtype=np.float32)
                x_scaled = _scaler.transform(x)
                p_xgb = _xgb_model.predict_proba(x_scaled)[0][1]
                p_lgb = _lgb_model.predict_proba(x_scaled)[0][1]
                prob  = _weights['xgb'] * p_xgb + _weights['lgb'] * p_lgb
                print(f'Raw prob: {prob:.4f} (threshold: 0.65)')
                print(f'Direction: {"UP" if prob >= 0.5 else "DOWN"}, Confidence: {max(prob, 1-prob)*100:.1f}%')

asyncio.run(test())
