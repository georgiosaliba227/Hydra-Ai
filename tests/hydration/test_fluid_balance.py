"""Signed, narrowly scoped exercise arithmetic never turns into hydration status."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from importlib import import_module
from uuid import UUID

import pytest

from ai.hydration.models import BeverageLog, WorkoutMeasurement
from ai.hydration.personal_forecast import Conditions, Exercise, MeasurementErrors, SweatSample

NOW = datetime(2026, 11, 2, 15, tzinfo=timezone.utc)
START = NOW - timedelta(hours=2)
END = START + timedelta(hours=1)
CONDITIONS = Conditions("running", "moderate", 20.0, 60.0)


def completed(*, post_mass=69.6, consumed=300.0):
    sample = SweatSample(UUID(int=1), END, CONDITIONS,
        WorkoutMeasurement(70.0, post_mass, consumed, 0.0, 60.0, True, ("test_weighing",)),
        MeasurementErrors(.05, .05, 10., 0., 0., ("test_instrument_error",)))
    return Exercise(UUID(int=1), START, 60., CONDITIONS, True, actual=sample)


def logged(amount=300., when=START + timedelta(minutes=30)):
    return BeverageLog(UUID(int=2), 1, "unknown composition", amount, when, "UTC", "manual", ("test_log",))


def calculate(exercise, logs=()):
    module = import_module("ai.hydration.fluid_balance")
    return module.logged_intake_minus_measured_exercise_loss(tuple(logs), exercise, generated_at=NOW, timezone="UTC")


@pytest.mark.parametrize("post_mass,consumed,want", [
    (69.6, 300., (-400., -510., -290.)),
    (70.8, 1200., (800., 690., 910.)),
    (70., 300., (0., -110., 110.)),
])
def test_signed_residual_preserves_negative_positive_and_cross_zero_ranges(post_mass, consumed, want):
    value = calculate(completed(post_mass=post_mass, consumed=consumed), [logged(consumed)])
    assert value["status"] == "estimated"
    assert (value["value_ml"], value["lower_ml"], value["upper_ml"]) == want
    assert value["quantity"] == "logged_intake_minus_measured_exercise_loss"
    assert value["start_utc"] == "2026-11-02T13:00:00.000000Z"
    assert value["end_utc"] == "2026-11-02T14:00:00.000000Z"
    assert value["logged_beverage_volume_ml"] == consumed
    assert set(value["provenance"]) == {"test_log", "test_weighing", "test_instrument_error"}


def test_planned_forecast_is_never_counted_as_already_lost():
    plan = replace(completed(), starts_at=NOW + timedelta(hours=1), actual=None)
    value = calculate(plan, [logged()])
    assert value["value_ml"] is value["lower_ml"] is value["upper_ml"] is None
    assert value["status"] == "unavailable"
    assert "actual_measurement_required" in value["reasons"]


def test_only_same_observed_workout_window_intake_is_counted():
    before = replace(logged(900., START - timedelta(microseconds=1)), id=UUID(int=3))
    after = replace(logged(700., END + timedelta(microseconds=1)), id=UUID(int=4))
    value = calculate(completed(), [before, logged(), after])
    assert value["value_ml"] == -400
    assert value["logged_beverage_volume_ml"] == 300


@pytest.mark.parametrize("mutation,reason", [
    (lambda e: replace(e, starts_at=e.starts_at-timedelta(minutes=1)), "measurement_window_mismatch"),
    (lambda e: replace(e, conditions=Conditions("cycling", "moderate", 20., 60.)), "measurement_conditions_mismatch"),
    (lambda e: replace(e, actual=replace(e.actual, errors=None)), "usable_measurements_with_error_bounds"),
    (lambda e: replace(e, starts_at=e.starts_at-timedelta(days=1),
                       actual=replace(e.actual, observed_at=e.actual.observed_at-timedelta(days=1))), "completed_workout_outside_today"),
])
def test_incompatible_measurements_abstain(mutation, reason):
    value = calculate(mutation(completed()), [logged()])
    assert value["status"] == "unavailable"
    assert value["lower_ml"] is value["upper_ml"] is None
    assert reason in value["reasons"]


def test_unmatched_consumption_does_not_silently_double_count_or_fill_logs():
    value = calculate(completed(), [logged(100.)])
    assert value["status"] == "unavailable"
    assert "logged_intake_does_not_match_measurement" in value["reasons"]


def test_explicit_measured_zero_is_distinct_from_missing_measurement():
    zero = completed(post_mass=69.6, consumed=0.)
    assert calculate(zero)["value_ml"] == -400.
    missing = replace(zero, actual=replace(zero.actual, measurement=replace(zero.actual.measurement, consumed_ml=None)))
    assert calculate(missing)["value_ml"] is None

