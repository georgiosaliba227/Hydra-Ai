"""No network or ML-library dependency; research artifacts never prescribe intake."""
from datetime import datetime
import json
import math
from pathlib import Path
from statistics import median
import struct

from ai.hydration.models import CalculationError, aware
from ai.hydration.personal_forecast import Exercise, SweatSample, exercise_loss
from ai.hydration.workout import estimate_workout_loss

ARTIFACT_DIR = Path(__file__).with_name("artifacts")
DEMO_FACTORS = {"duration_minutes": 60.0, "pre_mass_kg": 70.0,
                "age_years": 30.0, "temperature_c": 24.0,
                "humidity_percent": 50.0, "intensity": "moderate"}
BASE_LIMITATIONS = ["Not a drinking target or daily fluid requirement.",
                    "Not clinically validated; unmeasured mass changes remain unresolved.",
                    "No dehydration diagnosis or adjustment from HR, HRV, caffeine or creatine."]


def predict_artifact(artifact: dict, features: dict) -> float:
    """Evaluate a repository-owned JSON model, never unpickle executable objects."""
    values = []
    for i, name in enumerate(artifact["features"]):
        value = features.get(name)
        if value is None:
            value = artifact["imputation"][i]
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("invalid_model_input")
        scale = artifact["scales"][i]
        center = artifact["means"][i]
        if type(scale) not in (int, float) or not math.isfinite(scale) or scale <= 0 or type(center) not in (int, float) or not math.isfinite(center):
            raise ValueError("invalid_standardization")
        values.append((value - center) / scale)
    model = artifact["model"]
    if not isinstance(model, dict):
        raise ValueError("invalid_model")
    if model["kind"] == "ridge":
        prediction = model["intercept"] + sum(c * x for c, x in zip(model["coefficients"], values, strict=True))
    elif model["kind"] == "constant_rate":
        prediction = model["rate_ml_per_minute"] * features["duration_minutes"]
    else:
        # sklearn trees convert inputs to float32 before comparisons.
        values = [struct.unpack("f", struct.pack("f", value))[0] for value in values]
        if not model.get("trees"):
            raise ValueError("missing_trees")
        def tree_value(tree):
            node = 0
            for _ in range(len(tree["left"])):
                if tree["left"][node] == -1:
                    return tree["value"][node]
                node = tree["left"][node] if values[tree["feature"][node]] <= tree["threshold"][node] else tree["right"][node]
            raise ValueError("invalid_model_tree")
        if model["kind"] == "random_forest":
            prediction = sum(tree_value(t) for t in model["trees"]) / len(model["trees"])
        elif model["kind"] == "gradient_boosting":
            prediction = model["intercept"] + model["learning_rate"] * sum(tree_value(t) for t in model["trees"])
        else:
            raise ValueError("unsupported_model")
    if not math.isfinite(prediction):
        raise ValueError("nonfinite_prediction")
    return max(0.0, float(prediction))


