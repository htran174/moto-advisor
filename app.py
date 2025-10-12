# app.py
from flask import Flask, render_template, jsonify, request, url_for
from pathlib import Path
import json

APP_TITLE = "RideReady"
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
STATIC_DIR = ROOT / "static"

app = Flask(
    __name__,
    template_folder=str(ROOT / "templates"),
    static_folder=str(STATIC_DIR),
)

# Make APP_TITLE available to all templates (home.html uses {{ app_title }})
@app.context_processor
def inject_globals():
    return {"app_title": APP_TITLE}

# ---------- Pages ----------
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

# ---------- Utilities ----------
def load_bikes():
    with open(DATA_DIR / "bikes.json", "r", encoding="utf-8") as f:
        return json.load(f)

def basic_filter(items, profile):
    """Very light filtering to prove the flow works."""
    want_types = set(profile.get("bike_types") or [])
    k = int(max(1, min(6, profile.get("k", 3))))
    # If user picked no types, just return the first k
    if not want_types:
        return items[:k]
    out = [b for b in items if b.get("category") in want_types]
    if len(out) < k:
        # top-up with anything else
        seen = {id(b) for b in out}
        for b in items:
            if id(b) not in seen:
                out.append(b)
            if len(out) >= k:
                break
    return out[:k]

def pick_reasons(bike, profile):
    reasons = []
    # friendly demo reasons
    if bike.get("abs"):
        reasons.append("ABS available for safer braking")
    if bike.get("engine_cc", 0) <= 400:
        reasons.append("Beginner-friendly displacement (≤400cc)")
    if bike.get("seat_height_mm"):
        reasons.append(f"Seat height ~{bike['seat_height_mm']} mm")
    return reasons[:3]

def local_image_url(local_image):
    if not local_image:
        return url_for("static", filename="stock_images/motorcycle_ride.jpg")
    # put your JPGs in static/stock_images/
    return url_for("static", filename=f"stock_images/{local_image}")

# ---------- APIs expected by JS ----------
@app.route("/api/recommend", methods=["POST"])
def api_recommend():
    profile = request.get_json(force=True) or {}
    bikes = load_bikes()
    chosen = basic_filter(bikes, profile)
    # add reasons for the cards
    for b in chosen:
        b["reasons"] = pick_reasons(b, profile)
    return jsonify({"items": chosen})

@app.route("/api/images", methods=["POST"])
def api_images():
    """Return a single best image URL for the given bike id/local_image.
       Your recommendations.js falls back to /static/motorcyle_ride.jpg (typo); we’ll give a good local path."""
    data = request.get_json(force=True) or {}
    local = data.get("local_image")
    return jsonify({"images": [{"url": local_image_url(local)}]})

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Prototype: echo a small plan and possibly trigger a re-run on the client."""
    req = request.get_json(force=True) or {}
    msg = (req.get("message") or "").strip().lower()
    actions = []
    say = "Got it."
    if msg.startswith("/set"):
        # demo: /set k=3
        try:
            patch = {}
            for part in msg.split()[1:]:
                if "=" in part:
                    k, v = part.split("=", 1)
                    if k == "k":
                        patch["k"] = int(v)
            if patch:
                actions.append({"type": "UPDATE_PROFILE", "patch": patch})
                say = f"Updated profile: {patch}. "
        except Exception:
            pass
    if "/rec" in msg or "recommend" in msg:
        actions.append({"type": "RECOMMEND"})
        say += "I’ll refresh your recommendations."
    return jsonify({"message": say, "actions": actions})

if __name__ == "__main__":
    # Ensure folders exist
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (STATIC_DIR / "stock_images").mkdir(parents=True, exist_ok=True)
    app.run(debug=True)
