"""
News Feed Proxy
================
Fetches real financial news from public RSS feeds.
Parses XML, extracts headlines, links, and timestamps.
Caches in Redis for 5 minutes to avoid hammering RSS sources.
"""

import time
import asyncio
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
from fastapi import APIRouter, Query
from fastapi.responses import ORJSONResponse
import httpx

from core.redis_cache import get_cache

news_router = APIRouter(tags=["News"])

# ─── RSS Sources ──────────────────────────────────────────────────────────────
# All public RSS feeds — no API key required

RSS_FEEDS = [
    {
        "source": "Economic Times Markets",
        "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "category": "MARKET",
    },
    {
        "source": "Economic Times Economy",
        "url": "https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms",
        "category": "MACRO",
    },
    {
        "source": "Moneycontrol Markets",
        "url": "https://www.moneycontrol.com/rss/marketreports.xml",
        "category": "MARKET",
    },
    {
        "source": "Moneycontrol News",
        "url": "https://www.moneycontrol.com/rss/latestnews.xml",
        "category": "GENERAL",
    },
    {
        "source": "NSE India",
        "url": "https://www.nseindia.com/api/rss-feed",
        "category": "EXCHANGE",
    },
    {
        "source": "Livemint Markets",
        "url": "https://www.livemint.com/rss/markets",
        "category": "MARKET",
    },
    {
        "source": "Business Standard Markets",
        "url": "https://www.business-standard.com/rss/markets-106.rss",
        "category": "MARKET",
    },
    {
        "source": "Reuters India Business",
        "url": "https://feeds.reuters.com/reuters/INbusinessNews",
        "category": "GLOBAL",
    },
]

# Keyword → sentiment mapping
BULLISH_KEYWORDS = [
    "rally", "surge", "gain", "rise", "up", "high", "record", "bull",
    "positive", "growth", "profit", "beat", "strong", "buy", "upgrade",
    "outperform", "breakout", "recovery", "boost", "jump",
]
BEARISH_KEYWORDS = [
    "fall", "drop", "decline", "down", "low", "loss", "bear", "sell",
    "negative", "weak", "miss", "cut", "downgrade", "underperform",
    "crash", "slump", "plunge", "concern", "risk", "fear",
]

MARKET_KEYWORDS = ["nifty", "sensex", "bank nifty", "option", "futures", "f&o", "oi", "iv", "vix"]
OPTIONS_KEYWORDS = ["option", "call", "put", "strike", "expiry", "iv", "vix", "pcr", "oi", "gamma", "delta"]
MACRO_KEYWORDS = ["rbi", "fed", "rate", "inflation", "gdp", "repo", "cpi", "wpi", "fiscal", "budget"]
SECTOR_KEYWORDS = ["it", "bank", "auto", "pharma", "fmcg", "metal", "energy", "realty", "infra"]


def _detect_sentiment(text: str) -> str:
    t = text.lower()
    bull = sum(1 for w in BULLISH_KEYWORDS if w in t)
    bear = sum(1 for w in BEARISH_KEYWORDS if w in t)
    if bull > bear:
        return "BULLISH"
    if bear > bull:
        return "BEARISH"
    return "NEUTRAL"


def _detect_category(text: str, default: str) -> str:
    t = text.lower()
    if any(w in t for w in OPTIONS_KEYWORDS):
        return "OPTIONS"
    if any(w in t for w in MACRO_KEYWORDS):
        return "MACRO"
    if any(w in t for w in MARKET_KEYWORDS):
        return "MARKET"
    return default


def _extract_tags(text: str) -> List[str]:
    t = text.lower()
    tags = []
    tag_map = {
        "Nifty": ["nifty"], "BankNifty": ["bank nifty", "banknifty"],
        "Options": ["option"], "FII": ["fii"], "DII": ["dii"],
        "RBI": ["rbi"], "Fed": ["fed", "federal reserve"],
        "VIX": ["vix"], "PCR": ["pcr"], "OI": [" oi "],
        "IT": [" it sector", "infosys", "tcs", "wipro"],
        "Auto": ["maruti", "tata motors", "m&m", "auto"],
        "Bank": ["hdfc bank", "icici bank", "sbi", "kotak"],
        "Crude": ["crude", "oil", "brent"],
        "Gold": ["gold", "silver"],
        "Results": ["q1", "q2", "q3", "q4", "quarterly", "results", "earnings"],
    }
    for tag, keywords in tag_map.items():
        if any(kw in t for kw in keywords):
            tags.append(tag)
    return tags[:4]


