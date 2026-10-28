"""Caller-supplied chronological calibration; no storage, network, or cohort prior.

The recent-five median is a fixed engineering candidate, not a validated model
of physiological adaptation. Historical errors can widen, never shrink, the
existing measurement envelope. Current/future outcomes never enter a forecast.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import random
from statistics import mean, median
from uuid import UUID

from ai.hydration.models import CalculationError, WorkoutMeasurement, aware, convert_time
from ai.hydration.personal_forecast import Conditions, Exercise, MeasurementErrors, SweatSample, exercise_loss
from ai.hydration.workout import estimate_workout_loss
from .predict import predict_workout

MODEL_VERSION = 'personal-longitudinal-v2'
RECENT_WINDOW = 5
MIN_RECENT_HISTORY = 3
MAX_HISTORY = 256


def _chronological(samples: tuple[SweatSample, ...], generated_at: datetime) -> tuple[SweatSample, ...]:
    aware(generated_at, 'generated_at')
    if not isinstance(samples, tuple) or len(samples) > MAX_HISTORY:
        raise CalculationError('invalid_history', 'samples')
    current = convert_time(generated_at, timezone.utc, 'generated_at')
    seen = set()
    for sample in samples:
        if not isinstance(sample, SweatSample):
            raise CalculationError('invalid_sample', 'samples')
        observed = convert_time(sample.observed_at, timezone.utc, 'observed_at')
        if observed >= current:
            raise CalculationError('future_or_current_measurement', 'observed_at')
        # New event IDs do not turn a copied same-time measurement into new data.
        signature = (observed, sample.conditions, sample.measurement)
        if signature in seen:
            raise CalculationError('duplicate_measurement', 'samples')
        seen.add(signature)
    return tuple(sorted(samples, key=lambda s: (convert_time(s.observed_at, timezone.utc, 'observed_at'), str(s.event_id))))


def predict_longitudinal(exercise: Exercise | None, samples: tuple[SweatSample, ...] = (), *,
                         generated_at: datetime) -> dict:
    """Forecast from strictly earlier, comparable manual calibration history.

