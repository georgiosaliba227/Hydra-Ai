"""Accounting for consumed quantities, not physiological retention."""
from .models import BeverageLog, Contribution, exact, representable


def calculate_contribution(log: BeverageLog) -> Contribution:
    composition = log.nutrition

    def scaled(field: str) -> float | None:
        value = getattr(composition, field) if composition is not None else None
        if value is None:
            return None
        result = exact(value) * exact(log.consumed_ml) / exact(composition.basis_ml)
        return representable(result, field)

    water = scaled("water_ml")
    sources = log.provenance + (composition.provenance if composition is not None else ())
    return Contribution(
        beverage_total_ml=log.consumed_ml,
        estimated_water_ml=water,
        sodium_mg=scaled("sodium_mg"),
        potassium_mg=scaled("potassium_mg"),
        carbohydrate_g=scaled("carbohydrate_g"),
        provenance=tuple(dict.fromkeys(sources)),
        uncertainty_reasons=("composition_estimate_not_retention",) if water is not None else ("water_content_unknown",),
    )