def predict_workout(exercise: Exercise | None, samples: tuple[SweatSample, ...] = (), *,
                    generated_at: datetime, mode: str = "personal",
                    body_mass_kg: float | None = None) -> dict:
    aware(generated_at, "generated_at")
    if mode not in ("personal", "synthetic_demo"):
        raise CalculationError("invalid_mode", "mode")
    if body_mass_kg is not None:
        raise CalculationError("unsupported_input", "body_mass_kg")
    result = {"version": "workout-forecast-v1", "status": "insufficient_data",
              "model_version": "personal-exercise-loss-v1", "quantity": "estimated_sweat_loss",
              "units": "mL", "value_ml": None, "lower_ml": None, "upper_ml": None,
              "interval_kind": "conditional_measurement_envelope",
              "data_sufficiency": "usable_comparable_measurements_required",
              "personalization_status": "cold_start", "sample_count": 0,
              "provenance": [], "input_factors": {}, "limitations": list(BASE_LIMITATIONS),
              "synthetic": mode == "synthetic_demo"}
    if mode == "synthetic_demo":
        if exercise is not None or samples:
            raise CalculationError("synthetic_requires_server_fixture", "samples")
        result.update(model_version="synthetic-workout-demo-v1", data_sufficiency="artifact_unavailable",
                      personalization_status="simulated_population_only", input_factors=dict(DEMO_FACTORS),
                      interval_kind="synthetic_participant_split_conformal")
        result["limitations"] += ["Synthetic targets; baseline covariates come from deidentified study training anchors. No physiological validation.",
                                   "Synthetic interval coverage says nothing about real-world accuracy.",
                                   "Only duration, initial body mass and age enter this model; temperature, humidity and intensity are context only."]
        try:
            artifact = json.loads((ARTIFACT_DIR / "synthetic_demo.json").read_text())
            if artifact["synthetic"] is not True or artifact["target_name"] != "simulated_sweat_loss_ml":
                raise ValueError("wrong_artifact")
            model_version = artifact["model_version"]
            provenance = artifact["provenance"]
            interval_kind = artifact["interval"]["kind"]
            if not isinstance(model_version,str) or not model_version.strip() or len(model_version)>100:
                raise ValueError("invalid_version")
            if not isinstance(provenance,list) or not 1 <= len(provenance) <= 16 or any(not isinstance(p,str) or not p.strip() or len(p)>500 for p in provenance):
                raise ValueError("invalid_provenance")
            if interval_kind not in ("participant_split_conformal", "empirical_calibration_envelope"):
                raise ValueError("invalid_interval_kind")
            value = predict_artifact(artifact, DEMO_FACTORS)
            radius = artifact["interval"]["radius_ml"]
            if type(radius) not in (int, float) or not math.isfinite(radius) or radius < 0 or not math.isfinite(value+radius):
                raise ValueError("invalid_radius")
        except (OSError, ValueError, KeyError, TypeError, IndexError, OverflowError, ZeroDivisionError, struct.error):
            return result
        result.update(status="estimated", value_ml=value, lower_ml=max(0.0, value-radius), upper_ml=value+radius,
                      data_sufficiency="synthetic_demo_only", provenance=provenance,
                      model_version=model_version, interval_kind="synthetic_" + interval_kind)
        return result
    envelope = exercise_loss(exercise, samples, generated_at=generated_at)
    result["limitations"] += envelope["uncertainty_reasons"]
    result["provenance"] = envelope["provenance"]
    if exercise is not None:
        result["input_factors"] = {"duration_minutes": exercise.duration_minutes,
                                  "activity": exercise.conditions.activity,
                                  "intensity": exercise.conditions.intensity,
                                  "temperature_c": exercise.conditions.temperature_c,
                                  "humidity_percent": exercise.conditions.humidity_percent,
                                  "feedback": exercise.feedback}
    if envelope["status"] != "estimated":
        result["missing_inputs"] = envelope["missing_inputs"]
        return result
    selected_ids = set(envelope["sample_ids"])
    selected = (exercise.actual,) if exercise.actual is not None else tuple(s for s in samples if str(s.event_id) in selected_ids)
    points = []
    for sample in selected:
        measured = estimate_workout_loss(sample.measurement)
        points.append(measured.estimated_loss_ml if exercise.actual is not None else
                      measured.sweat_rate_ml_per_hour * exercise.duration_minutes / 60)
    center = median(points)
    if not math.isfinite(center) or not envelope["lower_ml"] <= center <= envelope["upper_ml"]:
        return result
    result.update(status="estimated", value_ml=center, lower_ml=envelope["lower_ml"], upper_ml=envelope["upper_ml"],
                  sample_count=envelope["sample_count"], data_sufficiency="conditional_measurements_only",
                  personalization_status="measured_actual" if exercise.actual else "personal_measured_calibration")
    result["limitations"].append("Point is a deterministic median of comparable measured rates; the range is not a calibrated future prediction interval.")
    return result
