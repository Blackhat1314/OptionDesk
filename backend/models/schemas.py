from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
import time


class IndexSymbol(str, Enum):
    NIFTY = "NIFTY"
    BANKNIFTY = "BANKNIFTY"
    FINNIFTY = "FINNIFTY"
    MIDCPNIFTY = "MIDCPNIFTY"


class OptionType(str, Enum):
    CALL = "CE"
    PUT = "PE"


# ─── Option Chain Models ──────────────────────────────────────────────────────

class Greeks(BaseModel):
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    rho: float = 0.0


class OptionLeg(BaseModel):
    security_id: str = ""
    trading_symbol: str = ""
    strike: float = 0.0
    option_type: str = ""
    expiry: str = ""
    ltp: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    oi: int = 0
    oi_change: int = 0
    oi_change_pct: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    bid_qty: int = 0
    ask_qty: int = 0
    iv: float = 0.0
    greeks: Greeks = Field(default_factory=Greeks)
    bid_ask_spread: float = 0.0
    vwap: float = 0.0


class OptionChainRow(BaseModel):
    strike: float
    is_atm: bool = False
    call: OptionLeg = Field(default_factory=OptionLeg)
    put: OptionLeg = Field(default_factory=OptionLeg)
    pcr_oi: float = 0.0
    pcr_volume: float = 0.0


class OptionChainResponse(BaseModel):
    symbol: str
    expiry: str
    spot_price: float
    atm_strike: float
    futures_price: float = 0.0
    timestamp: float = Field(default_factory=time.time)
    rows: List[OptionChainRow] = []
    expiries: List[str] = []


# ─── Greeks & Exposure Models ─────────────────────────────────────────────────

class ExposureByStrike(BaseModel):
    strike: float
    call_delta: float = 0.0
    put_delta: float = 0.0
    net_delta: float = 0.0
    call_gamma: float = 0.0
    put_gamma: float = 0.0
    net_gamma: float = 0.0
    gex: float = 0.0
    dex: float = 0.0
    call_vega: float = 0.0
    put_vega: float = 0.0
    net_vega: float = 0.0
    call_theta: float = 0.0
    put_theta: float = 0.0
    net_theta: float = 0.0


class GreeksExposureResponse(BaseModel):
    symbol: str
    expiry: str
    spot_price: float
    timestamp: float = Field(default_factory=time.time)
    exposures: List[ExposureByStrike] = []
    total_gex: float = 0.0
    total_dex: float = 0.0
    total_vega: float = 0.0
    total_theta: float = 0.0
    gamma_flip_level: float = 0.0
    call_wall: float = 0.0
    put_wall: float = 0.0


# ─── IV Analytics Models ──────────────────────────────────────────────────────

class IVSmilePoint(BaseModel):
    strike: float
    call_iv: float = 0.0
    put_iv: float = 0.0
    moneyness: float = 0.0


class IVTermStructurePoint(BaseModel):
    expiry: str
    dte: int
    atm_iv: float
    iv_rank: float = 0.0
    iv_percentile: float = 0.0


class IVAnalyticsResponse(BaseModel):
    symbol: str
    expiry: str
    spot_price: float
    timestamp: float = Field(default_factory=time.time)
    smile: List[IVSmilePoint] = []
    term_structure: List[IVTermStructurePoint] = []
    current_iv: float = 0.0
    iv_rank: float = 0.0
    iv_percentile: float = 0.0
    historical_vol_30d: float = 0.0
    historical_vol_7d: float = 0.0
    iv_rv_spread: float = 0.0
    avg_iv: float = 0.0


# ─── Market Summary Models ────────────────────────────────────────────────────

class MarketSummary(BaseModel):
    symbol: str
    spot_price: float = 0.0
    day_change: float = 0.0
    day_change_pct: float = 0.0
    pcr_oi: float = 0.0
    pcr_volume: float = 0.0
    max_pain: float = 0.0
    atm_iv: float = 0.0
    vix: float = 0.0
    total_call_oi: int = 0
    total_put_oi: int = 0
    total_call_vol: int = 0
    total_put_vol: int = 0
    timestamp: float = Field(default_factory=time.time)


# ─── Historical Data Models ───────────────────────────────────────────────────

class OHLCBar(BaseModel):
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: int
    oi: Optional[int] = None


class HistoricalDataResponse(BaseModel):
    security_id: str
    symbol: str
    interval: str
    bars: List[OHLCBar] = []


# ─── WebSocket Message Models ─────────────────────────────────────────────────

class WSMessageType(str, Enum):
    OPTION_CHAIN_UPDATE = "option_chain_update"
    GREEKS_UPDATE = "greeks_update"
    IV_UPDATE = "iv_update"
    MARKET_SUMMARY = "market_summary"
    TICK = "tick"
    OI_UPDATE = "oi_update"
    ERROR = "error"
    SUBSCRIBE_OK = "subscribe_ok"


class WSMessage(BaseModel):
    type: WSMessageType
    data: Any
    timestamp: float = Field(default_factory=time.time)


# ─── Strategy Builder Models ──────────────────────────────────────────────────

class StrategyLeg(BaseModel):
    option_type: str  # CE or PE
    strike: float
    expiry: str
    action: str  # BUY or SELL
    quantity: int = 1
    premium: float = 0.0
    iv: float = 0.0
    greeks: Greeks = Field(default_factory=Greeks)


class PayoffPoint(BaseModel):
    spot: float
    pnl: float


class StrategyAnalysis(BaseModel):
    strategy_name: str
    legs: List[StrategyLeg]
    net_premium: float = 0.0
    max_profit: float = 0.0
    max_loss: float = 0.0
    breakevens: List[float] = []
    payoff_curve: List[PayoffPoint] = []
    net_delta: float = 0.0
    net_gamma: float = 0.0
    net_theta: float = 0.0
    net_vega: float = 0.0


# ─── Dhan API Internal Models ─────────────────────────────────────────────────

class DhanOptionChainData(BaseModel):
    """Raw Dhan option chain response normalized"""
    oi: int = 0
    oiChange: int = 0
    volume: int = 0
    ltp: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    iv: float = 0.0
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
