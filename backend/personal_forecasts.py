"""Local-only forecast boundary; never imports a Meta provider or exports wearable records."""
from datetime import date, datetime, timezone
import re
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from ai.hydration.models import CalculationError, WorkoutMeasurement
from ai.hydration.personal_forecast import (Conditions, Exercise, MeasurementErrors, SweatSample, forecast_personal)

Number = Annotated[float, Field(strict=True, ge=0, le=50000, allow_inf_nan=False)]
Positive = Annotated[float, Field(strict=True, gt=0, le=1440, allow_inf_nan=False)]


class Wire(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConditionsInput(Wire):
    activity: Literal["running", "cycling", "walking", "strength", "other"]
    intensity: Literal["low", "moderate", "high"] | None = None
    temperature_c: Annotated[float, Field(strict=True, ge=-60, le=60, allow_inf_nan=False)] | None = None
    humidity_percent: Annotated[float, Field(strict=True, ge=0, le=100, allow_inf_nan=False)] | None = None


class ErrorsInput(Wire):
    pre_mass_kg: Number
    post_mass_kg: Number
    consumed_ml: Number
    urine_ml: Number
    duration_minutes: Number
    provenance: list[Annotated[str, Field(strict=True, min_length=1, max_length=100)]] = Field(min_length=1, max_length=4)


class MeasurementInput(Wire):
    pre_mass_kg: Annotated[float, Field(strict=True, gt=0, le=500, allow_inf_nan=False)] | None = None
    post_mass_kg: Annotated[float, Field(strict=True, gt=0, le=500, allow_inf_nan=False)] | None = None
    consumed_ml: Number | None = None
    urine_ml: Number | None = None
    duration_minutes: Positive | None = None
    protocol_confirmed: StrictBool
    provenance: list[Annotated[str, Field(strict=True, min_length=1, max_length=100)]] = Field(min_length=1, max_length=4)


class InstantInput(Wire):
    @field_validator("observed_at", "starts_at", mode="before", check_fields=False)
    @classmethod
    def explicit_instant(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", value):
            raise ValueError("Explicit timestamp offset required")
        return value


class SampleInput(InstantInput):
    event_id: UUID
    observed_at: datetime
    conditions: ConditionsInput
    measurement: MeasurementInput
    errors: ErrorsInput | None = None

    def engine(self) -> SweatSample:
        measurement = self.measurement.model_dump() | {"provenance": tuple(self.measurement.provenance)}
        errors = None if self.errors is None else MeasurementErrors(**(self.errors.model_dump() | {"provenance": tuple(self.errors.provenance)}))
        return SweatSample(self.event_id, self.observed_at, Conditions(**self.conditions.model_dump()),
                           WorkoutMeasurement(**measurement), errors)


class ExerciseInput(InstantInput):
    event_id: UUID
    starts_at: datetime
    duration_minutes: Positive
    conditions: ConditionsInput
    comparable_conditions_confirmed: StrictBool = False
    duration_source: Literal["manual", "wearable_aggregate"] = "manual"
    feedback: Literal["comfortable", "thirst_reported", "discomfort_reported"] | None = None
    actual: SampleInput | None = None

    @model_validator(mode="after")
    def no_wearable_export_yet(self):
        if self.duration_source == "wearable_aggregate":
            raise ValueError("Wearable export awaits separate policy review; use manual duration")
        return self

    def engine(self) -> Exercise:
        data = self.model_dump(exclude={"conditions", "actual"})
        return Exercise(**data, conditions=Conditions(**self.conditions.model_dump()),
                        actual=self.actual.engine() if self.actual is not None else None)


class ForecastInput(Wire):
    date: date
    timezone: Annotated[str, Field(strict=True, min_length=1, max_length=128)]
    history_days: Annotated[int, Field(strict=True, ge=1, le=90)] = 7
    calibration_processing_consent: StrictBool = False
    exercise: ExerciseInput | None = None
    samples: list[SampleInput] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def consent_to_calibration_processing(self):
        if (self.samples or (self.exercise is not None and self.exercise.actual is not None)) and not self.calibration_processing_consent:
            raise ValueError("Explicit consent for calibration processing required")
        return self

    @field_validator("date")
    @classmethod
    def supported_date(cls, value):
        if not 2000 <= value.year <= 2100:
            raise ValueError("Unsupported forecast date")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("Invalid timezone") from None
        return value


def install_forecast_routes(app, to_engine) -> None:
    @app.post("/v1/forecasts")
    def personal_forecast(payload: ForecastInput, request: Request):
        logs = tuple(to_engine(record) for record in request.app.state.repository.list_all("local-demo"))
        try:
            result = forecast_personal(logs, payload.date, payload.timezone, generated_at=datetime.now(timezone.utc),
                history_days=payload.history_days, exercise=payload.exercise.engine() if payload.exercise else None,
                samples=tuple(sample.engine() for sample in payload.samples))
        except CalculationError:
            raise HTTPException(422, "invalid_request") from None
        return jsonable_encoder(result)
