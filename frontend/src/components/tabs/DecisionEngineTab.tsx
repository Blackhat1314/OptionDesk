import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  LineChart, Line, BarChart, Bar, Cell, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, ReferenceLine, AreaChart, Area,
  ComposedChart,
} from 'recharts';
import { useMarketStore } from '../../store/marketStore';
import { fmt } from '../../utils/format';

// ─── Types ───────────────────────────────────────────────────────────────────

interface RegimeData {
  regime: string;
  entropy: number;
  volatility?: number;
  volatility_20d?: number;
  volatility_50d?: number;
  trend_strength?: number;
  hurst?: number;
  signal: string;
  rolling_vol_20?: number[];
  rolling_entropy?: number[];
}

interface IVAnalysis {
  current_iv: number;
  rv_30d: number;
  iv_rv_spread: number;
  signal: string;
  signal_strength?: number;
  iv_rank: number;
  iv_percentile: number;
  vol_of_vol?: number;
  rationale?: string;
  iv_history?: { ts: number; iv: number }[];
}

interface VWAPData {
  vwap: number;
  upper_band_1std?: number;
  lower_band_1std?: number;
  upper_band_2std?: number;
  lower_band_2std?: number;
  signal: string;
  z_score?: number;
  bias?: { z_score: number; distance_pct: number };
  chart_series?: { ts: number; price: number; vwap: number; upper1: number; lower1: number }[];
}

interface GEXPoint { ts: number; gex: number; dex: number; spot: number; gamma_flip: number; }
interface GEXTimeSeries { timeseries: GEXPoint[]; stats: any; latest: any; gamma_flip_event: any; gex_spike: any; }

interface OIFlow {
  flows: { strike: number; option_type: string; flow: string; color: string; oi: number; oi_change: number }[];
  dominant_strikes: any[];
  flow_counts: Record<string, number>;
}

interface Alert { type: string; severity: string; symbol: string; message: string; timestamp: number; }

interface DecisionEngine {
  score: number;
  bias: string;
  regime: any; iv: any; gex: any; oi_flow: any; vwap: any;
  pcr: number; max_pain: number; alerts: Alert[];
}

// ─── Module-level cache (same pattern as IntelligenceTab — prevents flicker) ──

interface DEState {
  engine:  DecisionEngine | null;
  regime:  RegimeData | null;
  ivData:  IVAnalysis | null;
  gexTS:   GEXTimeSeries | null;
  oiFlow:  OIFlow | null;
  vwap:    VWAPData | null;
  alerts:  Alert[];
}

const _cache: Record<string, DEState> = {};

const EMPTY_STATE: DEState = {
  engine: null, regime: null, ivData: null,
  gexTS: null, oiFlow: null, vwap: null, alerts: [],
};

// ─── Fetch helpers ────────────────────────────────────────────────────────────

const BASE = '/api';
const fetchJSON = async (url: string) => {
  const token = (await import('../../utils/api')).tokenStore.get();
  const r = await fetch(BASE + url, {
    headers: token ? { 'Authorization': `Bearer ${token}` } : {},
  });
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.json();
};

// ─── Colours per regime ───────────────────────────────────────────────────────

const REGIME_COLOR: Record<string, string> = {
  TRENDING:    '#00c853',
  RANGE_BOUND: '#00d4ff',
  VOLATILE:    '#ffcc00',
  CHAOTIC:     '#ff1744',
};

const SEVERITY_COLOR: Record<string, string> = {
  CRITICAL: '#ff1744',
  WARNING:  '#ffcc00',
  INFO:     '#00d4ff',
};

const AXIS = { fill: '#606060', fontSize: 8, fontFamily: 'monospace' };
const TOOLTIP_STYLE = { background: '#141414', border: '1px solid #2a2a2a', fontFamily: 'monospace', fontSize: 11 };
const GRID = { strokeDasharray: '2 4', stroke: '#1e1e1e' };

// ─── Main Component ───────────────────────────────────────────────────────────

