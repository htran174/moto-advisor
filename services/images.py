# services/images.py
from __future__ import annotations
from typing import List, Dict, Any
import re, json, os
from pathlib import Path
from functools import lru_cache

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "static"
MANIFEST_PATH = STATIC_DIR / "images.json"

# Load manifest once (id -> filename)
try:
    with MANIFEST_PATH.open("r", encoding="utf-8") as f:
        IMAGE_MANIFEST = json.load(f)
except Exception:
    IMAGE_MANIFEST = {}

LOCAL_IMAGE_MAP = {k.lower(): v for k,v in IMAGE_MANIFEST.items()}

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()

def _safe_local_url(fname: str) -> str | None:
    if re.fullmatch(r"[A-Za-z0-9_.-]+\.(jpg|jpeg|png|webp)", fname or ""):
        return f"/static/{fname}"
    return None

@lru_cache(maxsize=256)
def _query_to_local(query_norm: str) -> str | None:
    # try exact id hits first (e.g., "yamaha_r3")
    if query_norm in LOCAL_IMAGE_MAP:
        return _safe_local_url(LOCAL_IMAGE_MAP[query_norm])
    # heuristic brand/model contains
    for key, fname in LOCAL_IMAGE_MAP.items():
        if key in query_norm:
            return _safe_local_url(fname)
    return None

def get_images(payload: Dict[str, Any], offline_mode: bool, google: Dict[str, str] | None) -> Dict[str, Any]:
    """
    payload: { query, limit, mfr_domain, local_image?, id? }
    Returns: { source: "offline"|"google"|"local", images: [{url,width,height}] }
    """
    limit = int(payload.get("limit") or 3)
    query = str(payload.get("query") or "")[:120]
    local_hint = payload.get("local_image")
    id_hint = str(payload.get("id") or "").lower()

    # 0) explicit hint (whitelist)
    if local_hint:
        url = _safe_local_url(local_hint)
        if url:
            return {"source":"local","images":[{"url":url,"width":1200,"height":800}]}

    # 1) id hint (preferred)
    if id_hint:
        u = _query_to_local(id_hint)
        if u:
            return {"source":"local","images":[{"url":u,"width":1200,"height":800}]}

    # 2) map from query
    u = _query_to_local(_norm(query))
    if u:
        return {"source":"local","images":[{"url":u,"width":1200,"height":800}]}

    # 3) offline fallback
    if offline_mode or not google:
        return {"source":"offline","images":[{"url":"/static/motorcyle_ride.jpg","width":1200,"height":800}]}

    # 4) (stub) google cse – keep offline in local dev
    return {"source":"offline","images":[{"url":"/static/motorcyle_ride.jpg","width":1200,"height":800}]}
