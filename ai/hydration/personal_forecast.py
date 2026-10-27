"""Conditional exercise-loss envelopes, not daily requirements or drinking targets."""
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone as utc
from fractions import Fraction
from math import isfinite, nextafter, inf
from uuid import UUID

from .daily import summarize_day
from .forecast import calculate_forecast
from .models import (BeverageLog, CalculationError, WorkoutMeasurement, aware, exact,
                     number, provenance, representable, text, zone, convert_time)
from .workout import estimate_workout_loss

METHOD = "personal-exercise-loss-v1"


@dataclass(frozen=True)
class Conditions:
    activity: str
    intensity: str | None
    temperature_c: float | None
    humidity_percent: float | None

    def __post_init__(self) -> None:
        text(self.activity, "activity")
        if self.intensity not in (None, "low", "moderate", "high"):
            raise CalculationError("invalid_intensity", "intensity")
        if self.temperature_c is not None:
            # Signed temperatures, unlike the nonnegative accounting helper.
            if type(self.temperature_c) not in (int, float) or not -60 <= self.temperature_c <= 60:
                raise CalculationError("invalid_temperature", "temperature_c")
        if self.humidity_percent is not None:
            number(self.humidity_percent, "humidity_percent")
            if self.humidity_percent > 100:
                raise CalculationError("invalid_humidity", "humidity_percent")

    @property
    def complete(self) -> bool:
        return all(value is not None for value in (self.intensity, self.temperature_c, self.humidity_percent))


@dataclass(frozen=True)
class MeasurementErrors:
    """Absolute error bounds established independently, never inferred from samples."""
    pre_mass_kg: float
    post_mass_kg: float
    consumed_ml: float
    urine_ml: float
    duration_minutes: float
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("pre_mass_kg", "post_mass_kg", "consumed_ml", "urine_ml", "duration_minutes"):
            number(getattr(self, name), "error_" + name)
        provenance(self.provenance)


@dataclass(frozen=True)
class SweatSample:
    event_id: UUID
    observed_at: datetime
    conditions: Conditions
    measurement: WorkoutMeasurement
    errors: MeasurementErrors | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, UUID):
            raise CalculationError("invalid_id", "event_id")
        aware(self.observed_at, "observed_at")
        if not isinstance(self.conditions, Conditions) or not isinstance(self.measurement, WorkoutMeasurement):
            raise CalculationError("invalid_sample", "measurement")
        if self.errors is not None and not isinstance(self.errors, MeasurementErrors):
            raise CalculationError("invalid_sample", "errors")


@dataclass(frozen=True)
class Exercise:
    event_id: UUID
    starts_at: datetime
    duration_minutes: float
    conditions: Conditions
    comparable_conditions_confirmed: bool
    duration_source: str = "manual"
    feedback: str | None = None
    actual: SweatSample | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, UUID):
            raise CalculationError("invalid_id", "event_id")
        aware(self.starts_at, "starts_at")
        number(self.duration_minutes, "duration_minutes", positive=True)
        if not isinstance(self.conditions, Conditions):
            raise CalculationError("invalid_conditions", "conditions")
        if type(self.comparable_conditions_confirmed) is not bool:
            raise CalculationError("invalid_boolean", "comparable_conditions_confirmed")
        if self.duration_source not in ("manual", "wearable_aggregate"):
            raise CalculationError("invalid_source", "duration_source")
        if self.feedback not in (None, "comfortable", "thirst_reported", "discomfort_reported"):
            raise CalculationError("invalid_feedback", "feedback")
        if self.actual is not None and (not isinstance(self.actual, SweatSample) or self.actual.event_id != self.event_id):
            raise CalculationError("event_mismatch", "actual")


