# OptionsDesk — Bloomberg-Grade Options Analytics Platform

A production-ready, full-stack options analytics terminal for Indian markets (NIFTY/BANKNIFTY), powered by the Dhan API v2 with real-time WebSocket streaming and quant-grade analytics.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    NGINX (Port 80)                       │
│              Reverse proxy + WebSocket                   │
└───────────┬─────────────────────────┬───────────────────┘
            │                         │
    ┌───────▼──────┐         ┌────────▼──────┐
    │ React Frontend│         │  FastAPI      │
    │   (Port 3000) │◄───WS──►│  Backend      │
    │ TypeScript    │  REST   │  (Port 8000)  │
    │ Recharts      │         │  Async/uvicorn│
    └───────────────┘         └───────┬───────┘
                                      │
                          ┌───────────▼────────────┐
                          │  Dhan API v2 + WebSocket│
                          │  Option Chain REST      │
                          │  Live Feed WS           │
                          └─────────────────────────┘
                                      │
                              ┌───────▼────────┐
                              │  Redis Cache   │
                              │  (State Store) │
                              └────────────────┘
```

## Features

| Tab | Features |
|-----|----------|
| **Option Chain** | Full real-time chain, ATM highlighting, ITM/OTM coloring, OI bars, IV, Greeks, PCR per strike |
| **Greeks & Exposure** | GEX, DEX, Gamma Flip Level, Call/Put Wall, Vega/Theta exposure charts |
| **IV Analytics** | IV Smile, IV Rank, IV Percentile, HV comparison, Term Structure |
| **Strategy Builder** | Straddle/Strangle/Spreads/Iron Condor, payoff P&L diagram, breakeven calculation |
| **Historical** | OHLCV price and volume charts via Dhan Historical API |

## Backend Analytics Engine

All calculations implemented from scratch in Python:

- **Black-Scholes Model**: Full BS pricing (calls & puts)
- **Implied Volatility**: Newton-Raphson + bisection fallback
- **Greeks**: Delta, Gamma, Theta, Vega, Rho (single-pass d1/d2)
- **GEX**: Gamma × OI × LotSize × S² × 0.01 (dealer convention)
- **DEX**: Delta × OI × LotSize × S
- **Gamma Flip Level**: Zero-crossing of cumulative GEX
- **Max Pain**: Full payout minimization across all strikes
- **PCR (OI & Volume)**
- **VWAP**
- **Historical Volatility**: Close-to-close, annualized

---

## Quick Start

### 1. Clone & Configure

```bash
git clone <repo>
cd options-platform
cp .env.example .env
# Edit .env — add your DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN
```

### 2. Get Dhan API Credentials

1. Login at [login.dhan.co](https://login.dhan.co)
2. Go to **My Profile → API Credentials**
3. Generate an Access Token (valid 30 days)
4. Paste into `.env`

### 3. Docker (Recommended)

```bash
# Build and start all services
docker-compose up --build

# Or in background
docker-compose up --build -d

# View logs
docker-compose logs -f backend

# Stop
docker-compose down
```

Visit **http://localhost** in your browser.

---

### 4. Local Development (No Docker)

**Backend:**
```bash
cd backend
pip install -r requirements.txt
cp ../.env.example .env   # edit with your credentials
uvicorn main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install --legacy-peer-deps
npm run dev         # starts on http://localhost:3000
```

Make sure backend is running — the frontend proxies `/api` and `/ws` to `localhost:8000`.

---

## Dhan APIs Used

| API | Endpoint | Usage |
|-----|----------|-------|
| Option Chain | `GET /v2/optionchain` | Full real-time option chain |
| Expiry List | `GET /v2/optionchain/expirylist` | Available expiries |
| Market Quote | `POST /v2/marketfeed/quote` | Spot price |
| LTP Feed | `POST /v2/marketfeed/ltp` | Live last price |
| Full Market Depth | `POST /v2/marketfeed/full-depth` | 5-level bid/ask |
| Historical Charts | `POST /v2/charts/historical` | OHLCV bars |
| Expired Options | `POST /v2/optionchain/expireddata` | Backtesting data |
| Live Feed WS | `wss://api-feed.dhan.co` | Real-time tick streaming |

