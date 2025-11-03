# services/images.py
import os, json, re, time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]     # project root
IMAGES_JSON = ROOT / "static" / "images.json"

USE_GOOGLE_IMAGES = os.getenv("USE_GOOGLE_IMAGES", "false").lower() == "true"
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID  = os.getenv("GOOGLE_CSE_ID")

# simple in-memory cache for remote lookups
_CACHE = {}

def _load_map():
    try:
        with open(IMAGES_JSON, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}

IMG_MAP = _load_map()

def _snake(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s

def _norm_key(brand: str, model: str) -> str:
    """
    Convert (brand, model) into our canonical key style: 'kawasaki_ninja_400'
    Includes light aliasing so 'MT-03' → 'mt03', 'RC 390' → 'rc_390', etc.
    """
    b = _snake(brand)
    m = _snake(model)

    # light alias cleanup
    m = m.replace("mt_03", "mt03").replace("r_3", "r3").replace("rc_390", "rc_390")
    m = m.replace("cb_300r", "cb300r").replace("sv_650", "sv650").replace("rebel_500", "rebel_500")

    key = f"{b}_{m}" if b and m else m or b
    return key

# Extra alias map for common OpenAI spellings → our canonical keys
ALIASES = {
    "yamaha|r7": "yamaha_r7",
    "yamaha|r3": "yamaha_r3",
    "kawasaki|ninja_400": "kawasaki_ninja_400",
    "kawasaki|z_400": "kawasaki_z400",
    "ktm|rc_390": "ktm_rc_390",
    "ktm|390_rc": "ktm_rc_390",
    "ktm|390_duke": "ktm_390_duke",
    "honda|cbr300": "honda_cbr300",
    "honda|cb_300r": "honda_cb300r",
    "honda|rebel_300": "honda_rebel_300",
}

def _alias_key(brand: str, model: str) -> str | None:
    b = _snake(brand)
    m = _snake(model)
    pat = f"{b}|{m}"
    return ALIASES.get(pat)

def find_local_image(id_: str | None, brand: str | None, model: str | None, local_image: str | None) -> str | None:
    # 0) explicit path from caller
    if local_image:
        return f"/static/stock_images/{local_image.lstrip('/')}"

    # 1) direct id map (catalog path)
    if id_:
        path = IMG_MAP.get(id_)
        if path:
            return f"/static/{path}"

    # 2) normalized brand+model
    if brand or model:
        k = _norm_key(brand or "", model or "")
        path = IMG_MAP.get(k)
        if path:
            return f"/static/{path}"

        # 3) alias try
        alias = _alias_key(brand or "", model or "")
        if alias:
            path = IMG_MAP.get(alias)
            if path:
                return f"/static/{path}"

    return None

def google_image_search(query: str, mfr_domain: str | None = None) -> str | None:
    if not USE_GOOGLE_IMAGES or not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
        return None

    q = (query or "").strip()
    if not q:
        return None

    # cache
    if q in _CACHE and (time.time() - _CACHE[q]["t"] < 86400):
        return _CACHE[q]["url"]

    params = {
        "q": q,
        "searchType": "image",
        "num": 1,
        "cx": GOOGLE_CSE_ID,
        "key": GOOGLE_API_KEY,
        # optional bias toward manufacturer site helps quality
        "siteSearch": mfr_domain or "",
        "safe": "active",
    }
    try:
        r = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=6)
        r.raise_for_status()
        items = (r.json().get("items") or [])
        if items:
            url = items[0].get("link")
            if url:
                _CACHE[q] = {"url": url, "t": time.time()}
                return url
    except Exception:
        return None
    return None

def resolve_image_url(payload: dict) -> str:
    """
    Accepts the JSON body send from recommendations.js and returns a URL string.
    """
    id_ = payload.get("id")
    brand = payload.get("brand") or payload.get("manufacturer") or ""
    model = payload.get("model") or payload.get("name") or ""
    query = payload.get("query") or f"{brand} {model}".strip()
    mfr_domain = payload.get("mfr_domain")
    local_image = payload.get("local_image")

    # 1) Local first
    local = find_local_image(id_, brand, model, local_image)
    if local:
        return local

    # 2) Google fallback
    remote = google_image_search(query, mfr_domain)
    if remote:
        return remote

    # 3) Last resort – generic
    return "/static/motorcycle_ride.jpg"
