import React, { useMemo, useRef } from 'react';
import { FixedSizeList as List } from 'react-window';
import AutoSizer from 'react-virtualized-auto-sizer';
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceLine, CartesianGrid, Legend,
} from 'recharts';
import { useMarketStore } from '../../store/marketStore';
import { fmt, getOIBarWidth, getITMClass } from '../../utils/format';
import type { OptionChainRow, MlSignal } from '../../types';

const ROW_HEIGHT = 28;

export const OptionChainTab: React.FC = () => {
  const { chain, strikeRange, setStrikeRange, activeSymbol, mlSignals } = useMarketStore();

  // Check if market is open (9:15 - 15:30 IST, Mon-Fri)
  const isMarketOpen = useMemo(() => {
    const now = new Date();
    const ist = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }));
    const day = ist.getDay(); // 0=Sun, 6=Sat
    const mins = ist.getHours() * 60 + ist.getMinutes();
    return day >= 1 && day <= 5 && mins >= 555 && mins <= 930; // 9:15=555, 15:30=930
  }, []);

  // Get top ML signal for ATM strike (show regardless of threshold)
  const topMlSignal = useMemo(() => {
    if (!isMarketOpen) return null;
    const sigs = mlSignals[activeSymbol] ?? [];
    // Prefer strong signals, fall back to any signal
    return sigs.find(s => s.strong) ?? (sigs.length > 0 ? sigs[0] : null);
  }, [mlSignals, activeSymbol, isMarketOpen]);

  const filteredRows = useMemo(() => {
    if (!chain) return [];
    const atm = chain.atm_strike;
    // Sort rows by strike, find ATM index, slice exactly strikeRange*2+1 rows
    const sorted = [...chain.rows].sort((a, b) => a.strike - b.strike);
    const atmIdx = sorted.reduce(
      (best, row, i) =>
        Math.abs(row.strike - atm) < Math.abs(sorted[best].strike - atm) ? i : best,
      0
    );
    const half  = strikeRange;
    const total = strikeRange * 2 + 1;
    let start = atmIdx - half;
    let end   = start + total;
    if (start < 0) { start = 0; end = Math.min(total, sorted.length); }
    if (end > sorted.length) { end = sorted.length; start = Math.max(0, end - total); }
    return sorted.slice(start, end);
  }, [chain, strikeRange]);

  const maxCallOI = useMemo(
    () => Math.max(...(filteredRows.map((r) => r.call.oi) || [1])),
    [filteredRows]
  );
  const maxPutOI = useMemo(
    () => Math.max(...(filteredRows.map((r) => r.put.oi) || [1])),
    [filteredRows]
  );

  if (!chain) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <div className="text-accent-yellow font-mono text-sm animate-blink mb-2">■ FETCHING DATA</div>
          <div className="text-text-muted font-mono text-xs">Connecting to Dhan API...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left: Option Chain Table */}
      <div className="flex flex-col flex-1 min-w-0 border-r border-border-primary">
        {/* Controls */}
        <div className="flex items-center gap-4 px-3 py-1.5 bg-bg-secondary border-b border-border-primary shrink-0">
          <span className="text-2xs text-text-muted font-mono">STRIKES ±</span>
          {[5, 10, 15].map((n) => (
            <button
              key={n}
              onClick={() => setStrikeRange(n)}
              className={`text-2xs font-mono px-2 py-0.5 border transition-all ${
                strikeRange === n
                  ? 'border-accent-yellow text-accent-yellow bg-accent-yellow/10'
                  : 'border-border-primary text-text-muted hover:border-text-secondary'
              }`}
            >
              {n}
            </button>
          ))}

          {/* ML Prediction — shown in controls bar */}
          <div className="flex items-center gap-1.5 px-2 py-0.5 border border-border-primary bg-bg-tertiary rounded-sm">
            <span className="text-2xs text-text-muted font-mono">ML</span>
            {!isMarketOpen ? (
              <span className="text-2xs font-mono text-text-muted">0.00%</span>
            ) : topMlSignal ? (
              <>
                <span className={`text-2xs font-bold font-mono ${
                  topMlSignal.direction === 'UP'
                    ? topMlSignal.strong ? 'text-market-up' : 'text-market-up/60'
                    : topMlSignal.strong ? 'text-market-down' : 'text-market-down/60'
                }`}>
                  {topMlSignal.direction === 'UP' ? '↑' : '↓'}
                  {(topMlSignal.confidence * 100).toFixed(0)}%
                  {topMlSignal.strong && <span className="text-accent-yellow ml-0.5">★</span>}
                </span>
                <span className="text-2xs text-text-muted font-mono">
                  {topMlSignal.strike} {topMlSignal.type}
                </span>
              </>
            ) : (
              <span className="text-2xs font-mono text-text-muted">—</span>
            )}
          </div>

          <div className="ml-auto flex items-center gap-3 text-2xs font-mono text-text-muted">
            <span className="text-chart-call">■ CALL</span>
            <span className="text-chart-put">■ PUT</span>
            <span className="text-accent-yellow">■ ATM</span>
          </div>
        </div>

        {/* Table Header */}
        <ChainHeader />

        {/* Virtualized Rows */}
        <div className="flex-1 min-h-0">
          <AutoSizer>
            {({ height, width }) => (
              <List
                height={height}
                width={width}
                itemCount={filteredRows.length}
                itemSize={ROW_HEIGHT}
                itemData={{ rows: filteredRows, maxCallOI, maxPutOI, spot: chain.spot_price, mlSignals: mlSignals[activeSymbol] ?? [] }}
              >
                {ChainRow}
              </List>
            )}
          </AutoSizer>
        </div>
      </div>

      {/* Right: Charts Panel */}
      <div className="w-96 flex flex-col overflow-y-auto bg-bg-secondary">
        <OIDistributionChart rows={filteredRows} />
        <IVSmileChart rows={filteredRows} spot={chain.spot_price} />
        <PCRChart rows={filteredRows} />
      </div>
    </div>
  );
};

