"""
services/nlu.py
Handles RideReady natural-language chat interpretation using OpenAI (gpt-4o-mini)
with graceful fallback rules for offline or quota-exceeded modes.
"""

import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------
RR_OPENAI_ENABLED = os.getenv("RR_OPENAI_ENABLED", "false").lower() == "true"
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("RR_OPENAI_MODEL", "gpt-4o-mini")

client = None
if RR_OPENAI_ENABLED and OPENAI_KEY:
    try:
        client = OpenAI(api_key=OPENAI_KEY)
    except Exception as e:
        print("[NLU] Could not initialize OpenAI client:", e)
        client = None


# ---------------------------------------------------------------------
# Local fallback logic
# ---------------------------------------------------------------------
def _fallback_rules(message: str) -> dict:
    """Keyword-based interpretation for offline use."""
    msg = message.lower()
    actions = []

    if "cruiser" in msg:
        actions.append({"type": "UPDATE_PROFILE", "patch": {"bike_types": ["cruiser"]}})
    if "sport" in msg:
        actions.append({"type": "UPDATE_PROFILE", "patch": {"bike_types": ["sportbike"]}})
    if "adv" in msg or "dual" in msg:
        actions.append({"type": "UPDATE_PROFILE", "patch": {"bike_types": ["adv", "dual-sport"]}})
    if "cheap" in msg or "budget" in msg or "under" in msg:
        actions.append({"type": "UPDATE_PROFILE", "patch": {"budget_usd": 6000}})
    if "fast" in msg or "speed" in msg or "power" in msg:
        actions.append({"type": "UPDATE_PROFILE", "patch": {"engine_cc_min": 400}})
    if "tall" in msg or "height" in msg:
        actions.append({"type": "UPDATE_PROFILE", "patch": {"height_cm": 180}})
    if "short" in msg or "low" in msg:
        actions.append({"type": "UPDATE_PROFILE", "patch": {"height_cm": 165}})

    if actions:
        actions.append({"type": "RECOMMEND"})
        return {
            "topic": "MOTO_DOMAIN",
            "actions": actions,
            "message": "Updating your preferences and refreshing recommendations.",
        }

    return {
        "topic": "AMBIGUOUS",
        "actions": [],
        "message": "What would you like to change—style, budget, or size?",
    }


# ---------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------
def make_plan(message: str, profile: dict) -> dict:
    """Return a structured plan dict describing what to update or recommend."""
    if not message.strip():
        return {"topic": "EMPTY", "actions": [], "message": "Please type something."}

    if not RR_OPENAI_ENABLED or not client:
        print("[NLU] OpenAI disabled → fallback rules")
        return _fallback_rules(message)

    try:
        print(f"[NLU] Calling OpenAI model={OPENAI_MODEL} | msg='{message}'")

        system_prompt = (
            "You are RideReady Assistant, a helpful motorcycle recommender bot. "
            "Interpret user messages into structured actions. "
            "Stay strictly within motorcycle context. "
            "Return valid JSON with fields: topic, actions, message. "
            "Each action may be UPDATE_PROFILE (with patch fields) or RECOMMEND."
        )

        response = client.responses.create(
            model=OPENAI_MODEL,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            max_output_tokens=300,
        )

        raw = response.output_text.strip()
        import json

        try:
            plan = json.loads(raw)
            print(f"[NLU] Plan -> {plan}")
            return plan
        except Exception:
            print("[NLU] Could not parse JSON → fallback")
            return _fallback_rules(message)

    except Exception as e:
        err = str(e)
        print(f"[NLU] OpenAI error -> fallback: {err}")

        if "insufficient_quota" in err or "429" in err:
            return {
                "topic": "MOTO_DOMAIN",
                "actions": [],
                "message": "OpenAI credits are out — switching to keyword mode.",
            }

        if "invalid_api_key" in err or "AuthenticationError" in err:
            return {
                "topic": "AMBIGUOUS",
                "actions": [],
                "message": "Chat unavailable (API key issue). Please check configuration.",
            }

        return _fallback_rules(message)
