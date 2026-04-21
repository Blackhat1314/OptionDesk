import React from 'react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceLine, CartesianGrid, ScatterChart, Scatter,
} from 'recharts';
import { useMarketStore } from '../../store/marketStore';
import { fmt } from '../../utils/format';

// ─── IV Analytics Tab ─────────────────────────────────────────────────────────

export const IVAnalyticsTab: React.FC = () => {
  const { ivAnalytics } = useMarketStore();

  // Show tab structure immediately — data populates via WebSocket/background worker
  const spot = ivAnalytics?.spot_price ?? 0;
  const hasData = ivAnalytics && ivAnalytics.current_iv > 0;
  const iv = ivAnalytics;

  return (
    <div className="flex h-full overflow-auto bg-bg-primary p-3 gap-3">
      {/* Left column */}
      <div className="flex flex-col gap-3 flex-1">
        {/* ── IV SIGNAL SUMMARY ─────────────────────────────────────────────── */}
        {hasData && <IVSummarySignal iv={iv!} />}

        {/* Metrics Row */}
        <div className="grid grid-cols-4 gap-2">
          <IVMetric label="CURRENT IV"    value={hasData ? `${iv!.current_iv.toFixed(2)}%` : '—'} sub="ATM Implied Vol" />
          <IVMetric label="IV RANK"       value={hasData ? `${iv!.iv_rank.toFixed(1)}` : '—'} sub="0–100 scale" highlight={(iv?.iv_rank ?? 0) > 70} />
          <IVMetric label="IV PERCENTILE" value={hasData ? `${iv!.iv_percentile.toFixed(1)}%` : '—'} sub="Historical percentile" />
          <IVMetric label="HV 30D"        value={hasData ? `${iv!.historical_vol_30d.toFixed(2)}%` : '—'} sub="Realized Vol" />
        </div>

        <div className="grid grid-cols-3 gap-2">
          <IVMetric label="HV 7D"      value={hasData ? `${(iv!.historical_vol_7d ?? 0).toFixed(2)}%` : '—'} sub="1-week realized" />
          <IVMetric
            label="IV–RV SPREAD"
            value={hasData ? `${(iv!.iv_rv_spread ?? 0) >= 0 ? '+' : ''}${(iv!.iv_rv_spread ?? 0).toFixed(2)}%` : '—'}
            sub="Implied - Realized"
            highlight={Math.abs(iv?.iv_rv_spread ?? 0) > 5}
          />
          <IVMetric label="AVG IV" value={hasData ? `${iv!.avg_iv.toFixed(2)}%` : '—'} sub="All strikes avg" />
        </div>

        {/* IV Smile */}
        <div className="border border-border-primary bg-bg-panel p-3 flex-1">
          <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest mb-2">
            IV SMILE CURVE
          </div>
          {!hasData ? (
            <div className="flex items-center justify-center h-48 text-text-muted font-mono text-xs animate-pulse">Fetching data…</div>
          ) : (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart
              data={iv!.smile}
              margin={{ top: 4, right: 8, bottom: 20, left: 0 }}
            >
              <CartesianGrid strokeDasharray="2 4" stroke="#1e1e1e" />
              <XAxis
                dataKey="strike"
                tick={{ fill: '#606060', fontSize: 8, fontFamily: 'monospace' }}
                tickLine={false}
                interval={3}
              />
              <YAxis
                tick={{ fill: '#606060', fontSize: 8, fontFamily: 'monospace' }}
                tickLine={false}
                width={32}
                unit="%"
              />
              <Tooltip
                contentStyle={{ background: '#141414', border: '1px solid #2a2a2a', fontFamily: 'monospace', fontSize: 11 }}
                formatter={(v: number, name: string) => [`${v.toFixed(2)}%`, name === 'call_iv' ? 'CE IV' : 'PE IV']}
              />
              <ReferenceLine x={spot} stroke="#ffcc00" strokeDasharray="3 3" label={{ value: 'ATM', fill: '#ffcc00', fontSize: 8 }} />
              <Line type="monotone" dataKey="call_iv" stroke="#00c853" dot={false} strokeWidth={2} connectNulls />
              <Line type="monotone" dataKey="put_iv" stroke="#ff1744" dot={false} strokeWidth={2} connectNulls />
            </LineChart>
          </ResponsiveContainer>
          )}
        </div>

        {/* IV vs Moneyness Scatter */}
        <div className="border border-border-primary bg-bg-panel p-3">
          <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest mb-2">
            IV vs MONEYNESS
          </div>
          <ResponsiveContainer width="100%" height={150}>
            <ScatterChart margin={{ top: 4, right: 8, bottom: 16, left: 0 }}>
              <CartesianGrid strokeDasharray="2 4" stroke="#1e1e1e" />
              <XAxis
                dataKey="moneyness"
                type="number"
                domain={[0.9, 1.1]}
                tick={{ fill: '#606060', fontSize: 8, fontFamily: 'monospace' }}
                tickLine={false}
              />
              <YAxis
                dataKey="call_iv"
                tick={{ fill: '#606060', fontSize: 8, fontFamily: 'monospace' }}
                tickLine={false}
                width={28}
              />
              <Tooltip
                contentStyle={{ background: '#141414', border: '1px solid #2a2a2a', fontFamily: 'monospace', fontSize: 11 }}
              />
              <ReferenceLine x={1} stroke="#ffcc00" strokeDasharray="3 3" />
              <Scatter data={iv?.smile ?? []} fill="#00d4ff" opacity={0.6} />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Right column: Term Structure */}
      <div className="w-80 flex flex-col gap-3">
        <div className="border border-border-primary bg-bg-panel p-3 flex-1">
          <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest mb-2">
            IV TERM STRUCTURE
          </div>
          {(iv?.term_structure?.length ?? 0) > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <LineChart
                data={iv!.term_structure}
                margin={{ top: 4, right: 4, bottom: 16, left: 0 }}
              >
                <CartesianGrid strokeDasharray="2 4" stroke="#1e1e1e" />
                <XAxis dataKey="dte" tick={{ fill: '#606060', fontSize: 8, fontFamily: 'monospace' }} tickLine={false} />
                <YAxis tick={{ fill: '#606060', fontSize: 8, fontFamily: 'monospace' }} tickLine={false} width={28} />
                <Tooltip
                  contentStyle={{ background: '#141414', border: '1px solid #2a2a2a', fontFamily: 'monospace', fontSize: 11 }}
                  formatter={(v: number) => [`${v.toFixed(2)}%`, 'ATM IV']}
                />
                <Line type="monotone" dataKey="atm_iv" stroke="#00d4ff" dot={{ r: 3, fill: '#00d4ff' }} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-text-muted font-mono text-xs py-8 text-center">
              Requires multiple expiries
            </div>
          )}
        </div>

        {/* IV Strike Table */}
        <div className="border border-border-primary bg-bg-panel p-3 flex-1 overflow-y-auto">
          <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest mb-2">IV BY STRIKE</div>
          <div className="grid grid-cols-3 text-2xs font-mono text-text-muted border-b border-border-primary pb-1 mb-1">
            <span>STRIKE</span><span className="text-right text-chart-call">CE IV</span><span className="text-right text-chart-put">PE IV</span>
          </div>
          {(iv?.smile?.length ?? 0) > 0 ? (iv!.smile.map((point) => (
            <div key={point.strike} className="grid grid-cols-3 text-2xs font-mono py-0.5 hover:bg-bg-hover">
              <span className="text-text-secondary">{fmt.strike(point.strike)}</span>
              <span className="text-right text-chart-call">{point.call_iv > 0 ? `${point.call_iv.toFixed(1)}%` : '—'}</span>
              <span className="text-right text-chart-put">{point.put_iv > 0 ? `${point.put_iv.toFixed(1)}%` : '—'}</span>
            </div>
          ))) : null}
        </div>
      </div>
    </div>
  );
};

