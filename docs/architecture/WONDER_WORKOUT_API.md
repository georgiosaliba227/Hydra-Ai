# Muse Wonder explains your planned workout

Status: implemented and tested with fake Meta transports only. No real request
has run. Policy: AGENTS.md, October 29 Wonder trends policy. Design copied from
[WONDER_TRENDS_API.md](WONDER_TRENDS_API.md); the numerical engine is the
existing v2 workout forecast ([WORKOUT_MODEL_API.md](WORKOUT_MODEL_API.md),
[HYDRATION_CONTEXT_V2_API.md](HYDRATION_CONTEXT_V2_API.md)).

## What it does

The user enters (or the app prefills) a planned workout: activity, intensity,
start time, duration, temperature in °C and humidity in %. The app also sends
the user's previous sessions it keeps on the device. The backend computes facts
(`backend/wonder_workout.py`, `WorkoutFacts`):

- the planned workout, with its local time of day;
- the user's typical duration, temperature and humidity: medians of the
  supplied previous sessions **of the same activity**;
- how the plan compares: `longer`/`shorter`/`similar`, `hotter`/`cooler`/`similar`,
  `more_humid`/`less_humid`/`similar`;
- how many previous sessions of this activity there are, how many match the
  plan's intensity, temperature and humidity exactly (the engine's comparability
  rule), and how many have a complete before-and-after weigh-in (personal
  calibration measurements), with the median fluid loss those weigh-ins measured;
- the existing v2 engine's estimate (`predict_longitudinal`, unchanged): a range
  in mL, or `insufficient_data` with what is missing;
- whether the estimate is above, below or in line with the user's measured loss;
- which measurement would refine the estimate.

The screen shows those facts as "What would be sent to Meta". Nothing is sent
until the user turns on the consent toggle and taps **Explain my workout**.
Muse Wonder 1.0 then chooses 1 to 3 insights that apply and writes one or two
sentences for each, plus a one-sentence summary. For example:

> This workout is longer than your typical run (75 vs 45 minutes) and hotter
> than your typical run (31 °C vs 22 °C). Hydra has no estimate yet; it is
> missing … Recording your weight before and after this workout, plus what you
> drink and any urine during it would help refine the estimate.

Wonder cannot write numbers, units or directions. It writes placeholders such
as `{duration_comparison}` and Hydra fills in the exact text. Weather is context
only: the engine has no validated weather adjustment, so a hotter plan never
gets a number Hydra did not compute. When the weather differs from every
weighed session the engine abstains, and the explanation says what is missing
instead.

The display thresholds for "similar" are a duration within 10% of the typical
duration (inclusive), a temperature less than 3 °C apart and a humidity less
than 10 points apart. They only choose words; they are not physiological
thresholds and change no number.

## Rules Wonder's text must pass

The server rejects the whole reply, without repair or retry, if the wording
contains any of these (trend rules plus workout rules):

- a digit, a number word ("three", "double", "few", "several"), a unit
  (mL, minutes, °C, %, kg) or a link;
- a comparison or direction word: more, less, higher, lower, longer, shorter,
  hotter, cooler, than, same, similar, differ, above, below, within, every, only;
- anything about drinking: drink, water, intake, replace, replenish, sip,
  electrolytes, salt, thirst — Hydra never says whether, how much or when to drink;
- a daily amount or requirement (daily, require, need, goal, enough);
- medical, diagnostic or judging wording: hydrated/dehydrated, heart, pulse, HRV,
  symptom, risk, safe, heat, exhaustion, cramp, health, should, must, try,
  consider, recommend, cause, because, good, bad, likely, accurate;
- weather judgment or adjustment: hot, cold, humid, adjust, compensate;
- an unknown placeholder, or one these facts can't fill (for example
  `{estimate}` when the engine abstained);
- an insight these facts don't support, extra fields, line breaks, too much text.

An insight Wonder repeats counts once (the first text is kept; every repeat is
still checked). The required caveats are Hydra's fixed `limitations`; Wonder
does not choose them.

