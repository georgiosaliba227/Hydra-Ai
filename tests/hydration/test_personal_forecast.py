"""Independent numeric interval fixtures and failure cases; no clinical validation."""
from dataclasses import replace
from datetime import date, datetime, timezone
from fractions import Fraction
import socket
from uuid import UUID

import pytest

from ai.hydration.models import BeverageLog, CalculationError, Composition, WorkoutMeasurement
from ai.hydration.personal_forecast import (Conditions, Exercise, MeasurementErrors, SweatSample,
    exercise_loss, forecast_personal, _outward)

NOW = datetime(2026,10,27,12,tzinfo=timezone.utc)
CONDITIONS = Conditions('running','moderate',20,60)


def sample(identifier=1, **changes):
    values = dict(event_id=UUID(int=identifier), observed_at=NOW.replace(day=26), conditions=CONDITIONS,
        measurement=WorkoutMeasurement(70,69,400,0,60,True,('synthetic-weighing',)),
        errors=MeasurementErrors(.05,.05,10,0,0,('synthetic-instrument-bounds',)))
    return SweatSample(**(values | changes))


def exercise(**changes):
    values=dict(event_id=UUID(int=9),starts_at=NOW.replace(hour=14),duration_minutes=30,
                conditions=CONDITIONS,comparable_conditions_confirmed=True)
    return Exercise(**(values | changes))


def log(identifier=1, **changes):
    values=dict(id=UUID(int=identifier),revision=1,category='tea',consumed_ml=250,
        consumed_at=NOW.replace(day=26),timezone='UTC',source='manual',provenance=('manual',))
    return BeverageLog(**(values | changes))


def result(**changes):
    values=dict(logs=(),local_date=date(2026,10,27),timezone='UTC',generated_at=NOW,
                exercise=exercise(),samples=(sample(),))
    return forecast_personal(**(values | changes))


def test_independent_mass_error_fixture_and_daily_fallback():
    # Loss: (70-69)*1000+400=1400; error=.1kg*1000+10=110.
    # A 30-minute projection of the 60-minute measurement: [645,755].
    value=result()
    assert value['exercise_loss']['lower_ml'] == 645
    assert value['exercise_loss']['upper_ml'] == 755
    assert value['daily_requirement']['status'] == 'insufficient_data'
    assert value['daily_requirement']['lower_ml'] is None
    assert value['prediction_validated'] is False


def test_repeated_history_envelope_and_duration_uncertainty():
    other=sample(2,measurement=WorkoutMeasurement(70,68.8,400,0,60,True,('repeat',)))
    value=result(samples=(sample(),other))['exercise_loss']
    assert (value['lower_ml'],value['upper_ml'],value['sample_count']) == (645,855,2)
    uncertain=sample(errors=MeasurementErrors(.05,.05,10,0,1,('duration-bound',)))
    value=result(samples=(uncertain,))['exercise_loss']
    assert value['lower_ml'] == pytest.approx(1290*30/61)
    assert value['upper_ml'] == pytest.approx(1510*30/59)


@pytest.mark.parametrize('change',[dict(errors=None),dict(measurement=WorkoutMeasurement(70,69,400,None,60,True,('source',))),
    dict(measurement=WorkoutMeasurement(70,69,400,0,60,False,('source',))),
    dict(errors=MeasurementErrors(0,0,0,0,60,('bad-duration',)))])
def test_missing_measurement_or_uncertainty_blocks_estimate(change):
    value=result(samples=(sample(**change),))['exercise_loss']
    assert value['status'] == 'insufficient_data' and value['lower_ml'] is None


@pytest.mark.parametrize('conditions',[replace(CONDITIONS,temperature_c=21),replace(CONDITIONS,humidity_percent=None),
    replace(CONDITIONS,intensity='high'),replace(CONDITIONS,activity='cycling')])
def test_environment_intensity_activity_not_arbitrary_multipliers(conditions):
    value=result(samples=(sample(conditions=conditions),))['exercise_loss']
    assert value['status'] == 'insufficient_data' and len(value['excluded_samples']) == 1


def test_comparability_and_missing_target_weather_required():
    assert result(exercise=exercise(comparable_conditions_confirmed=False))['exercise_loss']['status'] == 'insufficient_data'
    assert result(exercise=exercise(conditions=replace(CONDITIONS,temperature_c=None)))['exercise_loss']['status'] == 'insufficient_data'