def _parse_rss(xml_text: str, source: str, default_category: str) -> List[Dict]:
    items = []
    try:
        root = ET.fromstring(xml_text)
        # Handle both RSS 2.0 and Atom
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        # RSS 2.0
        channel = root.find("channel")
        if channel is not None:
            for item in channel.findall("item")[:15]:
                title = (item.findtext("title") or "").strip()
                link  = (item.findtext("link") or "").strip()
                pub   = (item.findtext("pubDate") or "").strip()
                desc  = (item.findtext("description") or "").strip()
                if not title:
                    continue
                full_text = f"{title} {desc}"
                items.append({
                    "headline":  title,
                    "link":      link,
                    "source":    source,
                    "category":  _detect_category(full_text, default_category),
                    "sentiment": _detect_sentiment(full_text),
                    "tags":      _extract_tags(full_text),
                    "pub_date":  pub,
                    "ts":        time.time(),
                })
        else:
            # Atom feed
            for entry in root.findall("atom:entry", ns)[:15]:
                title = (entry.findtext("atom:title", namespaces=ns) or "").strip()
                link_el = entry.find("atom:link", ns)
                link = link_el.get("href", "") if link_el is not None else ""
                pub  = (entry.findtext("atom:published", namespaces=ns) or "").strip()
                if not title:
                    continue
                items.append({
                    "headline":  title,
                    "link":      link,
                    "source":    source,
                    "category":  _detect_category(title, default_category),
                    "sentiment": _detect_sentiment(title),
                    "tags":      _extract_tags(title),
                    "pub_date":  pub,
                    "ts":        time.time(),
                })
    except Exception:
        pass
    return items


async def _fetch_feed(client: httpx.AsyncClient, feed: Dict) -> List[Dict]:
    try:
        resp = await client.get(
            feed["url"],
            timeout=8.0,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; OptionsDesk/2.0; +https://optionsdesk.in)",
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            },
            follow_redirects=True,
        )
        if resp.status_code == 200:
            return _parse_rss(resp.text, feed["source"], feed["category"])
    except Exception:
        pass
    return []


@news_router.get("/news")
async def get_news(
    category: Optional[str] = Query(None),
    sentiment: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """
    Fetch real financial news from RSS feeds.
    Cached for 5 minutes in Redis.
    Falls back to empty list if all feeds fail.
    """
    cache = get_cache()
    cache_key = "news:feed:all"

    # Try Redis cache first
    cached = await cache.get(cache_key)
    if cached and isinstance(cached, list) and len(cached) > 0:
        items = cached
    else:
        # Fetch all feeds concurrently
        async with httpx.AsyncClient() as client:
            results = await asyncio.gather(
                *[_fetch_feed(client, feed) for feed in RSS_FEEDS],
                return_exceptions=True,
            )

        items: List[Dict] = []
        seen = set()
        for result in results:
            if isinstance(result, list):
                for item in result:
                    h = item.get("headline", "")
                    if h and h not in seen:
                        seen.add(h)
                        items.append(item)

        # Sort by timestamp (newest first)
        items.sort(key=lambda x: x.get("ts", 0), reverse=True)

        if items:
            await cache.set(cache_key, items, ttl=300)  # 5 min cache

    # Apply filters
    if category and category != "ALL":
        items = [i for i in items if i.get("category") == category]
    if sentiment and sentiment != "ALL":
        items = [i for i in items if i.get("sentiment") == sentiment]

    # Compute sentiment summary
    all_items = cached if (cached and isinstance(cached, list)) else items
    bull = sum(1 for i in all_items if i.get("sentiment") == "BULLISH")
    bear = sum(1 for i in all_items if i.get("sentiment") == "BEARISH")
    neut = sum(1 for i in all_items if i.get("sentiment") == "NEUTRAL")
    total = max(len(all_items), 1)

    return ORJSONResponse({
        "items":     items[:limit],
        "total":     len(items),
        "sentiment_summary": {
            "bullish":  bull,
            "bearish":  bear,
            "neutral":  neut,
            "score":    round((bull - bear) / total * 100),
        },
        "sources":   len(RSS_FEEDS),
        "cached":    bool(cached),
        "timestamp": time.time(),
    })