export const DecisionEngineTab: React.FC = () => {
  const { activeSymbol } = useMarketStore();

  // Single state object — one setState = one render (no flicker)
  const [state, setState] = useState<DEState>(() => _cache[activeSymbol] ?? EMPTY_STATE);
  const [loading, setLoading] = useState(!_cache[activeSymbol]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async (sym: string) => {
    try {
      // Fetch combined engine data + detailed time-series in parallel
      const [e, a, r, g, oi, v, iv] = await Promise.allSettled([
        fetchJSON(`/decision-engine?symbol=${sym}`),
        fetchJSON(`/alerts?symbol=${sym}&limit=20`),
        fetchJSON(`/regime?symbol=${sym}`),
        fetchJSON(`/gex-timeseries?symbol=${sym}`),
        fetchJSON(`/oi-flow?symbol=${sym}`),
        fetchJSON(`/vwap?symbol=${sym}`),
        fetchJSON(`/iv-analysis?symbol=${sym}`),
      ]);

      const eng    = e.status  === 'fulfilled' ? e.value  : null;
      const alerts = a.status  === 'fulfilled' ? (a.value.alerts || []) : [];
      const regime = r.status  === 'fulfilled' ? r.value  : (eng?.regime ?? null);
      const gexTS  = g.status  === 'fulfilled' ? g.value  : null;
      const oiFlow = oi.status === 'fulfilled' ? oi.value : null;
      const vwap   = v.status  === 'fulfilled' ? v.value  : null;
      const ivData = iv.status === 'fulfilled' ? iv.value : (eng?.iv ?? null);

      // Build GEX time-series from engine data if detailed endpoint failed
      const gexFinal = gexTS ?? (eng?.gex ? {
        timeseries: [], stats: { net_dealer_bias: eng.gex?.dealer_bias },
        latest: eng.gex, gamma_flip_event: eng.gex?.flip_event, gex_spike: null,
      } : null);

      const newState: DEState = {
        engine:  eng,
        regime:  regime,
        ivData:  ivData,
        gexTS:   gexFinal,
        oiFlow:  oiFlow ?? (eng?.oi_flow ? { flows: [], dominant_strikes: eng.oi_flow?.dominant || [], flow_counts: eng.oi_flow?.flow_counts || {} } : null),
        vwap:    vwap ?? (eng?.vwap ? { ...eng.vwap, chart_series: [], bias: { z_score: eng.vwap?.z_score || 0, distance_pct: 0 } } : null),
        alerts,
      };

      // Update module cache
      _cache[sym] = newState;

      // Only update state if this is still the active symbol
      setState(newState);
    } catch (err) {
      // keep existing state on error
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Serve from cache immediately (no loading flash on tab switch)
    if (_cache[activeSymbol]) {
      setState(_cache[activeSymbol]);
      setLoading(false);
    } else {
      setLoading(true);
    }

    load(activeSymbol);
    timerRef.current = setInterval(() => load(activeSymbol), 15000);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [activeSymbol, load]);

  const { engine, regime, ivData, gexTS, oiFlow, vwap, alerts } = state;

  if (loading && !engine) return (
    <div className="flex items-center justify-center h-full">
      <div className="text-accent-yellow font-mono text-sm animate-blink">■ LOADING DECISION ENGINE</div>
    </div>
  );

  const score     = engine?.score ?? 0;
  const scorePct  = Math.round((score + 1) * 50);
  const biasColor = score > 0.2 ? '#00c853' : score < -0.2 ? '#ff1744' : '#00d4ff';

  return (
    <div className="flex h-full overflow-auto bg-bg-primary p-3 gap-3 flex-col">

      {/* ── Row 1: Composite Score + Regime + IV Metrics ── */}
      <div className="grid grid-cols-5 gap-2 shrink-0">
        {/* Composite Score gauge */}
        <div className="col-span-1 border border-border-primary bg-bg-panel p-3 flex flex-col items-center justify-center">
          <div className="text-2xs font-mono text-text-muted tracking-widest mb-1">DECISION SCORE</div>
          <div className="text-3xl font-mono font-bold" style={{ color: biasColor }}>
            {score > 0 ? '+' : ''}{score.toFixed(2)}
          </div>
          <div className="text-xs font-mono font-bold mt-1" style={{ color: biasColor }}>
            {engine?.bias ?? 'NEUTRAL'}
          </div>
          {/* Score bar */}
          <div className="w-full mt-3 h-2 bg-bg-tertiary relative">
            <div className="absolute left-1/2 top-0 bottom-0 w-px bg-border-primary" />
            <div
              className="absolute top-0 bottom-0 transition-all duration-500"
              style={{
                backgroundColor: biasColor,
                left: score < 0 ? `${scorePct}%` : '50%',
                width: `${Math.abs(score) * 50}%`,
              }}
            />
          </div>
          <div className="flex justify-between w-full mt-0.5">
            <span className="text-2xs font-mono text-market-down">−1 BEAR</span>
            <span className="text-2xs font-mono text-market-up">+1 BULL</span>
          </div>
        </div>

        {/* Regime */}
        <RegimeMetric regime={regime} />

        {/* IV Analysis */}
        <IVMetricCard iv={ivData} />

        {/* GEX Summary */}
        <GEXMetricCard gex={gexTS} />

        {/* VWAP Summary */}
        <VWAPMetricCard vwap={vwap} />
      </div>

      {/* ── Row 2: Regime Chart + GEX Time-Series ── */}
      <div className="grid grid-cols-2 gap-3 shrink-0">
        <Panel title="MARKET REGIME — Entropy vs Volatility">
          <RegimeChart regime={regime} />
        </Panel>
        <Panel title="GEX / DEX TIME-SERIES">
          <GEXTimeSeriesChart gex={gexTS} />
        </Panel>
      </div>

      {/* ── Row 3: OI Flow Heatmap + VWAP Chart ── */}
      <div className="grid grid-cols-2 gap-3 shrink-0">
        <Panel title="OI FLOW INTELLIGENCE">
          <OIFlowChart oi={oiFlow} />
        </Panel>
        <Panel title="VWAP + BANDS">
          <VWAPChart vwap={vwap} />
        </Panel>
      </div>

      {/* ── Row 4: IV History + Alerts ── */}
      <div className="grid grid-cols-2 gap-3 shrink-0">
        <Panel title="IV HISTORY & REALIZED VOL SPREAD">
          <IVHistoryChart iv={ivData} />
        </Panel>
        <Panel title="ALERT FEED">
          <AlertFeed alerts={alerts} />
        </Panel>
      </div>

    </div>
  );
};

// ─── Regime Metric Card ───────────────────────────────────────────────────────

const RegimeMetric = React.memo<{ regime: RegimeData | null }>(({ regime }) => {
  if (!regime) return <BlankCard label="REGIME" />;
  const color = REGIME_COLOR[regime.regime] ?? '#78909c';
  return (
    <div className="border bg-bg-panel p-3" style={{ borderColor: color + '50' }}>
      <div className="text-2xs font-mono text-text-muted tracking-widest mb-1">REGIME</div>
      <div className="text-lg font-mono font-bold mb-2" style={{ color }}>{regime.regime}</div>
      <Row k="Entropy"    v={`${((regime.entropy ?? 0) * 100).toFixed(1)}%`} />
      <Row k="Vol 20d"    v={`${(regime.volatility_20d ?? regime.volatility ?? 0).toFixed(1)}%`} />
      <Row k="Hurst"      v={(regime.hurst ?? 0).toFixed(3)} vc={(regime.hurst ?? 0) > 0.5 ? '#00c853' : '#ff9900'} />
      <Row k="Signal"     v={(regime.signal ?? '—').replace(/_/g, ' ')} vc={color} />
    </div>
  );
});

// ─── IV Metric Card ───────────────────────────────────────────────────────────

const IVMetricCard = React.memo<{ iv: IVAnalysis | null }>(({ iv }) => {
  if (!iv) return <BlankCard label="IV ANALYSIS" />;
  const sc = iv.signal === 'SELL_OPTIONS' ? '#ff1744' : iv.signal === 'BUY_OPTIONS' ? '#00c853' : '#00d4ff';
  const rv = iv.rv_30d ?? 0;
  const spread = iv.iv_rv_spread ?? 0;
  return (
    <div className="border border-border-primary bg-bg-panel p-3">
      <div className="text-2xs font-mono text-text-muted tracking-widest mb-1">IV ANALYSIS</div>
      <div className="text-lg font-mono font-bold mb-2" style={{ color: sc }}>{(iv.signal ?? '—').replace(/_/g, ' ')}</div>
      <Row k="ATM IV"    v={`${(iv.current_iv ?? 0).toFixed(1)}%`} />
      <Row k="HV 30d"    v={`${rv.toFixed(1)}%`} />
      <Row k="Spread"    v={`${spread >= 0 ? '+' : ''}${spread.toFixed(1)}%`} vc={spread > 0 ? '#ff9900' : '#00c853'} />
      <Row k="IV Rank"   v={`${(iv.iv_rank ?? 0).toFixed(0)}/100`} vc={(iv.iv_rank ?? 0) > 70 ? '#ffcc00' : '#a0a0a0'} />
    </div>
  );
});

// ─── GEX Metric Card ──────────────────────────────────────────────────────────

const GEXMetricCard = React.memo<{ gex: GEXTimeSeries | null }>(({ gex }) => {
  const latest = gex?.latest;
  if (!latest) return <BlankCard label="GEX" />;
  const gexVal = latest.gex ?? latest.total_gex ?? 0;
  const gexColor = gexVal >= 0 ? '#00c853' : '#ff1744';
  const bias = gex?.stats?.net_dealer_bias ?? latest.dealer_bias ?? 'N/A';
  return (
    <div className="border border-border-primary bg-bg-panel p-3">
      <div className="text-2xs font-mono text-text-muted tracking-widest mb-1">GEX / DEALER</div>
      <div className="text-lg font-mono font-bold mb-2" style={{ color: gexColor }}>
        {gexVal >= 0 ? '+' : ''}{gexVal.toFixed(3)}B
      </div>
      <Row k="Dealer"    v={String(bias)} vc={bias === 'LONG' ? '#00c853' : '#ff1744'} />
      <Row k="Flip Lvl"  v={fmt.strike(latest.gamma_flip ?? 0)} vc="#ffcc00" />
      <Row k="Call Wall" v={fmt.strike(latest.call_wall ?? 0)} vc="#00c853" />
      <Row k="Put Wall"  v={fmt.strike(latest.put_wall ?? 0)} vc="#ff1744" />
    </div>
  );
});

// ─── VWAP Metric Card ─────────────────────────────────────────────────────────

const VWAPMetricCard = React.memo<{ vwap: VWAPData | null }>(({ vwap }) => {
  if (!vwap) return <BlankCard label="VWAP" />;
  const sc = vwap.signal === 'BULLISH' ? '#00c853' : vwap.signal === 'BEARISH' ? '#ff1744' : '#00d4ff';
  return (
    <div className="border border-border-primary bg-bg-panel p-3">
      <div className="text-2xs font-mono text-text-muted tracking-widest mb-1">VWAP</div>
      <div className="text-lg font-mono font-bold mb-2" style={{ color: sc }}>{vwap.signal ?? '—'}</div>
      <Row k="VWAP"    v={fmt.price(vwap.vwap ?? 0)} />
      <Row k="+1σ"     v={fmt.price(vwap.upper_band_1std ?? 0)} vc="#606060" />
      <Row k="−1σ"     v={fmt.price(vwap.lower_band_1std ?? 0)} vc="#606060" />
      <Row k="Z-score" v={(vwap.bias?.z_score ?? vwap.z_score ?? 0).toFixed(2)} vc={sc} />
    </div>
  );
});

// ─── Regime Chart ─────────────────────────────────────────────────────────────

const RegimeChart = React.memo<{ regime: RegimeData | null }>(({ regime }) => {
  if (!regime?.rolling_vol_20?.length || !regime?.rolling_entropy?.length) return <Empty />;
  const n = Math.min(regime.rolling_vol_20.length, regime.rolling_entropy.length);
  const data = Array.from({ length: n }, (_, i) => ({
    i,
    vol:     (regime.rolling_vol_20 as number[])[i],
    entropy: (regime.rolling_entropy as number[])[i] * 30,
  }));

  return (
    <ResponsiveContainer width="100%" height={160}>
      <LineChart data={data} margin={{ top: 4, right: 4, bottom: 4, left: 0 }}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="i" tick={false} />
        <YAxis tick={AXIS} tickLine={false} width={28} />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          formatter={(v: number, name: string) =>
            name === 'entropy' ? [`${(v / 30 * 100).toFixed(1)}%`, 'Entropy'] : [`${v.toFixed(2)}%`, 'Vol 20d']
          }
        />
        <ReferenceLine y={20} stroke="#ffcc00" strokeDasharray="3 3" strokeWidth={0.5} />
        <Line type="monotone" dataKey="vol"     stroke="#ffcc00" dot={false} strokeWidth={2} />
        <Line type="monotone" dataKey="entropy" stroke="#9b59b6" dot={false} strokeWidth={1.5} strokeDasharray="4 2" />
      </LineChart>
    </ResponsiveContainer>
  );
});

// ─── GEX Time-Series Chart ────────────────────────────────────────────────────

const GEXTimeSeriesChart = React.memo<{ gex: GEXTimeSeries | null }>(({ gex }) => {
  if (!gex?.timeseries?.length) return <Empty />;
  const data = gex.timeseries.slice(-60);

  return (
    <ResponsiveContainer width="100%" height={160}>
      <ComposedChart data={data} margin={{ top: 4, right: 4, bottom: 4, left: 0 }}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="ts" tick={false} />
        <YAxis tick={AXIS} tickLine={false} width={36} />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          formatter={(v: number, name: string) => [
            name === 'gex' ? `${v.toFixed(3)}B` : v.toFixed(3), name.toUpperCase()
          ]}
        />
        <ReferenceLine y={0} stroke="#606060" strokeWidth={1} />
        {gex.latest?.gamma_flip > 0 && (
          <ReferenceLine
            x={gex.timeseries.findIndex(d => d.spot >= gex.latest.gamma_flip)}
            stroke="#ffcc00" strokeDasharray="3 3"
            label={{ value: 'FLIP', fill: '#ffcc00', fontSize: 8 }}
          />
        )}
        <Bar dataKey="gex" maxBarSize={8}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.gex >= 0 ? '#00c853' : '#ff1744'} fillOpacity={0.8} />
          ))}
        </Bar>
        <Line type="monotone" dataKey="dex" stroke="#00d4ff" dot={false} strokeWidth={1} />
      </ComposedChart>
    </ResponsiveContainer>
  );
});