The schema sent to Wonder lists only the insights that apply to these facts,
and the prompt lists only the placeholders these facts can fill. Live Wonder
replied with repeated, invented and caveat-dropping items when given every
option (2026-10-29, trends and scenarios).

### Insights

| `id` | Title shown | Offered when |
| --- | --- | --- |
| `duration_vs_typical` | Duration vs your usual | a typical duration exists |
| `weather_vs_typical` | Weather vs your usual | a planned and a typical temperature or humidity exist |
| `comparable_history` | Your previous sessions | always |
| `estimate` | The estimate | the engine estimated a range |
| `estimate_vs_previous` | Estimate vs your measurements | an estimate and weighed sessions exist |
| `missing_information` | What is missing | no estimate, and Hydra knows what is missing |
| `refine_estimate` | What would refine it | always |

### Placeholders (Hydra's text)

| Placeholder | Example rendering | Available when |
| --- | --- | --- |
| `{planned_workout}` | 75 minutes of high-intensity running in the evening at 31 °C and 60% humidity | always |
| `{duration_comparison}` | longer than your typical run (75 vs 45 minutes) | typical duration |
| `{temperature_comparison}` | hotter than your typical run (31 °C vs 22 °C) | both temperatures |
| `{humidity_comparison}` | close to the humidity of your typical run (55% humidity) | both humidities |
| `{previous_sessions}` | 4 previous runs | always |
| `{matching_sessions}` | 0 of your 4 previous runs at the same intensity, temperature and humidity | always |
| `{weigh_ins}` | 2 of your 4 previous runs with a complete before-and-after weigh-in | always |
| `{measured_loss}` | 800 mL (the median of 2 weighed runs) | weighed sessions |
| `{estimate}` | about 1125 to 1750 mL | estimate |
| `{estimate_basis}` | 2 runs weighed at the same intensity, temperature and humidity | estimate |
| `{estimate_comparison}` | above what you measured on your weighed runs (median 800 mL) | estimate and weighed sessions |
| `{missing_information}` | previous weigh-ins at the same intensity, temperature and humidity, with their measurement error bounds | no estimate |
| `{suggested_measurement}` | your weight before and after this workout, plus what you drink and any urine during it | always |

## API

Both endpoints need the development session (`Authorization: Bearer <token>`),
return `Cache-Control: no-store`, use the generic error envelope and accept up
to **128 KiB** of JSON (the workout-forecast limit; 32 sessions fit).

### Request body (both endpoints)

The body is the existing personal `POST /v2/workout-forecasts` request
(`WorkoutForecastInput`, see WORKOUT_MODEL_API.md) with `exercise` required:

- `timezone` (IANA, required) — used for the local time of day.
- `exercise` (`ExerciseInput`, required) — the planned workout:
  - `event_id` (UUID), `starts_at` (timestamp with explicit offset or `Z`),
    `duration_minutes` (> 0, ≤ 1440);
  - `conditions`: `activity` (`running`, `cycling`, `walking`, `strength`,
    `other`), `intensity` (`low`, `moderate`, `high` or null),
    `temperature_c` (−60 to 60 or null), `humidity_percent` (0 to 100 or null);
  - `comparable_conditions_confirmed` (default false): send true only when the
    user confirms this workout's environment, intensity, equipment and
    acclimatization match their earlier sessions. Without it the engine
    abstains and says so;
  - `actual` must be absent (a planned workout has no completed measurement).
- `samples` (0 to 32 `SampleInput`) — previous sessions, each strictly in the
  past: `event_id`, `observed_at`, `conditions` (as above), `measurement`
  (`pre_mass_kg`, `post_mass_kg`, `consumed_ml`, `urine_ml`, `duration_minutes`
  — each nullable — plus `protocol_confirmed` and `provenance`), optional
  `errors` (measurement error bounds). A session with only a duration is a
  logged workout; a session with every measurement and `protocol_confirmed: true`
  is a weigh-in; the engine projects only from weigh-ins with `errors`.
- `calibration_processing_consent` — must be true when `samples` is not empty.
- `mode` may be omitted; only `"personal"` is accepted.

