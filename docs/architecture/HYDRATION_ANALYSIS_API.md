# Hydration analysis v1

November 2, 2026 additive contract. `POST /v1/hydration-analysis` is an authenticated,
nonbillable composition of existing numerical calculations and context. It does not
persist calibration, dispatch Meta, change financial state or insert beverages.
Existing workout and Wonder endpoints remain backward compatible.

## Request

Exactly `WorkoutForecastInput` from `WORKOUT_MODEL_API.md`: required IANA timezone,
personal or synthetic_demo mode, optional exercise, up to 32 manual samples and
strict calibration-processing consent. Unknown fields, raw HealthKit export and
synthetic requests carrying personal input are rejected. The body limit is 128 KiB;
authentication and `Cache-Control: no-store` use the shared request guard.

Each sample has an explicit offset completion timestamp, measurement protocol,
units and provenance. Personal calculations accept only chronological earlier
observations and do not infer missing error bounds. Repeated measurements remain
subject to existing duplicate and comparability checks.

## Response

| Field | Meaning |
| --- | --- |
| `version` | `hydration-analysis-v1` |
| `generated_at`, `timezone`, `mode` | UTC calculation instant, user timezone, explicit data origin |
| `research_only` | Always true; no physiological or clinical validation implied |
| `numerical_forecast` | Existing `predict_longitudinal` personal result or server-owned `predict_workout` synthetic result; no AI numerical changes |
| `intake` | Today's logged intake from local midnight through calculation time; explicit UTC boundaries, beverage volume, nullable composition water and documented electrolytes |
| `exercise_accounting` | Nullable signed `logged_intake_minus_measured_exercise_loss` for a completed workout's own window; unavailable for planned workouts |
| `environmental_context` | Supplied temperature, humidity and intensity, source label and `context_only: true` |
| `calibration` | Total, comparable and recent sample counts, personalization status, caller-retained history |
| `missing_inputs` | Explicit missingness codes; incomplete logs never mean measured zero intake |
| `sections` | Eight deterministic local sections with id, title, evidence status, facts and text |
| `wonder` | Existing workout facts preview and optional validated saved result, with `provider_called: false` |
| `limitations`, `text_origin` | Fixed limits and `deterministic_local`; saved Wonder wording remains separately labeled |

The eight section IDs are `summary`, `workout_loss`, `activity`, `environment`,
`beverages`, `trends`, `uncertainty`, and `measurement`. Evidence is labeled
`measured`, `estimated`, `context_only`, `insufficient_data`, or `synthetic`.
The last fourteen completed calendar days provide descriptive logged-day bounds;
unlogged days are excluded rather than imputed as zero.

`intake.composition.sodium_mg` and `potassium_mg` are null unless every included
entry documents that nutrient. Per-nutrient statuses distinguish complete, partial
and unknown coverage. Water, beverage volume and physiological retention are
different quantities. Missing nutrition is never filled by a beverage multiplier.

Exercise accounting requires a completed measurement, compatible duration and
conditions, and matching logged versus measurement-reported consumption within
that exact workout window. Interval subtraction reverses the loss interval's
bounds and preserves negative values. This quantity omits other losses and is not
a total fluid balance, hydration status, deficit or drinking target. Insufficient
evidence returns unavailable, with reasons and no fabricated number.

Synthetic mode never queries real intake or replays personal explanations. Its
composition/context comes only from the server fixture and is labeled simulated.

## Wonder boundary

The existing `WONDER_WORKOUT_API.md` preview remains authoritative. For a compatible
planned personal workout the analysis includes the exact same aggregated facts
and payload hash, and may read a validated saved explanation for that hash. It
never adds drink logs or the eight local section texts to that Meta payload.

Actual dispatch still requires a separate existing preview/consent/hash flow,
verified live configuration, account evidence, the authoritative ledger and all
spending/finality gates. Saving or revisiting an analysis is not fresh consent.
The local analysis sections cover broader context than this existing Wonder
workout explanation; they must never be presented as text Wonder generated or as
evidence of live explanation quality.
