# services/images.py
import os, time, requests
from typing import List, Dict

TTL_SECONDS = 600
_cache: Dict[str, Dict] = {}

def _now(): return int(time.time())

def cached(key: str):
    hit = _cache.get(key)
    if hit and (_now() - hit["t"] < TTL_SECONDS):
        return hit["v"]
    return None

def put_cache(key: str, value):
    _cache[key] = {"t": _now(), "v": value}

def search_images(query: str, limit: int = 6, mfr_domain: str | None = None):
    # Offline / missing keys path
    key = os.getenv("GOOGLE_CSE_KEY")
    cx = os.getenv("GOOGLE_CSE_ENGINE_ID")
    offline = os.getenv("OFFLINE_MODE", "false").lower() == "true"
    qnorm = (query or "").strip().lower()
    cache_key = f"img::{mfr_domain or ''}::{qnorm}::{limit}"
    if offline or not key or not cx:
        # Return local placeholders (front-end will still render)
        results = [
            {
                "url": "/static/motorcyle_ride.jpg",
                "width": 1200,
                "height": 800,
                "source": "local-offline"
            },
            {
                "url": "/static/gear_stock.jpg",
                "width": 1200,
                "height": 800,
                "source": "local-offline"
            }
        ][:limit]
        return {"images": results, "source": "offline"}

    hit = cached(cache_key)
    if hit: return hit

    # Build query
    q = query
    if mfr_domain:
        q = f"site:{mfr_domain} {query}"

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": key,
        "cx": cx,
        "q": q,
        "searchType": "image",
        "safe": "active",
        "num": min(limit, 10)
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    items = data.get("items", []) or []
    images: List[Dict] = []
    for it in items:
        link = it.get("link")
        if not link: continue
        images.append({
            "url": link,
            "width": int(it.get("image", {}).get("width") or 0),
            "height": int(it.get("image", {}).get("height") or 0),
            "source": it.get("displayLink") or ""
        })
    res = {"images": images[:limit], "source": "google_cse"}
    put_cache(cache_key, res)
    return res