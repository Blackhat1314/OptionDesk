"""Check investment simulator for new stocks."""
import asyncio
import numpy as np
from stocks.database import get_candles, get_candle_count, init_db
from stocks.monte_carlo import simulate_investment, run_monte_carlo


def test_stock(sym):
    count = get_candle_count(sym)
    if count < 60:
        print(f"  {sym}: only {count} candles — insufficient")
        return

    candles = get_candles(sym)
    closes  = np.array([c["close"] for c in candles], dtype=np.float64)
    price   = float(closes[-1])
    log_ret = np.log(closes[1:] / closes[:-1])
    window  = log_ret[-252:] if len(log_ret) >= 252 else log_ret

    # Test MC
    mc = run_monte_carlo(sym, price, window, horizon=30)
    # Test simulator
    sim = simulate_investment(price, window, 100000, horizon=126)

    print(f"  {sym}: price={price:.0f} mc_prob={mc['prob_up']:.1f}% "
          f"sim_expected={sim['expected_value']:.0f} sim_prob={sim['prob_profit']:.1f}%")


async def main():
    init_db()
    test_syms = ["BLUESTARCO", "DALBHARAT", "COFORGE", "NATIONALUM",
                 "HINDCOPPER", "RATNAMANI", "JKCEMENT", "ADANIGREEN"]
    print("Testing simulator for new stocks:")
    for sym in test_syms:
        test_stock(sym)


asyncio.run(main())