The facts, and therefore `payload_sha256`, depend only on the aggregates
above, not on event IDs, timestamps beyond the local time of day, or sample
order. Changing any input that changes a fact produces a new hash. A planned
workout whose start time has passed is reported as started (missing
`actual_measurement_for_started_exercise`), which also changes the hash.

### `POST /v1/wonder/workout/preview`

Computes the facts and shows exactly what would be sent. Nothing is sent or
charged. Request:

```json
{
  "timezone": "Europe/Paris",
  "calibration_processing_consent": true,
  "exercise": {
    "event_id": "0b7d9a52-3c1e-4f6a-9d2b-5e8f7a1c4d30",
    "starts_at": "2026-11-03T17:00:00Z",
    "duration_minutes": 75,
    "comparable_conditions_confirmed": false,
    "conditions": {"activity": "running", "intensity": "high", "temperature_c": 31, "humidity_percent": 60}
  },
  "samples": [
    {
      "event_id": "6f1c2a4e-0000-4000-8000-000000000001",
      "observed_at": "2026-10-20T18:30:00Z",
      "conditions": {"activity": "running", "intensity": "moderate", "temperature_c": 22.0, "humidity_percent": 55.0},
      "measurement": {"pre_mass_kg": 70.0, "post_mass_kg": 69.4, "consumed_ml": 200, "urine_ml": 0,
                      "duration_minutes": 45, "protocol_confirmed": true, "provenance": ["manual_weigh_in"]},
      "errors": {"pre_mass_kg": 0.05, "post_mass_kg": 0.05, "consumed_ml": 10, "urine_ml": 0,
                 "duration_minutes": 1, "provenance": ["scale_specification"]}
    },
    {
      "event_id": "6f1c2a4e-0000-4000-8000-000000000002",
      "observed_at": "2026-10-23T18:30:00Z",
      "conditions": {"activity": "running", "intensity": "moderate", "temperature_c": 22.0, "humidity_percent": 55.0},
      "measurement": {"pre_mass_kg": 70.0, "post_mass_kg": 69.4, "consumed_ml": 200, "urine_ml": 0,
                      "duration_minutes": 40, "protocol_confirmed": true, "provenance": ["manual_weigh_in"]},
      "errors": {"pre_mass_kg": 0.05, "post_mass_kg": 0.05, "consumed_ml": 10, "urine_ml": 0,
                 "duration_minutes": 1, "provenance": ["scale_specification"]}
    },
    {
      "event_id": "6f1c2a4e-0000-4000-8000-000000000003",
      "observed_at": "2026-10-25T18:30:00Z",
      "conditions": {"activity": "running", "intensity": "moderate", "temperature_c": 22.0, "humidity_percent": 55.0},
      "measurement": {"duration_minutes": 50, "protocol_confirmed": false, "provenance": ["manual_workout_log"]}
    },
    {
      "event_id": "6f1c2a4e-0000-4000-8000-000000000004",
      "observed_at": "2026-10-27T18:30:00Z",
      "conditions": {"activity": "running", "intensity": "moderate", "temperature_c": 22.0, "humidity_percent": 55.0},
      "measurement": {"duration_minutes": 45, "protocol_confirmed": false, "provenance": ["manual_workout_log"]}
    }
  ]
}
```

Response `200`:

```json
{
  "version": "wonder-workout-v1",
  "facts": {
    "version": "wonder-workout-facts-v1",
    "timezone": "Europe/Paris",
    "planned": {"activity": "running", "intensity": "high", "time_of_day": "evening", "duration_minutes": 75,
                "temperature_c": 31, "humidity_percent": 60, "conditions_confirmed": false},
    "history": {"sessions": 4, "activity_sessions": 4, "matching_sessions": 0, "weigh_in_sessions": 2,
                "typical_duration_minutes": 45, "typical_temperature_c": 22, "typical_humidity_percent": 55,
                "measured_loss_ml": 800},
    "estimate": {"status": "insufficient_data", "value_ml": null, "lower_ml": null, "upper_ml": null,
                 "sample_count": 0,
                 "missing_inputs": ["confirmed_comparable_conditions", "usable_measurements_with_error_bounds"]},
    "comparison": {"duration": "longer", "temperature": "hotter", "humidity": "similar", "estimate": null},
    "suggested_measurement": "weigh_this_workout",
    "applicable_insights": ["duration_vs_typical", "weather_vs_typical", "comparable_history",
                            "missing_information", "refine_estimate"]
  },
  "explainable": true,
  "payload_sha256": "fa6dfd6b2378ce12b206da62fb691d7479c2b418e9db2203b1c71178275084f7",
  "input_bound_tokens": 4286,
  "worst_case_micro_usd": 58104,
  "live_available": true,
  "account_id": "aminealichaouche",
  "saved": null
}
```

