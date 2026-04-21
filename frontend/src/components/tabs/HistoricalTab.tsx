import React, { useState, useCallback } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, BarChart, Bar } from 'recharts';
import { fmt } from '../../utils/format';
import { api } from '../../utils/api';

// All supported indices with their security IDs
const INDEX_OPTIONS = [
  { label: 'NIFTY 50',       id: '13',   segment: 'IDX_I' },
  { label: 'BANK NIFTY',     id: '25',   segment: 'IDX_I' },
  { label: 'FIN NIFTY',      id: '27',   segment: 'IDX_I' },
  { label: 'MIDCAP NIFTY',   id: '442',  segment: 'IDX_I' },
  { label: 'SENSEX',         id: '51',   segment: 'IDX_I' },
  { label: 'INDIA VIX',      id: '21',   segment: 'IDX_I' },
  { label: 'GIFT NIFTY',     id: '5024', segment: 'IDX_I' },
];

// Intervals — no 1-min (too noisy, too much data)
const INTERVAL_OPTIONS = [
  { label: '5 Min',   value: 5    },
  { label: '15 Min',  value: 15   },
  { label: '25 Min',  value: 25   },
  { label: '1 Hour',  value: 60   },
  { label: 'Daily',   value: 1440 },
];

export const HistoricalTab: React.FC = () => {
  const [data, setData]         = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedIdx, setSelectedIdx] = useState(0);   // index into INDEX_OPTIONS
  const [interval, setInterval] = useState(60);
  const [error, setError]       = useState('');

  const selected = INDEX_OPTIONS[selectedIdx];

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError('');
    try {
      const json = await api.getHistorical(selected.id, selected.segment, interval);

      const opens      = json.open      || [];
      const highs      = json.high      || [];
      const lows       = json.low       || [];
      const closes     = json.close     || [];
      const volumes    = json.volume    || [];
      const timestamps = json.timestamp || [];

      if (!timestamps.length) {
        throw new Error('No data available — try a different interval or check market hours');
      }

      const bars = timestamps.map((ts: number, i: number) => ({
        time: interval >= 1440
          ? new Date(ts * 1000).toLocaleDateString('en-IN')
          : new Date(ts * 1000).toLocaleString('en-IN', {
              timeZone: 'Asia/Kolkata', hour12: false,
              month: '2-digit', day: '2-digit',
              hour: '2-digit', minute: '2-digit',
            }),
        open:   opens[i]   ?? 0,
        high:   highs[i]   ?? 0,
        low:    lows[i]    ?? 0,
        close:  closes[i]  ?? 0,
        volume: volumes[i] ?? 0,
      })).filter((b: any) => b.close > 0);

      setData(bars);
    } catch (e: any) {
      setError(e.message || 'Failed to fetch data');
      setData([]);
    } finally {
      setIsLoading(false);
    }
  }, [selected, interval]);

  const lastBar  = data[data.length - 1];
  const firstBar = data[0];
  const netChange = lastBar && firstBar
    ? ((lastBar.close - firstBar.close) / firstBar.close * 100)
    : 0;

  return (
    <div className="flex h-full overflow-auto bg-bg-primary p-3 gap-3 flex-col">
      {/* Controls */}
      <div className="flex items-center gap-3 border border-border-primary bg-bg-panel p-3 shrink-0 flex-wrap">
        <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest shrink-0">
          HISTORICAL DATA
        </div>

        {/* Index selector */}
        <div className="flex items-center gap-2">
          <span className="text-2xs text-text-muted font-mono shrink-0">INDEX</span>
          <select
            value={selectedIdx}
            onChange={(e) => setSelectedIdx(Number(e.target.value))}
            className="bg-bg-primary border border-border-primary text-text-primary font-mono text-xs px-2 py-0.5 focus:outline-none focus:border-accent-yellow"
          >
            {INDEX_OPTIONS.map((opt, i) => (
              <option key={opt.id} value={i}>{opt.label}</option>
            ))}
          </select>
        </div>

        {/* Interval selector */}
        <div className="flex items-center gap-2">
          <span className="text-2xs text-text-muted font-mono shrink-0">INTERVAL</span>
          <div className="flex gap-1">
            {INTERVAL_OPTIONS.map(opt => (
              <button
                key={opt.value}
                onClick={() => setInterval(opt.value)}
                className="px-2 py-0.5 text-2xs font-mono transition-all"
                style={{
                  color: interval === opt.value ? '#0a0a0a' : '#a0a0a0',
                  backgroundColor: interval === opt.value ? '#ffcc00' : 'transparent',
                  border: `1px solid ${interval === opt.value ? '#ffcc00' : '#2a2a2a'}`,
                }}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        <button
          onClick={fetchData}
          disabled={isLoading}
          className="px-4 py-1 bg-accent-yellow text-black font-mono font-bold text-xs hover:bg-yellow-400 disabled:opacity-50 transition-colors shrink-0"
        >
          {isLoading ? 'LOADING...' : '▶ FETCH'}
        </button>

        {error && (
          <span className="text-market-down text-xs font-mono">⚠ {error}</span>
        )}

        {data.length > 0 && (
          <div className="ml-auto flex items-center gap-3 text-2xs font-mono">
            <span className="text-text-muted">{data.length} bars</span>
            <span className="text-text-muted">·</span>
            <span className="text-text-secondary">{selected.label}</span>
            {lastBar && (
              <>
                <span className="text-text-muted">·</span>
                <span className="text-text-primary font-bold">{fmt.price(lastBar.close)}</span>
                <span style={{ color: netChange >= 0 ? '#00c853' : '#f44336' }}>
                  {netChange >= 0 ? '+' : ''}{netChange.toFixed(2)}%
                </span>
              </>
            )}
          </div>
        )}
      </div>

      {data.length === 0 ? (
        <div className="flex items-center justify-center flex-1 border border-border-primary">
          <div className="text-center text-text-muted font-mono text-xs">
            <div className="text-3xl mb-3 opacity-30">📊</div>
            <div className="text-text-secondary mb-1">Select an index and interval</div>
            <div className="text-2xs opacity-60">then click FETCH to load chart data</div>
          </div>
        </div>
      ) : (
        <>
          {/* Price Chart */}
          <div className="border border-border-primary bg-bg-panel p-3 flex-1">
            <div className="flex items-center justify-between mb-2">
              <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest">
                {selected.label} — PRICE HISTORY
              </div>
              {lastBar && (
                <div className="flex items-center gap-3 text-2xs font-mono">
                  <span className="text-text-muted">H: <span className="text-market-up">{fmt.price(lastBar.high)}</span></span>
                  <span className="text-text-muted">L: <span className="text-market-down">{fmt.price(lastBar.low)}</span></span>
                  <span className="text-text-muted">C: <span className="text-accent-yellow font-bold">{fmt.price(lastBar.close)}</span></span>
                </div>
              )}
            </div>
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={data} margin={{ top: 4, right: 8, bottom: 16, left: 0 }}>
                <CartesianGrid strokeDasharray="2 4" stroke="#1e1e1e" />
                <XAxis
                  dataKey="time"
                  tick={{ fill: '#606060', fontSize: 8, fontFamily: 'monospace' }}
                  tickLine={false}
                  interval={Math.floor(data.length / 8)}
                />
                <YAxis
                  tick={{ fill: '#606060', fontSize: 8, fontFamily: 'monospace' }}
                  tickLine={false}
                  width={52}
                  domain={['auto', 'auto']}
                />
                <Tooltip
                  contentStyle={{ background: '#141414', border: '1px solid #2a2a2a', fontFamily: 'monospace', fontSize: 11 }}
                  formatter={(v: number, name: string) => [fmt.price(v), name === 'close' ? 'Close' : name === 'high' ? 'High' : 'Low']}
                />
                <Line type="monotone" dataKey="close" stroke="#ffcc00" dot={false} strokeWidth={1.5} name="close" />
                <Line type="monotone" dataKey="high"  stroke="#00c853" dot={false} strokeWidth={1} strokeDasharray="2 2" name="high" />
                <Line type="monotone" dataKey="low"   stroke="#ff1744" dot={false} strokeWidth={1} strokeDasharray="2 2" name="low" />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Volume Chart — hide for VIX (no volume) */}
          {selected.id !== '21' && (
            <div className="border border-border-primary bg-bg-panel p-3 shrink-0">
              <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest mb-2">VOLUME</div>
              <ResponsiveContainer width="100%" height={80}>
                <BarChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
                  <XAxis dataKey="time" tick={false} />
                  <YAxis tick={{ fill: '#606060', fontSize: 8, fontFamily: 'monospace' }} tickLine={false} width={40} />
                  <Tooltip
                    contentStyle={{ background: '#141414', border: '1px solid #2a2a2a', fontFamily: 'monospace', fontSize: 11 }}
                    formatter={(v: number) => [fmt.compact(v), 'Volume']}
                  />
                  <Bar dataKey="volume" fill="#00d4ff" opacity={0.6} maxBarSize={6} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* OHLCV Table */}
          <div className="border border-border-primary bg-bg-panel p-3 shrink-0 max-h-48 overflow-y-auto">
            <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest mb-2">OHLCV DATA</div>
            <div className="grid grid-cols-6 text-2xs font-mono text-text-muted border-b border-border-primary pb-1 mb-1">
              <span>TIME</span>
              <span className="text-right">OPEN</span>
              <span className="text-right">HIGH</span>
              <span className="text-right">LOW</span>
              <span className="text-right">CLOSE</span>
              <span className="text-right">VOL</span>
            </div>
            {[...data].reverse().slice(0, 20).map((bar, i) => (
              <div key={i} className="grid grid-cols-6 text-2xs font-mono py-0.5 hover:bg-bg-hover">
                <span className="text-text-muted truncate">{bar.time}</span>
                <span className="text-right text-text-secondary">{fmt.price(bar.open)}</span>
                <span className="text-right text-market-up">{fmt.price(bar.high)}</span>
                <span className="text-right text-market-down">{fmt.price(bar.low)}</span>
                <span className={`text-right font-bold ${bar.close >= bar.open ? 'text-market-up' : 'text-market-down'}`}>
                  {fmt.price(bar.close)}
                </span>
                <span className="text-right text-text-muted">
                  {bar.volume > 0 ? fmt.compact(bar.volume) : '—'}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
};
