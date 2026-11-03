# Stationary personal runtime research learner

Implemented November 3, 2026 in `ai/forecasting/personal_runtime.py`. This closes
the runtime fitting implementation gap: each request can fit a real coefficient
from the caller's earlier comparable measurements and select it against the
existing v2 personal baseline. It does **not** establish measured longitudinal
accuracy. There is no suitable independent repeated-person dataset with verified
chronology, corrected whole-workout loss and individual measurement bounds in
the current public-data inventory. EPL is a separate study of 31 distinct people;
QDE's cumulative readings within a workout are not longitudinal workouts.

The existing offline calendar-trend candidate is a different hypothesis. Its
failure modes do not justify promoting a time trend. This learner has one
stationary duration coefficient, no time trend, learned weather/biometric
effects, cohort prior, neural model or cross-study pooling. It neither recommends
drinking quantities nor diagnoses a physiological state. API/iPhone integration
is an additive orchestrator-owned v3 extension; this module changes no v1/v2
implementation or existing frozen study artifact.

## Fixed fit and selection

For qualified earlier measurements, let `x_i = duration_minutes_i / 60` hours and
`y_i = 1000 * (pre_mass_kg_i - post_mass_kg_i) + consumed_ml_i - urine_ml_i` mL.
The mass-balance result is a measurement proxy with unresolved non-water mass
changes, rather than physiological ground truth. Post-mass, consumption and urine
calculate the training target; they are never features of the future workout.

With `S = sum(x_i²)`, `r_0 = median(y_i / x_i)` and fixed `alpha = 1`, minimize

`sum((y_i - r*x_i)²) + alpha*S*(r - r_0)²`.

The exact minimizer is
`r = (sum(x_i*y_i) + alpha*S*r_0) / ((1 + alpha)*S)`, in mL/hour. The planned
point is `r * planned_duration_minutes / 60`. Fraction arithmetic preserves
decimal inputs through fitting and interval construction; output conversion
rejects unrepresentable numbers. `S` scales the regularizer consistently with
the squared-loss term; alpha is fixed, never tuned against the reported scenarios.
The robust anchor uses only this person's same training prefix. No population or
incompatible study target supplies an invented initial rate.

The candidate requires all of the following:

1. At least six usable distinct sessions with explicit protocol confirmation,
   independent measurement-error bounds and exactly matching complete activity,
   intensity, temperature and humidity context. The caller additionally confirms
   comparability of environment, equipment and acclimatization under the existing
   core contract. Exact condition matching is a support restriction, not a fitted
   environmental effect.
2. Nonoverlapping measurement windows. A historical start is the completion time
   minus the upper duration bound, rounded outward to a microsecond. Touching or
   overlapping windows disable the learned mode. Core validation rejects repeated
   IDs and copied same-time measurements; v3 also rejects duplicate completion
   instants even when other fields differ. Caller history must remain separated
   by person; there is no inferred identity or private persistent model store.
3. A planned duration inside the closed minimum/maximum of usable durations.
   There is no learned extrapolation outside this observed support.
4. At least three positive observed completion spacings. The planned start minus
   the most recent completion cannot exceed the largest observed spacing. This
   maximum-gap rule is an empirical cadence gate, **not** a biological freshness
   threshold; an unusually long historical gap can make it permissive.
5. At least three eligible chronological validation folds. Starting at three
   prior observations, each target is predicted using only samples completed
   strictly before its earliest possible start. Its duration must be inside that
   prefix's duration support. The exact existing v2 baseline and candidate are
   recomputed on the same prefix; no target loss enters its own fit or anchor.
6. Let each paired gain be baseline absolute error minus candidate absolute
   error. Select the candidate only if its mean gain exceeds both `1e-9` mL and
   `sample_standard_deviation(gains) / sqrt(number_of_folds)`. Otherwise retain
   the v2 point and bounds. Overlapping prefixes make this an engineering
   selection heuristic, not significance testing or independent validation.

The final rate is fitted on all eligible earlier samples only after sufficient
folds exist. Missing/shifted conditions, missing errors, unsupported duration,
stale history, overlap, numerical problems or insufficient evidence retain the
existing baseline or its abstention. A started workout still requires an actual
measurement. Completed actual measurements retain their v1 result and are never
replaced by a regression estimate. `training_samples` counts the final model's
actual fit rows, including when validation retains the baseline; it is zero when
no final fit was attempted. It is not a count of all supplied records.