- `explainable` is false (and `payload_sha256`, `input_bound_tokens`,
  `worst_case_micro_usd` are null) when there is no previous session of the
  planned activity. Show "Add a previous session of this activity first".
- `worst_case_micro_usd` is the upper bound of the token charge (58104 =
  $0.058), not a bill.
- `live_available` is false when this backend has no live Wonder
  configuration; the POST then returns `wonder_unavailable`.
- `saved` is the stored explanation of exactly this payload, if one exists
  (same shape as `result` below). Show it without asking again.

When the planned conditions match the weighed sessions and the user confirmed
them, the engine estimates a range and the facts look like this (same history,
planned `moderate`, 22 °C, 55%, `comparable_conditions_confirmed: true`):

```json
{
  "planned": {"activity": "running", "intensity": "moderate", "time_of_day": "evening", "duration_minutes": 75,
              "temperature_c": 22, "humidity_percent": 55, "conditions_confirmed": true},
  "history": {"sessions": 4, "activity_sessions": 4, "matching_sessions": 4, "weigh_in_sessions": 2,
              "typical_duration_minutes": 45, "typical_temperature_c": 22, "typical_humidity_percent": 55,
              "measured_loss_ml": 800},
  "estimate": {"status": "estimated", "value_ml": 1417, "lower_ml": 1125, "upper_ml": 1750, "sample_count": 2,
               "missing_inputs": []},
  "comparison": {"duration": "longer", "temperature": "similar", "humidity": "similar", "estimate": "above"},
  "suggested_measurement": "repeat_weigh_in",
  "applicable_insights": ["duration_vs_typical", "weather_vs_typical", "comparable_history", "estimate",
                          "estimate_vs_previous", "refine_estimate"]
}
```

The estimate's `lower_ml` is rounded down and `upper_ml` rounded up from the
engine's range; `value_ml` is its rounded point. It is a fluid-loss estimate,
never a drinking amount.

Enumerations in `facts`:

- `planned.time_of_day`: `morning` (05–12), `afternoon` (12–17), `evening` (17–22), `night`.
- `estimate.missing_inputs`: `complete_environment_and_intensity`,
  `confirmed_comparable_conditions`, `usable_measurements_with_error_bounds`,
  `actual_measurement_for_started_exercise`.
- `suggested_measurement`: `repeat_weigh_in`, `weigh_this_workout`,
  `record_conditions`, `confirm_conditions`.

### `POST /v1/wonder/workout`

Asks for the explanation. The body is the same request plus the previewed
hash and explicit consent:

```json
{
  "timezone": "Europe/Paris",
  "calibration_processing_consent": true,
  "exercise": {"...": "exactly as previewed"},
  "samples": ["...exactly as previewed"],
  "payload_sha256": "fa6dfd6b2378ce12b206da62fb691d7479c2b418e9db2203b1c71178275084f7",
  "consent_to_send": true
}
```

`consent_to_send` must be the JSON literal `true` (not `1` or `"true"`).
The backend recomputes the facts; if their hash differs from
`payload_sha256`, nothing is sent (`workout_preview_stale`).

Response `200`:

