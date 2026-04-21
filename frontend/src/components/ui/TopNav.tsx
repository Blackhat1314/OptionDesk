import React, { useEffect, useState, useRef } from 'react';
import { useMarketStore } from '../../store/marketStore';
import { fmt } from '../../utils/format';
import { api } from '../../utils/api';
import type { TabId, Tab } from '../../types';

const TABS: Tab[] = [
  { id: 'chain',        label: 'OPTION CHAIN',    shortcut: 'F1' },
  { id: 'greeks',       label: 'GREEKS',          shortcut: 'F2' },
  { id: 'iv',           label: 'IV ANALYTICS',    shortcut: 'F3' },
  { id: 'decision',     label: 'DECISION ENGINE', shortcut: 'F4' },
  { id: 'intelligence', label: 'INTELLIGENCE',    shortcut: 'F5' },
  { id: 'screener',     label: '⚡ SCREENER',     shortcut: 'F6' },
  { id: 'strategy',     label: 'STRATEGY',        shortcut: 'F7' },
  { id: 'historical',   label: 'HISTORICAL',      shortcut: 'F8' },
  { id: 'news',         label: 'NEWS',            shortcut: 'F9' },
  { id: 'livetv',       label: 'LIVE TV',         shortcut: 'F10' },
  { id: 'guide',        label: 'GUIDE',           shortcut: 'F11' },
];

// ─── Live Index Ticker (other indices) ───────────────────────────────────────

// All non-NIFTY indices shown in the top bar
const OTHER_INDICES = ['BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX', 'INDIAVIX', 'GIFTNIFTY'] as const;

