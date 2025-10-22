# services/chat_nlu.py
from __future__ import annotations
import os, json, re
from typing import Any, Dict, List, Optional

# -------------------------
# Config / constants
# -------------------------
ALLOWED_TYPES = {"cruiser", "sportbike", "naked", "adventure", "dual_sport", "standard", "touring"}
MAX_ITEMS = 2  # exactly 2 total (catalog + external combined), unless user asks for different k (still capped at 2 by default)

SYSTEM_PROMPT = """You are the RideReady NLU planner. Convert the user's motorcycle request into a strict JSON plan.
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
      "pin_ids": ["optional_catalog_id_1","optional_catalog_id_2"],
      "items": [
        { "id": "optional_catalog_id" },
        {
          "label": "External model name",
          "specs": {
            "engine_cc": 313,
            "seat_height_mm": 785,
            "wet_weight_kg": 164,
            "abs": true,
            "max_speed_mph": 90,
            "zero_to_sixty_s": 7.5,
            "category": "standard|sportbike|cruiser|naked|adventure|dual_sport|touring"
          },
          "official_url": "https://...",
          "mfr_domain": "bmw-motorrad.com",
          "image_query": "BMW G 310 R"
        }
      ]
    }
  ]
}

REQUIREMENTS:
- Action names MUST be exactly "UPDATE_PROFILE" then "RECOMMEND" (uppercase).
- ALWAYS include UPDATE_PROFILE with a patch.
- DEFAULT k to 2 unless the user explicitly asks for a different number. Keep total recommended items to 2 unless the user specifies k.
- Map wording to enums: "ADV" → adventure; "dual sport"/"dual-sport" → dual_sport; "naked" and "standard" map to those exact strings.
- Prefer our catalog IDs in "pin_ids" or "items[].id" when you recognize them (e.g., r3, ninja_400, cbr300r, rebel_300, versys_x_300, vulcan_s, sv650, mt03, z400).
- If a requested bike is not in our catalog, return it in "items" with at least "label" and an "image_query". Include "specs" when you know them.
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
    dedup: List[str] = []
    for x in out:
        if x in ALLOWED_TYPES and x not in dedup:
            dedup.append(x)
    return dedup

def _parse_patch_fallback(text: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    t = text.lower()
    patch: Dict[str, Any] = {}

    m = re.search(r"\$?\s*([1-2]?\d{3,5})\s*(usd|dollars?)?\b", t)
    if m:
        patch["budget_usd"] = _clamp_int(int(m.group(1)), 1000, 20000)
    else:
        m2 = re.search(r"under\s+(\d+(?:\.\d+)?)[kK]\b", t)
        if m2:
            patch["budget_usd"] = _clamp_int(int(float(m2.group(1)) * 1000), 1000, 20000)

    m = re.search(r"\b(\d{2,3})\s*cm\b", t) or re.search(r"\bheight\s*(\d{2,3})\b", t)
    if m:
        patch["height_cm"] = _clamp_int(int(m.group(1)), 130, 210)

    if re.search(r"\b(no|zero|never|brand\s*new)\b.*\b(experience|ridden?)\b", t):
        patch["experience"] = "no_experience"
    elif re.search(r"\b(little|some|a\s*bit)\b.*\b(experience|ridden?)\b", t) or "dirt" in t:
        patch["experience"] = "little_experience"

    types = _norm_types(t)
    if types:
        patch["bike_types"] = types

    m = re.search(r"\b(?:show|top|k\s*=?)(\s*=?\s*)(\d)\b", t)
    if m:
        patch["k"] = _clamp_int(int(m.group(2)), 1, 6)

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

def _is_update_profile(s: str) -> bool:
    s = (s or "").strip().lower()
    return s in ("update_profile", "updateprofile", "update")

def _is_recommend(s: str) -> bool:
    s = (s or "").strip().lower()
    return s in ("recommend", "recommendation", "recs", "run", "rerun")

def _normalize_types_list(bt) -> Optional[List[str]]:
    if not bt:
        return None
    if isinstance(bt, str):
        bt = [bt]
    out: List[str] = []
    for x in bt:
        xl = (x or "").lower().strip()
        if xl in ("adv", "adventure"): xl = "adventure"
        if xl in ("dual", "dual-sport", "dual sport"): xl = "dual_sport"
        if xl in ("sport", "sportbike"): xl = "sportbike"
        if xl in ("tour", "touring"): xl = "touring"
        if xl in ("std", "standard"): xl = "standard"
        if xl in ("naked",): xl = "naked"
        if xl in ("cruiser",): xl = "cruiser"
        if xl in ALLOWED_TYPES and xl not in out:
            out.append(xl)
    return out or None

def _normalize_keys(plan: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """Harden model output: correct enums, enforce k=2 default, ensure UPDATE_PROFILE then RECOMMEND, and accept external items."""
    topic = plan.get("topic") or "moto_recommendation"
    message = plan.get("message") or "Updating your preferences and fetching suggestions…"
    actions_in = plan.get("actions") or []

    normalized_actions: List[Dict[str, Any]] = []
    patch_accum: Dict[str, Any] = {}
    recommend_payload: Dict[str, Any] = {}

    for act in actions_in:
        if not isinstance(act, dict): 
            continue

        t_raw = act.get("type")
        if _is_update_profile(t_raw):
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

            bt_norm = _normalize_types_list(p.get("bike_types"))
            if bt_norm:
                p["bike_types"] = bt_norm
            else:
                p.pop("bike_types", None)

            patch_accum.update(p)

            # If the model used criteria/filters instead of patch, convert what we can
            crit = act.get("criteria") or act.get("filters") or {}
            if isinstance(crit, dict):
                if "bike_types" not in patch_accum:
                    bt2 = _normalize_types_list(crit.get("bike_types") or crit.get("type") or crit.get("category"))
                    if bt2: patch_accum["bike_types"] = bt2
                for key in ("budget_usd","max_price","price"):
                    if key in crit and "budget_usd" not in patch_accum:
                        try: patch_accum["budget_usd"] = int(crit[key])
                        except Exception: pass
                h = crit.get("height_cm") or crit.get("height")
                if h and "height_cm" not in patch_accum:
                    try: patch_accum["height_cm"] = int(h)
                    except Exception: pass
                if "k" in crit and "k" not in patch_accum:
                    try: patch_accum["k"] = int(crit["k"])
                    except Exception: pass

        elif _is_recommend(t_raw):
            # collect recommend payload (pin_ids and items)
            pin_ids = act.get("pin_ids") or []
            items = act.get("items") or []
            # normalize shapes
            norm_items: List[Dict[str, Any]] = []
            for it in items:
                if not isinstance(it, dict): 
                    continue
                if "id" in it and isinstance(it["id"], str) and it["id"].strip():
                    norm_items.append({"id": it["id"].strip()})
                elif "label" in it and isinstance(it["label"], str) and it["label"].strip():
                    ext = {
                        "label": it["label"].strip()
                    }
                    if isinstance(it.get("specs"), dict):
                        ext["specs"] = it["specs"]
                    if isinstance(it.get("mfr_domain"), str):
                        ext["mfr_domain"] = it["mfr_domain"]
                    if isinstance(it.get("official_url"), str):
                        ext["official_url"] = it["official_url"]
                    if isinstance(it.get("image_query"), str):
                        ext["image_query"] = it["image_query"]
                    norm_items.append(ext)
            recommend_payload = {}
            if pin_ids: recommend_payload["pin_ids"] = [pid for pid in pin_ids if isinstance(pid, str) and pid.strip()]
            if norm_items: recommend_payload["items"] = norm_items

    # Default k=2 if neither set
    if "k" not in patch_accum and profile.get("k") not in (1,2,3,4,5,6):
        patch_accum["k"] = 2

    # Cap to exactly 2 total items unless user asked for more (we still cap to MAX_ITEMS by design)
    k_eff = patch_accum.get("k", 2)
    k_cap = MAX_ITEMS if not isinstance(k_eff, int) else max(1, min(MAX_ITEMS, k_eff))

    if "items" in recommend_payload:
        recommend_payload["items"] = recommend_payload["items"][:k_cap]
    if "pin_ids" in recommend_payload:
        recommend_payload["pin_ids"] = recommend_payload["pin_ids"][:k_cap]

    # Prepend UPDATE_PROFILE if we have any patch keys
    if patch_accum:
        normalized_actions.append({"type": "UPDATE_PROFILE", "patch": patch_accum})

    # Always include RECOMMEND (even if model forgot), carrying the optional payload
    normalized_actions.append({"type": "RECOMMEND", **recommend_payload})

    return {"topic": topic, "message": message, "actions": normalized_actions}

def make_plan(message: str, profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Main entry:
    - Try OpenAI in JSON mode with a strict system prompt + few-shot directions.
    - Normalize/guard the output (map keys, enforce enums, cap items to 2).
    - If anything fails, use the local fallback parser.
    """
    text = (message or "").strip()
    prof = dict(profile or {})

    if not MOTO_TERMS.search(text):
        return {
            "topic": "OFFTOPIC",
            "message": "I can help with beginner-friendly motorcycle and gear advice. Try asking about style, budget, size, or features.",
            "actions": []
        }

    client = None
    api_key = os.getenv("OPENAI_API_KEY")
    try:
        from openai import OpenAI
        client = OpenAI() if api_key else None
    except Exception:
        client = None

    if client:
        try:
            resp = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    # A tiny few-shot to anchor external item behavior:
                    {"role": "user", "content": "I want an EU beginner sport bike like a BMW"},
                    {"role": "assistant", "content": json.dumps({
                        "topic": "moto_recommendation",
                        "message": "Here are beginner-friendly sport bikes including a BMW option.",
                        "actions": [
                            {"type": "UPDATE_PROFILE", "patch": {"bike_types": ["sportbike"], "k": 2}},
                            {"type": "RECOMMEND",
                             "items": [
                                {"id": "yamaha_r3"},
                                {"label": "BMW G 310 R",
                                 "specs": {"engine_cc": 313, "abs": True, "category": "standard"},
                                 "mfr_domain": "bmw-motorrad.com",
                                 "image_query": "BMW G 310 R"}]
                            }
                        ]
                    })},
                    {"role": "user", "content": text}
                ],
                temperature=0.2,
                max_tokens=500
            )
            raw = resp.choices[0].message.content or "{}"
            plan = json.loads(raw)
            return _normalize_keys(plan, prof)
        except Exception:
            pass

    # Fallback
    return _fallback_plan(text, prof)
