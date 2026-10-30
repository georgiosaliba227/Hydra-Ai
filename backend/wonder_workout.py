"""Muse Wonder explanations of a planned workout against the user's own previous sessions.

Built exactly like the trend explanations (backend/wonder_trends.py). Hydra's
tested code computes every number (WorkoutFacts): the planned workout, the
user's typical duration and weather (medians of the supplied history), counts
of previous, matching and weighed sessions, and the existing v2 workout
forecast engine's estimate range. Wonder only chooses which insights apply and
writes template sentences with placeholders such as {duration_comparison};
Hydra fills them in. Any digit, number word, unit, comparison or direction
word, drinking, medical, diagnostic or prescriptive wording, unknown
placeholder or unsupported insight rejects the whole reply. No repair, retry
or fallback text. Required caveats are Hydra's fixed LIMITATIONS.
Policy: AGENTS.md (2026-10-29) and docs/architecture/WONDER_WORKOUT_API.md.
"""
from datetime import datetime
import json
import math
import re
from statistics import median
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, ValidationError

from ai.forecasting.longitudinal import predict_longitudinal
from ai.hydration.personal_forecast import Exercise, SweatSample
from ai.hydration.workout import estimate_workout_loss
from .meta_provider import ProviderReply, strict_json
from .recognition import RecognitionUnavailable
from .wonder_hydration import MODEL, canonical, input_bound, payload_sha256, worst_case_micro_usd
from .wonder_trends import BLOCKED, COMPARATIVE, NUMERIC, PLACEHOLDER, TREND_OUTPUT_LIMIT

VERSION = "wonder-workout-v1"
FACTS_VERSION = "wonder-workout-facts-v1"
FORMAT_NAME = "planned_workout_explanation"
# Same budget as trend explanations: room for reasoning, far below the $0.25 per-request cap.
WORKOUT_OUTPUT_LIMIT = TREND_OUTPUT_LIMIT
MAX_INSIGHTS = 3
MAX_HISTORY = 32  # The workout-forecast request bound (WORKOUT_MODEL_API.md).
SUMMARY_CHARS, INSIGHT_CHARS = 240, 300
# Display thresholds for "longer/shorter", "hotter/cooler", "more/less humid". They only
# decide which words Hydra uses; they are not physiological thresholds and change no number.
DURATION_SIMILAR_PCT = 10
TEMPERATURE_SIMILAR_C = 3
HUMIDITY_SIMILAR_POINTS = 10

INSIGHTS = {
    "duration_vs_typical": "Duration vs your usual",
    "weather_vs_typical": "Weather vs your usual",
    "comparable_history": "Your previous sessions",
    "estimate": "The estimate",
    "estimate_vs_previous": "Estimate vs your measurements",
    "missing_information": "What is missing",
    "refine_estimate": "What would refine it",
}
PLACEHOLDERS = {
    "planned_workout": "the planned workout, e.g. 75 minutes of high-intensity running in the evening at 31 °C "
                       "and 60% humidity",
    "duration_comparison": "how its duration compares with the person's typical session, e.g. longer than your "
                           "typical run (75 vs 45 minutes)",
    "temperature_comparison": "how its temperature compares, e.g. hotter than your typical run (31 °C vs 22 °C)",
    "humidity_comparison": "how its humidity compares, e.g. close to the humidity of your typical run (55% humidity)",
    "previous_sessions": "the person's previous sessions of this activity, e.g. 8 previous runs",
    "matching_sessions": "previous sessions at the same intensity, temperature and humidity, e.g. 0 of your 8 "
                         "previous runs",
    "weigh_ins": "previous sessions with a complete before-and-after weigh-in, e.g. 3 of your 8 previous runs",
    "measured_loss": "the median fluid loss measured in those weigh-ins, e.g. 650 mL",
    "estimate": "Hydra's fluid-loss estimate for this workout, e.g. about 900 to 1200 mL",
    "estimate_basis": "what the estimate is based on, e.g. 2 previous runs weighed at the same intensity, "
                      "temperature and humidity",
    "estimate_comparison": "how the estimate compares with the weigh-ins, e.g. above what you measured on your "
                           "weighed runs (median 650 mL)",
    "missing_information": "what Hydra lacks for an estimate, e.g. previous weigh-ins at the same intensity, "
                           "temperature and humidity",
    "suggested_measurement": "the measurement that would refine the estimate, e.g. your weight before and after "
                             "this workout",
}
PROMPT = ("You explain how one person's planned workout compares with their own previous sessions and measurements. "
          "Hydra's tested code computed the facts below, including the only fluid-loss estimate. Choose 1 to 3 insight "
          "IDs from the schema that matter most for this person, most important first, each at most once, and write "
          "one or two plain sentences for each, plus a one-sentence summary. Never write a number, a number word, a "
          "unit, or a comparison or direction word (more, less, higher, lower, longer, shorter, hotter, cooler, than, "
          "same, similar, above, below, every, only) yourself: write a placeholder in braces instead and Hydra fills "
          "in the exact value and direction, for example \"Recording {suggested_measurement} would help refine "
          "the estimate.\" Describe only what the facts show. Do not say "
          "whether, how much or when to drink, give a daily amount, mention heart rate, dehydration, health or any "
          "medical condition, adjust anything for the weather, judge the workout, use causal words, give advice or add "
          "disclaimers; Hydra adds the required caveats. No tools. Use only these placeholders:")
