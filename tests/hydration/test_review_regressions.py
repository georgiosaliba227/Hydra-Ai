"""Boundary cases found during PR #4 review."""
import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from test_engine import log, measurement
from ai.hydration import (
    CalculationError, Composition, calculate_contribution, calculate_forecast,
    estimate_workout_loss, project_workout_loss, summarize_day,
)


class NumericalRegressionTests(unittest.TestCase):
    def test_scaling_does_not_underflow_intermediate_ratio(self):
        result = calculate_contribution(log(consumed_ml=1e300,
            nutrition=Composition(1e300, ("fixture",), water_ml=1e-100)))
        self.assertEqual(result.estimated_water_ml, 1e-100)

    def test_scaling_does_not_overflow_intermediate_ratio(self):
        result = calculate_contribution(log(consumed_ml=1e-300,
            nutrition=Composition(1e-300, ("fixture",), sodium_mg=1e100)))
        self.assertEqual(result.sodium_mg, 1e100)

    def test_true_underflow_does_not_become_known_zero(self):
        with self.assertRaises(CalculationError):
            calculate_contribution(log(consumed_ml=1e-300,
                nutrition=Composition(1e300, ("fixture",), water_ml=1e-300)))

    def test_decimal_zero_mass_balance(self):
        result = estimate_workout_loss(measurement(pre_mass_kg=70, post_mass_kg=70.1,
                                                   consumed_ml=100, urine_ml=0))
        self.assertEqual(result.status, "estimated")
        self.assertEqual(result.estimated_loss_ml, 0)

    def test_projection_does_not_underflow_duration_ratio(self):
        result = project_workout_loss(measurement(pre_mass_kg=70, post_mass_kg=70,
            consumed_ml=1e300, urine_ml=0), 5e-324, comparable_conditions=True)
        self.assertGreater(result.estimated_loss_ml, 0)

    def test_projection_true_underflow_returns_insufficient_data(self):
        result = project_workout_loss(measurement(pre_mass_kg=70, post_mass_kg=70,
            consumed_ml=1e-300, urine_ml=0), 1e-300, comparable_conditions=True)
        self.assertEqual(result.status, "insufficient_data")
        self.assertIsNone(result.estimated_loss_ml)
        self.assertIn("numeric_underflow", result.uncertainty_reasons)

    def test_zero_consumed_does_not_overflow_large_ratio(self):
        result = calculate_contribution(log(consumed_ml=0,
            nutrition=Composition(1e-300, ("fixture",), sodium_mg=1e300)))
        self.assertEqual(result.sodium_mg, 0)

    def test_supplement_name_has_no_effect(self):
        plain = calculate_contribution(log(category="water"))
        supplemented = calculate_contribution(log(category="water_with_creatine"))
        self.assertEqual(plain, supplemented)

    def test_forecast_rejects_invalid_internal_totals(self):
        summary = summarize_day([], date(2026, 10, 26), "UTC")
        for change in (dict(beverage_total_ml=float("nan")), dict(estimated_water_ml=-1),
                       dict(estimated_water_ml=1)):
            with self.subTest(change=change), self.assertRaises(CalculationError):
                calculate_forecast(replace(summary, **change), generated_at=datetime(2026, 10, 26, tzinfo=timezone.utc))


class TimeAndDuplicateRegressionTests(unittest.TestCase):
    def test_nonexistent_zoneinfo_wall_time_is_rejected(self):
        with self.assertRaises(CalculationError):
            log(consumed_at=datetime(2026, 3, 8, 2, 30, tzinfo=ZoneInfo("America/New_York")))

    def test_both_local_folds_are_preserved(self):
        local = datetime(2026, 11, 1, 1, 30, tzinfo=ZoneInfo("America/New_York"))
        entries = [log(consumed_at=local.replace(fold=fold)) for fold in (0, 1)]
        result = summarize_day(entries, date(2026, 11, 1), "America/New_York")
        self.assertEqual(result.beverage_total_ml, 500)
        self.assertEqual(tuple(item[0] for item in result.log_revisions), tuple(item.id for item in entries))

    def test_utc_conversion_overflow_is_typed(self):
        with self.assertRaises(CalculationError):
            log(consumed_at=datetime.min.replace(tzinfo=timezone(timedelta(hours=1))))

    def test_local_conversion_overflow_is_typed(self):
        entry = log(consumed_at=datetime.min.replace(tzinfo=timezone.utc))
        with self.assertRaises(CalculationError):
            summarize_day([entry], date.min, "America/New_York")

    def test_half_hour_dst_boundary(self):
        entries = [log(consumed_at=datetime.fromisoformat(stamp)) for stamp in (
            "2026-10-03T13:29:59+00:00", "2026-10-03T13:30:00+00:00",
            "2026-10-04T12:59:59+00:00", "2026-10-04T13:00:00+00:00")]
        self.assertEqual(summarize_day(entries, date(2026, 10, 4), "Australia/Lord_Howe").beverage_total_ml, 500)

    def test_duplicate_outside_selected_day_still_rejected(self):
        entry = log()
        with self.assertRaises(CalculationError):
            summarize_day([entry, entry], date(2026, 10, 27), "UTC")
