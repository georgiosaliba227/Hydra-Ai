"""Muse Wonder explanations of the user's own logged-drink trends.

Hydra's tested code computes every number (TrendFacts). Wonder chooses which
insights matter and writes the wording, but it cannot write a number: it uses
placeholders such as {weekly_change}, which Hydra fills in from the facts. Any
digit, number word, comparison word, medical or prescriptive wording, unknown
placeholder or unsupported insight rejects the whole reply. No repair, retry
or fallback text.
Policy: AGENTS.md (2026-10-29) and docs/architecture/WONDER_TRENDS_API.md.
"""
from datetime import date, datetime, timedelta
import json
import re
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from .meta_provider import ProviderReply, strict_json
from .recognition import RecognitionUnavailable
from .wonder_hydration import MODEL, canonical, input_bound, payload_sha256, worst_case_micro_usd

VERSION = "wonder-trends-v1"
FACTS_VERSION = "wonder-trends-facts-v1"
WINDOW_DAYS = 14
MAX_CATEGORIES = 12
# The live 2026-10-29 trend reply hit 512 output tokens (reasoning included) and was cut off.
# Worst case at 2048 stays far below the $0.25 per-request cap.
TREND_OUTPUT_LIMIT = 2048
MAX_INSIGHTS = 3
SUMMARY_CHARS, INSIGHT_CHARS = 240, 300
INSIGHTS = {
    "week_over_week": "This week vs last week",
    "goal_progress": "Your goal",
    "logging_consistency": "Logging habit",
    "beverage_mix": "What you drink",
    "timing": "When you drink",
}
PLACEHOLDERS = {
    "week_total": "total logged in the last 7 days, e.g. 13600 mL",
    "week_average": "daily average for the last 7 days, e.g. 1943 mL a day",
    "previous_week_total": "total logged in the 7 days before that",
    "weekly_change": "the change from the week before, e.g. 21% more than the week before",
    "week_logged_days": "days with a log in the last 7, e.g. 6 of the last 7 days",
    "days_without_logs": "days without a log in the 14-day window",
    "goal": "the person's own daily goal, e.g. 2000 mL",
    "goal_met_days": "days the goal was reached in the last 7",
    "top_drink": "the drink type logged most, with its share",
    "peak_time": "the time of day with the most volume, with its share",
}
PROMPT = ("You describe trends in one person's own logged drinks. Hydra's tested code computed the facts below. "
          "Choose 1 to 3 insight IDs from the schema that matter most for this person, most important first, and "
          "write one or two plain sentences for each, plus a one-sentence summary. Never write a number, a number "
          "word, a unit or a comparison word (more, less, higher, lower, most, every, never) yourself: write a "
          "placeholder in braces instead and Hydra fills in the exact value. Placeholders: "
          + "; ".join(f"{{{name}}} = {meaning}" for name, meaning in PLACEHOLDERS.items())
          + ". Use goal placeholders only when goal_ml is set. Describe only what the log shows. Do not give advice, "
          "judge the amounts, mention hydration, health or any medical condition, or add disclaimers. No tools.")
FACTS_MARKER = " Facts: "
LIMITATIONS = ["Wellness information, not medical advice.",
               "Muse Wonder wrote the wording; every number was filled in by Hydra from your log.",
               "Logged volume is not a measurement of hydration status."]
# Wonder may not state amounts, directions or quantities itself; placeholders carry them.
NUMERIC = re.compile(r"\d|\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
                     r"fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|"
                     r"ninety|hundred|thousand|million|dozen|half|halves|double[ds]?|twice|triple[ds]?|quarter|"
                     r"percent\w*|liters?|litres?|ml|millilit\w*|ounces?|oz|cups?|glass(?:es)?|bottles?)\b",
                     re.IGNORECASE)
COMPARATIVE = re.compile(r"\b(?:more|less|fewer|higher|lower|bigger|smaller|increas\w*|decreas\w*|rose|rises?|rising|"
                         r"fell|falls?|falling|drop\w*|declin\w*|grew|grow\w*|up|down|most|least|majority|minority|"
                         r"largest|smallest|biggest|greatest|highest|lowest|top|bottom|"
                         r"all|every|each|none|never|always|only|usually|mostly)\b", re.IGNORECASE)
# Diagnostic, medical, judging or prescriptive wording is outside what Hydra may say.
BLOCKED = re.compile(r"\b(?:\w*hydrat\w*|diagnos\w*|diseas\w*|disorder\w*|condition\w*|symptom\w*|syndrome\w*|"
                     r"diabet\w*|hyponat\w*|kidney\w*|heart\w*|blood|pressure|headache\w*|fatigue\w*|tired\w*|"
                     r"dizz\w*|cramp\w*|faint\w*|ill|illness\w*|sick\w*|pain\w*|risk\w*|danger\w*|harm\w*|"
                     r"unsafe|safe\w*|health\w*|medic\w*|doctor\w*|physician\w*|clinic\w*|prescri\w*|"
                     r"supplement\w*|recommend\w*|advi[cs]e\w*|should|must|need\w*|ought|try\w*|consider\w*|"
                     r"aim\w*|target\w*|enough|sufficien\w*|insufficien\w*|adequate\w*|optimal\w*|ideal\w*|"
                     r"deficien\w*|excess\w*|caus\w*|lead\w*|result\w*|because|improv\w*|better|worse|bad|"
                     r"poor\w*|good|great|concern\w*|worr\w*|warn\w*|caution\w*|careful\w*)\b|https?:|www\.|@",
                     re.IGNORECASE)
PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")

Ml = Annotated[int, Field(strict=True, ge=0, le=1_000_000_000)]
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
    change_pct: StrictInt | None = Field(ge=-100, le=10**12)
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
            "max_output_tokens": TREND_OUTPUT_LIMIT, "reasoning": {"effort": "minimal"},
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
            "input_bound_tokens": bound, "worst_case_micro_usd": worst_case_micro_usd(bound, TREND_OUTPUT_LIMIT)}


def placeholder_values(facts: dict) -> dict[str, str]:
    """Every value Wonder may refer to, formatted by Hydra; absent facts have no placeholder."""
    last, previous = facts["last_7_days"], facts["previous_7_days"]
    window = sum(day["total_ml"] for day in facts["days"])
    values = {"week_total": f"{last['total_ml']} mL", "week_average": f"{last['average_ml']} mL a day",
              "week_logged_days": f"{last['logged_days']} of the last 7 days",
              "days_without_logs": f"{sum(day['drinks'] == 0 for day in facts['days'])} of the last 14 days"}
    if previous["logged_days"]:
        values["previous_week_total"] = f"{previous['total_ml']} mL"
    change = facts["change_pct"]
    if change is not None:
        values["weekly_change"] = (f"{change}% more than the week before" if change > 0 else
                                   f"{-change}% less than the week before" if change < 0 else
                                   "the same amount as the week before")
    if facts["goal_ml"] is not None:
        values["goal"] = f"{facts['goal_ml']} mL"
        values["goal_met_days"] = f"{facts['goal_met_days_last_7']} of the last 7 days"
    if facts["categories"]:
        top = facts["categories"][0]
        values["top_drink"] = f"{top['category']} ({top['share_pct']}% of what you logged)"
    if window:
        name, volume = max(facts["time_of_day_ml"].items(), key=lambda item: item[1])
        values["peak_time"] = f"the {name.removesuffix('_ml')} ({round(100 * volume / window)}% of what you logged)"
    return values


def _render(template, limit: int, values: dict[str, str]) -> str:
    """One checked template to display text; raises on anything Wonder may not say itself."""
    if (not isinstance(template, str) or template != template.strip() or not 1 <= len(template) <= limit
            or any(ord(char) < 32 for char in template)):
        raise ValueError
    names = PLACEHOLDER.findall(template)
    prose = PLACEHOLDER.sub(" ", template)
    if (any(name not in values for name in names) or "{" in prose or "}" in prose
            or NUMERIC.search(prose) or COMPARATIVE.search(prose) or BLOCKED.search(prose)):
        raise ValueError
    return PLACEHOLDER.sub(lambda match: values[match.group(1)], template)


def validate_explanation(value, facts: dict) -> dict:
    """Wonder's JSON to checked templates and rendered text; any violation rejects it whole."""
    if not isinstance(value, dict) or set(value) != {"summary", "insights"}:
        raise ValueError
    values = placeholder_values(facts)
    insights = value["insights"]
    if not isinstance(insights, list) or not 1 <= len(insights) <= min(MAX_INSIGHTS, len(facts["applicable_insights"])):
        raise ValueError
    checked = []
    for item in insights:
        if not isinstance(item, dict) or set(item) != {"id", "text"} or item["id"] not in facts["applicable_insights"]:
            raise ValueError
        checked.append({"id": item["id"], "template": item["text"],
                        "text": _render(item["text"], INSIGHT_CHARS, values)})
    if len({item["id"] for item in checked}) != len(checked):
        raise ValueError
    return {"summary_template": value["summary"], "summary": _render(value["summary"], SUMMARY_CHARS, values),
            "insights": checked}


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
            "summary": explanation["summary"], "summary_template": explanation["summary_template"],
            "insights": [{"id": item["id"], "title": INSIGHTS[item["id"]], "template": item["template"],
                          "text": item["text"]} for item in explanation["insights"]],
            "generated_at": generated_at,
            "provenance": {"mode": "meta_live", "provider": "Meta", "model": MODEL, "account_id": account,
                           "attempt_id": attempt_id, "text_origin": "muse_wonder_checked",
                           "numbers_checked_against": "facts"},
            "provider_observations": observations, "limitations": list(LIMITATIONS)}


if __name__ == "__main__":
    print(json.dumps(trend_schema(list(INSIGHTS)), indent=2))