```json
{
  "replayed": false,
  "saved": true,
  "result": {
    "version": "wonder-workout-v1",
    "facts": {"...": "the previewed facts, exactly"},
    "payload_sha256": "fa6dfd6b2378ce12b206da62fb691d7479c2b418e9db2203b1c71178275084f7",
    "summary": "This workout is longer than your typical run (75 vs 45 minutes) and hotter than your typical run (31 °C vs 22 °C).",
    "summary_template": "This workout is {duration_comparison} and {temperature_comparison}.",
    "insights": [
      {
        "id": "comparable_history",
        "title": "Your previous sessions",
        "template": "Hydra compared it with {previous_sessions}, including {weigh_ins}.",
        "text": "Hydra compared it with 4 previous runs, including 2 of your 4 previous runs with a complete before-and-after weigh-in."
      },
      {
        "id": "missing_information",
        "title": "What is missing",
        "template": "Hydra has no estimate yet; it is missing {missing_information}.",
        "text": "Hydra has no estimate yet; it is missing your confirmation that this workout's conditions match your earlier sessions and previous weigh-ins at the same intensity, temperature and humidity, with their measurement error bounds."
      },
      {
        "id": "refine_estimate",
        "title": "What would refine it",
        "template": "Recording {suggested_measurement} would help refine the estimate.",
        "text": "Recording your weight before and after this workout, plus what you drink and any urine during it would help refine the estimate."
      }
    ],
    "generated_at": "2026-10-30T01:04:52.988795+00:00",
    "provenance": {
      "mode": "meta_live",
      "provider": "Meta",
      "model": "muse-wonder-1.0",
      "account_id": "aminealichaouche",
      "attempt_id": "7938cc7c-896c-4da0-9cf8-f013ddad8db1",
      "text_origin": "muse_wonder_checked",
      "numbers_checked_against": "facts"
    },
    "provider_observations": {
      "latency_ms": 0,
      "input_tokens": 1900,
      "output_tokens": 600,
      "usage_derived_cost_micro_usd": 19600,
      "billed_cost_usd": null
    },
    "limitations": [
      "Wellness information, not medical advice.",
      "Muse Wonder wrote the wording; every number was computed and filled in by Hydra from your entries.",
      "The estimate is of workout fluid loss only. It is not a drinking target or a daily fluid requirement.",
      "Temperature and humidity are context only; the estimate applies no weather adjustment.",
      "Heart rate is not used, and Hydra does not infer dehydration."
    ]
  }
}
```

(Values from a fake-transport test run; a live reply's wording, tokens and cost
will differ.) Display `summary`, then each insight's `title` and `text`, then
every `limitations` line. Never display `template` fields; they are kept so
replay can re-check the text.

- If the stored result for this payload already exists, it is returned with
  `replayed: true` and nothing is sent or charged.
- Otherwise the backend sends one request and stores the validated result
  write-once as `workout-<payload_sha256>.json`. `saved: false` means the
  request succeeded and was charged but the file could not be written; show
  the result anyway.

Errors use the standard envelope:

```json
{"code": "workout_preview_stale", "message": "Your planned workout or history changed since the preview. Review the new preview first.", "request_id": "68b7a294-e4a6-49e8-8706-f25a83778dba", "retryable": true}
```

| Status | Code | Meaning | App action |
| --- | --- | --- | --- |
| 409 | `workout_preview_stale` | The facts changed since the preview | Preview again, ask for consent again |
| 409 | `wonder_blocked` | A spending gate refused before reservation; nothing was sent | Show "paused by a spending safeguard" |
| 409 | `wonder_busy` | Another Wonder request (trend, workout or synthetic) is in progress; `retryable: true` | Try again shortly |
| 422 | `workout_insufficient_history` | No previous session of this activity | Ask for a previous session first |
| 422 | `invalid_request` | Malformed body, missing consent, `actual` present, a "previous" session not in the past, more than 32 sessions | Fix the request |
| 502 | `wonder_attempt_unresolved` | Failed after reservation (including a reply that failed the text checks); the body adds `"attempt_id"`. Do not retry | Show "a developer must review this attempt" |
| 503 | `wonder_unavailable` | Live Wonder is not configured | Hide or disable the button (`live_available: false`) |

Saved workout explanations are included in `GET /v1/export` as
`wonder_workout_explanations` (a list of `result` objects) and removed by
`DELETE /v1/data?confirm=delete-all-my-data`, whose response adds
`deleted_workout_explanations`. The ledger keeps only payload hashes and amounts.
Raw sessions are never stored by the backend; the app keeps them.

