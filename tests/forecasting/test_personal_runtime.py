"""Personal runtime fitting against invented measurements, never human evidence."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from uuid import UUID

import pytest

from ai.forecasting.longitudinal import predict_longitudinal
from ai.hydration.models import CalculationError, WorkoutMeasurement
from ai.hydration.personal_forecast import Conditions, Exercise, MeasurementErrors, SweatSample

NOW = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
CONDITIONS = Conditions('running', 'moderate', 22., 55.)
LEARNING_KEYS = {'version','selected_method','reason','training_samples','validation_folds',
    'fitted_rate_ml_per_hour','ridge_alpha','supported_duration_minutes','baseline_mae_ml',
    'candidate_mae_ml','paired_gain_ml','gain_standard_error_ml','training_sha256',
    'cadence_max_gap_seconds','storage','validation_origin','nominal_coverage'}


def history(losses, durations=None):
    durations = durations or [60.] * len(losses)
    return tuple(SweatSample(UUID(int=i+1),NOW-timedelta(days=2*(len(losses)-i)-1),CONDITIONS,
        WorkoutMeasurement(70.,70.-loss/1000,0.,0.,duration,True,('invented_test_measurement',)),
        MeasurementErrors(.01,.01,0.,0.,0.,('invented_test_bounds',)))
        for i,(loss,duration) in enumerate(zip(losses,durations,strict=True)))


def plan():
    return Exercise(UUID(int=999),NOW+timedelta(hours=1),60.,CONDITIONS,True)


def predict(samples=(), exercise=None, now=NOW):
    from ai.forecasting.personal_runtime import predict_personal_runtime
    return predict_personal_runtime(exercise or plan(),tuple(samples),generated_at=now)


def test_genuine_stationary_fit_selects_from_earlier_errors_and_preserves_bounds():
    samples=history([300.,500.,400.,500.,400.,500.])
    result=predict(samples)
    baseline=predict_longitudinal(plan(),samples,generated_at=NOW)
    learning=result['learning']
    assert set(learning)==LEARNING_KEYS
    assert learning['selected_method']=='regularized_duration_rate'
    # Fixed-alpha objective: final mean=433 1/3, median=450, fitted=(mean+median)/2.
    assert learning['fitted_rate_ml_per_hour']==pytest.approx(float(Fraction(1325,3)))
    assert result['value_ml']==pytest.approx(float(Fraction(1325,3)))
    assert learning['validation_folds']==3 and learning['training_samples']==6
    assert learning['baseline_mae_ml']==pytest.approx(250/3)
    assert learning['candidate_mae_ml']==pytest.approx(227.5/3)
    assert learning['paired_gain_ml']==pytest.approx(7.5)
    assert result['model_version']=='personal-runtime-rate-v1'
    assert result['interval_kind']=='personal_runtime_measurement_error_envelope'
    assert result['lower_ml']<=baseline['lower_ml'] and result['upper_ml']>=baseline['upper_ml']
    # Error to the first validation target's full [480,520] interval is120 mL/h.
    assert result['upper_ml']>=float(Fraction(1685,3))
    assert learning['nominal_coverage'] is None and learning['storage']=='request_memory_only'
    assert result['generated_at']=='2026-11-03T12:00:00.000000Z'
    assert result['research_only'] is True
    assert all('pre_mass_kg' not in key and 'predictions' not in key for key in learning)
    assert result['longitudinal_history']['method']=='regularized_duration_rate_with_historical_error_envelope'
    assert not any('Point is a deterministic median' in text or 'Recent-five weighting' in text for text in result['limitations'])
    assert any('Point is a fitted stationary' in text for text in result['limitations'])


def test_ties_cold_start_and_insufficient_history_retain_exact_baseline():
    for samples in ((),history([400.]*5),history([400.]*6),history([0.]*8)):
        result=predict(samples)
        baseline=predict_longitudinal(plan(),samples,generated_at=NOW)
        assert result['learning']['selected_method']=='existing_personal_baseline'
        assert all(result[k]==baseline[k] for k in ('status','value_ml','lower_ml','upper_ml','model_version','interval_kind'))
        assert set(result['learning'])==LEARNING_KEYS


def test_order_and_equivalent_utc_offsets_produce_identical_fit_hash_and_result():
    samples=history([300.,500.,400.,500.,400.,500.])
    shifted=tuple(replace(s,observed_at=s.observed_at.astimezone(timezone(timedelta(hours=3)))) for s in samples)
    assert predict(samples)==predict(reversed(shifted))


def test_query_duration_and_stale_history_do_not_extrapolate_learned_model():
    samples=history([300.,500.,400.,500.,400.,500.])
    for exercise,reason in ((replace(plan(),duration_minutes=90.),'outside_observed_duration_domain'),
                            (replace(plan(),starts_at=NOW+timedelta(days=30)),'beyond_observed_session_spacing')):
        result=predict(samples,exercise)
        baseline=predict_longitudinal(exercise,samples,generated_at=NOW)
        assert result['learning']['selected_method']=='existing_personal_baseline'
        assert result['learning']['reason']==reason
        assert result['value_ml']==baseline['value_ml']


def test_missing_shifted_started_and_actual_preserve_existing_behavior():
    samples=history([300.,500.,400.,500.,400.,500.])
    shifted=replace(plan(),conditions=replace(CONDITIONS,temperature_c=30.))
    started=replace(plan(),starts_at=NOW-timedelta(minutes=1))
    missing=tuple(replace(s,errors=None) for s in samples)
    actual=replace(samples[-1],event_id=plan().event_id,observed_at=NOW)
    done=replace(plan(),starts_at=NOW-timedelta(hours=1),actual=actual)
    for exercise,provided in ((shifted,samples),(started,samples),(plan(),missing),(done,samples)):
        result=predict(provided,exercise)
        baseline=predict_longitudinal(exercise,provided,generated_at=NOW)
        assert all(result[k]==baseline[k] for k in ('status','value_ml','lower_ml','upper_ml','model_version','interval_kind'))
        assert result['learning']['selected_method']=='existing_personal_baseline'
    assert predict(samples,done)['learning']['reason']=='actual_measurement_preserved'


def test_overlap_disables_learning_and_duplicate_instants_or_ids_are_rejected():
    samples=history([300.,500.,400.,500.,400.,500.])
    overlapping=tuple(replace(s,observed_at=NOW-timedelta(minutes=160-i*20)) for i,s in enumerate(samples))
    assert predict(overlapping)['learning']['reason']=='overlapping_measurement_windows'
    duplicate=(*samples[:-1],replace(samples[-1],observed_at=samples[-2].observed_at))
    with pytest.raises(CalculationError,match='duplicate_completion_time'):
        predict(duplicate)
    with pytest.raises(CalculationError):
        predict((*samples,replace(samples[-1],event_id=UUID(int=100))))
    with pytest.raises(CalculationError):
        predict((*samples,replace(samples[-1],observed_at=NOW+timedelta(days=1))))


def test_chronological_target_is_not_used_in_its_own_fit():
    from ai.forecasting.personal_runtime import _validation_rows
    samples=history([300.,500.,400.,500.,400.,500.])
    rows=_validation_rows(samples)
    altered=(*samples[:-1],replace(samples[-1],measurement=replace(samples[-1].measurement,post_mass_kg=69.)))
    other=_validation_rows(altered)
    assert rows[:-1]==other[:-1]
    assert rows[-1]['candidate_ml']==other[-1]['candidate_ml']
    assert rows[-1]['baseline_ml']==other[-1]['baseline_ml']
    assert rows[-1]['target_ml']!=other[-1]['target_ml']


def test_validation_requires_prefix_duration_support_not_just_six_rows():
    samples=history([300.,500.,400.,500.,400.,500.],[30.,35.,40.,45.,50.,60.])
    result=predict(samples)
    assert result['learning']['selected_method']=='existing_personal_baseline'
    assert result['learning']['reason']=='insufficient_chronological_validation'
    assert result['learning']['validation_folds']==0


def test_duration_weighted_fit_has_no_calendar_time_or_biometric_effect():
    from ai.forecasting.personal_runtime import _fit_rate
    samples=history([100.,450.,900.],[30.,60.,90.])
    # x=[.5,1,1.5], y=[100,450,900], r0=450, S=3.5.
    assert _fit_rate(samples)==Fraction(3425,7)
    retimed=tuple(replace(s,observed_at=s.observed_at-timedelta(days=i*10)) for i,s in enumerate(samples))
    assert _fit_rate(retimed)==_fit_rate(samples)


def test_widened_error_bounds_are_retained_even_when_candidate_is_selected():
    samples=history([300.,500.,400.,500.,400.,500.])
    widened=(*samples[:-1],replace(samples[-1],errors=replace(samples[-1].errors,pre_mass_kg=.5)))
    result=predict(widened)
    baseline=predict_longitudinal(plan(),widened,generated_at=NOW)
    assert result['lower_ml']<=baseline['lower_ml'] and result['upper_ml']>=baseline['upper_ml']
    assert result['upper_ml']>=1010.


def test_no_history_none_and_dst_ordering_keep_metadata_and_privacy():
    from ai.forecasting.personal_runtime import predict_personal_runtime
    from zoneinfo import ZoneInfo
    result=predict_personal_runtime(None,(),generated_at=NOW)
    assert result['status']=='insufficient_data' and set(result['learning'])==LEARNING_KEYS
    samples=history([300.,500.,400.,500.,400.,500.])
    ny=ZoneInfo('America/New_York')
    local=tuple(replace(s,observed_at=s.observed_at.astimezone(ny)) for s in samples)
    assert predict(local)==predict(samples)


def test_runtime_has_no_filesystem_network_or_raw_training_output(monkeypatch):
    import builtins,json,socket
    from pathlib import Path
    from ai.forecasting.personal_runtime import predict_personal_runtime
    samples=history([300.,500.,400.,500.,400.,500.])
    def forbidden(*args,**kwargs):
        pytest.fail('Pure personal fit attempted I/O')
    monkeypatch.setattr(builtins,'open',forbidden)
    monkeypatch.setattr(Path,'write_text',forbidden)
    monkeypatch.setattr(socket,'create_connection',forbidden)
    result=predict_personal_runtime(plan(),samples,generated_at=NOW)
    encoded=json.dumps(result,allow_nan=False)
    assert 'post_mass_kg' not in encoded and 'pre_mass_kg' not in encoded
    assert 'target_ml' not in encoded and 'candidate_ml' not in encoded
    assert len(result['learning']['training_sha256'])==64


def test_duration_error_can_make_close_sessions_overlap_and_disable_learning():
    samples=history([300.,500.,400.,500.,400.,500.])
    close=tuple(replace(s,observed_at=NOW-timedelta(minutes=367-i*61),
                        errors=replace(s.errors,duration_minutes=2.)) for i,s in enumerate(samples))
    assert predict(close)['learning']['reason']=='overlapping_measurement_windows'


def test_synthetic_stress_evaluation_is_reproducible_and_never_claims_real_accuracy():
    from ai.forecasting.personal_runtime import evaluate_synthetic_runtime
    first=evaluate_synthetic_runtime()
    assert first==evaluate_synthetic_runtime()
    assert first['evidence_origin']=='synthetic_software_scenarios'
    assert first['real_world_improvement'] is False
    assert set(first['scenarios'])=={'stable','unequal_duration','noisy','outlier','gradual_change','abrupt_change','condition_shift','missing_errors'}
    assert all(s['attempted_predictions']==120 for s in first['scenarios'].values())
    assert all(s['nominal_coverage'] is None for s in first['scenarios'].values())
