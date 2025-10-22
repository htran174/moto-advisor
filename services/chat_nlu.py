# services/chat_nlu.py
from __future__ import annotations
import os, json, re
from typing import Any, Dict, List, Optional

# -------------------------
# Config / constants
# -------------------------
ALLOWED_TYPES = {"cruiser", "sportbike", "naked", "adventure", "dual_sport", "standard", "touring"}

SYSTEM_PROMPT = """You are the RideReady NLU planner. Convert the user’s motorcycle request into a strict JSON plan.
OUTPUT RULES:
- Output a SINGLE JSON object and NOTHING ELSE. No prose outside JSON. No code fences.
- Use EXACT keys and enums from the schema. Omit unknown keys. Do not return nulls.

SCHEMA (example values only):
{
  "topic": "moto_recommendation",
  "message": "1-2 sentence rationale",
  "actions": [
    {
      "type": "UPDATE_PROFILE",
      "patch": {
        "bike_types": ["cruiser","sportbike","naked","adventure","dual_sport","standard","touring"],
        "budget_usd": 6500,
        "height_cm": 170,
        "experience": "no_experience|little_experience",
        "k": 2
      }
    },
    {
      "type": "RECOMMEND",
      "pin_ids": ["optional_bike_id_1","optional_bike_id_2"]
    }
  ]
}

REQUIREMENTS:
- ALWAYS include UPDATE_PROFILE with a patch.
- DEFAULT k to 2 unless the user explicitly asks for a different number.
- Map wording to enums: "ADV" → adventure; "dual sport"/"dual-sport" → dual_sport; "naked" and "standard" map to those exact strings.
- If the user is vague (e.g., "500cc bike"), infer a reasonable bike_types and STILL return UPDATE_PROFILE + RECOMMEND.
- If you know exact models from a common beginner set (e.g., r3, ninja 400, cbr300r, rebel 300, versys-x 300, vulcan s, sv650, mt-03, z400),
  include their IDs in pin_ids. Otherwise leave pin_ids empty.
- Only return the JSON object."""

# -------------------------
# Lightweight local fallback
# -------------------------
MOTO_TERMS = re.compile(r"\b(ride|riding|motorcycle|bike|helmet|cc|abs|yamaha|honda|kawasaki|suzuki|ktm|ducati|r3|cbr|ninja|rebel|mt[-\s]?0?3|z400|390\s*duke|seat|inseam|msf|gear|beginner)\b", re.I)

def _clamp_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))

def _norm_types(text: str) -> List[str]:
    t = text.lower()
    out: List[str] = []
    if "sportbike" in t or re.search(r"\bsport\b", t): out.append("sportbike")
    if "naked" in t: out.append("naked")
    if "standard" in t: out.append("standard")
    if "cruiser" in t: out.append("cruiser")
    if "adv" in t or "adventure" in t: out.append("adventure")
    if "dual-sport" in t or "dual sport" in t: out.append("dual_sport")
    if "touring" in t or "tour" in t: out.append("touring")
    # dedupe + only allowed
    dedup: List[str] = []
    for x in out:
        if x in ALLOWED_TYPES and x not in dedup:
            dedup.append(x)
    return dedup

