"""
services/recommend_rules.py
Implements beginner-friendly motorcycle recommendation logic.
Used by /api/recommend to filter bikes.json and explain why
each result was chosen.
"""

import json
import os

DATA_PATH = os.path.join("data", "bikes.json")


# ---------------------------------------------------------------------
# Load the whitelist
# ---------------------------------------------------------------------
def load_bikes() -> list[dict]:
    """Read and return the bikes whitelist as a list of dicts."""
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            bikes = json.load(f)
        return bikes
    except Exception as e:
        print(f"[recommend] Could not load bikes.json: {e}")
        return []


# ---------------------------------------------------------------------
# Apply filters to match user profile
# ---------------------------------------------------------------------
def apply_filters(bikes: list[dict], profile: dict) -> list[dict]:
    """Filter bikes based on profile fields (experience, height, budget, types, etc.)."""
    exp = profile.get("experience", "no_experience")
    height = profile.get("height_cm", 170)
    budget = profile.get("budget_usd", 6000)
    types = profile.get("bike_types", [])
    k = int(profile.get("k", 3))

    results = []
    for b in bikes:
        ok = True

        # Filter by type
        if types and b.get("category") not in types:
            ok = False

        # Height: remove bikes too tall for short riders
        seat = b.get("seat_height_mm", 0)
        if height < 165 and seat > 790:
            ok = False

        # Budget: simple check if MSRP exists
        msrp = b.get("msrp_usd") or budget  # placeholder
        if msrp > budget * 1.2:
            ok = False

        if ok:
            results.append(b)

    # Limit number of results
    return results[:k]


# ---------------------------------------------------------------------
# Pick reasons for display
# ---------------------------------------------------------------------
def pick_reasons(bike: dict, profile: dict) -> list[str]:
    """Explain why a bike was selected."""
    reasons = []
    cat = bike.get("category")
    if cat:
        reasons.append(f"{cat.title()} style fits your preference.")

    seat = bike.get("seat_height_mm")
    if seat:
        if profile.get("height_cm", 170) < 170 and seat < 785:
            reasons.append(f"Lower seat height ({seat} mm) — easier for shorter riders.")
        elif seat > 820:
            reasons.append(f"Taller stance ({seat} mm) — suitable for bigger riders.")

    if bike.get("abs"):
        reasons.append("Comes with ABS for added safety.")
    if bike.get("engine_cc") and bike["engine_cc"] <= 500:
        reasons.append("Beginner-friendly engine size.")
    if bike.get("wet_weight_kg") and bike["wet_weight_kg"] <= 185:
        reasons.append("Lightweight and easy to handle.")

    return reasons or ["Good overall fit for beginners."]
