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

# ------------------------------------------------------------
# Public API
# ------------------------------------------------------------

def make_plan(user_msg: str, profile: dict, logger=None, client=None, model_name: str = "gpt-4o-mini") -> dict:
    """
    Produce a strict JSON plan with exactly TWO RECOMMEND actions when recommending bikes.
    Also returns `external_items` (max 2) normalized for the recommender.
    Incorporates user profile context (height, budget, bike_types) when provided.
    """

    system = (
        "You are an expert motorcycle recommendation assistant helping beginner riders.\n"
        "You always consider the user's provided profile data if available: height (cm), budget (USD), and preferred bike types.\n"
        "If height is provided, avoid recommending bikes too tall for shorter riders (<170 cm).\n"
        "If budget is provided, recommend bikes within or near that range (do not exceed it by much).\n"
        "If bike types are provided, prioritize those categories first. Unless user ask for a different categorie.\n"
        "If a field is blank or missing, simply ignore it (do not make assumptions).\n"
        "User will be no experience or little experience, if User is no experience do not recommend bike bigger than midsize bike (i.e at most would be a cbr500)\n"
        "If User has little experience you can recommend bikes around 500cc range or more when user request to see bigger bikes you can show them bikes under 1000cc, but no supper bikes i.e no 1000cc bike or stronger.\n\n"
        "You must respond ONLY with a strict JSON object having keys: topic, message, actions.\n"
        "When recommending, always include exactly TWO RECOMMEND actions with fields:\n"
        "The message should always be general and not specfic about any bike leave the specfic for the description.\n"
        "{"
        "\"type\":\"RECOMMEND\","
        "\"brand\":\"... i.e honda ...\","
        "\"model\":\"... i.e cbr300r ...\","
        "\"category\":\"sportbike\","
        "\"max_speed_mph\":<int>,"
        "\"zero_to_sixty_s\":<float>,"
        "\"official_url\":\"...\","
        "\"image_query\":\"<brand and model>\","
        "\"description\":\"<short one-sentence summary of why it fits the user profile>\""
        "}\n"
        "Use numbers (not strings) for speeds/acceleration. Keep your message concise and informative.\n"
        "If user messesge isn't about motorcycle respond with 'Please only ask about motorcycle'.\n"
        "Unless user ask otherwise try to recommend common models that most US buyer can buy 2nd hand.\n"
    )

    user = {
        "role": "user",
        "content": (
            f"User message: {user_msg}\n\n"
            f"User profile (may be partially empty): {json.dumps(profile, ensure_ascii=False, indent=2)}"
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

    # --- JSON parsing helper ---
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

    ups = [a for a in actions if a.get("type") == "UPDATE_PROFILE"]
    recs = [a for a in actions if a.get("type") == "RECOMMEND"]

    # --- Enforce exactly two RECOMMEND actions ---
    if len(recs) >= 2:
        recs = recs[:2]
    elif len(recs) == 1:
        recs = [recs[0], dict(recs[0])]  # duplicate single rec
    else:
        recs = []  # allow empty (chat will still respond textually)

    # --- Normalize and build external items ---
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
        desc = (act.get("description") or "").strip()

        norm = {
            "type": "RECOMMEND",
            "brand": brand or None,
            "model": model,
            "category": category or None,
            "max_speed_mph": speed,
            "zero_to_sixty_s": zero_to_sixty,
            "official_url": official_url,
            "image_query": image_query,
            "description": desc,
        }
        norm_recs.append(norm)
        external_items.append({
            "brand": norm["brand"],
            "model": norm["model"],
            "category": norm["category"],
            "max_speed_mph": speed,
            "top_speed_mph": speed,
            "zero_to_sixty_s": zero_to_sixty,
            "official_url": official_url,
            "image_query": image_query,
            "description": desc,
        })

    data["actions"] = ups + norm_recs
    data["external_items"] = external_items

    if logger:
        logger.info("[NLU] Plan -> %s", json.dumps(data, ensure_ascii=False, indent=2))

    return data