FACTS_MARKER = " Facts: "
LIMITATIONS = [
    "Wellness information, not medical advice.",
    "Muse Wonder wrote the wording; every number was computed and filled in by Hydra from your entries.",
    "The estimate is of workout fluid loss only. It is not a drinking target or a daily fluid requirement.",
    "Temperature and humidity are context only; the estimate applies no weather adjustment.",
    "Heart rate is not used, and Hydra does not infer dehydration.",
]
ACTIVITY_TEXT = {"running": "running", "cycling": "cycling", "walking": "walking", "strength": "strength training",
                 "other": "exercise"}
WHEN = {"morning": "in the morning", "afternoon": "in the afternoon", "evening": "in the evening", "night": "at night"}
SESSION = {"running": ("run", "runs"), "cycling": ("ride", "rides"), "walking": ("walk", "walks"),
           "strength": ("strength session", "strength sessions"),
           "other": ("workout of this type", "workouts of this type")}
MISSING = {
    "complete_environment_and_intensity": "this workout's intensity, temperature and humidity",
    "confirmed_comparable_conditions": "your confirmation that this workout's conditions match your earlier sessions",
    "usable_measurements_with_error_bounds": "previous weigh-ins at the same intensity, temperature and humidity, "
                                             "with their measurement error bounds",
    "actual_measurement_for_started_exercise": "a weigh-in from this workout itself, since it has already started",
}
SUGGESTIONS = {
    "repeat_weigh_in": "another before-and-after weigh-in on a workout at this intensity, temperature and humidity",
    "weigh_this_workout": "your weight before and after this workout, plus what you drink and any urine during it",
    "record_conditions": "this workout's intensity, temperature and humidity, and your weight before and after it",
    "confirm_conditions": "a confirmation that this workout's conditions match your earlier sessions, and your "
                          "weight before and after it",
}
# Beyond the trend rules: relative and judging words, drinking and intake, weather adjustment, wearables
# and reliability claims. Direction always comes from a placeholder.
WORKOUT_BLOCKED = re.compile(
    r"[°%]|\b(?:minutes?|mins?|hours?|hrs?|seconds?|degrees?|celsius|fahrenheit|kg|kilo\w*|grams?|lbs?|pounds?|"
    r"single|couple|several|few|fewer|many|multiple|numerous|pair|"
    r"than|longer|shorter|long|short|brief|lengthy|extended|hotter|hottest|hot|colder|coldest|cold|cooler|cool|"
    r"warmer|warm|heat\w*|chill\w*|humid|muggy|dry|drier|wet|harder|hard|easier|easy|tough\w*|intense|strenuous|"
    r"vigorous|demanding|heav\w*|light|faster|slower|similar\w*|same|different|difference\w*|differ\w*|unlike|"
    r"match\w*|equal\w*|exceed\w*|above|below|beyond|within|outside|over|under|likely|probabl\w*|definite\w*|surely|"
    r"accura\w*|precis\w*|reliab\w*|unreliab\w*|exact\w*|certain\w*|confiden\w*|guarantee\w*|valid\w*|proven|"
    r"drink\w*|drank|water|beverage\w*|intake|replac\w*|replenish\w*|refuel\w*|refill\w*|sip\w*|gulp\w*|"
    r"electrolyt\w*|sodium|salt\w*|thirst\w*|daily|requir\w*|goal\w*|adjust\w*|compensat\w*|multipl\w*|"
    r"pulse|hrv|bpm|wearable\w*|overheat\w*|exhaust\w*|stroke\w*|collaps\w*|nause\w*|vomit\w*|injur\w*|"
    r"emergenc\w*)\b", re.IGNORECASE)

