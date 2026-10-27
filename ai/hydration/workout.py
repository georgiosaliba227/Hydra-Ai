"""NATA 2017 Table 2 mass-balance estimate; never a drinking prescription."""
from dataclasses import replace

from .models import CalculationError, WorkoutMeasurement, WorkoutResult, number

METHOD = "nata-2017-mass-balance-v1"
ASSUMPTIONS = (
    "one_kg_mass_change_approximates_1000_ml_water",
    "comparable_dry_weighing_and_recorded_intake_and_urine",
    "other_mass_changes_not_resolved",
)


def estimate_workout_loss(measurement: WorkoutMeasurement) -> WorkoutResult:
    fields = ("pre_mass_kg", "post_mass_kg", "consumed_ml", "urine_ml", "duration_minutes")
    missing = tuple(field for field in fields if getattr(measurement, field) is None)
    if not measurement.protocol_confirmed:
        missing += ("confirmed_measurement_protocol",)
    result = WorkoutResult("insufficient_data", None, None, METHOD, measurement.provenance,
                           ASSUMPTIONS, ("measurement_uncertainty_not_quantified",), missing)
    if missing:
        return result
    loss = ((measurement.pre_mass_kg - measurement.post_mass_kg) * 1000
            + measurement.consumed_ml - measurement.urine_ml)
    if loss < 0:
        return replace(result, uncertainty_reasons=result.uncertainty_reasons + ("inconsistent_mass_balance",))
    try:
        number(loss, "estimated_loss_ml")
        rate = loss / measurement.duration_minutes * 60
        number(rate, "sweat_rate_ml_per_hour")
    except CalculationError:
        return replace(result, uncertainty_reasons=result.uncertainty_reasons + ("numeric_overflow",))
    return replace(result, status="estimated", estimated_loss_ml=loss, sweat_rate_ml_per_hour=rate)


def project_workout_loss(
    measurement: WorkoutMeasurement, duration_minutes: float, *, comparable_conditions: bool
) -> WorkoutResult:
    """Scale a measured rate only when the caller confirms comparable conditions."""
    number(duration_minutes, "duration_minutes", positive=True)
    if type(comparable_conditions) is not bool:
        raise CalculationError("invalid_boolean", "comparable_conditions")
    result = estimate_workout_loss(measurement)
    if not comparable_conditions:
        return replace(result, status="insufficient_data", estimated_loss_ml=None,
                       sweat_rate_ml_per_hour=None,
                       missing_inputs=result.missing_inputs + ("comparable_conditions",))
    if result.status != "estimated":
        return result
    loss = result.sweat_rate_ml_per_hour * (duration_minutes / 60)
    try:
        number(loss, "estimated_loss_ml")
    except CalculationError:
        return replace(result, status="insufficient_data", estimated_loss_ml=None,
                       sweat_rate_ml_per_hour=None,
                       uncertainty_reasons=result.uncertainty_reasons + ("numeric_overflow",))
    return replace(result, estimated_loss_ml=loss, method_version=METHOD + "-projection",
                   assumptions=result.assumptions + ("same_rate_under_comparable_conditions",),
                   uncertainty_reasons=result.uncertainty_reasons + ("future_rate_may_vary",))
