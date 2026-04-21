"""
stocks/screener_scraper.py
Scrapes fundamental data from screener.in (India-specific, reliable).
No API key needed. Cached 24h in Redis.

Data fetched:
  - Key ratios: PE, Book Value, ROCE, ROE, Market Cap, Dividend Yield
  - Quarterly results: Sales, Net Profit, OPM%
  - Annual P&L: Sales, Net Profit, EPS, OPM%
  - Balance sheet: Borrowings, Equity Capital, Reserves
  - Ratios table: ROCE%, ROE%, Debt/Equity
"""

import re
import asyncio
import urllib.request
from typing import Dict, List, Optional, Tuple


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}


def _fetch_html(symbol: str) -> str:
    """
    Fetch screener.in consolidated page for a symbol.
    Tries multiple URL variants to handle alternate symbol names.
    """
    # Some symbols have different names on screener.in
    SYMBOL_ALIASES = {
        "BLUESTARCO": "BLUESTAR",
        "DALBHARAT":  "DALMIA-BHARAT",
        "LTM":        "LTIMINDTREE",
        "JIOFIN":     "JIOFINANCIALSERVICES",
        "ADANIENSOL": "ADANI-ENERGY-SOLUTIONS",
        "WAAREEENER": "WAAREE-ENERGIES",
        "SWIGGY":     "SWIGGY",
        "ETERNAL":    "ZOMATO",   # Eternal = Zomato rebranded
        "HYUNDAI":    "HYUNDAI-MOTOR-INDIA",
        "TATATECH":   "TATA-TECHNOLOGIES",
        "LODHA":      "MACROTECH-DEVELOPERS",
        "MANKIND":    "MANKIND-PHARMA",
        "PATANJALI":  "PATANJALI-FOODS",
        "NUVAMA":     "NUVAMA-WEALTH-MANAGEMENT",
        "MOTILALOFS": "MOTILAL-OSWAL-FINANCIAL-SERVICES",
        "POLICYBZR":  "PB-FINTECH",
        "DELHIVERY":  "DELHIVERY",
        "IREDA":      "IREDA",
        "HUDCO":      "HUDCO",
        "INDUSTOWER": "INDUS-TOWERS",
        "GMRAIRPORT": "GMR-AIRPORTS-INFRASTRUCTURE",
        "ADANIPOWER": "ADANI-POWER",
        "ADANIENSOL": "ADANI-ENERGY-SOLUTIONS",
        "KALYANKJIL": "KALYAN-JEWELLERS",
        "UNOMINDA":   "UNO-MINDA",
        "SONACOMS":   "SONA-BLW-PRECISION-FORGINGS",
        "TIINDIA":    "TUBE-INVESTMENTS-OF-INDIA",
        "APLAPOLLO":  "APL-APOLLO-TUBES",
        "CGPOWER":    "CG-POWER-AND-INDUSTRIAL-SOLUTIONS",
        "SUPREMEIND": "SUPREME-INDUSTRIES",
        "SOLARINDS":  "SOLAR-INDUSTRIES-INDIA",
        "KAYNES":     "KAYNES-TECHNOLOGY-INDIA",
        "WAAREEENER": "WAAREE-ENERGIES",
        "360ONE":     "360-ONE-WAM",
        "IEX":        "INDIAN-ENERGY-EXCHANGE",
        "NAUKRI":     "INFO-EDGE-INDIA",
        "JUBLFOOD":   "JUBILANT-FOODWORKS",
        "UNITDSPR":   "UNITED-SPIRITS",
        "MAZDOCK":    "MAZAGON-DOCK-SHIPBUILDERS",
        "FORCEMOT":   "FORCE-MOTORS",
        "ASHOKLEY":   "ASHOK-LEYLAND",
        "EXIDEIND":   "EXIDE-INDUSTRIES",
        "BANKINDIA":  "BANK-OF-INDIA",
        "INDIANB":    "INDIAN-BANK",
        "UNIONBANK":  "UNION-BANK-OF-INDIA",
        "YESBANK":    "YES-BANK",
        "LICI":       "LIC",
        "LTF":        "L-T-FINANCE",
        "ABCAPITAL":  "ADITYA-BIRLA-CAPITAL",
        "PNBHOUSING": "PNB-HOUSING-FINANCE",
        "JIOFIN":     "JIO-FINANCIAL-SERVICES",
        "CONCOR":     "CONTAINER-CORPORATION-OF-INDIA",
        "GLENMARK":   "GLENMARK-PHARMACEUTICALS",
        "LAURUSLABS": "LAURUS-LABS",
        "ZYDUSLIFE":  "ZYDUS-LIFESCIENCES",
        "MANKIND":    "MANKIND-PHARMA",
        "FORTIS":     "FORTIS-HEALTHCARE",
        "MAXHEALTH":  "MAX-HEALTHCARE-INSTITUTE",
        "BOSCHLTD":   "BOSCH",
        "BHARATFORG": "BHARAT-FORGE",
        "TVSMOTOR":   "TVS-MOTOR-COMPANY",
        "HINDPETRO":  "HINDUSTAN-PETROLEUM-CORPORATION",
        "PETRONET":   "PETRONET-LNG",
        "HINDZINC":   "HINDUSTAN-ZINC",
        "ADANIGREEN": "ADANI-GREEN-ENERGY",
        "JSWENERGY":  "JSW-ENERGY",
        "RECLTD":     "REC",
        "POWERINDIA": "ABB-POWER-PRODUCTS-AND-SYSTEMS-INDIA",
        "GMRAIRPORT": "GMR-AIRPORTS-INFRASTRUCTURE",
        "INDUSTOWER": "INDUS-TOWERS",
        "DMART":      "AVENUE-SUPERMARTS",
        "NYKAA":      "FSN-E-COMMERCE-VENTURES",
        "CROMPTON":   "CROMPTON-GREAVES-CONSUMER-ELECTRICALS",
        "JUBLFOOD":   "JUBILANT-FOODWORKS",
        "VBL":        "VARUN-BEVERAGES",
        "INDHOTEL":   "INDIAN-HOTELS-COMPANY",
        "DELHIVERY":  "DELHIVERY",
        "PAYTM":      "ONE-97-COMMUNICATIONS",
        "IDEA":       "VODAFONE-IDEA",
        "IRCON":      "IRCON-INTERNATIONAL",
        "RITES":      "RITES",
        "NBCC":       "NBCC-INDIA",
        "INOXWIND":   "INOX-WIND",
        "SUZLON":     "SUZLON-ENERGY",
        "NHPC":       "NHPC",
        "SJVN":       "SJVN",
        "HINDCOPPER": "HINDUSTAN-COPPER",
        "RATNAMANI":  "RATNAMANI-METALS-AND-TUBES",
        "RAMCOCEM":   "RAMCO-CEMENTS",
        "JKCEMENT":   "JK-CEMENT",
        "EMAMILTD":   "EMAMI",
        "RALLIS":     "RALLIS-INDIA",
        "PIIND":      "PI-INDUSTRIES",
        "IPCALAB":    "IPCA-LABORATORIES",
        "GRANULES":   "GRANULES-INDIA",
        "LALPATHLAB": "DR-LAL-PATHLABS",
        "METROPOLIS": "METROPOLIS-HEALTHCARE",
        "BALKRISIND": "BALKRISHNA-INDUSTRIES",
        "APOLLOTYRE": "APOLLO-TYRES",
        "DEEPAKNTR":  "DEEPAK-NITRITE",
        "NAVINFLUOR": "NAVIN-FLUORINE-INTERNATIONAL",
        "PCBL":       "PCBL",
        "SOLARINDS":  "SOLAR-INDUSTRIES-INDIA",
        "KAYNES":     "KAYNES-TECHNOLOGY-INDIA",
        "KEI":        "KEI-INDUSTRIES",
        "AMBER":      "AMBER-ENTERPRISES-INDIA",
        "DIXON":      "DIXON-TECHNOLOGIES-INDIA",
        "KALYANKJIL": "KALYAN-JEWELLERS-INDIA",
        "HFCL":       "HFCL",
        "TATATECH":   "TATA-TECHNOLOGIES",
        "HYUNDAI":    "HYUNDAI-MOTOR-INDIA",
        "360ONE":     "360-ONE-WAM",
        "ADANIENSOL": "ADANI-ENERGY-SOLUTIONS",
        "IEX":        "INDIAN-ENERGY-EXCHANGE",
        "SWIGGY":     "SWIGGY",
        "ETERNAL":    "ZOMATO",
    }

    candidates = []
    alias = SYMBOL_ALIASES.get(symbol)
    if alias:
        candidates.append(f"https://www.screener.in/company/{alias}/consolidated/")
        candidates.append(f"https://www.screener.in/company/{alias}/")
    candidates.append(f"https://www.screener.in/company/{symbol}/consolidated/")
    candidates.append(f"https://www.screener.in/company/{symbol}/")

    last_err = None
    for url in candidates:
        try:
            req  = urllib.request.Request(url, headers=_HEADERS)
            resp = urllib.request.urlopen(req, timeout=15)
            html = resp.read().decode("utf-8")
            # Verify it's a real company page (not a search/error page)
            if 'id="top-ratios"' in html or 'id="quarters"' in html:
                return html
        except Exception as e:
            last_err = e
            continue

    raise Exception(f"Could not fetch {symbol} from screener.in: {last_err}")


