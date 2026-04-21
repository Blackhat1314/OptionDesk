"""Verify all calculations using live data from Redis."""
import asyncio, math, json
from calculations.black_scholes import (
    bs_call_price, bs_put_price, delta, gamma, theta, vega,
    implied_volatility, compute_all_greeks, days_to_expiry,
    compute_max_pain, compute_pcr, compute_gamma_exposure
)
from config import get_settings
settings = get_settings()
r = settings.RISK_FREE_RATE


async def verify():
    from core.redis_cache import get_cache
    cache = get_cache()
    await cache.connect()

    chain_data = await cache.get("chain:NIFTY")
    if not chain_data:
        print("No chain in Redis")
        return

    spot   = chain_data["spot_price"]
    expiry = chain_data["expiry"]
    rows   = chain_data["rows"]
    T      = days_to_expiry(expiry)

    print(f"NIFTY Spot: {spot}")
    print(f"Expiry: {expiry}, T={T:.4f}yr ({T*365:.1f}d)")
    print(f"Rows: {len(rows)}")

    # Get ATM row
    atm = next((r for r in rows if r.get("is_atm")), rows[len(rows)//2])
    K = atm["strike"]
    call = atm["call"]
    put  = atm["put"]

    print(f"\n=== ATM Strike {K} ===")
    print(f"Call: LTP={call['ltp']} IV={call['iv']}% OI={call['oi']:,}")
    print(f"Put:  LTP={put['ltp']}  IV={put['iv']}% OI={put['oi']:,}")

    # ── 1. IV Verification ────────────────────────────────────────────────────
    print("\n--- 1. IV VERIFICATION ---")
    if call["ltp"] > 0 and T > 0:
        comp_iv = implied_volatility(call["ltp"], spot, K, r, T, "CE") * 100
        dhan_iv = call["iv"]
        diff = abs(dhan_iv - comp_iv)
        print(f"Dhan IV:    {dhan_iv:.2f}%")
        print(f"Computed IV: {comp_iv:.2f}%")
        print(f"Difference: {diff:.2f}% {'✓ GOOD' if diff < 2.0 else '⚠ CHECK'}")

        # Also verify put IV
        if put["ltp"] > 0:
            comp_put_iv = implied_volatility(put["ltp"], spot, K, r, T, "PE") * 100
            print(f"Put IV: Dhan={put['iv']:.2f}% Computed={comp_put_iv:.2f}%")
            # Call IV ≈ Put IV for ATM (put-call parity)
            iv_diff = abs(call["iv"] - put["iv"])
            print(f"Call-Put IV diff: {iv_diff:.2f}% {'✓' if iv_diff < 3 else '⚠ skew present'}")

    # ── 2. Greeks Verification ────────────────────────────────────────────────
    print("\n--- 2. GREEKS VERIFICATION ---")
    iv_d = call["iv"] / 100.0 if call["iv"] > 0 else 0.15
    bs = compute_all_greeks(spot, K, r, iv_d, T, "CE")
    bs_put = compute_all_greeks(spot, K, r, iv_d, T, "PE")

    print(f"BS Greeks (σ={iv_d*100:.1f}%, T={T*365:.1f}d):")
    print(f"  Call Delta: {bs.delta:.4f} (Dhan: {call['greeks']['delta']:.4f})")
    print(f"  Gamma:      {bs.gamma:.6f} (Dhan: {call['greeks']['gamma']:.6f})")
    print(f"  Theta/day:  {bs.theta:.4f} (Dhan: {call['greeks']['theta']:.4f})")
    print(f"  Vega/1%:    {bs.vega:.4f}  (Dhan: {call['greeks']['vega']:.4f})")

    # Sanity checks
    print(f"\nSanity checks:")
    print(f"  ATM call delta 0.4-0.7: {0.4 < bs.delta < 0.7} {'✓' if 0.4 < bs.delta < 0.7 else '✗'}")
    print(f"  Gamma > 0: {bs.gamma > 0} {'✓' if bs.gamma > 0 else '✗'}")
    print(f"  Theta < 0: {bs.theta < 0} {'✓' if bs.theta < 0 else '✗'}")
    print(f"  Vega > 0: {bs.vega > 0} {'✓' if bs.vega > 0 else '✗'}")

    # Delta parity: call_delta - put_delta = 1 (exactly, not approximately)
    delta_parity = bs.delta - bs_put.delta
    print(f"  Delta parity (C-P=1): {delta_parity:.4f} {'✓' if abs(delta_parity - 1.0) < 0.001 else '✗'}")

    # Theta-Gamma relationship: theta ≈ -0.5 * sigma² * S² * gamma (per year)
    theta_from_gamma = -0.5 * (iv_d**2) * (spot**2) * bs.gamma
    print(f"\nTheta-Gamma check:")
    print(f"  -0.5σ²S²Γ = {theta_from_gamma:.4f}/yr = {theta_from_gamma/365:.4f}/day")
    print(f"  Actual theta = {bs.theta:.4f}/day")
    print(f"  Ratio: {bs.theta / (theta_from_gamma/365):.2f} (should be ~1 for ATM)")

    # ── 3. Put-Call Parity ────────────────────────────────────────────────────
    print("\n--- 3. PUT-CALL PARITY ---")
    if call["ltp"] > 0 and put["ltp"] > 0:
        # C - P = S - K*e^(-rT)
        lhs = call["ltp"] - put["ltp"]
        rhs = spot - K * math.exp(-r * T)
        diff = abs(lhs - rhs)
        print(f"C - P = {lhs:.2f}")
        print(f"S - Ke^(-rT) = {rhs:.2f}")
        print(f"Difference: {diff:.2f} {'✓ GOOD' if diff < 10 else '⚠ CHECK (may be bid-ask spread)'}")

    # ── 4. PCR Verification ───────────────────────────────────────────────────
    print("\n--- 4. PCR VERIFICATION ---")
    total_call_oi = sum(r["call"]["oi"] for r in rows)
    total_put_oi  = sum(r["put"]["oi"]  for r in rows)
    pcr = compute_pcr(total_call_oi, total_put_oi)
    print(f"Total Call OI: {total_call_oi:,}")
    print(f"Total Put OI:  {total_put_oi:,}")
    print(f"PCR = {pcr:.4f} (>1 = more puts = bearish hedge)")
    assert pcr >= 0, "PCR must be non-negative"
    print("PCR sanity: ✓")

    # ── 5. Max Pain Verification ──────────────────────────────────────────────
    print("\n--- 5. MAX PAIN VERIFICATION ---")
    strikes  = [r["strike"] for r in rows]
    call_ois = [r["call"]["oi"] for r in rows]
    put_ois  = [r["put"]["oi"]  for r in rows]
    mp = compute_max_pain(strikes, call_ois, put_ois)
    dist = abs(mp - spot) / spot * 100
    print(f"Max Pain: {mp} (spot={spot:.0f}, dist={dist:.1f}%)")
    print(f"Max Pain within 5% of spot: {'✓' if dist < 5 else '⚠ check'}")

    # ── 6. GEX Verification ───────────────────────────────────────────────────
    print("\n--- 6. GEX VERIFICATION ---")
    exposure = await cache.get("exposure:NIFTY")
    if exposure:
        print(f"Total GEX: {exposure['total_gex']:.4f} Cr")
        print(f"Total DEX: {exposure['total_dex']:.4f} Cr")
        print(f"Gamma Flip: {exposure['gamma_flip_level']:.0f}")
        print(f"Call Wall: {exposure['call_wall']:.0f}")
        print(f"Put Wall:  {exposure['put_wall']:.0f}")

        # Manual GEX for ATM
        lot = 50
        gex_manual = compute_gamma_exposure(spot, K, r, iv_d, T, call["oi"], "CE", lot)
        gex_manual_cr = gex_manual / 1e9
        print(f"\nManual ATM Call GEX: {gex_manual_cr:.4f} Cr")
        print(f"Formula: Γ×OI×lot×S²×0.01 = {bs.gamma:.6f}×{call['oi']:,}×{lot}×{spot:.0f}²×0.01")

    # ── 7. IV Analytics Verification ─────────────────────────────────────────
    print("\n--- 7. IV ANALYTICS ---")
    iv_data = await cache.get("iv:NIFTY")
    if iv_data:
        print(f"ATM IV:    {iv_data['current_iv']:.2f}%")
        print(f"HV 30d:    {iv_data['historical_vol_30d']:.2f}%")
        print(f"IV-HV:     {iv_data['iv_rv_spread']:.2f}%")
        print(f"IV Rank:   {iv_data['iv_rank']:.1f}/100")
        print(f"IV Pct:    {iv_data['iv_percentile']:.1f}/100")

        # NIFTY IV typically 10-30%
        if iv_data["current_iv"] > 0:
            in_range = 5 < iv_data["current_iv"] < 60
            print(f"IV in normal range (5-60%): {'✓' if in_range else '✗'}")

    # ── 8. VWAP Verification ──────────────────────────────────────────────────
    print("\n--- 8. VWAP VERIFICATION ---")
    from features.vwap import get_vwap_engine
    engine = get_vwap_engine("NIFTY")
    v = engine.vwap
    std = engine.vwap_std
    lb1, ub1 = engine.bands(1.0)
    print(f"VWAP: {v:.2f}")
    print(f"Std:  {std:.2f}")
    print(f"+1σ:  {ub1:.2f}")
    print(f"-1σ:  {lb1:.2f}")
    if v > 0:
        print(f"Spot vs VWAP: {((spot-v)/v*100):.2f}%")
        print(f"VWAP > 0: ✓")

    # ── 9. Regime Verification ────────────────────────────────────────────────
    print("\n--- 9. REGIME VERIFICATION ---")
    from features.regime import get_regime
    regime = get_regime("NIFTY")
    print(f"Regime: {regime['regime']}")
    print(f"Entropy: {regime['entropy']:.4f} (0=ordered, 1=random)")
    print(f"Vol 20d: {regime['volatility_20d']:.2f}%")
    print(f"Hurst:   {regime['hurst']:.4f} (>0.5=trending, <0.5=mean-reverting)")
    print(f"Signal:  {regime['signal']}")

    # Hurst should be 0-1
    assert 0 <= regime["hurst"] <= 1, f"Hurst out of range: {regime['hurst']}"
    print("Regime sanity: ✓")

    print("\n" + "="*60)
    print("ALL VERIFICATIONS COMPLETE ✓")
    print("="*60)


asyncio.run(verify())
