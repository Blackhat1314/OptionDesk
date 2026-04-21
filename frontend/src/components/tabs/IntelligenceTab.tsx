import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, ReferenceLine, Cell
} from "recharts";
import { useMarketStore } from "../../store/marketStore";
import { api } from "../../utils/api";
import { fmt } from "../../utils/format";

// ─── Types ────────────────────────────────────────────────────────────────────

interface TSSnapshot {
  ts: number; gex: number; dex: number; iv: number;
  total_oi: number; delta_gex: number; delta_oi: number; delta_iv: number; spot: number;
}
interface OIRow {
  strike: number; type: string; classification: string; color: string;
  oi: number; oi_change: number; ltp: number; iv: number; delta: number; volume: number;
}
interface HeatmapStrike {
  strike: number; dist_pct: number; is_atm: boolean;
  call_oi: number; put_oi: number; call_oi_pct: number; put_oi_pct: number;
  call_iv: number; put_iv: number; iv_skew: number; pcr: number;
}
interface IntelData {
  symbol: string; spot: number; timestamp: number;
  timeseries: TSSnapshot[];
  oi_classification: { table: OIRow[]; flow_counts: Record<string,number>; dominant: OIRow[] };
  expected_move: {
    spot: number; iv_pct: number; dte: number; expected_move: number;
    upper_1sd: number; lower_1sd: number; upper_2sd: number; lower_2sd: number;
    upper_pct: number; lower_pct: number; prob_in_range: number; status?: string;
  };
  iv_regime: { regime: string; signal: string; description: string; color: string;
    iv_pct: number; hv_pct: number; iv_rank: number; iv_hv_ratio: number };
  smart_signal: { signal: string; signal_color: string; confidence: number; score: number; reasons: string[] };
  alerts: any[];
  heatmap: { strikes: HeatmapStrike[]; spot: number; max_oi: number; count: number; status?: string };
  summary: { gex: number; delta_gex: number; iv: number; hv: number; iv_rank: number;
    pcr: number; max_pain: number; call_wall: number; put_wall: number };
}

const FLOW_COLORS: Record<string,string> = {
  LONG_BUILDUP: "#00c853", SHORT_BUILDUP: "#ff1744",
  SHORT_COVERING: "#00e5ff", LONG_UNWINDING: "#ff9100", NEUTRAL: "#607d8b",
};

// ─── Global pre-fetch cache — survives tab switches ───────────────────────────
// Keyed by symbol so switching symbols still works correctly
const _cache: Record<string, IntelData> = {};

// ─── Main Component ───────────────────────────────────────────────────────────

