"""Experimental within-person ridge learning; no serving, storage or population prior.

Only measured rates from earlier comparable workouts enter a fit. A temporal
trend is an engineering candidate, not an established physiological effect.
The existing app method remains authoritative until real longitudinal evaluation.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import random
from statistics import mean, stdev
from uuid import UUID

from ai.hydration.models import CalculationError, WorkoutMeasurement, convert_time
from ai.hydration.personal_forecast import Conditions, Exercise, MeasurementErrors, SweatSample, exercise_loss
from ai.hydration.workout import estimate_workout_loss
from .longitudinal import _chronological, predict_longitudinal

ALPHAS = (.1, 1., 10.)
MIN_HISTORY = 6
VERSION = "personal-rate-ridge-research-v1"
LIMITATIONS = [
    "Research candidate only; not enabled in the app or used by Muse Wonder.",
    "A learned time trend is an engineering hypothesis, not validated physiological adaptation.",
    "Selection uses earlier within-person errors; overlapping fits are not independent validation.",
    "No population prior, weather coefficient, diagnosis, total hydration or drinking requirement.",
    "The envelope preserves measurement and past errors; it is not a calibrated prediction interval.",
]


def _fit(samples: tuple[SweatSample, ...], alpha: float) -> dict:
    origin = convert_time(samples[0].observed_at, timezone.utc, "observed_at")
    days = [(convert_time(sample.observed_at, timezone.utc, "observed_at")-origin).total_seconds()/86400 for sample in samples]
    rates = [estimate_workout_loss(sample.measurement).sweat_rate_ml_per_hour for sample in samples]
    center = mean(days)
    scale = math.sqrt(mean((day-center)**2 for day in days))
    if scale == 0:
        raise CalculationError("duplicate_completion_time", "samples")
    average = mean(rates)
    x = [(day-center)/scale for day in days]
    slope = math.fsum(value*(rate-average) for value, rate in zip(x, rates, strict=True))/(math.fsum(value*value for value in x)+alpha)
    return {"origin_utc": origin.isoformat(), "time_center_days": center, "time_scale_days": scale,
            "intercept_ml_per_hour": average, "standardized_time_slope_ml_per_hour": slope,
            "slope_ml_per_hour_per_day": slope/scale, "ridge_alpha": alpha, "training_samples": len(samples)}


def _rate(model: dict, completion: datetime) -> float:
    origin = datetime.fromisoformat(model["origin_utc"])
    day = (convert_time(completion, timezone.utc, "completion")-origin).total_seconds()/86400
    value = model["intercept_ml_per_hour"] + model["standardized_time_slope_ml_per_hour"]*(day-model["time_center_days"])/model["time_scale_days"]
    if not math.isfinite(value):
        raise CalculationError("numeric_overflow", "personal_model")
    return value


def predict_personal_research(exercise: Exercise | None, samples: tuple[SweatSample, ...] = (), *,
                              generated_at: datetime) -> dict:
    """Fit and compare a ridge candidate; never alter the application's forecast.

    Hyperparameters use rolling earlier-only outcomes. Final selection requires
    paired gain exceeding one empirical standard error, with at least three
    folds. This is a fixed engineering heuristic, not a significance test.
    """
    ordered = _chronological(samples, generated_at)
    baseline = predict_longitudinal(exercise, ordered, generated_at=generated_at)
    result = {"version": VERSION, "research_only": True, "application_promotion": "not_enabled",
              "selected_method": "existing_personal_baseline", "candidate": None,
              "selected_estimate": {key: baseline[key] for key in ("status", "value_ml", "lower_ml", "upper_ml")},
              "interval_kind": "historical_measurement_and_error_envelope", "nominal_coverage": None,
              "validation": None, "reason": "insufficient_comparable_history", "limitations": list(LIMITATIONS)}
    if baseline["status"] != "estimated" or exercise is None or exercise.actual is not None:
        return result
    envelope = exercise_loss(exercise, ordered, generated_at=generated_at)
    ids = set(envelope["sample_ids"])
    selected = tuple(sample for sample in ordered if str(sample.event_id) in ids)
    instants = [convert_time(sample.observed_at, timezone.utc, "observed_at") for sample in selected]
    if len(set(instants)) != len(instants):
        raise CalculationError("duplicate_completion_time", "samples")
    if len(selected) < MIN_HISTORY:
        return result
    try:
        completion = convert_time(exercise.starts_at, timezone.utc, "starts_at")+timedelta(minutes=exercise.duration_minutes)
    except (OverflowError, ValueError):
        raise CalculationError("invalid_time", "starts_at") from None
    maximum_gap = max(later-earlier for earlier, later in zip(instants, instants[1:]))
    if completion-instants[-1] > maximum_gap:
        result["reason"] = "beyond_observed_session_spacing"
        return result

    predictions = []
    for index, target_sample in enumerate(selected):
        duration = target_sample.measurement.duration_minutes
        at = convert_time(target_sample.observed_at, timezone.utc, "observed_at")-timedelta(minutes=duration)
        prior = tuple(sample for sample in selected[:index]
                      if convert_time(sample.observed_at, timezone.utc, "observed_at") < at)
        if len(prior) < 3:
            continue
        plan = Exercise(target_sample.event_id, at, duration, target_sample.conditions, True)
        previous = predict_longitudinal(plan, prior, generated_at=at)
        if previous["status"] != "estimated":
            continue
        target = estimate_workout_loss(target_sample.measurement).estimated_loss_ml
        candidate_points = {str(alpha): _rate(_fit(prior, alpha), target_sample.observed_at)*duration/60 for alpha in ALPHAS}
        predictions.append({"outcome_index": index, "training_samples": len(prior),
                            "target_ml": target, "baseline_ml": previous["value_ml"], "candidates_ml": candidate_points,
                            "duration_minutes": duration})
    if len(predictions) < 3:
        result["reason"] = "insufficient_chronological_validation"
        return result
    comparison = {}
    for alpha in ALPHAS:
        gains = [abs(row["baseline_ml"]-row["target_ml"])-abs(row["candidates_ml"][str(alpha)]-row["target_ml"]) for row in predictions]
        comparison[str(alpha)] = {"mae_ml": mean(abs(row["candidates_ml"][str(alpha)]-row["target_ml"]) for row in predictions),
                                  "paired_gain_ml": mean(gains), "gain_standard_error_ml": stdev(gains)/math.sqrt(len(gains))}
    # A larger alpha wins exact ties, preferring stronger shrinkage toward no trend.
    alpha = min(ALPHAS, key=lambda value: (comparison[str(value)]["mae_ml"], -value))
    model = _fit(selected, alpha)
    model["forecast_completion_utc"] = completion.isoformat()
    point = _rate(model, completion)*exercise.duration_minutes/60
    model["value_ml"] = point if point >= 0 else None
    chosen = comparison[str(alpha)]
    result.update(candidate=model, reason="baseline_retained_after_validation",
                  validation={"folds": len(predictions), "predictions": predictions, "comparison": comparison,
                              "baseline_mae_ml": mean(abs(row["baseline_ml"]-row["target_ml"]) for row in predictions),
                              "test_set_used": False})
    if point < 0:
        result["reason"] = "candidate_outside_nonnegative_loss_domain"
        return result
    if not chosen["paired_gain_ml"] > max(chosen["gain_standard_error_ml"], 1e-8):
        return result
    # Propagate historical one-step error as a rate to the planned duration; never
    # narrow the baseline envelope or treat a sample count as a coverage guarantee.
    radius = max(abs(row["candidates_ml"][str(alpha)]-row["target_ml"])*60/row["duration_minutes"] for row in predictions)*exercise.duration_minutes/60
    lower, upper = min(baseline["lower_ml"], max(0., point-radius)), max(baseline["upper_ml"], point+radius)
    if not all(math.isfinite(value) for value in (point, lower, upper)):
        result["reason"] = "nonfinite_candidate"
        return result
    result.update(selected_method="regularized_time_rate", reason="earlier_error_comparison_only",
                  selected_estimate={"status": "estimated", "value_ml": point, "lower_ml": lower, "upper_ml": upper})
    return result


def evaluate_synthetic_personal_learning(seed: int = 20261102) -> dict:
    """Fixed invented trajectories test training behavior, not human accuracy."""
    rng = random.Random(seed)
    start = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    scenarios = {}
    conditions = Conditions("running", "moderate", 22., 55.)
    for scenario in ("stable", "gradual_change", "abrupt_change", "condition_shift"):
        rows = []
        for participant in range(10):
            history = []
            for index in range(12):
                rate = 300.+20*participant
                if scenario == "gradual_change":
                    rate += 30*index
                elif scenario in ("abrupt_change", "condition_shift") and index >= 6:
                    rate += 200.
                rate += rng.uniform(-10., 10.)
                context = replace(conditions, temperature_c=30.) if scenario == "condition_shift" and index >= 6 else conditions
                sample = SweatSample(UUID(int=participant*100+index+1), start+timedelta(days=index*3), context,
                    WorkoutMeasurement(70., 70.-rate/1000, 0., 0., 60., True, ("invented_research_scenario",)),
                    MeasurementErrors(.01, .01, 0., 0., 0., ("invented_error_bound",)))
                at = sample.observed_at-timedelta(hours=1)
                plan = Exercise(sample.event_id, at, 60., context, True)
                before = predict_longitudinal(plan, tuple(history), generated_at=at)
                research = predict_personal_research(plan, tuple(history), generated_at=at)
                selected = research["selected_estimate"]
                target = estimate_workout_loss(sample.measurement).estimated_loss_ml
                if before["status"] == "estimated":
                    rows.append({"participant": participant, "step": index, "target_ml": target,
                                 "baseline_ml": before["value_ml"], "selected_ml": selected["value_ml"],
                                 "lower_ml": selected["lower_ml"], "upper_ml": selected["upper_ml"],
                                 "method": research["selected_method"]})
                history.append(sample)
        scores = {}
        for name in ("baseline", "selected"):
            errors = [row[name+"_ml"]-row["target_ml"] for row in rows]
            scores[name] = {"n": len(errors), "mae_ml": mean(abs(error) for error in errors),
                            "rmse_ml": math.sqrt(mean(error*error for error in errors)), "bias_ml": mean(errors)}
        scenarios[scenario] = {"systems": scores, "interval_inclusion": mean(row["lower_ml"] <= row["target_ml"] <= row["upper_ml"] for row in rows),
                               "ridge_selected_predictions": sum(row["method"] == "regularized_time_rate" for row in rows)}
    return {"version": VERSION, "seed": seed, "evidence_origin": "synthetic_software_scenarios",
            "real_world_improvement": False, "application_promotion": "not_enabled", "scenarios": scenarios,
            "assumptions": ["Invented 300+20*participant mL/h, 60-minute workouts every three days.",
                            "Invented gradual +30 mL/h per workout or +200 mL/h after six workouts.",
                            "Uniform +/-10 mL noise and +/-10 g scale bounds are software assumptions.",
                            "Condition shift is a label, not an attributed temperature effect."], "limitations": list(LIMITATIONS)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate_synthetic_personal_learning()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False)+"\n")
    print(json.dumps(report["scenarios"], sort_keys=True))


if __name__ == "__main__":
    main()
