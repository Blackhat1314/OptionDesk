import React from 'react';
import {
  BarChart, Bar, Cell, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceLine, CartesianGrid, ComposedChart, Area,
} from 'recharts';
import { useMarketStore } from '../../store/marketStore';
import { fmt } from '../../utils/format';

export const GreeksTab: React.FC = () => {
  const { exposure } = useMarketStore();

  // Show tab structure immediately — data populates via WebSocket/background worker
  const spot = exposure?.spot_price ?? 0;
  const hasData = exposure && exposure.exposures && exposure.exposures.length > 0;

  // Safe defaults when data not yet available
  const gex   = exposure?.total_gex   ?? 0;
  const dex   = exposure?.total_dex   ?? 0;
  const vega  = exposure?.total_vega  ?? 0;
  const theta = exposure?.total_theta ?? 0;
  const flip  = exposure?.gamma_flip_level ?? 0;
  const cwall = exposure?.call_wall ?? 0;
  const pwall = exposure?.put_wall  ?? 0;
  const exps  = exposure?.exposures ?? [];

  return (
    <div className="flex h-full overflow-auto bg-bg-primary p-3 gap-3">
      {/* Left Column */}
      <div className="flex flex-col gap-3 flex-1 min-w-0">
        {/* ── QUANT SIGNAL SUMMARY ─────────────────────────────────────────── */}
        {hasData && <GreeksSummarySignal gex={gex} dex={dex} vega={vega} theta={theta} flip={flip} cwall={cwall} pwall={pwall} spot={spot} />}

        {/* Summary Metrics */}
        <div className="grid grid-cols-4 gap-2">
          <ExposureMetric
            label="TOTAL GEX"
            value={hasData ? `${gex >= 0 ? '+' : ''}${gex.toFixed(3)}Cr` : '—'}
            subLabel="Gamma Exposure"
            positive={gex >= 0}
            description={gex >= 0 ? 'Dealers LONG Gamma → Stabilizing' : 'Dealers SHORT Gamma → Destabilizing'}
          />
          <ExposureMetric
            label="TOTAL DEX"
            value={hasData ? `${dex >= 0 ? '+' : ''}${dex.toFixed(2)}Cr` : '—'}
            subLabel="Delta Exposure"
            positive={dex >= 0}
          />
          <ExposureMetric
            label="TOTAL VEGA"
            value={hasData ? `${vega >= 0 ? '+' : ''}${vega.toFixed(2)}Cr` : '—'}
            subLabel="Vega Exposure (₹/1% IV)"
            positive={vega >= 0}
          />
          <ExposureMetric
            label="TOTAL THETA"
            value={hasData ? `${theta.toFixed(2)}Cr` : '—'}
            subLabel="Daily Decay (₹/day)"
            positive={theta >= 0}
          />
        </div>

        {/* Dealer Positioning */}
        <div className="grid grid-cols-3 gap-2">
          <KeyLevel label="GAMMA FLIP" value={hasData ? fmt.strike(flip) : '—'} description="GEX zero crossing" color="text-accent-yellow" spotDiff={flip - spot} />
          <KeyLevel label="CALL WALL"  value={hasData ? fmt.strike(cwall) : '—'} description="Max Call OI strike" color="text-chart-call" spotDiff={cwall - spot} />
          <KeyLevel label="PUT WALL"   value={hasData ? fmt.strike(pwall) : '—'} description="Max Put OI strike" color="text-chart-put" spotDiff={pwall - spot} />
        </div>

        {/* GEX by Strike Chart */}
        <ChartPanel title="GAMMA EXPOSURE BY STRIKE" className="flex-1">
          {hasData ? <GEXChart data={exps} spot={spot} flipLevel={flip} /> : <Awaiting />}
        </ChartPanel>

        {/* DEX Chart */}
        <ChartPanel title="DELTA EXPOSURE BY STRIKE" className="flex-1">
          {hasData ? <DEXChart data={exps} spot={spot} /> : <Awaiting />}
        </ChartPanel>
      </div>

      {/* Right Column */}
      <div className="flex flex-col gap-3 w-80">
        <ChartPanel title="VEGA EXPOSURE">
          {hasData ? <VegaChart data={exps} spot={spot} /> : <Awaiting />}
        </ChartPanel>
        <ChartPanel title="THETA DECAY">
          {hasData ? <ThetaChart data={exps} spot={spot} /> : <Awaiting />}
        </ChartPanel>
        <ChartPanel title="TOP 10 STRIKES BY GEX" className="flex-1">
          {hasData ? <GEXTable data={exps} spot={spot} /> : <Awaiting />}
        </ChartPanel>
      </div>
    </div>
  );
};