## Range and limitations

Each eligible fold's held-out measured rate has its full independently bounded
interval `[a_j, b_j]`. The candidate historical radius in rate units is
`max_j(max(abs(r_prefix_j-a_j), abs(r_prefix_j-b_j)))`. Scale that radius by the
query's planned duration and take the hull of the nonnegative candidate range,
the current fitted point and the full v2 range. The v2 range already includes the
full historical measurement envelope and its earlier baseline errors. No
standard-error or sample-count factor shrinks the measurement/range bounds.

This is a conservative empirical construction relative to those supplied
envelopes, not a calibrated future prediction interval. It preserves the current
v2 envelope; it does not guarantee that endpoints are monotone after appending
data, that changing physiology is detected, or that future outcomes are covered.
Independently specified errors can omit systematic protocol error. No nominal
coverage is claimed. A history of good earlier errors cannot identify an
unreported future shift; the frozen stress evaluation below exhibits this
failure. A supported input duration/context does not prove the relationship is
stationary. Fitting in request memory alone does not supply persistence, consent,
export or deletion: the caller owns that history and those controls.

## Runtime interface and metadata

`predict_personal_runtime(exercise: Exercise | None, samples: tuple[SweatSample,
...]=(), *, generated_at: datetime) -> dict` returns the existing forecast
envelope with canonical UTC `generated_at`, `research_only: true`, and a `learning`
object on estimated, insufficient and actual paths. Selected estimates use
`model_version: personal-runtime-rate-v1`,
`interval_kind: personal_runtime_measurement_error_envelope`,
`personalization_status: fitted_personal_rate`, and
`data_sufficiency: earlier_own_measurements_research_only`. Their
`longitudinal_history.method` is
`regularized_duration_rate_with_historical_error_envelope`; their prose describes
the fitted point. Fallback numeric/model/interval/history semantics remain v2;
completed actual numeric/model/interval semantics remain v1.

The exact `learning` keys and types are:

| Key | Value |
| --- | --- |
| version | string `personal-runtime-rate-v1` |
| selected_method | `existing_personal_baseline` or `regularized_duration_rate` |
| reason | fixed reason enum below |
| training_samples, validation_folds | nonnegative integers |
| fitted_rate_ml_per_hour | finite nonnegative float or null |
| ridge_alpha | float 1.0 |
| supported_duration_minutes | object: `minimum`, `maximum`, each float or null |
| baseline_mae_ml, candidate_mae_ml | finite nonnegative float or null |
| paired_gain_ml | finite signed float or null |
| gain_standard_error_ml | finite nonnegative float or null |
| training_sha256 | 64 lowercase hex characters or null |
| cadence_max_gap_seconds | finite positive float or null |
| storage | string `request_memory_only` |
| validation_origin | string `earlier_own_measurements` |
| nominal_coverage | null |

Reasons are `actual_measurement_preserved`, `baseline_unavailable`,
`insufficient_comparable_history`, `overlapping_measurement_windows`,
`outside_observed_duration_domain`, `beyond_observed_session_spacing`,
`insufficient_chronological_validation`, `baseline_retained_after_validation`,
`selected_by_earlier_error_comparison` and `nonfinite_candidate`.

The fit fingerprint canonicalizes UTC instants and exact numeric inputs, so
reordered history/equivalent offsets have identical hashes. The module does no
network access or prediction/history writes; returned metadata has no training
rows, targets or per-fold outcomes. The hash and fitted coefficient remain
sensitive derived metadata: the integrating gateway must exclude them from Meta
facts, prompts and logs. The reproducibility CLI writes only aggregate invented
evaluation output and is separate from the request predictor.

## Frozen synthetic evaluation

The algorithm, alpha and gates were fixed before generating these cases. The
committed artifact `ai/forecasting/artifacts/personal-runtime-synthetic-v1.json`
contains aggregate results only, using seed `20261103`. Each case invents ten
people with twelve workouts each, two days apart. Durations and conditions are
assumed known before each synthetic workout. Predict before the workout from
earlier completed measurements, score its invented loss, then append it to the
history. The baseline is exact v2. Every case attempts 120 predictions; paired
scored counts below exclude the same cold/condition/missing-error abstentions
from both systems. MAE/RMSE/bias aggregate paired workout errors, not independent
people. Point inclusion counts refer to marginal scored outcomes, not
participant simultaneous coverage or an estimated probability.

