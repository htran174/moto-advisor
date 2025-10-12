# services/recommend_rules.py
from __future__ import annotations
from typing import Dict, List, Any
import math

ALLOWED_TYPES = {"cruiser", "standard", "sportbike", "naked", "adventure", "touring", "dual_sport"}

def clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(n)))

def validate_profile(p: Dict[str, Any]) -> Dict[str, Any]:
    exp = p.get("experience", "no_experience")
    if exp not in ("no_experience", "little_experience"):
        exp = "no_experience"

    height_cm = clamp(p.get("height_cm", 170), 140, 210)
    budget_usd = clamp(p.get("budget_usd", 6000), 1000, 20000)

    k = clamp(p.get("k", 3), 1, 6)

    bike_types = p.get("bike_types") or []
    if not isinstance(bike_types, list):
        bike_types = []
    bike_types = [t for t in bike_types if t in ALLOWED_TYPES][:5]

    return {
        "experience": exp,
        "height_cm": height_cm,
        "budget_usd": budget_usd,
        "k": k,
        "bike_types": bike_types,
        "riding_style": []  # reserved for future
    }

def _height_match_score(seat_height_mm: int, rider_height_cm: int) -> float:
    # crude heuristic: inseam ~ 0.45 * height_cm; target seat around inseam +/- 30mm
    inseam_mm = rider_height_cm * 10 * 0.45
    if seat_height_mm is None:
        return 0.0
    diff = abs(seat_height_mm - inseam_mm)
    return max(0.0, 1.0 - (diff / 120.0))  # within ~12cm is good

def _beginner_power_guard(exp: str, max_speed_mph: float | None, zero_to_sixty_s: float | None) -> float:
    """Return a dampener (0..1) — lower if bike is very fast and rider has no experience."""
    if exp != "no_experience":
        return 1.0
    damp = 1.0
    if max_speed_mph is not None and max_speed_mph >= 115:
        damp *= 0.9
    if zero_to_sixty_s is not None and zero_to_sixty_s <= 5.0:
        damp *= 0.9
    return damp

def _base_reason_list(bike: Dict[str, Any], prof: Dict[str, Any]) -> List[str]:
    R = []
    if bike.get("abs") is True:
        R.append("Has ABS")
    if bike.get("wet_weight_kg") is not None and bike["wet_weight_kg"] <= 172:
        R.append("Lightweight")
    if bike.get("seat_height_mm") is not None:
        hm = _height_match_score(bike["seat_height_mm"], prof["height_cm"])
        if hm >= 0.7:
            R.append("Seat height close to estimated inseam")
    return R[:5]

def recommend(bikes: List[Dict[str, Any]], profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    prof = validate_profile(profile)

    # Type filter (optional)
    filtered = []
    bt_set = set(prof["bike_types"])
    for b in bikes:
        cat = (b.get("category") or "").lower()
        if bt_set and cat not in bt_set:
            continue
        filtered.append(b)

    # Score with light heuristics
    ranked = []
    for b in filtered:
        score = 0.0
        # Height match
        score += 0.6 * _height_match_score(b.get("seat_height_mm"), prof["height_cm"])
        # Weight preference (lighter is nicer for beginners)
        w = b.get("wet_weight_kg")
        if isinstance(w, (int, float)):
            score += 0.25 * max(0.0, 1.0 - (w - 150) / 60.0)  # 150kg → 1.0, 210kg → 0.0 approx
        # ABS small bonus
        if b.get("abs") is True:
            score += 0.05
        # Beginner guard on spicy bikes
        damp = _beginner_power_guard(prof["experience"], b.get("max_speed_mph"), b.get("zero_to_sixty_s"))
        score *= damp

        ranked.append((score, b))

    ranked.sort(key=lambda t: t[0], reverse=True)
    k = prof["k"]
    out: List[Dict[str, Any]] = []
    for score, b in ranked[:k*3]:  # take extra then the client can prefer style-first; also gives us buffer
        item = {
            "id": b["id"],
            "name": b["name"],
            "manufacturer": b["manufacturer"],
            "category": b["category"],
            "engine_cc": b.get("engine_cc"),
            "seat_height_mm": b.get("seat_height_mm"),
            "wet_weight_kg": b.get("wet_weight_kg"),
            "abs": b.get("abs"),
            # performance
            "max_speed_mph": b.get("max_speed_mph"),
            "zero_to_sixty_s": b.get("zero_to_sixty_s"),
            # links
            "official_url": b.get("official_url"),
            "mfr_domain": b.get("mfr_domain"),
            # reasons
            "reasons": _base_reason_list(b, prof),
            # hint for images service (prefer local)
            "local_image": b.get("local_image")
        }
        out.append(item)

    return out[:max(k, 1)]