def test_actual_replaces_planned_and_uses_actual_duration():
    actual=sample(9,observed_at=NOW.replace(hour=11))
    value=result(exercise=exercise(starts_at=NOW.replace(hour=10),duration_minutes=120,actual=actual))['exercise_loss']
    assert value['basis'] == 'actual_replaces_planned'
    assert (value['lower_ml'],value['upper_ml'],value['sample_count']) == (1290,1510,1)


def test_started_workout_needs_actual_measurement():
    assert result(exercise=exercise(starts_at=NOW.replace(hour=10)))['exercise_loss']['status'] == 'insufficient_data'


@pytest.mark.parametrize('samples',[ (sample(),sample()), (sample(observed_at=NOW.replace(day=28)),), (sample(9),) ])
def test_duplicate_and_future_events_rejected(samples):
    with pytest.raises(CalculationError): result(samples=samples)


def test_actual_event_cannot_also_be_history():
    actual=sample(9,observed_at=NOW.replace(hour=11))
    with pytest.raises(CalculationError): result(exercise=exercise(starts_at=NOW.replace(hour=10),actual=actual),samples=(actual,))


def test_history_and_composition_unknowns_preserved():
    entries=(log(),log(2,consumed_at=NOW.replace(day=25),consumed_ml=500,
        nutrition=Composition(100,('verified-fixture',),water_ml=95)))
    value=result(logs=entries)['historical_logged_intake']
    assert (value['logged_days'],value['days_without_logs'],value['beverage_lower_ml'],value['beverage_upper_ml']) == (2,5,250,500)
    assert value['days'][0]['estimated_water_ml'] == 475
    assert value['days'][1]['estimated_water_ml'] is None


def test_local_day_history_selection_and_revisions():
    value=result(logs=(log(consumed_at=NOW.replace(hour=1)),),timezone='America/New_York')
    assert value['historical_logged_intake']['days'][0]['local_date'] == date(2026,10,26)
    assert value['historical_logged_intake']['days'][0]['log_revisions'] == ((UUID(int=1),1),)
    assert value['intake']['beverage_total_ml'] == 0


def test_feedback_and_wearable_duration_do_not_change_loss():
    a=result()['exercise_loss']; b=result(exercise=exercise(feedback='thirst_reported',duration_source='wearable_aggregate'))['exercise_loss']
    assert (a['lower_ml'],a['upper_ml']) == (b['lower_ml'],b['upper_ml'])
    assert b['duration_source'] == 'wearable_aggregate'


def test_outward_rounding_cannot_narrow_exact_bounds():
    for value in (Fraction(1,3),Fraction(1,10),Fraction(123456789,7)):
        assert Fraction.from_float(_outward(value,upper=False)) <= value
        assert Fraction.from_float(_outward(value,upper=True)) >= value


@pytest.mark.parametrize('kwargs',[dict(duration_minutes=True),dict(comparable_conditions_confirmed=1),dict(duration_source='heart_rate'),dict(feedback='dehydrated')])
def test_invalid_core_inputs(kwargs):
    with pytest.raises(CalculationError): exercise(**kwargs)


def test_future_logs_and_no_network(monkeypatch):
    def forbidden(*args,**kwargs): raise AssertionError('No external connection')
    monkeypatch.setattr(socket,'create_connection',forbidden)
    assert result()['exercise_loss']['status'] == 'estimated'
    with pytest.raises(CalculationError): result(logs=(log(consumed_at=NOW.replace(day=28)),))


def test_dst_fold_temporal_checks_use_instants():
    from zoneinfo import ZoneInfo
    zone=ZoneInfo('America/New_York')
    early=datetime(2026,11,1,1,45,tzinfo=zone,fold=0)
    later=datetime(2026,11,1,1,15,tzinfo=zone,fold=1)
    # Later absolute instant despite an earlier displayed wall-clock time.
    with pytest.raises(CalculationError):
        exercise_loss(exercise(starts_at=later), (sample(observed_at=later),), generated_at=early)


def test_history_underflow_has_typed_error():
    with pytest.raises(CalculationError): result(local_date=date.min)


def test_measurement_interval_crossing_zero_stays_nonnegative():
    value=result(samples=(sample(measurement=WorkoutMeasurement(70,70,0,0,60,True,('source',))),))['exercise_loss']
    assert value['lower_ml'] == 0 and value['upper_ml'] == 55
