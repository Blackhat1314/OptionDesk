import { useEffect, useRef, useCallback } from 'react';
import { useMarketStore } from '../store/marketStore';
import { tokenStore } from '../utils/api';
import type { WSMessage, OptionChainResponse, GreeksExposureResponse, IVAnalyticsResponse, MarketSummary, MlSignal } from '../types';

// Auto-detect protocol: wss:// for HTTPS (ngrok/production), ws:// for HTTP (localhost)
const _wsProto = window.location.protocol === 'https:' ? 'wss' : 'ws';
const WS_BASE = import.meta.env.VITE_WS_URL || `${_wsProto}://${window.location.host}/ws`;
const RECONNECT_DELAY_BASE = 1000;
const MAX_RECONNECT_DELAY  = 30000;
const PING_INTERVAL        = 20000;

export function useWebSocket() {
  const wsRef           = useRef<WebSocket | null>(null);
  const reconnectDelay  = useRef(RECONNECT_DELAY_BASE);
  const pingTimer       = useRef<ReturnType<typeof setInterval> | null>(null);
  const reconnectTimer  = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef      = useRef(true);

  const {
    setConnected,
    setChainForSymbol,
    setExposureForSymbol,
    setIVAnalyticsForSymbol,
    setSummaryForSymbol,
    flashTick,
  } = useMarketStore();

  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const msg: WSMessage = JSON.parse(event.data);

      switch (msg.type) {
        // ── Option chain — store for ALL symbols + update spot price ─────────
        case 'option_chain_update':
        case 'option_chain_snapshot': {
          if (msg.data && msg.symbol) {
            setChainForSymbol(msg.symbol, msg.data as OptionChainResponse);
            // Update spot price directly from chain data (most reliable source)
            const chain = msg.data as OptionChainResponse;
            const activeSymbol = useMarketStore.getState().activeSymbol;
            if (msg.symbol === activeSymbol && chain.spot_price > 0) {
              const state = useMarketStore.getState();
              useMarketStore.getState().updateSpotPrice(
                chain.spot_price,
                state.dayChange,
                state.dayChangePct
              );
            }
          }
          break;
        }

        // ── Greeks exposure — store for ALL symbols ───────────────────────────
        case 'greeks_update':
        case 'exposure_snapshot': {
          if (msg.data && msg.symbol) {
            setExposureForSymbol(msg.symbol, msg.data as GreeksExposureResponse);
          }
          break;
        }

        // ── IV analytics — store for ALL symbols ─────────────────────────────
        case 'iv_update':
        case 'iv_snapshot': {
          if (msg.data && msg.symbol) {
            setIVAnalyticsForSymbol(msg.symbol, msg.data as IVAnalyticsResponse);
          }
          break;
        }

        // ── Market summary — store for ALL symbols + update spot price ──────
        case 'market_summary':
        case 'summary_snapshot': {
          if (msg.data) {
            const summary = msg.data as MarketSummary;
            const sym = msg.symbol || summary.symbol;
            if (sym) {
              setSummaryForSymbol(sym, summary);
              // Store prevClose so tick handler can recalculate day change in real-time
              // prevClose = spot_price - day_change (from the authoritative summary message)
              if (summary.spot_price > 0 && summary.day_change !== undefined && summary.day_change !== null) {
                const prevClose = summary.spot_price - summary.day_change;
                if (prevClose > 0) {
                  useMarketStore.getState().setPrevClose(sym, prevClose);
                }
              }
              // Explicitly update spot price if this is the active symbol
              const activeSymbol = useMarketStore.getState().activeSymbol;
              if (sym === activeSymbol && summary.spot_price > 0) {
                useMarketStore.getState().updateSpotPrice(
                  summary.spot_price,
                  summary.day_change ?? 0,
                  summary.day_change_pct ?? 0
                );
              }
            }
          }
          break;
        }

        // ── Tick — update live spot price for ALL symbols ────────────────
        case 'tick': {
          const tick = msg as unknown as {
            security_id: string;
            ltp: number;
            volume?: number;
            symbol?: string;   // present for stock ticks, absent for index ticks
            day_change?: number;
            day_change_pct?: number;
            prev_close?: number;
            open?: number;
            high?: number;
            low?: number;
            atp?: number;
          };
          if (!tick.security_id || !tick.ltp) break;

          // Map security_id → symbol (ONLY for index ticks — stock ticks have tick.symbol set)
          // Index ticks: no tick.symbol, use SID map
          // Stock ticks: tick.symbol is set by backend, skip index mapping
          const INDEX_SID_MAP: Record<string, string> = {
            '13':   'NIFTY',
            '25':   'BANKNIFTY',
            '27':   'FINNIFTY',
            '442':  'MIDCPNIFTY',
            '51':   'SENSEX',
            '21':   'INDIAVIX',
            '5024': 'GIFTNIFTY',
          };
          // Only use INDEX_SID_MAP if this is NOT a stock tick
          const tickSymbol = !tick.symbol ? INDEX_SID_MAP[tick.security_id] : undefined;

          if (tickSymbol) {
            const state = useMarketStore.getState();
            const existingSummary = state.symbolCache[tickSymbol]?.summary;

            // Use day_change from WS tick if available (index quote mode sends it)
            // Otherwise recalculate from stored prevClose
            let dayChange    = (tick as any).day_change    ?? existingSummary?.day_change    ?? 0;
            let dayChangePct = (tick as any).day_change_pct ?? existingSummary?.day_change_pct ?? 0;

            // Store prevClose from WS tick if provided (from prev_close packet or quote)
            const wsPrevClose = (tick as any).prev_close ?? 0;
            if (wsPrevClose > 0) {
              useMarketStore.getState().setPrevClose(tickSymbol, wsPrevClose);
            }

            // Fallback: recalculate from stored prevClose
            if (dayChange === 0) {
              const prevClose = state.symbolCache[tickSymbol]?.prevClose ?? 0;
              if (prevClose > 0) {
                dayChange    = parseFloat((tick.ltp - prevClose).toFixed(2));
                dayChangePct = parseFloat(((tick.ltp - prevClose) / prevClose * 100).toFixed(2));
              }
            }

            if (existingSummary) {
              const updatedSummary = {
                ...existingSummary,
                spot_price:     tick.ltp,
                day_change:     dayChange,
                day_change_pct: dayChangePct,
              };
              setSummaryForSymbol(tickSymbol, updatedSummary as MarketSummary);
            }
            if (tickSymbol === state.activeSymbol) {
              state.updateSpotPrice(tick.ltp, dayChange, dayChangePct);
            }
          }

          // ── Stock tick — REMOVED ─────────────────────────────────────────
          // Stock prices come from REST batch (/api/stocks/live-prices) every 30s
          // Not from WebSocket — keeps WS clean and prevents UI slowness

          // Flash option rows for active chain
          const state2 = useMarketStore.getState();
          const chain = state2.chain;
          if (chain && tick.security_id) {
            for (const row of chain.rows) {
              if (row.call.security_id === tick.security_id) {
                flashTick(tick.security_id, tick.ltp >= row.call.ltp ? 'up' : 'down');
                break;
              }
              if (row.put.security_id === tick.security_id) {
                flashTick(tick.security_id, tick.ltp >= row.put.ltp ? 'up' : 'down');
                break;
              }
            }
          }
          break;
        }

        case 'alert': {
          try {
            localStorage.setItem('last_alert', JSON.stringify(msg.data));
            window.dispatchEvent(new StorageEvent('storage', { key: 'last_alert' }));
          } catch {}
          break;
        }

        case 'ml_signals': {
          if (msg.data && msg.symbol) {
            useMarketStore.getState().setMlSignals(msg.symbol, msg.data as MlSignal[]);
          }
          break;
        }

        default:
          break;
      }
    } catch {}
  }, [setChainForSymbol, setExposureForSymbol, setIVAnalyticsForSymbol, setSummaryForSymbol, flashTick]);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const token = tokenStore.get();
    if (!token) return;
    
    // Skip WebSocket in demo mode — data comes from static snapshot
    if (token === 'DEMO_MODE_TOKEN') return;

    const WS_URL = `${WS_BASE}?token=${encodeURIComponent(token)}`;

    try {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
        setConnected(true);
        reconnectDelay.current = RECONNECT_DELAY_BASE;

        // Subscribe to all symbols
        const symbols = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX'];
        const channels = symbols.flatMap(sym => [
          `option_chain:${sym}`,
          `greeks:${sym}`,
          `iv:${sym}`,
          `summary:${sym}`,
        ]);
        ws.send(JSON.stringify({ action: 'subscribe', channels }));

        if (pingTimer.current) clearInterval(pingTimer.current);
        pingTimer.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ action: 'ping' }));
          }
        }, PING_INTERVAL);
      };

      ws.onmessage = handleMessage;

      ws.onclose = (event) => {
        setConnected(false);
        if (pingTimer.current) clearInterval(pingTimer.current);
        if (!mountedRef.current) return;
        reconnectTimer.current = setTimeout(() => {
          reconnectDelay.current = Math.min(reconnectDelay.current * 2, MAX_RECONNECT_DELAY);
          connect();
        }, reconnectDelay.current);
      };

      ws.onerror = () => {};
    } catch {
      reconnectTimer.current = setTimeout(connect, reconnectDelay.current);
    }
  }, [handleMessage, setConnected]);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      if (pingTimer.current)    clearInterval(pingTimer.current);
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const send = useCallback((msg: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  return { send };
}