Count = Annotated[int, Field(strict=True, ge=0, le=MAX_HISTORY)]
Minutes = Annotated[int, Field(strict=True, ge=1, le=1440)]
Celsius = Annotated[int, Field(strict=True, ge=-60, le=60)]
Percent = Annotated[int, Field(strict=True, ge=0, le=100)]
Ml = Annotated[int, Field(strict=True, ge=0, le=1_000_000_000)]
Activity = Literal["running", "cycling", "walking", "strength", "other"]
MissingCode = Literal["complete_environment_and_intensity", "confirmed_comparable_conditions",
                      "usable_measurements_with_error_bounds", "actual_measurement_for_started_exercise"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Planned(Strict):
    activity: Activity
    intensity: Literal["low", "moderate", "high"] | None
    time_of_day: Literal["morning", "afternoon", "evening", "night"]
    duration_minutes: Minutes
    temperature_c: Celsius | None
    humidity_percent: Percent | None
    conditions_confirmed: StrictBool


class History(Strict):
    sessions: Count
    activity_sessions: Count
    matching_sessions: Count
    weigh_in_sessions: Count
    typical_duration_minutes: Minutes | None
    typical_temperature_c: Celsius | None
    typical_humidity_percent: Percent | None
    measured_loss_ml: Ml | None


class Comparison(Strict):
    duration: Literal["longer", "shorter", "similar"] | None
    temperature: Literal["hotter", "cooler", "similar"] | None
    humidity: Literal["more_humid", "less_humid", "similar"] | None
    estimate: Literal["above", "below", "within"] | None


class Estimate(Strict):
    status: Literal["estimated", "insufficient_data"]
    value_ml: Ml | None
    lower_ml: Ml | None
    upper_ml: Ml | None
    sample_count: Count
    missing_inputs: list[MissingCode] = Field(max_length=len(MISSING))


class WorkoutFacts(Strict):
    version: Literal["wonder-workout-facts-v1"]
    timezone: str = Field(min_length=1, max_length=128)
    planned: Planned
    history: History
    comparison: Comparison
    estimate: Estimate
    suggested_measurement: Literal["repeat_weigh_in", "weigh_this_workout", "record_conditions", "confirm_conditions"]
    applicable_insights: list[str] = Field(max_length=len(INSIGHTS))


def _compare(planned: int | None, typical: int | None, similar, labels: tuple[str, str]) -> str | None:
    if planned is None or typical is None:
        return None
    if similar(planned, typical):
        return "similar"
    return labels[0] if planned > typical else labels[1]


def _derived(planned: dict, history: dict, estimate: dict) -> dict:
    """Everything computable from the stored numbers; recomputed on every validation."""
    comparison = {
        "duration": _compare(planned["duration_minutes"], history["typical_duration_minutes"],
                             lambda p, t: abs(p - t) * 100 <= DURATION_SIMILAR_PCT * t, ("longer", "shorter")),
        "temperature": _compare(planned["temperature_c"], history["typical_temperature_c"],
                                lambda p, t: abs(p - t) < TEMPERATURE_SIMILAR_C, ("hotter", "cooler")),
        "humidity": _compare(planned["humidity_percent"], history["typical_humidity_percent"],
                             lambda p, t: abs(p - t) < HUMIDITY_SIMILAR_POINTS, ("more_humid", "less_humid")),
        "estimate": None,
    }
    estimated = estimate["status"] == "estimated"
    measured = history["measured_loss_ml"]
    if estimated and measured is not None:
        comparison["estimate"] = ("above" if measured < estimate["lower_ml"] else
                                  "below" if measured > estimate["upper_ml"] else "within")
    missing = estimate["missing_inputs"]
    suggestion = ("repeat_weigh_in" if estimated else
                  "weigh_this_workout" if "actual_measurement_for_started_exercise" in missing else
                  "record_conditions" if "complete_environment_and_intensity" in missing else
                  "confirm_conditions" if "confirmed_comparable_conditions" in missing and history["matching_sessions"]
                  else "weigh_this_workout")
    applicable = [] if not history["activity_sessions"] else [name for name, applies in (
        ("duration_vs_typical", comparison["duration"] is not None),
        ("weather_vs_typical", comparison["temperature"] is not None or comparison["humidity"] is not None),
        ("comparable_history", True),
        ("estimate", estimated),
        ("estimate_vs_previous", comparison["estimate"] is not None),
        ("missing_information", not estimated and bool(missing)),
        ("refine_estimate", True),
    ) if applies]
    return {"comparison": comparison, "suggested_measurement": suggestion, "applicable_insights": applicable}


def _whole(value: float | None) -> int | None:
    return None if value is None else round(value)


def _typical(values: list[float]) -> int | None:
    return round(median(values)) if values else None


def _missing(engine_codes: list, planned: dict, history: dict) -> list[str]:
    """The engine's missing inputs, made specific: it reports conditions and confirmation together."""
    complete = None not in (planned["intensity"], planned["temperature_c"], planned["humidity_percent"])
    codes = [code for code in engine_codes if code in MISSING
             and not (code == "complete_environment_and_intensity" and complete)
             and not (code == "confirmed_comparable_conditions" and planned["conditions_confirmed"])]
    if (not history["matching_sessions"] and "actual_measurement_for_started_exercise" not in codes
            and "usable_measurements_with_error_bounds" not in codes):
        codes.append("usable_measurements_with_error_bounds")  # Nothing comparable to project from.
    return codes


def build_facts(exercise: Exercise, samples: tuple[SweatSample, ...], timezone: str, generated_at: datetime) -> dict:
    """Aggregates of the planned workout and the supplied history; raises CalculationError or ValueError."""
    if not isinstance(exercise, Exercise) or exercise.actual is not None:
        raise ValueError("A planned workout without a completed measurement is required")
    if not isinstance(samples, tuple) or len(samples) > MAX_HISTORY:
        raise ValueError("At most 32 history samples")
    zone = ZoneInfo(timezone)
    # The existing v2 engine, unchanged: strictly earlier, comparable, caller-supplied history only.
    forecast = predict_longitudinal(exercise, samples, generated_at=generated_at)
    conditions = exercise.conditions
    same = [sample for sample in samples if sample.conditions.activity == conditions.activity]
    # The engine's own comparability rule: identical complete activity, intensity, temperature and humidity.
    matching = [sample for sample in same if conditions.complete and sample.conditions == conditions]
    measured = [result.estimated_loss_ml for result in (estimate_workout_loss(sample.measurement) for sample in same)
                if result.status == "estimated"]
    hour = exercise.starts_at.astimezone(zone).hour
    planned = {"activity": conditions.activity, "intensity": conditions.intensity,
               "time_of_day": ("morning" if 5 <= hour < 12 else "afternoon" if 12 <= hour < 17
                               else "evening" if 17 <= hour < 22 else "night"),
               "duration_minutes": max(1, round(exercise.duration_minutes)),
               "temperature_c": _whole(conditions.temperature_c), "humidity_percent": _whole(conditions.humidity_percent),
               "conditions_confirmed": exercise.comparable_conditions_confirmed}
    history = {"sessions": len(samples), "activity_sessions": len(same), "matching_sessions": len(matching),
               "weigh_in_sessions": len(measured),
               "typical_duration_minutes": _typical([s.measurement.duration_minutes for s in same
                                                     if s.measurement.duration_minutes is not None]),
               "typical_temperature_c": _typical([s.conditions.temperature_c for s in same
                                                  if s.conditions.temperature_c is not None]),
               "typical_humidity_percent": _typical([s.conditions.humidity_percent for s in same
                                                     if s.conditions.humidity_percent is not None]),
               "measured_loss_ml": _typical(measured)}
    if history["typical_duration_minutes"] == 0:
        history["typical_duration_minutes"] = 1
    estimated = forecast["status"] == "estimated" and all(
        isinstance(forecast[name], (int, float)) and math.isfinite(forecast[name])
        for name in ("value_ml", "lower_ml", "upper_ml"))
    estimate = {"status": "estimated" if estimated else "insufficient_data",
                "value_ml": round(forecast["value_ml"]) if estimated else None,
                "lower_ml": math.floor(forecast["lower_ml"]) if estimated else None,
                "upper_ml": math.ceil(forecast["upper_ml"]) if estimated else None,
                "sample_count": forecast["sample_count"] if estimated else 0,
                "missing_inputs": [] if estimated else _missing(forecast.get("missing_inputs", []), planned, history)}
    facts = {"version": FACTS_VERSION, "timezone": timezone, "planned": planned, "history": history,
             "estimate": estimate}
    facts |= _derived(planned, history, estimate)
    return validate_facts(facts)


def validate_facts(facts: dict) -> dict:
    """Strict shape plus internal consistency; never trusts a stored or embedded derivation."""
    try:
        if WorkoutFacts.model_validate(facts).model_dump() != facts:
            raise ValueError
        ZoneInfo(facts["timezone"])
        history, estimate = facts["history"], facts["estimate"]
        if not (history["matching_sessions"] <= history["activity_sessions"] <= history["sessions"]
                and history["weigh_in_sessions"] <= history["activity_sessions"]):
            raise ValueError
        if (history["measured_loss_ml"] is None) != (history["weigh_in_sessions"] == 0):
            raise ValueError
        if not history["activity_sessions"] and any(history[name] is not None for name in (
                "typical_duration_minutes", "typical_temperature_c", "typical_humidity_percent")):
            raise ValueError
        values = (estimate["value_ml"], estimate["lower_ml"], estimate["upper_ml"])
        if estimate["status"] == "estimated":
            if (None in values or not values[1] <= values[0] <= values[2] or estimate["missing_inputs"]
                    or not 1 <= estimate["sample_count"] <= min(history["matching_sessions"], history["weigh_in_sessions"])):
                raise ValueError
        elif values != (None, None, None) or estimate["sample_count"]:
            raise ValueError
        planned, missing = facts["planned"], estimate["missing_inputs"]
        if (len(set(missing)) != len(missing)
                or ("complete_environment_and_intensity" in missing
                    and None not in (planned["intensity"], planned["temperature_c"], planned["humidity_percent"]))
                or ("confirmed_comparable_conditions" in missing and planned["conditions_confirmed"])
                or (estimate["status"] != "estimated" and not history["matching_sessions"]
                    and not {"usable_measurements_with_error_bounds", "actual_measurement_for_started_exercise"} & set(missing))):
            raise ValueError
        derived = _derived(facts["planned"], history, estimate)
        if any(facts[name] != value for name, value in derived.items()):
            raise ValueError
    except (ValidationError, ValueError, KeyError, TypeError):
        raise ValueError("Workout facts failed validation") from None
    return facts


def _count(n: int, noun: tuple[str, str]) -> str:
    return f"{n} {noun[0] if n == 1 else noun[1]}"


def placeholder_values(facts: dict) -> dict[str, str]:
    """Every value Wonder may refer to, formatted by Hydra; absent facts have no placeholder."""
    planned, history, comparison, estimate = facts["planned"], facts["history"], facts["comparison"], facts["estimate"]
    noun = SESSION[planned["activity"]]
    typical = f"your typical {noun[0]}"
    weather = [part for part in (None if planned["temperature_c"] is None else f"{planned['temperature_c']} °C",
                                 None if planned["humidity_percent"] is None else f"{planned['humidity_percent']}% humidity")
               if part]
    workout = f"{planned['duration_minutes']} minutes of "
    workout += f"{planned['intensity']}-intensity " if planned["intensity"] else ""
    workout += f"{ACTIVITY_TEXT[planned['activity']]} {WHEN[planned['time_of_day']]}"
    workout += f" at {' and '.join(weather)}" if weather else ""
    total = history["activity_sessions"]
    values = {"planned_workout": workout,
              "previous_sessions": f"{total} previous {noun[0] if total == 1 else noun[1]}",
              "matching_sessions": f"{history['matching_sessions']} of your {total} previous "
                                   f"{noun[0] if total == 1 else noun[1]} at the same intensity, temperature and humidity",
              "weigh_ins": f"{history['weigh_in_sessions']} of your {total} previous "
                           f"{noun[0] if total == 1 else noun[1]} with a complete before-and-after weigh-in",
              "suggested_measurement": SUGGESTIONS[facts["suggested_measurement"]]}
    duration, typical_duration = planned["duration_minutes"], history["typical_duration_minutes"]
    values |= {"duration_comparison": {
        "longer": f"longer than {typical} ({duration} vs {typical_duration} minutes)",
        "shorter": f"shorter than {typical} ({duration} vs {typical_duration} minutes)",
        "similar": f"close to the length of {typical} ({typical_duration} minutes)"}[comparison["duration"]]
    } if comparison["duration"] else {}
    temperature, typical_temperature = planned["temperature_c"], history["typical_temperature_c"]
    values |= {"temperature_comparison": {
        "hotter": f"hotter than {typical} ({temperature} °C vs {typical_temperature} °C)",
        "cooler": f"cooler than {typical} ({temperature} °C vs {typical_temperature} °C)",
        "similar": f"close to the temperature of {typical} ({typical_temperature} °C)"}[comparison["temperature"]]
    } if comparison["temperature"] else {}
    humidity, typical_humidity = planned["humidity_percent"], history["typical_humidity_percent"]
    values |= {"humidity_comparison": {
        "more_humid": f"more humid than {typical} ({humidity}% vs {typical_humidity}% humidity)",
        "less_humid": f"less humid than {typical} ({humidity}% vs {typical_humidity}% humidity)",
        "similar": f"close to the humidity of {typical} ({typical_humidity}% humidity)"}[comparison["humidity"]]
    } if comparison["humidity"] else {}
    if history["measured_loss_ml"] is not None:
        values["measured_loss"] = (f"{history['measured_loss_ml']} mL (the median of "
                                   f"{_count(history['weigh_in_sessions'], ('weighed ' + noun[0], 'weighed ' + noun[1]))})")
    if estimate["status"] == "estimated":
        low, high = estimate["lower_ml"], estimate["upper_ml"]
        values["estimate"] = f"about {low} mL" if low == high else f"about {low} to {high} mL"
        values["estimate_basis"] = (f"{_count(estimate['sample_count'], noun)} weighed at the same intensity, "
                                    f"temperature and humidity")
    if comparison["estimate"]:
        median_text = f"median {history['measured_loss_ml']} mL"
        values["estimate_comparison"] = {
            "above": f"above what you measured on your weighed {noun[1]} ({median_text})",
            "below": f"below what you measured on your weighed {noun[1]} ({median_text})",
            "within": f"in line with what you measured on your weighed {noun[1]} ({median_text})"}[comparison["estimate"]]
    if estimate["status"] != "estimated" and estimate["missing_inputs"]:
        values["missing_information"] = " and ".join(MISSING[code] for code in estimate["missing_inputs"])
    return values


def workout_schema(applicable: list[str]) -> dict:
    return {"type": "object", "additionalProperties": False, "required": ["summary", "insights"],
            "properties": {
                "summary": {"type": "string", "maxLength": SUMMARY_CHARS},
                "insights": {"type": "array", "minItems": 1, "maxItems": min(MAX_INSIGHTS, len(applicable)),
                             "items": {"type": "object", "additionalProperties": False, "required": ["id", "text"],
                                       "properties": {"id": {"type": "string", "enum": list(applicable)},
                                                      "text": {"type": "string", "maxLength": INSIGHT_CHARS}}}}}}


def _prompt(facts: dict) -> str:
    """The fixed instructions plus only the placeholders these facts can fill."""
    available = placeholder_values(facts)
    return (PROMPT + " " + "; ".join(f"{{{name}}} = {meaning}" for name, meaning in PLACEHOLDERS.items()
                                     if name in available) + ".")


def workout_payload(facts: dict) -> dict:
    validate_facts(facts)
    if not facts["applicable_insights"]:
        raise ValueError("No previous sessions of this activity")
    return {"model": MODEL, "store": False, "stream": False, "background": False,
            "max_output_tokens": WORKOUT_OUTPUT_LIMIT, "reasoning": {"effort": "minimal"},
            "text": {"format": {"type": "json_schema", "name": FORMAT_NAME, "strict": True,
                                "schema": workout_schema(facts["applicable_insights"])}},
            "input": [{"role": "user", "content": [{"type": "input_text",
                "text": _prompt(facts) + FACTS_MARKER + canonical(facts)}]}]}


def facts_from_payload(payload: dict) -> dict:
    """The facts a workout payload carries; raises unless the payload is exactly what Hydra builds."""
    try:
        text = payload["input"][0]["content"][0]["text"]
        if not isinstance(text, str) or not text.startswith(PROMPT) or FACTS_MARKER not in text:
            raise ValueError
        facts = validate_facts(strict_json(text[text.rindex(FACTS_MARKER) + len(FACTS_MARKER):]))
        if payload != workout_payload(facts):
            raise ValueError
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, RecursionError):
        raise ValueError("Not a Hydra workout payload") from None
    return facts


