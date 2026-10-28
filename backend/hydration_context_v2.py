"""Offline structured contextual comparison; no provider, key, ledger or transport."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from typing import Literal

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from ai.forecasting.predict import predict_workout
from ai.hydration.models import CalculationError, WorkoutMeasurement
from ai.hydration.workout import estimate_workout_loss
from .workout_forecasts import WorkoutForecastInput

SCENARIOS = ("complete", "missing_measurements", "contradictory_mass", "changing_conditions", "biometrics_and_supplements")
CANDIDATES = ("muse-spark-1.3", "muse-wonder-1.0")
Factor = Literal["workout_duration", "environment_reported", "personal_calibration", "intake_logged", "thirst_reported", "heart_rate_context", "supplement_context"]
Missing = Literal["calibration_measurements", "measurement_error_bounds", "environmental_context", "intake_completeness", "electrolyte_composition"]
Contradiction = Literal["negative_mass_balance", "incompatible_conditions"]
Uncertainty = Literal["synthetic_evidence_only", "not_daily_requirement", "insufficient_measurements", "environment_context_not_numeric_effect", "biometrics_not_dehydration", "supplements_no_automatic_adjustment"]
Suggestion = Literal["comparable_dry_weighing", "record_intake_urine", "record_error_bounds", "record_environment", "review_inconsistent_measurement", "compare_conditions"]

TEXT = {
    "workout_duration": "Workout duration provides context for the existing loss estimate.",
    "environment_reported": "Reported temperature and humidity describe the workout conditions.",
    "personal_calibration": "Comparable measured workouts can support personal calibration.",
    "intake_logged": "Logged beverage intake is separate from estimated exercise loss.",
    "thirst_reported": "Reported thirst is subjective context; it does not quantify a fluid deficit.",
    "heart_rate_context": "Heart-rate trends are contextual observations only.",
    "supplement_context": "Reported supplements remain context only.",
    "calibration_measurements": "Comparable pre/post-workout weighing and recorded intake/urine are missing.",
    "measurement_error_bounds": "Independently established measurement error bounds are missing.",
    "environmental_context": "Temperature or humidity is missing, limiting condition matching.",
    "intake_completeness": "Logging completeness is unknown; no entry does not mean zero consumption.",
    "electrolyte_composition": "Verified electrolyte composition is unavailable.",
    "negative_mass_balance": "The synthetic weighing/intake observations imply inconsistent negative loss; review the inputs.",
    "incompatible_conditions": "Historical and planned conditions differ; a comparable-rate projection is unsupported.",
    "synthetic_evidence_only": "This interpretation uses a synthetic fixture and reviewed local mock text, not a Meta response.",
    "not_daily_requirement": "Exercise loss is not a daily fluid requirement or a drinking recommendation.",
    "insufficient_measurements": "The numerical method abstained; contextual interpretation cannot fill in the missing value.",
    "environment_context_not_numeric_effect": "Weather context does not authorize an unvalidated numerical adjustment.",
    "biometrics_not_dehydration": "Heart rate and HRV do not directly establish dehydration.",
    "supplements_no_automatic_adjustment": "Caffeine or creatine use does not trigger an automatic hydration adjustment.",
    "comparable_dry_weighing": "Record comparable dry body mass before and after a completed workout.",
    "record_intake_urine": "Record fluid consumed and urine during that same workout, including measured zeros.",
    "record_error_bounds": "Obtain independently supported scale, volume and timing error bounds.",
    "record_environment": "Record workout environment and intensity to judge comparability.",
    "review_inconsistent_measurement": "Check timing, units, weighing protocol and intake/urine records before using this measurement.",
    "compare_conditions": "Collect a measurement under conditions comparable to the planned workout.",
}
PROMPT = ("Select only supported enum IDs for this synthetic context. The supplied numerical prediction is authoritative: "
          "do not change it, create goals or percentages, diagnose dehydration, infer it from HR/HRV, or apply caffeine/creatine adjustments. "
          "Identify missing data and contradictions, retain all required uncertainty, and suggest measurement steps. "
          "Return only the structured selection schema. No free-text advice, numerical output, tools or external data.")


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    factors: list[Factor] = Field(max_length=7)
    missing_information: list[Missing] = Field(max_length=5)
    contradictions: list[Contradiction] = Field(max_length=2)
    uncertainty: list[Uncertainty] = Field(min_length=2, max_length=6)
    measurement_suggestions: list[Suggestion] = Field(max_length=6)
    numerical_abstention: StrictBool

    @model_validator(mode="after")
    def unique_codes(self):
        for name in ("factors", "missing_information", "contradictions", "uncertainty", "measurement_suggestions"):
            value = getattr(self, name)
            if len(value) != len(set(value)):
                raise ValueError("Duplicate selections")
        return self


class ComparisonInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mode: Literal["mock"]
    scenario: Literal["complete", "missing_measurements", "contradictory_mass", "changing_conditions", "biometrics_and_supplements"]
    candidate_model: Literal["muse-spark-1.3", "muse-wonder-1.0"] = "muse-spark-1.3"


def build_scenario(name: str, *, generated_at: datetime | None = None) -> tuple[dict, dict]:
    """Only repository-owned scenarios. No caller health context is accepted."""
    if name not in SCENARIOS:
        raise ValueError("Unknown scenario")
    now = generated_at or datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
    prediction = predict_workout(None, generated_at=now, mode="synthetic_demo")
    context = {"synthetic": True, "workout_minutes": 60, "temperature_c": 24.0, "humidity_percent": 50.0,
               "calibration_count": 0, "error_bounds_available": False, "beverage_logged_ml": 500.0,
               "intake_complete": False, "sodium_known": False, "thirst_reported": False,
               "heart_rate_trend": None, "creatine_reported": False, "caffeine_reported": False,
               "measurement_consistent": None, "conditions_comparable": None}
    if name != "complete" and name != "biometrics_and_supplements":
        # No unsupported estimate is fabricated for absent/inconsistent calibration.
        prediction = predict_workout(None, generated_at=now)
        prediction["synthetic"] = True  # Entire scenario is server-owned synthetic data.
    if name == "missing_measurements":
        context.update(workout_minutes=None, temperature_c=None, humidity_percent=None, beverage_logged_ml=None)
    elif name == "contradictory_mass":
        # Hand-constructed observation: 70 kg before, 71 kg after, 0 mL intake/urine.
        measurement = WorkoutMeasurement(70.0, 71.0, 0.0, 0.0, 60.0, True, ("synthetic_contradiction_fixture",))
        measured = estimate_workout_loss(measurement)
        context.update(measurement_consistent=measured.status == "estimated", calibration_count=1, error_bounds_available=True)
    elif name == "changing_conditions":
        context.update(conditions_comparable=False, calibration_count=3, error_bounds_available=True)
    elif name == "biometrics_and_supplements":
        context.update(heart_rate_trend="higher_than_previous", creatine_reported=True, caffeine_reported=True, thirst_reported=True)
    return context, prediction


def supported_selection(context: dict, prediction: dict) -> dict:
    factors, missing, contradictions, suggestions = [], [], [], []
    uncertainty = ["synthetic_evidence_only", "not_daily_requirement"]
    if context["workout_minutes"] is not None:
        factors.append("workout_duration")
    if context["temperature_c"] is not None or context["humidity_percent"] is not None:
        factors.append("environment_reported")
        uncertainty.append("environment_context_not_numeric_effect")
    if context["temperature_c"] is None or context["humidity_percent"] is None:
        missing.append("environmental_context"); suggestions.append("record_environment")
    if context["calibration_count"]:
        factors.append("personal_calibration")
    else:
        missing.append("calibration_measurements"); suggestions += ["comparable_dry_weighing", "record_intake_urine"]
    if not context["error_bounds_available"]:
        missing.append("measurement_error_bounds"); suggestions.append("record_error_bounds")
    if context["beverage_logged_ml"] is not None:
        factors.append("intake_logged")
    if not context["intake_complete"]:
        missing.append("intake_completeness")
    if not context["sodium_known"]:
        missing.append("electrolyte_composition")
    if context["thirst_reported"]:
        factors.append("thirst_reported")
    if context["heart_rate_trend"] is not None:
        factors.append("heart_rate_context"); uncertainty.append("biometrics_not_dehydration")
    if context["creatine_reported"] or context["caffeine_reported"]:
        factors.append("supplement_context"); uncertainty.append("supplements_no_automatic_adjustment")
    if context["measurement_consistent"] is False:
        contradictions.append("negative_mass_balance"); suggestions.append("review_inconsistent_measurement")
    if context["conditions_comparable"] is False:
        contradictions.append("incompatible_conditions"); suggestions.append("compare_conditions")
    abstain = prediction["status"] != "estimated"
    if abstain:
        uncertainty.append("insufficient_measurements")
    return dict(factors=factors, missing_information=missing, contradictions=contradictions,
                uncertainty=uncertainty, measurement_suggestions=suggestions, numerical_abstention=abstain)


def mock_selection(context: dict, prediction: dict) -> dict:
    """Rule-based fixture adapter. This is deliberately not an LLM simulation score."""
    return supported_selection(context, prediction)


def validate_selection(value: dict, context: dict, prediction: dict) -> dict:
    selection = Selection.model_validate(value).model_dump()
    supported = supported_selection(context, prediction)
    for field in ("factors", "missing_information", "contradictions", "uncertainty", "measurement_suggestions"):
        if not set(selection[field]) <= set(supported[field]):
            raise ValueError("Unsupported context selection")
    if set(selection["contradictions"]) != set(supported["contradictions"]) or set(selection["uncertainty"]) != set(supported["uncertainty"]):
        raise ValueError("Required contradiction or uncertainty omitted")
    if selection["numerical_abstention"] != supported["numerical_abstention"]:
        raise ValueError("Numerical abstention mismatch")
    return selection


def compare_context(scenario: str, candidate_model: str = "muse-spark-1.3", *, generated_at: datetime | None = None) -> dict:
    if candidate_model not in CANDIDATES:
        raise ValueError("Unverified candidate")
    context, prediction = build_scenario(scenario, generated_at=generated_at)
    selection = validate_selection(mock_selection(context, prediction), context, prediction)
    interpretation = selection | {"reviewed_text": {name: [TEXT[code] for code in selection[name]]
        for name in ("factors", "missing_information", "contradictions", "uncertainty", "measurement_suggestions")}}
    return {"version": "hydration-context-comparison-v2", "scenario": scenario, "synthetic": True,
        "provenance": {"mode": "mock", "provider": None, "model": None,
            "candidate_model": candidate_model, "candidate_tier": "Standard", "model_identity_verified": False,
            "live_dispatch_enabled": False, "interpretation_origin": "local_rules_and_reviewed_text"},
        "provider_observations": {"latency_ms": None, "input_tokens": None, "output_tokens": None, "billed_cost_usd": None},
        "systems": {"A": {"prediction": deepcopy(prediction), "interpretation": None},
                    "B": {"prediction": None, "interpretation": deepcopy(interpretation)},
                    "C": {"prediction": deepcopy(prediction), "interpretation": deepcopy(interpretation)}},
        "limitations": ["Mock fixture checks do not measure Meta model quality.", "Context does not change numerical forecasts.",
                        "Future candidate identity, tier, terms, access and prices require verification before separately approved live use."]}


# Handwritten expected software labels, independent of the rule-selection function.
EXPECTED = {
    "complete": {"abstain": False, "contradictions": [], "missing": ["calibration_measurements", "measurement_error_bounds", "intake_completeness", "electrolyte_composition"]},
    "missing_measurements": {"abstain": True, "contradictions": [], "missing": ["environmental_context", "calibration_measurements", "measurement_error_bounds", "intake_completeness", "electrolyte_composition"]},
    "contradictory_mass": {"abstain": True, "contradictions": ["negative_mass_balance"], "missing": ["intake_completeness", "electrolyte_composition"]},
    "changing_conditions": {"abstain": True, "contradictions": ["incompatible_conditions"], "missing": ["intake_completeness", "electrolyte_composition"]},
    "biometrics_and_supplements": {"abstain": False, "contradictions": [], "missing": ["calibration_measurements", "measurement_error_bounds", "intake_completeness", "electrolyte_composition"]},
}


# Allowed factors and required uncertainty are also labeled independently.
EXPECTED["complete"].update(factors=["workout_duration", "environment_reported", "intake_logged"],
    uncertainty=["synthetic_evidence_only", "not_daily_requirement", "environment_context_not_numeric_effect"],
    suggestions=["comparable_dry_weighing", "record_intake_urine", "record_error_bounds"])
EXPECTED["missing_measurements"].update(factors=[],
    uncertainty=["synthetic_evidence_only", "not_daily_requirement", "insufficient_measurements"],
    suggestions=["record_environment", "comparable_dry_weighing", "record_intake_urine", "record_error_bounds"])
EXPECTED["contradictory_mass"].update(factors=["workout_duration", "environment_reported", "personal_calibration", "intake_logged"],
    uncertainty=["synthetic_evidence_only", "not_daily_requirement", "environment_context_not_numeric_effect", "insufficient_measurements"],
    suggestions=["review_inconsistent_measurement"])
EXPECTED["changing_conditions"].update(factors=["workout_duration", "environment_reported", "personal_calibration", "intake_logged"],
    uncertainty=["synthetic_evidence_only", "not_daily_requirement", "environment_context_not_numeric_effect", "insufficient_measurements"],
    suggestions=["compare_conditions"])
EXPECTED["biometrics_and_supplements"].update(factors=["workout_duration", "environment_reported", "intake_logged", "thirst_reported", "heart_rate_context", "supplement_context"],
    uncertainty=["synthetic_evidence_only", "not_daily_requirement", "environment_context_not_numeric_effect", "biometrics_not_dehydration", "supplements_no_automatic_adjustment"],
    suggestions=["comparable_dry_weighing", "record_intake_urine", "record_error_bounds"])


def score_selection(selection: dict, expected: dict) -> dict:
    """Score enum selections against hand labels; not free-text scientific claims."""
    names = {"factors": "factors", "missing_information": "missing", "contradictions": "contradictions",
             "uncertainty": "uncertainty", "measurement_suggestions": "suggestions"}
    unsupported = sum(len(set(selection[name]) - set(expected[label])) for name, label in names.items())
    count = sum(len(selection[name]) for name in names)
    return {"unsupported_claims": unsupported, "selection_count": count,
            "uncertainty_complete": set(selection["uncertainty"]) == set(expected["uncertainty"])}


def benchmark_context() -> dict:
    rows = []
    for candidate in CANDIDATES:
        for scenario in SCENARIOS:
            result = compare_context(scenario, candidate)
            interpretation = result["systems"]["B"]["interpretation"]
            expected = EXPECTED[scenario]
            score = score_selection(interpretation, expected)
            rows.append({"candidate": candidate, "scenario": scenario, **score,
                "abstention_correct": interpretation["numerical_abstention"] == expected["abstain"],
                "contradictions_correct": set(interpretation["contradictions"]) == set(expected["contradictions"]),
                "missing_information_correct": set(interpretation["missing_information"]) == set(expected["missing"]),
                "hybrid_numerical_equal": result["systems"]["A"]["prediction"] == result["systems"]["C"]["prediction"],
                "explanation_consistent": result["systems"]["B"]["interpretation"] == result["systems"]["C"]["interpretation"],
                "provider_observations": result["provider_observations"]})
    selections = sum(row["selection_count"] for row in rows)
    unsupported = sum(row["unsupported_claims"] for row in rows)
    metrics = {"case_count": len(rows), "unsupported_claims": unsupported,
        "enum_groundedness_fraction": 1 - unsupported / selections if selections else None,
        "uncertainty_communication_fraction": sum(r["uncertainty_complete"] for r in rows) / len(rows),
        "groundedness_scope": "enum validator and reviewed text only; not measured model groundedness",
        "appropriate_abstention_fraction": sum(r["abstention_correct"] for r in rows) / len(rows),
        "contradiction_detection_fraction": sum(r["contradictions_correct"] for r in rows) / len(rows),
        "missing_information_fraction": sum(r["missing_information_correct"] for r in rows) / len(rows),
        "explanation_consistency_fraction": sum(r["explanation_consistent"] for r in rows) / len(rows)}
    return {"version": "hydration-context-benchmark-v2", "evidence_kind": "hand_labeled_synthetic_mock_cases",
        "real_meta_observations": 0, "numerical_improvement_claimed": False, "rows": rows,
        "systems": {"A": {"contextual_metrics": None, "numerical_metrics": None, "note": "Numerical evaluation remains in separate real-study reports."},
                    "B": {"contextual_metrics": metrics, "numerical_metrics": None},
                    "C": {"contextual_metrics": deepcopy(metrics), "numerical_metrics": None,
                          "numerical_equal_to_A": all(r["hybrid_numerical_equal"] for r in rows)}},
        "limitations": ["No ranking of Spark and Wonder is possible from shared local mocks.",
                        "No provider latency, token usage or billed cost was observed.",
                        "Handwritten fixture labels are not physiological ground truth."]}


def install_context_v2_routes(app) -> None:
    @app.post("/v2/hydration-context-comparison")
    def comparison(payload: ComparisonInput):
        return compare_context(payload.scenario, payload.candidate_model)

    @app.post("/v2/workout-forecasts")
    def workout(payload: WorkoutForecastInput):
        now = datetime.now(timezone.utc)
        try:
            if payload.mode == "personal":
                from ai.forecasting.longitudinal import predict_longitudinal
                result = predict_longitudinal(payload.exercise.engine() if payload.exercise else None,
                    tuple(sample.engine() for sample in payload.samples), generated_at=now)
                comparison = None
            else:
                comparison = compare_context("complete", generated_at=now)
                result = comparison["systems"]["A"]["prediction"]
        except CalculationError:
            raise HTTPException(422, "invalid_request") from None
        return jsonable_encoder(result | {"generated_at": now, "timezone": payload.timezone, "mode": payload.mode,
            "mock_explanation": None, "context_comparison": comparison,
            "explanation_policy": "Meta_may_explain_reviewed_results_only_no_numeric_recalculation"})


if __name__ == "__main__":
    print(json.dumps(benchmark_context(), indent=2, sort_keys=True, allow_nan=False))
