"""
stocks/database.py
==================
SQLite database for persistent stock OHLCV storage.
Location: /app/data/stocks.db (mounted volume — survives container restarts)

Schema:
  daily_candles(symbol, ts, open, high, low, close, volume)
  stock_features(symbol, computed_at, features_json)
  stock_signals(symbol, computed_at, signals_json)
  stock_monte_carlo(symbol, computed_at, mc_json)
  stock_backtest(symbol, computed_at, bt_json)

Design:
  - Fetch 5-year history ONCE, store in SQLite
  - Daily: fetch only today's candle, append to DB
  - Compute features from DB data, store results in DB
  - API reads computed results from Redis (fast) or DB (fallback)
"""

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

DB_PATH = os.environ.get("STOCK_DB_PATH", "/app/data/stocks.db")


def _ensure_dir():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def get_connection() -> sqlite3.Connection:
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=10000")
    return conn


@contextmanager
def db_conn():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create tables if they don't exist."""
    _ensure_dir()
    with db_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS daily_candles (
                symbol  TEXT    NOT NULL,
                ts      INTEGER NOT NULL,
                open    REAL    NOT NULL,
                high    REAL    NOT NULL,
                low     REAL    NOT NULL,
                close   REAL    NOT NULL,
                volume  INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (symbol, ts)
            );

            CREATE INDEX IF NOT EXISTS idx_candles_symbol_ts
                ON daily_candles(symbol, ts);

            CREATE TABLE IF NOT EXISTS stock_features (
                symbol       TEXT    PRIMARY KEY,
                computed_at  REAL    NOT NULL,
                features_json TEXT   NOT NULL
            );

            CREATE TABLE IF NOT EXISTS stock_signals (
                symbol       TEXT    PRIMARY KEY,
                computed_at  REAL    NOT NULL,
                signals_json TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS stock_monte_carlo (
                symbol       TEXT    PRIMARY KEY,
                computed_at  REAL    NOT NULL,
                mc_json      TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS stock_backtest (
                symbol       TEXT    PRIMARY KEY,
                computed_at  REAL    NOT NULL,
                bt_json      TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pipeline_meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)


# ── Candle operations ─────────────────────────────────────────────────────────

def upsert_candles(symbol: str, candles: List[Dict]):
    """Insert or replace candles for a symbol."""
    if not candles:
        return
    with db_conn() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO daily_candles(symbol,ts,open,high,low,close,volume) "
            "VALUES(?,?,?,?,?,?,?)",
            [
                (symbol, c["ts"], c["open"], c["high"], c["low"], c["close"], c.get("volume", 0))
                for c in candles
            ],
        )


def get_candles(symbol: str, from_ts: int = 0) -> List[Dict]:
    """Load all candles for a symbol, optionally from a timestamp."""
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT ts,open,high,low,close,volume FROM daily_candles "
            "WHERE symbol=? AND ts>=? ORDER BY ts ASC",
            (symbol, from_ts),
        ).fetchall()
    return [{"ts": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]} for r in rows]


def get_latest_ts(symbol: str) -> Optional[int]:
    """Return the most recent timestamp for a symbol, or None."""
    with db_conn() as conn:
        row = conn.execute(
            "SELECT MAX(ts) FROM daily_candles WHERE symbol=?", (symbol,)
        ).fetchone()
    return row[0] if row and row[0] else None


def get_candle_count(symbol: str) -> int:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM daily_candles WHERE symbol=?", (symbol,)
        ).fetchone()
    return row[0] if row else 0


def get_all_symbols_with_data() -> List[str]:
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT symbol FROM daily_candles"
        ).fetchall()
    return [r[0] for r in rows]


# ── Computed results ──────────────────────────────────────────────────────────

def save_features(symbol: str, features: Dict):
    with db_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO stock_features(symbol,computed_at,features_json) VALUES(?,?,?)",
            (symbol, time.time(), json.dumps(features)),
        )


def save_signals(symbol: str, signals: Dict):
    with db_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO stock_signals(symbol,computed_at,signals_json) VALUES(?,?,?)",
            (symbol, time.time(), json.dumps(signals)),
        )


def save_monte_carlo(symbol: str, mc: Dict):
    with db_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO stock_monte_carlo(symbol,computed_at,mc_json) VALUES(?,?,?)",
            (symbol, time.time(), json.dumps(mc)),
        )


def save_backtest(symbol: str, bt: Dict):
    with db_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO stock_backtest(symbol,computed_at,bt_json) VALUES(?,?,?)",
            (symbol, time.time(), json.dumps(bt)),
        )


def load_features(symbol: str) -> Optional[Dict]:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT features_json FROM stock_features WHERE symbol=?", (symbol,)
        ).fetchone()
    return json.loads(row[0]) if row else None


def load_signals(symbol: str) -> Optional[Dict]:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT signals_json FROM stock_signals WHERE symbol=?", (symbol,)
        ).fetchone()
    return json.loads(row[0]) if row else None


def load_monte_carlo(symbol: str) -> Optional[Dict]:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT mc_json FROM stock_monte_carlo WHERE symbol=?", (symbol,)
        ).fetchone()
    return json.loads(row[0]) if row else None


def load_backtest(symbol: str) -> Optional[Dict]:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT bt_json FROM stock_backtest WHERE symbol=?", (symbol,)
        ).fetchone()
    return json.loads(row[0]) if row else None


# ── Pipeline metadata ─────────────────────────────────────────────────────────

def set_meta(key: str, value: str):
    with db_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO pipeline_meta(key,value) VALUES(?,?)",
            (key, value),
        )


def get_meta(key: str) -> Optional[str]:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT value FROM pipeline_meta WHERE key=?", (key,)
        ).fetchone()
    return row[0] if row else None


def get_db_stats() -> Dict:
    """Return database statistics."""
    with db_conn() as conn:
        total_candles = conn.execute("SELECT COUNT(*) FROM daily_candles").fetchone()[0]
        symbols       = conn.execute("SELECT COUNT(DISTINCT symbol) FROM daily_candles").fetchone()[0]
        features_done = conn.execute("SELECT COUNT(*) FROM stock_features").fetchone()[0]
        signals_done  = conn.execute("SELECT COUNT(*) FROM stock_signals").fetchone()[0]
        bt_done       = conn.execute("SELECT COUNT(*) FROM stock_backtest").fetchone()[0]
    return {
        "total_candles":  total_candles,
        "symbols_with_data": symbols,
        "features_computed": features_done,
        "signals_computed":  signals_done,
        "backtests_done":    bt_done,
        "db_path":           DB_PATH,
    }
