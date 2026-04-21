import React, { useState, useCallback, useMemo } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceLine, CartesianGrid, LineChart, Line, BarChart, Bar,
} from 'recharts';
import { useMarketStore } from '../../store/marketStore';
import { fmt } from '../../utils/format';
import { api } from '../../utils/api';
import type { StrategyLeg, StrategyAnalysis } from '../../types';

// ─── Preset strategies ────────────────────────────────────────────────────────

const PRESETS = [
  {
    name: 'Long Straddle', category: 'NEUTRAL',
    build: (atm: number, exp: string, p: number): StrategyLeg[] => [
      leg('CE', atm, exp, 'BUY', p), leg('PE', atm, exp, 'BUY', p),
    ],
  },
  {
    name: 'Short Straddle', category: 'NEUTRAL',
    build: (atm: number, exp: string, p: number): StrategyLeg[] => [
      leg('CE', atm, exp, 'SELL', p), leg('PE', atm, exp, 'SELL', p),
    ],
  },
  {
    name: 'Long Strangle', category: 'NEUTRAL',
    build: (atm: number, exp: string, p: number, step = 100): StrategyLeg[] => [
      leg('CE', atm + step, exp, 'BUY', p * 0.5), leg('PE', atm - step, exp, 'BUY', p * 0.5),
    ],
  },
  {
    name: 'Short Strangle', category: 'NEUTRAL',
    build: (atm: number, exp: string, p: number, step = 100): StrategyLeg[] => [
      leg('CE', atm + step, exp, 'SELL', p * 0.5), leg('PE', atm - step, exp, 'SELL', p * 0.5),
    ],
  },
  {
    name: 'Bull Call Spread', category: 'BULLISH',
    build: (atm: number, exp: string, p: number, step = 100): StrategyLeg[] => [
      leg('CE', atm, exp, 'BUY', p), leg('CE', atm + step, exp, 'SELL', p * 0.4),
    ],
  },
  {
    name: 'Bear Put Spread', category: 'BEARISH',
    build: (atm: number, exp: string, p: number, step = 100): StrategyLeg[] => [
      leg('PE', atm, exp, 'BUY', p), leg('PE', atm - step, exp, 'SELL', p * 0.4),
    ],
  },
  {
    name: 'Bull Put Spread', category: 'BULLISH',
    build: (atm: number, exp: string, p: number, step = 100): StrategyLeg[] => [
      leg('PE', atm - step, exp, 'BUY', p * 0.3), leg('PE', atm, exp, 'SELL', p * 0.7),
    ],
  },
  {
    name: 'Bear Call Spread', category: 'BEARISH',
    build: (atm: number, exp: string, p: number, step = 100): StrategyLeg[] => [
      leg('CE', atm, exp, 'SELL', p * 0.7), leg('CE', atm + step, exp, 'BUY', p * 0.3),
    ],
  },
  {
    name: 'Iron Condor', category: 'NEUTRAL',
    build: (atm: number, exp: string, p: number, step = 100): StrategyLeg[] => [
      leg('PE', atm - step * 2, exp, 'BUY', p * 0.2),
      leg('PE', atm - step, exp, 'SELL', p * 0.5),
      leg('CE', atm + step, exp, 'SELL', p * 0.5),
      leg('CE', atm + step * 2, exp, 'BUY', p * 0.2),
    ],
  },
  {
    name: 'Iron Butterfly', category: 'NEUTRAL',
    build: (atm: number, exp: string, p: number, step = 100): StrategyLeg[] => [
      leg('PE', atm - step, exp, 'BUY', p * 0.2),
      leg('PE', atm, exp, 'SELL', p),
      leg('CE', atm, exp, 'SELL', p),
      leg('CE', atm + step, exp, 'BUY', p * 0.2),
    ],
  },
  {
    name: 'Long Butterfly', category: 'NEUTRAL',
    build: (atm: number, exp: string, p: number, step = 100): StrategyLeg[] => [
      leg('CE', atm - step, exp, 'BUY', p * 1.5),
      leg('CE', atm, exp, 'SELL', p, 2),
      leg('CE', atm + step, exp, 'BUY', p * 0.5),
    ],
  },
  {
    name: 'Covered Call', category: 'BULLISH',
    build: (atm: number, exp: string, p: number, step = 100): StrategyLeg[] => [
      leg('CE', atm + step, exp, 'SELL', p * 0.4),
    ],
  },
];

