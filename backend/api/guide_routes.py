from fastapi import APIRouter
from fastapi.responses import ORJSONResponse

guide_router = APIRouter(tags=["Guide"])


def _p(text): return {"type": "para", "text": text}
def _f(text): return {"type": "formula", "text": text}
def _ex(label, text): return {"type": "example", "label": label, "text": text}
def _sig(label, color, text): return {"type": "signal", "label": label, "color": color, "text": text}
def _tip(text): return {"type": "tip", "text": text}
def _warn(text): return {"type": "warning", "text": text}
def _tbl(headers, rows): return {"type": "table", "headers": headers, "rows": rows}


GUIDE_DATA = {
  "sections": [
    # ── SECTION 1: Options Basics ──────────────────────────────────────────────
    {
      "id": "basics",
      "title": "Options Basics",
      "icon": "📚",
      "color": "#ffcc00",
      "topics": [
        {
          "id": "what-is-option",
          "title": "What is an Option?",
          "content": [
            _p("An option is a contract that gives the buyer the RIGHT (but not obligation) to buy or sell an asset at a fixed price (Strike Price) before a specific date (Expiry). You pay a small premium to get this right."),
            _ex("Real Example", "Nifty is at 24,350. You buy a 24,500 CALL option for Rs.80. If Nifty rises to 24,700 before expiry, your option is worth Rs.200 — profit of Rs.120 per unit x 50 lot = Rs.6,000 profit on Rs.4,000 investment."),
            _tbl(["Term", "Meaning"], [
              ["CALL Option", "Right to BUY — profits when market goes UP"],
              ["PUT Option", "Right to SELL — profits when market goes DOWN"],
              ["Strike Price", "The fixed price in the contract (e.g. 24,500)"],
              ["Premium", "Price you pay to buy the option (e.g. Rs.80)"],
              ["Expiry", "Date the contract expires (weekly Thursday / monthly last Thursday)"],
              ["Lot Size", "Minimum quantity — Nifty=50, BankNifty=15, FinNifty=40"],
              ["Buyer", "Pays premium, limited loss (premium paid), unlimited profit potential"],
              ["Seller/Writer", "Receives premium, limited profit, potentially large loss"],
            ]),
          ]
        },
        {
          "id": "itm-atm-otm",
          "title": "ITM, ATM, OTM — Moneyness",
          "content": [
            _p("Moneyness tells you how far the strike price is from the current spot price. This determines intrinsic value and premium cost."),
            _tbl(["Type", "CALL Condition", "PUT Condition", "Premium"], [
              ["ITM (In The Money)", "Strike < Spot", "Strike > Spot", "Expensive — has intrinsic value"],
              ["ATM (At The Money)", "Strike = Spot", "Strike = Spot", "Moderate — highest time value"],
              ["OTM (Out of The Money)", "Strike > Spot", "Strike < Spot", "Cheap — only time value, expires worthless most often"],
            ]),
            _ex("Nifty at 24,350", "24,350 CE/PE = ATM. 24,000 CE = ITM (has Rs.350 intrinsic value). 24,700 CE = OTM (no intrinsic value, only hope premium)."),
            _tip("ATM options have the highest Gamma and Theta. OTM options are cheap but expire worthless most of the time. Beginners should avoid buying far OTM options."),
          ]
        },
        {
          "id": "option-chain-read",
          "title": "How to Read the Option Chain",
          "content": [
            _p("The Option Chain shows all available strikes for an index. CALLS are on the left, PUTS on the right, strikes in the middle. The ATM strike is highlighted in yellow."),
            _tbl(["Column", "What it means", "How to use it"], [
              ["LTP", "Last Traded Price — current market price of the option", "Higher LTP = more expensive option"],
              ["OI", "Open Interest — total outstanding contracts", "Higher OI = more interest at that strike"],
              ["OI Change", "Change in OI from previous day", "Positive = new positions being added"],
              ["Volume", "Contracts traded today", "High volume = active trading at that strike"],
              ["IV", "Implied Volatility — market's expectation of future movement (%)", "Higher IV = more expensive options"],
              ["Delta", "How much option price moves per Rs.1 move in spot", "0.5 = ATM, 0.9 = deep ITM, 0.1 = far OTM"],
              ["Gamma", "Rate of change of Delta", "Highest at ATM, accelerates near expiry"],
              ["Theta", "Daily time decay — premium lost per day", "Always negative for buyers, positive for sellers"],
              ["Vega", "Sensitivity to IV change", "Higher Vega = more sensitive to volatility changes"],
            ]),
            _sig("BULLISH SIGNAL", "#00c853", "High PUT OI at lower strikes + Low CALL OI = Strong support below, market likely to stay up."),
            _sig("BEARISH SIGNAL", "#ff1744", "High CALL OI at upper strikes + Low PUT OI = Strong resistance above, market likely to stay down."),
          ]
        },
      ]
    },
    # ── SECTION 2: Greeks ──────────────────────────────────────────────────────
    {
      "id": "greeks",
      "title": "Greeks & Exposure",
      "icon": "🔢",
      "color": "#00d4ff",
      "topics": [
        {
          "id": "delta",
          "title": "Delta — Directional Exposure",
          "content": [
            _p("Delta measures how much an option price changes for every Rs.1 move in the underlying. It ranges from 0 to 1 for calls, -1 to 0 for puts. Think of it as the probability of expiring ITM."),
            _tbl(["Delta Value", "Meaning", "Example (Nifty +100)"], [
              ["0.5 (ATM Call)", "Option moves Rs.0.50 per Rs.1 spot move", "Call gains Rs.50"],
              ["0.9 (Deep ITM Call)", "Moves almost like the stock itself", "Call gains Rs.90"],
              ["0.1 (Far OTM Call)", "Barely moves", "Call gains Rs.10"],
              ["-0.5 (ATM Put)", "Put gains Rs.0.50 when spot falls Rs.1", "Put gains Rs.50 when Nifty falls 100"],
            ]),
            _f("DEX (Delta Exposure) = Delta x OI x Lot Size x Spot Price"),
            _ex("DEX Interpretation", "Positive DEX = Dealers are net LONG delta (bullish positioning). Negative DEX = Dealers are net SHORT delta (bearish). Large positive DEX near a strike = that strike acts as a magnet for price."),
            _tip("Delta also tells you how many shares of the underlying you are effectively holding. Buying 1 ATM call (delta=0.5) on Nifty is like holding 0.5 x 50 = 25 units of Nifty."),
          ]
        },
        {
          "id": "gamma",
          "title": "Gamma — The Acceleration of Delta",
          "content": [
            _p("Gamma tells you how fast Delta changes. High Gamma = Delta changes rapidly with spot moves. ATM options have the highest Gamma. Gamma is the most important Greek for understanding market stability."),
            _f("GEX (Gamma Exposure) = Gamma x OI x Lot Size x Spot^2 x 0.01"),
            _tbl(["GEX Sign", "Dealer Position", "Market Behavior", "What to expect"], [
              ["Positive GEX (+)", "Dealers are LONG Gamma", "Market stabilizes — dealers sell rallies, buy dips", "Range-bound, mean-reverting"],
              ["Negative GEX (-)", "Dealers are SHORT Gamma", "Market amplifies moves — dealers buy rallies, sell dips", "Trending, volatile, breakouts"],
            ]),
            _sig("GAMMA FLIP 🔄", "#ff9100", "When GEX crosses from positive to negative (or vice versa), it is called a Gamma Flip. This is a major volatility event — expect a breakout or breakdown. The Gamma Flip level is the most important price level to watch."),
            _ex("Real Example", "Nifty GEX = +2,500 Cr means dealers are long gamma. They will sell if Nifty rises and buy if it falls — Nifty stays in a range. If GEX flips to -500 Cr, dealers now amplify moves — breakout likely."),
          ]
        },
        {
          "id": "theta",
          "title": "Theta — Time Decay (The Silent Killer)",
          "content": [
            _p("Theta is the daily erosion of an option value due to time passing. It is always negative for option buyers and positive for sellers. Time decay accelerates as expiry approaches — especially in the last week."),
            _tbl(["Scenario", "Impact on You"], [
              ["Buying options", "You LOSE theta every day — time works against you"],
              ["Selling options", "You EARN theta every day — time works for you"],
              ["ATM options", "Highest theta decay — most sensitive to time"],
              ["Near expiry (last 3 days)", "Theta accelerates dramatically — OTM options lose value very fast"],
              ["Far from expiry (30+ days)", "Theta is slow — gives you time to be right"],
            ]),
            _tip("Total Theta shown in the Greeks tab = total daily decay of all open positions in the market. Large negative theta = market is paying sellers Rs.X crores per day. This is why option selling has a structural edge."),
            _warn("Never hold OTM options into expiry week unless you have a strong directional view. Theta will destroy your premium even if the market moves slightly in your favor."),
          ]
        },
        {
          "id": "vega",
          "title": "Vega — Volatility Sensitivity",
          "content": [
            _p("Vega measures how much an option price changes for every 1% change in Implied Volatility (IV). High Vega = option is very sensitive to IV changes. ATM options have the highest Vega."),
            _tbl(["Scenario", "Effect on Option Price"], [
              ["IV rises 1%", "Option price increases by Vega amount"],
              ["IV falls 1%", "Option price decreases by Vega amount"],
              ["ATM options", "Highest Vega — most sensitive to IV"],
              ["Near expiry", "Vega decreases — less time for IV to matter"],
              ["Far from expiry", "High Vega — IV changes have big impact"],
            ]),
            _sig("VEGA STRATEGY ⚡", "#00d4ff", "When IV is HIGH (IV Rank > 70) — Sell options (collect high premium, Vega works against buyers). When IV is LOW (IV Rank < 20) — Buy options (cheap premium, Vega works for buyers if IV expands)."),
            _ex("IV Crush Example", "Before RBI policy, Nifty ATM option costs Rs.200 (high IV). After policy announcement, IV collapses — same option now costs Rs.80 even if Nifty barely moved. This is IV crush — it destroys option buyers who bought before events."),
          ]
        },
      ]
    },
    # ── SECTION 3: IV Analytics ────────────────────────────────────────────────
    {
      "id": "iv",
      "title": "IV Analytics",
      "icon": "📊",
      "color": "#ff9100",
      "topics": [
        {
          "id": "what-is-iv",
          "title": "Implied Volatility (IV) — What It Means",
          "content": [
            _p("IV is the market forecast of how much the underlying will move. It is derived from option prices using Black-Scholes. High IV = market expects big moves. Low IV = market expects calm. IV is expressed as an annualized percentage."),
            _tbl(["IV Level", "Meaning", "Best Strategy"], [
              ["IV below 10%", "Very calm market", "Buy options — cheap, potential for expansion"],
              ["IV 10-15%", "Normal market", "Neutral strategies work well"],
              ["IV 15-25%", "Elevated volatility", "Sell premium cautiously"],
              ["IV above 25%", "High fear / event driven", "Sell premium aggressively (if experienced)"],
            ]),
            _ex("India VIX vs Nifty IV", "India VIX at 12 means Nifty expected to move +/-12% annually = +/-3.4% monthly = +/-1.1% weekly. If Nifty is at 24,350, weekly expected range = +/-268 points (24,082 to 24,618)."),
            _tip("India VIX is the fear gauge. VIX above 20 = high fear = good time to sell premium. VIX below 12 = complacency = good time to buy options as protection."),
          ]
        },
        {
          "id": "iv-rank",
          "title": "IV Rank & IV Percentile — Is IV High or Low?",
          "content": [
            _p("IV Rank and IV Percentile tell you whether current IV is HIGH or LOW compared to its own history. This is more useful than raw IV because it gives context."),
            _f("IV Rank = (Current IV - Min IV over period) / (Max IV - Min IV) x 100"),
            _f("IV Percentile = % of days in past year where IV was BELOW current IV"),
            _tbl(["IV Rank", "Interpretation", "Action"], [
              ["0-20", "IV is historically LOW", "Buy options — cheap relative to history"],
              ["20-50", "IV is moderate", "Neutral — no strong edge"],
              ["50-80", "IV is elevated", "Consider selling premium"],
              ["80-100", "IV is historically HIGH", "Strong sell premium signal"],
            ]),
            _sig("KEY INSIGHT 💡", "#ffcc00", "IV Rank > 70 + Positive GEX = Strong SELL PREMIUM signal. IV Rank < 20 + Negative GEX = Strong BUY OPTIONS signal. These are the highest conviction setups."),
          ]
        },
        {
          "id": "iv-smile",
          "title": "IV Smile — Reading the Volatility Curve",
          "content": [
            _p("The IV Smile chart shows IV across different strikes. In Indian markets, it typically forms a smirk — higher IV for OTM puts (fear of downside) than OTM calls. This is called negative skew."),
            _tbl(["Shape", "Meaning", "Market Sentiment"], [
              ["Flat smile", "Market is calm, no directional fear", "Neutral"],
              ["Left skew (puts expensive)", "Market fears downside", "Bearish bias"],
              ["Right skew (calls expensive)", "Market expects upside", "Bullish bias"],
              ["Steep smile", "High uncertainty, big move expected", "Event-driven volatility"],
            ]),
            _ex("Reading the Smile", "If 24,000 PE has IV = 22% and 24,700 CE has IV = 14%, the skew is negative (put skew). Market is paying more for downside protection — bearish bias. IV Skew = Put IV - Call IV. Positive skew = bearish fear."),
          ]
        },
        {
          "id": "hv-vs-iv",
          "title": "HV vs IV — The Edge for Options Traders",
          "content": [
            _p("Historical Volatility (HV) is what the market ACTUALLY moved. IV is what the market EXPECTS to move. The spread between them is the edge for options traders."),
            _f("IV-HV Spread = IV - HV (positive = options overpriced, negative = options cheap)"),
            _tbl(["Condition", "Meaning", "Trade"], [
              ["IV >> HV (spread > 3%)", "Options overpriced vs reality", "SELL premium — collect inflated IV"],
              ["IV = HV (spread near 0)", "Fair value", "No clear edge"],
              ["IV << HV (spread < -3%)", "Options cheap vs reality", "BUY options — cheap relative to actual moves"],
            ]),
            _sig("STRUCTURAL EDGE 📈", "#00c853", "Statistically, IV > HV about 80% of the time. This is why option selling has a structural edge — you are collecting the volatility risk premium. But the 20% of times when IV < HV, moves are violent and can wipe out sellers."),
          ]
        },
      ]
    },
    # ── SECTION 4: PCR & OI Analysis ──────────────────────────────────────────
    {
      "id": "pcr",
      "title": "PCR & OI Analysis",
      "icon": "⚖️",
      "color": "#00c853",
      "topics": [
        {
          "id": "pcr",
          "title": "Put-Call Ratio (PCR) — Contrarian Indicator",
          "content": [
            _p("PCR = Total Put OI / Total Call OI. It measures the ratio of bearish bets (puts) to bullish bets (calls). It is a CONTRARIAN indicator — extreme readings signal the opposite move."),
            _f("PCR = Total Put OI / Total Call OI"),
            _tbl(["PCR Value", "Sentiment", "Contrarian Signal", "Action"], [
              ["PCR > 1.5", "Extreme bearishness", "BULLISH — too many bears, market likely to bounce", "Look for long setups"],
              ["PCR 1.2-1.5", "Bearish", "Mildly bullish — put writers have edge", "Sell puts or buy calls"],
              ["PCR 0.8-1.2", "Neutral", "No clear signal", "Wait for extremes"],
              ["PCR 0.5-0.8", "Bullish", "Mildly bearish — call writers have edge", "Sell calls or buy puts"],
              ["PCR < 0.5", "Extreme bullishness", "BEARISH — too many bulls, market likely to fall", "Look for short setups"],
            ]),
            _ex("Example", "PCR = 1.35 means more puts than calls. Market is fearful. Contrarian signal: market may rally as put sellers defend their positions and short-covering occurs."),
            _warn("PCR alone is not enough. Always combine with GEX, IV Rank, and price action for confirmation. PCR works best at extremes (above 1.4 or below 0.6)."),
          ]
        },
        {
          "id": "max-pain",
          "title": "Max Pain — Where Market Wants to Close",
          "content": [
            _p("Max Pain is the strike price at which the maximum number of options (both calls and puts) expire worthless. Option writers (sellers) profit most when price closes at Max Pain on expiry."),
            _p("Since option writers (institutions, market makers) have more capital and influence, price tends to gravitate toward Max Pain as expiry approaches — especially in the last 2 days before expiry."),
            _tbl(["Scenario", "Implication", "Expected Move"], [
              ["Spot > Max Pain", "Calls are in pain — call buyers losing", "Market may drift DOWN toward Max Pain"],
              ["Spot < Max Pain", "Puts are in pain — put buyers losing", "Market may drift UP toward Max Pain"],
              ["Spot = Max Pain", "Equilibrium — both sides losing equally", "Market likely to stay range-bound"],
            ]),
            _tip("Max Pain is most reliable on expiry day (Thursday for weekly). Use it as a target, not a trigger. In the last 30 minutes of expiry, price often pins to Max Pain."),
          ]
        },
        {
          "id": "oi-buildup",
          "title": "OI Buildup — Reading New Positions",
          "content": [
            _p("OI Change tells you whether new positions are being added or old ones are being closed. Combined with price direction, it reveals the nature of the move and conviction behind it."),
            _tbl(["Price", "OI Change", "Classification", "Meaning", "Strength"], [
              ["Rising", "Increasing", "LONG BUILDUP", "Bulls adding new longs", "STRONG BULLISH"],
              ["Falling", "Increasing", "SHORT BUILDUP", "Bears adding new shorts", "STRONG BEARISH"],
              ["Rising", "Decreasing", "SHORT COVERING", "Bears exiting (forced)", "WEAK BULLISH"],
              ["Falling", "Decreasing", "LONG UNWINDING", "Bulls exiting (profit booking)", "WEAK BEARISH"],
            ]),
            _sig("STRONGEST SIGNALS 🎯", "#00c853", "Long Buildup at support = Strong bullish conviction. Short Buildup at resistance = Strong bearish conviction. These are the highest conviction signals because new money is entering the market."),
          ]
        },
        {
          "id": "call-put-wall",
          "title": "Call Wall & Put Wall — Key Levels",
          "content": [
            _p("Call Wall = Strike with highest Call OI. Put Wall = Strike with highest Put OI. These act as strong resistance and support levels because option sellers actively defend these levels."),
            _tbl(["Level", "Role", "Why it works", "How to trade"], [
              ["Call Wall", "RESISTANCE", "Huge call sellers defend this level — they sell more calls if price approaches, capping upside", "Sell calls at or near Call Wall"],
              ["Put Wall", "SUPPORT", "Huge put sellers defend this level — they buy futures if price falls here, providing support", "Sell puts at or near Put Wall"],
            ]),
            _ex("Example", "Call Wall at 24,500 + Put Wall at 24,000 means market expected to trade in 24,000-24,500 range. If Nifty breaks above 24,500 with high volume, the Call Wall is breached — next target is the next major Call OI strike (e.g. 24,700)."),
            _tip("When spot is between Call Wall and Put Wall, the market is in a stable zone. When it breaks either wall, expect acceleration in that direction."),
          ]
        },
      ]
    },
    # ── SECTION 5: Decision Engine ─────────────────────────────────────────────
    {
      "id": "decision",
      "title": "Decision Engine",
      "icon": "🎯",
      "color": "#ff1744",
      "topics": [
        {
          "id": "signal-matrix",
          "title": "Signal Matrix — How Signals Are Generated",
          "content": [
            _p("The Decision Engine combines IV, HV, IV Rank, and GEX to generate a structured trade signal. It never generates a signal when data is insufficient or market is closed."),
            _tbl(["Condition", "Signal", "Meaning", "Action"], [
              ["IV > HV AND IV Rank > 50 AND GEX > 0", "SELL OPTIONS", "Options overpriced + market stabilizing", "Sell straddle/strangle/iron condor"],
              ["IV < HV AND IV Rank < 20 AND GEX < 0", "BUY OPTIONS", "Options cheap + volatile market", "Buy ATM calls or puts based on direction"],
              ["HV = 0 OR IV = 0 OR Regime = INSUFFICIENT", "NO TRADE", "Not enough data to make a decision", "Wait for more data to accumulate"],
              ["Market Closed", "NO TRADE", "Signals disabled outside trading hours", "Check signals during market hours only"],
              ["Conditions not met", "NO TRADE", "No clear edge — mixed signals", "Stay out, preserve capital"],
            ]),
            _warn("NO TRADE is a valid and often the BEST signal. Forcing a trade when conditions are unclear is how most traders lose money. The system saying NO TRADE is protecting your capital."),
          ]
        },
        {
          "id": "confidence-score",
          "title": "Confidence Score — How Strong is the Signal?",
          "content": [
            _p("The confidence score (0-100%) measures how strong the signal is based on multiple factors. Higher confidence = more factors aligned = higher probability trade."),
            _tbl(["Factor", "Weight", "What it measures"], [
              ["IV/HV Spread", "40%", "How overpriced/underpriced options are vs actual volatility"],
              ["IV Rank Extremity", "30%", "How far IV Rank is from 50 (neutral) — extremes are more reliable"],
              ["GEX Magnitude", "20%", "How strong the dealer positioning is — larger GEX = stronger signal"],
              ["VWAP Alignment", "10%", "Whether price is above/below VWAP — confirms directional bias"],
            ]),
            _tip("Confidence > 70% = High conviction signal, consider full position. 50-70% = Moderate, consider half position. Below 50% = Weak signal, wait for better setup or skip."),
          ]
        },
        {
          "id": "market-regime",
          "title": "Market Regime — What Kind of Market Are We In?",
          "content": [
            _p("The regime engine classifies the market using volatility, entropy (randomness), and trend strength. Different regimes require completely different strategies."),
            _tbl(["Regime", "Characteristics", "Best Strategy", "Avoid"], [
              ["TRENDING", "Low entropy, directional move, Hurst > 0.5", "Follow trend — buy calls in uptrend, puts in downtrend", "Selling premium against the trend"],
              ["RANGE_BOUND", "High entropy, low volatility, price oscillating", "Sell premium — Iron Condor, Short Straddle", "Buying directional options"],
              ["VOLATILE", "Low entropy, high volatility, strong moves", "Directional options — buy ATM calls/puts", "Short straddles (unlimited risk)"],
              ["CHAOTIC", "High entropy, high volatility, no direction", "Reduce position size, wait for clarity", "Any large position"],
              ["INSUFFICIENT_DATA", "Not enough price history", "Wait — do not trade", "Everything"],
            ]),
            _ex("Regime Example", "Regime = RANGE_BOUND + IV Rank = 75 + GEX = +2,000 Cr. This is the ideal setup for selling premium. Sell a 24,000-24,700 Iron Condor and collect premium while market stays in range."),
          ]
        },
        {
          "id": "vwap-signal",
          "title": "VWAP — Intraday Institutional Benchmark",
          "content": [
            _p("VWAP (Volume Weighted Average Price) is the average price weighted by volume. It is the institutional benchmark — institutions buy below VWAP and sell above it. It resets every trading day at 9:15 AM."),
            _f("VWAP = Sum(Price x Volume) / Sum(Volume)"),
            _tbl(["Price vs VWAP", "Signal", "Implication", "Action"], [
              ["Price > VWAP", "BULLISH", "Institutions are net buyers — upward bias", "Favor call buying or put selling"],
              ["Price < VWAP", "BEARISH", "Institutions are net sellers — downward bias", "Favor put buying or call selling"],
              ["Price = VWAP", "AT_VWAP", "Equilibrium — wait for breakout", "Wait for direction"],
            ]),
            _ex("VWAP Bands", "The +/-1 sigma bands contain about 68% of price action. If price is above +1 sigma band, it is extended — potential mean reversion. If price is below -1 sigma band, it is oversold — potential bounce."),
          ]
        },
      ]
    },
    # ── SECTION 6: Intelligence Tab ────────────────────────────────────────────
    {
      "id": "intelligence",
      "title": "Intelligence Tab",
      "icon": "🧠",
      "color": "#9c27b0",
      "topics": [
        {
          "id": "timeseries",
          "title": "Time-Series Intelligence — Tracking Changes",
          "content": [
            _p("The time-series panel tracks how GEX, DEX, and IV change over time. Trends in these values are more important than single snapshots. A single GEX reading tells you the current state; the trend tells you where it is going."),
            _tbl(["Metric", "Rising Trend Means", "Falling Trend Means"], [
              ["GEX", "Dealers getting longer gamma — market stabilizing", "Dealers losing gamma — volatility risk increasing"],
              ["DEX", "Net delta increasing — bullish positioning building", "Net delta decreasing — bearish positioning building"],
              ["IV", "Fear increasing — options getting expensive", "Fear decreasing — options getting cheaper"],
              ["Delta GEX", "Positive = gamma being added (stabilizing)", "Negative = gamma being removed (destabilizing)"],
            ]),
            _tip("Delta GEX (change in GEX) is more important than GEX level. A sudden large negative Delta GEX means dealers are rapidly losing gamma — expect a volatility spike soon."),
          ]
        },
        {
          "id": "expected-move",
          "title": "Expected Move — Market Range Forecast",
          "content": [
            _p("Expected Move calculates the market implied price range for the current expiry based on ATM IV and days to expiry. This is what the options market is pricing in as the likely range."),
            _f("Expected Move = Spot x IV x sqrt(DTE / 365)"),
            _ex("Example Calculation", "Nifty = 24,350, IV = 15%, DTE = 7 days. EM = 24,350 x 0.15 x sqrt(7/365) = 24,350 x 0.15 x 0.138 = +/-504 points. Market expects Nifty to stay between 23,846 and 24,854 with 68% probability."),
            _tbl(["Band", "Probability", "Use Case"], [
              ["+/-1 sigma (1 std dev)", "68.27%", "Core range — sell options outside this range for high probability trades"],
              ["+/-2 sigma (2 std dev)", "95.45%", "Extreme range — very unlikely to breach, use for very wide spreads"],
            ]),
            _tip("If you sell a strangle at the 1-sigma levels, you have a 68% probability of profit. If you sell at 2-sigma levels, you have a 95% probability of profit but collect less premium."),
          ]
        },
        {
          "id": "oi-heatmap",
          "title": "OI Heatmap — Visualizing Concentration",
          "content": [
            _p("The OI heatmap shows call and put OI intensity across strikes. Wider bars = more OI = stronger support/resistance. The heatmap gives you a visual picture of where the market is concentrated."),
            _tbl(["What to look for", "Interpretation", "Action"], [
              ["Thick call bar at a strike", "Strong resistance — sellers defending that level", "Sell calls at or near that strike"],
              ["Thick put bar at a strike", "Strong support — sellers defending that level", "Sell puts at or near that strike"],
              ["Equal call and put bars", "Balanced market — no directional bias", "Sell straddle at that strike"],
              ["IV Skew (put IV > call IV)", "Market fears downside more — bearish bias", "Buy puts or sell calls"],
            ]),
          ]
        },
        {
          "id": "smart-signal",
          "title": "Smart Signal — Independent Signal Layer",
          "content": [
            _p("The Smart Signal is independent of the Decision Engine. It combines IV Regime, GEX, OI Flow, VWAP, and PCR into a single directional signal with a confidence score."),
            _tbl(["Signal", "Meaning", "Suggested Action"], [
              ["SELL_PREMIUM", "Multiple factors favor option sellers", "Sell straddle/strangle or iron condor"],
              ["BUY_OPTIONS", "Multiple factors favor option buyers", "Buy ATM calls or puts based on direction"],
              ["MILD_SELL_BIAS", "Weak sell signal", "Small position or wait for confirmation"],
              ["MILD_BUY_BIAS", "Weak buy signal", "Small position or wait for confirmation"],
              ["NEUTRAL", "No clear edge", "Stay out — preserve capital"],
            ]),
            _warn("The Smart Signal is a tool, not a guarantee. Always use it in conjunction with your own analysis. Never risk more than 2% of your capital on any single trade."),
          ]
        },
      ]
    },
    # ── SECTION 7: Strategy Builder ────────────────────────────────────────────
    {
      "id": "strategy",
      "title": "Strategy Builder",
      "icon": "🏗️",
      "color": "#00c853",
      "topics": [
        {
          "id": "common-strategies",
          "title": "Common Options Strategies",
          "content": [
            _tbl(["Strategy", "When to Use", "Max Profit", "Max Loss", "IV Rank"], [
              ["Long Call", "Strong bullish view, low IV", "Unlimited", "Premium paid", "Below 30"],
              ["Long Put", "Strong bearish view, low IV", "Strike - 0", "Premium paid", "Below 30"],
              ["Short Straddle", "Range-bound, high IV", "Premium collected", "Unlimited", "Above 70"],
              ["Short Strangle", "Range-bound, high IV, wider range", "Premium collected", "Unlimited", "Above 60"],
              ["Bull Call Spread", "Moderately bullish, lower cost", "Spread width - debit", "Debit paid", "Any"],
              ["Bear Put Spread", "Moderately bearish, lower cost", "Spread width - debit", "Debit paid", "Any"],
              ["Iron Condor", "Range-bound, high IV, defined risk", "Net premium", "Spread width - premium", "Above 60"],
              ["Iron Butterfly", "Very range-bound, very high IV", "Net premium", "Spread width - premium", "Above 70"],
            ]),
            _sig("WHEN TO USE EACH 💡", "#00d4ff", "High IV Rank (above 70) + Range-bound regime = Short Straddle/Strangle/Iron Condor. Low IV Rank (below 20) + Trending regime = Long Call/Put or Bull/Bear Spread."),
          ]
        },
        {
          "id": "payoff-chart",
          "title": "Reading the Payoff Chart",
          "content": [
            _p("The payoff chart shows your profit/loss at different spot prices at expiry. The X-axis is spot price, Y-axis is P&L. Understanding this chart is essential before entering any trade."),
            _tbl(["Chart Feature", "Meaning", "What to check"], [
              ["Breakeven points", "Where the line crosses zero", "Make sure breakevens are realistic"],
              ["Peak of chart", "Maximum profit point", "Is the reward worth the risk?"],
              ["Trough of chart", "Maximum loss point", "Can you afford this loss?"],
              ["Flat line", "Range where P&L does not change", "This is your profit zone for spreads"],
              ["Steep slope", "High delta — P&L changes rapidly with spot", "High risk/reward but also high risk"],
            ]),
            _warn("Always check: Is my max loss acceptable? Can I afford to hold if the trade goes against me? Never risk more than 2% of capital on a single trade. Position sizing is more important than strategy selection."),
          ]
        },
        {
          "id": "strategy-selection",
          "title": "How to Select the Right Strategy",
          "content": [
            _p("Strategy selection depends on three things: your market view (direction), IV environment (high or low), and risk tolerance (defined or undefined risk)."),
            _tbl(["Market View", "IV Environment", "Recommended Strategy"], [
              ["Strongly Bullish", "Low IV (below 30)", "Buy ATM Call or Bull Call Spread"],
              ["Strongly Bearish", "Low IV (below 30)", "Buy ATM Put or Bear Put Spread"],
              ["Mildly Bullish", "High IV (above 60)", "Sell OTM Put or Bull Put Spread"],
              ["Mildly Bearish", "High IV (above 60)", "Sell OTM Call or Bear Call Spread"],
              ["Neutral / Range-bound", "High IV (above 60)", "Iron Condor or Short Strangle"],
              ["Neutral / Range-bound", "Low IV (below 30)", "Long Straddle (expecting big move)"],
              ["Uncertain direction", "Very High IV (above 80)", "Iron Butterfly at ATM"],
            ]),
            _tip("The most common mistake beginners make is buying OTM options when IV is high. This is the worst possible trade — you are paying inflated premium for an option that needs a large move to profit."),
          ]
        },
      ]
    },
    # ── SECTION 8: Market Scenarios ────────────────────────────────────────────
    {
      "id": "scenarios",
      "title": "Market Scenarios",
      "icon": "🎲",
      "color": "#e91e63",
      "topics": [
        {
          "id": "bullish",
          "title": "When Will Market Go UP?",
          "content": [
            _sig("BULLISH CHECKLIST ✅", "#00c853", "All or most of these should be true for a high-conviction bullish trade:"),
            _tbl(["Indicator", "Bullish Reading", "Why it matters"], [
              ["PCR", "Above 1.2 (contrarian) or rising from low levels", "Too many bears = contrarian bullish"],
              ["GEX", "Positive and increasing", "Dealers will buy dips, stabilizing market"],
              ["OI Flow", "Long Buildup at support strikes", "New money entering on the long side"],
              ["IV Rank", "Low (below 30) — options cheap", "Good time to buy calls"],
              ["VWAP", "Price above VWAP", "Institutions are net buyers"],
              ["Regime", "TRENDING or RANGE_BOUND", "Predictable market behavior"],
              ["Max Pain", "Spot below Max Pain — gravitates up", "Option writers will push price up"],
              ["Put Wall", "Strong put wall below current price", "Sellers defending support"],
            ]),
            _ex("Bullish Setup Example", "Nifty at 24,200. PCR = 1.4 (high fear). GEX = +1,800 Cr (positive). Long Buildup at 24,000 PE. IV Rank = 25 (low). Price above VWAP. Max Pain = 24,400. RESULT: Strong bullish setup. Buy 24,300 CE or 24,200-24,500 Bull Call Spread."),
          ]
        },
        {
          "id": "bearish",
          "title": "When Will Market Go DOWN?",
          "content": [
            _sig("BEARISH CHECKLIST ✅", "#ff1744", "All or most of these should be true for a high-conviction bearish trade:"),
            _tbl(["Indicator", "Bearish Reading", "Why it matters"], [
              ["PCR", "Below 0.7 (contrarian) or falling from high levels", "Too many bulls = contrarian bearish"],
              ["GEX", "Negative or flipping negative", "Dealers will sell rallies, amplifying downside"],
              ["OI Flow", "Short Buildup at resistance strikes", "New money entering on the short side"],
              ["IV Rank", "Low (below 30) — options cheap", "Good time to buy puts"],
              ["VWAP", "Price below VWAP", "Institutions are net sellers"],
              ["Regime", "VOLATILE or CHAOTIC", "Market is in a downtrend or breakdown"],
              ["Max Pain", "Spot above Max Pain — gravitates down", "Option writers will push price down"],
              ["Call Wall", "Strong call wall above current price", "Sellers defending resistance"],
            ]),
            _ex("Bearish Setup Example", "Nifty at 24,600. PCR = 0.6 (low fear). GEX = -800 Cr (negative). Short Buildup at 24,700 CE. IV Rank = 20 (low). Price below VWAP. Max Pain = 24,300. RESULT: Bearish setup. Buy 24,500 PE or 24,500-24,200 Bear Put Spread."),
          ]
        },
        {
          "id": "neutral",
          "title": "When Will Market Stay NEUTRAL (Range-Bound)?",
          "content": [
            _sig("RANGE-BOUND CHECKLIST ✅", "#ff9100", "Ideal conditions for premium selling strategies:"),
            _tbl(["Indicator", "Range-Bound Reading", "Why it matters"], [
              ["GEX", "Large positive (above +1,000 Cr)", "Dealers will pin the market in a range"],
              ["IV Rank", "High (above 60)", "Sell expensive premium"],
              ["Regime", "RANGE_BOUND", "Market is oscillating, not trending"],
              ["PCR", "Near 1.0 — balanced", "No extreme sentiment"],
              ["Call Wall and Put Wall", "Close together — tight range defined", "Clear boundaries for the range"],
              ["Max Pain", "Between Call Wall and Put Wall", "Price will gravitate to this level"],
            ]),
            _ex("Range-Bound Setup Example", "Nifty at 24,350. GEX = +3,000 Cr. IV Rank = 75. Call Wall = 24,500. Put Wall = 24,000. Regime = RANGE_BOUND. RESULT: Sell 24,500 CE + 24,000 PE (Short Strangle). Collect premium, profit if Nifty stays between 24,000-24,500."),
          ]
        },
        {
          "id": "no-trade",
          "title": "When NOT to Trade? (Most Important Lesson)",
          "content": [
            _warn("The most important skill in trading is knowing when NOT to trade. Preserving capital is more important than making money. Most traders lose because they trade too often, not too little."),
            _tbl(["Condition", "Why to Avoid", "What to do instead"], [
              ["Regime = CHAOTIC", "Market is random — no edge exists", "Wait for regime to clarify"],
              ["INSUFFICIENT_DATA", "System does not have enough history", "Wait for more data to accumulate"],
              ["Market Closed", "No live data — signals are stale", "Check signals during market hours only"],
              ["IV Rank = 50 (neutral)", "No clear IV edge — wait for extremes", "Wait for IV Rank above 70 or below 20"],
              ["GEX near zero", "No clear dealer positioning — unpredictable", "Wait for GEX to build in one direction"],
              ["Major event upcoming", "RBI policy, Budget, Elections — IV spikes unpredictably", "Avoid new positions 2 days before events"],
              ["Confidence below 50%", "Weak signal — risk/reward not favorable", "Wait for higher confidence setup"],
              ["You are emotional", "Fear or greed leads to bad decisions", "Step away from the screen"],
            ]),
            _tip("Rule of thumb: If you cannot clearly explain WHY you are taking a trade in one sentence, do not take it. The best traders miss many trades. The worst traders take every trade."),
          ]
        },
      ]
    },
    # ── SECTION 9: Historical Data ─────────────────────────────────────────────
    {
      "id": "historical",
      "title": "Historical Data",
      "icon": "📈",
      "color": "#607d8b",
      "topics": [
        {
          "id": "reading-charts",
          "title": "Reading OHLCV Charts",
          "content": [
            _tbl(["Term", "Meaning", "How to use"], [
              ["Open (O)", "First price of the session", "Gap up/down from previous close shows overnight sentiment"],
              ["High (H)", "Highest price during the session", "Resistance level — sellers appeared here"],
              ["Low (L)", "Lowest price during the session", "Support level — buyers appeared here"],
              ["Close (C)", "Last price of the session", "Most important price — determines daily candle color"],
              ["Volume (V)", "Number of contracts/shares traded", "High volume = conviction, Low volume = weak move"],
            ]),
            _p("Use historical data to identify support/resistance levels, trend direction, and volatility patterns. High volume at a price level = strong support/resistance because many traders have positions there."),
            _tip("For options, use 1-min or 5-min charts for intraday. Use daily charts for swing trades. Use weekly charts for positional trades. The higher the timeframe, the more reliable the signal."),
          ]
        },
        {
          "id": "intervals",
          "title": "Which Interval to Use?",
          "content": [
            _tbl(["Interval", "Best For", "Noise Level", "Signals per Day"], [
              ["1 Min", "Scalping, very short-term", "Very high — many false signals", "50-100+"],
              ["5 Min", "Intraday trading", "High — use with caution", "20-40"],
              ["15 Min", "Intraday swing", "Moderate — good for most traders", "8-15"],
              ["1 Hour", "Short-term positional", "Low — cleaner signals", "2-5"],
              ["Daily", "Swing trading (days to weeks)", "Very low — most reliable", "1"],
            ]),
            _warn("Beginners should start with 15-min or 1-hour charts. Lower timeframes require faster decision-making and are more susceptible to noise and false signals."),
          ]
        },
      ]
    },

    # ── SECTION 10: Stock Screener ─────────────────────────────────────────────
    {
      "id": "screener",
      "title": "Stock Screener",
      "icon": "⚡",
      "color": "#00c853",
      "topics": [
        {
          "id": "screener-overview",
          "title": "What is the Stock Screener?",
          "content": [
            _p("The Stock Screener is a quantitative engine that analyzes 335+ NSE stocks using 5 years of daily price data. It computes 20+ features, scores each stock out of 10, and ranks them by a composite score. All calculations are purely mathematical — no AI, no guesswork."),
            _tbl(["Component", "What it does", "Data source"], [
              ["Feature Engine", "Computes MA, ROC, RS, volatility, ATR, z-score, VWAP", "5-year daily price candles"],
              ["Signal Engine", "Scores stock 0-10 based on 6 conditions + regime adjustment", "Features + market regime"],
              ["Monte Carlo", "Simulates 5000 price paths to estimate probability of profit", "Historical log returns"],
              ["Backtest", "Walk-forward test of the signal over 5 years", "Historical candles"],
              ["Ranking", "Composite rank = 30% score + 20% RS + 20% confidence + 30% prob_up", "All above"],
            ]),
            _tip("The pipeline runs every day at 15:35 IST (5 min after market close) to fetch today's candle and recompute all signals. During market hours, live prices update every 30 seconds automatically."),
          ]
        },
        {
          "id": "screener-score",
          "title": "Score (0-10) — How It's Calculated",
          "content": [
            _p("Each stock gets a base score from 6 conditions, then adjusted for market regime, overbought status, and liquidity. Maximum score is 10."),
            _tbl(["Condition", "Points", "Threshold", "What it means"], [
              ["Price > MA200", "+2", "Price above 200-day moving average", "Long-term uptrend confirmed"],
              ["MA50 > MA200 (Golden Cross)", "+2", "50-day MA above 200-day MA", "Trend momentum confirmed"],
              ["ROC 1Y > 25%", "+2", "1-year return > 25%", "Strong outperformance vs market"],
              ["RS > 1.2", "+2", "Relative Strength vs NIFTY > 1.2x", "Beating NIFTY by 20%+"],
              ["Drawdown < 15%", "+1", "Less than 15% off 52-week high", "Near highs, not broken"],
              ["Vol Stable + Sigma < 30%", "+1", "Volatility stable and < 30% annualized", "Controlled risk"],
            ]),
            _tbl(["Adjustment", "Effect", "Condition"], [
              ["TRENDING market", "+1", "65%+ stocks above MA200"],
              ["MIXED market", "-1", "45-65% stocks above MA200"],
              ["SIDEWAYS market", "-2", "< 45% stocks above MA200"],
              ["BEARISH market", "-3", "Extreme breadth weakness"],
              ["Overbought (z-score > 2)", "-2", "Price > 2 std deviations above 20-day mean"],
              ["Low liquidity (< 5Cr/day)", "-2", "Average daily turnover below 5 Crore"],
              ["Below MA50", "-1", "Price below short-term trend"],
            ]),
            _sig("STRONG BUY", "#00c853", "Score 8-10: All major conditions met. High conviction setup."),
            _sig("BUY", "#69f0ae", "Score 6-7: Most conditions met. Good setup with minor caveats."),
            _sig("WATCH", "#ffcc00", "Score 4-5: Some conditions met. Monitor for improvement."),
            _sig("REJECT", "#607d8b", "Score 0-3: Conditions not met. Avoid."),
          ]
        },
        {
          "id": "screener-smart-labels",
          "title": "Smart Labels — Trading Context",
          "content": [
            _p("Smart labels go beyond BUY/SELL to tell you WHERE in the cycle a stock is. This helps you pick the right strategy."),
            _tbl(["Label", "Meaning", "Best Strategy"], [
              ["BREAKOUT CONFIRMED", "Price broke above 20-day high, score >= 8, not extended", "Buy breakout, tight stop below breakout level"],
              ["PULLBACK OPPORTUNITY", "Price near MA50 in uptrend, score >= 8", "Buy the dip, stop below MA50"],
              ["TREND CONTINUATION", "Strong score, sustained momentum, not overbought", "Hold or add to existing position"],
              ["EARLY TREND", "Just starting to outperform NIFTY, ROC < 5%", "Small position, wait for confirmation"],
              ["STRONG MOMENTUM", "ROC > 30%, score >= 8, not overbought", "Momentum trade, trailing stop"],
              ["OVERBOUGHT", "Z-score > 2 (price > 2 std above 20-day mean)", "Wait for pullback, avoid chasing"],
              ["MOMENTUM PEAK", "ROC > 50% and overbought", "Take profits, do not buy"],
              ["RANGE TRADE", "Good stock but SIDEWAYS market regime", "Wait for market to trend, or use options"],
              ["NEUTRAL", "Mixed signals, no clear edge", "Avoid or very small position"],
            ]),
          ]
        },
        {
          "id": "screener-rs",
          "title": "Relative Strength (RS) — The Most Important Metric",
          "content": [
            _p("Relative Strength measures how a stock performs vs NIFTY 50 over the last 1 year. RS > 1.0 means the stock is outperforming NIFTY. This is the single most predictive factor for future outperformance."),
            _f("RS = (1 + Stock 1Y Return) / (1 + NIFTY 1Y Return)"),
            _tbl(["RS Value", "Interpretation", "Action"], [
              ["RS > 1.5", "Massively outperforming NIFTY", "Strong buy candidate — institutional accumulation likely"],
              ["RS 1.2-1.5", "Clearly outperforming", "Good buy candidate"],
              ["RS 1.0-1.2", "Slightly outperforming", "Neutral — needs other conditions"],
              ["RS 0.8-1.0", "Underperforming NIFTY", "Avoid — money flowing out"],
              ["RS < 0.8", "Significantly underperforming", "Strong avoid — broken stock"],
            ]),
            _ex("RS Example", "NIFTY returned +15% in 1 year. VEDL returned +40%. RS = (1+0.40)/(1+0.15) = 1.217. VEDL is outperforming NIFTY by 21.7%."),
            _tip("Focus on stocks with RS > 1.2 AND rising. A stock that was RS=0.9 last month and is now RS=1.1 is more interesting than one that has been RS=1.3 for a year."),
          ]
        },
        {
          "id": "screener-monte-carlo",
          "title": "Monte Carlo Simulation — Probability Engine",
          "content": [
            _p("Monte Carlo runs 5000 simulated price paths using Geometric Brownian Motion (GBM) to estimate the probability distribution of future prices. It uses a hybrid mu/sigma that adapts to recent market conditions."),
            _f("S_t = S0 × exp((μ - 0.5σ²)t + σ√t × Z)"),
            _tbl(["Parameter", "How calculated", "Why"], [
              ["μ (drift)", "0.7 × mean(1Y returns) + 0.3 × mean(3Y returns)", "Adaptive — recent trend weighted more"],
              ["σ (volatility)", "0.6 × std(6M returns) + 0.4 × std(1Y returns)", "Recent vol weighted more, less noisy"],
              ["Regime adjustment", "HIGH_VOL: σ×1.10 | LOW_VOL: σ×0.95 | TRENDING: μ weighted to 1Y", "Adapts to current market environment"],
            ]),
            _tbl(["Output", "Meaning", "How to use"], [
              ["Prob Up (2M)", "% of 5000 simulations where price is higher in 60 days", "Buy if > 65%"],
              ["Prob Up (1Y)", "% of 5000 simulations where price is higher in 1 year", "Long-term conviction"],
              ["Expected Price", "Mean of all simulated end prices", "Target price estimate"],
              ["Worst Case (5%)", "5th percentile — only 5% of simulations end lower", "Stop loss reference"],
              ["Best Case (95%)", "95th percentile — only 5% of simulations end higher", "Profit target reference"],
            ]),
            _warn("Monte Carlo is a probability tool, not a prediction. A 70% probability means 30% of the time the stock goes down. Always use stop losses."),
          ]
        },
        {
          "id": "screener-decision",
          "title": "Decision Tab — Entry, Exit & Position Sizing",
          "content": [
            _p("The Decision tab converts the quant analysis into actionable trade parameters. It tells you exactly how much to buy, where to put your stop loss, and when to exit."),
            _tbl(["Parameter", "Formula", "Example"], [
              ["Stop Loss", "Entry price - 1.5 × ATR(14)", "ATR=15, Entry=500 → Stop=477.5"],
              ["Target", "Entry price + 3.0 × ATR(14)", "ATR=15, Entry=500 → Target=545"],
              ["Risk/Reward", "Target distance / Stop distance", "45/22.5 = 2.0 (minimum acceptable)"],
              ["Position Size", "(Capital × 2%) / (Entry - Stop)", "₹5L × 2% = ₹10,000 risk / ₹22.5 = 444 shares"],
            ]),
            _p("ATR (Average True Range) is the average daily price range over 14 days. It adapts to each stock's volatility — high-volatility stocks get wider stops, low-volatility stocks get tighter stops."),
            _tbl(["Exit Rule", "Condition", "Priority"], [
              ["Stop Loss", "Price falls to stop loss level", "IMMEDIATE — no exceptions"],
              ["Book Profit", "Price reaches target level", "HIGH — take profits"],
              ["Time Exit", "Holding > 120 days", "MEDIUM — avoid dead capital"],
              ["Weakness Exit", "Score drops below 5", "MEDIUM — fundamentals changed"],
            ]),
            _tip("The 2% risk rule means you never risk more than 2% of your total capital on any single trade. This ensures even 10 consecutive losses only reduce capital by 20%, keeping you in the game."),
          ]
        },
        {
          "id": "screener-backtest",
          "title": "Backtest — Validating the System",
          "content": [
            _p("The backtest runs the signal engine on 5 years of historical data using walk-forward testing. It simulates buying when score >= 6 and exiting based on dynamic stop/target/time rules."),
            _p("Dynamic parameters adapt to each stock's volatility: Low vol stocks (sigma < 20%) use 60-day hold, 7% stop, 20% target. High vol stocks (sigma > 30%) use 20-day hold, 5% stop, 10% target."),
            _tbl(["Metric", "Good", "Acceptable", "Poor"], [
              ["Win Rate", "> 55%", "45-55%", "< 45%"],
              ["Avg Return per Trade", "> 5%", "2-5%", "< 2%"],
              ["Sharpe Ratio", "> 1.5", "1.0-1.5", "< 1.0"],
              ["Max Drawdown", "< 15%", "15-25%", "> 25%"],
            ]),
            _warn("Backtest results are based on historical data and do not guarantee future performance. Markets change. Use backtest as one input, not the only input."),
          ]
        },
        {
          "id": "screener-filters",
          "title": "Filters & How to Use Them",
          "content": [
            _p("The screener has multiple filters to narrow down the 335 stocks to your best opportunities."),
            _tbl(["Filter", "What it does", "Recommended setting"], [
              ["MIN SCORE", "Minimum score threshold", "7+ for high conviction, 5+ for watchlist"],
              ["GROUP", "Filter by index (NIFTY50, BANKNIFTY, MIDCAP, SMALLCAP)", "Start with NIFTY50 for liquidity"],
              ["SECTOR", "Filter by sector (IT, BANKING, PHARMA, etc.)", "Use to avoid over-concentration"],
              ["RISK", "Filter by risk level (LOW/MEDIUM/HIGH)", "LOW for conservative, MEDIUM for balanced"],
              ["MAX DD", "Maximum drawdown from 52-week high", "< 20% for trend-following"],
              ["SORT", "Sort by score, ROC, RS, or probability", "Score for quality, RS for momentum"],
            ]),
            _tip("Start with MIN SCORE=8, GROUP=ALL, RISK=LOW or MEDIUM. This gives you the highest-quality setups. Then use the DECISION tab to size your position correctly."),
            _sig("TOP PICKS", "#ffcc00", "The TOP PICKS panel at the top shows the 5 best stocks with sector diversity. These are correlation-filtered (no two highly correlated stocks) and allocation-tiered (Tier 1 = 40% of capital, Tier 2 = 40%, Watchlist = 20%)."),
          ]
        },
      ]
    },
  ]
}


@guide_router.get("/guide")
async def get_guide():
    """Returns the complete guide content as JSON. No auth required."""
    return ORJSONResponse(GUIDE_DATA)