export const IntelligenceTab: React.FC = () => {
  const { activeSymbol } = useMarketStore();

  // Initialise from cache immediately — no loading flash on tab switch
  const [data, setData] = useState<IntelData | null>(_cache[activeSymbol] ?? null);
  const [initialLoading, setInitialLoading] = useState(!_cache[activeSymbol]);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [activePanel, setActivePanel] = useState<"timeseries"|"oi"|"heatmap"|"signals"|"alerts">("timeseries");

  // Use a ref for the interval so it doesn't cause re-renders
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const symbolRef   = useRef(activeSymbol);
  symbolRef.current = activeSymbol;

  const fetchData = useCallback(async (isBackground = false) => {
    if (!isBackground) setRefreshing(true);
    try {
      const res = await api.getIntelligence(symbolRef.current) as IntelData;
      _cache[symbolRef.current] = res;          // persist in module-level cache
      setData(res);
      setError("");
    } catch (e: any) {
      // On background refresh failure, keep existing data — don't blank the UI
      if (!isBackground) setError(e.message || "Failed to load");
    } finally {
      setInitialLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    // If we already have cached data for this symbol, show it immediately
    // and do a silent background refresh
    if (_cache[activeSymbol]) {
      setData(_cache[activeSymbol]);
      setInitialLoading(false);
      fetchData(true);   // silent refresh
    } else {
      setInitialLoading(true);
      fetchData(false);  // first load — show spinner
    }

    // Background refresh every 15s — never shows loading spinner
    intervalRef.current = setInterval(() => fetchData(true), 15000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSymbol]);   // only re-run when symbol changes, not fetchData

  // ── Render ──────────────────────────────────────────────────────────────────

  // Only show full-screen loader on very first load with no cached data
  if (initialLoading && !data) {
    return (
      <div className="flex items-center justify-center h-full text-text-muted font-mono text-xs">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-accent-yellow animate-pulse" />
          LOADING INTELLIGENCE DATA...
        </div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="flex items-center justify-center h-full text-market-down font-mono text-xs">
        ⚠ {error}
      </div>
    );
  }

  if (!data) return null;

  const panels = [
    { id: "timeseries", label: "TIME-SERIES" },
    { id: "oi",         label: "OI FLOW" },
    { id: "heatmap",    label: "HEATMAP" },
    { id: "signals",    label: "SIGNALS" },
    { id: "alerts",     label: `ALERTS${data.alerts.length > 0 ? ` (${data.alerts.length})` : ""}` },
  ] as const;

  return (
    <div className="flex flex-col h-full overflow-hidden bg-bg-primary">
      {/* Header */}
      <div className="flex items-center gap-4 px-4 py-2 border-b border-border-primary bg-bg-panel shrink-0">
        <span className="text-2xs font-mono font-bold text-accent-yellow tracking-widest">INTELLIGENCE</span>
        <div className="w-px h-4 bg-border-primary" />
        <SummaryPills data={data} />
        <div className="flex-1" />
        {/* Subtle refresh indicator — never blocks UI */}
        {refreshing && (
          <div className="w-1.5 h-1.5 rounded-full bg-accent-yellow animate-pulse" title="Refreshing..." />
        )}
        <SmartSignalBadge sig={data.smart_signal} />
      </div>

      {/* Panel tabs */}
      <div className="flex border-b border-border-primary shrink-0 bg-bg-secondary">
        {panels.map(p => (
          <button key={p.id} onClick={() => setActivePanel(p.id as any)}
            className={`px-4 py-1.5 text-2xs font-mono font-bold tracking-wider border-r border-border-secondary transition-all ${
              activePanel === p.id
                ? "bg-bg-primary text-accent-yellow border-b-2 border-b-accent-yellow"
                : "text-text-muted hover:text-text-primary hover:bg-bg-hover"
            }`}>
            {p.label}
          </button>
        ))}
      </div>

      {/* Panel content — always rendered, never replaced by spinner */}
      <div className="flex-1 overflow-auto">
        {activePanel === "timeseries" && <TimeSeriesPanel data={data} />}
        {activePanel === "oi"         && <OIFlowPanel data={data} />}
        {activePanel === "heatmap"    && <HeatmapPanel data={data} />}
        {activePanel === "signals"    && <SignalsPanel data={data} />}
        {activePanel === "alerts"     && <AlertsPanel data={data} />}
      </div>
    </div>
  );
};

// ─── Summary Pills ────────────────────────────────────────────────────────────

const SummaryPills: React.FC<{ data: IntelData }> = ({ data: d }) => (
  <div className="flex items-center gap-3">
    <Pill label="GEX" value={`${d.summary.gex >= 0 ? "+" : ""}${d.summary.gex.toFixed(2)}Cr`}
      color={d.summary.gex >= 0 ? "text-market-up" : "text-market-down"} />
    <Pill label="ΔGEX" value={`${d.summary.delta_gex >= 0 ? "+" : ""}${d.summary.delta_gex.toFixed(3)}`}
      color={d.summary.delta_gex >= 0 ? "text-market-up" : "text-market-down"} />
    <Pill label="IV" value={`${d.summary.iv.toFixed(1)}%`} color="text-accent-yellow" />
    <Pill label="HV" value={`${d.summary.hv.toFixed(1)}%`} color="text-text-secondary" />
    <Pill label="IVR" value={`${d.summary.iv_rank.toFixed(0)}`} color="text-accent-cyan" />
    <Pill label="PCR" value={d.summary.pcr.toFixed(2)}
      color={d.summary.pcr > 1.2 ? "text-market-up" : d.summary.pcr < 0.8 ? "text-market-down" : "text-text-secondary"} />
  </div>
);

const Pill: React.FC<{ label: string; value: string; color: string }> = ({ label, value, color }) => (
  <div className="flex flex-col items-center">
    <span className="text-2xs text-text-muted font-mono">{label}</span>
    <span className={`text-xs font-mono font-bold ${color}`}>{value}</span>
  </div>
);

const SmartSignalBadge: React.FC<{ sig: IntelData["smart_signal"] }> = ({ sig }) => (
  <div className="flex items-center gap-2 px-3 py-1 border"
    style={{ borderColor: sig.signal_color + "60", backgroundColor: sig.signal_color + "15" }}>
    <div className="w-2 h-2 rounded-full animate-pulse" style={{ backgroundColor: sig.signal_color }} />
    <span className="text-xs font-mono font-bold" style={{ color: sig.signal_color }}>{sig.signal}</span>
    <span className="text-2xs font-mono text-text-muted">{sig.confidence}%</span>
  </div>
);

// ─── Time-Series Panel ────────────────────────────────────────────────────────

const TimeSeriesPanel: React.FC<{ data: IntelData }> = ({ data: d }) => {
  const ts = d.timeseries;
  if (!ts.length) return <EmptyState msg="No time-series data yet — accumulating ticks..." />;

  const chartData = ts.map(s => ({
    t:         new Date(s.ts * 1000).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" }),
    gex:       s.gex,
    dex:       s.dex,
    iv:        s.iv,
    delta_gex: s.delta_gex,
    delta_oi:  s.delta_oi,
    spot:      s.spot,
  }));

  return (
    <div className="p-3 space-y-3">
      <ChartCard title="GEX & DEX OVER TIME (Cr)">
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="#1e1e1e" />
            <XAxis dataKey="t" tick={{ fill: "#606060", fontSize: 8, fontFamily: "monospace" }} tickLine={false} interval={Math.max(1, Math.floor(chartData.length / 8))} />
            <YAxis tick={{ fill: "#606060", fontSize: 8, fontFamily: "monospace" }} tickLine={false} width={52} />
            <Tooltip contentStyle={{ background: "#141414", border: "1px solid #2a2a2a", fontFamily: "monospace", fontSize: 10 }} />
            <ReferenceLine y={0} stroke="#333" strokeDasharray="3 3" />
            <Line type="monotone" dataKey="gex" stroke="#ffcc00" dot={false} strokeWidth={1.5} name="GEX" />
            <Line type="monotone" dataKey="dex" stroke="#00d4ff" dot={false} strokeWidth={1} name="DEX" />
          </LineChart>
        </ResponsiveContainer>
      </ChartCard>

      <ChartCard title="IV OVER TIME (%)">
        <ResponsiveContainer width="100%" height={140}>
          <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="#1e1e1e" />
            <XAxis dataKey="t" tick={{ fill: "#606060", fontSize: 8, fontFamily: "monospace" }} tickLine={false} interval={Math.max(1, Math.floor(chartData.length / 8))} />
            <YAxis tick={{ fill: "#606060", fontSize: 8, fontFamily: "monospace" }} tickLine={false} width={36} />
            <Tooltip contentStyle={{ background: "#141414", border: "1px solid #2a2a2a", fontFamily: "monospace", fontSize: 10 }} />
            <Line type="monotone" dataKey="iv" stroke="#ff9100" dot={false} strokeWidth={1.5} name="ATM IV" />
          </LineChart>
        </ResponsiveContainer>
      </ChartCard>

      <ChartCard title="ΔGEX (Change per Tick)">
        <ResponsiveContainer width="100%" height={120}>
          <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="#1e1e1e" />
            <XAxis dataKey="t" tick={{ fill: "#606060", fontSize: 8, fontFamily: "monospace" }} tickLine={false} interval={Math.max(1, Math.floor(chartData.length / 8))} />
            <YAxis tick={{ fill: "#606060", fontSize: 8, fontFamily: "monospace" }} tickLine={false} width={52} />
            <Tooltip contentStyle={{ background: "#141414", border: "1px solid #2a2a2a", fontFamily: "monospace", fontSize: 10 }} />
            <ReferenceLine y={0} stroke="#333" />
            <Bar dataKey="delta_gex" name="ΔGEX" maxBarSize={6}>
              {chartData.map((entry, i) => (
                <Cell key={i} fill={entry.delta_gex >= 0 ? "#00c853" : "#ff1744"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>
    </div>
  );
};

// ─── OI Flow Panel ────────────────────────────────────────────────────────────

const OIFlowPanel: React.FC<{ data: IntelData }> = ({ data: d }) => {
  const { table, flow_counts, dominant } = d.oi_classification;
  if (!table.length) return <EmptyState msg="No OI classification data yet — needs 2+ chain refreshes" />;

  const flowOrder = ["LONG_BUILDUP","SHORT_BUILDUP","SHORT_COVERING","LONG_UNWINDING","NEUTRAL"];

  return (
    <div className="p-3 space-y-3">
      <div className="grid grid-cols-5 gap-2">
        {flowOrder.map(f => (
          <div key={f} className="border border-border-primary bg-bg-panel p-2 text-center">
            <div className="text-lg font-mono font-bold" style={{ color: FLOW_COLORS[f] }}>
              {flow_counts[f] || 0}
            </div>
            <div className="text-2xs font-mono text-text-muted leading-tight mt-0.5">
              {f.replace(/_/g, " ")}
            </div>
          </div>
        ))}
      </div>

      <div className="border border-border-primary bg-bg-panel">
        <div className="px-3 py-1.5 border-b border-border-primary">
          <span className="text-2xs font-mono font-bold text-accent-yellow tracking-widest">OI CLASSIFICATION TABLE</span>
        </div>
        <div className="grid grid-cols-8 text-2xs font-mono text-text-muted px-3 py-1 border-b border-border-secondary">
          <span>STRIKE</span><span>TYPE</span><span className="col-span-2">CLASSIFICATION</span>
          <span className="text-right">OI</span><span className="text-right">Δ OI</span>
          <span className="text-right">LTP</span><span className="text-right">IV%</span>
        </div>
        <div className="max-h-64 overflow-y-auto">
          {table.map((row, i) => (
            <div key={i} className="grid grid-cols-8 text-2xs font-mono px-3 py-0.5 hover:bg-bg-hover border-b border-border-secondary/30">
              <span className="text-text-secondary font-bold">{fmt.strike(row.strike)}</span>
              <span className="text-text-muted">{row.type}</span>
              <span className="col-span-2 font-bold" style={{ color: row.color }}>{row.classification.replace(/_/g," ")}</span>
              <span className="text-right text-text-secondary">{fmt.compact(row.oi)}</span>
              <span className={`text-right font-bold ${row.oi_change >= 0 ? "text-market-up" : "text-market-down"}`}>
                {row.oi_change >= 0 ? "+" : ""}{fmt.compact(row.oi_change)}
              </span>
              <span className="text-right text-text-primary">{row.ltp > 0 ? fmt.price(row.ltp) : "—"}</span>
              <span className="text-right text-accent-yellow">{row.iv > 0 ? `${row.iv.toFixed(1)}%` : "—"}</span>
            </div>
          ))}
        </div>
      </div>

      {dominant.length > 0 && (
        <ChartCard title="TOP STRIKES BY OI CHANGE">
          <ResponsiveContainer width="100%" height={160}>
            <BarChart
              data={dominant.slice(0,10).map(r => ({ name: `${r.strike}${r.type}`, oi_change: r.oi_change, color: r.color }))}
              margin={{ top: 4, right: 8, bottom: 20, left: 0 }}>
              <CartesianGrid strokeDasharray="2 4" stroke="#1e1e1e" />
              <XAxis dataKey="name" tick={{ fill: "#606060", fontSize: 7, fontFamily: "monospace" }} tickLine={false} angle={-45} textAnchor="end" />
              <YAxis tick={{ fill: "#606060", fontSize: 8, fontFamily: "monospace" }} tickLine={false} width={52} />
              <Tooltip contentStyle={{ background: "#141414", border: "1px solid #2a2a2a", fontFamily: "monospace", fontSize: 10 }} />
              <ReferenceLine y={0} stroke="#333" />
              <Bar dataKey="oi_change" name="OI Change" maxBarSize={20}>
                {dominant.slice(0,10).map((r, i) => <Cell key={i} fill={r.color} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      )}
    </div>
  );
};

// ─── Heatmap Panel ────────────────────────────────────────────────────────────

const HeatmapPanel: React.FC<{ data: IntelData }> = ({ data: d }) => {
  const hm = d.heatmap;
  if (hm.status === "INSUFFICIENT_DATA" || !hm.strikes?.length)
    return <EmptyState msg="No heatmap data yet" />;

  return (
    <div className="p-3 space-y-3">
      <div className="border border-border-primary bg-bg-panel">
        <div className="px-3 py-1.5 border-b border-border-primary flex items-center gap-3">
          <span className="text-2xs font-mono font-bold text-accent-yellow tracking-widest">OI HEATMAP</span>
          <span className="text-2xs text-text-muted font-mono">Bar width = OI intensity · Skew = Put IV − Call IV</span>
        </div>
        <div className="max-h-96 overflow-y-auto">
          <div className="grid grid-cols-12 text-2xs font-mono text-text-muted px-3 py-1 border-b border-border-secondary sticky top-0 bg-bg-panel">
            <span className="col-span-2">STRIKE</span>
            <span className="col-span-4 text-center text-chart-call">CALL OI</span>
            <span className="col-span-2 text-center">SKEW</span>
            <span className="col-span-4 text-center text-chart-put">PUT OI</span>
          </div>
          {hm.strikes.map((s, i) => {
            const isAtm = s.is_atm;
            return (
              <div key={i} className={`grid grid-cols-12 text-2xs font-mono px-3 py-0.5 border-b border-border-secondary/20 ${isAtm ? "bg-accent-yellow/5 border-l-2 border-l-accent-yellow" : "hover:bg-bg-hover"}`}>
                <span className={`col-span-2 font-bold ${isAtm ? "text-accent-yellow" : "text-text-secondary"}`}>
                  {fmt.strike(s.strike)}{isAtm ? " ◆" : ""}
                </span>
                <div className="col-span-4 flex items-center justify-end gap-1">
                  <span className="text-text-muted w-10 text-right tabular-nums">{fmt.compact(s.call_oi)}</span>
                  <div className="w-16 h-2 bg-bg-tertiary flex justify-end">
                    <div className="h-full bg-chart-call/70" style={{ width: `${s.call_oi_pct}%` }} />
                  </div>
                </div>
                <div className="col-span-2 text-center">
                  <span className={s.iv_skew > 0 ? "text-market-down" : s.iv_skew < 0 ? "text-market-up" : "text-text-muted"}>
                    {s.iv_skew > 0 ? "+" : ""}{s.iv_skew.toFixed(1)}
                  </span>
                </div>
                <div className="col-span-4 flex items-center gap-1">
                  <div className="w-16 h-2 bg-bg-tertiary">
                    <div className="h-full bg-chart-put/70" style={{ width: `${s.put_oi_pct}%` }} />
                  </div>
                  <span className="text-text-muted w-10 tabular-nums">{fmt.compact(s.put_oi)}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <ChartCard title="IV SKEW BY STRIKE (Put IV − Call IV)">
        <ResponsiveContainer width="100%" height={150}>
          <BarChart
            data={hm.strikes.map(s => ({ strike: fmt.strike(s.strike), skew: s.iv_skew }))}
            margin={{ top: 4, right: 8, bottom: 20, left: 0 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="#1e1e1e" />
            <XAxis dataKey="strike" tick={{ fill: "#606060", fontSize: 7, fontFamily: "monospace" }} tickLine={false} angle={-45} textAnchor="end" interval={Math.max(1, Math.floor(hm.strikes.length / 10))} />
            <YAxis tick={{ fill: "#606060", fontSize: 8, fontFamily: "monospace" }} tickLine={false} width={36} />
            <Tooltip contentStyle={{ background: "#141414", border: "1px solid #2a2a2a", fontFamily: "monospace", fontSize: 10 }} />
            <ReferenceLine y={0} stroke="#555" strokeDasharray="3 3" />
            <Bar dataKey="skew" name="IV Skew" maxBarSize={8}>
              {hm.strikes.map((s, i) => <Cell key={i} fill={s.iv_skew > 0 ? "#ff1744" : "#00c853"} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>
    </div>
  );
};

// ─── Signals Panel ────────────────────────────────────────────────────────────

const SignalsPanel: React.FC<{ data: IntelData }> = ({ data: d }) => {
  const { smart_signal: sig, iv_regime: ivr, expected_move: em, summary: s } = d;

  return (
    <div className="p-3 space-y-3">
      {/* Smart Signal */}
      <div className="border border-border-primary bg-bg-panel p-4">
        <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest mb-3">SMART SIGNAL (INDEPENDENT)</div>
        <div className="flex items-center gap-4 mb-3">
          <div className="text-2xl font-mono font-bold" style={{ color: sig.signal_color }}>{sig.signal.replace(/_/g," ")}</div>
          <div className="flex flex-col">
            <span className="text-2xs text-text-muted font-mono">CONFIDENCE</span>
            <div className="flex items-center gap-2">
              <div className="w-32 h-2 bg-bg-tertiary">
                <div className="h-full" style={{ width: `${sig.confidence}%`, backgroundColor: sig.signal_color }} />
              </div>
              <span className="text-xs font-mono font-bold" style={{ color: sig.signal_color }}>{sig.confidence}%</span>
            </div>
          </div>
          <div className="flex flex-col">
            <span className="text-2xs text-text-muted font-mono">SCORE</span>
            <span className="text-sm font-mono font-bold" style={{ color: sig.signal_color }}>
              {sig.score >= 0 ? "+" : ""}{sig.score}
            </span>
          </div>
        </div>
        <div className="space-y-1">
          {sig.reasons.map((r, i) => (
            <div key={i} className="flex items-start gap-2 text-2xs font-mono text-text-secondary">
              <span className="text-accent-yellow shrink-0">›</span><span>{r}</span>
            </div>
          ))}
        </div>
      </div>

      {/* IV Regime */}
      <div className="border border-border-primary bg-bg-panel p-4">
        <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest mb-3">IV REGIME</div>
        <div className="flex items-center gap-4 mb-2">
          <div className="text-lg font-mono font-bold" style={{ color: ivr.color }}>{ivr.regime.replace(/_/g," ")}</div>
          <div className="text-xs font-mono font-bold" style={{ color: ivr.color }}>{ivr.signal.replace(/_/g," ")}</div>
        </div>
        <p className="text-2xs font-mono text-text-secondary mb-3">{ivr.description}</p>
        <div className="grid grid-cols-4 gap-2">
          <MetricBox label="IV" value={`${ivr.iv_pct.toFixed(1)}%`} color={ivr.color} />
          <MetricBox label="HV" value={`${ivr.hv_pct.toFixed(1)}%`} color="text-text-secondary" />
          <MetricBox label="IV RANK" value={`${ivr.iv_rank.toFixed(0)}`} color="text-accent-cyan" />
          <MetricBox label="IV/HV" value={ivr.iv_hv_ratio.toFixed(2)}
            color={ivr.iv_hv_ratio > 1.2 ? "text-market-down" : ivr.iv_hv_ratio < 0.85 ? "text-market-up" : "text-text-secondary"} />
        </div>
      </div>

      {/* Expected Move */}
      {em && em.status !== "INSUFFICIENT_DATA" && em.expected_move > 0 && (
        <div className="border border-border-primary bg-bg-panel p-4">
          <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest mb-3">EXPECTED MOVE</div>
          <div className="flex items-center gap-2 mb-3 flex-wrap">
            <span className="text-2xs text-text-muted font-mono">Spot × IV × √(DTE/365)</span>
            <span className="text-2xs text-text-muted font-mono">· DTE: {em.dte?.toFixed(0)}d</span>
            <span className="text-2xs text-text-muted font-mono">· 68.27% prob in 1σ</span>
          </div>
          <div className="grid grid-cols-2 gap-3 mb-3">
            <div className="border border-market-up/30 bg-market-up/5 p-3">
              <div className="text-2xs text-text-muted font-mono mb-1">UPPER (1σ)</div>
              <div className="text-lg font-mono font-bold text-market-up">{fmt.price(em.upper_1sd)}</div>
              <div className="text-2xs text-market-up font-mono">+{em.upper_pct?.toFixed(2)}%</div>
            </div>
            <div className="border border-market-down/30 bg-market-down/5 p-3">
              <div className="text-2xs text-text-muted font-mono mb-1">LOWER (1σ)</div>
              <div className="text-lg font-mono font-bold text-market-down">{fmt.price(em.lower_1sd)}</div>
              <div className="text-2xs text-market-down font-mono">{em.lower_pct?.toFixed(2)}%</div>
            </div>
            <div className="border border-market-up/20 p-2">
              <div className="text-2xs text-text-muted font-mono mb-0.5">UPPER (2σ)</div>
              <div className="text-sm font-mono font-bold text-market-up/70">{fmt.price(em.upper_2sd)}</div>
            </div>
            <div className="border border-market-down/20 p-2">
              <div className="text-2xs text-text-muted font-mono mb-0.5">LOWER (2σ)</div>
              <div className="text-sm font-mono font-bold text-market-down/70">{fmt.price(em.lower_2sd)}</div>
            </div>
          </div>
          <div className="text-center border-t border-border-secondary pt-2">
            <span className="text-xs font-mono font-bold text-accent-yellow">±{fmt.price(em.expected_move)}</span>
            <span className="text-2xs text-text-muted font-mono ml-2">expected move this expiry</span>
          </div>
        </div>
      )}

      {/* Key levels */}
      <div className="grid grid-cols-3 gap-2">
        <MetricBox label="MAX PAIN" value={fmt.strike(s.max_pain)} color="text-accent-yellow" />
        <MetricBox label="CALL WALL" value={fmt.strike(s.call_wall)} color="text-chart-call" />
        <MetricBox label="PUT WALL" value={fmt.strike(s.put_wall)} color="text-chart-put" />
      </div>
    </div>
  );
};

const MetricBox: React.FC<{ label: string; value: string; color: string }> = ({ label, value, color }) => (
  <div className="border border-border-primary bg-bg-panel p-2 text-center">
    <div className="text-2xs text-text-muted font-mono">{label}</div>
    <div className={`text-sm font-mono font-bold ${color}`}>{value}</div>
  </div>
);

// ─── Alerts Panel ─────────────────────────────────────────────────────────────

const ALERT_COLORS: Record<string,string> = {
  CRITICAL: "#ff1744", WARNING: "#ff9100", INFO: "#00d4ff",
};

const AlertsPanel: React.FC<{ data: IntelData }> = ({ data: d }) => {
  if (!d.alerts.length) return <EmptyState msg="No alerts triggered yet" />;
  return (
    <div className="p-3 space-y-2">
      {d.alerts.map((a: any, i: number) => (
        <div key={i} className="border border-border-primary bg-bg-panel p-3 flex items-start gap-3"
          style={{ borderLeftColor: ALERT_COLORS[a.severity] || "#607d8b", borderLeftWidth: 3 }}>
          <div className="w-2 h-2 rounded-full shrink-0 mt-1" style={{ backgroundColor: ALERT_COLORS[a.severity] || "#607d8b" }} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-0.5">
              <span className="text-2xs font-mono font-bold" style={{ color: ALERT_COLORS[a.severity] }}>{a.type}</span>
              <span className="text-2xs text-text-muted font-mono">{a.symbol}</span>
              <span className="text-2xs text-text-muted font-mono ml-auto">
                {new Date(a.timestamp * 1000).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: false })}
              </span>
            </div>
            <p className="text-xs font-mono text-text-secondary">{a.message}</p>
          </div>
        </div>
      ))}
    </div>
  );
};

// ─── Shared ───────────────────────────────────────────────────────────────────

const ChartCard: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div className="border border-border-primary bg-bg-panel p-3">
    <div className="text-2xs font-mono font-bold text-accent-yellow tracking-widest mb-2">{title}</div>
    {children}
  </div>
);

const EmptyState: React.FC<{ msg: string }> = ({ msg }) => (
  <div className="flex items-center justify-center h-48 text-text-muted font-mono text-xs text-center px-8">{msg}</div>
);

// ─── Pre-warm export — called by App.tsx to populate cache before tab opens ──
export async function _prewarmIntelligence(symbol: string): Promise<void> {
  if (_cache[symbol]) return;   // already cached
  try {
    const res = await api.getIntelligence(symbol) as IntelData;
    _cache[symbol] = res;
  } catch {}
}