function leg(
  option_type: 'CE' | 'PE', strike: number, expiry: string,
  action: 'BUY' | 'SELL', premium: number, quantity = 1
): StrategyLeg {
  return { option_type, strike, expiry, action, quantity, premium, iv: 0, greeks: { delta: 0, gamma: 0, theta: 0, vega: 0, rho: 0 } };
}

const CATEGORY_COLOR: Record<string, string> = {
  BULLISH: '#00c853', BEARISH: '#ff1744', NEUTRAL: '#00d4ff',
};

// ─── Main Component ───────────────────────────────────────────────────────────

export const StrategyBuilderTab: React.FC = () => {
  const { chain, strategyLegs, addStrategyLeg, removeStrategyLeg, clearStrategyLegs } = useMarketStore();
  const [analysis, setAnalysis] = useState<StrategyAnalysis | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState('');
  const [activeCategory, setActiveCategory] = useState<string>('ALL');
  const [strikeStep, setStrikeStep] = useState(100);
  const [customLeg, setCustomLeg] = useState<Partial<StrategyLeg>>({
    option_type: 'CE', action: 'BUY', quantity: 1,
    strike: chain?.atm_strike || 0,
    expiry: chain?.expiry || '',
    premium: 0, iv: 0,
    greeks: { delta: 0, gamma: 0, theta: 0, vega: 0, rho: 0 },
  });

  // Sync custom leg defaults when chain loads
  React.useEffect(() => {
    if (chain && !customLeg.strike) {
      setCustomLeg(l => ({ ...l, strike: chain.atm_strike, expiry: chain.expiry }));
    }
  }, [chain]);

  const analyze = useCallback(async () => {
    if (!strategyLegs.length) return;
    setIsAnalyzing(true);
    setError('');
    try {
      const result = await api.analyzeStrategy(strategyLegs);
      setAnalysis(result);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setIsAnalyzing(false);
    }
  }, [strategyLegs]);

  const loadPreset = (preset: typeof PRESETS[0]) => {
    if (!chain) return;
    clearStrategyLegs();
    const atm = chain.atm_strike;
    const atmRow = chain.rows.find(r => r.is_atm);
    const p = ((atmRow?.call.ltp || 0) + (atmRow?.put.ltp || 0)) / 2 || 100;
    preset.build(atm, chain.expiry, p, strikeStep).forEach(addStrategyLeg);
  };

  const addCustom = () => {
    if (!customLeg.strike || !customLeg.expiry) return;
    addStrategyLeg(customLeg as StrategyLeg);
  };

  const filteredPresets = activeCategory === 'ALL'
    ? PRESETS
    : PRESETS.filter(p => p.category === activeCategory);

  return (
    <div className="flex h-full overflow-hidden bg-bg-primary">
      {/* ── Left Panel ── */}
      <div className="flex flex-col gap-2 w-72 shrink-0 border-r border-border-primary overflow-y-auto p-2">

        {/* Strike Step */}
        <div className="border border-border-primary bg-bg-panel p-2">
          <div className="text-2xs font-mono text-text-muted mb-1.5 tracking-widest">STRIKE STEP</div>
          <div className="flex gap-1">
            {[50, 100, 200, 500].map(s => (
              <button key={s} onClick={() => setStrikeStep(s)}
                className={`flex-1 py-0.5 text-2xs font-mono border transition-all ${strikeStep === s ? 'border-accent-yellow text-accent-yellow bg-accent-yellow/10' : 'border-border-primary text-text-muted hover:border-text-secondary'}`}>
                {s}
              </button>
            ))}
          </div>
        </div>

        {/* Preset Strategies */}
        <div className="border border-border-primary bg-bg-panel p-2">
          <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest mb-2">PRESET STRATEGIES</div>
          <div className="flex gap-1 mb-2">
            {['ALL', 'BULLISH', 'BEARISH', 'NEUTRAL'].map(cat => (
              <button key={cat} onClick={() => setActiveCategory(cat)}
                className={`flex-1 py-0.5 text-2xs font-mono border transition-all ${activeCategory === cat ? 'border-accent-yellow text-accent-yellow' : 'border-border-primary text-text-muted'}`}>
                {cat === 'ALL' ? 'ALL' : cat.slice(0, 4)}
              </button>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-1">
            {filteredPresets.map(preset => (
              <button key={preset.name} onClick={() => loadPreset(preset)}
                className="px-2 py-1.5 border border-border-primary text-2xs font-mono text-left hover:border-accent-yellow hover:bg-bg-hover transition-all group">
                <div className="flex items-center gap-1 mb-0.5">
                  <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: CATEGORY_COLOR[preset.category] }} />
                  <span className="text-text-secondary group-hover:text-accent-yellow truncate">{preset.name}</span>
                </div>
                <span className="text-2xs" style={{ color: CATEGORY_COLOR[preset.category], opacity: 0.7 }}>{preset.category}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Custom Leg Builder */}
        <div className="border border-border-primary bg-bg-panel p-2">
          <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest mb-2">CUSTOM LEG</div>
          <div className="flex flex-col gap-1.5">
            <div className="grid grid-cols-2 gap-1">
              {(['CE', 'PE'] as const).map(ot => (
                <button key={ot} onClick={() => setCustomLeg(l => ({ ...l, option_type: ot }))}
                  className={`py-1 text-xs font-mono font-bold border transition-all ${customLeg.option_type === ot ? (ot === 'CE' ? 'bg-chart-call/20 border-chart-call text-chart-call' : 'bg-chart-put/20 border-chart-put text-chart-put') : 'border-border-primary text-text-muted'}`}>
                  {ot}
                </button>
              ))}
            </div>
            <div className="grid grid-cols-2 gap-1">
              {(['BUY', 'SELL'] as const).map(act => (
                <button key={act} onClick={() => setCustomLeg(l => ({ ...l, action: act }))}
                  className={`py-1 text-xs font-mono font-bold border transition-all ${customLeg.action === act ? (act === 'BUY' ? 'bg-market-up/20 border-market-up text-market-up' : 'bg-market-down/20 border-market-down text-market-down') : 'border-border-primary text-text-muted'}`}>
                  {act}
                </button>
              ))}
            </div>
            {/* Strike selector from chain */}
            {chain && (
              <div>
                <label className="text-2xs font-mono text-text-muted block mb-0.5">STRIKE</label>
                <select value={customLeg.strike} onChange={e => setCustomLeg(l => ({ ...l, strike: Number(e.target.value) }))}
                  className="w-full bg-bg-primary border border-border-primary text-text-primary font-mono text-xs px-2 py-1 focus:outline-none focus:border-accent-yellow">
                  {chain.rows.map(r => (
                    <option key={r.strike} value={r.strike}>
                      {r.strike} {r.is_atm ? '← ATM' : ''}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <LegInput label="PREMIUM" type="number" value={customLeg.premium || ''} onChange={v => setCustomLeg(l => ({ ...l, premium: Number(v) }))} />
            <LegInput label="IV (%)" type="number" value={customLeg.iv || ''} onChange={v => setCustomLeg(l => ({ ...l, iv: Number(v) }))} />
            <LegInput label="QTY (LOTS)" type="number" value={customLeg.quantity || 1} onChange={v => setCustomLeg(l => ({ ...l, quantity: Number(v) }))} />
            <button onClick={addCustom}
              className="py-1.5 bg-accent-yellow text-black font-mono font-bold text-xs hover:bg-yellow-400 transition-colors">
              + ADD LEG
            </button>
          </div>
        </div>

        {/* Current Legs */}
        {strategyLegs.length > 0 && (
          <div className="border border-border-primary bg-bg-panel p-2">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-2xs font-mono font-bold text-accent-yellow tracking-widest">LEGS ({strategyLegs.length})</span>
              <button onClick={clearStrategyLegs} className="text-2xs font-mono text-text-muted hover:text-market-down">CLEAR ALL</button>
            </div>
            <div className="space-y-0.5 mb-2">
              {strategyLegs.map((l, i) => (
                <div key={i} className="flex items-center gap-1.5 py-1 border-b border-border-secondary text-2xs font-mono">
                  <span className={l.action === 'BUY' ? 'text-market-up font-bold' : 'text-market-down font-bold'}>{l.action}</span>
                  <span className={l.option_type === 'CE' ? 'text-chart-call' : 'text-chart-put'}>{l.option_type}</span>
                  <span className="text-text-primary font-bold">{l.strike}</span>
                  <span className="text-text-muted">@{l.premium.toFixed(1)}</span>
                  <span className="text-text-muted">×{l.quantity}</span>
                  <button onClick={() => removeStrategyLeg(i)} className="ml-auto text-market-down hover:text-red-400 text-xs">✕</button>
                </div>
              ))}
            </div>
            <button onClick={analyze} disabled={isAnalyzing}
              className="w-full py-1.5 bg-accent-yellow text-black font-mono font-bold text-xs hover:bg-yellow-400 disabled:opacity-50 transition-colors">
              {isAnalyzing ? '■ ANALYZING...' : '▶ ANALYZE'}
            </button>
          </div>
        )}
      </div>

      {/* ── Right Panel ── */}
      <div className="flex flex-col flex-1 min-w-0 overflow-y-auto p-2 gap-2">
        {error && (
          <div className="border border-market-down/30 bg-market-down/10 p-2 text-xs font-mono text-market-down shrink-0">⚠ {error}</div>
        )}

        {!analysis && !strategyLegs.length && (
          <div className="flex items-center justify-center flex-1 border border-border-primary">
            <div className="text-center text-text-muted font-mono text-xs">
              <div className="text-3xl mb-3 text-border-primary">⬡</div>
              <div className="text-text-secondary mb-1">Select a preset strategy or build custom legs</div>
              <div className="text-2xs">Then click Analyze to see P&L payoff</div>
            </div>
          </div>
        )}

        {strategyLegs.length > 0 && !analysis && (
          <div className="flex items-center justify-center flex-1 border border-border-primary border-dashed">
            <div className="text-center text-text-muted font-mono text-xs">
              <div className="text-accent-yellow mb-2">{strategyLegs.length} leg{strategyLegs.length > 1 ? 's' : ''} added</div>
              <div>Click ▶ ANALYZE to compute payoff</div>
            </div>
          </div>
        )}

        {analysis && <AnalysisPanel analysis={analysis} />}
      </div>
    </div>
  );
};

// ─── Analysis Panel ───────────────────────────────────────────────────────────

const AnalysisPanel: React.FC<{ analysis: StrategyAnalysis }> = ({ analysis }) => {
  const maxProfit = analysis.max_profit;
  const maxLoss   = analysis.max_loss;
  const rr = maxLoss !== 0 ? Math.abs(maxProfit / maxLoss) : Infinity;

  return (
    <>
      {/* Strategy Header */}
      <div className="border border-border-primary bg-bg-panel p-3 shrink-0">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-mono font-bold text-accent-yellow">{analysis.strategy_name}</span>
          <div className="flex gap-3 text-2xs font-mono">
            <span className="text-text-muted">Δ <span className="text-text-secondary">{analysis.net_delta.toFixed(3)}</span></span>
            <span className="text-text-muted">Γ <span className="text-text-secondary">{analysis.net_gamma.toFixed(5)}</span></span>
            <span className="text-text-muted">Θ <span className="text-market-down">{analysis.net_theta.toFixed(3)}</span></span>
            <span className="text-text-muted">ν <span className="text-accent-cyan">{analysis.net_vega.toFixed(3)}</span></span>
          </div>
        </div>
        <div className="grid grid-cols-5 gap-2">
          <Metric label="NET PREMIUM"
            value={`₹${fmt.price(Math.abs(analysis.net_premium))}`}
            sub={analysis.net_premium <= 0 ? 'DEBIT' : 'CREDIT'}
            color={analysis.net_premium <= 0 ? 'text-market-down' : 'text-market-up'} />
          <Metric label="MAX PROFIT"
            value={maxProfit === Infinity ? '∞' : `₹${fmt.price(maxProfit)}`}
            sub="per lot" color="text-market-up" />
          <Metric label="MAX LOSS"
            value={maxLoss === -Infinity ? '∞' : `₹${fmt.price(Math.abs(maxLoss))}`}
            sub="per lot" color="text-market-down" />
          <Metric label="RISK/REWARD"
            value={rr === Infinity ? '∞' : rr.toFixed(2)}
            sub="profit/loss" color={rr >= 1 ? 'text-market-up' : 'text-text-secondary'} />
          <Metric label="BREAKEVEN(S)"
            value={analysis.breakevens.length ? analysis.breakevens.map(b => fmt.strike(b)).join(' / ') : '—'}
            sub="" color="text-accent-yellow" />
        </div>
      </div>

      {/* Payoff Chart */}
      <div className="border border-border-primary bg-bg-panel p-3 flex-1 min-h-0">
        <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest mb-2">P&L PAYOFF AT EXPIRY</div>
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={analysis.payoff_curve} margin={{ top: 4, right: 8, bottom: 16, left: 8 }}>
            <defs>
              <linearGradient id="profitGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#00c853" stopOpacity={0.25} />
                <stop offset="95%" stopColor="#00c853" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="lossGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#ff1744" stopOpacity={0} />
                <stop offset="95%" stopColor="#ff1744" stopOpacity={0.25} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="2 4" stroke="#1e1e1e" />
            <XAxis dataKey="spot" tick={{ fill: '#606060', fontSize: 8, fontFamily: 'monospace' }} tickLine={false} interval={9}
              tickFormatter={v => fmt.strike(v)} />
            <YAxis tick={{ fill: '#606060', fontSize: 8, fontFamily: 'monospace' }} tickLine={false} width={52}
              tickFormatter={v => `₹${fmt.compact(v)}`} />
            <Tooltip
              contentStyle={{ background: '#141414', border: '1px solid #2a2a2a', fontFamily: 'monospace', fontSize: 11 }}
              formatter={(v: number) => [`₹${v.toFixed(2)}`, 'P&L']}
              labelFormatter={v => `Spot: ${fmt.strike(Number(v))}`}
            />
            <ReferenceLine y={0} stroke="#404040" strokeWidth={1.5} />
            {analysis.breakevens.map(be => (
              <ReferenceLine key={be} x={be} stroke="#ffcc00" strokeDasharray="3 3"
                label={{ value: `BE ${fmt.strike(be)}`, fill: '#ffcc00', fontSize: 7, position: 'top' }} />
            ))}
            <Area type="monotone" dataKey="pnl" stroke="#00d4ff" strokeWidth={2}
              fill="url(#profitGrad)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Legs Table */}
      <div className="border border-border-primary bg-bg-panel p-3 shrink-0">
        <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest mb-2">LEG DETAILS</div>
        <div className="grid text-2xs font-mono text-text-muted border-b border-border-primary pb-1 mb-1"
          style={{ gridTemplateColumns: '1fr 0.6fr 0.6fr 0.8fr 0.6fr 0.8fr 0.8fr 0.8fr 0.8fr' }}>
          <span>TYPE</span><span>STRIKE</span><span>ACTION</span><span>PREMIUM</span>
          <span>QTY</span><span>DELTA</span><span>GAMMA</span><span>THETA</span><span>VEGA</span>
        </div>
        {analysis.legs.map((l, i) => (
          <div key={i} className="grid text-2xs font-mono py-0.5 hover:bg-bg-hover"
            style={{ gridTemplateColumns: '1fr 0.6fr 0.6fr 0.8fr 0.6fr 0.8fr 0.8fr 0.8fr 0.8fr' }}>
            <span className={l.option_type === 'CE' ? 'text-chart-call' : 'text-chart-put'}>{l.option_type}</span>
            <span className="text-text-primary">{l.strike}</span>
            <span className={l.action === 'BUY' ? 'text-market-up' : 'text-market-down'}>{l.action}</span>
            <span className="text-text-secondary">₹{l.premium.toFixed(2)}</span>
            <span className="text-text-muted">{l.quantity}</span>
            <span className="text-text-secondary">{l.greeks.delta.toFixed(3)}</span>
            <span className="text-text-secondary">{l.greeks.gamma.toFixed(5)}</span>
            <span className="text-market-down">{l.greeks.theta.toFixed(3)}</span>
            <span className="text-accent-cyan">{l.greeks.vega.toFixed(3)}</span>
          </div>
        ))}
      </div>
    </>
  );
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

const LegInput: React.FC<{ label: string; type: string; value: string | number; onChange: (v: string) => void }> = ({ label, type, value, onChange }) => (
  <div>
    <label className="text-2xs font-mono text-text-muted block mb-0.5">{label}</label>
    <input type={type} value={value} onChange={e => onChange(e.target.value)}
      className="w-full bg-bg-primary border border-border-primary text-text-primary font-mono text-xs px-2 py-1 focus:outline-none focus:border-accent-yellow" />
  </div>
);

const Metric: React.FC<{ label: string; value: string; sub: string; color?: string }> = ({ label, value, sub, color = 'text-text-primary' }) => (
  <div className="border border-border-secondary bg-bg-tertiary p-2">
    <div className="text-2xs font-mono text-text-muted">{label}</div>
    <div className={`text-sm font-mono font-bold mt-0.5 truncate ${color}`}>{value || '—'}</div>
    {sub && <div className="text-2xs font-mono text-text-muted mt-0.5">{sub}</div>}
  </div>
);
