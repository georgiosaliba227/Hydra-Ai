"""Muse Wonder explanations of the user's own logged-drink trends.

Hydra's tested code computes every number (TrendFacts). Wonder chooses which
insights matter and writes short explanations; the server rejects any text
with a number that is not in the facts, medical or prescriptive language, or
an insight the facts do not support. No repair, retry or fallback text.
Policy: AGENTS.md (2026-10-29) and docs/architecture/WONDER_TRENDS_API.md.
"""
from datetime import date, datetime, timedelta
import json
import re
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from .meta_policy import OUTPUT_LIMIT
from .meta_provider import ProviderReply, strict_json
from .recognition import RecognitionUnavailable
from .wonder_hydration import MODEL, canonical, input_bound, payload_sha256, worst_case_micro_usd

VERSION = "wonder-trends-v1"
FACTS_VERSION = "wonder-trends-facts-v1"
WINDOW_DAYS = 14
MAX_CATEGORIES = 12
MAX_INSIGHTS = 3
SUMMARY_CHARS, INSIGHT_CHARS = 240, 300
INSIGHTS = {
    "week_over_week": "This week vs last week",
    "goal_progress": "Your goal",
    "logging_consistency": "Logging habit",
    "beverage_mix": "What you drink",
    "timing": "When you drink",
}
PROMPT = ("You explain trends in one person's own logged drinks. Hydra's tested code computed the facts below; "
          "treat them as exact. Choose 1 to 3 insight IDs from the schema that matter most for this person, most "
          "important first, and write one or two plain sentences for each, plus a one-sentence summary. Use only "
          "numbers that appear in the facts, written the same way (for example 1850 mL or 12%). Describe what the "
          "log shows. Do not diagnose, mention dehydration or medical conditions, recommend an amount to drink, or "
          "add disclaimers. Logged volume is not a measurement of hydration status. No tools.")
FACTS_MARKER = " Facts: "
LIMITATIONS = ["Wellness information, not medical advice.",
               "Muse Wonder wrote these explanations; Hydra checked every number against your log.",
               "Logged volume is not a measurement of hydration status."]
# Medical, diagnostic or prescriptive wording is outside what Hydra may say.
BLOCKED = re.compile(r"dehydrat|diagnos|disease|disorder|kidney|medic|doctor|prescri|supplement|recommend|"
                     r"should drink|need to drink|aim for|https?:|www\.", re.IGNORECASE)
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")

Ml = Annotated[int, Field(strict=True, ge=0, le=1_000_000)]
Day = Annotated[str, Field(strict=True, pattern=r"^\d{4}-\d{2}-\d{2}$")]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class DayTotal(Strict):
    date: Day
    total_ml: Ml
    drinks: StrictInt = Field(ge=0, le=1000)


class Week(Strict):
    total_ml: Ml
    average_ml: Ml
    logged_days: StrictInt = Field(ge=0, le=7)


class CategoryTotal(Strict):
    category: str = Field(min_length=1, max_length=80)
    total_ml: Ml
    share_pct: StrictInt = Field(ge=0, le=100)


class TimeOfDay(Strict):
    morning_ml: Ml
    afternoon_ml: Ml
    evening_ml: Ml
    night_ml: Ml


class TrendFacts(Strict):
    version: Literal["wonder-trends-facts-v1"]
    timezone: str = Field(min_length=1, max_length=128)
    through_date: Day
    window_days: Literal[14]
    days: list[DayTotal] = Field(min_length=WINDOW_DAYS, max_length=WINDOW_DAYS)
    last_7_days: Week
    previous_7_days: Week
    change_pct: StrictInt | None = Field(ge=-100_000, le=100_000)
    goal_ml: StrictInt | None = Field(ge=100, le=10_000)
    goal_met_days_last_7: StrictInt | None = Field(ge=0, le=7)
    categories: list[CategoryTotal] = Field(max_length=MAX_CATEGORIES)
    other_categories_ml: Ml
    time_of_day_ml: TimeOfDay
    applicable_insights: list[str] = Field(max_length=len(INSIGHTS))


def _week(days: list[dict]) -> dict:
    total = sum(day["total_ml"] for day in days)
    return {"total_ml": total, "average_ml": round(total / 7), "logged_days": sum(day["drinks"] > 0 for day in days)}