def preview(facts: dict) -> dict:
    """What would be sent and its worst-case cost; not a billing guarantee."""
    if not facts["applicable_insights"]:
        return {"version": VERSION, "facts": facts, "explainable": False, "payload_sha256": None,
                "input_bound_tokens": None, "worst_case_micro_usd": None}
    payload = workout_payload(facts)
    bound = input_bound(payload)
    return {"version": VERSION, "facts": facts, "explainable": True, "payload_sha256": payload_sha256(payload),
            "input_bound_tokens": bound, "worst_case_micro_usd": worst_case_micro_usd(bound, WORKOUT_OUTPUT_LIMIT)}


def _render(template, limit: int, values: dict[str, str]) -> str:
    """One checked template to display text; raises on anything Wonder may not say itself."""
    if (not isinstance(template, str) or template != template.strip() or not 1 <= len(template) <= limit
            or any(ord(char) < 32 for char in template)):
        raise ValueError
    names = PLACEHOLDER.findall(template)
    prose = PLACEHOLDER.sub(" ", template)
    if (any(name not in values for name in names) or "{" in prose or "}" in prose
            or NUMERIC.search(prose) or COMPARATIVE.search(prose) or BLOCKED.search(prose)
            or WORKOUT_BLOCKED.search(prose)):
        raise ValueError
    return PLACEHOLDER.sub(lambda match: values[match.group(1)], template)


