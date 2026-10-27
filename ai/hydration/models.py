"""Internal calculation types; HTTP schemas and authorization belong to backend."""
from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

METHOD_VERSION = "hydration-accounting-v1"


class CalculationError(ValueError):
    """Stable code/field only: never echo sensitive input values."""

    def __init__(self, code: str, field: str):
        self.code = code
        self.field = field
        super().__init__(f"{code}: {field}")


def number(value: float, field: str, *, positive: bool = False) -> None:
    if type(value) not in (int, float):
        raise CalculationError("invalid_number", field)
    try:
        valid = isfinite(value) and (value > 0 if positive else value >= 0)
    except OverflowError:
        valid = False
    if not valid:
        raise CalculationError("invalid_number", field)


def text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise CalculationError("missing_text", field)


def aware(value: datetime, field: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise CalculationError("invalid_timestamp", field)


def zone(value: str) -> ZoneInfo:
    text(value, "timezone")
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise CalculationError("invalid_timezone", "timezone") from None


def provenance(value: tuple[str, ...]) -> None:
    if not isinstance(value, tuple) or not value:
        raise CalculationError("missing_provenance", "provenance")
    for item in value:
        text(item, "provenance")


@dataclass(frozen=True)
class Composition:
    """Source-backed composition per basis volume; no category defaults."""

    basis_ml: float
    provenance: tuple[str, ...]
    water_ml: float | None = None
    sodium_mg: float | None = None
    potassium_mg: float | None = None
    carbohydrate_g: float | None = None

    def __post_init__(self) -> None:
        number(self.basis_ml, "basis_ml", positive=True)
        provenance(self.provenance)
        for field in ("water_ml", "sodium_mg", "potassium_mg", "carbohydrate_g"):
            value = getattr(self, field)
            if value is not None:
                number(value, field)
        if self.water_ml is not None and self.water_ml > self.basis_ml:
            raise CalculationError("invalid_composition", "water_ml")


@dataclass(frozen=True)
class BeverageLog:
    id: UUID
    revision: int
    category: str
    consumed_ml: float
    consumed_at: datetime
    timezone: str
    source: str
    provenance: tuple[str, ...]
    nutrition: Composition | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise CalculationError("invalid_id", "id")
        if type(self.revision) is not int or self.revision < 1:
            raise CalculationError("invalid_revision", "revision")
        text(self.category, "category")
        number(self.consumed_ml, "consumed_ml")
        aware(self.consumed_at, "consumed_at")
        zone(self.timezone)
        if self.source not in ("manual", "confirmed_recognition"):
            raise CalculationError("unconfirmed_source", "source")
        provenance(self.provenance)
        if self.nutrition is not None and not isinstance(self.nutrition, Composition):
            raise CalculationError("invalid_composition", "nutrition")


@dataclass(frozen=True)
class Contribution:
    beverage_total_ml: float
    estimated_water_ml: float | None
    sodium_mg: float | None
    potassium_mg: float | None
    carbohydrate_g: float | None
    provenance: tuple[str, ...]
    uncertainty_reasons: tuple[str, ...]


@dataclass(frozen=True)
class DailySummary:
    local_date: date
    timezone: str
    beverage_total_ml: float
    estimated_water_ml: float | None
    log_revisions: tuple[tuple[UUID, int], ...]
    provenance: tuple[str, ...]
    uncertainty_reasons: tuple[str, ...]


@dataclass(frozen=True)
class WorkoutMeasurement:
    pre_mass_kg: float | None
    post_mass_kg: float | None
    consumed_ml: float | None
    urine_ml: float | None
    duration_minutes: float | None
    protocol_confirmed: bool
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        for field in ("pre_mass_kg", "post_mass_kg", "consumed_ml", "urine_ml", "duration_minutes"):
            value = getattr(self, field)
            if value is not None:
                number(value, field, positive=field in ("pre_mass_kg", "post_mass_kg", "duration_minutes"))
        if type(self.protocol_confirmed) is not bool:
            raise CalculationError("invalid_boolean", "protocol_confirmed")
        provenance(self.provenance)


@dataclass(frozen=True)
class WorkoutResult:
    status: str
    estimated_loss_ml: float | None
    sweat_rate_ml_per_hour: float | None
    method_version: str
    provenance: tuple[str, ...]
    assumptions: tuple[str, ...]
    uncertainty_reasons: tuple[str, ...]
    missing_inputs: tuple[str, ...]


@dataclass(frozen=True)
class Forecast:
    status: str
    lower_ml: float | None
    upper_ml: float | None
    beverage_total_ml: float
    estimated_water_ml: float | None
    component_ledger: tuple[Contribution, ...]
    input_provenance: tuple[str, ...]
    method_version: str
    assumptions: tuple[str, ...]
    uncertainty_reasons: tuple[str, ...]
    reasons: tuple[str, ...]
    missing_inputs: tuple[str, ...]
    generated_at: datetime
