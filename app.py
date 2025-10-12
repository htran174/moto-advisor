"""
RideReady Advisor — Flask backend
Author: Hien Tran
License: GNU GPLv3
"""

import os, json, re
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

# Local imports
from services.recommend_rules import recommend, validate_profile
from services.images import get_images

# --------------------------------------------------------------------
# Setup
# --------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
STATIC_DIR = os.path.join(BASE_DIR, "static")

load_dotenv()  # load .env for API keys

# Environment keys
GOOGLE_CSE_KEY = os.getenv("GOOGLE_CSE_KEY")
GOOGLE_CSE_ENGINE = os.getenv("GOOGLE_CSE_ENGINE")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

OFFLINE_MODE = not (GOOGLE_CSE_KEY and GOOGLE_CSE_ENGINE and OPENAI_API_KEY)
print(f"Offline mode: {OFFLINE_MODE}")

# --------------------------------------------------------------------
# Load data
# --------------------------------------------------------------------
def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] Failed to load {path}: {e}")
        return []

BIKES = load_json(os.path.join(DATA_DIR, "bikes.json"))
GEAR = load_json(os.path.join(DATA_DIR, "gear.json"))  # unused for now

# --------------------------------------------------------------------
# Flask app
# --------------------------------------------------------------------
app = Flask(__name__, static_folder="static", template_folder="templates")

# --------------------------------------------------------------------
# Routes: HTML pages
# --------------------------------------------------------------------

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/advisor")
def advisor():
    return render_template("advisor.html")

@app.route("/recommendations")
def recommendations():
    return render_template("recommendations.html")

@app.route("/disclaimer")
def disclaimer():
    return render_template("disclaimer.html")

# --------------------------------------------------------------------
# Health check
# --------------------------------------------------------------------
@app.route("/healthz")
def healthz():
    try:
        whitelist_summary = {
            "bikes": len(BIKES),
            "gear": len(GEAR)
        }
        keys_present = {
            "google_cse_engine": bool(GOOGLE_CSE_ENGINE),
            "google_cse_key": bool(GOOGLE_CSE_KEY),
            "openai": bool(OPENAI_API_KEY)
        }
        return jsonify({
            "status": "ok",
            "offline_mode": OFFLINE_MODE,
            "keys_present": keys_present,
            "whitelist": whitelist_summary
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --------------------------------------------------------------------
# API: Recommendations
# --------------------------------------------------------------------
@app.post("/api/recommend")
def api_recommend():
    """
    POST /api/recommend
    Body:
      {
        "experience": "no_experience" | "little_experience",
        "height_cm": 170,
        "budget_usd": 6000,
        "bike_types": ["sportbike", "naked"],
        "k": 3
      }
    """
    try:
        payload = request.get_json(force=True, silent=False) or {}
    except Exception:
        return {"error": {"code": "bad_json", "message": "Invalid JSON"}}, 400

    try:
        profile = validate_profile(payload)
        results = recommend(BIKES, profile)
        return jsonify({
            "count": len(results),
            "items": results,
            "profile": profile
        })
    except Exception as e:
        print(f"[ERROR] /api/recommend: {e}")
        return {"error": {"code": "server_error", "message": str(e)}}, 500

# --------------------------------------------------------------------
# API: Images
# --------------------------------------------------------------------
@app.post("/api/images")
def api_images():
    """
    POST /api/images
    Body:
      {
        "query": "Yamaha MT-03 2023",
        "limit": 1,
        "mfr_domain": "yamahamotorsports.com",
        "local_image": "Yamaha_mt03.jpg"
      }
    """
    try:
        payload = request.get_json(force=True, silent=False) or {}
    except Exception:
        return {"error": {"code": "bad_json", "message": "Invalid JSON"}}, 400

    # Basic input sanitation
    for k, v in list(payload.items()):
        if isinstance(v, str):
            payload[k] = v.strip()[:128]  # prevent long junk
        elif isinstance(v, (int, float)):
            continue
        else:
            payload[k] = str(v)[:128]

    try:
        data = get_images(payload, OFFLINE_MODE, {
            "GOOGLE_CSE_KEY": GOOGLE_CSE_KEY,
            "GOOGLE_CSE_ENGINE": GOOGLE_CSE_ENGINE
        } if not OFFLINE_MODE else None)
        return jsonify(data)
    except Exception as e:
        print(f"[ERROR] /api/images: {e}")
        return {"source": "offline", "images": [
            {"url": "/static/motorcyle_ride.jpg", "width": 1200, "height": 800}
        ]}

# --------------------------------------------------------------------
# Security: limit headers and disable caching
# --------------------------------------------------------------------
@app.after_request
def add_headers(resp):
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp

# --------------------------------------------------------------------
# Main entry
# --------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
