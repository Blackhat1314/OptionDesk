"""Verify live calculations with next week's expiry."""
import asyncio, math
from calculations.black_scholes import (
    implied_volatility, compute_all_greeks, days_to_expiry,
    compute_max_pain, compute_pcr
)
from config import get_settings

settings = get_settings()
r = settings.RISK_FREE_RATE


async def verify():
    from api.dhan_client import get_dhan_client
    from core.analytics_processor import (
        process_option_chain, compute_greeks_exposure,
        compute_iv_analytics, compute_market_summary
    )

    dhan = get_dhan_client()

    # Get all expiries and use the second one (next week)
    expiries = await dhan.get_option_expiries("NIFTY")
    print(f"Available expiries: {expiries}")

    # Use expiry with most time (last one in list)
    expiry = expiries[-1] if len(expiries) > 1 else expiries[0]
    print(f"Using expiry: {expiry}")

    # Get spot
    ltp_resp = await dhan.get_ltp([13], "IDX_I")
    seg_data = ltp_resp.get("data", {}).get("IDX_I", {})
    q = seg_data.get("13") or seg_data.get(13) or {}
    spot = float(q.get("last_price") or 0)
    print(f"NIFTY Spot: {spot}")

    T = days_to_expiry(expiry)
    print(f"T = {T:.4f} years ({T*365:.1f} days)")

    # Get chain
    raw = await dhan.get_option_chain("NIFTY", expiry)
    chain = process_option_chain(raw, "NIFTY", expiry, spot)
    print(f"Chain rows: {len(chain.rows)}, ATM: {chain.atm_strike}")

    if not chain.rows:
        print("Empty chain — market may be closed or expiry has no data")
        await dhan.close()
        return

    # ATM row
    atm = next((r for r in chain.rows if r.is_atm), chain.rows[len(chain.rows)//2])
    print(f"\n=== ATM Strike {atm.strike} ===")
    print(f"Call: LTP={atm.call.ltp} IV={atm.call.iv}% OI={atm.call.oi:,}")
    print(f"Put:  LTP={atm.put.ltp}  IV={atm.put.iv}% OI={atm.put.oi:,}")

    # IV verification
    if atm.call.ltp > 0 and T > 0:
        comp_iv = implied_volatility(atm.call.ltp, spot, atm.strike, r, T, "CE")
        print(f"\nIV Check: Dhan={atm.call.iv:.2f}% Computed={comp_iv*100:.2f}% Diff={abs(atm.call.iv - comp_iv*100):.2f}%")

    # Greeks verification
    if atm.call.iv > 0 and T > 0:
        iv_d = atm.call.iv / 100.0
        bs = compute_all_greeks(spot, atm.strike, r, iv_d, T, "CE")
        print(f"\nGreeks (BS computed at σ={atm.call.iv:.1f}%):")
        print(f"  Delta: {bs.delta:.4f} (ATM call should be 0.45-0.60)")
        print(f"  Gamma: {bs.gamma:.6f} (should be positive)")
        print(f"  Theta: {bs.theta:.4f} (should be negative, per day)")
        print(f"  Vega:  {bs.vega:.4f}  (should be positive, per 1% IV)")

        # Theta annualized check: theta * 365 should ≈ -0.5 * sigma² * S * gamma * S
        # (rough approximation for ATM)
        theta_check = -0.5 * (iv_d**2) * (spot**2) * bs.gamma
        print(f"\nTheta sanity (≈ -0.5σ²S²Γ/365): {theta_check/365:.4f} vs actual {bs.theta:.4f}")

        # Put-call parity for Greeks: call_delta - put_delta = 1 (approximately)
        bs_put = compute_all_greeks(spot, atm.strike, r, iv_d, T, "PE")
        delta_sum = bs.delta + abs(bs_put.delta)
        print(f"Delta parity (call_Δ + |put_Δ|): {delta_sum:.4f} (should be ~1.0)")

    # Market summary
    summary = compute_market_summary(chain, "NIFTY")
    print(f"\n=== Market Summary ===")
    print(f"PCR OI:   {summary.pcr_oi:.3f}")
    print(f"Max Pain: {summary.max_pain}")
    print(f"ATM IV:   {summary.atm_iv:.2f}%")

    # Max pain should be within 3% of spot
    if summary.max_pain > 0:
        dist = abs(summary.max_pain - spot) / spot * 100
        print(f"Max Pain vs Spot: {dist:.1f}% away {'✓' if dist < 5 else '⚠ check'}")

    # GEX
    exposure = compute_greeks_exposure(chain, "NIFTY")
    print(f"\n=== GEX/DEX ===")
    print(f"Total GEX: {exposure.total_gex:.4f} Cr")
    print(f"Total DEX: {exposure.total_dex:.4f} Cr")
    print(f"Gamma Flip: {exposure.gamma_flip_level:.0f}")
    print(f"Call Wall:  {exposure.call_wall:.0f}")
    print(f"Put Wall:   {exposure.put_wall:.0f}")

    # GEX sign: positive = dealers long gamma (stabilizing)
    print(f"GEX sign: {'POSITIVE (stabilizing)' if exposure.total_gex > 0 else 'NEGATIVE (destabilizing)'}")

    # IV Analytics
    iv_a = compute_iv_analytics(chain, "NIFTY")
    print(f"\n=== IV Analytics ===")
    print(f"ATM IV:    {iv_a.current_iv:.2f}%")
    print(f"HV 30d:    {iv_a.historical_vol_30d:.2f}%")
    print(f"IV-HV:     {iv_a.iv_rv_spread:.2f}% (positive = IV premium)")
    print(f"IV Rank:   {iv_a.iv_rank:.1f}/100")

    # Verify HV formula: should be annualized std of log returns
    from features.regime import get_price_buffer
    buf = get_price_buffer("NIFTY")
    prices = list(buf._prices)
    print(f"Price buffer size: {len(prices)} ticks")
    if len(prices) >= 5:
        import numpy as np
        log_rets = [math.log(prices[i]/prices[i-1]) for i in range(1, len(prices)) if prices[i-1] > 0]
        if log_rets:
            hv_manual = np.std(log_rets) * math.sqrt(252) * 100
            print(f"Manual HV: {hv_manual:.2f}% vs computed {iv_a.historical_vol_30d:.2f}%")

    await dhan.close()
    print("\n✓ All live verifications complete")


asyncio.run(verify())