The caller retains history and must keep records separated by person. This
function neither persists samples nor treats the supplied count as validation.
Actual completed measurements are returned by the unchanged baseline engine.
"""
    ordered = _chronological(samples, generated_at)
    result = predict_workout(exercise, ordered, generated_at=generated_at)
    envelope = exercise_loss(exercise, ordered, generated_at=generated_at)
    selected_ids = set(envelope['sample_ids'])
    selected = tuple(s for s in ordered if str(s.event_id) in selected_ids)
    recent = selected[-RECENT_WINDOW:]
    result['longitudinal_history'] = {
        'total_samples': len(ordered), 'comparable_samples': len(selected),
        'recent_samples': len(recent),
        'first_observed_at': convert_time(selected[0].observed_at, timezone.utc, 'observed_at').isoformat() if selected else None,
        'last_observed_at': convert_time(selected[-1].observed_at, timezone.utc, 'observed_at').isoformat() if selected else None,
        'method': 'recent_comparable_median_with_historical_error_envelope',
        'history_retained_by_caller': True,
    }
    result['limitations'] += [
        'Longitudinal history is supplied by the caller; this calculation does not store or automatically collect measurements.',
        'Recent-five weighting is an engineering hypothesis, not independently validated physiological adaptation.',
        'Past measurements and errors cannot guarantee coverage of future variation or unreported condition changes.',
    ]
    if exercise is not None and exercise.actual is not None:
        return result
    result['model_version'] = MODEL_VERSION
    result['interval_kind'] = 'historical_error_envelope'
    if result['status'] != 'estimated':
        return result
    rates = [estimate_workout_loss(s.measurement).sweat_rate_ml_per_hour for s in selected]
    if len(selected) < MIN_RECENT_HISTORY:
        result['personalization_status'] = 'limited_personal_history'
        result['data_sufficiency'] = 'limited_comparable_history'
        return result
    center = median(rates[-RECENT_WINDOW:]) * exercise.duration_minutes / 60.
    # Every residual uses only observations preceding that outcome. Re-evaluate
    # at each request; no fitted private state, population label, or future data.
    past_rate_errors = [abs(rate - median(rates[max(0, i-RECENT_WINDOW):i]))
                        for i, rate in enumerate(rates) if i]
    radius = max(past_rate_errors, default=0.) * exercise.duration_minutes / 60.
    lower = min(result['lower_ml'], max(0., center-radius))
    upper = max(result['upper_ml'], center+radius)
    if not all(math.isfinite(v) for v in (center, lower, upper)):
        result.update(status='insufficient_data', value_ml=None, lower_ml=None, upper_ml=None,
                      data_sufficiency='numeric_overflow', personalization_status='unavailable')
        return result
    result.update(value_ml=center, lower_ml=lower, upper_ml=upper,
        personalization_status='longitudinal_personal_calibration',
        data_sufficiency='comparable_history_not_clinically_validated')
    result['limitations'].append('Range is the union of the full measurement envelope and maximum past one-step error; it is not a calibrated prediction interval.')
    return result


def _scores(rows: list[dict], system: str) -> dict:
    available = [r for r in rows if r[system+'_ml'] is not None and r['target_ml'] is not None]
    errors = [r[system+'_ml']-r['target_ml'] for r in available]
    return {
        'n': len(errors),
        'mae_ml': mean(abs(e) for e in errors) if errors else None,
        'rmse_ml': math.sqrt(mean(e*e for e in errors)) if errors else None,
        'bias_ml': mean(errors) if errors else None,
        'empirical_interval_coverage': mean(r[system+'_lower_ml'] <= r['target_ml'] <= r[system+'_upper_ml'] for r in available) if available else None,
        'prediction_coverage': len(available)/len(rows) if rows else 0.,
    }


def evaluate_prequential(histories: dict[str, tuple[SweatSample, ...]], *, synthetic: bool) -> dict:
    """Predict before each workout, score after it, then expose it to later steps.