// ─── IV Summary Signal ────────────────────────────────────────────────────────

const IVSummarySignal: React.FC<{ iv: any }> = ({ iv }) => {
  const ivRank    = iv.iv_rank       ?? 0;
  const ivPct     = iv.iv_percentile ?? 0;
  const ivRvSpread = iv.iv_rv_spread ?? 0;
  const currentIV = iv.current_iv    ?? 0;
  const hv30      = iv.historical_vol_30d ?? 0;

  // ── Quant-level IV signal conditions ─────────────────────────────────────
  const ivHigh    = ivRank > 70;    // IV rank > 70 = expensive options
  const ivLow     = ivRank < 30;    // IV rank < 30 = cheap options
  const ivExtreme = ivRank > 85;    // IV rank > 85 = very expensive
  const ivCrush   = ivRank > 70 && ivRvSpread > 5;   // IV >> RV = sell premium
  const ivExpand  = ivRank < 30 && ivRvSpread < -3;  // IV << RV = buy options
  const ivNeutral = ivRank >= 30 && ivRank <= 70;

  let signal: string;
  let signalColor: string;
  let signalBg: string;
  let suggestion: string;
  let risk: string;
  let details: string[];

  if (ivExtreme) {
    signal      = '🔥 IV EXTREME — SELL PREMIUM';
    signalColor = '#ff1744';
    signalBg    = 'rgba(255,23,68,0.08)';
    suggestion  = 'Options are VERY expensive. SELL straddles/strangles or Iron Condors. IV crush likely after event.';
    risk        = 'HIGH — If market makes a large move, losses can exceed premium collected.';
    details     = [`IV Rank: ${ivRank.toFixed(0)} (top ${(100-ivRank).toFixed(0)}% of history)`, `IV ${ivRvSpread.toFixed(1)}% above realized vol`, 'Premium sellers have statistical edge'];
  } else if (ivCrush) {
    signal      = '📉 IV ELEVATED — SELL BIAS';
    signalColor = '#ff9100';
    signalBg    = 'rgba(255,145,0,0.08)';
    suggestion  = 'IV is elevated vs realized vol. Favor SELLING options (covered calls, cash-secured puts, spreads).';
    risk        = 'MEDIUM — IV can stay elevated or spike further before crushing.';
    details     = [`IV Rank: ${ivRank.toFixed(0)}`, `IV-RV Spread: +${ivRvSpread.toFixed(1)}%`, 'Options overpriced vs actual movement'];
  } else if (ivExpand) {
    signal      = '📈 IV CHEAP — BUY BIAS';
    signalColor = '#00c853';
    signalBg    = 'rgba(0,200,83,0.08)';
    suggestion  = 'IV is cheap vs realized vol. Favor BUYING options (long straddles, directional plays). Good risk/reward.';
    risk        = 'LOW-MEDIUM — Options are cheap but need a big move to profit.';
    details     = [`IV Rank: ${ivRank.toFixed(0)} (historically cheap)`, `IV ${Math.abs(ivRvSpread).toFixed(1)}% below realized vol`, 'Options underpriced vs actual movement'];
  } else if (ivLow) {
    signal      = '💤 IV LOW — LONG GAMMA';
    signalColor = '#00c853';
    signalBg    = 'rgba(0,200,83,0.08)';
    suggestion  = 'Low IV = cheap options. Buy straddles before expected events. Long gamma benefits from large moves.';
    risk        = 'LOW — Cheap entry but needs catalyst for profit.';
    details     = [`IV Rank: ${ivRank.toFixed(0)} (cheap)`, `Current IV: ${currentIV.toFixed(1)}%`, 'Good time to buy protection'];
  } else {
    signal      = '↔ IV NEUTRAL — NO EDGE';
    signalColor = '#607d8b';
    signalBg    = 'rgba(96,125,139,0.08)';
    suggestion  = 'IV is in normal range. No strong edge for buyers or sellers. Use directional strategies.';
    risk        = 'MEDIUM — Neither buyers nor sellers have a clear statistical edge.';
    details     = [`IV Rank: ${ivRank.toFixed(0)} (neutral zone)`, `IV-RV Spread: ${ivRvSpread >= 0 ? '+' : ''}${ivRvSpread.toFixed(1)}%`, 'Wait for IV to reach extremes'];
  }

  return (
    <div className="border rounded-sm p-3" style={{ borderColor: signalColor + '40', backgroundColor: signalBg }}>
      <div className="flex items-center justify-between mb-2">
        <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest">⚡ IV SIGNAL</div>
        <div className="text-2xs font-mono text-text-muted">
          IV Rank {ivRank.toFixed(0)} · Percentile {ivPct.toFixed(0)}%
        </div>
      </div>
      <div className="flex items-start gap-4">
        <div className="shrink-0">
          <div className="text-sm font-mono font-bold" style={{ color: signalColor }}>{signal}</div>
          <div className="text-2xs font-mono text-text-muted mt-1">RISK: <span style={{ color: signalColor }}>{risk.split('—')[0].trim()}</span></div>
        </div>
        <div className="w-px h-10 bg-border-primary shrink-0" />
        <div className="flex-1">
          <div className="text-2xs font-mono text-text-secondary">{suggestion}</div>
        </div>
        <div className="w-px h-10 bg-border-primary shrink-0" />
        <div className="shrink-0 space-y-0.5">
          {details.map((d, i) => (
            <div key={i} className="flex items-center gap-1 text-2xs font-mono text-text-muted">
              <span style={{ color: signalColor }}>✓</span> {d}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

const IVMetric: React.FC<{
  label: string;
  value: string;
  sub: string;
  highlight?: boolean;
}> = ({ label, value, sub, highlight }) => (
  <div className={`p-3 border ${highlight ? 'border-accent-yellow/40 bg-accent-yellow/5' : 'border-border-primary bg-bg-panel'}`}>
    <div className="text-2xs font-mono text-text-muted tracking-widest mb-1">{label}</div>
    <div className={`text-xl font-mono font-bold ${highlight ? 'text-accent-yellow' : 'text-text-primary'}`}>
      {value}
    </div>
    <div className="text-2xs font-mono text-text-muted mt-1">{sub}</div>
  </div>
);
