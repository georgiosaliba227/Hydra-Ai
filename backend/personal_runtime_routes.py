"""Explicit v3 predictor wiring; callers cannot select engines or send fit state."""
from datetime import datetime, timezone
from collections.abc import Callable
from statistics import median
from fastapi import FastAPI

from ai.hydration.personal_forecast import Exercise, SweatSample
from ai.hydration.models import BeverageLog
from .hydration_analysis import install_hydration_analysis_routes
from .wonder_analysis_routes import install_wonder_analysis_routes
from .workout_forecasts import WorkoutForecastInput, install_workout_forecast_routes

NUMERICAL_CONTRACT = "personal-runtime-api-v3"
ANALYSIS_VERSION = "hydration-analysis-v3"


def predict_runtime(exercise: Exercise | None, samples: tuple[SweatSample, ...], *, generated_at: datetime) -> dict:
    # The dependency is loaded only for an explicit personal v3 request. There is
    # no automatic fallback to another engine if runtime loading/calculation fails.
    from ai.forecasting.personal_runtime import predict_personal_runtime
    return predict_personal_runtime(exercise, samples, generated_at=generated_at)


def descriptive_workout_comparison(payload: WorkoutForecastInput, generated_at: datetime) -> dict | None:
    """Earlier supplied activity summaries only; does not run either predictor."""
    if payload.mode != "personal" or payload.exercise is None:
        return None
    exercise = payload.exercise
    start = exercise.starts_at.astimezone(timezone.utc)
    current = generated_at.astimezone(timezone.utc)
    previous = [sample for sample in payload.samples if sample.conditions.activity == exercise.conditions.activity
                and sample.observed_at.astimezone(timezone.utc) < min(start, current)]

    def typical(values: list[float]) -> int | None:
        return round(median(values)) if values else None

    duration = typical([sample.measurement.duration_minutes for sample in previous if sample.measurement.duration_minutes is not None])
    return {"planned_duration_minutes": max(1, round(exercise.duration_minutes)),
            "typical_duration_minutes": max(1, duration) if duration is not None else None,
            "planned_temperature_c": round(exercise.conditions.temperature_c) if exercise.conditions.temperature_c is not None else None,
            "typical_temperature_c": typical([sample.conditions.temperature_c for sample in previous if sample.conditions.temperature_c is not None]),
            "planned_humidity_percent": round(exercise.conditions.humidity_percent) if exercise.conditions.humidity_percent is not None else None,
            "typical_humidity_percent": typical([sample.conditions.humidity_percent for sample in previous if sample.conditions.humidity_percent is not None])}


def install_personal_runtime_routes(app: FastAPI, to_engine: Callable[[dict], BeverageLog], *,
                                    enabled: bool, error_response: Callable) -> None:
    install_workout_forecast_routes(app, path="/v3/workout-forecasts", personal_predictor=predict_runtime)
    install_hydration_analysis_routes(app, to_engine, error_response=error_response, path="/v3/hydration-analysis",
        personal_predictor=predict_runtime, version=ANALYSIS_VERSION, embedded_workout_wonder=False)
    install_wonder_analysis_routes(app, to_engine, enabled=enabled, error_response=error_response,
        path="/v3/wonder/analysis", personal_predictor=predict_runtime, analysis_version=ANALYSIS_VERSION,
        embedded_workout_wonder=False, comparison_builder=descriptive_workout_comparison,
        project_forecast=True, numerical_contract=NUMERICAL_CONTRACT)
