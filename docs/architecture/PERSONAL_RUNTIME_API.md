# Personal runtime research API

Versioned extension approved November 3, 2026 for the autonomous hydration
intelligence assignment. No billable request, deployment or financial-state
change is authorized by this contract.

## Routes and compatibility

Add `POST /v3/workout-forecasts`, `/v3/hydration-analysis`,
`/v3/wonder/analysis/preview` and `/v3/wonder/analysis`. All use the existing strict
`WorkoutForecastInput` boundary: at most 32 manual samples, explicit processing
consent, bearer authentication, no-store responses and 128 KiB maximum bodies.
The Wonder dispatch request additionally requires the existing exact payload hash
and strict `consent_to_send: true`. No route upgrades consent or retries a call.
Existing v1/v2 routes keep their engines and payload hashes.

All personal v3 routes call
`ai.forecasting.personal_runtime.predict_personal_runtime(exercise, samples,
generated_at=...)`. Synthetic mode retains the existing server-built synthetic
engine and never fits caller data or reads personal beverage logs. Forecast
responses retain `workout-forecast-v1` envelope fields. Local analysis identifies
itself as `hydration-analysis-v3`; its numerical forecast must exactly match the
forecast route for the same inputs and time. Do not expose the older embedded
workout Wonder preview/replay for this version: it uses a different predictor.
Use only the comprehensive v3 preview for its explanation.

## Numerical method and metadata

The stationary model minimizes squared measured loss errors plus fixed alpha=1
regularization toward the median rate from the same earlier training samples.
Six usable, nonoverlapping comparable sessions and at least three strictly
earlier chronological folds are required. Each fold respects workout start,
duration uncertainty and its prefix's observed duration support. Compare against
the exact v2 baseline on the same prefix. Require positive mean paired absolute
error improvement greater than one standard-error heuristic and numerical
tolerance. This heuristic is neither significance testing nor independent
validation. Restrict the query to observed durations and at most the largest
observed gap since the latest session; cadence is an engineering support rule.

Selected learned estimates use `model_version: personal-runtime-rate-v1`,
`interval_kind: personal_runtime_measurement_error_envelope`,
`personalization_status: fitted_personal_rate` and
`data_sufficiency: earlier_own_measurements_research_only`. Baseline fallback and
completed measurements preserve their existing numbers, versions and interval
interpretations. Insufficient evidence can still abstain.

Every personal numerical predictor response adds `research_only: true` and
`learning` with exact keys below. They appear at the forecast root and inside
`hydration-analysis-v3.numerical_forecast`; no duplicate learning object is added
at the analysis or explanation-preview root.

| Key | Value |
| --- | --- |
| version | `personal-runtime-rate-v1` |
| selected_method | `existing_personal_baseline` or `regularized_duration_rate` |
| reason | One of the fixed reasons below |
| training_samples, validation_folds | Bounded nonnegative integers |
| fitted_rate_ml_per_hour | Finite nonnegative number or null |
| ridge_alpha | 1.0 |
| supported_duration_minutes | Object with `minimum`, `maximum` numbers or null |
| baseline_mae_ml, candidate_mae_ml | Finite nonnegative number or null |
| paired_gain_ml | Finite signed number or null |
| gain_standard_error_ml | Finite nonnegative number or null |
| training_sha256 | 64 lowercase hex characters or null |
| cadence_max_gap_seconds | Finite positive number or null |
| storage | `request_memory_only` |
| validation_origin | `earlier_own_measurements` |
| nominal_coverage | null |

Reasons: `actual_measurement_preserved`, `baseline_unavailable`,
`insufficient_comparable_history`, `overlapping_measurement_windows`,
`outside_observed_duration_domain`, `beyond_observed_session_spacing`,
`insufficient_chronological_validation`, `baseline_retained_after_validation`,
`selected_by_earlier_error_comparison`, `nonfinite_candidate`.

The interval unions existing measurement bounds, v2 historical errors and the
candidate's earlier endpoint errors. It has no nominal coverage promise and no
sample-count contraction. Never describe more records as automatically improving
accuracy or narrowing uncertainty. Actual completed measurements bypass fitting.

## Explanation and privacy

The comprehensive `wonder-analysis-facts-v2` allowlist remains the explanation
schema, adding only the new interval-kind literal. Every forecast number is
projected from the v3 numerical result: point to the nearest integer with ties to
even, lower bound by floor and upper bound by ceiling. The v3 rich preview adds
`numerical_contract: personal-runtime-api-v3` outside the provider facts; the
phone requires this marker when using the new routes. Legacy previews retain
their exact shape and precision. Numeric
duration/weather comparisons are descriptive history aggregates, independent of
model fitting, using ties-to-even integer rounding. Model weights, training hash, event IDs, raw measurements and
HealthKit records do not enter the provider payload. The phone checks the preview
against its authoritative v3 forecast before offering Meta consent.

All existing comprehensive feature flags, account/billing guards, shared lock,
exact-hash replay, unresolved-attempt handling and deletion semantics apply.
No new credential, account, ledger, provider transport or automatic fallback is
introduced. The fitted metadata is transient; saved explanation export/deletion
retains the existing behavior. Local history remains explicitly opt-in and
protected on the phone.

## Required evidence

Meaningful regression cases cover earlier-only fitting, targets withheld from
their own prediction, baseline ties/losses, copies/overlap, offsets/DST, missing
protocol/errors, shifted conditions, duration/cadence gates, actual bypass,
overflow and conservative intervals. Boundary tests prove auth/body limits,
consent, numeric equality across all v3 routes, synthetic isolation, unchanged
legacy outputs and disabled live dispatch. Native tests verify typed method
metadata, binding, default-off consent, invalidation and honest research labels.
Synthetic stress results prove software behavior, not real-person accuracy.
