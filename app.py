import os
import json
import time
from flask import Flask, render_template, request, jsonify, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Services
from services.nlu import make_plan
from services.images import get_image_results
from services.recommend_rules import load_bikes, apply_filters, pick_reasons

APP_TITLE = "RideReady"
APP_BOOT_ID = str(int(time.time()))

app = Flask(__name__)

# Simple dev limiter (in-memory). Fine for local work.
limiter = Limiter(get_remote_address, app=app, default_limits=["200/day"])

# -------------------- helpers --------------------

def local_image_url(local_image: str | None) -> str:
    if not local_image:
        return url_for("static", filename="stock_images/motorcycle_ride.jpg")
    if not local_image.startswith("stock_images/"):
        local_image = f"stock_images/{local_image}"
    return url_for("static", filename=local_image)

def _run_recommend(profile: dict) -> list[dict]:
    """Apply filters and attach reasons; return list of bikes."""
    bikes = load_bikes()
    chosen = apply_filters(bikes, profile)
    for b in chosen:
        b.setdefault("id", b.get("name"))
        b["reasons"] = pick_reasons(b, profile)
    return chosen

# -------------------- pages ----------------------

@app.route("/")
def home():
    return render_template("home.html",
                           app_title=APP_TITLE, page_title="Home", boot_id=APP_BOOT_ID)

@app.route("/advisor")
def advisor():
    return render_template("advisor.html",
                           app_title=APP_TITLE, page_title="Advisor", boot_id=APP_BOOT_ID)

@app.route("/recommendations")
def recommendations():
    return render_template("recommendations.html",
                           app_title=APP_TITLE, page_title="Recommendations", boot_id=APP_BOOT_ID)

@app.route("/disclaimer")
def disclaimer():
    return render_template("disclaimer.html",
                           app_title=APP_TITLE, page_title="Disclaimer", boot_id=APP_BOOT_ID)

# -------------------- APIs ----------------------

@app.route("/api/recommend", methods=["POST"])
@limiter.limit("30/minute;300/day")
def api_recommend():
    profile = request.get_json(silent=True) or {}
    items = _run_recommend(profile)
    return jsonify({"items": items, "profile": profile})

@app.route("/api/images", methods=["POST"])
@limiter.limit("60/minute;600/day")
def api_images():
    data = request.get_json(silent=True) or {}
    return jsonify(get_image_results(data))

@app.route("/api/chat", methods=["POST"])
@limiter.limit("12/minute;120/day")
def api_chat():
    """
    Returns a plan + optional embedded recommendations so the Chat tab
    can render inline “card bubbles”, while the Recs tab stays in sync.
    """
    data = request.get_json(silent=True) or {}
    msg = data.get("message", "")
    profile = data.get("profile", {}) or {}

    plan = make_plan(msg, profile)

    # If the plan tells us to recommend, run the same logic as /api/recommend and attach.
    items = []
    for act in plan.get("actions", []):
        if act.get("type") == "UPDATE_PROFILE":
            patch = act.get("patch", {})
            profile.update(patch)
        if act.get("type") == "RECOMMEND":
            items = _run_recommend(profile)

    # Harmonize shape for the frontend
    return jsonify({
        "topic": plan.get("topic", "MOTO_DOMAIN"),
        "actions": plan.get("actions", []),
        "message": plan.get("message") or "Updating your preferences and refreshing recommendations.",
        "chat_reply": plan.get("chat_reply") or plan.get("message") or "Okay! I’ve updated your preferences.",
        "items": items,                 # inline recs for chat bubbles
        "profile": profile              # merged profile after actions
    })

@app.route("/healthz")
def healthz():
    limits = {
        "recommend": "30/minute;300/day",
        "images": "60/minute;600/day",
        "chat": "12/minute;120/day",
        "default_daily": "200/day",
    }
    ok = os.path.exists(os.path.join("data", "bikes.json"))
    return jsonify({
        "ok": ok,
        "bikes_json": ok,
        "limits": limits,
        "openai_enabled": os.getenv("RR_OPENAI_ENABLED", "false").lower() == "true"
    })

if __name__ == "__main__":
    app.run(debug=True)
