import sys, json, subprocess
sys.path.insert(0, '/app')

# Get chain from Redis
result = subprocess.run(['redis-cli', '-h', 'redis', 'get', 'chain:NIFTY'],
                       capture_output=True, text=True)
raw = result.stdout.strip()
if not raw:
    print('No chain in Redis')
    sys.exit()

d = json.loads(raw)
atm = d.get('atm_strike', 0)
rows = d.get('rows', [])
print('ATM:', atm)
print('Total rows:', len(rows))
strikes = sorted([r['strike'] for r in rows])
print('All strikes:', strikes)
atm_rows = [r for r in rows if abs(r['strike'] - atm) <= 250]
print('ATM+-5 strikes:', sorted([r['strike'] for r in atm_rows]))

# Now test ingest directly
from features.ml_signals import ingest_chain_for_ml, _buffers
spot = d.get('spot_price', 0)
print('Spot:', spot)
ingest_chain_for_ml(d, spot)
print('Buffers after ingest:', len(_buffers))
for k, v in list(_buffers.items())[:5]:
    closed = v['15m'].get_closed()
    print(f'  Strike={k[0]} {k[1]}: 15m closed candles={len(closed)}')
