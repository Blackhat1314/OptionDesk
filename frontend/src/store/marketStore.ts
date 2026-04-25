import { create } from 'zustand';
import type {
  OptionChainResponse,
  GreeksExposureResponse,
  IVAnalyticsResponse,
  MarketSummary,
  StrategyLeg,
  TabId,
  MlSignal,
} from '../types';

// All supported symbols
export const ALL_SYMBOLS = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX'] as const;
export type SymbolId = typeof ALL_SYMBOLS[number];

// Per-symbol data cache — holds data for ALL symbols, not just the active one
export interface SymbolData {
  chain:      OptionChainResponse | null;
  exposure:   GreeksExposureResponse | null;
  ivAnalytics: IVAnalyticsResponse | null;
  summary:    MarketSummary | null;
  expiries:   string[];
  lastUpdate: number;
  prevClose:  number; // previous day's close — used to recalculate day change on every tick
}

type SymbolCache = Record<string, SymbolData>;

function emptySymbolData(): SymbolData {
  return {
    chain: null, exposure: null, ivAnalytics: null,
    summary: null, expiries: [], lastUpdate: 0, prevClose: 0,
  };
}

interface TickFlash {
  [securityId: string]: 'up' | 'down' | null;
}

interface MarketStore {
  // Active state
  activeTab:    TabId;
  activeSymbol: string;
  isConnected:  boolean;
  isLoading:    boolean;

  // Per-symbol cache — ALL symbols stored here
  symbolCache: SymbolCache;

  // Derived from symbolCache[activeSymbol] — convenience accessors
  chain:       OptionChainResponse | null;
  exposure:    GreeksExposureResponse | null;
  ivAnalytics: IVAnalyticsResponse | null;
  summary:     MarketSummary | null;
  expiries:    string[];
  activeExpiry: string;
  lastUpdate:  number;
  spotPrice:   number;
  dayChange:   number;
  dayChangePct: number;

  // Strategy builder
  strategyLegs: StrategyLeg[];

  // Tick flashes
  tickFlashes: TickFlash;

  // ML signals — per symbol
  mlSignals: Record<string, MlSignal[]>;
  setMlSignals: (symbol: string, signals: MlSignal[]) => void;

  // UI Filters
  strikeRange: number;
  showITM: boolean;
  showOTM: boolean;

  // Actions
  setActiveTab:    (tab: TabId) => void;
  setActiveSymbol: (symbol: string) => void;
  setActiveExpiry: (expiry: string) => void;
  setConnected:    (connected: boolean) => void;
  setLoading:      (loading: boolean) => void;

  // Per-symbol setters — update cache AND active views if symbol matches
  setChainForSymbol:      (symbol: string, chain: OptionChainResponse) => void;
  setExposureForSymbol:   (symbol: string, exposure: GreeksExposureResponse) => void;
  setIVAnalyticsForSymbol:(symbol: string, iv: IVAnalyticsResponse) => void;
  setSummaryForSymbol:    (symbol: string, summary: MarketSummary) => void;
  setExpiriesForSymbol:   (symbol: string, expiries: string[]) => void;

  // Legacy setters (set for active symbol)
  setChain:      (chain: OptionChainResponse) => void;
  setExposure:   (exposure: GreeksExposureResponse) => void;
  setIVAnalytics:(iv: IVAnalyticsResponse) => void;
  setSummary:    (summary: MarketSummary) => void;
  setExpiries:   (expiries: string[]) => void;

  updateSpotPrice: (price: number, change: number, changePct: number) => void;
  addStrategyLeg:  (leg: StrategyLeg) => void;
  removeStrategyLeg:(idx: number) => void;
  clearStrategyLegs:() => void;
  flashTick:       (securityId: string, direction: 'up' | 'down') => void;
  setStrikeRange:  (range: number) => void;
  setPrevClose:    (symbol: string, prevClose: number) => void;
  // Stock live prices from WS ticks — {SYMBOL: ltp}
  stockLtps:       Record<string, number>;
  updateStockLtp:  (symbol: string, ltp: number) => void;

  // Get cached data for any symbol (used when switching)
  getCachedData: (symbol: string) => SymbolData;
}

// Build initial cache with empty data for all symbols
function buildInitialCache(): SymbolCache {
  const cache: SymbolCache = {};
  for (const sym of ALL_SYMBOLS) {
    cache[sym] = emptySymbolData();
  }
  return cache;
}

// Derive active-symbol convenience fields from cache
function deriveActive(cache: SymbolCache, symbol: string) {
  const d = cache[symbol] || emptySymbolData();
  return {
    chain:        d.chain,
    exposure:     d.exposure,
    ivAnalytics:  d.ivAnalytics,
    summary:      d.summary,
    expiries:     d.expiries,
    activeExpiry: d.chain?.expiry || (d.expiries[0] ?? ''),
    lastUpdate:   d.lastUpdate,
    spotPrice:    d.summary?.spot_price ?? d.chain?.spot_price ?? 0,
    dayChange:    d.summary?.day_change ?? 0,
    dayChangePct: d.summary?.day_change_pct ?? 0,
  };
}

