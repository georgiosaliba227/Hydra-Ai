"""Product rubric, local calendar and strict aggregate boundary; no health/provider data."""
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from backend import hydration_score as score


NOW = datetime(2026, 11, 3, 17, tzinfo=timezone.utc)


def record(when, ml):
    return {"consumed_at": when, "consumed_ml": ml}


def test_combines_current_goal_previous_calendar_days_and_capped_manual_support():
    facts = score.build_facts([
        record("2026-11-03T12:00:00+00:00", 1000),
        record("2026-11-02T12:00:00+00:00", 4000),
        record("2026-11-01T12:00:00+00:00", 1000),
        record("2026-11-03T18:00:00+00:00", 5000),  # Future, including later today.
        record("2026-10-26T12:00:00+00:00", 5000),  # Outside preceding seven days.
    ], 2000, "UTC", 3, now=NOW)
    assert facts["today_ml"] == 1000
    assert facts["components"] == pytest.approx({"today_points": 25.0, "consistency_points": 45 / 7,
                                                  "measurement_points": 10.0})
    assert facts["score"] == 41
    assert [day["local_date"] for day in facts["previous_days"]] == [
        "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30", "2026-10-31", "2026-11-01", "2026-11-02"]
    assert [day["logged"] for day in facts["previous_days"]] == [False] * 5 + [True, True]
    assert score.build_facts([], 2000, "UTC", 32, now=NOW)["score"] == 20


def test_half_rounding_is_up_and_no_intermediate_rounding():
    assert score.build_facts([record("2026-11-03T12:00:00Z", 1020)], 2000, "UTC", 0, now=NOW)["score"] == 26
    assert score.build_facts([], 2000, "UTC", 1, now=NOW)["score"] == 3


def test_local_midnight_and_dst_use_calendar_dates_not_utc_or_elapsed_hours():
    facts = score.build_facts([
        record("2026-11-01T03:59:59Z", 100),  # Oct31 in New York
        record("2026-11-01T04:00:00Z", 200),  # Nov1 before fallback
        record("2026-11-01T06:30:00Z", 300),  # Nov1 after fallback
        record("2026-11-02T05:00:00Z", 400),  # Nov2 local midnight
    ], 1000, "America/New_York", 0, now=NOW)
    assert [(day["local_date"], day["total_ml"]) for day in facts["previous_days"]][-3:] == [
        ("2026-10-31", 100), ("2026-11-01", 500), ("2026-11-02", 400)]


@pytest.mark.parametrize("count", [True, 1.0, -1, 33, None])
def test_manual_count_is_strict_and_bounded(count):
    with pytest.raises(ValueError):
        score.build_facts([], 2000, "UTC", count, now=NOW)


def test_missing_goal_and_unavailable_records_do_not_silently_become_zero():
    with pytest.raises(score.GoalRequired):
        score.build_facts([], None, "UTC", 0, now=NOW)
    for records in (None, [{"consumed_ml": 100}], [record("2026-11-03T12:00:00", 100)],
                    [record("2026-11-03T12:00:00Z", float("nan"))]):
        with pytest.raises(ValueError):
            score.build_facts(records, 2000, "UTC", 0, now=NOW)


@pytest.mark.parametrize("field,value", [("score", 1), ("research_only", 1), ("measurement_count", True)])
def test_derived_fields_and_boolean_types_are_revalidated(field, value):
    facts = deepcopy(score.build_facts([], 2000, "UTC", 0, now=NOW))
    facts[field] = value
    with pytest.raises(ValueError):
        score.validate_facts(facts)


def test_changed_goals_recompute_past_reference_and_reject_tampered_dates_flags_components():
    records = [record("2026-11-02T12:00:00Z", 1000)]
    assert score.build_facts(records, 1000, "UTC", 0, now=NOW)["components"]["consistency_points"] == 30 / 7
    assert score.build_facts(records, 2000, "UTC", 0, now=NOW)["components"]["consistency_points"] == 15 / 7
    good = score.build_facts(records, 2000, "UTC", 0, now=NOW)
    for mutate in (lambda f: f["previous_days"][0].update(local_date="2026-10-28"),
                   lambda f: f["previous_days"][0].update(logged=True),
                   lambda f: f["components"].update(today_points=1),
                   lambda f: f.update(extra="private")):
        facts = deepcopy(good)
        mutate(facts)
        with pytest.raises(ValueError):
            score.validate_facts(facts)
