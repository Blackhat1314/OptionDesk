import React, { useState, useEffect, useMemo, useCallback } from "react";
import { api } from "../../utils/api";
import { useMarketStore } from "../../store/marketStore";

// ─── Types ────────────────────────────────────────────────────────────────────

interface StockRisk {
  drawdown: number;
  volatility: number;
  vol_stable: boolean;
}

interface StockMonteCarlo {
  expected_price: number;
  prob_up: number;
  prob_down?: number;
  worst_case_5pct: number;
  best_case_95pct?: number;
  position_advice: string;
  horizon_days?: number;
  horizon_label?: string;
  regime?: string;
}

interface StockBacktest {
  total_trades: number;
  win_rate: number;
  avg_return?: number;
  sharpe: number;
  max_drawdown?: number;
}

interface StockEntry {
  symbol: string;
  group?: string;
  sector?: string;
  price: number;
  signal: string;
  smart_label?: string;
  score: number;
  risk_adj_score?: number;
  rank_score?: number;
  confidence?: number;
  trend?: string;
  momentum?: string;
  risk_level?: string;
  relative_strength?: number;
  entry_type?: string;
  entry_detail?: string;
  adjustments?: string[];
  buy_conditions_met?: boolean;
  roc_252: number;
  roc_63?: number;
  roc_21?: number;
  ma50: number;
  ma200: number;
  w52_high?: number;
  w52_low?: number;
  support?: number;
  resistance?: number;
  sparkline?: number[];
  avg_turnover_cr?: number;
  is_liquid?: boolean;
  overbought?: boolean;
  oversold?: boolean;
  atr_pct?: number;
  // Trade levels (ATR-based)
  stop_loss_price?: number;
  target_price?: number;
  atr_stop_loss_pct?: number;
  atr_target_pct?: number;
  risk_reward_ratio?: number;
  // Time horizon guidance
  recommended_hold?: string;
  hold_confidence?: string;
  risk?: StockRisk;
  monte_carlo?: StockMonteCarlo;
  backtest?: StockBacktest;
  // Live price fields (populated during market hours)
  live_price?: boolean;
  day_change?: number;
  day_change_pct?: number;
  intraday_change_pct?: number;
  range_position?: number;
  live_open?: number;
  live_high?: number;
  live_low?: number;
  // Legacy flat fields
  drawdown?: number;
  sigma?: number;
  prob_up?: number;
  expected_price?: number;
  worst_case_5pct?: number;
  position_advice?: string;
  backtest_trades?: number;
  backtest_winrate?: number;
  backtest_sharpe?: number;
}

interface TopPick {
  rank: number;
  symbol: string;
  signal: string;
  score: number;
  rank_score: number;
  rs: number;
  prob_up: number;
  entry_detail: string;
  sector: string;
  group: string;
  confidence: number;
  roc_252: number;
}

interface MarketContext {
  market_regime?: string;
  breadth_pct?: number;
  top_sector?: string;
  weak_sector?: string;
  sector_avg_rs?: Record<string, number>;
  avg_rs?: number;
  avg_confidence?: number;
  score_distribution?: Record<string, number>;
  bullish_count?: number;
  total_computed?: number;
}

interface MarketInsights {
  top_sector?: string;
  sector_counts?: Record<string, number>;
  avg_rs?: number;
  market_regime?: string;
  avg_confidence?: number;
  score_distribution?: Record<string, number>;
  bullish_pct?: number;
}

interface PipelineStatus {
  status: string;
  message?: string;
  progress?: number;
  stage?: string;
}

interface DbStats {
  total_stocks?: number;
  buy_signals?: number;
  candles_cached?: number;
  last_run?: string;
}

interface LongTermResult {
  stocks?: StockEntry[];
  pipeline_status?: PipelineStatus;
  db_stats?: DbStats;
  insights?: MarketInsights;
  top_picks?: TopPick[];
  market_context?: MarketContext;
  computing?: boolean;
  waiting?: boolean;
  last_updated?: string;
}

interface FundamentalsRatios {
  pe_ratio?: number | null;
  pb_ratio?: number | null;
  roce?: number | null;
  roe?: number | null;
  debt_equity?: number | null;
  dividend_yield?: number | null;
  market_cap_cr?: number | null;
  book_value?: number | null;
  face_value?: number | null;
}

interface FundamentalsGrowth {
  revenue_growth_yoy?: number | null;
  profit_growth_yoy?: number | null;
  revenue_cagr_3y?: number | null;
  revenue_cagr_5y?: number | null;
  profit_cagr_3y?: number | null;
  profit_cagr_5y?: number | null;
}

interface FundamentalsQuarter {
  period?: string;
  year?: string;
  revenue?: number | null;
  net_profit?: number | null;
  opm_pct?: number | null;
  eps?: number | null;
}

interface FundamentalsInfo {
  name?: string;
  sector?: string;
  industry?: string;
  description?: string;
}

interface Fundamentals {
  symbol: string;
  status: string;
  message?: string;
  source?: string;
  ratios?: FundamentalsRatios;
  growth?: FundamentalsGrowth;
  quarterly?: FundamentalsQuarter[];
  annual?: FundamentalsQuarter[];
  info?: FundamentalsInfo;
  fetched_at?: number;
}

// ─── Color constants ──────────────────────────────────────────────────────────

const SIGNAL_COLOR: Record<string, string> = {
  "STRONG BUY": "#00c853",
  "BUY": "#69f0ae",
  "REJECT": "#607d8b",
};

function SCORE_COLOR(n: number): string {
  if (n >= 8) return "#00c853";
  if (n >= 6) return "#ffcc00";
  if (n >= 5) return "#ff9800";
  return "#607d8b";
}

const RISK_COLOR: Record<string, string> = {
  LOW: "#00c853",
  MEDIUM: "#ffcc00",
  HIGH: "#f44336",
};

const ENTRY_COLOR: Record<string, string> = {
  PULLBACK: "#2196f3",
  BREAKOUT: "#00c853",
  NONE: "#607d8b",
};

function rowBg(score: number): string {
  if (score >= 10) return "rgba(0,200,83,0.12)";
  if (score >= 8) return "rgba(0,200,83,0.07)";
  if (score >= 6) return "rgba(255,204,0,0.05)";
  return "transparent";
}

// ─── Safe accessor helpers ────────────────────────────────────────────────────

function getDrawdown(s: StockEntry): number {
  if (s.risk?.drawdown !== undefined) return s.risk.drawdown * 100;
  return s.drawdown ?? 0;
}

function getVolatility(s: StockEntry): number {
  if (s.risk?.volatility !== undefined) return s.risk.volatility * 100;
  return s.sigma ?? 0;
}

function getProbUp(s: StockEntry): number {
  if (s.monte_carlo?.prob_up !== undefined) return s.monte_carlo.prob_up;
  return s.prob_up ?? 50;
}

function getExpectedPrice(s: StockEntry): number {
  if (s.monte_carlo?.expected_price !== undefined) return s.monte_carlo.expected_price;
  return s.expected_price ?? s.price;
}

function getWorstCase(s: StockEntry): number {
  if (s.monte_carlo?.worst_case_5pct !== undefined) return s.monte_carlo.worst_case_5pct;
  return s.worst_case_5pct ?? 0;
}

function getPositionAdvice(s: StockEntry): string {
  if (s.monte_carlo?.position_advice) return s.monte_carlo.position_advice;
  return s.position_advice ?? "NORMAL";
}

function getBtTrades(s: StockEntry): number {
  if (s.backtest?.total_trades !== undefined) return s.backtest.total_trades;
  return s.backtest_trades ?? 0;
}

function getBtWinRate(s: StockEntry): number {
  if (s.backtest?.win_rate !== undefined) return s.backtest.win_rate;
  return s.backtest_winrate ?? 0;
}

function getBtSharpe(s: StockEntry): number {
  if (s.backtest?.sharpe !== undefined) return s.backtest.sharpe;
  return s.backtest_sharpe ?? 0;
}

// ─── Shared sub-components ────────────────────────────────────────────────────

const StatPill: React.FC<{ label: string; value: string | number; color?: string }> = ({ label, value, color }) => (
  <div className="flex flex-col items-center px-2 border-r border-border-secondary last:border-r-0">
    <span className="text-2xs font-mono text-text-muted">{label}</span>
    <span className="text-xs font-mono font-bold" style={{ color: color ?? "#f5f5f5" }}>{value}</span>
  </div>
);

const StatBox: React.FC<{ label: string; value: string | number; color?: string }> = ({ label, value, color }) => (
  <div className="border border-border-primary bg-bg-panel p-2 text-center">
    <div className="text-2xs font-mono text-text-muted">{label}</div>
    <div className="text-sm font-mono font-bold" style={{ color: color ?? "#f5f5f5" }}>{value}</div>
  </div>
);

const Row: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <div className="flex items-center justify-between py-0.5 border-b border-border-secondary/30">
    <span className="text-2xs font-mono text-text-muted">{label}</span>
    <span className="text-2xs font-mono text-text-primary">{value}</span>
  </div>
);

const RiskDot: React.FC<{ level?: string }> = ({ level }) => {
  const lvl = (level ?? "").toUpperCase();
  const color = RISK_COLOR[lvl] ?? "#607d8b";
  return (
    <span className="inline-flex items-center gap-1">
      <span className="w-1.5 h-1.5 rounded-full inline-block" style={{ backgroundColor: color }} />
      <span className="text-2xs font-mono" style={{ color }}>{lvl || "—"}</span>
    </span>
  );
};

const ScoreBar: React.FC<{ score: number }> = ({ score }) => {
  const pct = Math.min(100, Math.max(0, (score / 10) * 100));
  const color = SCORE_COLOR(score);
  return (
    <div className="flex items-center gap-1">
      <div className="w-16 h-1.5 bg-bg-tertiary rounded-sm overflow-hidden">
        <div className="h-full rounded-sm" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
      <span className="text-2xs font-mono font-bold" style={{ color }}>{score}</span>
    </div>
  );
};

// ─── Sparkline SVG ────────────────────────────────────────────────────────────

