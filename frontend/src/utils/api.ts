import type {
  OptionChainResponse,
  GreeksExposureResponse,
  IVAnalyticsResponse,
  MarketSummary,
  StrategyLeg,
  StrategyAnalysis,
} from '../types';

const BASE_URL = import.meta.env.VITE_API_URL || '/api';

// Demo mode token — when set, all API calls route to /api/demo/*
export const DEMO_TOKEN = 'DEMO_MODE_TOKEN';

// ─── Token management ─────────────────────────────────────────────────────────

export const tokenStore = {
  get: (): string | null => localStorage.getItem('auth_token'),
  set: (token: string) => localStorage.setItem('auth_token', token),
  clear: () => localStorage.removeItem('auth_token'),
  getUsername: (): string | null => localStorage.getItem('auth_username'),
  setUsername: (u: string) => localStorage.setItem('auth_username', u),
  isDemo: (): boolean => localStorage.getItem('auth_token') === DEMO_TOKEN,
};

// ─── Core fetch ───────────────────────────────────────────────────────────────

async function apiFetch<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const token = tokenStore.get();
  const isDemo = token === DEMO_TOKEN;
  
  // Route to /api/demo/* if in demo mode
  const baseUrl = isDemo ? '/api/demo' : BASE_URL;
  
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options?.headers as Record<string, string>),
  };
  
  // Don't send demo token to backend — demo endpoints don't need auth
  if (token && !isDemo) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(`${baseUrl}${endpoint}`, {
    ...options,
    headers,
  });

  if (res.status === 401 && !isDemo) {
    tokenStore.clear();
    window.location.href = '/login';
    throw new Error('Session expired');
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API error: ${res.status}`);
  }
  return res.json();
}

// ─── Auth API ─────────────────────────────────────────────────────────────────

export const authApi = {
  signup: (username: string, password: string, invite_code: string) =>
    apiFetch<{ access_token: string; username: string; expires_in: number }>(
      '/auth/signup',
      { method: 'POST', body: JSON.stringify({ username, password, invite_code }) }
    ),

  login: (username: string, password: string) =>
    apiFetch<{ access_token: string; username: string; expires_in: number }>(
      '/auth/login',
      { method: 'POST', body: JSON.stringify({ username, password }) }
    ),

  logout: () => apiFetch<{ status: string }>('/auth/logout', { method: 'POST' }),

  me: () => apiFetch<{ username: string; ip: string; last_seen: number }>('/auth/me'),
};

// ─── Market data API ──────────────────────────────────────────────────────────

export const api = {
  getOptionChain: (symbol: string, expiry?: string) =>
    apiFetch<OptionChainResponse>(
      `/option-chain?symbol=${symbol}${expiry ? `&expiry=${expiry}` : ''}`
    ),

  getExpiries: (symbol: string) =>
    apiFetch<{ symbol: string; expiries: string[] }>(`/expiries?symbol=${symbol}`),

  getGreeksExposure: (symbol: string) =>
    apiFetch<GreeksExposureResponse>(`/greeks-exposure?symbol=${symbol}`),

  getIVAnalytics: (symbol: string) =>
    apiFetch<IVAnalyticsResponse>(`/iv-analytics?symbol=${symbol}`),

  getMarketSummary: (symbol: string) =>
    apiFetch<MarketSummary>(`/market-summary?symbol=${symbol}`),

  getQuote: (symbol: string) =>
    apiFetch<{
      symbol: string;
      ltp: number;
      change: number;
      change_pct: number;
      open: number;
      high: number;
      low: number;
      close: number;
    }>(`/quote?symbol=${symbol}`),

  analyzeStrategy: (legs: StrategyLeg[]) =>
    apiFetch<StrategyAnalysis>('/strategy/analyze', {
      method: 'POST',
      body: JSON.stringify(legs),
    }),

  getHistorical: (securityId: string, exchangeSegment: string, interval: number) =>
    apiFetch<{
      open: number[];
      high: number[];
      low: number[];
      close: number[];
      volume: number[];
      timestamp: number[];
    }>(`/historical?security_id=${securityId}&exchange_segment=${exchangeSegment}&interval=${interval}`),

  getExtraIndices: () =>
    apiFetch<Array<{ symbol: string; ltp: number; change: number; change_pct: number }>>('/indices'),

  getScreener: () =>
    apiFetch<any>('/screener'),

  getLongTermStocks: (minScore: number = 0) =>
    apiFetch<any>(`/long-term-stocks?min_score=${minScore}&limit=200`),

  getStockDetail: (symbol: string) =>
    apiFetch<any>(`/stock/${symbol}`),

  getStockFundamentals: (symbol: string) =>
    apiFetch<any>(`/stock/${symbol}/fundamentals`),

  simulateStockInvestment: (symbol: string, investment: number, horizon: number) =>
    apiFetch<any>(`/stock/${symbol}/simulate?investment=${investment}&horizon=${horizon}`),

  getLiveStockPrices: () =>
    apiFetch<{
      available: boolean;
      market_open: boolean;
      prices: Record<string, {
        ltp: number;
        day_change: number;
        day_change_pct: number;
        intraday_change_pct: number;
        vwap: number;
        volume: number;
        range_position: number;
        buy_pressure: number;
        open: number;
        high: number;
        low: number;
        prev_close: number;
        upper_circuit: number;
        lower_circuit: number;
        w52_high_live: number;
        w52_low_live: number;
        ts: number;
      }>;
      fetched_at: number;
      count: number;
    }>('/stocks/live-prices'),

  getIntelligence: (symbol: string) =>
    apiFetch<any>(`/intelligence?symbol=${symbol}`),

  getNews: (category?: string, sentiment?: string) =>
    apiFetch<any>(`/news${category && category !== 'ALL' ? `?category=${category}` : ''}${sentiment && sentiment !== 'ALL' ? `${category && category !== 'ALL' ? '&' : '?'}sentiment=${sentiment}` : ''}`),

  healthCheck: () => apiFetch<{ status: string; connections: number; redis: boolean; demo_mode: boolean }>('/health'),
};
