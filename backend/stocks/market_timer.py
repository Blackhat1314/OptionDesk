"""
stocks/market_timer.py
Market status logic — India NSE/BSE hours.
"""
import pytz
from datetime import datetime, time as dtime


IST = pytz.timezone("Asia/Kolkata")
_OPEN  = dtime(9, 15)
_CLOSE = dtime(15, 30)


def is_market_open() -> bool:
    now = datetime.now(IST)
    if now.weekday() >= 5:          # Saturday=5, Sunday=6
        return False
    t = now.time()
    return _OPEN <= t <= _CLOSE


def is_market_closed() -> bool:
    return not is_market_open()


def minutes_until_close() -> int:
    now = datetime.now(IST)
    close_dt = now.replace(hour=15, minute=30, second=0, microsecond=0)
    delta = (close_dt - now).total_seconds()
    return max(0, int(delta // 60))


def minutes_since_close() -> int:
    now = datetime.now(IST)
    close_dt = now.replace(hour=15, minute=30, second=0, microsecond=0)
    delta = (now - close_dt).total_seconds()
    return max(0, int(delta // 60))