// ─── Table Header ─────────────────────────────────────────────────────────────

const ChainHeader: React.FC = () => (
  <div
    className="grid font-mono text-2xs text-text-muted uppercase tracking-widest
                bg-bg-tertiary border-b border-border-primary shrink-0"
    style={{ gridTemplateColumns: GRID_COLS }}
  >
    <ColHead>OI</ColHead>
    <ColHead>Δ OI</ColHead>
    <ColHead>VOL</ColHead>
    <ColHead>IV%</ColHead>
    <ColHead>Δ</ColHead>
    <ColHead>LTP</ColHead>
    <ColHead center>STRIKE</ColHead>
    <ColHead>LTP</ColHead>
    <ColHead>Δ</ColHead>
    <ColHead>IV%</ColHead>
    <ColHead>VOL</ColHead>
    <ColHead>Δ OI</ColHead>
    <ColHead>OI</ColHead>
  </div>
);

const ColHead: React.FC<{ children: React.ReactNode; center?: boolean }> = ({ children, center }) => (
  <div className={`px-1 py-1 ${center ? 'text-center' : ''} truncate`}>{children}</div>
);

// ─── Grid Template ────────────────────────────────────────────────────────────

const GRID_COLS =
  '1fr 0.7fr 0.7fr 0.6fr 0.6fr 0.8fr 1.1fr 0.8fr 0.6fr 0.6fr 0.7fr 0.7fr 1fr';

// ─── Virtualized Row ──────────────────────────────────────────────────────────

interface RowData {
  rows: OptionChainRow[];
  maxCallOI: number;
  maxPutOI: number;
  spot: number;
  mlSignals: MlSignal[];
}

const ChainRow: React.FC<{ index: number; style: React.CSSProperties; data: RowData }> = ({
  index, style, data,
}) => {
  const { rows, maxCallOI, maxPutOI, spot, mlSignals } = data;
  const row = rows[index];
  if (!row) return null;

  const { call, put, strike, is_atm } = row;
  const isCallITM = strike <= spot;
  const isPutITM = strike >= spot;

  // Find ML signals for this strike
  const callSig = mlSignals.find(s => s.strike === strike && s.type === 'CALL');
  const putSig  = mlSignals.find(s => s.strike === strike && s.type === 'PUT');

  const rowBg = is_atm
    ? 'bg-accent-yellow/8 border-b border-accent-yellow/30'
    : index % 2 === 0
    ? 'bg-transparent border-b border-border-secondary/50'
    : 'bg-bg-secondary/30 border-b border-border-secondary/50';

  return (
    <div
      style={{ ...style, gridTemplateColumns: GRID_COLS }}
      className={`grid items-center font-mono text-xs ${rowBg} hover:bg-bg-hover/50 transition-colors cursor-pointer group`}
    >
      {/* CALL side */}
      <OICell value={call.oi} max={maxCallOI} side="call" isITM={isCallITM} />
      <Cell value={fmt.oiChange(call.oi_change)} className={fmt.colorClass(call.oi_change)} />
      <Cell value={fmt.compact(call.volume)} className="text-text-secondary" />
      <Cell value={fmt.iv(call.iv)} className="text-accent-cyan" />
      <Cell value={call.greeks.delta.toFixed(3)} className="text-text-secondary" />
      <LTPCell value={call.ltp} securityId={call.security_id} mlSignal={callSig} />

      {/* STRIKE */}
      <div className={`text-center px-1 font-bold text-sm ${is_atm ? 'text-accent-yellow' : 'text-text-primary'}`}>
        {is_atm && <span className="text-2xs text-accent-yellow mr-1">▶</span>}
        {fmt.strike(strike)}
        {is_atm && <span className="text-2xs text-accent-yellow ml-1">◀</span>}
      </div>

      {/* PUT side */}
      <LTPCell value={put.ltp} securityId={put.security_id} mlSignal={putSig} />
      <Cell value={put.greeks.delta.toFixed(3)} className="text-text-secondary" />
      <Cell value={fmt.iv(put.iv)} className="text-accent-cyan" />
      <Cell value={fmt.compact(put.volume)} className="text-text-secondary" />
      <Cell value={fmt.oiChange(put.oi_change)} className={fmt.colorClass(put.oi_change)} />
      <OICell value={put.oi} max={maxPutOI} side="put" isITM={isPutITM} />
    </div>
  );
};

