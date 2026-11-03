"""Request-memory personal duration regression selected by earlier workout errors.

This stationary research learner has no time trend, cohort prior, weather effect,
provider access or prediction persistence. Existing v1/v2 functions stay intact.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import random
from statistics import mean, median, stdev
from uuid import UUID

from ai.hydration.models import CalculationError, WorkoutMeasurement, convert_time, exact, representable
from ai.hydration.personal_forecast import Conditions, Exercise, MeasurementErrors, SweatSample, _interval, _outward, exercise_loss
from .longitudinal import _chronological, predict_longitudinal

VERSION = 'personal-runtime-rate-v1'
ALPHA = Fraction(1)
MIN_HISTORY = 6
MIN_PRIOR = 3
MIN_FOLDS = 3
LIMITATIONS = [
    'Research-only stationary personal duration regression; no independent measured longitudinal accuracy established.',
    'Earlier within-person selection errors overlap and do not establish prospective improvement or clinical validity.',
    'No calendar-time trend, population prior, learned weather or biometric adjustment, diagnosis or intake requirement.',
    'Freshness and duration support are empirical engineering gates, not biological validity thresholds.',
    'The range preserves measurement and historical errors; it has no nominal future coverage guarantee or sample-count contraction.',
    'History remains caller-owned; the fit and its fingerprint exist in request memory only and must not be sent to Meta or logged.',
]


def _stamp(value: datetime) -> str:
    return convert_time(value, timezone.utc, 'timestamp').isoformat(timespec='microseconds').replace('+00:00','Z')


def _loss(sample: SweatSample) -> Fraction:
    m = sample.measurement
    return (exact(m.pre_mass_kg)-exact(m.post_mass_kg))*1000+exact(m.consumed_ml)-exact(m.urine_ml)


def _fit_rate(samples: tuple[SweatSample, ...]) -> Fraction:
    """Minimize sum((y-r*x)^2) + S*(r-median(y/x))^2, x in hours."""
    hours = [exact(sample.measurement.duration_minutes)/60 for sample in samples]
    losses = [_loss(sample) for sample in samples]
    squared = sum((x*x for x in hours), Fraction())
    robust = median(y/x for x,y in zip(hours,losses,strict=True))
    return (sum((x*y for x,y in zip(hours,losses,strict=True)),Fraction())+ALPHA*squared*robust)/((1+ALPHA)*squared)


def _earliest_start(sample: SweatSample) -> datetime:
    # Round the duration's upper bound outward to the microsecond. A future
    # outcome cannot leak into a prefix through rounding a start time later.
    minutes = exact(sample.measurement.duration_minutes)+exact(sample.errors.duration_minutes)
    try:
        return convert_time(sample.observed_at,timezone.utc,'observed_at')-timedelta(microseconds=math.ceil(minutes*60_000_000))
    except (OverflowError,ValueError):
        raise CalculationError('invalid_time','samples') from None


def _validation_rows(samples: tuple[SweatSample, ...]) -> list[dict]:
    """Private RAM-only fold details; the API returns aggregate metrics only."""
    rows=[]
    for index,target in enumerate(samples):
        at=_earliest_start(target)
        prior=tuple(sample for sample in samples[:index]
                    if convert_time(sample.observed_at,timezone.utc,'observed_at') < at)
        if len(prior)<MIN_PRIOR:
            continue
        duration=target.measurement.duration_minutes
        durations=[sample.measurement.duration_minutes for sample in prior]
        if not min(durations)<=duration<=max(durations):
            continue
        planned=Exercise(target.event_id,at,duration,target.conditions,True)
        baseline=predict_longitudinal(planned,prior,generated_at=at)
        if baseline['status']!='estimated':
            continue
        rate=_fit_rate(prior)
        point=representable(rate*exact(duration)/60,'personal_prediction')
        interval=_interval(target)
        rows.append({'candidate_ml':point,'baseline_ml':baseline['value_ml'],
                     'target_ml':representable(_loss(target),'personal_target'),
                     'maximum_rate_endpoint_error':max(abs(rate-interval[2]),abs(rate-interval[3]))})
    return rows


def _fingerprint(samples: tuple[SweatSample,...]) -> str:
    def canonical(value):
        if isinstance(value,datetime): return _stamp(value)
        if isinstance(value,UUID): return str(value)
        if type(value) in (int,float): return str(exact(value))
        if isinstance(value,dict): return {key:canonical(item) for key,item in value.items()}
        if isinstance(value,(tuple,list)): return [canonical(item) for item in value]
        return value
    payload={'version':VERSION,'alpha':str(ALPHA),'samples':[canonical(asdict(sample)) for sample in samples]}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def predict_personal_runtime(exercise: Exercise | None, samples: tuple[SweatSample,...]=(), *, generated_at: datetime) -> dict:
    """Fit/serve the candidate only when earlier comparable own errors support it.

    Original median/envelope numerics remain exact on fallback and actual paths.
    No supplied outcome for the current planned exercise is used as a feature.
    """
    ordered=_chronological(samples,generated_at)
    result=predict_longitudinal(exercise,ordered,generated_at=generated_at)
    learning={
        'version':VERSION,'selected_method':'existing_personal_baseline','reason':'baseline_unavailable',
        'training_samples':0,'validation_folds':0,'fitted_rate_ml_per_hour':None,'ridge_alpha':1.0,
        'supported_duration_minutes':{'minimum':None,'maximum':None},
        'baseline_mae_ml':None,'candidate_mae_ml':None,'paired_gain_ml':None,'gain_standard_error_ml':None,
        'training_sha256':None,'cadence_max_gap_seconds':None,'storage':'request_memory_only',
        'validation_origin':'earlier_own_measurements','nominal_coverage':None,
    }
    result.update(learning=learning,generated_at=_stamp(generated_at),research_only=True)
    result['limitations']+=LIMITATIONS
    if exercise is not None and exercise.actual is not None:
        learning['reason']='actual_measurement_preserved'
        return result
    instants=[convert_time(sample.observed_at,timezone.utc,'observed_at') for sample in ordered]
    if len(set(instants))!=len(instants):
        raise CalculationError('duplicate_completion_time','samples')
    if result['status']!='estimated' or exercise is None:
        return result
    envelope=exercise_loss(exercise,ordered,generated_at=generated_at)
    usable=set(envelope['sample_ids'])
    selected=tuple(sample for sample in ordered if str(sample.event_id) in usable)
    learning['reason']='insufficient_comparable_history'
    if len(selected)<MIN_HISTORY:
        return result
    durations=[sample.measurement.duration_minutes for sample in selected]
    learning['supported_duration_minutes']={'minimum':float(min(durations)),'maximum':float(max(durations))}
    if any(convert_time(earlier.observed_at,timezone.utc,'observed_at') >= _earliest_start(later)
           for earlier,later in zip(selected,selected[1:])):
        learning['reason']='overlapping_measurement_windows'
        return result
    if not min(durations)<=exercise.duration_minutes<=max(durations):
        learning['reason']='outside_observed_duration_domain'
        return result
    selected_instants=[convert_time(sample.observed_at,timezone.utc,'observed_at') for sample in selected]
    gaps=[later-earlier for earlier,later in zip(selected_instants,selected_instants[1:]) if later>earlier]
    if len(gaps)<3:
        learning['reason']='insufficient_chronological_validation'
        return result
    maximum_gap=max(gaps)
    learning['cadence_max_gap_seconds']=maximum_gap.total_seconds()
    if convert_time(exercise.starts_at,timezone.utc,'starts_at')-selected_instants[-1]>maximum_gap:
        learning['reason']='beyond_observed_session_spacing'
        return result
    try:
        rows=_validation_rows(selected)
        learning['validation_folds']=len(rows)
        if len(rows)<MIN_FOLDS:
            learning['reason']='insufficient_chronological_validation'
            return result
        rate=_fit_rate(selected)
        point=representable(rate*exact(exercise.duration_minutes)/60,'personal_prediction')
        gains=[abs(row['baseline_ml']-row['target_ml'])-abs(row['candidate_ml']-row['target_ml']) for row in rows]
        gain=mean(gains); standard_error=stdev(gains)/math.sqrt(len(gains))
        learning.update(training_samples=len(selected),fitted_rate_ml_per_hour=representable(rate,'personal_rate'),
            baseline_mae_ml=mean(abs(row['baseline_ml']-row['target_ml']) for row in rows),
            candidate_mae_ml=mean(abs(row['candidate_ml']-row['target_ml']) for row in rows),
            paired_gain_ml=gain,gain_standard_error_ml=standard_error,training_sha256=_fingerprint(selected),
            reason='baseline_retained_after_validation')
        if not gain>max(standard_error,1e-9):
            return result
        # Endpoint residuals include the target's full independently bounded
        # measurement-rate interval. No division by sqrt(n) or nominal quantile.
        radius=max(row['maximum_rate_endpoint_error'] for row in rows)*exact(exercise.duration_minutes)/60
        center=rate*exact(exercise.duration_minutes)/60
        lower=min(result['lower_ml'],_outward(max(Fraction(),center-radius),upper=False))
        upper=max(result['upper_ml'],_outward(center+radius,upper=True))
        if not all(math.isfinite(value) for value in (point,lower,upper)):
            raise CalculationError('numeric_overflow','personal_model')
    except (CalculationError,OverflowError,ValueError,ZeroDivisionError):
        learning['reason']='nonfinite_candidate'
        return result
    learning.update(selected_method='regularized_duration_rate',reason='selected_by_earlier_error_comparison')
    result.update(value_ml=point,lower_ml=lower,upper_ml=upper,model_version=VERSION,
        interval_kind='personal_runtime_measurement_error_envelope',personalization_status='fitted_personal_rate',
        data_sufficiency='earlier_own_measurements_research_only')
    result['longitudinal_history']['method']='regularized_duration_rate_with_historical_error_envelope'
    result['limitations']=[text for text in result['limitations']
        if text not in (
            'Point is a deterministic median of comparable measured rates; the range is not a calibrated future prediction interval.',
            'Recent-five weighting is an engineering hypothesis, not independently validated physiological adaptation.',
        )]
    result['limitations'].append('Point is a fitted stationary through-origin duration regression, regularized toward the same training person\'s robust rate; earlier error selection is research-only.')
    return result


def _synthetic_scores(rows: list[dict], method: str) -> dict:
    errors=[row[method]['value_ml']-row['target_ml'] for row in rows]
    included=[row[method]['lower_ml']<=row['target_ml']<=row[method]['upper_ml'] for row in rows]
    return {
        'n':len(errors),
        'mae_ml':mean(abs(error) for error in errors) if errors else None,
        'rmse_ml':math.sqrt(mean(error*error for error in errors)) if errors else None,
        'bias_ml':mean(errors) if errors else None,
        'empirical_point_inclusion_count':sum(included),
        'empirical_point_inclusion_fraction':mean(included) if included else None,
    }


def evaluate_synthetic_runtime(seed: int=20261103) -> dict:
    """Fixed invented prequential stress protocol; aggregate software evidence only.

    The fit, gates and alpha were frozen before these scenarios were evaluated.
    The current workout's loss/error bounds enter history only after prediction.
    No real records, learned physiology or nominal-coverage claim is involved.
    """
    rng=random.Random(seed)
    scenarios={}
    origin=datetime(2026,1,1,12,tzinfo=timezone.utc)
    names=('stable','unequal_duration','noisy','outlier','gradual_change','abrupt_change','condition_shift','missing_errors')
    for scenario in names:
        paired=[]; selected=[]; reasons={}; deteriorated=0; attempted=0
        for person in range(10):
            past=[]; person_rows=[]
            for step in range(12):
                duration=(30.,45.,60.,90.)[step%4] if scenario=='unequal_duration' else 60.
                rate=300.+20.*person
                if scenario=='gradual_change': rate+=30.*step
                if scenario in ('abrupt_change','condition_shift') and step>=6: rate+=200.
                amplitude=150. if scenario=='noisy' else (30. if scenario=='unequal_duration' else 10.)
                # Noise represents invented true between-workout variation,
                # distinct from the independently assumed measurement bounds.
                loss=max(0.,rate*duration/60.+rng.uniform(-amplitude,amplitude))
                if scenario=='outlier' and step==4: loss+=500.
                temperature=30. if scenario=='condition_shift' and step>=6 else 22.
                conditions=Conditions('running','moderate',temperature,55.)
                completion=origin+timedelta(days=2*step)
                start=completion-timedelta(minutes=duration)
                event=UUID(int=1+person*100+step)
                planned=Exercise(event,start,duration,conditions,True)
                baseline=predict_longitudinal(planned,tuple(past),generated_at=start)
                runtime=predict_personal_runtime(planned,tuple(past),generated_at=start)
                attempted+=1
                reason=runtime['learning']['reason']; reasons[reason]=reasons.get(reason,0)+1
                row={'baseline':baseline,'runtime':runtime,'target_ml':loss}
                if baseline['status']=='estimated' and runtime['status']=='estimated':
                    paired.append(row); person_rows.append(row)
                    if runtime['learning']['selected_method']=='regularized_duration_rate': selected.append(row)
                error=.2 if scenario=='outlier' and step==4 else .01
                bounds=MeasurementErrors(error,error,0.,0.,0.,('invented_software_bounds',))
                if scenario=='missing_errors' and step%4==0: bounds=None
                measured=WorkoutMeasurement(70.,70.-loss/1000.,0.,0.,duration,True,('invented_software_measurement',))
                past.append(SweatSample(event,completion,conditions,measured,bounds))
            before=_synthetic_scores(person_rows,'baseline')['mae_ml']
            after=_synthetic_scores(person_rows,'runtime')['mae_ml']
            deteriorated+=before is not None and after>before
        scores={method:_synthetic_scores(paired,method) for method in ('baseline','runtime')}
        scenarios[scenario]={
            'attempted_predictions':attempted,'paired_scored_predictions':len(paired),
            'prediction_fraction':len(paired)/attempted,'selected_candidate_predictions':len(selected),
            'selection_reason_counts':dict(sorted(reasons.items())), 'nominal_coverage':None,
            'systems':scores,
            'runtime_minus_baseline_mae_ml':scores['runtime']['mae_ml']-scores['baseline']['mae_ml'],
            'synthetic_trajectories_with_worse_runtime_mae':deteriorated,
            'selected_prediction_subset':{method:_synthetic_scores(selected,method) for method in ('baseline','runtime')},
        }
    return {
        'version':'personal-runtime-synthetic-v1','model_version':VERSION,'seed':seed,
        'evidence_origin':'synthetic_software_scenarios','real_world_improvement':False,
        'protocol':{
            'algorithm_frozen_before_scenarios':True,'people_per_scenario':10,'workouts_per_person':12,
            'spacing_days':2,'base_rate_ml_per_hour':'300 + 20 * invented_person_index',
            'duration_minutes':60.,'unequal_duration_minutes_cycle':[30.,45.,60.,90.],
            'true_between_workout_uniform_variation_ml':{'default':10.,'unequal_duration':30.,'noisy':150.},
            'gradual_rate_change_per_workout_ml_per_hour':30.,'step_change_after_six_ml_per_hour':200.,
            'outlier_added_loss_at_fifth_workout_ml':500.,
            'assumed_independent_mass_error_kg_per_endpoint':.01,'outlier_endpoint_error_kg':.2,
            'missing_errors':'every fourth workout, starting with the first',
            'condition_shift':'22 to 30 degrees C after six workouts; declared context change, no causal weather effect',
            'validation':'before each workout, predict using strictly earlier completed measurements; append outcome afterward',
            'selection':'fixed alpha=1; >=6 qualified distinct sessions and >=3 earlier folds; mean paired gain > max(standard error, 1e-9)',
        },
        'scenarios':scenarios,
        'limitations':LIMITATIONS+[
            'All people, measurements, rates, variations, error bounds and condition changes are invented software inputs.',
            'Pooled workout errors and within-person folds are dependent; standard errors here are selection heuristics, not significance tests.',
            'Point inclusion is a marginal count across scored synthetic workouts, not participant simultaneous coverage or a validated future probability.',
            'Selected-subset scores are descriptive and selection-conditioned; no tuning or promotion follows these outcomes.',
        ],
    }


def main() -> None:
    parser=argparse.ArgumentParser(description='Reproduce aggregate invented personal-runtime stress evaluation; no external I/O or data required.')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=evaluate_synthetic_runtime()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n')


if __name__=='__main__':
    main()
