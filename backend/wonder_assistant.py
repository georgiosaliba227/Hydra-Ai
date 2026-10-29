"""Muse Wonder topic selection for the fixed suggested assistant questions.

Wonder only chooses which reviewed answers apply, from a per-question allowed
set; answer text and safety escalation stay local. Free-text questions never
use this path because their exact payload cannot be approved in advance.
"""
import json

from ai.assistant import SUGGESTED, VERSION, answers_for
from .meta_experiments import ACCOUNT
from .meta_policy import OUTPUT_LIMIT
from .meta_provider import ProviderReply, strict_json
from .recognition import RecognitionUnavailable
from .wonder_hydration import MODEL

# Topics Wonder may select per suggested question. urgent and medical_scope are
# never selectable: fixed questions describe no symptoms or conditions.
ALLOWED = {
    "coffee_counts": ("coffee_caffeine", "beverage_types", "logged_intake"),
    "creatine_water": ("creatine", "daily_needs"),
    "workout_sweat": ("exercise_sweat", "weather", "daily_needs"),
    "milk_vs_water": ("beverage_types", "exercise_sweat"),
    "daily_amount": ("daily_needs", "logged_intake", "exercise_sweat", "weather"),
    "logged_meaning": ("logged_intake", "daily_needs"),
    "heart_rate": ("heart_rate", "exercise_sweat"),
    "hot_weather": ("weather", "exercise_sweat", "daily_needs"),
}
PROMPT = ("Choose which reviewed hydration answers apply to the question. Return only topic IDs from the schema, "
          "most relevant first, including every directly relevant topic and no unrelated ones. Do not write advice, "
          "numbers or diagnoses. No tools.")


def topic_schema(question_id: str) -> dict:
    return {"type": "object", "additionalProperties": False, "required": ["topics"],
            "properties": {"topics": {"type": "array", "minItems": 1, "maxItems": len(ALLOWED[question_id]),
                                      "items": {"type": "string", "enum": list(ALLOWED[question_id])}}}}


def assistant_payload(question_id: str) -> dict:
    if question_id not in SUGGESTED:
        raise ValueError("Only suggested questions can use Wonder")
    return {"model": MODEL, "store": False, "stream": False, "background": False,
            "max_output_tokens": OUTPUT_LIMIT, "reasoning": {"effort": "minimal"},
            "text": {"format": {"type": "json_schema", "name": "hydration_answer_topics", "strict": True,
                                "schema": topic_schema(question_id)}},
            "input": [{"role": "user", "content": [{"type": "input_text",
                "text": PROMPT + " Question: " + SUGGESTED[question_id][0]}]}]}


def parse_topics(reply: ProviderReply, question_id: str) -> tuple[str, ...]:
    """Untrusted Wonder output to allowed topics that include a reviewed match; no repair or fallback."""
    try:
        body = reply.body
        if (reply.status != 200 or body.get("model") != MODEL or body.get("status") != "completed"
                or body.get("error") is not None or body.get("incomplete_details") is not None):
            raise ValueError
        messages = [item for item in body["output"] if item.get("type") != "reasoning"]
        if len(messages) != 1 or messages[0]["type"] != "message" or messages[0]["role"] != "assistant" or messages[0]["status"] != "completed":
            raise ValueError
        parts = messages[0]["content"]
        if len(parts) != 1 or parts[0]["type"] != "output_text" or not isinstance(parts[0]["text"], str) or len(parts[0]["text"]) > 4096:
            raise ValueError
        value = strict_json(parts[0]["text"])
        topics = value["topics"] if isinstance(value, dict) and set(value) == {"topics"} else None
        if (not isinstance(topics, list) or not topics or len(topics) != len(set(topics))
                or not all(isinstance(t, str) for t in topics) or not set(topics) <= set(ALLOWED[question_id])
                or not set(topics) & set(SUGGESTED[question_id][1])):
            raise ValueError
        return tuple(topics)
    except (ValueError, KeyError, TypeError, AttributeError):
        raise RecognitionUnavailable() from None


def live_answer(question_id: str, topics: tuple[str, ...], *, attempt_id: str, observations: dict) -> dict:
    return {"version": VERSION, "question_id": question_id, "topics": [a["topic"] for a in answers_for(topics)],
            "escalation": False, "answers": answers_for(topics), "intake_context": None,
            "provenance": {"mode": "meta_live", "provider": "Meta", "model": MODEL, "answer_origin": "reviewed_text",
                           "topic_selection": MODEL, "account_id": ACCOUNT, "attempt_id": attempt_id},
            "provider_observations": observations,
            "limitations": ["Wellness information, not medical advice.",
                            "Muse Wonder chose which reviewed answers apply; it did not write them.",
                            "Logged volume is not a measurement of hydration status."]}


if __name__ == "__main__":
    print(json.dumps({question_id: assistant_payload(question_id) for question_id in SUGGESTED}, indent=2))
