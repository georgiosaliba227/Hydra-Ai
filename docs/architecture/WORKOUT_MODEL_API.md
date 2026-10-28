# Adaptive workout model v1

Additive review contract, October 28, 2026. This work follows the existing
`PERSONAL_FORECAST_API.md`, `PROTOTYPE_API.md`, and
`HYDRATION_INTELLIGENCE_API.md`. Existing accounting, camera, and Meta budget
contracts remain authoritative. No deployment or billable inference is authorized.

## Targets established before synthetic generation

| Target | Meaning and permitted evidence | Current boundary |
| --- | --- | --- |
| A: workout loss | Future workout fluid-loss estimate, with each study's measured/derived target identified. Corrected body-mass change is an estimate, not direct sweat collection. Uncorrected body-mass loss remains a separate proxy target. | Compare real-data models within each valid study/target. No pooling of incompatible targets, no post-workout predictors. Personal projections require comparable, protocol-confirmed past measurements. |
| B: consumption behavior | Future consumed beverage volume, distinct from loss, balance, or need. Missing logs do not mean no consumption. | Existing logged-intake history stays descriptive. No validated longitudinal consumption forecasting claim. Dietary recall/composition data cannot label workout loss. |
| C: conditional requirements | Supported intake need with adequate population, measurement and safety evidence. | `insufficient_data`; do not turn a loss prediction into a drinking recommendation or add it to an unapproved daily goal. |

The deterministic comparator is the existing NATA-based mass-balance engine.
Post-workout mass is an outcome and must never be a pre-workout predictor.
Evaluating the engine against labels calculated by the same equation checks
arithmetic, not predictive accuracy. A cohort rate learned on training participants
is a separate statistical baseline. Historical measured-rate projections require
chronologically earlier, comparable measurements; unavailable inputs produce
abstention rather than invented zero intake/urine.

Real-data inventory and target semantics must be recorded before generation of
synthetic users. Synthetic distributions are scenario assumptions for software
stress tests; they are not an evidence-backed population model. No invented causal
effects from caffeine, creatine, heart rate, HRV, sleep, or thirst. Real and synthetic
identifiers, files, metrics, and artifact provenance remain distinct. Never join
unrelated study participants. Select models using held-out real outcomes only for
the corresponding real research task; synthetic accuracy cannot authorize a
physiological model for app users.

## Internal boundary

`ai.forecasting.predict.predict_workout(exercise, samples=(), *, generated_at,
mode="personal", body_mass_kg=None)` accepts existing validated `Exercise` and
`SweatSample` domain types. The function performs no network call, ledger access,
persistence, or provider inference.

Personal mode reuses measured mass balance and the existing conditional measurement
envelope. Unsupported cold starts return `insufficient_data`. Repeated comparable
observations update a descriptive point estimate and envelope; neither is a
clinically validated individual prediction interval. A synthetic demonstration
uses a trained synthetic artifact and clearly labeled server-owned example inputs,
never real personal records relabeled as synthetic.

Results expose `version`, `status`, `model_version`, `quantity`, `units`, nullable
`value_ml`, `lower_ml`, `upper_ml`, `interval_kind`, `data_sufficiency`,
`personalization_status`, `sample_count`, `provenance`, `input_factors`,
`limitations`, and `synthetic`. Quantities and methods must distinguish a learned
model from the deterministic personal fallback. `units` is `mL`. No result changes
confirmed beverages or claims to estimate dehydration, retention, or net balance.

## HTTP and iPhone boundary

The additive authenticated `POST /v1/workout-forecasts` uses the existing bounded
request guard, generic error envelope, and `Cache-Control: no-store`. The adapter
uses existing exercise/sample validators, explicit timezone and offset timestamps,
server-generated UTC calculation time, and separate strict calibration-processing
consent. Manual measurements are transient request data only. Raw HealthKit records
are not accepted or exported. The synthetic demonstration uses server-owned
fixtures and rejects personal calibration samples.

Request fields are `mode` (`personal`, the default, or `synthetic_demo`), required
IANA `timezone`, nullable `exercise` (`ExerciseInput`), `samples` (at most 32
`SampleInput` items), and `calibration_processing_consent` (strict boolean,
default false). Unknown fields are rejected. Personal samples or an actual
measurement require consent. Synthetic mode rejects any exercise, samples, or
true calibration consent; the runtime constructs the example. The response adds
`mode`, `timezone`, and server UTC `generated_at` to the internal result. No
caller-selected model path, artifact, source URL, account, or numerical goal is
accepted.

The iPhone presents workout estimates separately from confirmed intake and daily
requirements. Loading/failure/insufficient-data and synthetic mode are visible.
Changing backend configuration invalidates pending forecast results. A demo does
not insert measurements or beverages into the user's history.

## Meta interpretation

Preserve the existing Muse Spark guarded explanation service and reviewed signal
rendering. Numerical predictions and measurements remain authoritative; provider
text cannot overwrite them or create goals. Development may exercise the existing
mock explanation path with synthetic context only. Personal measurements must not
be sent to Meta. No account, credential, permit, private ledger, or billable flag is
modified by this feature. Actual model explanation quality remains unverified until
a separately authorized live evaluation.

## Verification and scientific release boundary

Require provenance checks, unit conversions, participant-disjoint splits, duplicate
exclusion, training-only imputation, deterministic reruns, held-out calibration,
MAE/RMSE/interval coverage, missingness and domain checks, plus API/iOS regressions.
Report study/participant counts, unavailable strata and unavailable cross-study
validation. Empirical coverage on a small held-out set is not a universal guarantee.
Personal data stays local to the configured development backend; no cloud model
training or paid compute occurs. Human review is required before merge.

Scientific basis: [NATA 2017 fluid replacement position statement](https://pmc.ncbi.nlm.nih.gov/articles/PMC5634236/)
supports comparable-condition measurement-based assessment, with individual
variability and limitations. Dataset-specific evidence and licenses are recorded in
`docs/FORECAST_DATA_INVENTORY.md`; training decisions and measured metrics belong
in `docs/FORECAST_MODEL.md` and `docs/FORECAST_EVALUATION.md`.