def _interval(sample: SweatSample) -> tuple[Fraction, Fraction, Fraction, Fraction] | None:
    """Exact decimal interval propagation; systematic unknown errors remain a limitation."""
    result = estimate_workout_loss(sample.measurement)
    if result.status != "estimated" or sample.errors is None:
        return None
    m, e = sample.measurement, sample.errors
    duration = exact(m.duration_minutes)
    error_duration = exact(e.duration_minutes)
    if duration <= error_duration:
        return None
    center = (exact(m.pre_mass_kg) - exact(m.post_mass_kg)) * 1000 + exact(m.consumed_ml) - exact(m.urine_ml)
    error = (exact(e.pre_mass_kg) + exact(e.post_mass_kg)) * 1000 + exact(e.consumed_ml) + exact(e.urine_ml)
    lower, upper = max(Fraction(0), center - error), center + error
    return lower, upper, lower * 60 / (duration + error_duration), upper * 60 / (duration - error_duration)


def _outward(value: Fraction, *, upper: bool) -> float:
    result = representable(value, "range_ml")
    rounded = Fraction.from_float(result)
    if (upper and rounded < value) or (not upper and rounded > value):
        result = nextafter(result, inf if upper else -inf)
    if not isfinite(result):
        raise CalculationError("numeric_overflow", "range_ml")
    return result


def exercise_loss(exercise: Exercise | None, samples: tuple[SweatSample, ...], *, generated_at: datetime) -> dict:
    aware(generated_at, "generated_at")
    seen = set()
    for sample in samples:
        if not isinstance(sample, SweatSample):
            raise CalculationError("invalid_sample", "samples")
        if sample.event_id in seen:
            raise CalculationError("duplicate_event", "samples")
        seen.add(sample.event_id)
        if convert_time(sample.observed_at, utc.utc, "observed_at") > convert_time(generated_at, utc.utc, "generated_at"):
            raise CalculationError("future_measurement", "observed_at")
    result = {"status": "insufficient_data", "lower_ml": None, "upper_ml": None,
              "quantity": "estimated_sweat_loss", "range_type": "conditional_measurement_envelope",
              "sample_count": 0, "sample_ids": [], "provenance": [], "excluded_samples": [],
              "missing_inputs": [], "method_version": METHOD,
              "assumptions": ["one_kg_mass_change_approximates_1000_ml_water", "not_a_drinking_target"],
              "uncertainty_reasons": ["not_a_calibrated_future_prediction_interval", "unmeasured_mass_changes_not_resolved", "lower_bound_clipped_to_nonnegative_physical_loss"]}
    if exercise is None:
        result["missing_inputs"] = ["exercise"]
        return result
    result["duration_source"] = exercise.duration_source
    result["feedback"] = exercise.feedback
    if exercise.feedback is not None:
        result["uncertainty_reasons"].append("feedback_is_context_only_no_numeric_adjustment")
    if exercise.actual is not None:
        actual = exercise.actual
        observed = convert_time(actual.observed_at, utc.utc, "observed_at")
        started = convert_time(exercise.starts_at, utc.utc, "starts_at")
        if observed > convert_time(generated_at, utc.utc, "generated_at") or observed < started:
            raise CalculationError("invalid_actual_time", "actual")
        if actual.measurement.duration_minutes is not None and actual.errors is not None:
            elapsed = observed - started
            elapsed_minutes = (Fraction(elapsed.days * 86400 + elapsed.seconds)
                               + Fraction(elapsed.microseconds, 1_000_000)) / 60
            # A completed measurement cannot precede even the shortest duration
            # allowed by its independently supplied error bounds.
            minimum_duration = exact(actual.measurement.duration_minutes) - exact(actual.errors.duration_minutes)
            if minimum_duration > elapsed_minutes:
                raise CalculationError("invalid_actual_duration", "actual")
        if actual.event_id in seen:
            raise CalculationError("duplicate_event", "actual")
        selected = [actual]
        result["basis"] = "actual_replaces_planned"
    else:
        result["basis"] = "historical_comparable_rate_projection"
        if convert_time(exercise.starts_at, utc.utc, "starts_at") < convert_time(generated_at, utc.utc, "generated_at"):
            result["missing_inputs"] = ["actual_measurement_for_started_exercise"]
            return result
        if not exercise.comparable_conditions_confirmed or not exercise.conditions.complete:
            result["missing_inputs"] = ["complete_environment_and_intensity", "confirmed_comparable_conditions"]
            return result
        selected = []
        for sample in samples:
            if sample.event_id == exercise.event_id:
                raise CalculationError("duplicate_event", "exercise")
            if sample.conditions != exercise.conditions or not sample.conditions.complete:
                result["excluded_samples"].append({"event_id": str(sample.event_id), "reason": "conditions_differ_or_missing"})
            else:
                selected.append(sample)
        result["assumptions"].append("same_rate_with_confirmed_comparable_environment_intensity_equipment_and_acclimatization")
    intervals = []
    for sample in selected:
        interval = _interval(sample)
        if interval is None:
            result["excluded_samples"].append({"event_id": str(sample.event_id), "reason": "missing_protocol_measurements_or_error_bounds"})
            continue
        if exercise.actual is not None:
            lower, upper = interval[:2]
        else:
            lower, upper = (rate * exact(exercise.duration_minutes) / 60 for rate in interval[2:])
        intervals.append((lower, upper))
        result["sample_ids"].append(str(sample.event_id))
        result["provenance"].extend(sample.measurement.provenance + sample.errors.provenance)
    if not intervals:
        result["missing_inputs"] = ["usable_measurements_with_error_bounds"]
        return result
    try:
        lower = _outward(min(value[0] for value in intervals), upper=False)
        upper = _outward(max(value[1] for value in intervals), upper=True)
    except CalculationError as error:
        result["uncertainty_reasons"].append(error.code)
        return result
    result.update(status="estimated", lower_ml=lower, upper_ml=upper, sample_count=len(intervals))
    result["provenance"] = list(dict.fromkeys(result["provenance"]))
    result["uncertainty_reasons"].append("single_observation" if len(intervals) == 1 else "observed_envelope_does_not_cover_all_future_variation")
    return result


