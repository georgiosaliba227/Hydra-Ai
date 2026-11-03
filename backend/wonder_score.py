"""Exact Home aggregate disclosure and fact-grounded, number-free Muse wording.

Muse ranks supported findings and selects reviewed prose. The parser rejects
unbounded prose, invented claims and all altered payload fields. No transport or
financial admission occurs here.
"""
from .hydration_score import validate_facts
from .meta_accounts import CAP
from .meta_provider import ProviderReply, strict_json
from .recognition import RecognitionUnavailable
from .wonder_hydration import MODEL, canonical, input_bound, payload_sha256, worst_case_micro_usd

VERSION = "wonder-score-preview-v1"
LIVE_VERSION = "wonder-score-live-v1"
OUTPUT_LIMIT = 1024
REQUIRED_IDS = ("today_alignment", "recent_consistency", "measurement_support")
TITLES = {"today_alignment": "Today's goal alignment", "recent_consistency": "Recorded consistency",
          "measurement_support": "Measurement support", "goal_cap": "Capped goal rewards",
          "unlogged_unknown": "Unlogged intake is unknown", "research_meaning": "Experimental meaning"}
LIMITATIONS = ["Experimental product rubric; not hydration status or a drinking requirement.",
               "Extra logged volume above the current chosen goal earns no extra points.",
               "An unlogged day does not establish no actual consumption.",
               "Measurement support does not establish physiological accuracy or narrower uncertainty."]
PROMPT = ("Explain Hydra's experimental product rubric, not physiological status. Rank supported finding IDs, "
          "including every required component ID, and select exactly a supplied reviewed text for its ID. "
          "Do not modify the text, add numbers, advice, diagnosis, interpretations or other claims. "
          "All figures are computed by Hydra and displayed separately. No tools. ")
FACTS_MARKER = " Facts: "


def allowed_texts(facts: dict) -> dict[str, tuple[str, ...]]:
    """Reviewed, conditional statements whose support follows from exact facts."""
    validate_facts(facts)
    texts = {
        "today_alignment": (("Today's logged beverage volume is compared with the current chosen goal.",
                             "The current chosen goal is the reference for today's logged volume.")
                            if facts["today_ml"] > 0 else
                            ("Today's record has no logged beverage volume in this snapshot.",
                             "No beverage volume is logged for today in this snapshot.")),
        "recent_consistency": (("Recorded prior-day volumes are compared with the current chosen goal.",
                                "The current chosen goal is the retrospective reference for recorded consistency.")
                               if any(day["logged"] for day in facts["previous_days"]) else
                               ("The preceding local dates have no logged beverage volume in this snapshot.",
                                "This snapshot contains no logged beverage volume for the preceding local dates.")),
        "measurement_support": (("Validated manual sessions contribute measurement support to this snapshot.",
                                 "The measurement component reflects documented valid manual sessions.")
                                if facts["measurement_count"] > 0 else
                                ("No validated manual sessions contribute measurement support to this snapshot.",
                                 "This snapshot has no valid manual sessions for the measurement component.")),
        "goal_cap": ("Logged volume beyond the current chosen goal earns no extra score points.",
                     "The goal-based contributions stop growing at the current chosen goal."),
        "research_meaning": ("This score is an unvalidated product rubric, not a physiological measurement.",
                             "The score describes recorded goal alignment, consistency and measurement support."),
    }
    if any(not day["logged"] for day in facts["previous_days"]):
        texts["unlogged_unknown"] = ("Unlogged prior dates earn no recorded-consistency points; actual consumption is unknown.",
                                    "Absence of a beverage log does not establish absence of consumption.")
    return texts


def score_schema(facts: dict) -> dict:
    choices = allowed_texts(facts)
    return {"type": "object", "additionalProperties": False, "required": ["insights"], "properties": {
        "insights": {"type": "array", "minItems": 3, "maxItems": len(choices), "items": {
            "type": "object", "additionalProperties": False, "required": ["id", "text"], "properties": {
                "id": {"type": "string", "enum": list(choices)},
                "text": {"type": "string", "enum": [text for values in choices.values() for text in values]}}}}}}


