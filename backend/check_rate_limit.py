import sys, time, json
sys.path.insert(0, '/app')
from pathlib import Path

rl = Path('/app/data/.dhan_last_fetch.txt')
tc = Path('/app/data/.dhan_token.json')

if rl.exists():
    last = float(rl.read_text().strip())
    elapsed = int(time.time() - last)
    wait = max(0, 125 - elapsed)
    print(f'Rate limit: last fetch {elapsed}s ago, need to wait {wait}s more')
    if wait == 0:
        print('Rate limit cleared — can fetch now')
else:
    print('No rate limit file — can fetch now')

if tc.exists():
    data = json.loads(tc.read_text())
    tok_type = data.get('tokenConsumerType', '?')
    expiry   = data.get('expiryTime', '?')
    print(f'Cached token: type={tok_type}, expiry={expiry}')
else:
    print('No cached token file')

# Also try fetching a token right now
import asyncio
async def try_fetch():
    from token_manager import get_access_token, _inject_token
    try:
        token = await get_access_token()
        print(f'Token fetch OK: len={len(token)}')
        _inject_token(token)
        print('Token injected into REST + WS')
    except Exception as e:
        print(f'Token fetch failed: {e}')

asyncio.run(try_fetch())