def validate_explanation(value, facts: dict) -> dict:
    """Wonder's JSON to checked templates and rendered text; any violation rejects it whole.

    An insight Wonder repeats counts once (its first text is kept); every repeat is still checked.
    """
    if not isinstance(value, dict) or set(value) != {"summary", "insights"}:
        raise ValueError
    values = placeholder_values(facts)
    insights = value["insights"]
    if not isinstance(insights, list) or not 1 <= len(insights) <= min(MAX_INSIGHTS, len(facts["applicable_insights"])):
        raise ValueError
    checked = {}
    for item in insights:
        if not isinstance(item, dict) or set(item) != {"id", "text"} or item["id"] not in facts["applicable_insights"]:
            raise ValueError
        text = _render(item["text"], INSIGHT_CHARS, values)
        checked.setdefault(item["id"], {"id": item["id"], "template": item["text"], "text": text})
    return {"summary_template": value["summary"], "summary": _render(value["summary"], SUMMARY_CHARS, values),
            "insights": list(checked.values())}


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


def workout_result(facts: dict, explanation: dict, *, account: str, attempt_id: str, observations: dict,
                   generated_at: str) -> dict:
    return {"version": VERSION, "facts": facts, "payload_sha256": payload_sha256(workout_payload(facts)),
            "summary": explanation["summary"], "summary_template": explanation["summary_template"],
            "insights": [{"id": item["id"], "title": INSIGHTS[item["id"]], "template": item["template"],
                          "text": item["text"]} for item in explanation["insights"]],
            "generated_at": generated_at,
            "provenance": {"mode": "meta_live", "provider": "Meta", "model": MODEL, "account_id": account,
                           "attempt_id": attempt_id, "text_origin": "muse_wonder_checked",
                           "numbers_checked_against": "facts"},
            "provider_observations": observations, "limitations": list(LIMITATIONS)}


if __name__ == "__main__":
    print(json.dumps(workout_schema(list(INSIGHTS)), indent=2))
