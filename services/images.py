# services/images.py
from __future__ import annotations
from typing import List, Dict, Any
import re
import os

# Known local mappings (model → filename under /static)
# Keep these in sync with /static filenames (case sensitive)
LOCAL_IMAGE_MAP = {
    # SPORT
    ("yamaha", "r3"): "Yamaha_r3.jpg",
    ("honda", "cbr300"): "Honda_cbr300.jpg",
    ("kawasaki", "ninja 400"): "Kawasaki_ninja400.jpg",
    # NAKED
    ("yamaha", "mt-03"): "Yamaha_mt03.jpg",
    ("kawasaki", "z400"): "kawasaki_z400.jpg",
    ("ktm", "390 duke"): "ktm_duke390.jpg",
    # CRUISER
    ("honda", "rebel 300"): "honda_rebel300.jpg",
}

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()

def _try_local_from_hint(local_image: str | None) -> str | None:
    if not local_image:
        return None
    # prevent path traversal; allow only simple filenames
    if re.fullmatch(r"[A-Za-z0-9_.-]+\.(jpg|jpeg|png|webp)", local_image):
        return f"/static/{local_image}"
    return None

def _try_local_from_query(query: str) -> str | None:
    q = _norm(query)
    for (brand, key), filename in LOCAL_IMAGE_MAP.items():
        if brand in q and key in q:
            return f"/static/{filename}"
    return None

def get_images(payload: Dict[str, Any], offline_mode: bool, google: Dict[str, str] | None) -> Dict[str, Any]:
    """
    payload: { query, limit, mfr_domain, local_image? }
    Returns: { source: "offline"|"google"|"local", images: [{url,width,height}] }
    """
    limit = int(payload.get("limit") or 3)
    query = str(payload.get("query") or "")[:120]
    local_hint = payload.get("local_image")

    # 1) Prefer explicit local hint from server (whitelist)
    hint_url = _try_local_from_hint(local_hint)
    if hint_url:
        return {"source": "local", "images": [{"url": hint_url, "width": 1200, "height": 800}]}

    # 2) Try to resolve from query using local map
    mapped = _try_local_from_query(query)
    if mapped:
        return {"source": "local", "images": [{"url": mapped, "width": 1200, "height": 800}]}

    # 3) Fallback to offline stock if offline_mode or no keys
    if offline_mode or not google:
        return {
            "source": "offline",
            "images": [{"url": "/static/motorcyle_ride.jpg", "width": 1200, "height": 800}]
        }

    # 4) Else: do Google CSE (existing logic you already had)
    # NOTE: Keep your current implementation here. Pseudocode:
    # results = google_cse_search(query, mfr_domain=payload.get("mfr_domain"), limit=limit)
    # images = [{"url": r.url, "width": r.width, "height": r.height} for r in results]
    # if not images: images = [{"url": "/static/motorcyle_ride.jpg", "width": 1200, "height": 800}]
    # return {"source":"google","images": images[:limit]}
    return {
        "source": "offline",
        "images": [{"url": "/static/motorcyle_ride.jpg", "width": 1200, "height": 800}]
    }
