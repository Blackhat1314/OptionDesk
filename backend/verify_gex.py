"""Verify GEX calculation in detail."""
import asyncio, math
from calculations.black_scholes import gamma, compute_gamma_exposure, days_to_expiry
from config import get_settings
settings = get_settings()
r = settings.RISK_FREE_RATE


async def verify():
    from core.redis_cache import get_cache
    cache = get_cache()
    await cache.connect()

    chain = await cache.get("chain:NIFTY")
    exposure = await cache.get("exposure:NIFTY")

    spot = chain["spot_price"]
    expiry = chain["expiry"]
    T = days_to_expiry(expiry)
    lot = 50

    print(f"Spot: {spot}, T: {T:.4f}yr")
    print(f"Total GEX from Redis: {exposure['total_gex']:.4f} Cr")
    print()

    # Manual GEX calculation for all strikes
    total_gex_manual = 0.0
    print(f"{'Strike':>8} {'Call_GEX':>12} {'Put_GEX':>12} {'Net_GEX':>12} {'Call_OI':>10} {'Put_OI':>10}")
    print("-" * 70)

    for row in chain["rows"]:
        K = row["strike"]
        call_oi = row["call"]["oi"]
        put_oi  = row["put"]["oi"]
        call_iv = row["call"]["iv"] / 100.0 if row["call"]["iv"] > 0 else 0.15
        put_iv  = row["put"]["iv"]  / 100.0 if row["put"]["iv"]  > 0 else 0.15

        if call_oi < 500 and put_oi < 500:
            continue

        call_gex = compute_gamma_exposure(spot, K, r, call_iv, T, call_oi, "CE", lot) / 1e9 if call_oi >= 500 else 0
        put_gex  = compute_gamma_exposure(spot, K, r, put_iv,  T, put_oi,  "PE", lot) / 1e9 if put_oi  >= 500 else 0
        net_gex  = call_gex + put_gex
        total_gex_manual += net_gex

        if abs(K - spot) < 500:  # show near-ATM strikes
            print(f"{K:>8.0f} {call_gex:>12.2f} {put_gex:>12.2f} {net_gex:>12.2f} {call_oi:>10,} {put_oi:>10,}")

    print("-" * 70)
    print(f"Manual Total GEX: {total_gex_manual:.4f} Cr")
    print(f"Redis Total GEX:  {exposure['total_gex']:.4f} Cr")
    print(f"Match: {'✓' if abs(total_gex_manual - exposure['total_gex']) < 1 else '✗ MISMATCH'}")

    # GEX interpretation
    print(f"\nGEX Interpretation:")
    print(f"  Positive GEX = dealers long gamma = market stabilizing (sell rallies, buy dips)")
    print(f"  Negative GEX = dealers short gamma = market destabilizing (chase moves)")
    print(f"  Current: {'POSITIVE (stabilizing)' if exposure['total_gex'] > 0 else 'NEGATIVE (destabilizing)'}")
    print(f"  Gamma Flip: {exposure['gamma_flip_level']:.0f} (below this = negative GEX)")
    print(f"  Call Wall: {exposure['call_wall']:.0f} (max call OI = resistance)")
    print(f"  Put Wall:  {exposure['put_wall']:.0f} (max put OI = support)")


asyncio.run(verify())
