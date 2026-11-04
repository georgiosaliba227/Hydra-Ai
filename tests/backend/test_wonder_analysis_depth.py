"""Wonder ranks substantive, evidence-applicable insights without creating facts."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from backend import wonder_analysis as api

FIXTURES = Path(__file__).parents[1] / "fixtures" / "hydration_analysis"


def source():
    return json.loads((FIXTURES / "personal_calibrated.json").read_text())


def selection(facts):
    return {"sections": {key: values[:1] for key, values in api.applicable_insights(facts).items()}}


def test_model_selects_different_supported_information_not_cosmetic_prefixes():
    facts = api.build_facts(source())
    supported = api.applicable_insights(facts)
    assert "loss_estimate" in supported["workout_loss"]
    assert "loss_limited_history" in supported["workout_loss"]
    first = selection(facts)
    first["sections"]["workout_loss"] = ["loss_estimate"]
    second = deepcopy(first)
    second["sections"]["workout_loss"] = ["loss_limited_history"]
    a = api.validate_selection(first, facts)["workout_loss"]["text"]
    b = api.validate_selection(second, facts)["workout_loss"]["text"]
    assert a != b
    assert "700 mL" in a and "700 mL" not in b
    assert "1 comparable" in b


@pytest.mark.parametrize("duration,label", [(.5, "0.5"), (1.5, "1.5"), (.01, "0.01")])
def test_activity_duration_keeps_fractional_minutes(duration, label):
    facts = api.build_facts(source())
    facts["activity"]["duration_minutes"] = duration
    facts["workout_comparison"] = None
    request = selection(facts)
    request["sections"]["activity"] = ["activity_context"]
    text = api.validate_selection(request, facts)["activity"]["text"]
    assert label + " minutes" in text


def test_rank_is_preserved_and_duplicates_cross_section_or_inapplicable_ids_rejected():
    facts = api.build_facts(source())
    request = selection(facts)
    request["sections"]["workout_loss"] = ["loss_limited_history", "loss_estimate"]
    section = api.validate_selection(request, facts)["workout_loss"]
    assert [insight["id"] for insight in section["insights"]] == ["loss_limited_history", "loss_estimate"]
    for invalid in (["loss_estimate", "loss_estimate"], ["beverage_volume"], ["loss_no_estimate"], []):
        changed = deepcopy(request)
        changed["sections"]["workout_loss"] = invalid
        with pytest.raises(ValueError):
            api.validate_selection(changed, facts)


def test_planned_comparison_context_controls_shift_and_duration_insights():
    value = source()
    previous = value["wonder"]["preview"]["facts"]["history"]
    previous.update(typical_duration_minutes=20, typical_temperature_c=10, typical_humidity_percent=40)
    facts = api.build_facts(value)
    ids = api.applicable_insights(facts)
    assert "activity_duration_comparison" in ids["activity"]
    assert "environment_shift" in ids["environment"]
    text = api.placeholder_values(facts)
    assert "longer" in text["duration_comparison"]
    assert "warmer" in text["environment_comparison"]
    absent = source()
    absent["wonder"]["preview"] = None
    absent_facts = api.build_facts(absent)
    assert "environment_shift" not in api.applicable_insights(absent_facts)["environment"]


def test_weekly_and_timing_insights_use_only_consistent_logged_aggregates():
    context = {"last_7_days": {"total_ml": 2000., "logged_days": 4},
        "previous_7_days": {"total_ml": 1000., "logged_days": 3}, "change_pct": 100,
        "time_of_day_ml": {"morning_ml": 2000., "afternoon_ml": 1000., "evening_ml": 0., "night_ml": 0.}}
    value = source()
    value["sections"][5]["facts"].update(logged_days=7, beverage_lower_ml=200., beverage_upper_ml=800.)
    facts = api.build_facts(value, trend_context=context)
    available = api.applicable_insights(facts)["trends"]
    assert "trends_week_change" in available and "trends_timing" in available
    rendered = api.placeholder_values(facts)
    assert "100% more logged volume" in rendered["weekly_comparison"]
    assert "morning" in rendered["timing_pattern"]
    assert "unverified" in rendered["trend_scope"]
    altered = deepcopy(context)
    altered["change_pct"] = -20
    with pytest.raises(ValueError):
        api.build_facts(source(), trend_context=altered)
    assert api.preview(facts)["payload_sha256"] != api.preview(api.build_facts(source()))["payload_sha256"]


def test_weekly_context_cannot_claim_logged_days_absent_from_neighboring_history_window():
    context = {"last_7_days": {"total_ml": 2000., "logged_days": 4},
        "previous_7_days": {"total_ml": 1000., "logged_days": 3}, "change_pct": 100,
        "time_of_day_ml": {"morning_ml": 2000., "afternoon_ml": 1000., "evening_ml": 0., "night_ml": 0.}}
    with pytest.raises(ValueError):
        api.build_facts(source(), trend_context=context)


def test_rounded_zero_percent_does_not_claim_different_logged_totals_are_unchanged():
    value = source()
    value["sections"][5]["facts"].update(logged_days=2, beverage_lower_ml=1000., beverage_upper_ml=1001.)
    context = {"last_7_days": {"total_ml": 1001., "logged_days": 1},
        "previous_7_days": {"total_ml": 1000., "logged_days": 1}, "change_pct": 0,
        "time_of_day_ml": {"morning_ml": 2001., "afternoon_ml": 0., "evening_ml": 0., "night_ml": 0.}}
    text = api.placeholder_values(api.build_facts(value, trend_context=context))["weekly_comparison"]
    assert "percentage change rounds to 0%" in text
    assert "unchanged" not in text


def test_environment_comparisons_match_existing_strict_display_boundaries():
    value = source()
    value["wonder"]["preview"]["facts"]["history"].update(typical_temperature_c=17, typical_humidity_percent=50)
    facts = api.build_facts(value)
    assert "environment_shift" in api.applicable_insights(facts)["environment"]
    text = api.placeholder_values(facts)["environment_comparison"]
    assert "warmer" in text and "more humid" in text
    assert "similar" not in text
