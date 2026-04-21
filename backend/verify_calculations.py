"""
Comprehensive calculation verification against live market data.
Tests: Black-Scholes, Greeks, IV, GEX, PCR, Max Pain, VWAP, Regime, HV
"""
import asyncio, math, time
from calculations.black_scholes import (
    bs_call_price, bs_put_price, delta, gamma, theta, vega,
    implied_volatility, compute_max_pain, compute_pcr,
    compute_gamma_exposure, days_to_expiry
)
from scipy.stats import norm


# ─── 1. Black-Scholes Verification ───────────────────────────────────────────
print("=" * 60)
print("1. BLACK-SCHOLES FORMULA VERIFICATION")
print("=" * 60)

# Known test case: S=100, K=100, r=5%, sigma=20%, T=1yr
# Expected call ≈ 10.45, put ≈ 5.57 (textbook values)
S, K, r, sigma, T = 100.0, 100.0, 0.05, 0.20, 1.0
call = bs_call_price(S, K, r, sigma, T)
put  = bs_put_price(S, K, r, sigma, T)
print(f"ATM Call (S=K=100, r=5%, σ=20%, T=1Y): {call:.4f} (expected ~10.45)")
print(f"ATM Put  (S=K=100, r=5%, σ=20%, T=1Y): {put:.4f}  (expected ~5.57)")

# Put-Call Parity: C - P = S - K*e^(-rT)
parity_lhs = call - put
parity_rhs = S - K * math.exp(-r * T)
print(f"Put-Call Parity: C-P={parity_lhs:.4f}, S-Ke^(-rT)={parity_rhs:.4f} ✓" if abs(parity_lhs - parity_rhs) < 0.001 else "PUT-CALL PARITY FAILED ✗")

# ─── 2. Greeks Verification ───────────────────────────────────────────────────
print("\n" + "=" * 60)
print("2. GREEKS VERIFICATION")
print("=" * 60)

# ATM call delta should be ~0.5-0.6 (slightly above 0.5 due to drift)
d = delta(S, K, r, sigma, T, "CE")
print(f"ATM Call Delta: {d:.4f} (expected 0.53-0.58)")
assert 0.50 < d < 0.65, f"Delta out of range: {d}"

# ATM put delta should be ~-0.4 to -0.5
d_put = delta(S, K, r, sigma, T, "PE")
print(f"ATM Put Delta:  {d_put:.4f} (expected -0.42 to -0.47)")
assert -0.50 < d_put < -0.35, f"Put delta out of range: {d_put}"

# Delta call + |Delta put| should ≈ 1 (not exactly due to discounting)
print(f"Call Delta + |Put Delta| = {d + abs(d_put):.4f} (expected ~1.0)")

# Gamma should be same for call and put (same formula)
g_call = gamma(S, K, r, sigma, T)
print(f"ATM Gamma: {g_call:.6f} (should be positive)")
assert g_call > 0, "Gamma must be positive"

# Theta should be negative (time decay)
t_call = theta(S, K, r, sigma, T, "CE")
t_put  = theta(S, K, r, sigma, T, "PE")
print(f"Call Theta (per day): {t_call:.4f} (should be negative)")
print(f"Put Theta  (per day): {t_put:.4f}  (should be negative for ATM)")
assert t_call < 0, f"Call theta should be negative: {t_call}"

# Vega should be same for call and put
v_call = vega(S, K, r, sigma, T)
print(f"Vega (per 1% IV): {v_call:.4f} (should be positive)")
assert v_call > 0, "Vega must be positive"

# ─── 3. Implied Volatility Verification ──────────────────────────────────────
print("\n" + "=" * 60)
print("3. IMPLIED VOLATILITY ROUND-TRIP")
print("=" * 60)

# Compute price at known sigma, then recover sigma from price
for test_sigma in [0.10, 0.15, 0.20, 0.25, 0.30, 0.40]:
    price = bs_call_price(S, K, r, test_sigma, T)
    recovered = implied_volatility(price, S, K, r, T, "CE")
    error = abs(recovered - test_sigma)
    status = "✓" if error < 0.001 else "✗ ERROR"
    print(f"  σ={test_sigma:.2f} → price={price:.4f} → recovered σ={recovered:.4f} {status}")

# ─── 4. Live Market Verification ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("4. LIVE MARKET DATA VERIFICATION")
print("=" * 60)