const SparklineSVG: React.FC<{ prices: number[]; ma50?: number; currentPrice?: number }> = ({
  prices,
  ma50,
  currentPrice,
}) => {
  if (!prices || prices.length < 2) {
    return (
      <div className="w-full h-20 flex items-center justify-center text-2xs text-text-muted font-mono">
        NO PRICE DATA
      </div>
    );
  }

  const W = 200;
  const H = 60;
  const pad = 4;

  const minP = Math.min(...prices);
  const maxP = Math.max(...prices);
  const range = maxP - minP || 1;

  const toX = (i: number) => pad + ((i / (prices.length - 1)) * (W - pad * 2));
  const toY = (p: number) => H - pad - ((p - minP) / range) * (H - pad * 2);

  const points = prices.map((p, i) => `${toX(i).toFixed(1)},${toY(p).toFixed(1)}`).join(" ");

  // MA50 horizontal line (normalized to chart)
  const ma50Y = ma50 !== undefined ? toY(Math.min(Math.max(ma50, minP), maxP)) : null;

  // Current price dot
  const lastX = toX(prices.length - 1);
  const lastY = toY(prices[prices.length - 1]);
  const cp = currentPrice ?? prices[prices.length - 1];
  const cpY = toY(Math.min(Math.max(cp, minP), maxP));

  const isUp = prices[prices.length - 1] >= prices[0];

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      height="80"
      preserveAspectRatio="none"
      className="block"
    >
      {/* Area fill */}
      <defs>
        <linearGradient id="sparkGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={isUp ? "#00c853" : "#f44336"} stopOpacity="0.25" />
          <stop offset="100%" stopColor={isUp ? "#00c853" : "#f44336"} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <polygon
        points={`${pad},${H - pad} ${points} ${toX(prices.length - 1)},${H - pad}`}
        fill="url(#sparkGrad)"
      />
      {/* Price line */}
      <polyline
        points={points}
        fill="none"
        stroke={isUp ? "#00c853" : "#f44336"}
        strokeWidth="1.2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {/* MA50 line */}
      {ma50Y !== null && (
        <line
          x1={pad}
          y1={ma50Y}
          x2={W - pad}
          y2={ma50Y}
          stroke="#ffcc00"
          strokeWidth="0.8"
          strokeDasharray="3 2"
          opacity="0.7"
        />
      )}
      {/* Current price dot */}
      <circle cx={lastX} cy={cpY} r="2.5" fill={isUp ? "#00c853" : "#f44336"} />
      <circle cx={lastX} cy={lastY} r="1.5" fill="#ffffff" opacity="0.6" />
    </svg>
  );
};

// ─── Detail Panel ─────────────────────────────────────────────────────────────

const DetailPanel: React.FC<{
  stock: StockEntry;
  onClose: () => void;
  inWatchlist: boolean;
  isPinned: boolean;
  onToggleWatchlist: (sym: string) => void;
  onTogglePin: (sym: string) => void;
}> = ({ stock: s, onClose, inWatchlist, isPinned, onToggleWatchlist, onTogglePin }) => {
  const dd = getDrawdown(s);
  const vol = getVolatility(s);
  const probUp = getProbUp(s);
  const expPrice = getExpectedPrice(s);
  const worst = getWorstCase(s);
  const advice = getPositionAdvice(s);
  const btTrades = getBtTrades(s);
  const btWr = getBtWinRate(s);
  const btSharpe = getBtSharpe(s);

  const signalColor = SIGNAL_COLOR[s.signal] ?? "#607d8b";
  const scoreColor = SCORE_COLOR(s.score ?? 0);
  const riskLvl = (s.risk_level ?? "").toUpperCase();

  return (
    <div className="w-96 flex flex-col border-l border-border-primary bg-bg-panel overflow-y-auto shrink-0">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border-primary bg-bg-secondary shrink-0">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-mono font-bold text-text-primary">{s.symbol}</span>
            {s.group && (
              <span className="text-2xs font-mono px-1 border border-border-primary text-text-muted">{s.group}</span>
            )}
          </div>
          {s.sector && (
            <span className="text-2xs font-mono text-text-muted">{s.sector}</span>
          )}
        </div>
        <button
          onClick={() => onToggleWatchlist(s.symbol)}
          className="text-sm hover:scale-110 transition-transform"
          title={inWatchlist ? "Remove from watchlist" : "Add to watchlist"}
        >
          {inWatchlist ? "⭐" : "☆"}
        </button>
        <button
          onClick={() => onTogglePin(s.symbol)}
          className="text-sm hover:scale-110 transition-transform"
          title={isPinned ? "Unpin" : "Pin to top"}
        >
          <span style={{ opacity: isPinned ? 1 : 0.4 }}>📌</span>
        </button>
        <button
          onClick={onClose}
          className="text-text-muted hover:text-text-primary text-sm font-mono ml-1"
        >
          ✕
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {/* Signal card */}
        <div className="border border-border-primary bg-bg-secondary p-3">
          <div className="flex items-center justify-between mb-2">
            <span
              className="text-xs font-mono font-bold px-2 py-0.5"
              style={{ color: signalColor, backgroundColor: signalColor + "20", border: `1px solid ${signalColor}40` }}
            >
              {s.signal}
            </span>
            <span className="text-2xs font-mono text-text-muted">
              ₹{(s.price ?? 0).toFixed(2)}
              {s.live_price && s.day_change_pct !== undefined && (
                <span className="ml-1 font-bold" style={{ color: (s.day_change_pct ?? 0) >= 0 ? '#00c853' : '#f44336' }}>
                  {(s.day_change_pct ?? 0) >= 0 ? '+' : ''}{(s.day_change_pct ?? 0).toFixed(2)}%
                </span>
              )}
              {s.live_price && (
                <span className="ml-1 text-market-up opacity-70">●</span>
              )}
            </span>
          </div>
          <div className="mb-2">
            <div className="flex items-center justify-between mb-1">
              <span className="text-2xs font-mono text-text-muted">SCORE</span>
              <span className="text-2xs font-mono font-bold" style={{ color: scoreColor }}>{s.score ?? 0}/10</span>
            </div>
            <div className="w-full h-2 bg-bg-tertiary rounded-sm overflow-hidden">
              <div
                className="h-full rounded-sm transition-all"
                style={{ width: `${Math.min(100, ((s.score ?? 0) / 10) * 100)}%`, backgroundColor: scoreColor }}
              />
            </div>
          </div>
          {s.confidence !== undefined && (
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-2xs font-mono text-text-muted">CONFIDENCE</span>
                <span className="text-2xs font-mono font-bold text-accent-cyan">{(s.confidence ?? 0).toFixed(0)}%</span>
              </div>
              <div className="w-full h-1.5 bg-bg-tertiary rounded-sm overflow-hidden">
                <div
                  className="h-full rounded-sm"
                  style={{ width: `${Math.min(100, s.confidence ?? 0)}%`, backgroundColor: "#00d4ff" }}
                />
              </div>
            </div>
          )}
        </div>

        {/* Sparkline */}
        {s.sparkline && s.sparkline.length > 1 && (
          <div className="border border-border-primary bg-bg-secondary p-2">
            <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest mb-1">PRICE HISTORY</div>
            <SparklineSVG prices={s.sparkline} ma50={s.ma50} currentPrice={s.price} />
            <div className="flex items-center gap-3 mt-1">
              <span className="flex items-center gap-1 text-2xs font-mono text-text-muted">
                <span className="w-3 h-px bg-accent-yellow inline-block" style={{ borderTop: "1px dashed #ffcc00" }} />
                MA50
              </span>
              <span className="flex items-center gap-1 text-2xs font-mono text-text-muted">
                <span className="w-2 h-2 rounded-full bg-market-up inline-block" />
                Price
              </span>
            </div>
          </div>
        )}

        {/* Key Levels */}
        <div className="border border-border-primary bg-bg-secondary p-3">
          <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest mb-2">KEY LEVELS</div>
          <div className="grid grid-cols-2 gap-1">
            {s.w52_high !== undefined && (
              <Row label="52W HIGH" value={<span className="text-market-up">₹{(s.w52_high ?? 0).toFixed(2)}</span>} />
            )}
            {s.w52_low !== undefined && (
              <Row label="52W LOW" value={<span className="text-market-down">₹{(s.w52_low ?? 0).toFixed(2)}</span>} />
            )}
            {s.support !== undefined && (
              <Row label="SUPPORT" value={<span className="text-chart-put">₹{(s.support ?? 0).toFixed(2)}</span>} />
            )}
            {s.resistance !== undefined && (
              <Row label="RESISTANCE" value={<span className="text-chart-call">₹{(s.resistance ?? 0).toFixed(2)}</span>} />
            )}
            <Row label="MA50" value={`₹${(s.ma50 ?? 0).toFixed(2)}`} />
            <Row label="MA200" value={`₹${(s.ma200 ?? 0).toFixed(2)}`} />
          </div>
          {/* Price position bar */}
          {s.w52_low !== undefined && s.w52_high !== undefined && s.w52_high > s.w52_low && (
            <div className="mt-2">
              <div className="flex justify-between text-2xs font-mono text-text-muted mb-0.5">
                <span>52W LOW</span>
                <span>CURRENT</span>
                <span>52W HIGH</span>
              </div>
              <div className="relative w-full h-2 bg-bg-tertiary rounded-sm">
                <div
                  className="absolute top-0 h-full w-0.5 bg-accent-yellow rounded-sm"
                  style={{
                    left: `${Math.min(100, Math.max(0, ((s.price - (s.w52_low ?? 0)) / ((s.w52_high ?? s.price) - (s.w52_low ?? 0))) * 100)).toFixed(1)}%`,
                  }}
                />
              </div>
            </div>
          )}
        </div>

        {/* Strength */}
        <div className="border border-border-primary bg-bg-secondary p-3">
          <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest mb-2">STRENGTH</div>
          <Row
            label="RS vs NIFTY"
            value={
              <span style={{ color: (s.relative_strength ?? 0) >= 1.2 ? "#00c853" : (s.relative_strength ?? 0) >= 1.0 ? "#69f0ae" : "#f44336" }}>
                {(s.relative_strength ?? 0).toFixed(2)}
              </span>
            }
          />
          <Row label="ROC 1Y" value={<span style={{ color: (s.roc_252 ?? 0) >= 0 ? "#00c853" : "#f44336" }}>{(s.roc_252 ?? 0).toFixed(1)}%</span>} />
          {s.momentum && <Row label="MOMENTUM" value={s.momentum} />}
          {s.trend && <Row label="TREND" value={s.trend} />}
          {s.entry_type && (
            <Row
              label="ENTRY TYPE"
              value={
                <span
                  className="px-1 text-2xs font-mono"
                  style={{
                    color: ENTRY_COLOR[(s.entry_type ?? "NONE").toUpperCase()] ?? "#607d8b",
                    backgroundColor: (ENTRY_COLOR[(s.entry_type ?? "NONE").toUpperCase()] ?? "#607d8b") + "20",
                  }}
                >
                  {s.entry_type}
                </span>
              }
            />
          )}
        </div>

        {/* Risk */}
        <div className="border border-border-primary bg-bg-secondary p-3">
          <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest mb-2">RISK</div>
          <Row label="DRAWDOWN" value={<span className="text-market-down">{dd.toFixed(1)}%</span>} />
          <Row label="VOLATILITY" value={`${vol.toFixed(1)}%`} />
          <Row label="RISK LEVEL" value={<RiskDot level={riskLvl} />} />
          {s.risk?.vol_stable !== undefined && (
            <Row
              label="VOL STABLE"
              value={
                <span style={{ color: s.risk.vol_stable ? "#00c853" : "#ff9800" }}>
                  {s.risk.vol_stable ? "YES" : "NO"}
                </span>
              }
            />
          )}
        </div>

        {/* Monte Carlo */}
        {(s.monte_carlo || s.prob_up !== undefined) && (
          <div className="border border-border-primary bg-bg-secondary p-3">
            <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest mb-2">
              MONTE CARLO ({s.monte_carlo?.horizon_label ?? s.monte_carlo?.horizon_days ? `${s.monte_carlo.horizon_days}d` : '60d'})
            </div>
            <Row label="EXPECTED PRICE" value={`₹${expPrice.toFixed(2)}`} />
            <Row label="PROB UP"
              value={<span style={{ color: probUp >= 55 ? "#00c853" : probUp >= 45 ? "#ffcc00" : "#f44336" }}>{probUp.toFixed(1)}%</span>}
            />
            {s.monte_carlo?.prob_down !== undefined && (
              <Row label="PROB DOWN" value={<span className="text-market-down">{(s.monte_carlo.prob_down ?? 0).toFixed(1)}%</span>} />
            )}
            <Row label="WORST 5%" value={<span className="text-market-down">₹{worst.toFixed(2)}</span>} />
            {s.monte_carlo?.best_case_95pct !== undefined && (
              <Row label="BEST 95%" value={<span className="text-market-up">₹{(s.monte_carlo.best_case_95pct ?? 0).toFixed(2)}</span>} />
            )}
            <Row label="POSITION ADVICE"
              value={
                <span className="text-2xs font-mono font-bold"
                  style={{ color: advice === "REDUCE" ? "#f44336" : advice === "INCREASE" ? "#00c853" : "#ffcc00" }}>
                  {advice}
                </span>
              }
            />
          </div>
        )}

        {/* Investment Simulator */}
        <InvestmentSimulator symbol={s.symbol} currentPrice={s.price} mc={s.monte_carlo} />

        {/* Backtest */}
        {btTrades > 0 && (
          <div className="border border-border-primary bg-bg-secondary p-3">
            <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest mb-2">BACKTEST</div>
            <Row label="TOTAL TRADES" value={btTrades} />
            <Row
              label="WIN RATE"
              value={<span style={{ color: btWr >= 55 ? "#00c853" : btWr >= 45 ? "#ffcc00" : "#f44336" }}>{btWr.toFixed(1)}%</span>}
            />
            <Row
              label="SHARPE"
              value={<span style={{ color: btSharpe >= 1 ? "#00c853" : btSharpe >= 0 ? "#ffcc00" : "#f44336" }}>{btSharpe.toFixed(2)}</span>}
            />
            {s.backtest?.avg_return !== undefined && (
              <Row
                label="AVG RETURN"
                value={
                  <span style={{ color: (s.backtest.avg_return ?? 0) >= 0 ? "#00c853" : "#f44336" }}>
                    {(s.backtest.avg_return ?? 0).toFixed(2)}%
                  </span>
                }
              />
            )}
            {s.backtest?.max_drawdown !== undefined && (
              <Row label="MAX DD" value={<span className="text-market-down">{(s.backtest.max_drawdown ?? 0).toFixed(1)}%</span>} />
            )}
          </div>
        )}
      </div>
    </div>
  );
};

