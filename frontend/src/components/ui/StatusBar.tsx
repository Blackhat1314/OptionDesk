import React, { useEffect, useState } from 'react';
import { useMarketStore } from '../../store/marketStore';
import { fmt } from '../../utils/format';
import { api } from '../../utils/api';

interface HealthData {
  status: string;
  connections: number;
  redis: boolean;
  demo_mode: boolean;
  timestamp: number;
}

// All indices shown in the bottom ticker
const TICKER_SYMBOLS = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX', 'INDIAVIX', 'GIFTNIFTY'] as const;

export const StatusBar: React.FC = () => {
  const { isConnected, lastUpdate, chain, summary, symbolCache } = useMarketStore();
  const [health, setHealth] = useState<HealthData | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const poll = async () => {
      try {
        const h = await api.healthCheck() as unknown as HealthData;
        setHealth(h);
      } catch {}
    };
    poll();
    const t = setInterval(poll, 10_000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => { if (lastUpdate) setTick(n => n + 1); }, [lastUpdate]);

  const lag = lastUpdate ? Math.floor((Date.now() - lastUpdate) / 1000) : null;

  // Build ticker quotes from symbolCache (populated by WS ticks + REST prefetch)
  const tickerQuotes = TICKER_SYMBOLS.map(sym => {
    const s = symbolCache[sym]?.summary;
    return {
      symbol:     sym,
      ltp:        s?.spot_price    ?? 0,
      change:     s?.day_change    ?? 0,
      change_pct: s?.day_change_pct ?? 0,
    };
  }).filter(q => q.ltp > 0);

  return (
    <div className="flex flex-col bg-bg-secondary border-t border-border-primary shrink-0">
      {/* ── Index Price Ticker ── */}
      {tickerQuotes.length > 0 && <ContractTicker quotes={tickerQuotes} />}

      {/* ── Status Row ── */}
      <div className="flex items-center gap-3 px-3 py-0.5 text-2xs font-mono text-text-muted">
        <div className="flex items-center gap-1.5">
          <div className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-market-up animate-pulse-fast' : 'bg-market-down'}`} />
          <span className={isConnected ? 'text-market-up' : 'text-market-down'}>
            {isConnected ? 'LIVE' : 'OFFLINE'}
          </span>
        </div>
        <Divider />
        {health?.demo_mode && (
          <span className="px-1 bg-accent-yellow/20 text-accent-yellow border border-accent-yellow/40 font-bold">DEMO</span>
        )}
        {health !== null && (
          <span className={health.redis ? 'text-market-up' : 'text-text-muted'}>
            Redis {health.redis ? '✓' : '✗'}
          </span>
        )}
        <Divider />
        {lag !== null && (
          <span className={lag > 15 ? 'text-market-down' : ''}>
            {lag === 0 ? 'just now' : `${lag}s ago`}
          </span>
        )}
        {tick > 0 && lag !== null && lag < 2 && (
          <span className="text-market-up animate-pulse-fast">●</span>
        )}
        <Divider />
        {chain && (
          <span>{chain.rows.length} strikes · ATM {fmt.strike(chain.atm_strike)} · {chain.expiry}</span>
        )}
        {summary && (
          <>
            <Divider />
            <span>
              PCR{' '}
              <span className={summary.pcr_oi >= 1 ? 'text-market-up' : 'text-market-down'}>
                {summary.pcr_oi.toFixed(2)}
              </span>
            </span>
            <Divider />
            <span>
              MAX PAIN <span className="text-accent-yellow">{fmt.strike(summary.max_pain)}</span>
            </span>
          </>
        )}
        <div className="flex-1" />
        {health && <span>{health.connections} ws</span>}
        <Divider />
        <span className="text-border-primary tracking-widest">OPTIONSDESK v2.0</span>
      </div>
    </div>
  );
};

// ─── Index Price Ticker ───────────────────────────────────────────────────────

interface IndexQuote { symbol: string; ltp: number; change: number; change_pct: number; }

const ContractTicker: React.FC<{ quotes: IndexQuote[] }> = ({ quotes }) => {
  // Triple the items so the scroll looks continuous
  const items = [...quotes, ...quotes, ...quotes];
  return (
    <div className="overflow-hidden border-b border-border-secondary bg-bg-primary h-6 flex items-center">
      <div className="flex items-center animate-ticker whitespace-nowrap">
        {items.map((q, i) => {
          const up = q.change >= 0;
          return (
            <span
              key={i}
              className="inline-flex items-center gap-2 px-5 text-2xs font-mono border-r border-border-secondary h-6"
            >
              <span className="text-text-muted font-bold tracking-wider">{q.symbol}</span>
              <span className="text-text-primary tabular-nums font-bold">{fmt.num(q.ltp, 2)}</span>
              <span className={`tabular-nums ${up ? 'text-market-up' : 'text-market-down'}`}>
                {up ? '▲' : '▼'} {up ? '+' : ''}{fmt.num(q.change, 2)} ({up ? '+' : ''}{q.change_pct.toFixed(2)}%)
              </span>
            </span>
          );
        })}
      </div>
    </div>
  );
};

const Divider: React.FC = () => <div className="w-px h-3 bg-border-primary" />;
