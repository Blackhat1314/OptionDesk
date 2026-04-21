"""Check rate limiter state in running process via shared singleton."""
import asyncio, time
from api.rate_limiter import get_rate_limiter


async def check():
    rl = get_rate_limiter()
    
    print("=== RATE LIMITER STATE ===")
    print(f"option_chain: tokens={rl.option_chain._tokens:.4f} rate={rl.option_chain.rate}")
    print(f"ltp:          tokens={rl.ltp._tokens:.4f}")
    print(f"ohlc:         tokens={rl.ohlc._tokens:.4f}")
    print(f"expiry_list:  tokens={rl.expiry_list._tokens:.4f}")
    
    bo_oc  = await rl.check_backoff("/optionchain")
    bo_ltp = await rl.check_backoff("/marketfeed/ltp")
    print(f"\nBackoffs:")
    print(f"  /optionchain:    {bo_oc:.1f}s remaining")
    print(f"  /marketfeed/ltp: {bo_ltp:.1f}s remaining")
    
    print("\n=== TESTING ACQUIRE (should take ~3s) ===")
    t0 = time.time()
    await rl.acquire_option_chain()
    elapsed = round(time.time() - t0, 2)
    print(f"acquire_option_chain() took {elapsed}s")
    
    print("\n=== TESTING SECOND ACQUIRE (should take ~3s) ===")
    t0 = time.time()
    await rl.acquire_option_chain()
    elapsed = round(time.time() - t0, 2)
    print(f"acquire_option_chain() took {elapsed}s")


asyncio.run(check())
