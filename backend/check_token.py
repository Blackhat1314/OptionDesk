"""Check if Dhan access token is valid."""
import json, base64, time
from config import get_settings

settings = get_settings()
token = settings.DHAN_ACCESS_TOKEN

# Decode JWT payload (no verification needed, just check expiry)
try:
    parts = token.split(".")
    if len(parts) >= 2:
        payload_b64 = parts[1]
        # Add padding
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.b64decode(payload_b64))
        exp = payload.get("exp", 0)
        iat = payload.get("iat", 0)
        now = time.time()
        print(f"Token issued at:  {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(iat))}")
        print(f"Token expires at: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(exp))}")
        print(f"Current time:     {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))}")
        if now > exp:
            print(f"\n❌ TOKEN EXPIRED {round((now - exp)/3600, 1)} hours ago!")
            print("→ You need to generate a new access token from Dhan portal")
            print("→ https://login.dhan.co → My Profile → API → Generate Token")
        else:
            remaining = exp - now
            print(f"\n✓ Token valid for {round(remaining/3600, 1)} more hours")
        print(f"\nFull payload: {json.dumps(payload, indent=2)}")
except Exception as e:
    print(f"Could not decode token: {e}")
