"""Local model boundary: manual calibration or a server-owned synthetic fixture only."""
from datetime import datetime, timezone
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import Field, StrictBool, field_validator, model_validator

from ai.forecasting.predict import predict_workout
from ai.hydration.models import CalculationError
from .personal_forecasts import ExerciseInput, SampleInput, Wire


class WorkoutForecastInput(Wire):
    mode: Literal["personal", "synthetic_demo"] = "personal"
    timezone: Annotated[str, Field(strict=True, min_length=1, max_length=128)]
    exercise: ExerciseInput | None = None
    samples: list[SampleInput] = Field(default_factory=list, max_length=32)
    calibration_processing_consent: StrictBool = False

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("Invalid timezone") from None
        return value

    @model_validator(mode="after")
    def separate_measurements_from_demo(self):
        if self.mode == "synthetic_demo":
            if self.exercise is not None or self.samples or self.calibration_processing_consent:
                raise ValueError("Synthetic demonstration accepts no personal inputs")
        elif (self.samples or (self.exercise is not None and self.exercise.actual is not None)) and not self.calibration_processing_consent:
            raise ValueError("Explicit calibration processing consent required")
        return self


def install_workout_forecast_routes(app) -> None:
    @app.post("/v1/workout-forecasts")
    def workout_forecast(payload: WorkoutForecastInput):
        generated_at = datetime.now(timezone.utc)
        try:
            result = predict_workout(
                payload.exercise.engine() if payload.exercise is not None else None,
                tuple(sample.engine() for sample in payload.samples),
                generated_at=generated_at, mode=payload.mode,
            )
        except CalculationError:
            raise HTTPException(422, "invalid_request") from None
        # Never use the configured live service here. Real measurements never reach
        # even the mock explanation adapter; synthetic fixture explanation is local.
        explanation = None
        if payload.mode == "synthetic_demo":
            from .hydration_intelligence import MockHydrationIntelligence, SyntheticContext
            factors = result["input_factors"]
            context = SyntheticContext(
                synthetic=True, disclosure_consent=True, beverage_total_ml=0.0,
                workout_minutes=int(factors["duration_minutes"]),
                workout_intensity=factors.get("intensity", "missing"),
                temperature_c=factors.get("temperature_c"),
                humidity_percent=factors.get("humidity_percent"),
                estimated_sweat_loss_ml=result["value_ml"],
            )
            explanation = MockHydrationIntelligence().explain(context)
        return jsonable_encoder(result | {
            "generated_at": generated_at, "timezone": payload.timezone, "mode": payload.mode,
            "mock_explanation": explanation,
            "explanation_policy": "Meta_may_explain_reviewed_results_only_no_numeric_recalculation",
        })