def _derived(days: list[dict], goal_ml: int | None, categories: list[dict]) -> dict:
    """Everything computable from the daily totals; recomputed on every validation."""
    last, previous = _week(days[7:]), _week(days[:7])
    change = round(100 * (last["total_ml"] - previous["total_ml"]) / previous["total_ml"]) if previous["total_ml"] else None
    applicable = [name for name, applies in (
        ("week_over_week", last["logged_days"] > 0 and previous["logged_days"] > 0),
        ("goal_progress", goal_ml is not None and last["logged_days"] > 0),
        ("logging_consistency", any(day["drinks"] for day in days)),
        ("beverage_mix", bool(categories)),
        ("timing", any(day["total_ml"] for day in days)),
    ) if applies]
    return {"last_7_days": last, "previous_7_days": previous, "change_pct": change,
            "goal_met_days_last_7": None if goal_ml is None else sum(day["total_ml"] >= goal_ml for day in days[7:]),
            "applicable_insights": applicable}


def build_facts(records: list[dict], goal_ml: int | None, timezone: str, through: date) -> dict:
    """The last 14 local days of logged drinks, aggregated; local dates follow the daily summary."""
    zone = ZoneInfo(timezone)
    start = through - timedelta(days=WINDOW_DAYS - 1)
    totals = {start + timedelta(days=offset): [0.0, 0] for offset in range(WINDOW_DAYS)}
    categories: dict[str, float] = {}
    periods = {"morning_ml": 0.0, "afternoon_ml": 0.0, "evening_ml": 0.0, "night_ml": 0.0}
    for record in records:
        local = datetime.fromisoformat(record["consumed_at"]).astimezone(zone)
        if local.date() not in totals:
            continue
        volume = float(record["consumed_ml"])
        totals[local.date()][0] += volume
        totals[local.date()][1] += 1
        categories[record["category"]] = categories.get(record["category"], 0.0) + volume
        hour = local.hour
        period = ("morning_ml" if 5 <= hour < 12 else "afternoon_ml" if 12 <= hour < 17
                  else "evening_ml" if 17 <= hour < 22 else "night_ml")
        periods[period] += volume
    days = [{"date": day.isoformat(), "total_ml": round(volume), "drinks": count}
            for day, (volume, count) in sorted(totals.items())]
    window_total = sum(categories.values())
    ranked = sorted(categories.items(), key=lambda item: (-item[1], item[0]))
    shown = [{"category": name, "total_ml": round(volume),
              "share_pct": round(100 * volume / window_total) if window_total else 0}
             for name, volume in ranked[:MAX_CATEGORIES]]
    facts = {"version": FACTS_VERSION, "timezone": timezone, "through_date": through.isoformat(),
             "window_days": WINDOW_DAYS, "days": days, "goal_ml": goal_ml, "categories": shown,
             "other_categories_ml": round(sum(volume for _, volume in ranked[MAX_CATEGORIES:])),
             "time_of_day_ml": {name: round(volume) for name, volume in periods.items()}}
    facts |= _derived(days, goal_ml, shown)
    return validate_facts(facts)


def validate_facts(facts: dict) -> dict:
    """Strict shape plus internal consistency; never trusts a stored or embedded derivation."""
    try:
        parsed = TrendFacts.model_validate(facts).model_dump()
        if parsed != facts:
            raise ValueError
        ZoneInfo(facts["timezone"])
        through = date.fromisoformat(facts["through_date"])
        expected = [(through - timedelta(days=WINDOW_DAYS - 1 - offset)).isoformat() for offset in range(WINDOW_DAYS)]
        if [day["date"] for day in facts["days"]] != expected:
            raise ValueError
        derived = _derived(facts["days"], facts["goal_ml"], facts["categories"])
        if any(facts[name] != value for name, value in derived.items()):
            raise ValueError
        # Rounded buckets of the same drinks: sums agree to within one mL per bucket.
        window = sum(day["total_ml"] for day in facts["days"])
        category_sum = sum(item["total_ml"] for item in facts["categories"]) + facts["other_categories_ml"]
        if (abs(category_sum - window) > len(facts["categories"]) + 1
                or abs(sum(facts["time_of_day_ml"].values()) - window) > 4):
            raise ValueError
    except (ValidationError, ValueError, KeyError, TypeError):
        raise ValueError("Trend facts failed validation") from None
    return facts


def trend_schema(applicable: list[str]) -> dict:
    return {"type": "object", "additionalProperties": False, "required": ["summary", "insights"],
            "properties": {
                "summary": {"type": "string", "maxLength": SUMMARY_CHARS},
                "insights": {"type": "array", "minItems": 1, "maxItems": min(MAX_INSIGHTS, len(applicable)),
                             "items": {"type": "object", "additionalProperties": False, "required": ["id", "text"],
                                       "properties": {"id": {"type": "string", "enum": list(applicable)},
                                                      "text": {"type": "string", "maxLength": INSIGHT_CHARS}}}}}}