const IndexTicker: React.FC = () => {
  const symbolCache = useMarketStore(s => s.symbolCache);
  // Local ref cache — persists last known good values across re-renders
  // Prevents prices from flashing to '—' during WS-triggered re-renders
  const lastKnown = React.useRef<Record<string, { ltp: number; change: number; changePct: number }>>({});

  // Fetch all indices in ONE batch call at startup (and every 60s)
  React.useEffect(() => {
    const fetchAll = async () => {
      try {
        const results = await api.getExtraIndices();
        results.forEach((q: { symbol: string; ltp: number; change: number; change_pct: number }) => {
          if (q.ltp > 0) {
            const prevClose = q.ltp - (q.change ?? 0);
            if (prevClose > 0) {
              useMarketStore.getState().setPrevClose(q.symbol, prevClose);
            }
            const existing = useMarketStore.getState().symbolCache[q.symbol]?.summary;
            useMarketStore.getState().setSummaryForSymbol(q.symbol, {
              ...(existing ?? {}),
              symbol:         q.symbol,
              spot_price:     q.ltp,
              day_change:     q.change    ?? 0,
              day_change_pct: q.change_pct ?? 0,
            } as any);
          }
        });
      } catch {}
    };
    fetchAll();
    const t = setInterval(fetchAll, 60_000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="flex items-center gap-3">
      {OTHER_INDICES.map(sym => {
        const summary   = symbolCache[sym]?.summary;
        const ltp       = summary?.spot_price ?? 0;
        const change    = summary?.day_change    ?? 0;
        const changePct = summary?.day_change_pct ?? 0;

        // Update ref cache whenever we have a valid value
        if (ltp > 0) {
          lastKnown.current[sym] = { ltp, change, changePct };
        }
        // Use ref cache as fallback — never show '—' if we had a value before
        const display = ltp > 0 ? { ltp, change, changePct } : lastKnown.current[sym];

        const isUp  = (display?.change ?? 0) >= 0;
        const isVix = sym === 'INDIAVIX';
        const upColor   = isVix ? 'text-market-down' : 'text-market-up';
        const downColor = isVix ? 'text-market-up'   : 'text-market-down';

        return (
          <div key={sym} className="flex flex-col items-start">
            <span className="text-2xs font-mono text-text-muted leading-none">
              {sym === 'INDIAVIX' ? 'VIX' : sym === 'GIFTNIFTY' ? 'GIFT' : sym}
            </span>
            <div className="flex items-baseline gap-1">
              <span className="text-xs font-mono font-bold text-text-primary tabular-nums">
                {display ? fmt.num(display.ltp, 2) : '—'}
              </span>
              {display && (
                <span className={`text-2xs font-mono ${isUp ? upColor : downColor}`}>
                  {isUp ? '+' : ''}{display.changePct.toFixed(2)}%
                </span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};

// ─── Main TopNav ──────────────────────────────────────────────────────────────

export const TopNav: React.FC = () => {
  const {
    activeTab, setActiveTab,
    activeExpiry,
    isConnected,
    spotPrice, dayChange, dayChangePct,
    summary,
  } = useMarketStore();

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'F1') setActiveTab('chain');
      else if (e.key === 'F2') setActiveTab('greeks');
      else if (e.key === 'F3') setActiveTab('iv');
      else if (e.key === 'F4') setActiveTab('decision');
      else if (e.key === 'F5') setActiveTab('strategy');
      else if (e.key === 'F6') setActiveTab('historical');
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [setActiveTab]);

  // Poll NIFTY quote every 3s as REST fallback
  useEffect(() => {
    const fetchQuote = async () => {
      try {
        const q = await api.getQuote('NIFTY');
        if (q.ltp > 0) {
          useMarketStore.getState().updateSpotPrice(q.ltp, q.change, q.change_pct);
          // Store prevClose so tick handler can recalculate day change in real-time
          const prevClose = q.ltp - (q.change ?? 0);
          if (prevClose > 0) {
            useMarketStore.getState().setPrevClose('NIFTY', prevClose);
          }
        }
      } catch {}
    };
    fetchQuote();
    const t = setInterval(fetchQuote, 3000);
    return () => clearInterval(t);
  }, []);

  const changeClass = dayChange >= 0 ? 'text-market-up' : 'text-market-down';
  const changeBg    = dayChange >= 0 ? 'bg-market-up/10' : 'bg-market-down/10';

  return (
    <div className="flex flex-col bg-bg-secondary border-b border-border-primary select-none">
      {/* Top bar */}
      <div className="flex items-center px-3 py-2 gap-3 border-b border-border-secondary overflow-x-auto">

        {/* Logo */}
        <div className="flex items-center gap-2 shrink-0">
          <div className="w-5 h-5 border border-accent-yellow flex items-center justify-center">
            <div className="w-2.5 h-2.5 bg-accent-yellow" />
          </div>
          <span className="font-mono text-accent-yellow font-bold text-sm tracking-widest">
            OPTIONS<span className="text-text-secondary">DESK</span>
          </span>
        </div>

        <div className="w-px h-5 bg-border-primary shrink-0" />

        {/* Other indices — live spot prices (left side) */}
        <div className="shrink-0">
          <IndexTicker />
        </div>

        <div className="w-px h-5 bg-border-primary shrink-0" />

        {/* Expiry */}
        {activeExpiry && (
          <div className="flex items-center gap-1.5 shrink-0">
            <span className="text-2xs text-text-muted font-mono">EXPIRY</span>
            <span className="bg-bg-panel border border-border-primary text-accent-yellow font-mono text-xs px-2 py-0.5 font-bold">
              {activeExpiry}
            </span>
          </div>
        )}

        <div className="flex-1" />

        {/* NIFTY Spot Price — main display */}
        <div className={`flex items-center gap-3 px-3 py-1 shrink-0 ${changeBg} border border-${dayChange >= 0 ? 'market-up' : 'market-down'}/20`}>
          <div>
            <div className="text-2xs text-text-muted font-mono">NIFTY SPOT</div>
            <div className="text-lg font-mono font-bold text-text-primary tracking-tight tabular-nums">
              {fmt.num(spotPrice, 2)}
            </div>
          </div>
          <div className={`text-right ${changeClass}`}>
            <div className="text-xs font-mono font-bold">{fmt.oiChange(dayChange)}</div>
            <div className="text-xs font-mono">{fmt.pct(dayChangePct)}</div>
          </div>
        </div>

        {/* NIFTY Summary Metrics */}
        {summary && (
          <>
            <MetricPill label="PCR OI"   value={summary.pcr_oi.toFixed(2)} />
            <MetricPill label="MAX PAIN" value={fmt.strike(summary.max_pain)} />
            <MetricPill label="ATM IV"   value={`${summary.atm_iv.toFixed(1)}%`} />
            <MetricPill label="CALL OI"  value={fmt.compact(summary.total_call_oi)} color="text-chart-call" />
            <MetricPill label="PUT OI"   value={fmt.compact(summary.total_put_oi)}  color="text-chart-put" />
          </>
        )}

        <div className="w-px h-5 bg-border-primary shrink-0" />

        {/* Connection Status */}
        <div className="flex items-center gap-1.5 shrink-0">
          <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-market-up animate-pulse-fast' : 'bg-market-down'}`} />
          <span className={`text-2xs font-mono font-bold ${isConnected ? 'text-market-up' : 'text-market-down'}`}>
            {isConnected ? 'LIVE' : 'DISCONNECTED'}
          </span>
        </div>

        {/* Demo mode badge */}
        {localStorage.getItem('auth_token') === 'DEMO_MODE_TOKEN' && (
          <div className="flex items-center gap-1 px-2 py-0.5 border border-accent-yellow/50 bg-accent-yellow/10 shrink-0 animate-pulse-fast">
            <span className="text-2xs font-mono font-bold text-accent-yellow">⚡ DEMO</span>
          </div>
        )}

        {/* Clock */}
        <LiveClock />

        {/* Logout */}
        <button
          onClick={async () => {
            try { await import('../../utils/api').then(m => m.authApi.logout()); } catch {}
            import('../../utils/api').then(m => m.tokenStore.clear());
            window.location.reload();
          }}
          className="text-2xs font-mono text-text-muted hover:text-market-down border border-border-secondary px-2 py-0.5 hover:border-market-down/50 transition-all shrink-0"
          title="Logout"
        >
          ⏻ LOGOUT
        </button>
      </div>

      {/* Tab Navigation */}
      <div className="flex items-end gap-0">
        {TABS.map((tab) => (
          <TabButton
            key={tab.id}
            tab={tab}
            isActive={activeTab === tab.id}
            onClick={() => setActiveTab(tab.id)}
          />
        ))}
        <div className="flex-1 border-b border-border-primary" />
      </div>
    </div>
  );
};

// ─── Shared components ────────────────────────────────────────────────────────

const MetricPill: React.FC<{ label: string; value: string; color?: string }> = ({
  label, value, color = 'text-accent-yellow',
}) => (
  <div className="flex flex-col items-center shrink-0">
    <span className="text-2xs text-text-muted font-mono">{label}</span>
    <span className={`text-xs font-mono font-bold ${color}`}>{value}</span>
  </div>
);

const TabButton: React.FC<{ tab: Tab; isActive: boolean; onClick: () => void }> = ({
  tab, isActive, onClick,
}) => (
  <button
    onClick={onClick}
    className={`
      group relative flex items-center gap-2 px-4 py-2
      font-mono text-xs font-bold tracking-wider
      border-t border-l border-r transition-all duration-150
      ${isActive
        ? 'bg-bg-primary text-accent-yellow border-border-accent border-b-bg-primary -mb-px z-10'
        : 'bg-bg-secondary text-text-muted border-border-secondary border-b-border-primary hover:text-text-primary hover:bg-bg-hover'
      }
    `}
  >
    <span className="text-2xs opacity-50">{tab.shortcut}</span>
    <span>{tab.label}</span>
    {isActive && <div className="absolute top-0 left-0 right-0 h-0.5 bg-accent-yellow" />}
  </button>
);

const LiveClock: React.FC = () => {
  const [time, setTime] = React.useState('');
  useEffect(() => {
    const update = () => {
      setTime(new Date().toLocaleTimeString('en-IN', {
        timeZone: 'Asia/Kolkata', hour12: false,
        hour: '2-digit', minute: '2-digit', second: '2-digit',
      }));
    };
    update();
    const t = setInterval(update, 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="text-right shrink-0">
      <div className="text-2xs text-text-muted font-mono">IST</div>
      <div className="text-xs font-mono text-text-secondary font-bold tabular-nums">{time}</div>
    </div>
  );
};
