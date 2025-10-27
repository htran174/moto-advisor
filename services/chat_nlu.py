# services/chat_nlu.py
from __future__ import annotations

import json, re, math
from typing import Any, Dict, List, Optional

from openai import OpenAI

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _to_int(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        s = v.strip().lower().replace('mph', '').replace('km/h', '')
        s = ''.join(ch for ch in s if (ch.isdigit() or ch in '.-'))
        try:
            return int(float(s))
        except Exception:
            return None
    return None

def _to_float(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().lower().replace('s', '')
        s = ''.join(ch for ch in s if (ch.isdigit() or ch in '.-'))
        try:
            return float(s)
        except Exception:
            return None
    return None

def _coerce_actions(actions: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(actions, list):
        return out
    for a in actions:
        if not isinstance(a, dict):
            continue
        t = (a.get("type") or a.get("action") or "").upper()
        if t != "RECOMMEND":
            # Only one action type for now
            continue

        # Accept both "details" and top-level fields
        d = a.get("details") if isinstance(a.get("details"), dict) else {}

        # Promote / normalize fields
        brand = a.get("brand") or d.get("brand")
        model = a.get("model") or d.get("model")
        engine_cc = _to_int(a.get("engine_cc") or d.get("engine_cc"))
        top_speed_mph = _to_int(a.get("top_speed_mph") or d.get("top_speed_mph"))
        zero_to_sixty_s = _to_float(a.get("zero_to_sixty_s") or d.get("zero_to_sixty_s"))

        notes = (
            a.get("notes")
            or a.get("description")
            or d.get("notes")
            or d.get("description")
            or ""
        )

        official_url = a.get("official_url") or d.get("official_url") or ""
        image_query = a.get("image_query") or d.get("image_query") or ""

        # Build normalized action
        out.append({
            "type": "RECOMMEND",
            "brand": brand,
            "model": model,
            "engine_cc": engine_cc,
            "top_speed_mph": top_speed_mph,
            "zero_to_sixty_s": zero_to_sixty_s,
            "official_url": official_url,
            "image_query": image_query,
            "notes": notes
        })
    return out

def _brief_actions_for_log(actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    brief = []
    for a in actions:
        brief.append({
            "type": a.get("type"),
            "model": a.get("model"),
            "top_speed_mph": a.get("top_speed_mph"),
            "zero_to_sixty_s": a.get("zero_to_sixty_s"),
        })
    return brief

def _pair_alternative(rec):
    """
    If the model only returns one bike, suggest a sensible second one.
    Very small heuristic map for 500-ish cc sportbikes.
    """
    model = (rec.get("model") or "").lower()
    if "ninja 500" in model or "ninja 500r" in model or "versys" in model:
        return {
            "type": "RECOMMEND",
            "brand": "Honda",
            "model": "CBR500R",
            "category": "sportbike",
            "max_speed_mph": 112,
            "zero_to_sixty_s": 5.6,
            "official_url": "https://powersports.honda.com/motorcycle/sport/cbr500r",
            "image_query": "Honda CBR500R"
        }
    if "cbr500" in model:
        return {
            "type": "RECOMMEND",
            "brand": "Kawasaki",
            "model": "Ninja 500R",
            "category": "sportbike",
            "max_speed_mph": 120,
            "zero_to_sixty_s": 5.0,
            "official_url": "https://www.kawasaki.com/en-us/motorcycle/ninja/ninja-500r",
            "image_query": "Kawasaki Ninja 500R"
        }
    if "rc 390" in model or "rc390" in model:
        return {
            "type": "RECOMMEND",
            "brand": "Yamaha",
            "model": "YZF-R3",
            "category": "sportbike",
            "max_speed_mph": 112,
            "zero_to_sixty_s": 5.6,
            "official_url": "https://www.yamahamotorsports.com/supersport/models/yzf-r3",
            "image_query": "Yamaha YZF-R3"
        }
    # generic fallback pair
    return {
        "type": "RECOMMEND",
        "brand": "Honda",
        "model": "CBR500R",
        "category": "sportbike",
        "max_speed_mph": 112,
        "zero_to_sixty_s": 5.6,
        "official_url": "https://powersports.honda.com/motorcycle/sport/cbr500r",
        "image_query": "Honda CBR500R"
    }

# ------------------------------------------------------------
# Prompt
# ------------------------------------------------------------

SYSTEM_PROMPT = """You are a planner that returns STRICT JSON for motorcycle recommendations.

Return a single JSON object with:
{
  "topic": "motorcycle_recommendation",
  "message": "<one-line user-facing summary>",
  "actions": [
    {
      "type": "RECOMMEND",
      "brand": "<brand name (optional)>",
      "model": "<model name (required)>",
      "engine_cc": <number>,                // e.g., 500
      "max_speed_mph": <number>,            // e.g., 112
      "zero_to_sixty_s": <number>,          // e.g., 5.2
      "official_url": "<url or empty string>",
      "image_query": "<brand and model or useful query>",
      "notes": "<short helpful note>"
    }
  ]
}

Rules:
- Output MUST be valid JSON only; no explanations.
- Populate numeric fields with best-known approximate values (integers for mph; decimals OK for 0–60).
- Prefer common/current model names; if unsure, pick the nearest commonly known spec.
- Keep "message" short and friendly (one sentence).
"""

# ------------------------------------------------------------
# Public API
# ------------------------------------------------------------

def make_plan(user_msg: str, profile: dict, logger=None, client=None, model_name: str = "gpt-4o-mini") -> dict:
    """
    Produce a strict JSON plan with exactly TWO RECOMMEND actions when recommending bikes.
    Also returns `external_items` (max 2) normalized for the recommender.
    """
    system = (
        "You are a planning assistant for a motorcycle recommender.\n"
        "Respond ONLY with a strict JSON object having keys: topic, message, actions.\n"
        "If the user asks for or implies a recommendation, actions MUST contain EXACTLY TWO\n"
        "items with this shape (no more, no less):\n"
        '{\"type\":\"RECOMMEND\",\"brand\":\"...\",\"model\":\"...\",\"category\":\"sportbike\",'
        '\"max_speed_mph\": <int>, \"zero_to_sixty_s\": <float>,'
        '\"official_url\":\"...\",\"image_query\":\"<brand and model or useful query>\"}\n'
        "Use numbers (not strings) for speeds/accel. If only one speed is known, set max_speed_mph.\n"
        "Prefer common, real models that a US rider can buy. Keep message short and helpful."
    )

    user = {
        "role": "user",
        "content": (
            f"User message: {user_msg}\n\n"
            f"Current profile (may be empty): {json.dumps(profile, ensure_ascii=False)}"
        ),
    }

    if logger:
        logger.info("[NLU] Calling OpenAI model=%s | msg=%r", model_name, user_msg)

    if client is None and OpenAI is not None:
        client = OpenAI()

    raw_text = ""
    try:
        resp = client.responses.create(
            model=model_name,
            input=[{"role": "system", "content": system}, user],
            temperature=0.2,
            max_output_tokens=400,
            # response_format={"type": "json_object"},  # enable if your SDK supports it
        )
        raw_text = resp.output_text
    except Exception as e:
        if logger:
            logger.exception("NLU call failed: %s", e)
        return {"topic": "fallback", "message": "Sorry—something went wrong.", "actions": [], "external_items": []}

    def _parse_json(s: str):
        s = (s or "").strip()
        try:
            return json.loads(s)
        except Exception:
            pass
        m = re.search(r"\{.*\}", s, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        return None

    data = _parse_json(raw_text) or {"topic": "motorcycle_recommendation", "message": user_msg, "actions": []}

    actions = data.get("actions") or []
    if isinstance(actions, dict):
        actions = [actions]
    actions = [a for a in actions if isinstance(a, dict)]

    ups = [a for a in actions if a.get("type") == "UPDATE_PROFILE"]
    recs = [a for a in actions if a.get("type") == "RECOMMEND"]

    # --- ENFORCE exactly two recommendations ---
    if len(recs) == 1:
        recs.append(_pair_alternative(recs[0]))
    elif len(recs) == 0:
        # generic two if the model whiffs completely
        recs = [
            {
                "type": "RECOMMEND",
                "brand": "Kawasaki",
                "model": "Ninja 500R",
                "category": "sportbike",
                "max_speed_mph": 120,
                "zero_to_sixty_s": 5.0,
                "official_url": "https://www.kawasaki.com/en-us/motorcycle/ninja/ninja-500r",
                "image_query": "Kawasaki Ninja 500R",
            },
            _pair_alternative({"model": "Ninja 500R"})
        ]
    else:
        recs = recs[:2]

    # normalize and build external items
    external_items = []
    norm_recs = []
    for act in recs:
        brand = (act.get("brand") or "").strip()
        model = (act.get("model") or "").strip()
        category = (act.get("category") or "sportbike").strip()

        speed = _to_int(act.get("max_speed_mph"))
        zero_to_sixty = _to_float(act.get("zero_to_sixty_s"))
        official_url = (act.get("official_url") or "").strip() or None
        image_query = (act.get("image_query") or f"{brand} {model}".strip()) or None

        norm = {
            "type": "RECOMMEND",
            "brand": brand or None,
            "model": model,
            "category": category or None,
            "max_speed_mph": speed,
            "zero_to_sixty_s": zero_to_sixty,
            "official_url": official_url,
            "image_query": image_query,
        }
        norm_recs.append(norm)

        external_items.append({
            "brand": norm["brand"],
            "model": norm["model"],
            "category": norm["category"],
            "top_speed_mph": speed,     # keep both keys happy downstream
            "max_speed_mph": speed,
            "zero_to_sixty_s": zero_to_sixty,
            "official_url": official_url,
            "image_query": image_query,
        })

    data["actions"] = ups + norm_recs
    data["external_items"] = external_items

    if logger:
        logger.info("[NLU] Plan -> %s", data)

    return data