def trends_payload(facts: dict) -> dict:
    validate_facts(facts)
    if not facts["applicable_insights"]:
        raise ValueError("No logged drinks in the window")
    return {"model": MODEL, "store": False, "stream": False, "background": False,
            "max_output_tokens": OUTPUT_LIMIT, "reasoning": {"effort": "minimal"},
            "text": {"format": {"type": "json_schema", "name": "hydration_trend_explanations", "strict": True,
                                "schema": trend_schema(facts["applicable_insights"])}},
            "input": [{"role": "user", "content": [{"type": "input_text",
                "text": PROMPT + FACTS_MARKER + canonical(facts)}]}]}


def facts_from_payload(payload: dict) -> dict:
    """The facts a trend payload carries; raises unless the payload is exactly what Hydra builds."""
    try:
        text = payload["input"][0]["content"][0]["text"]
        if not isinstance(text, str) or not text.startswith(PROMPT + FACTS_MARKER):
            raise ValueError
        facts = validate_facts(strict_json(text[len(PROMPT + FACTS_MARKER):]))
        if payload != trends_payload(facts):
            raise ValueError
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, RecursionError):
        raise ValueError("Not a Hydra trend payload") from None
    return facts


def preview(facts: dict) -> dict:
    """What would be sent and its worst-case cost; not a billing guarantee."""
    if not facts["applicable_insights"]:
        return {"version": VERSION, "facts": facts, "explainable": False, "payload_sha256": None,
                "input_bound_tokens": None, "worst_case_micro_usd": None}
    payload = trends_payload(facts)
    bound = input_bound(payload)
    return {"version": VERSION, "facts": facts, "explainable": True, "payload_sha256": payload_sha256(payload),
            "input_bound_tokens": bound, "worst_case_micro_usd": worst_case_micro_usd(bound)}


def _allowed_numbers(facts: dict) -> set[str]:
    allowed = {_number(token) for token in NUMBER.findall(canonical(facts))}
    for token in list(allowed):
        if token.isdigit():
            liters = int(token) / 1000
            allowed |= {f"{liters:g}", f"{round(liters, 1):g}"}
    return allowed


def _number(token: str) -> str:
    value = token.replace(",", "")
    return value[:-2] if value.endswith(".0") else value


def _checked_text(value, limit: int, allowed: set[str]) -> str:
    if (not isinstance(value, str) or value != value.strip() or not 1 <= len(value) <= limit
            or any(ord(char) < 32 for char in value) or BLOCKED.search(value)
            or any(_number(token) not in allowed for token in NUMBER.findall(value))):
        raise ValueError
    return value


def validate_explanation(value, facts: dict) -> dict:
    """Wonder's JSON to a checked explanation; any ungrounded number or claim rejects it whole."""
    if not isinstance(value, dict) or set(value) != {"summary", "insights"}:
        raise ValueError
    allowed = _allowed_numbers(facts)
    insights = value["insights"]
    if not isinstance(insights, list) or not 1 <= len(insights) <= min(MAX_INSIGHTS, len(facts["applicable_insights"])):
        raise ValueError
    checked = []
    for item in insights:
        if not isinstance(item, dict) or set(item) != {"id", "text"} or item["id"] not in facts["applicable_insights"]:
            raise ValueError
        checked.append({"id": item["id"], "text": _checked_text(item["text"], INSIGHT_CHARS, allowed)})
    if len({item["id"] for item in checked}) != len(checked):
        raise ValueError
    return {"summary": _checked_text(value["summary"], SUMMARY_CHARS, allowed), "insights": checked}


def parse_explanation(reply: ProviderReply, facts: dict) -> dict:
    """Untrusted Wonder output; no repair, retry or fallback."""
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
        return validate_explanation(strict_json(parts[0]["text"]), facts)
    except (ValueError, KeyError, TypeError, AttributeError):
        raise RecognitionUnavailable() from None


def trend_result(facts: dict, explanation: dict, *, account: str, attempt_id: str, observations: dict,
                 generated_at: str) -> dict:
    return {"version": VERSION, "facts": facts, "payload_sha256": payload_sha256(trends_payload(facts)),
            "summary": explanation["summary"],
            "insights": [{"id": item["id"], "title": INSIGHTS[item["id"]], "text": item["text"]}
                         for item in explanation["insights"]],
            "generated_at": generated_at,
            "provenance": {"mode": "meta_live", "provider": "Meta", "model": MODEL, "account_id": account,
                           "attempt_id": attempt_id, "text_origin": "muse_wonder_checked",
                           "numbers_checked_against": "facts"},
            "provider_observations": observations, "limitations": list(LIMITATIONS)}


if __name__ == "__main__":
    print(json.dumps(trend_schema(list(INSIGHTS)), indent=2))
