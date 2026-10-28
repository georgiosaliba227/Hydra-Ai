from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from ai.hydration.models import CalculationError, WorkoutMeasurement
from ai.hydration.personal_forecast import Conditions, Exercise, MeasurementErrors, SweatSample
from ai.forecasting.predict import predict_workout

NOW = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
CONDITIONS = Conditions('running', 'moderate', 24., 50.)


def forecast(samples=(), exercise=None):
    from ai.forecasting.longitudinal import predict_longitudinal
    planned = exercise or Exercise(UUID(int=999), NOW + timedelta(hours=1), 60., CONDITIONS, True)
    return predict_longitudinal(planned, tuple(samples), generated_at=NOW)


def history(losses):
    return tuple(SweatSample(UUID(int=i + 1), NOW - timedelta(days=len(losses)-i), CONDITIONS,
        WorkoutMeasurement(70., 70.-loss/1000, 0., 0., 60., True, ('invented_test_measurement',)),
        MeasurementErrors(.01, .01, 0., 0., 0., ('invented_test_error_bound',)))
        for i, loss in enumerate(losses))


def test_cold_start_does_not_make_up_population_estimate():
    result = forecast()
    assert result['status'] == 'insufficient_data'
    assert result['value_ml'] is None
    assert result['longitudinal_history']['comparable_samples'] == 0


def test_latest_comparable_history_changes_point_without_narrowing_envelope():
    samples = history([200., 200., 200., 200., 200., 400., 500., 600., 700., 800.])
    result = forecast(samples)
    assert result['value_ml'] == pytest.approx(600.)
    assert result['lower_ml'] <= 180.
    assert result['upper_ml'] >= 820.
    assert result['sample_count'] == 10
    assert result['longitudinal_history']['recent_samples'] == 5
    assert result['personalization_status'] == 'longitudinal_personal_calibration'
    assert result['interval_kind'] == 'historical_error_envelope'


def test_presentation_order_does_not_change_chronological_learning():
    samples = history([200., 400., 600., 800., 900., 1000.])
    assert forecast(samples) == forecast(reversed(samples))


def test_one_sample_retains_baseline_and_discloses_limited_history():
    result = forecast(history([600.]))
    assert result['value_ml'] == pytest.approx(600.)
    assert result['lower_ml'] <= 580. and result['upper_ml'] >= 620.
    assert result['personalization_status'] == 'limited_personal_history'


def test_unmatched_conditions_and_missing_errors_do_not_become_history():
    samples = history([300., 600., 900.])
    unmatched = replace(samples[1], conditions=Conditions('cycling', 'moderate', 24., 50.))
    missing = replace(samples[2], errors=None)
    result = forecast((samples[0], unmatched, missing))
    assert result['value_ml'] == pytest.approx(300.)
    assert result['longitudinal_history']['total_samples'] == 3
    assert result['longitudinal_history']['comparable_samples'] == 1


def test_duplicate_measurement_with_new_id_is_not_new_evidence():
    sample = history([600.])[0]
    with pytest.raises(CalculationError, match='duplicate_measurement'):
        forecast((sample, replace(sample, event_id=UUID(int=200))))


def test_future_observation_rejected_not_silently_used():
    sample = replace(history([600.])[0], observed_at=NOW + timedelta(minutes=1))
    with pytest.raises(CalculationError):
        forecast((sample,))


def test_completed_actual_outcome_is_not_replaced_by_learned_prediction():
    actual = replace(history([650.])[0], event_id=UUID(int=999), observed_at=NOW)
    exercise = Exercise(UUID(int=999), NOW-timedelta(hours=1), 60., CONDITIONS, True, actual=actual)
    result = forecast(history([200., 300., 400.]), exercise)
    assert result['value_ml'] == pytest.approx(650.)
    assert result['personalization_status'] == 'measured_actual'


def test_prequential_evaluation_withholds_current_and_future_measurements():
    from ai.forecasting.longitudinal import evaluate_prequential
    samples = history([200., 300., 400., 500., 600., 700., 800.])
    result = evaluate_prequential({'synthetic-person-1': samples}, synthetic=True)
    assert result['origin'] == 'synthetic'
    assert result['attempted_predictions'] == 7
    assert result['scored_predictions'] == 6
    assert result['systems']['baseline']['mae_ml'] is not None
    assert result['predictions'][0]['baseline_ml'] is None
    assert result['predictions'][1]['adaptive_ml'] == pytest.approx(200.)
    changed = (*samples[:-1], replace(samples[-1], measurement=replace(samples[-1].measurement, post_mass_kg=68.)))
    altered = evaluate_prequential({'synthetic-person-1': changed}, synthetic=True)
    assert result['predictions'][:-1] == altered['predictions'][:-1]
    assert result['predictions'][-1]['adaptive_ml'] == altered['predictions'][-1]['adaptive_ml']


def test_synthetic_evaluation_is_reproducible_and_does_not_claim_real_evidence():
    from ai.forecasting.longitudinal import evaluate_synthetic_histories
    first = evaluate_synthetic_histories()
    second = evaluate_synthetic_histories()
    assert first == second
    assert set(first['scenarios']) == {'stable', 'gradual_change', 'abrupt_change', 'condition_shift'}
    assert first['real_world_improvement'] is False
    assert all(r['origin'] == 'synthetic' for r in first['scenarios'].values())


def test_dst_fold_uses_actual_utc_order_for_recent_history():
    from zoneinfo import ZoneInfo
    from ai.forecasting.longitudinal import predict_longitudinal
    ny = ZoneInfo('America/New_York')
    times = [datetime(2026, 11, 1, 0, 10, tzinfo=ny),
             datetime(2026, 11, 1, 0, 20, tzinfo=ny),
             datetime(2026, 11, 1, 1, 30, tzinfo=ny, fold=0),
             datetime(2026, 11, 1, 1, 40, tzinfo=ny, fold=0),
             datetime(2026, 11, 1, 1, 50, tzinfo=ny, fold=0),
             datetime(2026, 11, 1, 1, 10, tzinfo=ny, fold=1)]
    samples = tuple(replace(s, observed_at=t) for s,t in zip(history([100.,200.,300.,400.,500.,600.]),times))
    now = datetime(2026,11,1,3,tzinfo=ny)
    query = Exercise(UUID(int=999),now+timedelta(hours=1),60.,CONDITIONS,True)
    result = predict_longitudinal(query,samples,generated_at=now)
    assert result['longitudinal_history']['last_observed_at'] == '2026-11-01T06:10:00+00:00'
