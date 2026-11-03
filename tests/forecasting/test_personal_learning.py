"""Experimental learned personalization; never a substitute for validated evidence."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from ai.hydration.models import CalculationError, WorkoutMeasurement
from ai.hydration.personal_forecast import Conditions, Exercise, MeasurementErrors, SweatSample

NOW = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
CONDITIONS = Conditions("running", "moderate", 22., 55.)


def samples(rates):
    return tuple(SweatSample(UUID(int=i+1), NOW-timedelta(days=(len(rates)-i)*3-1), CONDITIONS,
        WorkoutMeasurement(70., 70.-rate/1000, 0., 0., 60., True, ("synthetic_test_measurement",)),
        MeasurementErrors(.01, .01, 0., 0., 0., ("synthetic_test_error",))) for i, rate in enumerate(rates))


def predict(history, *, planned=None):
    from ai.forecasting.personal_learning import predict_personal_research
    planned = planned or Exercise(UUID(int=999), NOW+timedelta(hours=1), 60., CONDITIONS, True)
    return predict_personal_research(planned, tuple(history), generated_at=NOW)


def test_cold_start_and_few_measurements_retain_existing_numerical_method():
    for history in ((), samples([300., 350., 400.])):
        result = predict(history)
        assert result["research_only"] is True
        assert result["selected_method"] == "existing_personal_baseline"
        assert result["candidate"] is None
        assert result["application_promotion"] == "not_enabled"


def test_model_fits_personal_history_selects_without_future_outcome_and_keeps_envelope():
    from ai.forecasting.longitudinal import predict_longitudinal
    history = samples([300.+30*i for i in range(12)])
    plan = Exercise(UUID(int=999), NOW+timedelta(hours=1), 60., CONDITIONS, True)
    result = predict(history, planned=plan)
    baseline = predict_longitudinal(plan, history, generated_at=NOW)
    assert result["selected_method"] == "regularized_time_rate"
    candidate = result["candidate"]
    assert candidate["training_samples"] == 12
    assert candidate["ridge_alpha"] in (.1, 1., 10.)
    assert candidate["slope_ml_per_hour_per_day"] > 0
    assert result["selected_estimate"]["lower_ml"] <= baseline["lower_ml"]
    assert result["selected_estimate"]["upper_ml"] >= baseline["upper_ml"]
    assert result["interval_kind"] == "historical_measurement_and_error_envelope"
    assert result["nominal_coverage"] is None
    assert result["validation"]["folds"] >= 3
    assert all(row["training_samples"] < row["outcome_index"]+1 for row in result["validation"]["predictions"])


def test_stable_history_retains_simpler_baseline_and_order_does_not_change_training():
    history = samples([400.]*10)
    first = predict(history)
    assert first["selected_method"] == "existing_personal_baseline"
    assert predict(reversed(history)) == first


def test_condition_shift_actual_and_far_horizon_do_not_extrapolate_learned_trend():
    history = samples([300.+30*i for i in range(12)])
    plan = Exercise(UUID(int=999), NOW+timedelta(hours=1), 60., CONDITIONS, True)
    shifted = replace(plan, conditions=Conditions("running", "moderate", 30., 55.))
    assert predict(history, planned=shifted)["candidate"] is None
    far = replace(plan, starts_at=NOW+timedelta(days=30))
    assert predict(history, planned=far)["selected_method"] == "existing_personal_baseline"
    assert predict(history, planned=far)["reason"] == "beyond_observed_session_spacing"
    actual = replace(history[-1], event_id=plan.event_id, observed_at=NOW)
    done = replace(plan, starts_at=NOW-timedelta(hours=1), actual=actual)
    assert predict(history, planned=done)["candidate"] is None


def test_future_or_duplicate_history_is_rejected_before_training():
    history = samples([300.]*8)
    with pytest.raises(CalculationError):
        predict((*history, replace(history[-1], event_id=UUID(int=100), observed_at=NOW+timedelta(days=1))))
    with pytest.raises(CalculationError):
        predict((*history, replace(history[-1], event_id=UUID(int=100))))


def test_latest_outcome_is_withheld_from_its_validation_prediction():
    history = samples([300.+30*i for i in range(12)])
    first = predict(history)["validation"]["predictions"]
    changed = (*history[:-1], replace(history[-1], measurement=replace(history[-1].measurement, post_mass_kg=68.)))
    second = predict(changed)["validation"]["predictions"]
    assert first[:-1] == second[:-1]
    assert first[-1]["baseline_ml"] == second[-1]["baseline_ml"]
    assert first[-1]["candidates_ml"] == second[-1]["candidates_ml"]
    assert first[-1]["target_ml"] != second[-1]["target_ml"]


def test_report_marks_synthetic_evidence_and_reproduces():
    from ai.forecasting.personal_learning import evaluate_synthetic_personal_learning
    report = evaluate_synthetic_personal_learning()
    assert report == evaluate_synthetic_personal_learning()
    assert report["evidence_origin"] == "synthetic_software_scenarios"
    assert report["real_world_improvement"] is False
    assert report["application_promotion"] == "not_enabled"
    assert report["scenarios"]["gradual_change"]["systems"]["selected"]["mae_ml"] < report["scenarios"]["gradual_change"]["systems"]["baseline"]["mae_ml"]