def _parse_patch_fallback(text: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    t = text.lower()
    patch: Dict[str, Any] = {}

    # budget: "$6500", "under 7k"
    m = re.search(r"\$?\s*([1-2]?\d{3,5})\s*(usd|dollars?)?\b", t)
    if m:
        patch["budget_usd"] = _clamp_int(int(m.group(1)), 1000, 20000)
    else:
        m2 = re.search(r"under\s+(\d+(?:\.\d+)?)[kK]\b", t)
        if m2:
            patch["budget_usd"] = _clamp_int(int(float(m2.group(1)) * 1000), 1000, 20000)

    # height: "170cm" or "height 175"
    m = re.search(r"\b(\d{2,3})\s*cm\b", t) or re.search(r"\bheight\s*(\d{2,3})\b", t)
    if m:
        patch["height_cm"] = _clamp_int(int(m.group(1)), 130, 210)

    # experience (lightweight)
    if re.search(r"\b(no|zero|never|brand\s*new)\b.*\b(experience|ridden?)\b", t):
        patch["experience"] = "no_experience"
    elif re.search(r"\b(little|some|a\s*bit)\b.*\b(experience|ridden?)\b", t) or "dirt" in t:
        patch["experience"] = "little_experience"

    # types
    types = _norm_types(t)
    if types:
        patch["bike_types"] = types

    # k override: "show 3", "k=3", "top 4"
    m = re.search(r"\b(?:show|top|k\s*=?)(\s*=?\s*)(\d)\b", t)
    if m:
        patch["k"] = _clamp_int(int(m.group(2)), 1, 6)

    # default k=2 if neither user nor profile set it
    if "k" not in patch and profile.get("k") not in (1,2,3,4,5,6):
        patch["k"] = 2

    return patch

def _looks_like_recommend(text: str) -> bool:
    return bool(
        re.search(r"\b(recommend|suggest|what.*bike|show\s+me)\b", text, re.I)
        or re.search(r"\b\d{2,4}\s*cc\b", text, re.I)
        or _norm_types(text)
    )

def _fallback_plan(message: str, profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    prof = dict(profile or {})
    patch = _parse_patch_fallback(message, prof)
    actions: List[Dict[str, Any]] = []
    if patch:
        actions.append({"type": "UPDATE_PROFILE", "patch": patch})
    if _looks_like_recommend(message) or patch:
        actions.append({"type": "RECOMMEND"})
    return {
        "topic": "MOTO_DOMAIN",
        "message": "Updating your preferences and fetching suggestions…",
        "actions": actions
    }

# -------------------------
# OpenAI branch (JSON mode)
# -------------------------
def _openai_client():
    try:
        from openai import OpenAI
        return OpenAI()
    except Exception:
        return None

def _normalize_keys(plan: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """Hardens the model output: corrects enums, enforces k=2 default, ensures UPDATE_PROFILE before RECOMMEND."""
    topic = plan.get("topic") or "moto_recommendation"
    message = plan.get("message") or "Updating your preferences and fetching suggestions…"
    actions_in = plan.get("actions") or []

    # map legacy/foreign keys inside UPDATE_PROFILE.patch if present
    normalized_actions: List[Dict[str, Any]] = []
    patch_accum: Dict[str, Any] = {}

    for act in actions_in:
        if not isinstance(act, dict): 
            continue
        t = act.get("type")
        if t == "UPDATE_PROFILE":
            p = dict(act.get("patch") or {})
            # legacy key mapping
            if "type" in p and "bike_types" not in p:
                p["bike_types"] = [p.pop("type")]
            if "max_price" in p and "budget_usd" not in p:
                p["budget_usd"] = p.pop("max_price")
            if "price" in p and "budget_usd" not in p:
                p["budget_usd"] = p.pop("price")
            if "height" in p and "height_cm" not in p:
                p["height_cm"] = p.pop("height")

            # normalize types to allowed enums
            if "bike_types" in p:
                bt = p["bike_types"]
                if isinstance(bt, str):
                    bt = [bt]
                bt_norm = []
                for x in bt:
                    xl = (x or "").lower().strip()
                    if xl in ("adv", "adventure"): xl = "adventure"
                    if xl in ("dual", "dual-sport", "dual sport"): xl = "dual_sport"
                    if xl in ("std",): xl = "standard"
                    if xl in ("naked",): xl = "naked"
                    if xl in ("sport", "sportbike"): xl = "sportbike"
                    if xl in ("tour", "touring"): xl = "touring"
                    if xl in ("cruiser",): xl = "cruiser"
                    if xl in ("standard",): xl = "standard"
                    if xl in ALLOWED_TYPES and xl not in bt_norm:
                        bt_norm.append(xl)
                if bt_norm:
                    p["bike_types"] = bt_norm
                else:
                    p.pop("bike_types", None)

            patch_accum.update(p)

        elif t == "RECOMMEND":
            # keep RECOMMEND; pass through optional pin_ids if present
            normalized_actions.append({"type": "RECOMMEND", **({ "pin_ids": act.get("pin_ids") } if act.get("pin_ids") else {})})

    # default k=2 if neither set
    if "k" not in patch_accum and profile.get("k") not in (1,2,3,4,5,6):
        patch_accum["k"] = 2

    # Prepend UPDATE_PROFILE if we have any patch keys
    if patch_accum:
        normalized_actions.insert(0, {"type": "UPDATE_PROFILE", "patch": patch_accum})

    # If there are no actions at all, fall back to a single RECOMMEND to keep UX responsive
    if not normalized_actions:
        normalized_actions = [{"type": "UPDATE_PROFILE", "patch": {"k": 2}}, {"type": "RECOMMEND"}]

    return {"topic": topic, "message": message, "actions": normalized_actions}

def make_plan(message: str, profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Main entry:
    - Try OpenAI in JSON mode with a strict system prompt.
    - Normalize/guard the output (map legacy keys, enforce enums, default k=2).
    - If anything fails, use the local fallback parser.
    """
    text = (message or "").strip()
    prof = dict(profile or {})

    # If clearly non-moto text, return a gentle nudge (still safe JSON)
    if not MOTO_TERMS.search(text):
        return {
            "topic": "OFFTOPIC",
            "message": "I can help with beginner-friendly motorcycle and gear advice. Try asking about style, budget, size, or features.",
            "actions": []
        }

    client = _openai_client()
    api_key = os.getenv("OPENAI_API_KEY")
    use_openai = bool(client and api_key)

    if use_openai:
        try:
            # JSON mode (OpenAI Python SDK v1)
            resp = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text}
                ],
                temperature=0.2,
                max_tokens=400
            )
            raw = resp.choices[0].message.content or "{}"
            plan = json.loads(raw)
            return _normalize_keys(plan, prof)
        except Exception:
            # fall through to local
            pass

    # Fallback (no API key, network error, or invalid JSON)
    return _fallback_plan(text, prof)
