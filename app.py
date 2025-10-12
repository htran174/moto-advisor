"""
RideReady Advisor — Flask backend
"""

import os, json, re
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

# Local services
from services.recommend_rules import recommend, validate_profile
from services.images import get_images

# --------------------------------------------------------------------
# App constants / paths
# --------------------------------------------------------------------
APP_TITLE = "RideReady"
ROOT: Path = Path(__file__).resolve().parent
DATA_DIR: Path = ROOT / "data"
STATIC_DIR: Path = ROOT / "static"
TEMPLATES_DIR: Path = ROOT / "templates"

# --------------------------------------------------------------------
# Flask app
# --------------------------------------------------------------------
app = Flask(
    __name__,
    static_folder=str(STATIC_DIR),
    template_folder=str(TEMPLATES_DIR),
)

# Make the app title available in all templates
@app.context_processor
def inject_globals():
    return {"app_title": APP_TITLE}

# --------------------------------------------------------------------
# Env / keys / mode
# --------------------------------------------------------------------
load_dotenv()

GOOGLE_CSE_KEY = os.getenv("GOOGLE_CSE_KEY")
GOOGLE_CSE_ENGINE = os.getenv("GOOGLE_CSE_ENGINE")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

OFFLINE_MODE = not (GOOGLE_CSE_KEY and GOOGLE_CSE_ENGINE and OPENAI_API_KEY)
print(f"[RideReady] OFFLINE_MODE={OFFLINE_MODE}")

# --------------------------------------------------------------------
# Data loading
# --------------------------------------------------------------------
def load_json(path: Path):
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] Failed to load {path}: {e}")
        return []

BIKES = load_json(DATA_DIR / "bikes.json")
# Gear is out-of-scope for now; we keep the file load to avoid errors if referenced elsewhere
GEAR = load_json(DATA_DIR / "gear.json")

# --------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------
@app.route("/")
def home():
    return render_template("home.html", page_title="Home")

@app.route("/advisor")
def advisor():
    return render_template("advisor.html", page_title="Advisor")

@app.route("/recommendations")
def recommendations():
    return render_template("recommendations.html", page_title="Recommendations")

@app.route("/disclaimer")
def disclaimer():
    return render_template("disclaimer.html", page_title="Disclaimer")

# --------------------------------------------------------------------
# Health
# --------------------------------------------------------------------
@app.route("/healthz")
def healthz():
    try:
        return jsonify({
            "status": "ok",
            "offline_mode": OFFLINE_MODE,
            "keys_present": {
                "google_cse_engine": bool(GOOGLE_CSE_ENGINE),
                "google_cse_key": bool(GOOGLE_CSE_KEY),
                "openai": bool(OPENAI_API_KEY)
            },
            "whitelist": {
                "bikes": len(BIKES),
                "gear": len(GEAR)
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --------------------------------------------------------------------
# API: recommend
# --------------------------------------------------------------------
@app.post("/api/recommend")
def api_recommend():
    """
    Body:
      {
        "experience": "no_experience" | "little_experience",
        "height_cm": 170,
        "budget_usd": 6000,
        "bike_types": ["sportbike","naked"],
        "k": 3
      }
    """
    try:
        payload = request.get_json(force=True, silent=False) or {}
    except Exception:
        return {"error": {"code": "bad_json", "message": "Invalid JSON"}}, 400

    try:
        profile = validate_profile(payload)
        items = recommend(BIKES, profile)
        return jsonify({"count": len(items), "items": items, "profile": profile})
    except Exception as e:
        print(f"[ERROR] /api/recommend: {e}")
        return {"error": {"code": "server_error", "message": "Internal error"}}, 500

# --------------------------------------------------------------------
# API: images
# --------------------------------------------------------------------
@app.post("/api/images")
def api_images():
    """
    Body:
      {
        "query": "Yamaha MT-03 2023",
        "limit": 1,
        "mfr_domain": "yamahamotorsports.com",
        "local_image": "Yamaha_mt03.jpg"   # optional hint from whitelist
      }
    """
    try:
        payload = request.get_json(force=True, silent=False) or {}
    except Exception:
        return {"error": {"code": "bad_json", "message": "Invalid JSON"}}, 400

    # Basic sanitation: trim strings, clamp lengths
    clean = {}
    for k, v in payload.items():
        if isinstance(v, str):
            clean[k] = v.strip()[:128]
        elif isinstance(v, (int, float)):
            clean[k] = v
        else:
            clean[k] = str(v)[:128]

    try:
        data = get_images(
            clean,
            OFFLINE_MODE,
            {
                "GOOGLE_CSE_KEY": GOOGLE_CSE_KEY,
                "GOOGLE_CSE_ENGINE": GOOGLE_CSE_ENGINE
            } if not OFFLINE_MODE else None
        )
        return jsonify(data)
    except Exception as e:
        print(f"[ERROR] /api/images: {e}")
        # Safe fallback image
        return jsonify({
            "source": "offline",
            "images": [{"url": "/static/motorcyle_ride.jpg", "width": 1200, "height": 800}]
        })

# --------------------------------------------------------------------
# Security headers
# --------------------------------------------------------------------
@app.after_request
def add_headers(resp):
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return resp

# --------------------------------------------------------------------
# Main
# --------------------------------------------------------------------
if __name__ == "__main__":
    # Use localhost only for dev; Gunicorn will serve in multi-worker later
    app.run(host="127.0.0.1", port=5000, debug=True)