const Cell: React.FC<{ value: string; className?: string }> = ({ value, className }) => (
  <div className={`px-1 truncate tabular-nums ${className}`}>{value}</div>
);

const LTPCell: React.FC<{ value: number; securityId: string; mlSignal?: MlSignal }> = ({ value, securityId, mlSignal }) => {
  const flash = useMarketStore((s) => s.tickFlashes[securityId]);
  const flashClass = flash === 'up' ? 'bg-market-up/25 text-market-up' : flash === 'down' ? 'bg-market-down/25 text-market-down' : 'text-text-primary';
  return (
    <div className={`px-1 tabular-nums font-bold transition-colors duration-200 flex items-center gap-0.5 ${flashClass}`}>
      {fmt.price(value)}
      {mlSignal && (
        <span
          title={`ML: ${mlSignal.direction} ${(mlSignal.confidence * 100).toFixed(0)}% conf${mlSignal.strong ? ' ★ HIGH' : ''}${!mlSignal.candle_based ? ' (snapshot)' : ''}`}
          className={`text-2xs font-bold px-0.5 rounded leading-none ${
            mlSignal.direction === 'UP'
              ? mlSignal.strong
                ? 'text-market-up bg-market-up/20'
                : 'text-market-up/50 bg-market-up/10'
              : mlSignal.strong
                ? 'text-market-down bg-market-down/20'
                : 'text-market-down/50 bg-market-down/10'
          }`}
        >
          {mlSignal.candle_based === false ? '~' : (mlSignal.direction === 'UP' ? '↑' : '↓')}{(mlSignal.confidence * 100).toFixed(0)}
        </span>
      )}
    </div>
  );
};

const OICell: React.FC<{
  value: number;
  max: number;
  side: 'call' | 'put';
  isITM: boolean;
}> = ({ value, max, side, isITM }) => {
  const width = getOIBarWidth(value, max);
  const barColor = side === 'call' ? 'bg-chart-call/30' : 'bg-chart-put/30';
  const textColor = isITM ? (side === 'call' ? 'text-chart-call' : 'text-chart-put') : 'text-text-secondary';
  const barAlign = side === 'call' ? 'right-0' : 'left-0';

  return (
    <div className="relative px-1 overflow-hidden">
      <div
        className={`absolute top-0 ${barAlign} h-full ${barColor}`}
        style={{ width: `${width}%` }}
      />
      <span className={`relative tabular-nums text-2xs ${textColor}`}>
        {fmt.compact(value)}
      </span>
    </div>
  );
};

// ─── OI Distribution Chart ────────────────────────────────────────────────────

const OIDistributionChart: React.FC<{ rows: OptionChainRow[] }> = ({ rows }) => {
  const data = rows.slice(0, 25).map((r) => ({
    strike: r.strike,
    callOI: r.call.oi / 1000,
    putOI: r.put.oi / 1000,
    isATM: r.is_atm,
  }));

  return (
    <ChartPanel title="OI DISTRIBUTION" subtitle="(000s)">
      <ResponsiveContainer width="100%" height={160}>
        <BarChart data={data} margin={{ top: 4, right: 8, bottom: 16, left: 0 }}>
          <CartesianGrid strokeDasharray="2 4" stroke="#1e1e1e" />
          <XAxis
            dataKey="strike"
            tick={{ fill: '#606060', fontSize: 8, fontFamily: 'monospace' }}
            tickLine={false}
            interval={2}
          />
          <YAxis tick={{ fill: '#606060', fontSize: 8, fontFamily: 'monospace' }} tickLine={false} width={28} />
          <Tooltip content={<OITooltip />} />
          <Bar dataKey="callOI" fill="#00c853" opacity={0.8} maxBarSize={14} />
          <Bar dataKey="putOI" fill="#ff1744" opacity={0.8} maxBarSize={14} />
        </BarChart>
      </ResponsiveContainer>
    </ChartPanel>
  );
};

