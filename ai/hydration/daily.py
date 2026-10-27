"""Aggregate an owned, current-revision snapshot by local calendar date."""
from collections.abc import Iterable
from datetime import date, timezone as dt_timezone
from math import fsum

from .contributions import calculate_contribution
from .models import BeverageLog, CalculationError, DailySummary, number, zone


def summarize_day(logs: Iterable[BeverageLog], local_date: date, timezone: str) -> DailySummary:
    if type(local_date) is not date:
        raise CalculationError("invalid_date", "local_date")
    local_zone = zone(timezone)
    snapshot = tuple(logs)
    seen = set()
    for log in snapshot:
        if log.id in seen:
            raise CalculationError("duplicate_log", "id")
        seen.add(log.id)
    selected = sorted(
        (log for log in snapshot if log.consumed_at.astimezone(local_zone).date() == local_date),
        key=lambda log: (log.consumed_at.astimezone(dt_timezone.utc), str(log.id)),
    )
    contributions = tuple(calculate_contribution(log) for log in selected)
    try:
        total = fsum(item.beverage_total_ml for item in contributions)
        water = (fsum(item.estimated_water_ml for item in contributions)
                 if all(item.estimated_water_ml is not None for item in contributions) else None)
    except OverflowError:
        raise CalculationError("numeric_overflow", "daily_total") from None
    number(total, "beverage_total_ml")
    if water is not None:
        number(water, "estimated_water_ml")
    return DailySummary(
        local_date, timezone, total, water,
        tuple((log.id, log.revision) for log in selected),
        tuple(dict.fromkeys(source for item in contributions for source in item.provenance)),
        tuple(dict.fromkeys(reason for item in contributions for reason in item.uncertainty_reasons)),
    )