## Spending controls

Unchanged from trend explanations, through the same `WonderExperimentLedger`,
live configuration (`HYDRA_WONDER_*` variables, see WONDER_TRENDS_API.md) and
results folder:

- $0.25 cap per request; a workout request is about $0.06 worst case at
  `max_output_tokens` 2048 (the trend limit);
- one request in flight per backend, through the lock shared with trends and
  synthetic runs;
- invoice finality for every earlier attempt before the next one, $75 notice,
  key/account checks before reservation, unresolved-billing and frozen-account
  blocks, settlement from reported usage;
- no retries; a saved result replays for free and the same payload is never
  approved or sent twice.

**Standing approval.** A workout request uses the allocation's existing
`trend_dispatch_reference`. That approval covers Wonder explanations of the
owner's own data (the October 29 Wonder trends policy: the user's own logged
data, sent only as the aggregated payload they previewed and consented to, with
deterministic numbers and server-side text checks). A planned-workout
explanation is the same kind of request: aggregated facts about the owner's own
entries, Hydra-computed numbers, the same text checks plus stricter workout
rules, and each request recorded as its own case bound to the exact consented
payload hash (`register_workout_case`, consent reference
`in-app-workout-consent:<request_id>:<payload_sha256>`). An allocation without
`trend_dispatch_reference` refuses workout requests before anything is
reserved. No new approval field, allocation or limit is added.

A reply rejected *after* settlement is recorded as `experiment_output_rejected`
and does not freeze the account, because its charge is already known from
usage. Anything that leaves the charge uncertain still freezes it.

The transport sends only payloads Hydra builds: `facts_from_payload` rebuilds
the payload from its embedded facts and refuses any difference (another
prompt, schema, token limit, tool or inconsistent facts).

## iOS integration

Implemented in the "Plan a workout" screen (`ios/HydraAI/Features/Forecast/WorkoutForecastView.swift`,
models and controller in `ios/HydraAI/Data/WonderWorkout.swift`, service methods
`wonderWorkoutPreview` / `explainWorkout` in `HTTPBeverageService`). Unit-tested against this
document's JSON examples and a stub service; UI-tested against a local mock backend only. No live
request has been made from the app.

- **Same request as the estimate.** "Estimate my workout" builds one `WorkoutForecastRequest`
  (`WorkoutDraft.personalRequest(samples:)`). After the estimate returns, the app posts that exact
  value to `/preview`; "Explain this workout" posts it again unchanged plus `payload_sha256` and
  `consent_to_send: true`. Any edit to the workout or the session measurements drops the preview.
- **History is the session's manual measurements.** The app sends only the weigh-ins the user
  added under "Your own measurements" on this screen. Apple Health workouts are not sent as
  history, so with no added measurement the preview is not explainable and the app says "Log a
  previous session of this activity first".
- **Gating.** The consent toggle and button appear only when the preview is explainable,
  `live_available` is true with an account, the payload was not already explained (saved result
  or explained this visit), and no attempt for it failed after reservation. The button stays
  disabled until the toggle is on; the toggle resets after each tap and whenever the preview
  changes. On a mock backend the section shows the preview and "Live Muse Wonder isn't set up on
  this backend".
- **Errors.** Each code above maps to its own message. `workout_preview_stale` re-runs the
  (non-billable) preview and asks for consent again; `wonder_attempt_unresolved` shows the attempt
  id and never offers that payload again during the visit. Nothing is retried automatically.
- **Display.** `summary` as the headline, one card per insight with Hydra's `title`, and a
  collapsed "How this was made" with model, tokens, usage-based cost, account, attempt and every
  `limitations` line. `template` fields are never decoded for display.

## Privacy

Sent to Meta: the aggregated `facts` above (no event IDs, timestamps, body
masses, intake, urine or error bounds; only counts, medians, the rounded
estimate and the measured median loss). Raw HealthKit records are not
accepted. App Store review of health-data disclosure remains separate for any
public release.
