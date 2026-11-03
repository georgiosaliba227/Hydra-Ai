"""Offline eight-section Wonder contract; no route, gateway, persistence or dispatch.

Wonder may select vetted sentence scaffolds. Hydra supplies every factual
clause, number, limitation and title. This deliberately does not advertise free
model-authored prose or a live integration. Recorded validation establishes
internal consistency, not provider authenticity, invoice finality or permission
to spend. Existing workout explanations and their gateway remain unchanged.
"""
from typing import Annotated, Literal
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError

from .meta_accounts import CAP
from .meta_provider import ProviderReply, strict_json
from .recognition import RecognitionUnavailable
from .wonder_hydration import MODEL, canonical, input_bound, payload_sha256, worst_case_micro_usd
from .wonder_trends import BLOCKED, COMPARATIVE, NUMERIC, PLACEHOLDER
from .wonder_workout import WORKOUT_BLOCKED

VERSION = "wonder-analysis-preview-v1"
FACTS_VERSION = "wonder-analysis-facts-v1"
OUTPUT_LIMIT = 2048
SECTIONS = {
    "summary": "Hydration-related summary", "workout_loss": "Workout fluid-loss estimate",
    "activity": "Activity context", "environment": "Environmental context",
    "beverages": "Beverage and electrolyte context", "trends": "Personal trends",
    "uncertainty": "Prediction uncertainty", "measurement": "Measurement insights",
}
SCAFFOLDS = {
    "summary": ("{record_summary}. {research_scope}.", "The supplied record shows {record_summary}. {research_scope}."),
    "workout_loss": ("{loss_estimate}. {calibration_context}.",
                     "For this workout: {loss_estimate}. The basis is {calibration_context}."),
    "activity": ("{activity_context}. {activity_history}.",
                 "The supplied workout describes {activity_context}. {activity_history}."),
    "environment": ("{environment_context}. {environment_role}.",
                    "The supplied environment is {environment_context}. {environment_role}."),
    "beverages": ("{beverage_context}. {water_context}; {electrolyte_context}. {logging_scope}.",
                  "The log shows {beverage_context}. Composition: {water_context}; {electrolyte_context}. {logging_scope}."),
    "trends": ("{history_context}. {trend_scope}.", "The descriptive record shows {history_context}. {trend_scope}."),
    "uncertainty": ("{uncertainty_context}. {missing_context}. {accounting_context}.",
                    "Evidence limits: {uncertainty_context}. {missing_context}. {accounting_context}."),
    "measurement": ("{measurement_context}.", "Further observations can document {measurement_context}."),
}
MISSING = {
    "exercise": "a supplied workout",
    "complete_environment_and_intensity": "complete environmental and intensity context",
    "confirmed_comparable_conditions": "confirmation of comparable conditions",
    "usable_measurements_with_error_bounds": "usable comparable measurements with error bounds",
    "actual_measurement_for_started_exercise": "a completed measurement for the started workout",
    "intake_completeness": "verified logging completeness",
    "documented_water_composition": "documented water composition",
    "complete_electrolyte_composition": "complete electrolyte composition",
    "environmental_context": "environmental context",
}
LIMITATIONS = [
    "Offline contract and mock/recorded validation only; live dispatch and client integration are not implemented here.",
    "Muse Wonder can select vetted scaffolds; Hydra authors the factual clauses and supplies every number.",
    "Logged intake does not measure hydration status, retention or a required intake amount.",
    "Workout loss is a research mass-balance proxy; historical envelopes do not guarantee future interval coverage.",
    "Recorded consistency checks do not attest provider authenticity, billing settlement or spending authorization.",
]
PROMPT = ("Select exactly one permitted sentence template for each required section. Copy a schema enum verbatim. "
          "Hydra supplies every factual clause through the section-specific placeholders. Do not add prose, numbers, "
          "units, comparisons, diagnoses, prescriptions, causal claims or new facts. Missing values stay missing. "
          "This is an offline contract, not permission to dispatch. No tools. Aggregated facts: ")