---

## Project Structure

```
options-platform/
├── backend/
│   ├── main.py                    # FastAPI app + WebSocket endpoint
│   ├── config.py                  # Pydantic settings
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── api/
│   │   ├── dhan_client.py         # Dhan REST + WebSocket client
│   │   └── websocket_manager.py   # Frontend WS connection manager
│   ├── calculations/
│   │   └── black_scholes.py       # Full BS engine + analytics
│   ├── core/
│   │   └── analytics_processor.py # Chain normalization + GEX/DEX
│   └── models/
│       └── schemas.py             # Pydantic schemas
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx                # Root component + tab routing
│   │   ├── main.tsx
│   │   ├── index.css
│   │   ├── components/
│   │   │   ├── ui/TopNav.tsx      # Top bar + tab nav
│   │   │   └── tabs/
│   │   │       ├── OptionChainTab.tsx
│   │   │       ├── GreeksTab.tsx
│   │   │       ├── IVAnalyticsTab.tsx
│   │   │       ├── StrategyBuilderTab.tsx
│   │   │       └── HistoricalTab.tsx
│   │   ├── hooks/
│   │   │   └── useWebSocket.ts    # Auto-reconnect WS hook
│   │   ├── store/
│   │   │   └── marketStore.ts     # Zustand global store
│   │   ├── types/index.ts         # TypeScript interfaces
│   │   └── utils/
│   │       ├── api.ts             # REST API client
│   │       └── format.ts          # Bloomberg-style formatters
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── Dockerfile
│
├── nginx/
│   ├── nginx.conf                 # Main reverse proxy
│   └── nginx.frontend.conf        # React SPA serving
│
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## REST API Reference

```
GET  /api/health              → System health + connection count
GET  /api/option-chain        → Full option chain (symbol, expiry)
GET  /api/expiries            → Available expiry dates
GET  /api/greeks-exposure     → GEX, DEX, call/put wall
GET  /api/iv-analytics        → IV smile, rank, percentile
GET  /api/market-summary      → PCR, max pain, OI totals
GET  /api/quote               → Spot price + OHLC
GET  /api/historical          → OHLCV bars
POST /api/strategy/analyze    → Payoff + strategy metrics
```

## WebSocket Protocol

**Connect:** `ws://localhost/ws`

**Client → Server messages:**
```json
{ "action": "subscribe", "channels": ["option_chain:NIFTY"] }
{ "action": "get_chain", "symbol": "NIFTY" }
{ "action": "ping" }
```

**Server → Client messages:**
```json
{ "type": "option_chain_update", "symbol": "NIFTY", "data": {...} }
{ "type": "greeks_update", "data": {...} }
{ "type": "iv_update", "data": {...} }
{ "type": "market_summary", "data": {...} }
{ "type": "tick", "security_id": "...", "ltp": 145.5 }
```

---

## Performance Notes

- Option chain rows are **virtualized** (react-window) — handles 200+ strikes smoothly
- Backend Greeks are computed **on-demand** and cached in Redis + in-memory store
- WebSocket is **single-connection per client**, multiplexed across all tabs
- Dhan feed is one persistent connection **shared** across all frontend clients
- Periodic refresh only runs when **at least one client is connected**

---

## UI Theme

| Token | Value | Usage |
|-------|-------|-------|
| `bg.primary` | `#0a0a0a` | Main background |
| `bg.panel` | `#141414` | Card/panel background |
| `accent.yellow` | `#ffcc00` | ATM, active elements |
| `market.up` | `#00c853` | Positive P&L, call side |
| `market.down` | `#ff1744` | Negative P&L, put side |
| `accent.cyan` | `#00d4ff` | IV, misc analytics |
| `text.primary` | `#f5f5f5` | Main text |
| Font | `IBM Plex Mono` | All text |