// ─── Stock Table ──────────────────────────────────────────────────────────────

const StockList: React.FC<{
  stocks: StockEntry[];
  pinnedSymbols: Set<string>;
  watchlistSymbols: Set<string>;
  selected: StockEntry | null;
  onSelect: (s: StockEntry) => void;
  onTogglePin: (sym: string) => void;
  onToggleWatchlist: (sym: string) => void;
}> = ({ stocks, pinnedSymbols, watchlistSymbols, selected, onSelect, onTogglePin, onToggleWatchlist }) => {
  return (
    <div className="flex-1 overflow-auto">
      <table className="w-full border-collapse text-2xs font-mono">
        <thead className="sticky top-0 z-10 bg-bg-secondary">
          <tr className="border-b border-border-primary">
            <th className="px-2 py-1.5 text-left text-text-muted font-normal w-8">#</th>
            <th className="px-2 py-1.5 text-left text-text-muted font-normal">SYMBOL</th>
            <th className="px-2 py-1.5 text-left text-text-muted font-normal hidden md:table-cell">GROUP</th>
            <th className="px-2 py-1.5 text-left text-text-muted font-normal hidden lg:table-cell">SECTOR</th>
            <th className="px-2 py-1.5 text-right text-text-muted font-normal">PRICE</th>
            <th className="px-2 py-1.5 text-left text-text-muted font-normal">SIGNAL</th>
            <th className="px-2 py-1.5 text-left text-text-muted font-normal">SCORE</th>
            <th className="px-2 py-1.5 text-right text-text-muted font-normal hidden sm:table-cell">RS</th>
            <th className="px-2 py-1.5 text-right text-text-muted font-normal hidden sm:table-cell">ROC 1Y</th>
            <th className="px-2 py-1.5 text-left text-text-muted font-normal">RISK</th>
            <th className="px-2 py-1.5 text-left text-text-muted font-normal hidden md:table-cell">ENTRY</th>
            <th className="px-2 py-1.5 text-right text-text-muted font-normal hidden xl:table-cell">TURNOVER</th>
            <th className="px-2 py-1.5 text-right text-text-muted font-normal hidden lg:table-cell">CONF%</th>
            <th className="px-2 py-1.5 text-right text-text-muted font-normal hidden xl:table-cell">P(UP)</th>
          </tr>
        </thead>
        <tbody>
          {stocks.map((s, idx) => {
            const isPinned = pinnedSymbols.has(s.symbol);
            const isWatched = watchlistSymbols.has(s.symbol);
            const isSelected = selected?.symbol === s.symbol;
            const signalColor = SIGNAL_COLOR[s.signal] ?? "#607d8b";
            const rs = s.relative_strength ?? 0;
            const rsColor = rs >= 1.2 ? "#00c853" : rs >= 1.0 ? "#69f0ae" : "#f44336";
            const roc = s.roc_252 ?? 0;
            const entryKey = (s.entry_type ?? "NONE").toUpperCase();
            const entryColor = ENTRY_COLOR[entryKey] ?? "#607d8b";
            const probUp = getProbUp(s);

            return (
              <tr
                key={s.symbol}
                onClick={() => onSelect(s)}
                className={`border-b border-border-secondary/40 cursor-pointer transition-colors group ${
                  isSelected ? "bg-accent-yellow/10" : "hover:bg-bg-hover"
                }`}
                style={{
                  backgroundColor: isSelected ? "rgba(255,204,0,0.1)" : rowBg(s.score ?? 0),
                  borderLeft: isPinned ? "2px solid #ffcc00" : "2px solid transparent",
                }}
              >
                {/* Rank */}
                <td className="px-2 py-1 text-text-muted w-8">
                  <div className="flex items-center gap-0.5">
                    <span>{idx + 1}</span>
                  </div>
                </td>

                {/* Symbol + actions */}
                <td className="px-2 py-1">
                  <div className="flex items-center gap-1">
                    <span className={`font-bold ${isSelected ? "text-accent-yellow" : "text-text-primary"}`}>
                      {s.symbol}
                    </span>
                    <button
                      onClick={(e) => { e.stopPropagation(); onTogglePin(s.symbol); }}
                      className="opacity-0 group-hover:opacity-100 transition-opacity text-xs"
                      title="Pin"
                    >
                      <span style={{ opacity: isPinned ? 1 : 0.5 }}>📌</span>
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); onToggleWatchlist(s.symbol); }}
                      className="opacity-0 group-hover:opacity-100 transition-opacity text-xs"
                      title="Watchlist"
                    >
                      {isWatched ? "⭐" : "☆"}
                    </button>
                  </div>
                </td>

                {/* Group */}
                <td className="px-2 py-1 text-text-muted hidden md:table-cell">{s.group ?? "—"}</td>

                {/* Sector */}
                <td className="px-2 py-1 text-text-muted hidden lg:table-cell truncate max-w-24">{s.sector ?? "—"}</td>

                {/* Price */}
                <td className="px-2 py-1 text-right text-text-primary tabular-nums">
                  <div className="flex flex-col items-end">
                    <span>₹{(s.price ?? 0).toFixed(2)}</span>
                    {s.live_price && s.day_change_pct !== undefined && (
                      <span className="text-2xs" style={{ color: (s.day_change_pct ?? 0) >= 0 ? '#00c853' : '#f44336' }}>
                        {(s.day_change_pct ?? 0) >= 0 ? '+' : ''}{(s.day_change_pct ?? 0).toFixed(2)}%
                      </span>
                    )}
                  </div>
                </td>

                {/* Signal */}
                <td className="px-2 py-1">
                  <div className="flex flex-col gap-0.5">
                    <span
                      className="px-1 py-0.5 text-2xs font-mono font-bold"
                      style={{ color: signalColor, backgroundColor: signalColor + "18" }}
                    >
                      {s.signal}
                    </span>
                    {s.smart_label && s.smart_label !== s.signal && (
                      <span className="text-2xs font-mono opacity-60" style={{ color: signalColor }}>
                        {s.smart_label}
                      </span>
                    )}
                  </div>
                </td>

                {/* Score */}
                <td className="px-2 py-1">
                  <ScoreBar score={s.score ?? 0} />
                </td>

                {/* RS */}
                <td className="px-2 py-1 text-right tabular-nums hidden sm:table-cell" style={{ color: rsColor }}>
                  {rs.toFixed(2)}
                </td>

                {/* ROC 1Y */}
                <td
                  className="px-2 py-1 text-right tabular-nums hidden sm:table-cell"
                  style={{ color: roc >= 0 ? "#00c853" : "#f44336" }}
                >
                  {roc >= 0 ? "+" : ""}{roc.toFixed(1)}%
                </td>

                {/* Risk */}
                <td className="px-2 py-1">
                  <RiskDot level={s.risk_level} />
                </td>

                {/* Entry */}
                <td className="px-2 py-1 hidden md:table-cell">
                  {s.entry_detail && s.entry_detail !== "NONE" ? (
                    <span className="px-1 py-0.5 text-2xs font-mono"
                      style={{
                        color: s.entry_detail.includes("BREAKOUT") ? "#00c853" :
                               s.entry_detail.includes("PULLBACK") ? "#2196f3" : "#607d8b",
                        backgroundColor: (s.entry_detail.includes("BREAKOUT") ? "#00c853" :
                                          s.entry_detail.includes("PULLBACK") ? "#2196f3" : "#607d8b") + "18",
                      }}>
                      {s.entry_detail.replace(" (IDEAL)", "✓").replace(" (FRESH)", "✓").replace(" (WEAK)", "~").replace(" (EXTENDED)", "!")}
                    </span>
                  ) : s.entry_type && s.entry_type !== "NONE" ? (
                    <span className="px-1 py-0.5 text-2xs font-mono"
                      style={{ color: ENTRY_COLOR[(s.entry_type ?? "NONE").toUpperCase()] ?? "#607d8b",
                               backgroundColor: (ENTRY_COLOR[(s.entry_type ?? "NONE").toUpperCase()] ?? "#607d8b") + "18" }}>
                      {s.entry_type}
                    </span>
                  ) : (
                    <span className="text-text-muted">—</span>
                  )}
                </td>

                {/* Liquidity */}
                <td className="px-2 py-1 hidden xl:table-cell">
                  {s.is_liquid === false ? (
                    <span className="text-2xs font-mono text-market-down">LOW LIQ</span>
                  ) : s.avg_turnover_cr != null && s.avg_turnover_cr > 0 ? (
                    <span className="text-2xs font-mono text-text-muted">
                      {s.avg_turnover_cr >= 1000 ? `${(s.avg_turnover_cr/1000).toFixed(1)}KCr` : `${s.avg_turnover_cr.toFixed(0)}Cr`}
                    </span>
                  ) : (
                    <span className="text-text-muted">—</span>
                  )}
                </td>

                {/* Confidence */}
                <td className="px-2 py-1 text-right tabular-nums text-accent-cyan hidden lg:table-cell">
                  {s.confidence !== undefined ? `${(s.confidence ?? 0).toFixed(0)}%` : "—"}
                </td>

                {/* P(UP) */}
                <td
                  className="px-2 py-1 text-right tabular-nums hidden xl:table-cell"
                  style={{ color: probUp >= 55 ? "#00c853" : probUp >= 45 ? "#ffcc00" : "#f44336" }}
                >
                  {probUp.toFixed(0)}%
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {stocks.length === 0 && (
        <div className="flex items-center justify-center h-32 text-text-muted font-mono text-xs">
          NO STOCKS MATCH CURRENT FILTERS
        </div>
      )}
    </div>
  );
};

// ─── Investment Simulator ─────────────────────────────────────────────────────

interface SimResult {
  investment: number;
  horizon_days: number;
  shares: number;
  expected_value: number;
  best_case: number;
  worst_case: number;
  prob_profit: number;
  expected_return: number;
  best_return: number;
  worst_return: number;
}

const HORIZONS = [
  { label: "3M",  days: 63  },
  { label: "6M",  days: 126 },
  { label: "1Y",  days: 252 },
];

const InvestmentSimulator: React.FC<{
  symbol: string;
  currentPrice: number;
  mc?: StockMonteCarlo;
}> = ({ symbol, currentPrice, mc }) => {
  const [investment, setInvestment] = useState(100000);
  const [horizon, setHorizon]       = useState(126);
  const [result, setResult]         = useState<SimResult | null>(null);
  const [loading, setLoading]       = useState(false);

  const run = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.simulateStockInvestment(symbol, investment, horizon) as SimResult;
      setResult(r);
    } catch {
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, [symbol, investment, horizon]);

  const fmtINR = (v: number) => {
    if (v >= 10000000) return `₹${(v / 10000000).toFixed(2)}Cr`;
    if (v >= 100000)   return `₹${(v / 100000).toFixed(2)}L`;
    return `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
  };

  return (
    <div className="border border-border-primary bg-bg-secondary p-3">
      <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest mb-2">💰 INVESTMENT SIMULATOR</div>

      {/* Inputs */}
      <div className="space-y-2 mb-3">
        <div className="flex items-center gap-2">
          <span className="text-2xs font-mono text-text-muted w-20">INVEST</span>
          <div className="flex gap-1 flex-wrap">
            {[10000, 50000, 100000, 500000].map(v => (
              <button key={v} onClick={() => setInvestment(v)}
                className="px-1.5 py-0.5 text-2xs font-mono transition-all"
                style={{
                  color: investment === v ? "#0a0a0a" : "#a0a0a0",
                  backgroundColor: investment === v ? "#ffcc00" : "transparent",
                  border: `1px solid ${investment === v ? "#ffcc00" : "#2a2a2a"}`,
                }}>
                {v >= 100000 ? `${v/100000}L` : `${v/1000}K`}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-2xs font-mono text-text-muted w-20">HORIZON</span>
          <div className="flex gap-1">
            {HORIZONS.map(h => (
              <button key={h.days} onClick={() => setHorizon(h.days)}
                className="px-1.5 py-0.5 text-2xs font-mono transition-all"
                style={{
                  color: horizon === h.days ? "#0a0a0a" : "#a0a0a0",
                  backgroundColor: horizon === h.days ? "#ffcc00" : "transparent",
                  border: `1px solid ${horizon === h.days ? "#ffcc00" : "#2a2a2a"}`,
                }}>
                {h.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <button onClick={run} disabled={loading}
        className="w-full py-1.5 text-2xs font-mono font-bold transition-all mb-3"
        style={{
          backgroundColor: loading ? "#2a2a2a" : "#ffcc00",
          color: loading ? "#606060" : "#0a0a0a",
        }}>
        {loading ? "SIMULATING..." : "▶ RUN SIMULATION"}
      </button>

      {result && (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between py-1 border-b border-border-secondary/30">
            <span className="text-2xs font-mono text-text-muted">INVESTED</span>
            <span className="text-2xs font-mono text-text-primary">{fmtINR(result.investment)}</span>
          </div>
          <div className="flex items-center justify-between py-1 border-b border-border-secondary/30">
            <span className="text-2xs font-mono text-text-muted">SHARES</span>
            <span className="text-2xs font-mono text-text-primary">{result.shares.toFixed(2)}</span>
          </div>
          <div className="flex items-center justify-between py-1 border-b border-border-secondary/30">
            <span className="text-2xs font-mono text-text-muted">EXPECTED VALUE</span>
            <span className="text-2xs font-mono font-bold text-accent-yellow">
              {fmtINR(result.expected_value)}
              <span className="ml-1 text-2xs" style={{ color: result.expected_return >= 0 ? "#00c853" : "#f44336" }}>
                ({result.expected_return >= 0 ? "+" : ""}{result.expected_return.toFixed(1)}%)
              </span>
            </span>
          </div>
          <div className="flex items-center justify-between py-1 border-b border-border-secondary/30">
            <span className="text-2xs font-mono text-text-muted">BEST CASE (95%)</span>
            <span className="text-2xs font-mono font-bold text-market-up">
              {fmtINR(result.best_case)}
              <span className="ml-1 text-2xs text-market-up">(+{result.best_return.toFixed(1)}%)</span>
            </span>
          </div>
          <div className="flex items-center justify-between py-1 border-b border-border-secondary/30">
            <span className="text-2xs font-mono text-text-muted">WORST CASE (5%)</span>
            <span className="text-2xs font-mono font-bold text-market-down">
              {fmtINR(result.worst_case)}
              <span className="ml-1 text-2xs text-market-down">({result.worst_return.toFixed(1)}%)</span>
            </span>
          </div>
          {/* Probability bar */}
          <div className="pt-1">
            <div className="flex items-center justify-between mb-1">
              <span className="text-2xs font-mono text-text-muted">PROB OF PROFIT</span>
              <span className="text-2xs font-mono font-bold"
                style={{ color: result.prob_profit >= 60 ? "#00c853" : result.prob_profit >= 45 ? "#ffcc00" : "#f44336" }}>
                {result.prob_profit.toFixed(1)}%
              </span>
            </div>
            <div className="w-full h-2 bg-bg-tertiary rounded-sm overflow-hidden">
              <div className="h-full rounded-sm transition-all"
                style={{
                  width: `${result.prob_profit}%`,
                  backgroundColor: result.prob_profit >= 60 ? "#00c853" : result.prob_profit >= 45 ? "#ffcc00" : "#f44336",
                }} />
            </div>
          </div>
          <div className="text-2xs text-text-muted text-center pt-1 opacity-50">
            3,000 GBM simulations · {HORIZONS.find(h => h.days === horizon)?.label} horizon
          </div>
        </div>
      )}
    </div>
  );
};

// ─── Fundamentals Panel ──────────────────────────────────────────────────────

const FundamentalsPanel: React.FC<{
  symbol: string;
  fundamentals: Fundamentals | null;
  loading: boolean;
}> = ({ symbol, fundamentals, loading }) => {
  if (loading) return (
    <div className="flex items-center justify-center h-32 gap-2 font-mono text-2xs text-text-muted">
      <div className="w-2 h-2 rounded-full bg-accent-yellow animate-pulse" />
      FETCHING FUNDAMENTALS...
    </div>
  );

  if (!fundamentals || fundamentals.status === "ERROR") return (
    <div className="flex flex-col items-center justify-center h-32 gap-2 font-mono text-2xs text-text-muted p-4 text-center">
      <span>⚠</span>
      <span>{fundamentals?.message || "No fundamental data available"}</span>
      <span className="text-2xs opacity-60">Data sourced from Screener.in</span>
    </div>
  );

  const r = fundamentals.ratios ?? {};
  const g = fundamentals.growth ?? {};
  const info = fundamentals.info ?? {};
  const quarters = fundamentals.quarterly ?? [];
  const years = fundamentals.annual ?? [];

  const fmtCr = (v: number | null | undefined) => {
    if (v == null) return "—";
    if (v >= 100000) return `₹${(v / 100000).toFixed(1)}L Cr`;
    if (v >= 1000)   return `₹${(v / 1000).toFixed(1)}K Cr`;
    return `₹${v.toFixed(0)} Cr`;
  };

  const fmtNum = (v: number | null | undefined, d = 2) =>
    v == null ? "—" : v.toFixed(d);

  const fmtPct = (v: number | null | undefined) =>
    v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;

  const gc = (v: number | null | undefined) =>
    v == null ? "text-text-muted" : v >= 0 ? "text-market-up" : "text-market-down";

  return (
    <div className="p-3 space-y-3 font-mono">
      {/* Source badge */}
      <div className="flex items-center justify-between">
        <span className="text-2xs text-text-muted">Source: Screener.in</span>
        {fundamentals.fetched_at && (
          <span className="text-2xs text-text-muted opacity-50">
            {new Date(fundamentals.fetched_at * 1000).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: false })}
          </span>
        )}
      </div>

      {/* Company info */}
      {info.name && (
        <div className="border border-border-primary bg-bg-secondary p-3">
          <div className="text-xs font-bold text-text-primary">{info.name}</div>
          {(info.sector || info.industry) && (
            <div className="text-2xs text-text-muted mt-0.5">
              {[info.sector, info.industry].filter(Boolean).join(" · ")}
            </div>
          )}
          {info.description && (
            <div className="text-2xs text-text-muted mt-1.5 leading-relaxed opacity-70 line-clamp-3">
              {info.description}
            </div>
          )}
        </div>
      )}

      {/* Key Ratios */}
      <div className="border border-border-primary bg-bg-secondary p-3">
        <div className="text-2xs font-bold text-accent-yellow tracking-widest mb-2">KEY RATIOS</div>
        <div className="space-y-0.5">
          <FRow label="P/E Ratio"
            value={fmtNum(r.pe_ratio, 1)}
            color={r.pe_ratio != null && r.pe_ratio < 25 ? "text-market-up" : r.pe_ratio != null && r.pe_ratio > 50 ? "text-market-down" : "text-text-secondary"} />
          <FRow label="P/B Ratio"     value={fmtNum(r.pb_ratio, 2)} />
          <FRow label="ROCE"
            value={r.roce != null ? `${fmtNum(r.roce, 1)}%` : "—"}
            color={r.roce != null && r.roce >= 15 ? "text-market-up" : r.roce != null && r.roce < 10 ? "text-market-down" : "text-text-secondary"} />
          <FRow label="ROE"
            value={r.roe != null ? `${fmtNum(r.roe, 1)}%` : "—"}
            color={r.roe != null && r.roe >= 15 ? "text-market-up" : r.roe != null && r.roe < 10 ? "text-market-down" : "text-text-secondary"} />
          <FRow label="Debt / Equity"
            value={fmtNum(r.debt_equity, 2)}
            color={r.debt_equity != null && r.debt_equity > 1 ? "text-market-down" : r.debt_equity != null ? "text-market-up" : "text-text-secondary"} />
          <FRow label="Dividend Yield"
            value={r.dividend_yield != null ? `${fmtNum(r.dividend_yield, 2)}%` : "—"} />
          {r.market_cap_cr != null && (
            <FRow label="Market Cap" value={fmtCr(r.market_cap_cr)} />
          )}
          {r.book_value != null && (
            <FRow label="Book Value" value={`₹${fmtNum(r.book_value, 0)}`} />
          )}
        </div>
      </div>

      {/* Growth */}
      <div className="border border-border-primary bg-bg-secondary p-3">
        <div className="text-2xs font-bold text-accent-yellow tracking-widest mb-2">GROWTH</div>
        <div className="space-y-0.5">
          <FRow label="Revenue Growth YoY"  value={fmtPct(g.revenue_growth_yoy)}  color={gc(g.revenue_growth_yoy)} />
          <FRow label="Profit Growth YoY"   value={fmtPct(g.profit_growth_yoy)}   color={gc(g.profit_growth_yoy)} />
          {g.revenue_cagr_3y != null && (
            <FRow label="Revenue CAGR 3Y"   value={fmtPct(g.revenue_cagr_3y)}     color={gc(g.revenue_cagr_3y)} />
          )}
          {g.revenue_cagr_5y != null && (
            <FRow label="Revenue CAGR 5Y"   value={fmtPct(g.revenue_cagr_5y)}     color={gc(g.revenue_cagr_5y)} />
          )}
          {g.profit_cagr_3y != null && (
            <FRow label="Profit CAGR 3Y"    value={fmtPct(g.profit_cagr_3y)}      color={gc(g.profit_cagr_3y)} />
          )}
          {g.profit_cagr_5y != null && (
            <FRow label="Profit CAGR 5Y"    value={fmtPct(g.profit_cagr_5y)}      color={gc(g.profit_cagr_5y)} />
          )}
        </div>
      </div>

      {/* Quarterly Financials */}
      {quarters.length > 0 && (
        <div className="border border-border-primary bg-bg-secondary p-3">
          <div className="text-2xs font-bold text-accent-yellow tracking-widest mb-2">QUARTERLY (₹ Cr)</div>
          <div className="overflow-x-auto">
            <table className="w-full text-2xs">
              <thead>
                <tr className="border-b border-border-secondary/40">
                  <th className="text-left text-text-muted font-normal py-1 pr-2">QTR</th>
                  <th className="text-right text-text-muted font-normal py-1 pr-2">REVENUE</th>
                  <th className="text-right text-text-muted font-normal py-1 pr-2">NET PROFIT</th>
                  <th className="text-right text-text-muted font-normal py-1">OPM%</th>
                </tr>
              </thead>
              <tbody>
                {[...quarters].reverse().slice(0, 6).map((q, i) => (
                  <tr key={i} className="border-b border-border-secondary/20">
                    <td className="py-1 pr-2 text-text-muted">{q.period ?? "—"}</td>
                    <td className="py-1 pr-2 text-right text-text-primary tabular-nums">{fmtCr(q.revenue)}</td>
                    <td className={`py-1 pr-2 text-right tabular-nums ${q.net_profit != null && q.net_profit >= 0 ? "text-market-up" : "text-market-down"}`}>
                      {fmtCr(q.net_profit)}
                    </td>
                    <td className="py-1 text-right text-text-secondary tabular-nums">
                      {q.opm_pct != null ? `${q.opm_pct.toFixed(0)}%` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Annual Financials */}
      {years.length > 0 && (
        <div className="border border-border-primary bg-bg-secondary p-3">
          <div className="text-2xs font-bold text-accent-yellow tracking-widest mb-2">ANNUAL (₹ Cr)</div>
          <div className="overflow-x-auto">
            <table className="w-full text-2xs">
              <thead>
                <tr className="border-b border-border-secondary/40">
                  <th className="text-left text-text-muted font-normal py-1 pr-2">YEAR</th>
                  <th className="text-right text-text-muted font-normal py-1 pr-2">REVENUE</th>
                  <th className="text-right text-text-muted font-normal py-1 pr-2">NET PROFIT</th>
                  <th className="text-right text-text-muted font-normal py-1">OPM%</th>
                </tr>
              </thead>
              <tbody>
                {[...years].reverse().slice(0, 6).map((y, i) => (
                  <tr key={i} className="border-b border-border-secondary/20">
                    <td className="py-1 pr-2 text-text-muted">{y.year ?? "—"}</td>
                    <td className="py-1 pr-2 text-right text-text-primary tabular-nums">{fmtCr(y.revenue)}</td>
                    <td className={`py-1 pr-2 text-right tabular-nums ${y.net_profit != null && y.net_profit >= 0 ? "text-market-up" : "text-market-down"}`}>
                      {fmtCr(y.net_profit)}
                    </td>
                    <td className="py-1 text-right text-text-secondary tabular-nums">
                      {y.opm_pct != null ? `${y.opm_pct.toFixed(0)}%` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="text-2xs text-text-muted text-center pb-2 opacity-40">
        Screener.in · Cached 24h · ₹ Crores
      </div>
    </div>
  );
};

const FRow: React.FC<{ label: string; value: string; color?: string }> = ({
  label, value, color = "text-text-secondary"
}) => (
  <div className="flex items-center justify-between py-0.5">
    <span className="text-2xs text-text-muted">{label}</span>
    <span className={`text-2xs font-bold ${color}`}>{value}</span>
  </div>
);

// ─── Decision Panel ───────────────────────────────────────────────────────────

const DecisionPanel: React.FC<{ stock: StockEntry }> = ({ stock: s }) => {
  const [capital, setCapital] = useState(500000);
  const price       = s.price ?? 0;
  const stopLoss    = s.stop_loss_price  ?? (price * 0.92);
  const target      = s.target_price     ?? (price * 1.15);
  const rrRatio     = s.risk_reward_ratio ?? 2.0;
  const atrStop     = s.atr_stop_loss_pct ?? 8.0;
  const atrTarget   = s.atr_target_pct    ?? 15.0;
  const probUp      = s.monte_carlo?.prob_up ?? 50;
  const smartLabel  = s.smart_label ?? s.signal;
  const adjustments = s.adjustments ?? [];
  const buyOk       = s.buy_conditions_met ?? false;
  const riskAdj     = s.risk_adj_score ?? s.score;
  const holdPeriod  = s.recommended_hold ?? "—";
  const holdConf    = s.hold_confidence  ?? "MEDIUM";

  // Position sizing: risk 2% of capital
  const riskAmount   = capital * 0.02;
  const riskPerShare = price - stopLoss;
  const sharesByRisk = riskPerShare > 0 ? Math.floor(riskAmount / riskPerShare) : 0;
  const invested     = sharesByRisk * price;
  const allocPct     = capital > 0 ? (invested / capital * 100).toFixed(1) : "0";

  // Expected P&L
  const expectedGain = sharesByRisk * (target - price);
  const expectedLoss = sharesByRisk * (price - stopLoss);

  const fmtINR = (v: number) => {
    if (v >= 10000000) return `₹${(v/10000000).toFixed(2)}Cr`;
    if (v >= 100000)   return `₹${(v/100000).toFixed(2)}L`;
    return `₹${Math.round(v).toLocaleString("en-IN")}`;
  };

  const signalColor = buyOk ? "#00c853" : s.score >= 6 ? "#ffcc00" : "#607d8b";

  return (
    <div className="p-3 space-y-3 font-mono">

      {/* Smart Label + Signal */}
      <div className="border border-border-primary bg-bg-secondary p-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-bold px-2 py-0.5"
            style={{ color: signalColor, backgroundColor: signalColor + "20", border: `1px solid ${signalColor}40` }}>
            {smartLabel}
          </span>
          <div className="text-right">
            <div className="text-2xs text-text-muted">RISK-ADJ SCORE</div>
            <div className="text-sm font-bold" style={{ color: riskAdj >= 7 ? "#00c853" : riskAdj >= 5 ? "#ffcc00" : "#f44336" }}>
              {typeof riskAdj === 'number' ? riskAdj.toFixed(1) : riskAdj}/10
            </div>
          </div>
        </div>

        {/* Buy conditions checklist */}
        <div className="space-y-0.5">
          {[
            { label: "Score ≥ 8",          ok: (s.score ?? 0) >= 8 },
            { label: "Prob Up > 70%",       ok: probUp > 70 },
            { label: "Trend aligned",       ok: s.buy_conditions_met ?? false },
            { label: "Not overbought",      ok: !s.overbought },
            { label: "Liquid (>5Cr/day)",   ok: s.is_liquid !== false },
          ].map(({ label, ok }) => (
            <div key={label} className="flex items-center gap-2">
              <span style={{ color: ok ? "#00c853" : "#f44336" }}>{ok ? "✓" : "✗"}</span>
              <span className="text-2xs text-text-muted">{label}</span>
            </div>
          ))}
        </div>

        {/* Adjustments applied */}
        {adjustments.length > 0 && (
          <div className="mt-2 pt-2 border-t border-border-secondary/30">
            <div className="text-2xs text-text-muted mb-1">SCORE ADJUSTMENTS</div>
            {adjustments.map((adj, i) => (
              <div key={i} className="text-2xs text-market-down">{adj.replace(":-", " → -")}</div>
            ))}
          </div>
        )}
      </div>

      {/* Entry / Exit levels */}
      <div className="border border-border-primary bg-bg-secondary p-3">
        <div className="text-2xs font-bold text-accent-yellow tracking-widest mb-2">ENTRY / EXIT LEVELS</div>
        <Row label="ENTRY PRICE"  value={`₹${price.toFixed(2)}`} />
        <Row label="STOP LOSS"    value={
          <span className="text-market-down">₹{stopLoss.toFixed(2)} <span className="opacity-60">(-{atrStop.toFixed(1)}%)</span></span>
        } />
        <Row label="TARGET"       value={
          <span className="text-market-up">₹{target.toFixed(2)} <span className="opacity-60">(+{atrTarget.toFixed(1)}%)</span></span>
        } />
        <Row label="RISK/REWARD"  value={
          <span style={{ color: rrRatio >= 2 ? "#00c853" : rrRatio >= 1.5 ? "#ffcc00" : "#f44336" }}>
            1 : {rrRatio.toFixed(1)}
          </span>
        } />
        <Row label="PROB UP (MC)" value={
          <span style={{ color: probUp >= 70 ? "#00c853" : probUp >= 55 ? "#ffcc00" : "#f44336" }}>
            {probUp.toFixed(1)}%
          </span>
        } />
      </div>

      {/* Position sizing */}
      <div className="border border-border-primary bg-bg-secondary p-3">
        <div className="text-2xs font-bold text-accent-yellow tracking-widest mb-2">POSITION SIZING (2% RISK RULE)</div>
        <div className="flex items-center gap-2 mb-2">
          <span className="text-2xs text-text-muted w-16">CAPITAL</span>
          <div className="flex gap-1">
            {[100000, 500000, 1000000, 5000000].map(v => (
              <button key={v} onClick={() => setCapital(v)}
                className="px-1.5 py-0.5 text-2xs font-mono transition-all"
                style={{
                  color: capital === v ? "#0a0a0a" : "#a0a0a0",
                  backgroundColor: capital === v ? "#ffcc00" : "transparent",
                  border: `1px solid ${capital === v ? "#ffcc00" : "#2a2a2a"}`,
                }}>
                {v >= 1000000 ? `${v/100000}L` : `${v/1000}K`}
              </button>
            ))}
          </div>
        </div>
        <Row label="RISK AMOUNT (2%)" value={fmtINR(riskAmount)} />
        <Row label="SHARES"           value={sharesByRisk.toString()} />
        <Row label="INVESTED"         value={`${fmtINR(invested)} (${allocPct}%)`} />
        <Row label="EXPECTED GAIN"    value={<span className="text-market-up">{fmtINR(expectedGain)}</span>} />
        <Row label="MAX LOSS"         value={<span className="text-market-down">{fmtINR(expectedLoss)}</span>} />
      </div>

      {/* Time horizon */}
      <div className="border border-border-primary bg-bg-secondary p-3">
        <div className="text-2xs font-bold text-accent-yellow tracking-widest mb-2">TIME HORIZON</div>
        <Row label="RECOMMENDED HOLD" value={
          <span style={{ color: holdConf === "HIGH" ? "#00c853" : holdConf === "MEDIUM" ? "#ffcc00" : "#607d8b" }}>
            {holdPeriod}
          </span>
        } />
        <Row label="CONFIDENCE"       value={holdConf} />
        <Row label="TIME EXIT"        value="120 days max" />
        <div className="mt-2 pt-2 border-t border-border-secondary/30 text-2xs text-text-muted">
          Exit if: price hits stop loss, target reached, 120 days elapsed, or score drops below 5.
        </div>
      </div>

      {/* Momentum context */}
      <div className="border border-border-primary bg-bg-secondary p-3">
        <div className="text-2xs font-bold text-accent-yellow tracking-widest mb-2">MOMENTUM</div>
        <Row label="1Y ROC"  value={
          <span style={{ color: (s.roc_252 ?? 0) >= 0 ? "#00c853" : "#f44336" }}>
            {(s.roc_252 ?? 0) >= 0 ? "+" : ""}{(s.roc_252 ?? 0).toFixed(1)}%
          </span>
        } />
        {s.roc_63 !== undefined && (
          <Row label="3M ROC" value={
            <span style={{ color: (s.roc_63 ?? 0) >= 0 ? "#00c853" : "#f44336" }}>
              {(s.roc_63 ?? 0) >= 0 ? "+" : ""}{(s.roc_63 ?? 0).toFixed(1)}%
            </span>
          } />
        )}
        {s.roc_21 !== undefined && (
          <Row label="1M ROC" value={
            <span style={{ color: (s.roc_21 ?? 0) >= 0 ? "#00c853" : "#f44336" }}>
              {(s.roc_21 ?? 0) >= 0 ? "+" : ""}{(s.roc_21 ?? 0).toFixed(1)}%
            </span>
          } />
        )}
        <Row label="RS vs NIFTY" value={
          <span style={{ color: (s.relative_strength ?? 1) >= 1.1 ? "#00c853" : (s.relative_strength ?? 1) >= 1 ? "#ffcc00" : "#f44336" }}>
            {(s.relative_strength ?? 1).toFixed(2)}x
          </span>
        } />
        {s.overbought && (
          <div className="mt-1 text-2xs text-market-down font-bold">⚠ OVERBOUGHT — late entry risk</div>
        )}
        {s.oversold && (
          <div className="mt-1 text-2xs text-market-up font-bold">↓ OVERSOLD — potential reversal</div>
        )}
      </div>

      <div className="text-2xs text-text-muted text-center pb-2 opacity-40">
        Rule-based system · Not financial advice · Always use stop loss
      </div>
    </div>
  );
};

// ─── Main Component ───────────────────────────────────────────────────────────

export const QuantScreenerTab: React.FC = () => {
  const [data, setData] = useState<LongTermResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<StockEntry | null>(null);
  const [detailView, setDetailView] = useState<"quant" | "decision" | "fundamentals">("quant");
  const [fundamentals, setFundamentals] = useState<Fundamentals | null>(null);
  const [fundLoading, setFundLoading] = useState(false);
  const [minScore, setMinScore] = useState(5);
  const [lastUpdated, setLastUpdated] = useState<string>("");
  const [sortBy, setSortBy] = useState<"score" | "roc" | "rs" | "prob">("score");
  const [filterGroup, setFilterGroup] = useState("ALL");
  const [filterSector, setFilterSector] = useState("ALL");
  const [filterRisk, setFilterRisk] = useState("ALL");
  const [maxDrawdown, setMaxDrawdown] = useState(30);
  const [watchlist, setWatchlist] = useState<Set<string>>(new Set());
  const [pinned, setPinned] = useState<Set<string>>(new Set());
  // Search with debounce
  const [searchInput, setSearchInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");

  // Debounce search — 250ms delay
  useEffect(() => {
    const t = setTimeout(() => setSearchQuery(searchInput.trim().toUpperCase()), 250);
    return () => clearTimeout(t);
  }, [searchInput]);

  // Live prices — polled every 30s independently from the main data fetch
  // Backend fetches from Dhan every 30s and caches in Redis
  // This keeps prices fresh without re-fetching all screener data
  const [livePrices, setLivePrices] = useState<Record<string, {
    ltp: number; day_change: number; day_change_pct: number;
    intraday_change_pct: number; vwap: number; volume: number;
    range_position: number; buy_pressure: number;
    open: number; high: number; low: number;
    upper_circuit: number; lower_circuit: number;
    w52_high_live: number; w52_low_live: number;
  }>>({});
  const [liveAvailable, setLiveAvailable] = useState(false);
  // Stock prices come from REST batch only — no WS for stocks

  useEffect(() => {
    const fetchLive = async () => {
      try {
        const r = await api.getLiveStockPrices();
        if (r.available && r.prices && Object.keys(r.prices).length > 0) {
          setLivePrices(r.prices);
          setLiveAvailable(true);
        }
      } catch {}
    };
    fetchLive();
    const t = setInterval(fetchLive, 30000);
    return () => clearInterval(t);
  }, []);

  const fetchData = useCallback(async () => {
    try {
      const res = await api.getLongTermStocks(minScore) as LongTermResult;
      setData(res);
      if (res.last_updated) setLastUpdated(res.last_updated);
    } catch {
      // keep existing data on error
    } finally {
      setLoading(false);
    }
  }, [minScore]);

  useEffect(() => {
    setLoading(true);
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Fetch fundamentals when stock is selected and fundamentals tab is active
  useEffect(() => {
    if (!selected || detailView !== "fundamentals") return;
    setFundLoading(true);
    setFundamentals(null);
    api.getStockFundamentals(selected.symbol)
      .then((f: unknown) => setFundamentals(f as Fundamentals))
      .catch(() => setFundamentals({ symbol: selected.symbol, status: "ERROR", message: "Failed to fetch" }))
      .finally(() => setFundLoading(false));
  }, [selected, detailView]);

  const stocks: StockEntry[] = useMemo(() => {
    const base = data?.stocks ?? [];
    // Merge live prices from REST batch (every 30s) — no WS for stocks
    if (!liveAvailable || Object.keys(livePrices).length === 0) return base;
    return base.map(s => {
      const lp = livePrices[s.symbol];
      if (!lp || lp.ltp <= 0) return s;
      return {
        ...s,
        price:               lp.ltp,
        live_price:          true,
        day_change:          lp.day_change,
        day_change_pct:      lp.day_change_pct,
        intraday_change_pct: lp.intraday_change_pct,
        range_position:      lp.range_position,
        live_open:           lp.open,
        live_high:           lp.high,
        live_low:            lp.low,
      };
    });
  }, [data?.stocks, livePrices, liveAvailable]);
  const insights: MarketInsights = data?.insights ?? {};
  const topPicks: TopPick[] = data?.top_picks ?? [];
  const marketCtx: MarketContext = data?.market_context ?? {};
  const pipelineStatus: PipelineStatus | undefined = data?.pipeline_status;
  const dbStats: DbStats = data?.db_stats ?? {};

  // ── Derived data ────────────────────────────────────────────────────────────

  const allGroups = useMemo(() => {
    const groups = new Set<string>();
    stocks.forEach(s => { if (s.group) groups.add(s.group); });
    return Array.from(groups).sort();
  }, [stocks]);

  const allSectors = useMemo(() => {
    const sectors = new Set<string>();
    stocks.forEach(s => { if (s.sector) sectors.add(s.sector); });
    return Array.from(sectors).sort();
  }, [stocks]);

  const filteredStocks = useMemo(() => {
    let list = [...stocks];

    // Symbol / sector / group text search
    if (searchQuery) {
      list = list.filter(s =>
        s.symbol.toUpperCase().includes(searchQuery) ||
        (s.sector ?? "").toUpperCase().includes(searchQuery) ||
        (s.group ?? "").toUpperCase().includes(searchQuery)
      );
    }

    if (filterGroup !== "ALL") {
      list = list.filter(s => s.group === filterGroup);
    }
    if (filterSector !== "ALL") {
      list = list.filter(s => s.sector === filterSector);
    }
    if (filterRisk !== "ALL") {
      list = list.filter(s => (s.risk_level ?? "").toUpperCase() === filterRisk);
    }
    list = list.filter(s => getDrawdown(s) <= maxDrawdown);

    list.sort((a, b) => {
      switch (sortBy) {
        case "roc": return (b.roc_252 ?? 0) - (a.roc_252 ?? 0);
        case "rs": return (b.relative_strength ?? 0) - (a.relative_strength ?? 0);
        case "prob": return getProbUp(b) - getProbUp(a);
        case "score":
        default: return (b.score ?? 0) - (a.score ?? 0);
      }
    });

    // Pinned stocks first
    const pinnedList = list.filter(s => pinned.has(s.symbol));
    const unpinnedList = list.filter(s => !pinned.has(s.symbol));
    return [...pinnedList, ...unpinnedList];
  }, [stocks, searchQuery, filterGroup, filterSector, filterRisk, maxDrawdown, sortBy, pinned]);

  const pinnedStocks = useMemo(
    () => stocks.filter(s => pinned.has(s.symbol)),
    [stocks, pinned]
  );

  // ── Handlers ────────────────────────────────────────────────────────────────

  const toggleWatchlist = useCallback((sym: string) => {
    setWatchlist(prev => {
      const next = new Set(prev);
      if (next.has(sym)) next.delete(sym); else next.add(sym);
      return next;
    });
  }, []);

  const togglePin = useCallback((sym: string) => {
    setPinned(prev => {
      const next = new Set(prev);
      if (next.has(sym)) next.delete(sym); else next.add(sym);
      return next;
    });
  }, []);

  // ── Market open check ────────────────────────────────────────────────────────

  const isMarketOpen = useMemo(() => {
    const now = new Date();
    const ist = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
    const h = ist.getHours();
    const m = ist.getMinutes();
    const day = ist.getDay();
    if (day === 0 || day === 6) return false;
    const mins = h * 60 + m;
    return mins >= 555 && mins <= 930; // 9:15 to 15:30
  }, []);

  // ── Loading state ────────────────────────────────────────────────────────────

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-full text-text-muted font-mono text-xs">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-accent-yellow animate-pulse" />
          LOADING SCREENER DATA...
        </div>
      </div>
    );
  }

  // ── Computing / Waiting state ────────────────────────────────────────────────

  if (data?.computing || data?.waiting) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 font-mono">
        <div className="w-2 h-2 rounded-full bg-accent-yellow animate-pulse" />
        <div className="text-xs text-accent-yellow font-bold tracking-widest">
          {data.computing ? "PIPELINE COMPUTING..." : "WAITING FOR DATA..."}
        </div>
        {pipelineStatus && (
          <div className="border border-border-primary bg-bg-panel p-4 w-80 space-y-2">
            <div className="text-2xs text-text-muted">PIPELINE STATUS</div>
            <div className="text-xs text-text-primary font-bold">{pipelineStatus.status}</div>
            {pipelineStatus.stage && (
              <div className="text-2xs text-text-secondary">{pipelineStatus.stage}</div>
            )}
            {pipelineStatus.message && (
              <div className="text-2xs text-text-muted">{pipelineStatus.message}</div>
            )}
            {pipelineStatus.progress !== undefined && (
              <div className="w-full h-1.5 bg-bg-tertiary rounded-sm overflow-hidden">
                <div
                  className="h-full bg-accent-yellow rounded-sm transition-all"
                  style={{ width: `${pipelineStatus.progress}%` }}
                />
              </div>
            )}
          </div>
        )}
        {dbStats && (
          <div className="grid grid-cols-3 gap-2 w-80">
            <StatBox label="UNIVERSE" value={dbStats.total_stocks ?? 0} />
            <StatBox label="BUY SIGNALS" value={dbStats.buy_signals ?? 0} color="#00c853" />
            <StatBox label="CANDLES" value={dbStats.candles_cached ?? 0} />
          </div>
        )}
      </div>
    );
  }

  // ── Regime badge color ───────────────────────────────────────────────────────

  const scoreDist   = marketCtx.score_distribution ?? insights.score_distribution ?? {};
  const regime      = marketCtx.market_regime ?? insights.market_regime ?? "";
  const regimeColor = regime === "TRENDING" ? "#00c853" : regime === "MIXED" ? "#ffcc00" : "#607d8b";

  return (
    <div className="flex flex-col h-full overflow-hidden bg-bg-primary">

      {/* ── A. INSIGHTS BAR ─────────────────────────────────────────────────── */}
      <div className="flex items-center gap-4 px-3 py-1.5 border-b border-border-primary bg-bg-panel shrink-0 overflow-x-auto">
        {regime && (
          <div className="flex items-center gap-1.5 shrink-0">
            <span className="text-2xs font-mono text-text-muted">REGIME</span>
            <span className="text-2xs font-mono font-bold px-1.5 py-0.5"
              style={{ color: regimeColor, backgroundColor: regimeColor + "20", border: `1px solid ${regimeColor}40` }}>
              {regime}
            </span>
          </div>
        )}
        {marketCtx.breadth_pct !== undefined && (
          <div className="flex items-center gap-1 shrink-0">
            <span className="text-2xs font-mono text-text-muted">BREADTH</span>
            <span className="text-2xs font-mono font-bold"
              style={{ color: (marketCtx.breadth_pct ?? 0) >= 60 ? "#00c853" : (marketCtx.breadth_pct ?? 0) >= 40 ? "#ffcc00" : "#f44336" }}>
              {(marketCtx.breadth_pct ?? 0).toFixed(0)}%
            </span>
          </div>
        )}
        {(marketCtx.top_sector || insights.top_sector) && (
          <div className="flex items-center gap-1 shrink-0">
            <span className="text-2xs font-mono text-text-muted">TOP</span>
            <span className="text-2xs font-mono font-bold text-market-up">{marketCtx.top_sector || insights.top_sector}</span>
          </div>
        )}
        {marketCtx.weak_sector && (
          <div className="flex items-center gap-1 shrink-0">
            <span className="text-2xs font-mono text-text-muted">WEAK</span>
            <span className="text-2xs font-mono font-bold text-market-down">{marketCtx.weak_sector}</span>
          </div>
        )}
        {(marketCtx.avg_rs ?? insights.avg_rs) !== undefined && (
          <div className="flex items-center gap-1 shrink-0">
            <span className="text-2xs font-mono text-text-muted">AVG RS</span>
            <span className="text-2xs font-mono font-bold"
              style={{ color: (marketCtx.avg_rs ?? insights.avg_rs ?? 0) >= 1 ? "#00c853" : "#f44336" }}>
              {(marketCtx.avg_rs ?? insights.avg_rs ?? 0).toFixed(2)}
            </span>
          </div>
        )}
        {(marketCtx.avg_confidence ?? insights.avg_confidence) !== undefined && (
          <div className="flex items-center gap-1 shrink-0">
            <span className="text-2xs font-mono text-text-muted">CONF</span>
            <span className="text-2xs font-mono font-bold text-accent-yellow">
              {(marketCtx.avg_confidence ?? insights.avg_confidence ?? 0).toFixed(0)}%
            </span>
          </div>
        )}
        {Object.keys(scoreDist).length > 0 && (
          <div className="flex items-center gap-2 shrink-0 border-l border-border-secondary pl-3">
            <span className="text-2xs font-mono text-text-muted">DIST</span>
            {[["10","#00c853"],["8-9","#69f0ae"],["6-7","#ffcc00"],["4-5","#ff9800"]].map(([key, color]) =>
              scoreDist[key] !== undefined ? (
                <span key={key} className="text-2xs font-mono" style={{ color: color as string }}>
                  {key}:{scoreDist[key]}
                </span>
              ) : null
            )}
          </div>
        )}
        <div className="flex-1" />
        {pinnedStocks.length > 0 && <span className="text-2xs font-mono text-accent-yellow shrink-0">📌 {pinnedStocks.length}</span>}
        {watchlist.size > 0 && <span className="text-2xs font-mono text-text-muted shrink-0">⭐ {watchlist.size}</span>}
      </div>

      {/* ── TOP PICKS PANEL ─────────────────────────────────────────────────── */}
      {topPicks.length > 0 && (
        <div className="px-3 py-1.5 border-b border-border-primary bg-bg-secondary shrink-0">
          <div className="flex items-center gap-2 overflow-x-auto">
            <span className="text-2xs font-mono font-bold text-accent-yellow shrink-0 tracking-widest">🔥 TOP PICKS</span>
            {topPicks.map((p) => (
              <button key={p.symbol}
                onClick={() => { const s = stocks.find(st => st.symbol === p.symbol); if (s) { setSelected(s); setDetailView("quant"); setFundamentals(null); } }}
                className="flex items-center gap-1.5 px-2 py-1 border border-border-primary bg-bg-panel hover:border-accent-yellow/60 transition-all shrink-0">
                <span className="text-2xs font-mono text-text-muted">#{p.rank}</span>
                <span className="text-xs font-mono font-bold text-text-primary">{p.symbol}</span>
                <span className="text-2xs font-mono" style={{ color: p.rs >= 1.2 ? "#00c853" : "#69f0ae" }}>
                  {p.rs.toFixed(2)}x
                </span>
                <span className="text-2xs font-mono text-text-muted">{p.prob_up.toFixed(0)}%↑</span>
                {p.entry_detail && p.entry_detail !== "NONE" && (
                  <span className="text-2xs font-mono px-1"
                    style={{ color: p.entry_detail.includes("BREAKOUT") ? "#00c853" : "#2196f3", backgroundColor: (p.entry_detail.includes("BREAKOUT") ? "#00c853" : "#2196f3") + "18" }}>
                    {p.entry_detail.split(" ")[0]}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}
      {/* ── B. HEADER BAR ───────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 px-3 py-1.5 border-b border-border-primary bg-bg-secondary shrink-0 overflow-x-auto">
        <span className="text-xs font-mono font-bold text-accent-yellow tracking-widest shrink-0">
          LONG-TERM STOCK SCREENER
        </span>
        <div className="w-px h-4 bg-border-primary shrink-0" />

        {/* Search bar with debounce */}
        <div className="relative shrink-0">
          <span className="absolute left-2 top-1/2 -translate-y-1/2 text-text-muted text-2xs pointer-events-none">🔍</span>
          <input
            type="text"
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            placeholder="Search symbol, sector..."
            className="pl-6 pr-2 py-1 text-2xs font-mono bg-bg-panel border border-border-primary text-text-primary placeholder-text-muted outline-none focus:border-accent-yellow transition-colors"
            style={{ width: "180px" }}
          />
          {searchInput && (
            <button
              onClick={() => setSearchInput("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary text-2xs"
            >
              ✕
            </button>
          )}
        </div>

        <div className="w-px h-4 bg-border-primary shrink-0" />
        <span
          className="text-2xs font-mono px-1.5 py-0.5 shrink-0"
          style={{
            color: isMarketOpen ? "#00c853" : "#607d8b",
            backgroundColor: isMarketOpen ? "#00c85318" : "#60606018",
            border: `1px solid ${isMarketOpen ? "#00c85340" : "#60606040"}`,
          }}
        >
          {isMarketOpen ? "● MARKET OPEN" : "○ MARKET CLOSED"}
        </span>

        {/* Live prices indicator */}
        {liveAvailable && (
          <span className="text-2xs font-mono px-1.5 py-0.5 shrink-0 text-market-up border border-market-up/30 bg-market-up/10 animate-pulse-fast">
            ⚡ LIVE PRICES
          </span>
        )}

        {/* Stat pills */}
        <div className="flex items-center border border-border-primary bg-bg-panel shrink-0">
          <StatPill label="UNIVERSE" value={dbStats.total_stocks ?? stocks.length} />
          <StatPill label="CANDLES" value={dbStats.candles_cached ?? "—"} />
          <StatPill label="BUY SIGNALS" value={dbStats.buy_signals ?? stocks.length} color="#00c853" />
          <StatPill label="SHOWING" value={filteredStocks.length} color="#ffcc00" />
        </div>

        <div className="w-px h-4 bg-border-primary shrink-0" />

        {/* Score filter */}
        <div className="flex items-center gap-1 shrink-0">
          <span className="text-2xs font-mono text-text-muted">MIN SCORE</span>
          {[5, 7, 9].map(v => (
            <button
              key={v}
              onClick={() => setMinScore(v)}
              className="px-2 py-0.5 text-2xs font-mono transition-all"
              style={{
                color: minScore === v ? "#0a0a0a" : "#a0a0a0",
                backgroundColor: minScore === v ? "#ffcc00" : "transparent",
                border: `1px solid ${minScore === v ? "#ffcc00" : "#2a2a2a"}`,
              }}
            >
              {v}+
            </button>
          ))}
        </div>

        <div className="w-px h-4 bg-border-primary shrink-0" />

        {/* Sort controls */}
        <div className="flex items-center gap-1 shrink-0">
          <span className="text-2xs font-mono text-text-muted">SORT</span>
          {(["score", "roc", "rs", "prob"] as const).map(key => (
            <button
              key={key}
              onClick={() => setSortBy(key)}
              className="px-2 py-0.5 text-2xs font-mono transition-all"
              style={{
                color: sortBy === key ? "#ffcc00" : "#606060",
                borderBottom: sortBy === key ? "1px solid #ffcc00" : "1px solid transparent",
              }}
            >
              {key.toUpperCase()}
            </button>
          ))}
        </div>

        <div className="flex-1" />

        {lastUpdated && (
          <span className="text-2xs font-mono text-text-muted shrink-0">
            UPD {lastUpdated}
          </span>
        )}
      </div>

      {/* ── C. FILTER BAR ───────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-1.5 border-b border-border-primary bg-bg-panel shrink-0">
        {/* Group filter */}
        <div className="flex items-center gap-1 flex-wrap">
          <span className="text-2xs font-mono text-text-muted">GROUP</span>
          {["ALL", "NIFTY50", "BANKNIFTY", "FINNIFTY", "MIDCAP", ...allGroups.filter(g => !["NIFTY50","BANKNIFTY","FINNIFTY","MIDCAP"].includes(g))].map(g => (
            <button
              key={g}
              onClick={() => setFilterGroup(g)}
              className="px-1.5 py-0.5 text-2xs font-mono transition-all"
              style={{
                color: filterGroup === g ? "#0a0a0a" : "#a0a0a0",
                backgroundColor: filterGroup === g ? "#ffcc00" : "transparent",
                border: `1px solid ${filterGroup === g ? "#ffcc00" : "#2a2a2a"}`,
              }}
            >
              {g}
            </button>
          ))}
        </div>

        <div className="w-px h-4 bg-border-secondary" />

        {/* Sector filter */}
        <div className="flex items-center gap-1 overflow-x-auto max-w-xs">
          <span className="text-2xs font-mono text-text-muted shrink-0">SECTOR</span>
          {["ALL", ...allSectors].map(sec => (
            <button
              key={sec}
              onClick={() => setFilterSector(sec)}
              className="px-1.5 py-0.5 text-2xs font-mono transition-all shrink-0"
              style={{
                color: filterSector === sec ? "#0a0a0a" : "#a0a0a0",
                backgroundColor: filterSector === sec ? "#00d4ff" : "transparent",
                border: `1px solid ${filterSector === sec ? "#00d4ff" : "#2a2a2a"}`,
              }}
            >
              {sec}
            </button>
          ))}
        </div>

        <div className="w-px h-4 bg-border-secondary" />

        {/* Risk filter */}
        <div className="flex items-center gap-1">
          <span className="text-2xs font-mono text-text-muted">RISK</span>
          {["ALL", "LOW", "MEDIUM", "HIGH"].map(r => (
            <button
              key={r}
              onClick={() => setFilterRisk(r)}
              className="px-1.5 py-0.5 text-2xs font-mono transition-all"
              style={{
                color: filterRisk === r ? "#0a0a0a" : (RISK_COLOR[r] ?? "#a0a0a0"),
                backgroundColor: filterRisk === r ? (RISK_COLOR[r] ?? "#ffcc00") : "transparent",
                border: `1px solid ${filterRisk === r ? (RISK_COLOR[r] ?? "#ffcc00") : "#2a2a2a"}`,
              }}
            >
              {r}
            </button>
          ))}
        </div>

        <div className="w-px h-4 bg-border-secondary" />

        {/* Max Drawdown */}
        <div className="flex items-center gap-2">
          <span className="text-2xs font-mono text-text-muted">MAX DD</span>
          <input
            type="range"
            min={0}
            max={50}
            step={5}
            value={maxDrawdown}
            onChange={e => setMaxDrawdown(Number(e.target.value))}
            className="w-20 accent-accent-yellow"
          />
          <span className="text-2xs font-mono text-accent-yellow w-8">{maxDrawdown}%</span>
        </div>
      </div>

      {/* ── D. PIPELINE STATUS BAR ──────────────────────────────────────────── */}
      {pipelineStatus && (
        <div
          className="px-3 py-0.5 text-2xs font-mono shrink-0 flex items-center gap-2"
          style={{
            backgroundColor:
              pipelineStatus.status === "RUNNING" ? "rgba(255,204,0,0.08)" :
              pipelineStatus.status === "DONE" ? "rgba(0,200,83,0.08)" :
              pipelineStatus.status === "ERROR" ? "rgba(244,67,54,0.08)" :
              "rgba(96,96,96,0.08)",
            borderBottom: "1px solid",
            borderColor:
              pipelineStatus.status === "RUNNING" ? "#ffcc0030" :
              pipelineStatus.status === "DONE" ? "#00c85330" :
              pipelineStatus.status === "ERROR" ? "#f4433630" :
              "#60606030",
          }}
        >
          <span
            className="w-1.5 h-1.5 rounded-full inline-block"
            style={{
              backgroundColor:
                pipelineStatus.status === "RUNNING" ? "#ffcc00" :
                pipelineStatus.status === "DONE" ? "#00c853" :
                pipelineStatus.status === "ERROR" ? "#f44336" :
                "#607d8b",
            }}
          />
          <span className="text-text-muted">PIPELINE</span>
          <span
            style={{
              color:
                pipelineStatus.status === "RUNNING" ? "#ffcc00" :
                pipelineStatus.status === "DONE" ? "#00c853" :
                pipelineStatus.status === "ERROR" ? "#f44336" :
                "#607d8b",
            }}
          >
            {pipelineStatus.status}
          </span>
          {pipelineStatus.stage && <span className="text-text-muted">· {pipelineStatus.stage}</span>}
          {pipelineStatus.message && <span className="text-text-muted truncate">· {pipelineStatus.message}</span>}
          {pipelineStatus.progress !== undefined && pipelineStatus.progress > 0 && (
            <span className="text-text-muted">{pipelineStatus.progress.toFixed(0)}%</span>
          )}
        </div>
      )}

      {/* ── E. MAIN CONTENT ─────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        <StockList
          stocks={filteredStocks}
          pinnedSymbols={pinned}
          watchlistSymbols={watchlist}
          selected={selected}
          onSelect={(s) => { setSelected(s); setDetailView("quant"); setFundamentals(null); }}
          onTogglePin={togglePin}
          onToggleWatchlist={toggleWatchlist}
        />

        {selected && (
          <div className="w-96 shrink-0 flex flex-col border-l border-border-primary bg-bg-panel overflow-hidden">
            {/* Tab switcher */}
            <div className="flex border-b border-border-primary shrink-0">
              {(["quant", "decision", "fundamentals"] as const).map(tab => (
                <button
                  key={tab}
                  onClick={() => setDetailView(tab)}
                  className="flex-1 py-1.5 text-2xs font-mono font-bold transition-all"
                  style={{
                    color: detailView === tab ? "#ffcc00" : "#606060",
                    backgroundColor: detailView === tab ? "rgba(255,204,0,0.08)" : "transparent",
                    borderBottom: detailView === tab ? "2px solid #ffcc00" : "2px solid transparent",
                  }}
                >
                  {tab === "quant" ? "⚡ QUANT" : tab === "decision" ? "🎯 DECISION" : "📊 FUNDAMENTALS"}
                </button>
              ))}
            </div>

            {detailView === "quant" ? (
              <div className="flex-1 overflow-y-auto">
                <DetailPanel
                  stock={selected}
                  onClose={() => setSelected(null)}
                  inWatchlist={watchlist.has(selected.symbol)}
                  isPinned={pinned.has(selected.symbol)}
                  onToggleWatchlist={toggleWatchlist}
                  onTogglePin={togglePin}
                />
              </div>
            ) : detailView === "decision" ? (
              <div className="flex-1 overflow-y-auto">
                <DecisionPanel stock={selected} />
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto">
                <FundamentalsPanel
                  symbol={selected.symbol}
                  fundamentals={fundamentals}
                  loading={fundLoading}
                />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
