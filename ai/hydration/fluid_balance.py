"""Narrow signed exercise accounting, never total body water or an intake goal."""
from datetime import datetime, timezone as utc
from fractions import Fraction
from math import inf, isfinite, nextafter

from .models import BeverageLog, CalculationError, aware, convert_time, exact, zone
from .personal_forecast import Exercise, exercise_loss


def _utc_string(value: datetime) -> str:
    return convert_time(value, utc.utc, "timestamp").isoformat(timespec="microseconds").replace("+00:00", "Z")


def _signed(value: Fraction, *, upper: bool | None = None) -> float:
    """Signed output, with outward rounding for the interval endpoints."""
    result = float(value)
    if upper is not None:
        rounded = Fraction.from_float(result)
        if (upper and rounded < value) or (not upper and rounded > value):
            result = nextafter(result, inf if upper else -inf)
    if not isfinite(result):
        raise CalculationError("numeric_overflow", "exercise_accounting")
    return result


def logged_intake_minus_measured_exercise_loss(
    logs: tuple[BeverageLog, ...], exercise: Exercise | None, *, generated_at: datetime, timezone: str,
) -> dict:
    """Subtract only an explicitly matched completed-workout loss proxy.

    Logged beverage volume must match the measurement's recorded consumption in
    the same observed exercise window. Neither the planned projection nor
    historical calibration measurements enter this arithmetic. Unknown water
    fraction, urine and other losses prevent interpreting this as full balance.
    """
    aware(generated_at, "generated_at")
    local_zone = zone(timezone)
    result = {
        "status": "unavailable", "quantity": "logged_intake_minus_measured_exercise_loss",
        "start_utc": None, "end_utc": None, "timezone": timezone,
        "value_ml": None, "lower_ml": None, "upper_ml": None,
        "logged_beverage_volume_ml": None, "reasons": [], "provenance": [],
    }
    if exercise is None or exercise.actual is None:
        result["reasons"] = ["actual_measurement_required"]
        return result
    actual = exercise.actual
    started = convert_time(exercise.starts_at, utc.utc, "starts_at")
    observed = convert_time(actual.observed_at, utc.utc, "observed_at")
    current = convert_time(generated_at, utc.utc, "generated_at")
    result.update(start_utc=_utc_string(started), end_utc=_utc_string(observed))
    # Validate the existing actual event/protocol/error envelope before deriving anything.
    loss = exercise_loss(exercise, (), generated_at=generated_at)
    if loss["status"] != "estimated":
        result["reasons"] = loss["missing_inputs"] or ["usable_measurements_with_error_bounds"]
        return result
    if started.astimezone(local_zone).date() != current.astimezone(local_zone).date():
        result["reasons"] = ["completed_workout_outside_today"]
        return result
    measurement = actual.measurement
    elapsed = observed-started
    elapsed_minutes = Fraction(elapsed.days*86400+elapsed.seconds, 60) + Fraction(elapsed.microseconds, 60_000_000)
    if (elapsed_minutes != exact(measurement.duration_minutes)
            or exact(exercise.duration_minutes) != exact(measurement.duration_minutes)):
        result["reasons"] = ["measurement_window_mismatch"]
        return result
    if actual.conditions != exercise.conditions:
        result["reasons"] = ["measurement_conditions_mismatch"]
        return result
    seen = set()
    selected = []
    for log in logs:
        if not isinstance(log, BeverageLog) or log.id in seen:
            raise CalculationError("invalid_log_snapshot", "logs")
        seen.add(log.id)
        if started <= convert_time(log.consumed_at, utc.utc, "consumed_at") <= observed:
            selected.append(log)
    logged = sum((exact(log.consumed_ml) for log in selected), Fraction())
    if logged != exact(measurement.consumed_ml):
        result["reasons"] = ["logged_intake_does_not_match_measurement"]
        return result
    measured_loss = ((exact(measurement.pre_mass_kg)-exact(measurement.post_mass_kg))*1000
                     + exact(measurement.consumed_ml)-exact(measurement.urine_ml))
    result.update(
        status="estimated", value_ml=_signed(logged-measured_loss),
        lower_ml=_signed(logged-exact(loss["upper_ml"]), upper=False),
        upper_ml=_signed(logged-exact(loss["lower_ml"]), upper=True),
        logged_beverage_volume_ml=_signed(logged),
        reasons=["logged_beverage_volume_not_retained_water", "exercise_loss_is_mass_balance_proxy",
                 "urine_and_other_losses_not_subtracted", "logging_completeness_unverified",
                 "not_total_body_water_balance_or_hydration_status"],
        provenance=list(dict.fromkeys([source for log in selected for source in log.provenance] + loss["provenance"])),
    )
    return result
