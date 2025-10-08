from __future__ import annotations
import json, os
from pathlib import Path
from dataclasses import asdict
from typing import Any, Dict, List
from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv

from services.recommend_rules import RiderProfile, shortlist
from services.images import search_images

load_dotenv()  # loads .env if present

APP_TITLE = "RideReady"
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

app = Flask(__name__)

# ------------ utilities ------------
def json_load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def fail(message: str, code: str = "BAD_REQUEST", http=400):
    return jsonify({"error": {"code": code, "message": message}}), http

def ok(payload: Dict[str, Any]):
    return jsonify(payload)

def env_bool(name: str, default=False) -> bool:
    v = os.getenv(name)
    if v is None: return default
    return str(v).lower() in ("1", "true", "yes", "on")

# ------------ load whitelist ------------
try:
    BIKES: List[Dict[str, Any]] = json_load(DATA_DIR / "bikes.json")
    GEAR:  List[Dict[str, Any]] = json_load(DATA_DIR / "gear.json")
except FileNotFoundError as e:
    BIKES, GEAR = [], []
    print("⚠️  Whitelist missing: ", e)

# Basic schema sanity (lightweight — expand later if needed)
REQUIRED_BIKE_FIELDS = {"id","name","manufacturer","category","engine_cc","seat_height_mm","wet_weight_kg","abs","beginner_score","budget_tier","official_url","mfr_domain"}

def validate_whitelist() -> List[str]:
    errs: List[str] = []
    for b in BIKES:
        missing = REQUIRED_BIKE_FIELDS - set(b.keys())
        if missing:
            errs.append(f"Bike {b.get('id') or b.get('name')}: missing {sorted(missing)}")
    return errs

VALIDATION_ERRORS = validate_whitelist()
if VALIDATION_ERRORS:
    print("⚠️  Whitelist validation warnings:")
    for e in VALIDATION_ERRORS: print("   -", e)

# ------------ context ------------
@app.context_processor
def inject_app_title():
    return {"app_title": APP_TITLE}

# ------------ pages ------------
@app.route("/")
def home():
    return render_template("home.html", page_title="Home")

@app.route("/disclaimer")
def disclaimer():
    return render_template("disclaimer.html", page_title="Disclaimer")

@app.route("/advisor")
def advisor():
    return render_template("advisor.html", page_title="Advisor")

# ------------ health ------------
@app.route("/healthz")
def healthz():
    keys = {
        "openai": bool(os.getenv("OPENAI_API_KEY")),
        "google_cse_key": bool(os.getenv("GOOGLE_CSE_KEY")),
        "google_cse_engine": bool(os.getenv("GOOGLE_CSE_ENGINE_ID")),
    }
    return ok({
        "status": "ok",
        "offline_mode": env_bool("OFFLINE_MODE", False),
        "whitelist": {"bikes": len(BIKES), "gear": len(GEAR)},
        "keys_present": keys
    })

# ------------ API: recommend (v1 rules only, deterministic) ------------
@app.route("/api/recommend", methods=["POST"])
def api_recommend():
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        return fail("Invalid JSON body.", "INVALID_JSON")

    # Coerce inputs with safe defaults
    profile = RiderProfile(
        experience = str(payload.get("experience") or "new").lower(),
        height_cm  = int(payload.get("height_cm") or 170),
        budget_usd = int(payload.get("budget_usd") or 6000),
        riding_style = list(payload.get("riding_style") or []),
        must_have = [str(x).lower() for x in (payload.get("must_have") or [])]
    )

    if not BIKES:
        return fail("Bike whitelist is empty or not loaded.", "NO_DATA", 500)

    top = shortlist(BIKES, profile, k=int(payload.get("k") or 3))

    # Project only safe fields
    def clean(item: Dict[str, Any]) -> Dict[str, Any]:
        allowed = {
            "id","name","manufacturer","category","engine_cc","seat_height_mm",
            "wet_weight_kg","abs","official_url","mfr_domain","tags","beginner_score"
        }
        out = {k: item[k] for k in item.keys() if k in allowed}
        out["score"] = item.get("_score")
        out["reasons"] = item.get("_reasons", [])
        return out

    result = [clean(x) for x in top]
    return ok({
        "profile": asdict(profile),
        "count": len(result),
        "items": result
    })

# ------------ API: images ------------
@app.route("/api/images", methods=["POST"])
def api_images():
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        return fail("Invalid JSON body.", "INVALID_JSON")

    query = (payload.get("query") or "").strip()
    if not query:
        return fail("Missing 'query' in request body.", "MISSING_QUERY")

    # If caller knows the mfr domain, better results:
    mfr_domain = (payload.get("mfr_domain") or "").strip() or None
    limit = int(payload.get("limit") or 6)
    try:
        res = search_images(query=query, limit=limit, mfr_domain=mfr_domain)
        return ok(res)
    except Exception as e:
        return fail(f"Image search failed: {e}", "IMAGE_SEARCH_FAILED", 502)

# ------------ main ------------
if __name__ == "__main__":
    app.run(debug=True)