This evaluates a fixed rule, not selection/training. No current measured mass or
intake is passed as a forecasting feature. Duration/conditions are assumed known
before each workout; retrospective datasets must justify that assumption.
"""
    if type(synthetic) is not bool or not isinstance(histories, dict) or not histories:
        raise ValueError('explicit_nonempty_evaluation_origin_required')
    predictions = []
    for user, samples in sorted(histories.items()):
        if not isinstance(user, str) or not user or not isinstance(samples, tuple) or not samples:
            raise ValueError('invalid_evaluation_history')
        if any(not isinstance(s, SweatSample) for s in samples):
            raise ValueError('invalid_evaluation_sample')
        last = max(convert_time(s.observed_at, timezone.utc, 'observed_at') for s in samples)
        try:
            after_last = last+timedelta(microseconds=1)
        except OverflowError:
            raise CalculationError('invalid_time', 'observed_at') from None
        ordered = _chronological(samples, after_last)
        past: list[SweatSample] = []
        for index, sample in enumerate(ordered):
            duration = sample.measurement.duration_minutes
            if duration is None:
                raise ValueError('evaluation_requires_known_planned_duration')
            try:
                start = convert_time(sample.observed_at, timezone.utc, 'observed_at') - timedelta(minutes=duration)
            except (OverflowError, ValueError):
                raise CalculationError('invalid_time', 'observed_at') from None
            # Overlapping/completed-at-start records are not available before
            # forecast generation. The target observation is never in this list.
            available = tuple(s for s in past if convert_time(s.observed_at, timezone.utc, 'observed_at') < start)
            planned = Exercise(sample.event_id, start, duration, sample.conditions, True)
            baseline = predict_workout(planned, available, generated_at=start)
            adaptive = predict_longitudinal(planned, available, generated_at=start)
            target = estimate_workout_loss(sample.measurement)
            predictions.append({
                'participant_id': user, 'step': index,
                'generated_at': start.astimezone(timezone.utc).isoformat(),
                'observed_at': convert_time(sample.observed_at, timezone.utc, 'observed_at').isoformat(),
                'target_ml': target.estimated_loss_ml,
                'baseline_ml': baseline['value_ml'], 'adaptive_ml': adaptive['value_ml'],
                'baseline_lower_ml': baseline['lower_ml'], 'baseline_upper_ml': baseline['upper_ml'],
                'adaptive_lower_ml': adaptive['lower_ml'], 'adaptive_upper_ml': adaptive['upper_ml'],
                'available_prior_samples': len(available),
            })
            past.append(sample)
    per_user = {}
    for user in sorted(histories):
        rows = [r for r in predictions if r['participant_id'] == user]
        scores = {name: _scores(rows, name) for name in ('baseline', 'adaptive')}
        before, after = scores['baseline']['mae_ml'], scores['adaptive']['mae_ml']
        per_user[user] = scores | {'adaptive_minus_baseline_mae_ml': None if before is None or after is None else after-before}
    return {
        'origin': 'synthetic' if synthetic else 'user_calibration_measurements',
        'attempted_predictions': len(predictions),
        'scored_predictions': sum(r['adaptive_ml'] is not None and r['target_ml'] is not None for r in predictions),
        'systems': {name: _scores(predictions, name) for name in ('baseline', 'adaptive')},
        'per_user': per_user, 'predictions': predictions,
        'limitations': ['Chronological within-person evaluation, not unseen-person clinical validation.',
            'Outcome is a mass-balance estimate, not physiological ground truth.',
            'The strategy and window were fixed before this evaluation; no score-based model selection.'],
    }


def evaluate_synthetic_histories(seed: int = 20261029) -> dict:
    """Software stress scenarios with declared invented trajectories, never fit."""
    rng = random.Random(seed)
    scenarios = {}
    start = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    for scenario in ('stable', 'gradual_change', 'abrupt_change', 'condition_shift'):
        histories = {}
        for user in range(10):
            samples = []
            for step in range(12):
                rate = 300.+20.*user
                if scenario == 'gradual_change':
                    rate += 35.*step
                elif scenario == 'abrupt_change' and step >= 6:
                    rate += 250.
                elif scenario == 'condition_shift' and step >= 6:
                    rate += 250.
                measured = rate+rng.uniform(-15., 15.)
                temperature = 30. if scenario == 'condition_shift' and step >= 6 else 24.
                samples.append(SweatSample(UUID(int=user*100+step+1), start+timedelta(days=step*3),
                    Conditions('running', 'moderate', temperature, 50.),
                    WorkoutMeasurement(70., 70.-measured/1000., 0., 0., 60., True, ('synthetic_longitudinal_scenario',)),
                    MeasurementErrors(.01, .01, 0., 0., 0., ('synthetic_assumed_error_bound',))))
            histories[f'simulated-{user:02}'] = tuple(samples)
        scenarios[scenario] = evaluate_prequential(histories, synthetic=True)
    return {'schema_version': 'longitudinal-evaluation-v2', 'seed': seed,
        'real_world_improvement': False, 'scenarios': scenarios,
        'assumptions': ['Invented 300+20*user mL/h base rates and 60-minute workouts.',
            'Gradual +35 mL/h per workout; abrupt/condition shift +250 mL/h after six workouts.',
            'Uniform +/-15 mL observation noise and +/-10 g per weighing are simulation assumptions.',
            'No effects are attributed to temperature, supplements, HR, HRV, or thirst; condition shift is a scenario label.']}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = evaluate_synthetic_histories()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False)+'\n')
    print(json.dumps({name: value['systems'] for name, value in report['scenarios'].items()}, indent=2))


if __name__ == '__main__':
    main()
