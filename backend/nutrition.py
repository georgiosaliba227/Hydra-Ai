"""Reviewed catalogue snapshots, never nutrition inferred by a language model."""
from copy import deepcopy

PRODUCT_ID = "coca-cola-original-us-12floz-v1"
IDENTITY = "Coca-Cola Original Taste (US)"
SOURCE = "https://www.coca-cola.com/us/en/brands/coca-cola/products/original"
# US fluid ounce definition: 29.5735295625 mL. Keep exact basis rather than
# treating a rounded can-volume suggestion (355 mL) as a nutrition measurement.
CATALOGUE = {
    PRODUCT_ID: {
        "identity": IDENTITY,
        "nutrition": {
            "basis_ml": 12 * 29.5735295625,
            "sodium_mg": 45, "carbohydrate_g": 39,
            "water_ml": None, "potassium_mg": None,
            "provenance": [SOURCE, "manufacturer-US-12-fl-oz;verified-2026-10-27;catalogue-v1"],
        },
    }
}


def lookup(product_id: str | None, identity: str) -> dict | None:
    if product_id is None:
        return None
    entry = CATALOGUE.get(product_id)
    if entry is None or entry["identity"] != identity:
        raise ValueError("Product identity must match the confirmed catalogue entry")
    return deepcopy(entry["nutrition"])
