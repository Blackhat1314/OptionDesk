// ─── Core Types ───────────────────────────────────────────────────────────────

export interface Greeks {
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  rho: number;
}

export interface OptionLeg {
  security_id: string;
  trading_symbol: string;
  strike: number;
  option_type: 'CE' | 'PE';
  expiry: string;
  ltp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  oi: number;
  oi_change: number;
  oi_change_pct: number;
  bid: number;
  ask: number;
  bid_qty: number;
  ask_qty: number;
  iv: number;
  greeks: Greeks;
  bid_ask_spread: number;
  vwap: number;
}

export interface OptionChainRow {
  strike: number;
  is_atm: boolean;
  call: OptionLeg;
  put: OptionLeg;
  pcr_oi: number;
  pcr_volume: number;
}

export interface OptionChainResponse {
  symbol: string;
  expiry: string;
  spot_price: number;
  atm_strike: number;
  futures_price: number;
  timestamp: number;
  rows: OptionChainRow[];
  expiries: string[];
}

// ─── Greeks Exposure ──────────────────────────────────────────────────────────

export interface ExposureByStrike {
  strike: number;
  call_delta: number;
  put_delta: number;
  net_delta: number;
  call_gamma: number;
  put_gamma: number;
  net_gamma: number;
  gex: number;
  dex: number;
  call_vega: number;
  put_vega: number;
  net_vega: number;
  call_theta: number;
  put_theta: number;
  net_theta: number;
}

export interface GreeksExposureResponse {
  symbol: string;
  expiry: string;
  spot_price: number;
  timestamp: number;
  exposures: ExposureByStrike[];
  total_gex: number;
  total_dex: number;
  total_vega: number;
  total_theta: number;
  gamma_flip_level: number;
  call_wall: number;
  put_wall: number;
}

// ─── IV Analytics ─────────────────────────────────────────────────────────────

export interface IVSmilePoint {
  strike: number;
  call_iv: number;
  put_iv: number;
  moneyness: number;
}

export interface IVTermStructurePoint {
  expiry: string;
  dte: number;
  atm_iv: number;
  iv_rank: number;
  iv_percentile: number;
}

export interface IVAnalyticsResponse {
  symbol: string;
  expiry: string;
  spot_price: number;
  timestamp: number;
  smile: IVSmilePoint[];
  term_structure: IVTermStructurePoint[];
  current_iv: number;
  iv_rank: number;
  iv_percentile: number;
  historical_vol_30d: number;
  historical_vol_7d: number;
  iv_rv_spread: number;
  avg_iv: number;
}

// ─── Market Summary ───────────────────────────────────────────────────────────

export interface MarketSummary {
  symbol: string;
  spot_price: number;
  day_change: number;
  day_change_pct: number;
  pcr_oi: number;
  pcr_volume: number;
  max_pain: number;
  atm_iv: number;
  vix: number;
  total_call_oi: number;
  total_put_oi: number;
  total_call_vol: number;
  total_put_vol: number;
  timestamp: number;
}

// ─── Strategy Builder ─────────────────────────────────────────────────────────

export interface StrategyLeg {
  option_type: 'CE' | 'PE';
  strike: number;
  expiry: string;
  action: 'BUY' | 'SELL';
  quantity: number;
  premium: number;
  iv: number;
  greeks: Greeks;
}

export interface PayoffPoint {
  spot: number;
  pnl: number;
}

export interface StrategyAnalysis {
  strategy_name: string;
  legs: StrategyLeg[];
  net_premium: number;
  max_profit: number;
  max_loss: number;
  breakevens: number[];
  payoff_curve: PayoffPoint[];
  net_delta: number;
  net_gamma: number;
  net_theta: number;
  net_vega: number;
}

// ─── ML Signals ──────────────────────────────────────────────────────────────

export interface MlSignal {
  strike:     number;
  type:       'CALL' | 'PUT';
  direction:  'UP' | 'DOWN';
  confidence: number;
  prob_up:    number;
  atm_offset: number;
  ts:         number;
}

// ─── WebSocket Messages ───────────────────────────────────────────────────────

export type WSMessageType =
  | 'option_chain_update'
  | 'greeks_update'
  | 'iv_update'
  | 'market_summary'
  | 'tick'
  | 'alert'
  | 'ml_signals'
  | 'option_chain_snapshot'
  | 'exposure_snapshot'
  | 'iv_snapshot'
  | 'summary_snapshot'
  | 'pong'
  | 'subscribe_ok'
  | 'error';

export interface WSMessage<T = unknown> {
  type: WSMessageType;
  data?: T;
  symbol?: string;
  timestamp: number;
}

// ─── UI Types ─────────────────────────────────────────────────────────────────

export type TabId = 'chain' | 'greeks' | 'iv' | 'decision' | 'strategy' | 'historical' | 'news' | 'livetv' | 'intelligence' | 'guide' | 'screener';

export interface Tab {
  id: TabId;
  label: string;
  shortcut: string;
}

export interface TickFlash {
  security_id: string;
  direction: 'up' | 'down';
}
