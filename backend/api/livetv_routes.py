"""
Live TV — YouTube Live Video ID Resolver
==========================================
Scrapes the current live video ID from a YouTube channel's /live page.
No API key required — parses the page HTML for the videoId.

Cached in Redis for 5 minutes.
"""

import re
import time
import asyncio
from typing import Optional, Dict
from fastapi import APIRouter
from fastapi.responses import ORJSONResponse
import httpx

from core.redis_cache import get_cache

livetv_router = APIRouter(tags=["LiveTV"])

CHANNELS = [
    {"id": "cnbctv18",         "name": "CNBC TV18",        "liveUrl": "https://www.youtube.com/CNBCTV18/live"},
    {"id": "etnow",            "name": "ET Now",            "liveUrl": "https://www.youtube.com/ETNow/live"},
    {"id": "zeebusiness",      "name": "Zee Business",      "liveUrl": "https://www.youtube.com/ZeeBusiness/live"},
    {"id": "ndtvprofit",       "name": "NDTV Profit",       "liveUrl": "https://www.youtube.com/@NDTVProfitIndia/live"},
    {"id": "bloomberg",        "name": "Bloomberg Markets", "liveUrl": "https://www.youtube.com/@markets/live"},
    {"id": "moneycontrol",     "name": "Moneycontrol",      "liveUrl": "https://www.youtube.com/moneycontrol/live"},
    {"id": "moneycontrolhindi","name": "MC Hindi",          "liveUrl": "https://www.youtube.com/MoneyControlHindi18/live"},
]

# Matches the canonical videoId from the watch endpoint in the page JS
# YouTube embeds it as: "videoId":"XXXXXXXXXXX" in the page source
VIDEO_ID_RE = re.compile(r'"videoId"\s*:\s*"([A-Za-z0-9_-]{11})"')

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


async def _scrape_live_video_id(live_url: str, client: httpx.AsyncClient) -> Optional[str]:
    """
    Fetch the channel's /live page and extract the current live video ID.

    YouTube embeds the canonical live video ID in the page's inline JS as:
      window['ytCommand'] = {..., "watchEndpoint":{"videoId":"XXXXXXXXXXX"}}
    This is the ONLY reliable source — it's the exact video the /live URL resolves to.
    All other videoId occurrences in the page are recommendations/end-screens.
    """
    try:
        resp = await client.get(live_url, timeout=10.0, headers=HEADERS, follow_redirects=True)
        if resp.status_code != 200:
            return None

        html = resp.text

        # Primary: ytCommand.watchEndpoint.videoId — this is the canonical live video
        # Pattern: window['ytCommand'] = {...,"watchEndpoint":{"videoId":"XXXXXXXXXXX"}...}
        yt_command_match = re.search(
            r"window\['ytCommand'\]\s*=\s*\{.*?\"watchEndpoint\"\s*:\s*\{\"videoId\"\s*:\s*\"([A-Za-z0-9_-]{11})\"",
            html,
            re.DOTALL,
        )
        if yt_command_match:
            return yt_command_match.group(1)

        # Fallback: ytInitialPlayerResponse videoId (also reliable for live streams)
        player_match = re.search(
            r'"videoId"\s*:\s*"([A-Za-z0-9_-]{11})".*?"isLive"\s*:\s*true',
            html,
            re.DOTALL,
        )
        if player_match:
            return player_match.group(1)

        return None

    except Exception:
        return None


@livetv_router.get("/livetv/streams")
async def get_live_streams():
    """Resolve current live video IDs for all channels. Cached 5 min."""
    cache = get_cache()
    cache_key = "livetv:streams"

    cached = await cache.get(cache_key)
    if cached and isinstance(cached, list):
        return ORJSONResponse({"streams": cached, "cached": True, "timestamp": time.time()})

    async with httpx.AsyncClient() as client:
        tasks = [_scrape_live_video_id(ch["liveUrl"], client) for ch in CHANNELS]
        video_ids = await asyncio.gather(*tasks, return_exceptions=True)

    streams = []
    for ch, vid in zip(CHANNELS, video_ids):
        video_id = vid if isinstance(vid, str) else None
        streams.append({
            "id":       ch["id"],
            "name":     ch["name"],
            "liveUrl":  ch["liveUrl"],
            "videoId":  video_id,
            "embedUrl": (
                f"https://www.youtube-nocookie.com/embed/{video_id}"
                f"?autoplay=1&rel=0&modestbranding=1"
            ) if video_id else None,
            "isLive": video_id is not None,
        })

    await cache.set(cache_key, streams, ttl=300)
    return ORJSONResponse({"streams": streams, "cached": False, "timestamp": time.time()})


@livetv_router.get("/livetv/stream/{channel_id}")
async def get_single_stream(channel_id: str):
    """Resolve a single channel — bypasses cache for fresh ID."""
    ch = next((c for c in CHANNELS if c["id"] == channel_id), None)
    if not ch:
        return ORJSONResponse({"error": "Channel not found"}, status_code=404)

    # Invalidate cache for this channel so next /streams call re-fetches
    cache = get_cache()
    await cache.delete("livetv:streams")

    async with httpx.AsyncClient() as client:
        video_id = await _scrape_live_video_id(ch["liveUrl"], client)

    result = {
        "id":       ch["id"],
        "name":     ch["name"],
        "liveUrl":  ch["liveUrl"],
        "videoId":  video_id,
        "embedUrl": (
            f"https://www.youtube-nocookie.com/embed/{video_id}"
            f"?autoplay=1&rel=0&modestbranding=1"
        ) if video_id else None,
        "isLive":    video_id is not None,
        "timestamp": time.time(),
    }
    return ORJSONResponse(result)