// ─── OI Flow Chart ────────────────────────────────────────────────────────────

const OIFlowChart = React.memo<{ oi: OIFlow | null }>(({ oi }) => {
  if (!oi?.flows?.length) return <Empty />;

  // Aggregate CE+PE OI change per strike
  const strikeMap: Record<number, { strike: number; call: number; put: number; callFlow: string; putFlow: string }> = {};
  for (const f of oi.flows) {
    if (!strikeMap[f.strike]) strikeMap[f.strike] = { strike: f.strike, call: 0, put: 0, callFlow: 'NEUTRAL', putFlow: 'NEUTRAL' };
    if (f.option_type === 'CE') { strikeMap[f.strike].call = f.oi_change; strikeMap[f.strike].callFlow = f.flow; }
    else                        { strikeMap[f.strike].put  = f.oi_change; strikeMap[f.strike].putFlow  = f.flow; }
  }
  const data = Object.values(strikeMap).sort((a, b) => a.strike - b.strike);

  const FLOW_FILL: Record<string, string> = {
    LONG_BUILDUP: '#00c853', SHORT_BUILDUP: '#ff1744',
    SHORT_COVERING: '#00d4ff', LONG_UNWINDING: '#ff9100', NEUTRAL: '#607d8b',
  };

  return (
    <ResponsiveContainer width="100%" height={160}>
      <BarChart data={data} margin={{ top: 4, right: 4, bottom: 16, left: 0 }}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="strike" tick={AXIS} tickLine={false} interval={3} />
        <YAxis tick={AXIS} tickLine={false} width={40} />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          formatter={(v: number, name: string) => [fmt.compact(v), name === 'call' ? 'CE ΔOI' : 'PE ΔOI']}
        />
        <ReferenceLine y={0} stroke="#606060" />
        <Bar dataKey="call" maxBarSize={10}>
          {data.map((d, i) => <Cell key={i} fill={FLOW_FILL[d.callFlow]} fillOpacity={0.8} />)}
        </Bar>
        <Bar dataKey="put" maxBarSize={10}>
          {data.map((d, i) => <Cell key={i} fill={FLOW_FILL[d.putFlow]} fillOpacity={0.5} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
});

// ─── VWAP Chart ───────────────────────────────────────────────────────────────

const VWAPChart = React.memo<{ vwap: VWAPData | null }>(({ vwap }) => {
  if (!vwap?.chart_series?.length) return <Empty />;
  const data = vwap.chart_series.slice(-80);

  return (
    <ResponsiveContainer width="100%" height={160}>
      <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 4, left: 0 }}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="ts" tick={false} />
        <YAxis tick={AXIS} tickLine={false} width={48} domain={['auto', 'auto']} />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          formatter={(v: number, name: string) => [fmt.price(v), name.toUpperCase()]}
        />
        <Area type="monotone" dataKey="upper1" stroke="transparent" fill="#00c853" fillOpacity={0.06} />
        <Area type="monotone" dataKey="lower1" stroke="transparent" fill="#ff1744" fillOpacity={0.06} />
        <Line type="monotone" dataKey="vwap"   stroke="#ffcc00" dot={false} strokeWidth={2} />
        <Line type="monotone" dataKey="upper1" stroke="#00c853" dot={false} strokeWidth={1} strokeDasharray="4 2" />
        <Line type="monotone" dataKey="lower1" stroke="#ff1744" dot={false} strokeWidth={1} strokeDasharray="4 2" />
        <Line type="monotone" dataKey="price"  stroke="#f5f5f5" dot={false} strokeWidth={1.5} />
      </AreaChart>
    </ResponsiveContainer>
  );
});

// ─── IV History Chart ─────────────────────────────────────────────────────────

const IVHistoryChart = React.memo<{ iv: IVAnalysis | null }>(({ iv }) => {
  if (!iv?.iv_history?.length) return <Empty />;
  const data = iv.iv_history.slice(-60).map(d => ({ ...d, rv: iv.rv_30d }));

  return (
    <ResponsiveContainer width="100%" height={160}>
      <LineChart data={data} margin={{ top: 4, right: 4, bottom: 4, left: 0 }}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="ts" tick={false} />
        <YAxis tick={AXIS} tickLine={false} width={28} unit="%" />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          formatter={(v: number) => [`${v.toFixed(2)}%`, '']}
        />
        <ReferenceLine
          y={iv.rv_30d}
          stroke="#9b59b6"
          strokeDasharray="3 3"
          label={{ value: `HV ${iv.rv_30d.toFixed(1)}%`, fill: '#9b59b6', fontSize: 8 }}
        />
        <Line type="monotone" dataKey="iv" stroke="#00d4ff" dot={false} strokeWidth={2} />
        <Line type="monotone" dataKey="rv" stroke="#9b59b6" dot={false} strokeWidth={1} strokeDasharray="3 3" />
      </LineChart>
    </ResponsiveContainer>
  );
});

// ─── Alert Feed ───────────────────────────────────────────────────────────────

const AlertFeed = React.memo<{ alerts: Alert[] }>(({ alerts }) => {
  if (!alerts.length) return (
    <div className="flex items-center justify-center h-28 text-text-muted font-mono text-xs">
      No alerts triggered
    </div>
  );

  return (
    <div className="overflow-y-auto max-h-44 space-y-1">
      {alerts.map((a, i) => {
        const color = SEVERITY_COLOR[a.severity] ?? '#607d8b';
        return (
          <div key={i} className="flex gap-2 items-start py-1 border-b border-border-secondary/50">
            <div className="w-1.5 h-1.5 rounded-full mt-1 shrink-0" style={{ backgroundColor: color }} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-2xs font-mono font-bold" style={{ color }}>{a.type}</span>
                <span className="text-2xs font-mono text-text-muted">{a.symbol}</span>
              </div>
              <div className="text-2xs font-mono text-text-secondary truncate">{a.message}</div>
            </div>
            <span className="text-2xs font-mono text-text-muted shrink-0">
              {new Date(a.timestamp * 1000).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false })}
            </span>
          </div>
        );
      })}
    </div>
  );
});

// ─── Shared primitives ────────────────────────────────────────────────────────

const Panel: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div className="border border-border-primary bg-bg-panel p-3">
    <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest mb-2">{title}</div>
    {children}
  </div>
);

const Row: React.FC<{ k: string; v: string; vc?: string }> = ({ k, v, vc }) => (
  <div className="flex justify-between text-2xs font-mono py-0.5">
    <span className="text-text-muted">{k}</span>
    <span style={vc ? { color: vc } : undefined} className={vc ? '' : 'text-text-secondary'}>{v}</span>
  </div>
);

const BlankCard: React.FC<{ label: string }> = ({ label }) => (
  <div className="border border-border-primary bg-bg-panel p-3 flex items-center justify-center">
    <span className="text-2xs font-mono text-text-muted animate-blink">{label} loading…</span>
  </div>
);

const Empty: React.FC = () => (
  <div className="flex items-center justify-center h-28 text-text-muted font-mono text-xs">
    Awaiting data…
  </div>
);
