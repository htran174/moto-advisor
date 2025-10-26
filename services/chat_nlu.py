# chat_nlu.py
# Natural Language Understanding module for RideReady
# ---------------------------------------------------

import re
import json
import logging
from openai import OpenAI

client = OpenAI()
log = logging.getLogger(__name__)

# ---------------------------------------------------
# Utility: regex model extractor
# ---------------------------------------------------

def extract_models_from_text(text):
    """
    Extract known motorcycle model names from text.
    Simple heuristic for common brand + model patterns.
    """
    if not text:
        return []
    pattern = (
        r'\b(?:Honda|Yamaha|Kawasaki|Suzuki|BMW|KTM|Ducati|Triumph|Harley|Royal Enfield|Aprilia|CFMoto|Benelli|Bajaj|Moto Guzzi|Zero)\s+'
        r'(?:[A-Z0-9][A-Za-z0-9\- ]{1,25})'
    )
    found = re.findall(pattern, text)
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for f in found:
        f = f.strip()
        if f not in seen:
            seen.add(f)
            unique.append(f)
    return unique


# ---------------------------------------------------
# Core NLU function
# ---------------------------------------------------

def make_plan(user_msg: str, profile: dict):
    """
    Takes a user message and the current user profile,
    sends it to OpenAI, and returns a structured plan dict.

    The plan includes:
      - topic (what kind of intent)
      - actions (structured list for backend logic)
      - message (natural-language reply from model)
    """
    if not user_msg:
        return {"topic": "unknown", "actions": [], "message": "Empty input."}

    try:
        log.info(f"[NLU] Calling OpenAI model=gpt-4o-mini | msg={user_msg!r}")
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are RideReady's assistant. "
                        "Understand user motorcycle needs (style, budget, seat height, experience, region). "
                        "Output structured JSON in this format:\n"
                        "{"
                        "  \"topic\": \"motorcycle_recommendation\","
                        "  \"actions\": ["
                        "    {\"type\": \"RECOMMEND\", \"details\": {"
                        "        \"category\": \"sportbike\","
                        "        \"max_price\": 7000,"
                        "        \"experience_level\": \"beginner\","
                        "        \"seat_height_cm\": 79"
                        "    }}"
                        "  ],"
                        "  \"message\": \"Short explanation to show the user.\""
                        "}"
                    ),
                },
                {"role": "user", "content": user_msg},
            ],
            temperature=0.4,
        )

        content = completion.choices[0].message.content.strip()
        log.debug(f"[NLU] Raw model content: {content}")

        # Try to parse JSON directly
        plan = None
        try:
            plan = json.loads(content)
        except Exception:
            # fallback: wrap into dict
            plan = {"topic": "motorcycle_recommendation", "actions": [], "message": content}

        # Extract structured fields
        message = plan.get("message", content)
        actions = plan.get("actions", [])

        # ---------------------------------------------------
        # NEW: If the model only gave generic info,
        # extract real model names from the message text
        # ---------------------------------------------------
        models = extract_models_from_text(message)
        if models:
            # Replace generic plan with direct RECOMMENDs
            plan["actions"] = [
                {"type": "RECOMMEND", "model": m, "description": f"Suggested model: {m}"} for m in models
            ]
        elif not actions:
            # fallback default if model gave nothing structured
            plan["actions"] = [
                {
                    "type": "RECOMMEND",
                    "details": {
                        "category": "sportbike",
                        "max_price": 7000,
                        "experience_level": "beginner"
                    },
                }
            ]

        plan["topic"] = plan.get("topic", "motorcycle_recommendation")
        plan["message"] = message

        log.info(f"[NLU] Plan -> {plan}")
        return plan

    except Exception as e:
        log.exception("[NLU] Failed to get plan")
        # fallback minimal structure
        return {
            "topic": "motorcycle_recommendation",
            "actions": [
                {
                    "type": "RECOMMEND",
                    "details": {
                        "category": "sportbike",
                        "max_price": 7000,
                        "experience_level": "beginner"
                    },
                }
            ],
            "message": (
                "I'm sorry—something went wrong understanding your request. "
                "I'll show beginner sportbike options under $7k."
            ),
        }