def forecast_personal(logs: tuple[BeverageLog, ...], local_date: date, timezone: str, *,
                      generated_at: datetime, history_days: int = 7, exercise: Exercise | None = None,
                      samples: tuple[SweatSample, ...] = ()) -> dict:
    """Pure local calculation; no network, keys, persistence, or model-authored arithmetic."""
    aware(generated_at, "generated_at")
    if type(history_days) is not int or not 1 <= history_days <= 90:
        raise CalculationError("invalid_history_window", "history_days")
    local_zone = zone(timezone)
    if type(local_date) is not date:
        raise CalculationError("invalid_date", "local_date")
    try:
        history_start = local_date - timedelta(days=history_days)
    except OverflowError:
        raise CalculationError("invalid_date", "local_date") from None
    if any(convert_time(log.consumed_at, utc.utc, "consumed_at") > convert_time(generated_at, utc.utc, "generated_at") for log in logs):
        raise CalculationError("future_log", "consumed_at")
    summary = summarize_day(logs, local_date, timezone)
    if exercise is not None and convert_time(exercise.starts_at, local_zone, "starts_at").date() != local_date:
        raise CalculationError("date_mismatch", "exercise")
    # Empty/partially logged days do not measure actual absence of intake.
    dates = sorted({convert_time(log.consumed_at, local_zone, "consumed_at").date() for log in logs
                    if history_start <= convert_time(log.consumed_at, local_zone, "consumed_at").date() < local_date})
    history = [summarize_day(logs, day, timezone) for day in dates]
    daily = asdict(calculate_forecast(summary, generated_at=generated_at))
    return {"version": METHOD, "generated_at": generated_at.astimezone(utc.utc), "local_date": local_date,
            "timezone": timezone, "intake": asdict(summary), "daily_requirement": daily,
            "historical_logged_intake": {"window_days": history_days, "logged_days": len(history),
                "days_without_logs": history_days-len(history), "kind": "descriptive_logged_totals_not_needs",
                "beverage_lower_ml": min((s.beverage_total_ml for s in history), default=None),
                "beverage_upper_ml": max((s.beverage_total_ml for s in history), default=None),
                "days": [asdict(value) for value in history], "completeness": "unverified"},
            "exercise_loss": exercise_loss(exercise, samples, generated_at=generated_at),
            "explanation_policy": "Meta_may_explain_reviewed_results_only_no_numeric_recalculation",
            "prediction_validated": False}
