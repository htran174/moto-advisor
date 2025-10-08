# services/recommend_rules.py
from dataclasses import dataclass
from typing import Dict, Any, List, Tuple

@dataclass
class RiderProfile:
    experience: str            # "new" | "returning"
    height_cm: int             # e.g., 170
    budget_usd: int            # e.g., 6000
    riding_style: List[str]    # e.g., ["commute","weekend"]
    must_have: List[str]       # e.g., ["abs"]

def estimate_inseam_cm(height_cm: int) -> float:
    # Simple anthropometric approximation (works well enough for coarse filtering)
    return round(height_cm * 0.45, 1)

def budget_tier(budget_usd: int) -> str:
    if budget_usd < 4500: return "low"
    if budget_usd <= 8000: return "mid"
    return "high"

def score_bike(bike: Dict[str, Any], profile: RiderProfile) -> Tuple[float, List[str]]:
    """
    Returns (score, reasons[])
    """
    reasons: List[str] = []
    score = 0.0

    # 1) ABS preference
    if "abs" in [s.lower() for s in profile.must_have]:
        if bike.get("abs"):
            score += 15; reasons.append("Has ABS (requested)")
        else:
            return (-1, ["Rejected: lacks ABS which you requested"])

    # 2) Weight (lighter is friendlier)
    w = bike.get("wet_weight_kg", 999)
    if w <= 175: score += 18; reasons.append("Lightweight")
    elif w <= 190: score += 10; reasons.append("Moderate weight")
    else: score += 2; reasons.append("Heavier for a beginner")

    # 3) Engine displacement (gentle for new riders)
    cc = bike.get("engine_cc", 9999)
    cat = (bike.get("category") or "").lower()
    if profile.experience == "new":
        if cat == "cruiser":
            # cruisers tolerate a bit more cc due to tune/weight
            cc_score = 18 if cc <= 650 else (10 if cc <= 750 else 0)
        else:
            cc_score = 18 if 250 <= cc <= 500 else (12 if cc < 250 else 6 if cc <= 650 else 0)
    else:
        cc_score = 16 if 300 <= cc <= 650 else 8
    score += cc_score

    # 4) Seat height vs estimated inseam
    inseam_cm = estimate_inseam_cm(profile.height_cm)
    seat_cm = bike.get("seat_height_mm", 0) / 10.0
    delta = seat_cm - inseam_cm
    if -3 <= delta <= 3:
        score += 18; reasons.append("Seat height matches estimated inseam")
    elif -5 <= delta <= 5:
        score += 12; reasons.append("Seat height close to inseam")
    else:
        score += 4; reasons.append("Seat height may feel tall/short")

    # 5) Budget tier
    tier = budget_tier(profile.budget_usd)
    if bike.get("budget_tier") == tier:
        score += 12; reasons.append(f"Fits your {tier} budget")
    else:
        score += 5; reasons.append("Possible with stretch or deal")

    # 6) Built-in prior (beginner_score from whitelist)
    score += (bike.get("beginner_score", 70) - 70) * 0.6  # modest influence

    return (round(score, 2), reasons)

def shortlist(bikes: List[Dict[str, Any]], profile: RiderProfile, k: int = 3) -> List[Dict[str, Any]]:
    scored: List[Tuple[float, Dict[str, Any], List[str]]] = []
    for b in bikes:
        s, rs = score_bike(b, profile)
        if s >= 0:
            item = dict(b)
            item["_score"] = s
            item["_reasons"] = rs
            scored.append((s, item, rs))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [t[1] for t in scored[:k]]
