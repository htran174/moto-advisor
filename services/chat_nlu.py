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

def _pair_alternative(act: dict, bikes: list[dict]) -> dict:
    """
    If the model's recommended 'model' exists in local bikes.json,
    use the local bike data instead of the OpenAI-provided info.
    Otherwise, keep the original.
    """
    if not act or act.get("type") != "RECOMMEND":
        return act

    model_name = act.get("model", "").strip().lower()
    if not model_name:
        return act

    # Check if model exists in local bikes.json
    for bike in bikes:
        if bike.get("model", "").strip().lower() == model_name:
            # Found a match — use local data instead of OpenAI’s
            merged = dict(act)
            merged.update({
                "brand": bike.get("brand", merged.get("brand")),
                "model": bike.get("model", merged.get("model")),
                "category": bike.get("category", merged.get("category")),
                "top_speed_mph": bike.get("max_speed_mph", merged.get("top_speed_mph")),
                "zero_to_sixty_s": bike.get("zero_to_sixty_s", merged.get("zero_to_sixty_s")),
                "official_url": bike.get("official_url", merged.get("official_url")),
                "image_query": f"{bike.get('brand', '')} {bike.get('model', '')}".strip()
            })
            return merged

    # No local match — return original
    return act

# ------------------------------------------------------------
# Public API
# ------------------------------------------------------------

def make_plan(user_msg: str, profile: dict, logger=None, client=None, model_name: str = "gpt-4o-mini") -> dict:
    """
    Produce a strict JSON plan with up to TWO RECOMMEND actions when recommending bikes.
    Each RECOMMEND action now includes a short 'description' suitable to render
    beneath the corresponding card.

    Returns:
      {
        topic: str,
        message: str,
        actions: [ ... UPDATE_PROFILE and RECOMMEND ... ],
        external_items: [ {normalized for recommender} ]
      }
    """
    system = (
        "You are a planning assistant for a beginner motorcycle recommender.\n"
        "Respond ONLY with a strict JSON object with keys: topic, message, actions.\n"
        "If the user asks for or implies a recommendation, actions MUST contain two items unless user ask differently\n"
        "with this exact shape (numeric where applicable):\n"
        "{"
        "\"type\":\"RECOMMEND\","
        "\"brand\":\"...\","
        "\"model\":\"...\","
        "\"category\":\"sportbike\","
        "\"max_speed_mph\": <int or null>,"
        "\"zero_to_sixty_s\": <float or null>,"
        "\"official_url\":\"...\","
        "\"image_query\":\"<brand and model or useful query>\","
        "\"description\":\"<=35 words, neutral, beginner-suitable, what it’s like to own/ride\""
        "}\n"
        "Use *real, current* models a US rider can buy. Be honest about beginner suitability.\n"
        "Keep 'message' concise and helpful. Do not include extra keys."
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

    # Lazily create client the same way you already do elsewhere.
    if client is None and OpenAI is not None:
        client = OpenAI()

    raw_text = ""
    try:
        # Keep the same API style you were using to avoid any compatibility issues.
        resp = client.responses.create(
            model=model_name,
            input=[{"role": "system", "content": system}, user],
            temperature=0.2,
            max_output_tokens=400,
            # If your SDK supports it reliably, you can enable JSON mode:
            # response_format={"type": "json_object"},
        )
        raw_text = resp.output_text
    except Exception as e:
        if logger:
            logger.exception("NLU call failed: %s", e)
        return {
            "topic": "fallback",
            "message": "Sorry—something went wrong.",
            "actions": [],
            "external_items": [],
        }

    # --- tolerant JSON parsing (unchanged in spirit) ---
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

    data = _parse_json(raw_text) or {
        "topic": "motorcycle_recommendation",
        "message": user_msg,
        "actions": [],
    }

    actions = data.get("actions") or []
    if isinstance(actions, dict):
        actions = [actions]
    actions = [a for a in actions if isinstance(a, dict)]

    # Partition
    ups = [a for a in actions if a.get("type") == "UPDATE_PROFILE"]
    recs = [a for a in actions if a.get("type") == "RECOMMEND"]

    # --- enforce up to two recs, with duplicate if exactly one; allow zero ---
    if len(recs) >= 2:
        recs = recs[:2]
    elif len(recs) == 1:
        recs = [recs[0], dict(recs[0])]
    else:
        recs = []  # OK to return zero (no hardcoded fallback)

    # --- normalize and build external_items (leave external_items shape unchanged) ---
    norm_recs = []
    external_items = []

    for act in recs:
        brand = (act.get("brand") or "").strip()
        model = (act.get("model") or "").strip()
        category = (act.get("category") or "sportbike").strip()

        # Keep your existing numeric coercion helpers (present elsewhere in this file)
        speed = _to_int(act.get("max_speed_mph"))
        zero_to_sixty = _to_float(act.get("zero_to_sixty_s"))

        official_url = (act.get("official_url") or "").strip() or None
        image_query = (act.get("image_query") or f"{brand} {model}".strip()) or None

        # NEW: capture description (short, neutral, beginner-relevant)
        description = (act.get("description") or "").strip() or None

        norm = {
            "type": "RECOMMEND",
            "brand": brand or None,
            "model": model or None,
            "category": category or None,
            "max_speed_mph": speed,
            "zero_to_sixty_s": zero_to_sixty,
            "official_url": official_url,
            "image_query": image_query,
            "description": description,  # <— keep on the action for UI to render
        }
        norm_recs.append(norm)

        # Leave external_items exactly as your card/recommender expects
        external_items.append({
            "brand": norm["brand"],
            "model": norm["model"],
            "category": norm["category"],
            "top_speed_mph": speed,
            "max_speed_mph": speed,
            "zero_to_sixty_s": zero_to_sixty,
            "official_url": official_url,
            "image_query": image_query,
        })

    data["actions"] = ups + norm_recs
    data["external_items"] = external_items

    if logger:
        # Keep the log readable while showing that descriptions were captured
        brief = []
        for a in norm_recs:
            brief.append({
                "brand": a.get("brand"),
                "model": a.get("model"),
                "max_speed_mph": a.get("max_speed_mph"),
                "zero_to_sixty_s": a.get("zero_to_sixty_s"),
                "has_description": bool(a.get("description")),
            })
        logger.info("[NLU] Plan -> topic=%s | msg=%s | recs=%s", data.get("topic"), data.get("message"), brief)

    return data