const Awaiting: React.FC = () => (
  <div className="flex items-center justify-center h-24 text-text-muted font-mono text-xs animate-pulse">
    Fetching data…
  </div>
);

// ─── Greeks Summary Signal ────────────────────────────────────────────────────

const GreeksSummarySignal: React.FC<{
  gex: number; dex: number; vega: number; theta: number;
  flip: number; cwall: number; pwall: number; spot: number;
}> = ({ gex, dex, vega, theta, flip, cwall, pwall, spot }) => {
  // ── Quant-level signal logic ──────────────────────────────────────────────
  // Based on GEX, DEX, and key levels — production-grade conditions

  // 1. GEX regime: positive = dealers long gamma (stabilizing), negative = short gamma (amplifying)
  const gexPositive   = gex > 0;
  const gexStrong     = Math.abs(gex) > 500;   // >500Cr = strong positioning

  // 2. DEX: positive = net bullish delta, negative = net bearish
  const dexBullish    = dex > 0;

  // 3. Spot vs key levels
  const aboveFlip     = spot > flip && flip > 0;
  const nearCallWall  = cwall > 0 && (cwall - spot) < 100;   // within 100pts of call wall
  const nearPutWall   = pwall > 0 && (spot - pwall) < 100;   // within 100pts of put wall
  const betweenWalls  = pwall > 0 && cwall > 0 && spot > pwall && spot < cwall;

  // 4. Theta: large negative = heavy premium decay (good for sellers)
  const heavyDecay    = theta < -200;   // >200Cr/day decay

  // 5. Vega: large positive = market sensitive to IV changes
  const highVega      = Math.abs(vega) > 300;

  // ── Signal determination ──────────────────────────────────────────────────
  let signal: string;
  let signalColor: string;
  let signalBg: string;
  let conditions: string[] = [];
  let suggestion: string;
  let risk: string;

  if (gexPositive && aboveFlip && dexBullish && betweenWalls) {
    signal      = '↑ BULLISH — RANGE BOUND';
    signalColor = '#00c853';
    signalBg    = 'rgba(0,200,83,0.08)';
    suggestion  = 'SELL OTM PUTS or BULL SPREAD. Dealers will buy dips (long gamma stabilizes).';
    risk        = 'LOW — Gamma positive environment suppresses large moves.';
    conditions  = ['GEX positive (dealers long gamma)', 'Spot above gamma flip', 'DEX bullish', 'Price between walls'];
  } else if (!gexPositive && !aboveFlip && !dexBullish) {
    signal      = '↓ BEARISH — VOLATILE';
    signalColor = '#ff1744';
    signalBg    = 'rgba(255,23,68,0.08)';
    suggestion  = 'AVOID selling options. Buy PUT spreads or reduce position size.';
    risk        = 'HIGH — Negative GEX amplifies moves. Dealers sell into weakness.';
    conditions  = ['GEX negative (dealers short gamma)', 'Spot below gamma flip', 'DEX bearish'];
  } else if (nearCallWall && gexPositive) {
    signal      = '⚡ RESISTANCE — CALL WALL';
    signalColor = '#ff9100';
    signalBg    = 'rgba(255,145,0,0.08)';
    suggestion  = 'SELL CALLS at/above call wall. Strong resistance — market likely to stall.';
    risk        = 'MEDIUM — Breakout above call wall triggers short covering (explosive move).';
    conditions  = ['Near call wall resistance', 'GEX positive (stabilizing)', 'Upside capped'];
  } else if (nearPutWall && gexPositive) {
    signal      = '🛡 SUPPORT — PUT WALL';
    signalColor = '#00c853';
    signalBg    = 'rgba(0,200,83,0.08)';
    suggestion  = 'BUY CALLS or SELL PUTS near put wall. Strong support — market likely to bounce.';
    risk        = 'MEDIUM — Break below put wall triggers stop-loss cascade.';
    conditions  = ['Near put wall support', 'GEX positive (stabilizing)', 'Downside protected'];
  } else if (!gexPositive && gexStrong) {
    signal      = '💥 EXPLOSIVE MOVE POSSIBLE';
    signalColor = '#ff1744';
    signalBg    = 'rgba(255,23,68,0.12)';
    suggestion  = 'BUY STRADDLE or STRANGLE. Large negative GEX = dealers amplify moves in both directions.';
    risk        = 'HIGH — Direction unclear but magnitude likely large. Avoid naked selling.';
    conditions  = ['Large negative GEX', 'Dealers short gamma', 'Move amplification active'];
  } else if (gexPositive && betweenWalls && heavyDecay) {
    signal      = '↔ NEUTRAL — SELL PREMIUM';
    signalColor = '#ffcc00';
    signalBg    = 'rgba(255,204,0,0.08)';
    suggestion  = 'IRON CONDOR or SHORT STRANGLE. High theta decay favors option sellers.';
    risk        = 'LOW-MEDIUM — Range-bound with heavy time decay. Watch for breakout.';
    conditions  = ['GEX positive (range-bound)', 'Heavy theta decay (₹' + Math.abs(theta).toFixed(0) + 'Cr/day)', 'Price between walls'];
  } else {
    signal      = '↔ NEUTRAL — WAIT';
    signalColor = '#607d8b';
    signalBg    = 'rgba(96,125,139,0.08)';
    suggestion  = 'No clear edge. Wait for clearer setup or reduce position size.';
    risk        = 'MEDIUM — Mixed signals. Avoid large directional bets.';
    conditions  = ['Mixed GEX/DEX signals', 'No dominant positioning'];
  }

  return (
    <div className="border rounded-sm p-3" style={{ borderColor: signalColor + '40', backgroundColor: signalBg }}>
      <div className="flex items-center justify-between mb-2">
        <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest">⚡ GREEKS SIGNAL</div>
        <div className="text-2xs font-mono text-text-muted">Real-time · Based on GEX/DEX/Levels</div>
      </div>
      <div className="flex items-start gap-4">
        {/* Signal */}
        <div className="shrink-0">
          <div className="text-sm font-mono font-bold" style={{ color: signalColor }}>{signal}</div>
          <div className="text-2xs font-mono text-text-muted mt-1">RISK: <span style={{ color: signalColor }}>{risk.split('—')[0].trim()}</span></div>
        </div>
        <div className="w-px h-10 bg-border-primary shrink-0" />
        {/* Suggestion */}
        <div className="flex-1">
          <div className="text-2xs font-mono text-text-secondary">{suggestion}</div>
        </div>
        <div className="w-px h-10 bg-border-primary shrink-0" />
        {/* Conditions */}
        <div className="shrink-0 space-y-0.5">
          {conditions.map((c, i) => (
            <div key={i} className="flex items-center gap-1 text-2xs font-mono text-text-muted">
              <span style={{ color: signalColor }}>✓</span> {c}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

// ─── Metric Tiles ─────────────────────────────────────────────────────────────

const ExposureMetric: React.FC<{
  label: string;
  value: string;
  subLabel: string;
  positive: boolean;
  description?: string;
}> = ({ label, value, subLabel, positive, description }) => (
  <div className={`p-3 border ${positive ? 'border-market-up/30 bg-market-up-dim/50' : 'border-market-down/30 bg-market-down-dim/50'}`}>
    <div className="text-2xs font-mono text-text-muted mb-1 tracking-widest">{label}</div>
    <div className={`text-xl font-mono font-bold ${positive ? 'text-market-up' : 'text-market-down'}`}>
      {value}
    </div>
    <div className="text-2xs font-mono text-text-muted mt-1">{subLabel}</div>
    {description && (
      <div className={`text-2xs font-mono mt-1 ${positive ? 'text-market-up/70' : 'text-market-down/70'}`}>
        {description}
      </div>
    )}
  </div>
);

const KeyLevel: React.FC<{
  label: string;
  value: string;
  description: string;
  color: string;
  spotDiff: number;
}> = ({ label, value, description, color, spotDiff }) => (
  <div className="p-3 border border-border-primary bg-bg-panel">
    <div className="text-2xs font-mono text-text-muted tracking-widest mb-1">{label}</div>
    <div className={`text-lg font-mono font-bold ${color}`}>{value}</div>
    <div className="text-2xs font-mono text-text-muted mt-1">{description}</div>
    <div className={`text-2xs font-mono mt-1 ${spotDiff >= 0 ? 'text-market-up' : 'text-market-down'}`}>
      {spotDiff >= 0 ? '+' : ''}{fmt.num(spotDiff, 0)} from spot
    </div>
  </div>
);

// ─── Charts ───────────────────────────────────────────────────────────────────

const AXIS_STYLE = { fill: '#606060', fontSize: 8, fontFamily: 'monospace' };
const TOOLTIP_STYLE = { background: '#141414', border: '1px solid #2a2a2a', fontFamily: 'monospace', fontSize: 11 };
const GRID_STYLE = { strokeDasharray: '2 4', stroke: '#1e1e1e' };

const GEXChart: React.FC<{
  data: { strike: number; gex: number }[];
  spot: number;
  flipLevel: number;
}> = ({ data, spot, flipLevel }) => {
  const chartData = data.map((d) => ({
    strike: d.strike,
    gex: d.gex,
    fill: d.gex >= 0 ? '#00c853' : '#ff1744',
  }));

  return (
    <ResponsiveContainer width="100%" height={180}>
      <BarChart data={chartData} margin={{ top: 4, right: 4, bottom: 16, left: 0 }}>
        <CartesianGrid {...GRID_STYLE} />
        <XAxis dataKey="strike" tick={AXIS_STYLE} tickLine={false} interval={2} />
        <YAxis tick={AXIS_STYLE} tickLine={false} width={36} />
        <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={{ color: '#a0a0a0' }} formatter={(v: number) => [`${v.toFixed(4)}B`, 'GEX']} />
        <ReferenceLine y={0} stroke="#606060" strokeWidth={1} />
        <ReferenceLine x={spot} stroke="#ffcc00" strokeDasharray="3 3" label={{ value: 'S', fill: '#ffcc00', fontSize: 9 }} />
        {flipLevel > 0 && (
          <ReferenceLine x={flipLevel} stroke="#9b59b6" strokeDasharray="3 3" label={{ value: 'FLIP', fill: '#9b59b6', fontSize: 8 }} />
        )}
        <Bar dataKey="gex" maxBarSize={12}>
          {chartData.map((entry, i) => (
            <Cell key={i} fill={entry.gex >= 0 ? '#00c853' : '#ff1744'} fillOpacity={0.8} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
};

const DEXChart: React.FC<{ data: { strike: number; dex: number }[]; spot: number }> = ({ data, spot }) => (
  <ResponsiveContainer width="100%" height={160}>
    <ComposedChart data={data} margin={{ top: 4, right: 4, bottom: 16, left: 0 }}>
      <CartesianGrid {...GRID_STYLE} />
      <XAxis dataKey="strike" tick={AXIS_STYLE} tickLine={false} interval={2} />
      <YAxis tick={AXIS_STYLE} tickLine={false} width={36} />
      <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={{ color: '#a0a0a0' }} formatter={(v: number) => [`${v.toFixed(3)}Cr`, 'DEX']} />
      <ReferenceLine y={0} stroke="#606060" />
      <ReferenceLine x={spot} stroke="#ffcc00" strokeDasharray="3 3" />
      <Area type="monotone" dataKey="dex" fill="#00d4ff" fillOpacity={0.15} stroke="#00d4ff" strokeWidth={1.5} />
    </ComposedChart>
  </ResponsiveContainer>
);

const VegaChart: React.FC<{ data: { strike: number; net_vega: number }[]; spot: number }> = ({ data, spot }) => (
  <ResponsiveContainer width="100%" height={130}>
    <BarChart data={data} margin={{ top: 4, right: 4, bottom: 12, left: 0 }}>
      <CartesianGrid {...GRID_STYLE} />
      <XAxis dataKey="strike" tick={AXIS_STYLE} tickLine={false} interval={3} />
      <YAxis tick={AXIS_STYLE} tickLine={false} width={30} />
      <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={{ color: '#a0a0a0' }} />
      <ReferenceLine x={spot} stroke="#ffcc00" strokeDasharray="3 3" />
      <Bar dataKey="net_vega" fill="#9b59b6" fillOpacity={0.8} maxBarSize={10} />
    </BarChart>
  </ResponsiveContainer>
);

const ThetaChart: React.FC<{ data: { strike: number; net_theta: number }[]; spot: number }> = ({ data, spot }) => {
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    const theta = payload[0]?.value ?? 0;
    return (
      <div style={{ background: '#141414', border: '1px solid #2a2a2a', padding: '8px', fontFamily: 'monospace', fontSize: 11 }}>
        <div style={{ color: '#a0a0a0' }}>Strike: {label}</div>
        <div style={{ color: '#ff9900' }}>Theta: ₹{Math.abs(theta).toFixed(2)} Cr/day</div>
        <div style={{ color: '#606060', fontSize: 9 }}>
          {theta < 0 ? 'Buyers lose this per day' : 'Sellers earn this per day'}
        </div>
      </div>
    );
  };
  return (
    <ResponsiveContainer width="100%" height={130}>
      <BarChart data={data} margin={{ top: 4, right: 4, bottom: 12, left: 0 }}>
        <CartesianGrid {...GRID_STYLE} />
        <XAxis dataKey="strike" tick={AXIS_STYLE} tickLine={false} interval={3} />
        <YAxis tick={AXIS_STYLE} tickLine={false} width={30} />
        <Tooltip content={<CustomTooltip />} />
        <ReferenceLine x={spot} stroke="#ffcc00" strokeDasharray="3 3" />
        <Bar dataKey="net_theta" fill="#ff9900" fillOpacity={0.8} maxBarSize={10} />
      </BarChart>
    </ResponsiveContainer>
  );
};

const GEXTable: React.FC<{ data: { strike: number; gex: number; call_gamma: number; put_gamma: number }[]; spot: number }> = ({ data, spot }) => {
  const sorted = [...data].sort((a, b) => Math.abs(b.gex) - Math.abs(a.gex)).slice(0, 10);
  return (
    <div className="font-mono text-2xs overflow-y-auto">
      <div className="grid grid-cols-4 text-text-muted border-b border-border-primary pb-1 mb-1">
        <span>STRIKE</span><span className="text-right">CALL Γ</span><span className="text-right">PUT Γ</span><span className="text-right">NET GEX</span>
      </div>
      {sorted.map((row) => (
        <div key={row.strike} className={`grid grid-cols-4 py-0.5 ${row.strike === Math.round(spot / 50) * 50 ? 'text-accent-yellow' : 'text-text-secondary'}`}>
          <span>{fmt.strike(row.strike)}</span>
          <span className="text-right text-chart-call">{row.call_gamma.toFixed(4)}</span>
          <span className="text-right text-chart-put">{row.put_gamma.toFixed(4)}</span>
          <span className={`text-right ${row.gex >= 0 ? 'text-market-up' : 'text-market-down'}`}>
            {row.gex.toFixed(4)}
          </span>
        </div>
      ))}
    </div>
  );
};

// ─── Panel Wrapper ────────────────────────────────────────────────────────────

const ChartPanel: React.FC<{
  title: string;
  children: React.ReactNode;
  className?: string;
}> = ({ title, children, className = '' }) => (
  <div className={`border border-border-primary bg-bg-panel p-3 ${className}`}>
    <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest mb-2">{title}</div>
    {children}
  </div>
);