async def verify_live():
    from api.dhan_client import get_dhan_client
    from core.analytics_processor import process_option_chain, compute_greeks_exposure, compute_iv_analytics
    from calculations.black_scholes import days_to_expiry
    from config import get_settings

    dhan = get_dhan_client()
    settings = get_settings()
    r = settings.RISK_FREE_RATE

    # Get live NIFTY data
    expiries = await dhan.get_option_expiries("NIFTY")
    expiry = expiries[0] if expiries else None
    if not expiry:
        print("No expiry available")
        return

    # Get spot
    ltp_resp = await dhan.get_ltp([13], "IDX_I")
    seg_data = ltp_resp.get("data", {}).get("IDX_I", {})
    q = seg_data.get("13") or seg_data.get(13) or {}
    spot = float(q.get("last_price") or 0)
    print(f"NIFTY Spot: {spot}")
    print(f"Expiry: {expiry}")

    T = days_to_expiry(expiry)
    print(f"Time to expiry: {T:.6f} years ({T*365:.1f} days)")

    # Get option chain
    raw = await dhan.get_option_chain("NIFTY", expiry)
    chain = process_option_chain(raw, "NIFTY", expiry, spot)

    print(f"\nChain rows: {len(chain.rows)}")
    print(f"ATM strike: {chain.atm_strike}")

    # Find ATM row
    atm = next((r for r in chain.rows if r.is_atm), None)
    if not atm:
        print("No ATM row found")
        await dhan.close()
        return

    print(f"\n--- ATM Strike {atm.strike} ---")
    print(f"Call LTP: {atm.call.ltp}  Put LTP: {atm.put.ltp}")
    print(f"Call IV:  {atm.call.iv}%  Put IV:  {atm.put.iv}%")
    print(f"Call OI:  {atm.call.oi:,}  Put OI:  {atm.put.oi:,}")

    # Verify IV by recomputing from LTP
    if atm.call.ltp > 0 and spot > 0 and T > 0:
        computed_iv = implied_volatility(atm.call.ltp, spot, atm.strike, r, T, "CE")
        print(f"\nIV Verification (ATM Call):")
        print(f"  Dhan IV:    {atm.call.iv:.2f}%")
        print(f"  Computed IV: {computed_iv*100:.2f}%")
        diff = abs(atm.call.iv - computed_iv*100)
        print(f"  Difference: {diff:.2f}% {'✓ OK' if diff < 2.0 else '⚠ CHECK'}")

    # Verify Greeks
    if atm.call.ltp > 0 and T > 0:
        iv_dec = atm.call.iv / 100.0 if atm.call.iv > 0 else 0.15
        from calculations.black_scholes import compute_all_greeks
        bs_greeks = compute_all_greeks(spot, atm.strike, r, iv_dec, T, "CE")
        print(f"\nGreeks Verification (ATM Call, σ={iv_dec*100:.1f}%):")
        print(f"  Delta:  Dhan={atm.call.greeks.delta:.4f}  BS={bs_greeks.delta:.4f}")
        print(f"  Gamma:  Dhan={atm.call.greeks.gamma:.6f}  BS={bs_greeks.gamma:.6f}")
        print(f"  Theta:  Dhan={atm.call.greeks.theta:.4f}  BS={bs_greeks.theta:.4f}")
        print(f"  Vega:   Dhan={atm.call.greeks.vega:.4f}  BS={bs_greeks.vega:.4f}")

        # Sanity checks
        assert 0.4 < bs_greeks.delta < 0.7, f"ATM call delta out of range: {bs_greeks.delta}"
        assert bs_greeks.gamma > 0, "Gamma must be positive"
        assert bs_greeks.theta < 0, "Theta must be negative"
        assert bs_greeks.vega > 0, "Vega must be positive"
        print("  All Greeks sanity checks: ✓")

    # Verify PCR
    exposure = compute_greeks_exposure(chain, "NIFTY")
    iv_analytics = compute_iv_analytics(chain, "NIFTY")
    from core.analytics_processor import compute_market_summary
    summary = compute_market_summary(chain, "NIFTY")

    print(f"\n--- Market Summary ---")
    print(f"PCR OI:    {summary.pcr_oi:.4f} (>1 = bullish, <1 = bearish)")
    print(f"Max Pain:  {summary.max_pain}")
    print(f"ATM IV:    {summary.atm_iv:.2f}%")
    print(f"Total Call OI: {summary.total_call_oi:,}")
    print(f"Total Put OI:  {summary.total_put_oi:,}")

    # PCR sanity
    assert summary.pcr_oi >= 0, "PCR must be non-negative"
    print("PCR sanity: ✓")

    # Max Pain sanity — should be within ±5% of spot
    if summary.max_pain > 0:
        mp_dist = abs(summary.max_pain - spot) / spot * 100
        print(f"Max Pain distance from spot: {mp_dist:.1f}% {'✓' if mp_dist < 10 else '⚠ far from spot'}")

    print(f"\n--- GEX/DEX ---")
    print(f"Total GEX: {exposure.total_gex:.4f} Cr")
    print(f"Total DEX: {exposure.total_dex:.4f} Cr")
    print(f"Gamma Flip: {exposure.gamma_flip_level:.0f}")
    print(f"Call Wall:  {exposure.call_wall:.0f}")
    print(f"Put Wall:   {exposure.put_wall:.0f}")

    # GEX sanity: call wall should be above spot, put wall below
    if exposure.call_wall > 0 and exposure.put_wall > 0:
        print(f"Call Wall > Spot: {exposure.call_wall > spot} {'✓' if exposure.call_wall > spot else '⚠'}")
        print(f"Put Wall < Spot:  {exposure.put_wall < spot} {'✓' if exposure.put_wall < spot else '⚠'}")

    print(f"\n--- IV Analytics ---")
    print(f"ATM IV:     {iv_analytics.current_iv:.2f}%")
    print(f"HV 30d:     {iv_analytics.historical_vol_30d:.2f}%")
    print(f"IV-RV Spread: {iv_analytics.iv_rv_spread:.2f}%")
    print(f"IV Rank:    {iv_analytics.iv_rank:.1f}/100")
    print(f"IV Pct:     {iv_analytics.iv_percentile:.1f}/100")

    # IV sanity: NIFTY IV typically 10-30%
    if iv_analytics.current_iv > 0:
        assert 5 < iv_analytics.current_iv < 60, f"IV out of normal range: {iv_analytics.current_iv}"
        print("IV range sanity: ✓")

    await dhan.close()

