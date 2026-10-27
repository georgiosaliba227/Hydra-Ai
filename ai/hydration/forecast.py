"""Contract-shaped fallback until a daily requirement method is approved."""
from datetime import datetime, timezone

from .models import Contribution, DailySummary, Forecast, METHOD_VERSION, aware


def calculate_forecast(summary: DailySummary, *, generated_at: datetime) -> Forecast:
    aware(generated_at, "generated_at")
    return Forecast(
        status="insufficient_data", lower_ml=None, upper_ml=None,
        beverage_total_ml=summary.beverage_total_ml,
        estimated_water_ml=summary.estimated_water_ml,
        component_ledger=(Contribution(summary.beverage_total_ml, summary.estimated_water_ml,
                                       None, None, None, summary.provenance, summary.uncertainty_reasons),),
        input_provenance=summary.provenance, method_version=METHOD_VERSION,
        assumptions=("beverage_volume_is_not_total_dietary_water",),
        uncertainty_reasons=summary.uncertainty_reasons,
        reasons=("personalized_requirement_method_not_approved",),
        missing_inputs=("approved_baseline_method",),
        generated_at=generated_at.astimezone(timezone.utc),
    )