def _clean(text: str) -> str:
    """Strip HTML tags and whitespace."""
    return re.sub(r"<[^>]+>", "", text).strip().replace("\xa0", " ")


def _to_float(s: str) -> Optional[float]:
    """Convert string like '1,23,456' or '24.1%' to float."""
    if not s or s in ("-", "—", ""):
        return None
    s = s.replace(",", "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _parse_top_ratios(html: str) -> Dict:
    """Parse the top key ratios (PE, ROCE, ROE, Market Cap etc.)."""
    result = {}
    ul = re.search(r'<ul[^>]*id="top-ratios"[^>]*>(.*?)</ul>', html, re.DOTALL)
    if not ul:
        return result
    items = re.findall(r"<li[^>]*>(.*?)</li>", ul.group(1), re.DOTALL)
    for item in items:
        name_m = re.search(r'<span[^>]*class="[^"]*name[^"]*"[^>]*>(.*?)</span>', item, re.DOTALL)
        val_m  = re.search(r'<span[^>]*class="[^"]*number[^"]*"[^>]*>(.*?)</span>', item, re.DOTALL)
        if name_m and val_m:
            name = _clean(name_m.group(1))
            val  = _clean(val_m.group(1))
            result[name] = val
    return result


def _parse_section_table(html: str, section_id: str) -> Tuple[List[str], Dict[str, List]]:
    """
    Parse a data table from a screener.in section.
    Returns (headers, {row_name: [values]}).
    """
    start = html.find(f'id="{section_id}"')
    if start < 0:
        return [], {}
    chunk = html[start:start + 25000]
    end   = chunk.find("</section>")
    if end > 0:
        chunk = chunk[:end]

    # Column headers (dates)
    headers = re.findall(r'data-date-key="([^"]+)"', chunk)

    # Table rows
    rows: Dict[str, List] = {}
    row_matches = re.findall(
        r'<tr[^>]*>\s*<td[^>]*class="[^"]*text[^"]*"[^>]*>(.*?)</td>(.*?)</tr>',
        chunk, re.DOTALL,
    )
    for row_name_raw, cells_raw in row_matches:
        row_name = _clean(row_name_raw).rstrip("+").strip()
        if not row_name:
            continue
        cell_vals = re.findall(r"<td[^>]*>(.*?)</td>", cells_raw, re.DOTALL)
        rows[row_name] = [_clean(cv).replace(",", "") for cv in cell_vals]

    return headers, rows


def _safe_row(rows: Dict, *keys) -> List[str]:
    """Try multiple key variants to find a row."""
    for k in keys:
        for rk in rows:
            if k.lower() in rk.lower():
                return rows[rk]
    return []


def _growth(vals: List[str], idx_new: int, idx_old: int) -> Optional[float]:
    """Calculate YoY growth % between two indices in a value list."""
    try:
        v_new = _to_float(vals[idx_new])
        v_old = _to_float(vals[idx_old])
        if v_new is not None and v_old and abs(v_old) > 0.01:
            return round((v_new - v_old) / abs(v_old) * 100, 1)
    except (IndexError, TypeError):
        pass
    return None


def _cagr(vals: List[str], years: int) -> Optional[float]:
    """Calculate CAGR over N years from the end of the list."""
    try:
        if len(vals) < years + 1:
            return None
        v_end   = _to_float(vals[-1])
        v_start = _to_float(vals[-(years + 1)])
        if v_end and v_start and v_start > 0 and v_end > 0:
            return round(((v_end / v_start) ** (1 / years) - 1) * 100, 1)
    except Exception:
        pass
    return None


async def fetch_fundamentals(symbol: str) -> Dict:
    """
    Fetch and parse fundamental data for a symbol from screener.in.
    Runs in a thread pool to avoid blocking the event loop.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_fundamentals_sync, symbol)


def _fetch_fundamentals_sync(symbol: str) -> Dict:
    """Synchronous implementation — called from thread pool."""
    import time

    try:
        html = _fetch_html(symbol)
    except Exception as e:
        return {"symbol": symbol, "status": "ERROR", "message": f"Fetch failed: {e}"}

    # ── Top ratios ────────────────────────────────────────────────────────────
    top = _parse_top_ratios(html)

    market_cap_raw = top.get("Market Cap", "")
    market_cap_cr  = _to_float(market_cap_raw.replace(",", "")) if market_cap_raw else None

    pe_ratio       = _to_float(top.get("Stock P/E", ""))
    book_value     = _to_float(top.get("Book Value", "").replace(",", ""))
    current_price  = _to_float(top.get("Current Price", "").replace(",", ""))
    roce_top       = _to_float(top.get("ROCE", ""))
    roe_top        = _to_float(top.get("ROE", ""))
    div_yield      = _to_float(top.get("Dividend Yield", ""))
    face_value     = _to_float(top.get("Face Value", ""))

    pb_ratio = None
    if current_price and book_value and book_value > 0:
        pb_ratio = round(current_price / book_value, 2)

    # ── Quarterly results ─────────────────────────────────────────────────────
    q_headers, q_rows = _parse_section_table(html, "quarters")
    quarterly = []
    sales_row  = _safe_row(q_rows, "Sales", "Revenue")
    profit_row = _safe_row(q_rows, "Net Profit", "Profit after tax")
    opm_row    = _safe_row(q_rows, "OPM %", "Operating Profit Margin")
    eps_row    = _safe_row(q_rows, "EPS")

    for i, hdr in enumerate(q_headers[-8:]):   # last 8 quarters
        idx = len(q_headers) - 8 + i if len(q_headers) > 8 else i
        quarterly.append({
            "period":     hdr[:7],   # "2024-03"
            "revenue":    _to_float(sales_row[idx])  if idx < len(sales_row)  else None,
            "net_profit": _to_float(profit_row[idx]) if idx < len(profit_row) else None,
            "opm_pct":    _to_float(opm_row[idx].replace("%", "")) if idx < len(opm_row) else None,
            "eps":        _to_float(eps_row[idx])    if idx < len(eps_row)    else None,
        })

    # ── Annual P&L ────────────────────────────────────────────────────────────
    pl_headers, pl_rows = _parse_section_table(html, "profit-loss")
    annual = []
    a_sales  = _safe_row(pl_rows, "Sales", "Revenue")
    a_profit = _safe_row(pl_rows, "Net Profit", "Profit after tax")
    a_opm    = _safe_row(pl_rows, "OPM %")
    a_eps    = _safe_row(pl_rows, "EPS")

    for i, hdr in enumerate(pl_headers[-6:]):   # last 6 years
        idx = len(pl_headers) - 6 + i if len(pl_headers) > 6 else i
        annual.append({
            "year":       hdr[:4],
            "revenue":    _to_float(a_sales[idx])  if idx < len(a_sales)  else None,
            "net_profit": _to_float(a_profit[idx]) if idx < len(a_profit) else None,
            "opm_pct":    _to_float(a_opm[idx].replace("%", "")) if idx < len(a_opm) else None,
            "eps":        _to_float(a_eps[idx])    if idx < len(a_eps)    else None,
        })

    # ── Growth metrics ────────────────────────────────────────────────────────
    rev_growth_yoy    = _growth(a_sales,  -1, -2)
    profit_growth_yoy = _growth(a_profit, -1, -2)
    rev_cagr_3y       = _cagr(a_sales,  3)
    rev_cagr_5y       = _cagr(a_sales,  5)
    profit_cagr_3y    = _cagr(a_profit, 3)
    profit_cagr_5y    = _cagr(a_profit, 5)

    # ── Ratios table (ROCE, ROE, D/E over years) ──────────────────────────────
    r_headers, r_rows = _parse_section_table(html, "ratios")
    roce_row = _safe_row(r_rows, "ROCE %", "ROCE")
    roe_row  = _safe_row(r_rows, "ROE %",  "ROE")
    de_row   = _safe_row(r_rows, "Debt / Equity", "D/E")

    # Latest values from ratios table (last column)
    roce_latest = _to_float(roce_row[-1].replace("%", "")) if roce_row else roce_top
    roe_latest  = _to_float(roe_row[-1].replace("%", ""))  if roe_row  else roe_top
    de_latest   = _to_float(de_row[-1])  if de_row  else None

    # ── Balance sheet ─────────────────────────────────────────────────────────
    bs_headers, bs_rows = _parse_section_table(html, "balance-sheet")
    borrow_row = _safe_row(bs_rows, "Borrowings", "Total Debt")
    equity_row = _safe_row(bs_rows, "Equity Capital")
    reserve_row = _safe_row(bs_rows, "Reserves")

    total_debt   = _to_float(borrow_row[-1]) if borrow_row else None
    equity_cap   = _to_float(equity_row[-1]) if equity_row else None
    reserves     = _to_float(reserve_row[-1]) if reserve_row else None
    total_equity = None
    if equity_cap is not None and reserves is not None:
        total_equity = equity_cap + reserves
    if de_latest is None and total_debt is not None and total_equity and total_equity > 0:
        de_latest = round(total_debt / total_equity, 2)

    # ── Company info from page title / meta ───────────────────────────────────
    name_m = re.search(r'<h1[^>]*>(.*?)</h1>', html)
    company_name = _clean(name_m.group(1)) if name_m else symbol

    sector_m = re.search(r'class="[^"]*company-sector[^"]*"[^>]*>(.*?)</a>', html, re.DOTALL)
    sector = _clean(sector_m.group(1)) if sector_m else ""

    industry_m = re.search(r'class="[^"]*company-industry[^"]*"[^>]*>(.*?)</a>', html, re.DOTALL)
    industry = _clean(industry_m.group(1)) if industry_m else ""

    # About text
    about_m = re.search(r'<div[^>]*class="[^"]*about[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
    about = _clean(about_m.group(1))[:400] if about_m else ""

    return {
        "symbol":     symbol,
        "status":     "OK",
        "source":     "screener.in",
        "info": {
            "name":        company_name,
            "sector":      sector,
            "industry":    industry,
            "description": about,
        },
        "ratios": {
            "pe_ratio":      pe_ratio,
            "pb_ratio":      pb_ratio,
            "roce":          roce_latest,
            "roe":           roe_latest,
            "debt_equity":   de_latest,
            "dividend_yield": div_yield,
            "market_cap_cr": market_cap_cr,
            "book_value":    book_value,
            "face_value":    face_value,
        },
        "growth": {
            "revenue_growth_yoy":    rev_growth_yoy,
            "profit_growth_yoy":     profit_growth_yoy,
            "revenue_cagr_3y":       rev_cagr_3y,
            "revenue_cagr_5y":       rev_cagr_5y,
            "profit_cagr_3y":        profit_cagr_3y,
            "profit_cagr_5y":        profit_cagr_5y,
        },
        "quarterly": quarterly,
        "annual":    annual,
        "fetched_at": time.time(),
    }
