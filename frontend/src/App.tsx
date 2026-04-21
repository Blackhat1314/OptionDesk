import React, { useEffect, useRef, useState } from 'react';
import { useMarketStore, ALL_SYMBOLS } from './store/marketStore';
import { useWebSocket } from './hooks/useWebSocket';
import { TopNav } from './components/ui/TopNav';
import { StatusBar } from './components/ui/StatusBar';
import { ErrorBoundary } from './components/ui/ErrorBoundary';
import { LoadingOverlay } from './components/ui/Skeleton';
import { OptionChainTab } from './components/tabs/OptionChainTab';
import { GreeksTab } from './components/tabs/GreeksTab';
import { IVAnalyticsTab } from './components/tabs/IVAnalyticsTab';
import { DecisionEngineTab } from './components/tabs/DecisionEngineTab';
import { StrategyBuilderTab } from './components/tabs/StrategyBuilderTab';
import { HistoricalTab } from './components/tabs/HistoricalTab';
import { LiveTVTab } from './components/tabs/LiveTVTab';
import { NewsTab } from './components/tabs/NewsTab';
import { IntelligenceTab, _prewarmIntelligence } from './components/tabs/IntelligenceTab';
import { QuantScreenerTab } from './components/tabs/QuantScreenerTab';
import { GuideTab } from './components/tabs/GuideTab';
import { LoginPage } from './components/auth/LoginPage';
import { api, tokenStore } from './utils/api';

// ─── Authenticated shell ──────────────────────────────────────────────────────

function AuthenticatedApp() {
  const {
    activeTab, activeSymbol, isLoading,
    setChainForSymbol, setExposureForSymbol, setIVAnalyticsForSymbol,
    setSummaryForSymbol, setExpiriesForSymbol, setLoading,
    getCachedData,
  } = useMarketStore();

  // Track which symbols have been fetched via REST (to avoid duplicate calls)
  const fetchedRef = useRef<Set<string>>(new Set());

  useWebSocket();

  // On mount: pre-fetch ALL symbols from REST so cache is warm immediately
  useEffect(() => {
    const prefetchAll = async () => {
      // NIFTY: full prefetch (option chain + all data)
      // Other indices: summary only (for live spot price display in ticker)
      const fetches = ALL_SYMBOLS.map((sym, i) =>
        new Promise<void>(resolve => {
          setTimeout(async () => {
            if (fetchedRef.current.has(sym)) { resolve(); return; }
            fetchedRef.current.add(sym);
            try {
              if (sym === 'NIFTY') {
                // Full prefetch for NIFTY
                const [chain, expData] = await Promise.allSettled([
                  api.getOptionChain(sym),
                  api.getExpiries(sym),
                ]);
                if (chain.status === 'fulfilled' && chain.value?.rows?.length) {
                  setChainForSymbol(sym, chain.value);
                }
                if (expData.status === 'fulfilled' && expData.value?.expiries?.length) {
                  setExpiriesForSymbol(sym, expData.value.expiries);
                }
                Promise.allSettled([
                  api.getGreeksExposure(sym),
                  api.getIVAnalytics(sym),
                  api.getMarketSummary(sym),
                ]).then(([exp, iv, sum]) => {
                  if (exp.status === 'fulfilled') setExposureForSymbol(sym, exp.value);
                  if (iv.status  === 'fulfilled') setIVAnalyticsForSymbol(sym, iv.value);
                  if (sum.status === 'fulfilled') setSummaryForSymbol(sym, sum.value);
                });
              } else {
                // Other indices: only fetch summary for spot price display
                try {
                  const sum = await api.getMarketSummary(sym);
                  if (sum) setSummaryForSymbol(sym, sum);
                } catch {}
              }
            } catch {}
            resolve();
          }, i * 300);
        })
      );
      await Promise.all(fetches);
    };

    setLoading(true);
    prefetchAll().finally(() => setLoading(false));
    _prewarmIntelligence('NIFTY');
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Run once on mount — WS handles live updates after this

  // When active symbol changes: serve from cache instantly (no loading spinner)
  // If cache is empty for this symbol, trigger a background fetch
  useEffect(() => {
    const cached = getCachedData(activeSymbol);
    const hasData = cached.chain !== null || cached.summary !== null;

    if (!hasData && !fetchedRef.current.has(activeSymbol)) {
      // Cache miss — fetch in background without showing loading overlay
      fetchedRef.current.add(activeSymbol);
      (async () => {
        try {
          const [chain, expData] = await Promise.allSettled([
            api.getOptionChain(activeSymbol),
            api.getExpiries(activeSymbol),
          ]);
          if (chain.status === 'fulfilled' && chain.value?.rows?.length) {
            setChainForSymbol(activeSymbol, chain.value);
          }
          if (expData.status === 'fulfilled' && expData.value?.expiries?.length) {
            setExpiriesForSymbol(activeSymbol, expData.value.expiries);
          }
          Promise.allSettled([
            api.getGreeksExposure(activeSymbol),
            api.getIVAnalytics(activeSymbol),
            api.getMarketSummary(activeSymbol),
          ]).then(([exp, iv, sum]) => {
            if (exp.status === 'fulfilled') setExposureForSymbol(activeSymbol, exp.value);
            if (iv.status  === 'fulfilled') setIVAnalyticsForSymbol(activeSymbol, iv.value);
            if (sum.status === 'fulfilled') setSummaryForSymbol(activeSymbol, sum.value);
          });
        } catch {}
      })();
    }

    _prewarmIntelligence(activeSymbol);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSymbol]);

  const TAB_CONTENT: Record<string, React.ReactNode> = {
    chain:        <OptionChainTab />,
    greeks:       <GreeksTab />,
    iv:           <IVAnalyticsTab />,
    decision:     <DecisionEngineTab />,
    intelligence: <IntelligenceTab />,
    screener:     <QuantScreenerTab />,
    strategy:     <StrategyBuilderTab />,
    historical:   <HistoricalTab />,
    news:         <NewsTab />,
    livetv:       <LiveTVTab />,
    guide:        <GuideTab />,
  };

  return (
    <div className="scanlines flex flex-col h-screen bg-bg-primary text-text-primary font-mono overflow-hidden">
      <TopNav />
      <main className="relative flex-1 min-h-0 overflow-hidden">
        <ErrorBoundary>
          {TAB_CONTENT[activeTab] ?? <OptionChainTab />}
        </ErrorBoundary>
        {isLoading && <LoadingOverlay label="LOADING MARKET DATA" />}
      </main>
      <StatusBar />
    </div>
  );
}

// ─── Root ─────────────────────────────────────────────────────────────────────

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(() => !!tokenStore.get());

  if (!isAuthenticated) {
    return <LoginPage onAuth={() => setIsAuthenticated(true)} />;
  }

  return <AuthenticatedApp />;
}

export default App;
