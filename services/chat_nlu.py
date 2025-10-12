# services/chat_nlu.py
from __future__ import annotations
import re
from typing import Dict, Any, List, Tuple

ALLOWED_TYPES = {"cruiser","standard","sportbike","naked","adventure","touring","dual_sport"}

# Very small, fast, offline topic gate.
MOTO_TERMS = re.compile(
    r"\b(ride|riding|motorcycle|bike|helmet|cc|abs|yamaha|honda|kawasaki|suzuki|ktm|ducati|"
    r"r3|cbr|ninja|rebel|mt[-\s]?03|z400|390\s*duke|seat|inseam|msf|gear|beginner)\b",
    re.I
)
OFFTOPIC_TERMS = re.compile(
    r"\b(python|javascript|recipe|stocks?|crypto|politics|election|taxes?|medical|diagnosis|"
    r"homework|poem|novel|lyrics|song|news|celebrity|football|basketball)\b",
    re.I
)

def classify_topic(text: str) -> str:
    t = text.lower()
    if OFFTOPIC_TERMS.search(t) and not MOTO_TERMS.search(t):
        return "OFFTOPIC"
    if MOTO_TERMS.search(t):
        return "MOTO_DOMAIN"
    return "AMBIGUOUS"

def _extract_int(value: str, lo: int, hi: int) -> int | None:
    m = re.search(r"(-?\d+)", value)
    if not m: 
        return None
    n = int(m.group(1))
    return max(lo, min(hi, n))

def parse_profile_patch(text: str) -> Dict[str, Any]:
    """Extract height, budget, experience, types from free text."""
    t = text.lower()

    patch: Dict[str, Any] = {}

    # Height cm (allow '175 cm' or 'height 175')
    if "cm" in t or "height" in t:
        n = _extract_int(t, 140, 210)
        if n: patch["height_cm"] = n

    # Budget USD (allow $6500 or 6500 usd)
    m = re.search(r"\$?\s*(\d{3,5})\s*(usd|dollars?)?", t)
    if m:
        budget = int(m.group(1))
        patch["budget_usd"] = max(1000, min(20000, budget))

    # Experience
    if re.search(r"\b(no|zero|never|brand\s*new)\b.*\b(experience|ridden?)\b", t):
        patch["experience"] = "no_experience"
    elif re.search(r"\b(little|some|a\s*bit)\b.*\b(experience|ridden?)\b", t) or "atv" in t or "dirt" in t:
        patch["experience"] = "little_experience"

    # Types
    types: List[str] = []
    for typ in ALLOWED_TYPES:
        if re.search(rf"\b{re.escape(typ).replace('_','[-\s]?')}\b", t):
            types.append(typ)
    if types:
        patch["bike_types"] = sorted(set(types))[:5]

    return patch

def parse_slash_commands(text: str) -> Tuple[Dict[str, Any], bool, bool]:
    """
    Supports:
      /set height=175 budget=7000 types=naked,sportbike exp=no_experience k=3
      /rec
    """
    t = text.strip()
    if not t.startswith("/"):
        return {}, False, False

    if t.startswith("/rec"):
        return {}, False, True

    if t.startswith("/set"):
        parts = t.split()[1:]
        patch: Dict[str, Any] = {}
        for p in parts:
            if "=" not in p: 
                continue
            k, v = p.split("=", 1)
            k = k.lower().strip()
            v = v.lower().strip()
            if k in ("height","height_cm"):
                n = _extract_int(v, 140, 210)
                if n: patch["height_cm"] = n
            elif k in ("budget","budget_usd"):
                n = _extract_int(v, 1000, 20000)
                if n: patch["budget_usd"] = n
            elif k in ("exp","experience"):
                patch["experience"] = "little_experience" if "little" in v else "no_experience"
            elif k == "types":
                arr = [s.strip() for s in v.split(",") if s.strip() in ALLOWED_TYPES]
                patch["bike_types"] = arr[:5]
            elif k == "k":
                n = _extract_int(v, 1, 6)
                if n: patch["k"] = n
        return patch, True, False

    return {}, False, False

def nlu(text: str) -> Dict[str, Any]:
    """
    Returns a JSON plan with actions (no side effects):
    {
      "topic": "MOTO_DOMAIN|AMBIGUOUS|OFFTOPIC",
      "actions": [ {"type":"UPDATE_PROFILE","patch":{...}}, {"type":"RECOMMEND"} ],
      "message": "assistant message to show"
    }
    """
    text = (text or "").strip()
    if not text:
        return {"topic":"AMBIGUOUS", "actions": [], "message":"Say something about bikes, budget, height, or types."}

    # Slash commands first
    patch, is_set, is_rec = parse_slash_commands(text)
    if is_set:
        msg = "Updated your profile."
        acts = [{"type":"UPDATE_PROFILE","patch":patch}] if patch else []
        return {"topic":"MOTO_DOMAIN", "actions": acts, "message": msg}
    if is_rec:
        return {"topic":"MOTO_DOMAIN", "actions":[{"type":"RECOMMEND"}], "message":"Running recommendations."}

    topic = classify_topic(text)
    if topic == "OFFTOPIC":
        return {"topic":"OFFTOPIC", "actions": [], 
                "message":"I’m for motorcycle & gear guidance. Ask about bikes, fit/height, budget, or types."}

    # MOTO or ambiguous: try to extract a patch and maybe recommend
    patch = parse_profile_patch(text)
    actions: List[Dict[str,Any]] = []
    msg = "Got it."
    if patch:
        actions.append({"type":"UPDATE_PROFILE","patch":patch})
        msg = "Updated your profile."
    # If the text looks like a request to recommend
    if re.search(r"\b(recommend|suggest|what.*bike|show\s+me)\b", text, re.I):
        actions.append({"type":"RECOMMEND"})
        msg = "Here are updated suggestions."
    return {"topic": "MOTO_DOMAIN" if topic=="MOTO_DOMAIN" else "AMBIGUOUS", 
            "actions": actions, "message": msg}