Amount = Annotated[float, Field(strict=True, ge=0, le=10**12, allow_inf_nan=False)]
Signed = Annotated[float, Field(strict=True, ge=-(10**12), le=10**12, allow_inf_nan=False)]
Count = Annotated[int, Field(strict=True, ge=0, le=10**9)]
HistoryCount = Annotated[int, Field(strict=True, ge=0, le=32)]
Status = Literal["estimated", "insufficient_data"]
CompositionStatus = Literal["complete", "partial", "unknown"]
MissingCode = Literal[
    "exercise", "complete_environment_and_intensity", "confirmed_comparable_conditions",
    "usable_measurements_with_error_bounds", "actual_measurement_for_started_exercise", "intake_completeness",
    "documented_water_composition", "complete_electrolyte_composition", "environmental_context",
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Forecast(Strict):
    status: Status
    value_ml: Amount | None
    lower_ml: Amount | None
    upper_ml: Amount | None
    interval_kind: Literal["historical_error_envelope", "conditional_measurement_envelope",
                           "synthetic_participant_split_conformal", "synthetic_empirical_calibration_envelope"]


class Intake(Strict):
    beverage_count: Count | None
    beverage_volume_ml: Amount | None
    water_ml: Amount | None
    sodium_mg: Amount | None
    potassium_mg: Amount | None
    sodium_status: CompositionStatus
    potassium_status: CompositionStatus
    completeness: Literal["unverified"]


class Activity(Strict):
    activity: Literal["running", "cycling", "walking", "strength", "other"] | None
    duration_minutes: Annotated[float, Field(strict=True, gt=0, le=1440, allow_inf_nan=False)] | None
    intensity: Literal["low", "moderate", "high"] | None


class Environment(Strict):
    temperature_c: Annotated[float, Field(strict=True, ge=-60, le=60, allow_inf_nan=False)] | None
    humidity_percent: Annotated[float, Field(strict=True, ge=0, le=100, allow_inf_nan=False)] | None
    context_only: StrictBool


class Calibration(Strict):
    total_samples: HistoryCount
    comparable_samples: HistoryCount
    recent_samples: HistoryCount


class Trends(Strict):
    window_days: Literal[14]
    logged_days: Annotated[int, Field(strict=True, ge=0, le=14)] | None
    beverage_lower_ml: Amount | None
    beverage_upper_ml: Amount | None


class Accounting(Strict):
    status: Literal["estimated", "unavailable"]
    quantity: Literal["logged_intake_minus_measured_exercise_loss"]
    value_ml: Signed | None
    lower_ml: Signed | None
    upper_ml: Signed | None


class AnalysisFacts(Strict):
    version: Literal["wonder-analysis-facts-v1"]
    mode: Literal["personal", "synthetic_demo"]
    research_only: StrictBool
    forecast: Forecast
    intake: Intake
    activity: Activity
    environment: Environment
    calibration: Calibration
    trends: Trends
    accounting: Accounting
    missing_inputs: list[MissingCode] = Field(max_length=len(MISSING))


def _range_valid(values: tuple, estimated: bool) -> bool:
    return (None not in values and values[1] <= values[0] <= values[2]) if estimated else values == (None, None, None)


def validate_facts(facts: dict) -> dict:
    try:
        checked = AnalysisFacts.model_validate(facts).model_dump()
        forecast, intake, calibration, trends, accounting = (checked[key] for key in (
            "forecast", "intake", "calibration", "trends", "accounting"))
        if checked["research_only"] is not True or checked["environment"]["context_only"] is not True:
            raise ValueError
        for item in (forecast, accounting):
            if not _range_valid(tuple(item[name] for name in ("value_ml", "lower_ml", "upper_ml")), item["status"] == "estimated"):
                raise ValueError
        if not calibration["recent_samples"] <= min(5, calibration["comparable_samples"]) <= calibration["total_samples"]:
            raise ValueError
        # Check the comparable count itself, even if recent history is capped at five.
        if calibration["comparable_samples"] > calibration["total_samples"]:
            raise ValueError
        if (intake["beverage_volume_ml"] is None) != (intake["beverage_count"] is None):
            raise ValueError
        if intake["beverage_count"] == 0 and intake["beverage_volume_ml"] != 0:
            raise ValueError
        if intake["water_ml"] is not None and (intake["beverage_volume_ml"] is None or intake["water_ml"] > intake["beverage_volume_ml"]):
            raise ValueError
        for nutrient in ("sodium", "potassium"):
            if (intake[nutrient+"_mg"] is not None) != (intake[nutrient+"_status"] == "complete"):
                raise ValueError
        if not intake["beverage_count"] and (intake["water_ml"] is not None or any(
                intake[nutrient+"_status"] != "unknown" for nutrient in ("sodium", "potassium"))):
            raise ValueError
        low, high = trends["beverage_lower_ml"], trends["beverage_upper_ml"]
        if trends["logged_days"]:
            if low is None or high is None or low > high:
                raise ValueError
        elif low is not None or high is not None:
            raise ValueError
        if checked["mode"] == "synthetic_demo":
            if (any(intake[name] is not None for name in ("beverage_count", "beverage_volume_ml", "water_ml", "sodium_mg", "potassium_mg"))
                    or trends["logged_days"] is not None or accounting["status"] != "unavailable"
                    or not forecast["interval_kind"].startswith("synthetic_")
                    or any(intake[nutrient+"_status"] != "unknown" for nutrient in ("sodium", "potassium"))):
                raise ValueError
        elif intake["beverage_volume_ml"] is None or trends["logged_days"] is None or forecast["interval_kind"].startswith("synthetic_"):
            raise ValueError
        if len(set(checked["missing_inputs"])) != len(checked["missing_inputs"]):
            raise ValueError
    except (ValidationError, ValueError, TypeError, KeyError):
        raise ValueError("Analysis facts failed validation") from None
    return checked


def build_facts(analysis: dict) -> dict:
    """Allowlist local aggregates; never carry identifiers, times or caller text."""
    try:
        if (analysis["version"] != "hydration-analysis-v1" or analysis["research_only"] is not True
                or analysis["text_origin"] != "deterministic_local"
                or analysis["numerical_forecast"]["units"] != "mL"
                or analysis["numerical_forecast"]["quantity"] != "estimated_sweat_loss"
                or analysis["numerical_forecast"]["synthetic"] is not (analysis["mode"] == "synthetic_demo")):
            raise ValueError
        numerical, intake = analysis["numerical_forecast"], analysis["intake"]
        trends = next(section["facts"] for section in analysis["sections"] if section["id"] == "trends")
        facts = {"version": FACTS_VERSION, "mode": analysis["mode"], "research_only": True,
            "forecast": {key: numerical[key] for key in ("status", "value_ml", "lower_ml", "upper_ml", "interval_kind")},
            "intake": {**{key: intake[key] for key in ("beverage_count", "beverage_volume_ml", "water_ml", "completeness")},
                       **{key: intake["composition"][key] for key in ("sodium_mg", "potassium_mg", "sodium_status", "potassium_status")}},
            "activity": {key: numerical["input_factors"].get(key) for key in ("activity", "duration_minutes", "intensity")},
            "environment": {key: analysis["environmental_context"][key] for key in ("temperature_c", "humidity_percent", "context_only")},
            "calibration": {key: analysis["calibration"][key] for key in ("total_samples", "comparable_samples", "recent_samples")},
            "trends": {key: trends[key] for key in ("window_days", "logged_days", "beverage_lower_ml", "beverage_upper_ml")},
            "accounting": {key: analysis["exercise_accounting"][key] for key in ("status", "quantity", "value_ml", "lower_ml", "upper_ml")},
            "missing_inputs": list(analysis["missing_inputs"])}
        return validate_facts(facts)
    except (ValueError, KeyError, TypeError, StopIteration):
        raise ValueError("A valid local hydration analysis is required") from None


def _n(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


def placeholder_values(facts: dict) -> dict[str, str]:
    facts = validate_facts(facts)
    f, i, a, e, c, t, accounting = (facts[key] for key in ("forecast", "intake", "activity", "environment", "calibration", "trends", "accounting"))
    loss = (f"research estimate {_n(f['lower_ml'])} to {_n(f['upper_ml'])} mL, with point {_n(f['value_ml'])} mL"
            if f["status"] == "estimated" else "no numerical estimate is available")
    beverage = (f"{_n(i['beverage_volume_ml'])} mL of logged beverage volume" if i["beverage_volume_ml"] is not None
                else "personal beverage logs are excluded from this synthetic case")
    activity = (f"{_n(a['duration_minutes'])} minutes of {a['intensity'] or 'unspecified-intensity'} {a['activity'] or 'exercise'}"
                if a["duration_minutes"] is not None else "workout duration and activity are unavailable")
    environmental = "; ".join([
        f"temperature {_n(e['temperature_c'])} °C" if e["temperature_c"] is not None else "temperature unavailable",
        f"humidity {_n(e['humidity_percent'])}%" if e["humidity_percent"] is not None else "humidity unavailable"])
    nutrient = []
    for name in ("sodium", "potassium"):
        nutrient.append(f"documented {name} {_n(i[name+'_mg'])} mg" if i[name+"_mg"] is not None else
                        f"{name} composition {'incomplete; total withheld' if i[name+'_status'] == 'partial' else 'unknown'}")
    history = (f"{t['logged_days']} logged days in the {t['window_days']}-day descriptive record; recorded day totals "
               f"range from {_n(t['beverage_lower_ml'])} to {_n(t['beverage_upper_ml'])} mL" if t["logged_days"] else
               "no prior logged-day totals are available" if t["logged_days"] == 0 else "personal logged history is excluded from this synthetic case")
    account = (f"the matched completed-workout signed intake-minus-exercise-loss proxy is {_n(accounting['value_ml'])} mL, "
               f"ranging from {_n(accounting['lower_ml'])} to {_n(accounting['upper_ml'])} mL; urine and other losses are omitted"
               if accounting["status"] == "estimated" else
               "matched completed-workout arithmetic is unavailable; planned losses are not subtracted")
    return {"record_summary": beverage+"; "+loss,
        "research_scope": "this is research context, not total body hydration, an intake target or a diagnosis",
        "loss_estimate": loss,
        "calibration_context": f"{c['total_samples']} supplied observations; {c['comparable_samples']} comparable and {c['recent_samples']} recent comparable observations",
        "activity_context": activity,
        "activity_history": "workout comparability depends on documented conditions, protocol and instrument error bounds",
        "environment_context": environmental, "environment_role": "environment is context; no added weather adjustment is applied",
        "beverage_context": beverage,
        "water_context": f"documented water content {_n(i['water_ml'])} mL" if i["water_ml"] is not None else "water composition unknown",
        "electrolyte_context": "; ".join(nutrient),
        "logging_scope": "logging completeness is unverified; volume does not measure retention",
        "history_context": history, "trend_scope": "logged-day patterns do not determine physiological needs; absent logs are not measured zero consumption",
        "uncertainty_context": "measurement errors and incompatible observations limit interpretation; historical envelopes do not guarantee future coverage",
        "missing_context": "missing evidence includes "+"; ".join(MISSING[code] for code in facts["missing_inputs"]) if facts["missing_inputs"] else "the supplied fields do not remove measurement and generalization uncertainty",
        "accounting_context": account,
        "measurement_context": "comparable dry before-and-after weighing, recorded workout consumption and urine, timing, environment and instrument error bounds"}


def analysis_payload(facts: dict) -> dict:
    facts = validate_facts(facts)
    schema = {"type": "object", "additionalProperties": False, "required": ["sections"], "properties": {
        "sections": {"type": "object", "additionalProperties": False, "required": list(SECTIONS),
                     "properties": {key: {"type": "string", "enum": list(SCAFFOLDS[key]), "maxLength": 500} for key in SECTIONS}}}}
    return {"model": MODEL, "store": False, "stream": False, "background": False,
        "max_output_tokens": OUTPUT_LIMIT, "reasoning": {"effort": "minimal"},
        "text": {"format": {"type": "json_schema", "name": "hydration_analysis_scaffold_selection", "strict": True, "schema": schema}},
        "input": [{"role": "user", "content": [{"type": "input_text", "text": PROMPT+canonical(facts)}]}]}


def facts_from_payload(payload: dict) -> dict:
    """Recognize only an exact server-built payload; this does not authorize sending."""
    try:
        text = payload["input"][0]["content"][0]["text"]
        if not isinstance(text, str) or not text.startswith(PROMPT):
            raise ValueError
        facts = validate_facts(strict_json(text[len(PROMPT):]))
        if analysis_payload(facts) != payload:
            raise ValueError
    except (ValueError, TypeError, KeyError, IndexError):
        raise ValueError("Not a Hydra analysis payload") from None
    return facts


def preview(facts: dict) -> dict:
    facts = validate_facts(facts)
    payload = analysis_payload(facts)
    bound = input_bound(payload)
    exposure = worst_case_micro_usd(bound, OUTPUT_LIMIT)
    available = exposure <= CAP
    return {"version": VERSION, "facts": facts, "model": MODEL, "payload_sha256": payload_sha256(payload),
        "status": "available" if available else "unavailable", "explainable": available,
        "reason": None if available else "cost_bound_exceeds_per_request_cap", "input_bound_tokens": bound,
        "max_output_tokens": OUTPUT_LIMIT, "worst_case_micro_usd": exposure, "per_request_cap_micro_usd": CAP,
        "live_available": False, "dispatch_supported": False, "verified_for_billing": False,
        "cost_estimate_policy": "existing_reference_prices_not_a_verified_live_quote"}


def validate_selection(selection: dict, facts: dict) -> dict:
    values = placeholder_values(facts)
    try:
        if not isinstance(selection, dict) or set(selection) != {"sections"} or set(selection["sections"]) != set(SECTIONS):
            raise ValueError
        checked = {}
        for identifier in SECTIONS:
            template = selection["sections"][identifier]
            if not isinstance(template, str) or not 1 <= len(template) <= 500:
                raise ValueError
            plain = unicodedata.normalize("NFKC", PLACEHOLDER.sub(" ", template))
            if (any(character.isnumeric() or ord(character) < 32 for character in plain)
                    or NUMERIC.search(plain) or COMPARATIVE.search(plain) or BLOCKED.search(plain) or WORKOUT_BLOCKED.search(plain)
                    or template not in SCAFFOLDS[identifier]):
                raise ValueError
            # Exact scaffold membership also forbids cross-section placeholders,
            # missing caveats and unsupported nonnumeric prose.
            checked[identifier] = {"template": template, "text": PLACEHOLDER.sub(lambda match: values[match.group(1)], template)}
    except (ValueError, TypeError, KeyError):
        raise ValueError("Analysis selection failed validation") from None
    return checked


def _result(facts: dict, selection: dict, *, origin: str) -> dict:
    checked = validate_selection(selection, facts)
    synthetic = facts["mode"] == "synthetic_demo"
    return {"version": VERSION, "facts": validate_facts(facts), "payload_sha256": payload_sha256(analysis_payload(facts)),
        "sections": [{"id": key, "title": SECTIONS[key], **checked[key],
                      "evidence_status": "synthetic" if synthetic else
                      "estimated" if facts["forecast"]["status"] == "estimated" and key in ("summary", "workout_loss") else
                      "insufficient_data" if facts["forecast"]["status"] != "estimated" and key in ("summary", "workout_loss") else "context_only"}
                     for key in SECTIONS],
        "dispatch_supported": False, "limitations": list(LIMITATIONS),
        "provenance": {"selection_origin": origin, "text_origin": "hydra_vetted_scaffolds_and_facts",
                       "provider": "Meta" if origin == "checked_provider_reply" else None,
                       "model": MODEL if origin == "checked_provider_reply" else None,
                       "numbers_checked_against": "facts", "provider_authenticity_or_billing_attested": False}}


def mock_result(facts: dict) -> dict:
    return _result(facts, {"sections": {key: SCAFFOLDS[key][0] for key in SECTIONS}}, origin="mock_local")


def checked_result(reply: ProviderReply, facts: dict) -> dict:
    """Validate a supplied reply offline. This function never sends a request."""
    try:
        body = reply.body
        if (reply.status != 200 or body.get("model") != MODEL or body.get("status") != "completed"
                or body.get("error") is not None or body.get("incomplete_details") is not None):
            raise ValueError
        messages = [item for item in body["output"] if item.get("type") != "reasoning"]
        if len(messages) != 1 or messages[0]["type"] != "message" or messages[0]["role"] != "assistant" or messages[0]["status"] != "completed":
            raise ValueError
        parts = messages[0]["content"]
        if len(parts) != 1 or parts[0]["type"] != "output_text" or not isinstance(parts[0]["text"], str) or len(parts[0]["text"].encode()) > 16_384:
            raise ValueError
        return _result(facts, strict_json(parts[0]["text"]), origin="checked_provider_reply")
    except (ValueError, KeyError, TypeError, AttributeError):
        raise RecognitionUnavailable() from None


def replay_recorded(record: dict, facts: dict) -> dict:
    """Rebuild a supplied record against the exact current facts; no file writes."""
    try:
        facts = validate_facts(facts)
        if record["facts"] != facts or record["provenance"]["selection_origin"] not in ("mock_local", "checked_provider_reply"):
            raise ValueError
        selection = {"sections": {item["id"]: item["template"] for item in record["sections"]}}
        if _result(facts, selection, origin=record["provenance"]["selection_origin"]) != record:
            raise ValueError
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ValueError("Recorded analysis failed validation") from None
    return record