export const useMarketStore = create<MarketStore>((set, get) => ({
  activeTab:    'chain',
  activeSymbol: 'NIFTY',
  isConnected:  false,
  isLoading:    false,

  symbolCache: buildInitialCache(),

  // Derived — start empty, populated by setters
  chain:        null,
  exposure:     null,
  ivAnalytics:  null,
  summary:      null,
  expiries:     [],
  activeExpiry: '',
  lastUpdate:   0,
  spotPrice:    0,
  dayChange:    0,
  dayChangePct: 0,

  strategyLegs: [],
  tickFlashes:  {},
  mlSignals:    {},
  strikeRange:  10,
  showITM:      true,
  showOTM:      true,
  stockLtps:    {},

  setActiveTab: (tab) => set({ activeTab: tab }),

  setActiveSymbol: (symbol) => {
    // Switch active symbol — immediately serve from cache (no loading)
    const cache = get().symbolCache;
    const derived = deriveActive(cache, symbol);
    set({ activeSymbol: symbol, ...derived });
  },

  setActiveExpiry: (expiry) => set({ activeExpiry: expiry }),
  setConnected:    (connected) => set({ isConnected: connected }),
  setLoading:      (loading) => set({ isLoading: loading }),

  // ── Per-symbol setters ────────────────────────────────────────────────────

  setChainForSymbol: (symbol, chain) => {
    set((state) => {
      const newCache = {
        ...state.symbolCache,
        [symbol]: {
          ...state.symbolCache[symbol],
          chain,
          expiries: chain.expiries?.length
            ? chain.expiries
            : state.symbolCache[symbol]?.expiries ?? [],
          lastUpdate: Date.now(),
        },
      };
      // If this is the active symbol, update derived fields too
      if (symbol === state.activeSymbol) {
        return {
          symbolCache: newCache,
          chain,
          activeExpiry: chain.expiry,
          spotPrice: chain.spot_price,
          expiries: newCache[symbol].expiries,
          lastUpdate: Date.now(),
        };
      }
      return { symbolCache: newCache };
    });
  },

  setExposureForSymbol: (symbol, exposure) => {
    set((state) => {
      const newCache = {
        ...state.symbolCache,
        [symbol]: { ...state.symbolCache[symbol], exposure },
      };
      if (symbol === state.activeSymbol) {
        return { symbolCache: newCache, exposure };
      }
      return { symbolCache: newCache };
    });
  },

  setIVAnalyticsForSymbol: (symbol, ivAnalytics) => {
    set((state) => {
      const newCache = {
        ...state.symbolCache,
        [symbol]: { ...state.symbolCache[symbol], ivAnalytics },
      };
      if (symbol === state.activeSymbol) {
        return { symbolCache: newCache, ivAnalytics };
      }
      return { symbolCache: newCache };
    });
  },

  setSummaryForSymbol: (symbol, summary) => {
    set((state) => {
      const newCache = {
        ...state.symbolCache,
        [symbol]: { ...state.symbolCache[symbol], summary },
      };
      if (symbol === state.activeSymbol) {
        return {
          symbolCache: newCache,
          summary,
          spotPrice:    summary.spot_price,
          dayChange:    summary.day_change,
          dayChangePct: summary.day_change_pct,
        };
      }
      return { symbolCache: newCache };
    });
  },

  setExpiriesForSymbol: (symbol, expiries) => {
    set((state) => {
      const newCache = {
        ...state.symbolCache,
        [symbol]: { ...state.symbolCache[symbol], expiries },
      };
      if (symbol === state.activeSymbol) {
        return { symbolCache: newCache, expiries };
      }
      return { symbolCache: newCache };
    });
  },

  // ── Legacy setters (operate on active symbol) ─────────────────────────────

  setChain: (chain) => {
    const symbol = get().activeSymbol;
    get().setChainForSymbol(symbol, chain);
  },

  setExposure: (exposure) => {
    const symbol = get().activeSymbol;
    get().setExposureForSymbol(symbol, exposure);
  },

  setIVAnalytics: (ivAnalytics) => {
    const symbol = get().activeSymbol;
    get().setIVAnalyticsForSymbol(symbol, ivAnalytics);
  },

  setSummary: (summary) => {
    const symbol = get().activeSymbol;
    get().setSummaryForSymbol(symbol, summary);
  },

  setExpiries: (expiries) => {
    const symbol = get().activeSymbol;
    get().setExpiriesForSymbol(symbol, expiries);
  },

  updateSpotPrice: (price, change, changePct) =>
    set({ spotPrice: price, dayChange: change, dayChangePct: changePct }),

  addStrategyLeg: (leg) =>
    set((state) => ({ strategyLegs: [...state.strategyLegs, leg] })),

  removeStrategyLeg: (idx) =>
    set((state) => ({
      strategyLegs: state.strategyLegs.filter((_, i) => i !== idx),
    })),

  clearStrategyLegs: () => set({ strategyLegs: [] }),

  flashTick: (securityId, direction) => {
    set((state) => ({
      tickFlashes: { ...state.tickFlashes, [securityId]: direction },
    }));
    setTimeout(() => {
      set((state) => ({
        tickFlashes: { ...state.tickFlashes, [securityId]: null },
      }));
    }, 500);
  },

  setStrikeRange: (range) => set({ strikeRange: range }),

  updateStockLtp: (symbol, ltp) =>
    set((state) => ({
      stockLtps: { ...state.stockLtps, [symbol]: ltp },
    })),

  setMlSignals: (symbol, signals) =>
    set((state) => ({
      mlSignals: { ...state.mlSignals, [symbol]: signals },
    })),

  setPrevClose: (symbol, prevClose) => {
    set((state) => ({
      symbolCache: {
        ...state.symbolCache,
        [symbol]: {
          ...state.symbolCache[symbol],
          prevClose,
        },
      },
    }));
  },

  getCachedData: (symbol) => {
    return get().symbolCache[symbol] || emptySymbolData();
  },
}));
