import json
import socket
import unittest
from dataclasses import asdict, replace
from datetime import date, datetime, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

from ai.hydration import (
    BeverageLog, CalculationError, Composition, WorkoutMeasurement,
    calculate_contribution, calculate_forecast, estimate_workout_loss,
    project_workout_loss, summarize_day,
)


def log(**changes):
    values = dict(id=uuid4(), revision=1, category="coffee", consumed_ml=250,
                  consumed_at=datetime(2026, 10, 26, 12, tzinfo=timezone.utc),
                  timezone="America/New_York", source="manual", provenance=("manual-entry",))
    values.update(changes)
    return BeverageLog(**values)


def measurement(**changes):
    values = dict(pre_mass_kg=70, post_mass_kg=69, consumed_ml=500, urine_ml=100,
                  duration_minutes=60, protocol_confirmed=True, provenance=("synthetic-workout",))
    values.update(changes)
    return WorkoutMeasurement(**values)


class ContributionTests(unittest.TestCase):
    def test_all_categories_count_consumed_volume(self):
        for category in ("water", "coffee", "milk", "shake", "sports_drink", "unknown"):
            with self.subTest(category=category):
                result = calculate_contribution(log(category=category))
                self.assertEqual(result.beverage_total_ml, 250)
                self.assertIsNone(result.estimated_water_ml)

    def test_sourced_serving_conversion(self):
        nutrition = Composition(100, ("synthetic-composition",), water_ml=90,
                                sodium_mg=40, potassium_mg=20, carbohydrate_g=10)
        result = calculate_contribution(log(nutrition=nutrition))
        self.assertEqual((result.estimated_water_ml, result.sodium_mg,
                          result.potassium_mg, result.carbohydrate_g), (225, 100, 50, 25))
        self.assertEqual(result.provenance, ("manual-entry", "synthetic-composition"))

    def test_unknown_is_not_zero(self):
        result = calculate_contribution(log(nutrition=Composition(100, ("source",), sodium_mg=0)))
        self.assertEqual(result.sodium_mg, 0)
        self.assertIsNone(result.potassium_mg)
        self.assertIsNone(result.estimated_water_ml)

    def test_invalid_consumed_values(self):
        for value in (-1, float("nan"), float("inf"), True, "250", 10**400):
            with self.subTest(value=type(value).__name__), self.assertRaises(CalculationError):
                log(consumed_ml=value)

    def test_zero_consumption_is_valid(self):
        self.assertEqual(calculate_contribution(log(consumed_ml=0)).beverage_total_ml, 0)

    def test_bad_composition(self):
        for kwargs in (dict(basis_ml=0), dict(water_ml=101), dict(sodium_mg=-1), dict(provenance=())):
            args = dict(basis_ml=100, provenance=("source",))
            args.update(kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(CalculationError):
                Composition(**args)

    def test_boundary_metadata(self):
        for kwargs in (dict(id="not-a-uuid"), dict(revision=True), dict(revision=0),
                       dict(consumed_at=datetime(2026, 1, 1)), dict(timezone="bad/zone"),
                       dict(source="unconfirmed_recognition"), dict(provenance=()),
                       dict(category=""), dict(nutrition={})):
            with self.subTest(kwargs=kwargs), self.assertRaises(CalculationError):
                log(**kwargs)

    def test_unknown_constructor_field_rejected(self):
        with self.assertRaises(TypeError):
            log(container_ml=500)

    def test_scaling_overflow_rejected(self):
        with self.assertRaises(CalculationError):
            calculate_contribution(log(nutrition=Composition(1e-300, ("source",), sodium_mg=1e300)))

    def test_error_does_not_echo_value(self):
        try:
            log(category="", provenance=("private-health-record",))
        except CalculationError as error:
            self.assertEqual(str(error), "missing_text: category")


class DailyTests(unittest.TestCase):
    def test_totals_and_complete_water(self):
        entries = [log(consumed_ml=200, nutrition=Composition(100, ("source",), water_ml=95)),
                   log(consumed_ml=100, nutrition=Composition(100, ("source",), water_ml=100))]
        result = summarize_day(entries, date(2026, 10, 26), "UTC")
        self.assertEqual(result.beverage_total_ml, 300)
        self.assertEqual(result.estimated_water_ml, 290)

    def test_partial_water_is_unknown(self):
        result = summarize_day([log(), log(nutrition=Composition(100, ("source",), water_ml=100))],
                               date(2026, 10, 26), "UTC")
        self.assertEqual(result.beverage_total_ml, 500)
        self.assertIsNone(result.estimated_water_ml)

    def test_empty_day_is_zero_logged_intake(self):
        result = summarize_day([], date(2026, 10, 26), "UTC")
        self.assertEqual((result.beverage_total_ml, result.estimated_water_ml), (0, 0))

    def test_duplicate_and_conflicting_revisions(self):
        entry = log()
        for duplicate in (entry, replace(entry, revision=2)):
            with self.assertRaises(CalculationError) as caught:
                summarize_day([entry, duplicate], date(2026, 10, 26), "UTC")
            self.assertEqual(caught.exception.code, "duplicate_log")

    def test_local_midnight_includes_start_excludes_end(self):
        entries = [log(consumed_at=datetime.fromisoformat(stamp)) for stamp in
                   ("2026-10-26T03:59:59+00:00", "2026-10-26T04:00:00+00:00",
                    "2026-10-27T03:59:59+00:00", "2026-10-27T04:00:00+00:00")]
        self.assertEqual(summarize_day(entries, date(2026, 10, 26), "America/New_York").beverage_total_ml, 500)

    def test_spring_dst_23_hour_day(self):
        entries = [log(consumed_at=datetime.fromisoformat(stamp)) for stamp in
                   ("2026-03-08T05:00:00+00:00", "2026-03-09T03:59:59+00:00", "2026-03-09T04:00:00+00:00")]
        self.assertEqual(summarize_day(entries, date(2026, 3, 8), "America/New_York").beverage_total_ml, 500)

    def test_fall_dst_both_repeated_hours(self):
        entries = [log(consumed_at=datetime.fromisoformat(stamp)) for stamp in
                   ("2026-11-01T05:30:00+00:00", "2026-11-01T06:30:00+00:00",
                    "2026-11-02T04:59:59+00:00", "2026-11-02T05:00:00+00:00")]
        self.assertEqual(summarize_day(entries, date(2026, 11, 1), "America/New_York").beverage_total_ml, 750)

    def test_invalid_day_and_zone(self):
        for day, zone in (("2026-10-26", "UTC"), (date(2026, 10, 26), "../UTC")):
            with self.assertRaises(CalculationError):
                summarize_day([], day, zone)

    def test_input_order_does_not_change_output(self):
        entries = [log(id=UUID(int=2)), log(id=UUID(int=1))]
        self.assertEqual(summarize_day(entries, date(2026, 10, 26), "UTC"),
                         summarize_day(reversed(entries), date(2026, 10, 26), "UTC"))

    def test_total_overflow(self):
        with self.assertRaises(CalculationError):
            summarize_day([log(consumed_ml=1e308), log(consumed_ml=1e308)], date(2026, 10, 26), "UTC")


class WorkoutTests(unittest.TestCase):
    def test_mass_balance_and_units(self):
        result = estimate_workout_loss(measurement(duration_minutes=30))
        self.assertEqual(result.status, "estimated")
        self.assertEqual(result.estimated_loss_ml, 1400)
        self.assertEqual(result.sweat_rate_ml_per_hour, 2800)

    def test_published_nata_table_three_runner_example(self):
        result = estimate_workout_loss(measurement(pre_mass_kg=80, post_mass_kg=79.2,
                                                   consumed_ml=400, urine_ml=0, duration_minutes=45))
        self.assertAlmostEqual(result.sweat_rate_ml_per_hour, 1600)

    def test_missing_urine_does_not_become_zero(self):
        result = estimate_workout_loss(measurement(urine_ml=None))
        self.assertEqual(result.status, "insufficient_data")
        self.assertIsNone(result.estimated_loss_ml)
        self.assertIn("urine_ml", result.missing_inputs)

    def test_unconfirmed_protocol(self):
        self.assertEqual(estimate_workout_loss(measurement(protocol_confirmed=False)).status, "insufficient_data")

    def test_negative_balance_is_not_clamped(self):
        result = estimate_workout_loss(measurement(post_mass_kg=72))
        self.assertIsNone(result.estimated_loss_ml)
        self.assertIn("inconsistent_mass_balance", result.uncertainty_reasons)

    def test_invalid_measurements_raise(self):
        for kwargs in (dict(duration_minutes=0), dict(pre_mass_kg=-1), dict(consumed_ml=float("nan")),
                       dict(protocol_confirmed=1)):
            with self.subTest(kwargs=kwargs), self.assertRaises(CalculationError):
                measurement(**kwargs)

    def test_future_projection_requires_comparability(self):
        result = project_workout_loss(measurement(), 90, comparable_conditions=True)
        self.assertEqual(result.estimated_loss_ml, 2100)
        self.assertIn("future_rate_may_vary", result.uncertainty_reasons)
        blocked = project_workout_loss(measurement(), 90, comparable_conditions=False)
        self.assertEqual(blocked.status, "insufficient_data")
        self.assertIsNone(blocked.estimated_loss_ml)

    def test_workout_numeric_overflow(self):
        result = estimate_workout_loss(measurement(duration_minutes=1e-320))
        self.assertEqual(result.status, "insufficient_data")
        self.assertIsNone(result.sweat_rate_ml_per_hour)


class ForecastTests(unittest.TestCase):
    def test_fallback_contract_and_no_network(self):
        with patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")):
            calculate_contribution(log(nutrition=Composition(100, ("source",), water_ml=95)))
            estimate_workout_loss(measurement())
            project_workout_loss(measurement(), 90, comparable_conditions=True)
            summary = summarize_day([log()], date(2026, 10, 26), "UTC")
            result = calculate_forecast(summary, generated_at=datetime.fromisoformat("2026-10-26T12:00:00-04:00"))
        payload = asdict(result)
        payload["generated_at"] = result.generated_at.isoformat()
        json.dumps(payload, allow_nan=False)
        self.assertEqual(result.status, "insufficient_data")
        self.assertIsNone(result.lower_ml)
        self.assertIsNone(result.upper_ml)
        self.assertEqual(result.beverage_total_ml, 250)
        self.assertEqual(result.generated_at.hour, 16)
        self.assertEqual(result.missing_inputs, ("approved_baseline_method",))

    def test_explicit_clock_is_required(self):
        summary = summarize_day([], date(2026, 10, 26), "UTC")
        with self.assertRaises(CalculationError):
            calculate_forecast(summary, generated_at=datetime(2026, 10, 26))

    def test_same_input_same_output(self):
        summary = summarize_day([], date(2026, 10, 26), "UTC")
        now = datetime(2026, 10, 26, tzinfo=timezone.utc)
        self.assertEqual(calculate_forecast(summary, generated_at=now), calculate_forecast(summary, generated_at=now))


if __name__ == "__main__":
    unittest.main()