const OITooltip: React.FC<{ active?: boolean; payload?: any[]; label?: any }> = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-bg-panel border border-border-primary p-2 font-mono text-xs">
      <div className="text-text-muted mb-1">Strike: {label}</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} style={{ color: p.color }}>
          {p.dataKey === 'callOI' ? 'CE OI' : 'PE OI'}: {(p.value * 1000).toLocaleString('en-IN')}
        </div>
      ))}
    </div>
  );
};

// ─── IV Smile Chart ───────────────────────────────────────────────────────────

const IVSmileChart: React.FC<{ rows: OptionChainRow[]; spot: number }> = ({ rows, spot }) => {
  const data = rows
    .filter((r) => r.call.iv > 0 || r.put.iv > 0)
    .map((r) => ({
      strike: r.strike,
      callIV: r.call.iv > 0 ? r.call.iv : null,
      putIV: r.put.iv > 0 ? r.put.iv : null,
    }));

  return (
    <ChartPanel title="IV SMILE" subtitle="">
      <ResponsiveContainer width="100%" height={150}>
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 16, left: 0 }}>
          <CartesianGrid strokeDasharray="2 4" stroke="#1e1e1e" />
          <XAxis dataKey="strike" tick={{ fill: '#606060', fontSize: 8, fontFamily: 'monospace' }} tickLine={false} interval={2} />
          <YAxis tick={{ fill: '#606060', fontSize: 8, fontFamily: 'monospace' }} tickLine={false} width={28} />
          <Tooltip
            contentStyle={{ background: '#141414', border: '1px solid #2a2a2a', fontFamily: 'monospace', fontSize: 11 }}
            labelStyle={{ color: '#a0a0a0' }}
          />
          <ReferenceLine x={spot} stroke="#ffcc00" strokeDasharray="3 3" strokeWidth={1} />
          <Line type="monotone" dataKey="callIV" stroke="#00c853" dot={false} strokeWidth={1.5} connectNulls />
          <Line type="monotone" dataKey="putIV" stroke="#ff1744" dot={false} strokeWidth={1.5} connectNulls />
        </LineChart>
      </ResponsiveContainer>
    </ChartPanel>
  );
};

// ─── PCR Chart ────────────────────────────────────────────────────────────────

const PCRChart: React.FC<{ rows: OptionChainRow[] }> = ({ rows }) => {
  const data = rows.map((r) => ({
    strike: r.strike,
    pcr: r.pcr_oi > 0 ? r.pcr_oi : null,
    isATM: r.is_atm,
  }));

  return (
    <ChartPanel title="PCR (OI)" subtitle="">
      <ResponsiveContainer width="100%" height={130}>
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 16, left: 0 }}>
          <CartesianGrid strokeDasharray="2 4" stroke="#1e1e1e" />
          <XAxis dataKey="strike" tick={{ fill: '#606060', fontSize: 8, fontFamily: 'monospace' }} tickLine={false} interval={3} />
          <YAxis tick={{ fill: '#606060', fontSize: 8, fontFamily: 'monospace' }} tickLine={false} width={28} />
          <Tooltip
            contentStyle={{ background: '#141414', border: '1px solid #2a2a2a', fontFamily: 'monospace', fontSize: 11 }}
            labelStyle={{ color: '#a0a0a0' }}
          />
          <ReferenceLine y={1} stroke="#ffcc00" strokeDasharray="3 3" label={{ value: '1.0', fill: '#ffcc00', fontSize: 8 }} />
          <Line type="monotone" dataKey="pcr" stroke="#00d4ff" dot={false} strokeWidth={1.5} connectNulls />
        </LineChart>
      </ResponsiveContainer>
    </ChartPanel>
  );
};

// ─── Chart Panel Wrapper ──────────────────────────────────────────────────────

const ChartPanel: React.FC<{
  title: string;
  subtitle: string;
  children: React.ReactNode;
}> = ({ title, subtitle, children }) => (
  <div className="border-b border-border-primary p-3">
    <div className="flex items-center gap-2 mb-2">
      <span className="text-2xs font-mono font-bold text-accent-yellow tracking-widest">{title}</span>
      {subtitle && <span className="text-2xs font-mono text-text-muted">{subtitle}</span>}
    </div>
    {children}
  </div>
);