def score_payload(facts: dict) -> dict:
    validate_facts(facts)
    instructions = PROMPT + "Required IDs: " + ", ".join(REQUIRED_IDS) + ". Reviewed choices: " + canonical(allowed_texts(facts))
    return {"model": MODEL, "store": False, "stream": False, "background": False,
            "max_output_tokens": OUTPUT_LIMIT, "reasoning": {"effort": "minimal"},
            "text": {"format": {"type": "json_schema", "name": "hydration_home_score_explanations", "strict": True,
                                "schema": score_schema(facts)}},
            "input": [{"role": "user", "content": [{"type": "input_text",
                "text": instructions + FACTS_MARKER + canonical(facts)}]}]}


def facts_from_payload(payload: dict) -> dict:
    """Canonical comparison distinguishes false from zero and true from one."""
    try:
        text = payload["input"][0]["content"][0]["text"]
        facts = validate_facts(strict_json(text.rsplit(FACTS_MARKER, 1)[1]))
        if canonical(payload) != canonical(score_payload(facts)):
            raise ValueError
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError):
        raise ValueError("Not a Hydra Home score payload") from None
    return facts


def preview(facts: dict) -> dict:
    payload = score_payload(facts)
    bound = input_bound(payload)
    exposure = worst_case_micro_usd(bound, OUTPUT_LIMIT)
    if exposure > CAP:
        raise ValueError("Score payload exceeds per-request cap")
    return {"version": VERSION, "facts": facts, "payload_sha256": payload_sha256(payload), "model": MODEL,
            "input_bound_tokens": bound, "max_output_tokens": OUTPUT_LIMIT, "worst_case_micro_usd": exposure,
            "per_request_cap_micro_usd": CAP, "live_available": False, "account_id": None, "saved": None,
            "cost_estimate_policy": "existing_reference_prices_not_a_verified_live_quote"}


def validate_explanation(value: dict, facts: dict) -> dict:
    choices = allowed_texts(facts)
    if type(value) is not dict or set(value) != {"insights"} or type(value["insights"]) is not list:
        raise ValueError("Invalid score explanation")
    insights = value["insights"]
    if not 3 <= len(insights) <= len(choices):
        raise ValueError("Invalid score explanation length")
    ids = []
    for item in insights:
        if (type(item) is not dict or set(item) != {"id", "text"} or type(item["id"]) is not str
                or item["id"] not in choices or type(item["text"]) is not str
                or item["text"] not in choices[item["id"]]):
            raise ValueError("Unsupported score finding")
        ids.append(item["id"])
    if len(set(ids)) != len(ids) or not set(REQUIRED_IDS) <= set(ids):
        raise ValueError("Score components missing or duplicated")
    return {"insights": [{"id": item["id"], "text": item["text"]} for item in insights]}


def parse_explanation(reply: ProviderReply, facts: dict) -> dict:
    try:
        body = reply.body
        if (reply.status != 200 or body.get("model") != MODEL or body.get("status") != "completed"
                or body.get("error") is not None or body.get("incomplete_details") is not None):
            raise ValueError
        messages = [item for item in body["output"] if item.get("type") != "reasoning"]
        if (len(messages) != 1 or messages[0]["type"] != "message" or messages[0]["role"] != "assistant"
                or messages[0]["status"] != "completed"):
            raise ValueError
        parts = messages[0]["content"]
        if len(parts) != 1 or parts[0]["type"] != "output_text" or type(parts[0]["text"]) is not str or len(parts[0]["text"]) > 4096:
            raise ValueError
        return validate_explanation(strict_json(parts[0]["text"]), facts)
    except (ValueError, KeyError, TypeError, AttributeError):
        raise RecognitionUnavailable() from None


def score_result(facts: dict, explanation: dict, *, account: str, attempt_id: str, observations: dict,
                 generated_at: str) -> dict:
    explanation = validate_explanation(explanation, facts)
    return {"version": LIVE_VERSION, "facts": facts, "payload_sha256": payload_sha256(score_payload(facts)),
            "insights": [{"id": item["id"], "title": TITLES[item["id"]], "text": item["text"]}
                         for item in explanation["insights"]], "generated_at": generated_at,
            "provenance": {"mode": "meta_live", "provider": "Meta", "model": MODEL, "account_id": account,
                "attempt_id": attempt_id, "selection_origin": MODEL,
                "text_origin": "hydra_reviewed_selected_by_muse", "numbers_checked_against": "facts"},
            "provider_observations": observations, "limitations": list(LIMITATIONS)}