asyncio.run(verify_live())

# ─── 5. GEX Formula Verification ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("5. GEX FORMULA VERIFICATION")
print("=" * 60)

# GEX = Gamma * OI * LotSize * Spot² * 0.01
# For NIFTY: lot=50, spot=24000, K=24000, sigma=15%, T=7/365
S_test = 24000.0
K_test = 24000.0
sigma_test = 0.15
T_test = 7/365
oi_test = 100000
lot_test = 50

g = gamma(S_test, K_test, 0.065, sigma_test, T_test)
gex = compute_gamma_exposure(S_test, K_test, 0.065, sigma_test, T_test, oi_test, "CE", lot_test)
gex_cr = gex / 1e9

print(f"Gamma at ATM (σ=15%, T=7d): {g:.8f}")
print(f"GEX = {g:.8f} × {oi_test:,} × {lot_test} × {S_test}² × 0.01")
print(f"GEX raw = {gex:.2f}")
print(f"GEX in Crores = {gex_cr:.4f} Cr")

# Manual verification
manual_gex = g * oi_test * lot_test * (S_test**2) * 0.01
print(f"Manual GEX = {manual_gex:.2f} {'✓' if abs(manual_gex - gex) < 1 else '✗'}")

# ─── 6. Max Pain Verification ─────────────────────────────────────────────────
print("\n" + "=" * 60)
print("6. MAX PAIN VERIFICATION")
print("=" * 60)

# Simple test: if all OI is at one strike, max pain = that strike
strikes = [24000, 24100, 24200, 24300, 24400]
call_oi = [10000, 5000, 2000, 1000, 500]
put_oi  = [500, 1000, 2000, 5000, 10000]

mp = compute_max_pain(strikes, call_oi, put_oi)
print(f"Max Pain test: {mp} (expected ~24200 — balanced OI)")
# Max pain should be near the middle where total pain is minimized
assert 24100 <= mp <= 24300, f"Max pain out of expected range: {mp}"
print("Max Pain sanity: ✓")

print("\n" + "=" * 60)
print("ALL VERIFICATIONS COMPLETE")
print("=" * 60)