The invented base rate is `300 + 20*person_index` mL/hour. Default between-workout
variation is uniform ±10 mL, unequal-duration variation ±30 mL, noisy variation
±150 mL. These are declared software inputs, not physiological constants. The
unequal-duration cycle is 30/45/60/90 minutes. Gradual change adds 30 mL/hour each
workout; abrupt change adds 200 mL/hour after six. The fifth outlier adds 500 mL
loss. Assumed mass errors are ±0.01 kg per endpoint, ±0.2 kg for the outlier;
other assumed errors are zero. Missing-error histories omit bounds every fourth
workout starting with the first. Condition shift changes 22°C to 30°C after six
workouts alongside the invented rate step; no causal environmental interpretation
is possible.

| Case | Paired n | Learned n | Baseline → runtime MAE mL | Baseline → runtime RMSE mL | Baseline → runtime bias mL | Inclusion, both | People with worse runtime MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Stable | 110 | 22 | 5.984 → 5.873 | 7.419 → 7.282 | -0.117 → -0.057 | 110/110 | 3/10 |
| Unequal duration | 110 | 24 | 19.684 → 19.433 | 24.497 → 24.089 | 3.106 → 2.710 | 103/110 | 5/10 |
| Noisy | 110 | 18 | 83.644 → 82.113 | 101.129 → 100.677 | 0.336 → 0.163 | 87/110 | 4/10 |
| Outlier | 110 | 0 | 50.426 → 50.426 | 151.444 → 151.444 | -45.285 → -45.285 | 100/110 | 0/10 |
| Gradual change | 110 | 3 | 76.387 → 76.897 | 79.230 → 79.846 | -76.387 → -76.897 | 49/110 | 3/10 |
| Abrupt change | 110 | 21 | 57.731 → 70.489 | 102.630 → 111.383 | -54.608 → -67.461 | 100/110 | 10/10 |
| Condition shift | 100 | 0 | 6.959 → 6.959 | 8.148 → 8.148 | 0.631 → 0.631 | 100/100 | 0/10 |
| Missing errors | 100 | 12 | 6.221 → 6.048 | 7.521 → 7.297 | 1.504 → 1.280 | 100/100 | 0/10 |

These outcomes provide software evidence that fitting and conditional selection
work. They also show failed generalization: earlier validation selects a
stationary rate before unreported abrupt shifts, increasing MAE in all ten
invented trajectories. Even the small stable aggregate gain coexists with three
worse trajectories. Gradual-change inclusion is only 49/110 for both systems.
Reported condition matching avoids using the old context; this is not successful
prediction of the new context. None of these cases establishes real-person
improvement, a validated coverage level, or suitability for medical decisions.
There was no retuning after these results.

Reproduce using the standard-library-only module:

```sh
python -m ai.forecasting.personal_runtime --output /tmp/personal-runtime-synthetic-v1.json
cmp ai/forecasting/artifacts/personal-runtime-synthetic-v1.json /tmp/personal-runtime-synthetic-v1.json
python -m pytest tests/forecasting/test_personal_runtime.py -q
```

Fourteen new meaningful tests cover the hand-derived coefficient and selection,
exact fallback ties/abstentions/actuals, prefix-only validation, duration/cadence
support, overlap including duration uncertainty, duplicate/copy/future rejection,
UTC/DST/reorder identity, widened measurement envelopes, no predictor I/O/raw
training output, correct selected-point metadata, and deterministic labeled
synthetic reproduction. The forecasting suite passed **85 tests** in the isolated
environment (Python 3.13; existing pinned training environment, no new runtime
dependency). The full isolated-branch suite ran **1,121 passed, 1 failed** in
23.09 seconds. Its only failure is the pre-existing date-dependent recognition
fixture `tests/recognition/test_wonder_workout.py::test_invalid_requests_are_rejected[<lambda>11]`
(409 instead of 422); the orchestrator already fixed that fixture separately in
`1f65cf3`, which is not on this isolated ML branch. No recognition code or tests
were changed here. The synthetic artifact reproduced byte-for-byte, SHA-256
`d1e26db8b72c73554a1e3a34ed77e53286b9fedec0884577d422ef90ec5f2872`.
`git diff --check` passed. These checks establish implementation/reproduction,
not scientific accuracy or physical iPhone behavior.
