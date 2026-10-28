# Hydration contextual comparison V2

Additive, mock-only review contract. Existing v1 APIs, numerical artifacts, Meta
provider adapters, private ledgers and permits are unchanged. There is no live
provider path in these endpoints, regardless of environment configuration.

## Numerical and contextual separation

`POST /v2/workout-forecasts` accepts the existing `WorkoutForecastInput` schema,
using the same explicit calibration consent, manual-only data, 32-sample and
128 KiB bounds. It returns the v1 numerical shape and UTC/timezone metadata.
Personal mode uses `predict_longitudinal` with session-supplied historical
measurements and adds `longitudinal_history`. No personal measurements reach any
contextual adapter or provider. History is retained only by the caller, not saved
in a new health database. Synthetic mode uses the existing server-owned fixture
and adds the structured `context_comparison` below. No custom synthetic input is
accepted through the numerical endpoint.

`POST /v2/hydration-context-comparison` accepts only `mode:"mock"`, a server-owned
scenario ID (`complete`, `missing_measurements`, `contradictory_mass`,
`changing_conditions`, or `biometrics_and_supplements`) and an optional
`candidate_model` (`muse-spark-1.3` default, or `muse-wonder-1.0`). Unknown fields,
raw records, prompts, account selectors, numerical goals and live modes are rejected.
This endpoint uses the existing 16 KiB bound. All v2 routes require the development
session and return `Cache-Control:no-store` with redacted errors.

System A preserves the existing numerical result. System B returns contextual
interpretation with no numerical prediction. System C carries an identical copy
of A's numerical result plus that interpretation; contextual output cannot change
any number. This implementation therefore claims no numerical improvement from
adding mock reasoning. Personal longitudinal comparisons are reported separately.

## Structured interpretation and provenance

Selections contain only bounded enum IDs for relevant factors, missing information,
contradictions, uncertainty and measurement suggestions, plus a strict abstention
boolean. Unknown fields, numerical values/goals, free text, duplicate IDs,
unsupported IDs and context-inconsistent selections are rejected. Contradictions
and safety-critical uncertainty cannot be omitted. Reviewed local text is rendered
after validation. Model output cannot overwrite values or generate medical advice.

Response provenance states `mode:mock`, `synthetic:true`, `provider:null`,
`model:null`, candidate model/tier as unverified future experiment labels, and
`live_dispatch_enabled:false`. Provider latency, input/output tokens and actual
billed cost are null because no such observations exist. A mock execution is not a
Meta-generated explanation or evidence about Spark/Wonder quality or prices.

Server-owned fixtures include explicit measured/unknown flags and consistent or
contradictory synthetic inputs. They never reuse user records or expose held-out
research outcomes. Expected benchmark labels are handwritten software-test labels.
Groundedness, abstention, missingness, contradiction and consistency scores test
this local validator/fixture mechanism only. Real, synthetic and personal-calibration
quality remain separate. No model-generated labels become physiological ground truth.

## Native client

The existing workout screen consumes v2 without replacing drink/camera flows.
Personal history counts/time bounds, insufficient-data information and session-only
retention are visible. The synthetic comparison explicitly labels A numerical,
B contextual mock and C hybrid; the app validates equality of A/C numerical values,
null B predictions and null actual usage/cost/model provenance before display.
Connection/input changes invalidate late results. Raw HealthKit export remains
unsupported. No unsupported daily percentage, drinking goal or diagnosis is shown.
