"""
stocks/backtest.py
Vectorized walk-forward backtest with dynamic parameters (spec §7).

Dynamic parameters based on sigma_252 (annualized volatility):
  sigma < 20%:  hold=60d, stop=7%, target=20%
  sigma > 30%:  hold=20d, stop=5%, target=10%
  else:         hold=40d, stop=6%, target=15%
"""

import math
import numpy as np
import pandas as pd
from typing import Dict, List

from stocks.features import compute_features
from stocks.signals  import compute_signal

MIN_BARS = 300


def _dynamic_params(sigma_252: float) -> tuple:
    """
    Spec §7: dynamic backtest parameters based on annualized volatility.
    Returns (hold_days, stop_loss, target).
    """
    if sigma_252 < 20.0:
        return 60, 0.07, 0.20
    elif sigma_252 > 30.0:
        return 20, 0.05, 0.10
    else:
        return 40, 0.06, 0.15


def run_backtest(symbol: str, candles: List[Dict]) -> Dict:
    """
    Walk-forward backtest with dynamic SL/TP/hold based on stock volatility.
    """
    if len(candles) < MIN_BARS:
        return _empty(symbol)

    df     = pd.DataFrame(candles).sort_values("ts").reset_index(drop=True)
    closes = df["close"].values.astype(np.float64)
    n      = len(closes)

    # Compute sigma_252 for the full history to set dynamic params
    log_ret   = np.log(closes[1:] / closes[:-1])
    sigma_252 = float(log_ret[-252:].std() * math.sqrt(252) * 100) if len(log_ret) >= 252 else 25.0

    hold_days, stop_loss, target = _dynamic_params(sigma_252)

    trades:      List[Dict] = []
    in_trade:    bool       = False
    entry_price: float      = 0.0
    entry_idx:   int        = 0

    for i in range(252, n - hold_days - 1):
        if in_trade:
            current = closes[i]
            ret     = (current - entry_price) / entry_price

            if ret <= -stop_loss or ret >= target or (i - entry_idx) >= hold_days:
                trades.append({
                    "entry":  entry_price,
                    "exit":   current,
                    "return": ret,
                    "days":   i - entry_idx,
                    "result": "WIN" if ret > 0 else "LOSS",
                })
                in_trade = False
            continue

        # Compute features on 252-bar window ending at bar i
        window = [
            {
                "ts":     df["ts"].iloc[j],
                "open":   df["open"].iloc[j],
                "high":   df["high"].iloc[j],
                "low":    df["low"].iloc[j],
                "close":  df["close"].iloc[j],
                "volume": df["volume"].iloc[j],
            }
            for j in range(max(0, i - 252), i + 1)
        ]
        feats = compute_features(window)
        sig   = compute_signal(feats)

        if sig.get("signal") in ("BUY", "STRONG BUY") and not in_trade:
            in_trade    = True
            entry_price = closes[i]
            entry_idx   = i

    if not trades:
        return _empty(symbol, sigma_252, hold_days, stop_loss, target)

    returns    = np.array([t["return"] for t in trades])
    win_rate   = float((returns > 0).mean() * 100)
    avg_return = float(returns.mean() * 100)
    total      = len(trades)

    sharpe = float((returns.mean() / returns.std()) * math.sqrt(252)) if returns.std() > 1e-8 else 0.0

    equity = np.cumprod(1 + returns)
    peak   = np.maximum.accumulate(equity)
    dd_arr = (peak - equity) / peak
    max_dd = float(dd_arr.max() * 100)

    return {
        "symbol":       symbol,
        "total_trades": total,
        "win_rate":     round(win_rate, 1),
        "avg_return":   round(avg_return, 2),
        "sharpe_ratio": round(sharpe, 3),
        "max_drawdown": round(max_dd, 2),
        "best_trade":   round(float(returns.max() * 100), 2),
        "worst_trade":  round(float(returns.min() * 100), 2),
        # Dynamic params used
        "hold_days":    hold_days,
        "stop_loss":    round(stop_loss * 100, 1),
        "target":       round(target * 100, 1),
        "sigma_252":    round(sigma_252, 1),
    }


def _empty(
    symbol:    str,
    sigma_252: float = 25.0,
    hold_days: int   = 40,
    stop_loss: float = 0.06,
    target:    float = 0.15,
) -> Dict:
    return {
        "symbol":       symbol,
        "total_trades": 0,
        "win_rate":     0.0,
        "avg_return":   0.0,
        "sharpe_ratio": 0.0,
        "max_drawdown": 0.0,
        "best_trade":   0.0,
        "worst_trade":  0.0,
        "hold_days":    hold_days,
        "stop_loss":    round(stop_loss * 100, 1),
        "target":       round(target * 100, 1),
        "sigma_252":    round(sigma_252, 1),
    }
