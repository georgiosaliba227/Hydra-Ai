# US units and automatic daily context

The owner confirmed real workout import and weather autofill on the installed
iPhone, then requested American units and first-use Health/weather setup followed
by autonomous daily updates. This extends the authorized ongoing implementation.
The choices below are engineering decisions under that autonomy, not additional
human approvals. Existing financial approvals and exact Meta disclosure consent
are unchanged.

## Approach

Use one app-wide US/metric display preference, US by default, with canonical mL,
kg and °C in storage/calculation/API contracts. An alternative API-wide conversion
would disturb existing numerical and financial bindings. Locale-only formatting
would not honor the owner's explicit US preference. A single conversion boundary
also prevents interpreting an old mL value as fl oz after a settings change.

Use optional first-use setup and app-wide consented context refresh, rather than
repeated manual imports. Refresh at launch/foreground, at a local-day boundary
while open, and through best-effort iOS background refresh. A guaranteed daily
server schedule would require always-on deployment and additional disclosure;
neither is part of this change. iOS controls background scheduling, and locked
HealthKit data may be unavailable. Show actual freshness/failure state.

## Display contract

- US fluid ounce = 29.5735295625 mL; pound = 0.45359237 kg; °F = °C × 9/5 +32.
- The app preference defaults to US, including existing installs without a value.
  Settings permits metric. mL/°C/kg remain canonical internally.
- Convert input at the boundary and display from canonical values. A unit switch
  must preserve the represented quantity, measurement error and validation range;
  it must invalidate pending previews if the actual quantity changes.
  Retain untouched canonical values: showing 250mL as 8.5fl oz must not save 251mL.
- Convert beverage totals/goal/log/edit, charts, workout and measurement forms,
  forecasts/analysis and Home explanations. mg, %, minutes and kcal are unchanged.
- Exact API/Meta payload previews remain exact canonical data, clearly labeled;
  US summaries may accompany them. Never mutate a saved provider result, consent
  hash or numerical prediction to implement display units.

## Setup and refresh contract

- One optional setup sheet on the first launch after this feature is installed.
  Explain and separately offer Health workout reads and automatic local weather.
  The owner can skip either and revisit Settings. No goal or manual data is invented.
- Health read authorization is requested only by the setup/connect/manual action.
  Automatic refresh queries existing access without raising a permission sheet.
  Read denial is indistinguishable from empty data; show that distinction honestly.
- Health workout/HR/energy summaries remain in memory on device. No automatic
  forecast upload, Health export, Meta call, drink logging or calibration creation.
- Automatic weather needs a new explicit option; the old tap-only weather consent
  must not silently become consent for background requests. Disclose that a rounded
  approximate area is stored on this iPhone for automatic Open-Meteo refresh.
  Store only the rounded area and weather metadata locally; clear it on revocation.
  No background location permission or continuous tracking. Foreground refresh may
  update the area after a previously granted when-in-use permission; background
  refresh uses only the saved rounded area, never prompts or requests a fresh fix.
- Keep independent Health/weather timestamps. Coalesce concurrent refreshes;
  new day or sufficiently old context becomes eligible, without repeated busy loops.
  Expired/canceled/revoked replies must not republish data. Errors never become zero.
  A persisted success timestamp cannot suppress a new process's in-memory Health
  load. Distinguish attempt timestamps from successful data freshness.
- The workout form offers automatic suggestions without overwriting an edited
  workout or silently changing an already previewed request. Requested forecast-hour
  weather stays distinct from current-area weather; stale/wrong-hour values must
  not be silently applied to a planned workout.
  Preserve requested/actual forecast-hour metadata through the form draft, and
  invalidate its provenance on workout-start changes.
- Home shows available context, freshness and setup access. Context is not used
  as an arbitrary hydration-score multiplier. Model numerical authority remains.

## Verification

Test conversion round trips and boundary values, migration/defaults, input unit
switches, consent/revocation and delayed replies, no permission prompts during
automatic refresh, local-day/timezone changes, duplicate refresh suppression,
empty/locked Health, missing cached area and background expiry. Run relevant
XCTest and the full native suite, actual Simulator setup/US-unit workflows and
post-change physical checks when the device remains available. All checks use
mock providers or GET-only readiness; a personal Meta request still needs its own
preview and consent. Keep diagnostics and actual health/location values private.

Apple references: [background earliest date](https://developer.apple.com/documentation/backgroundtasks/bgtaskrequest/earliestbegindate)
and [HealthKit privacy](https://developer.apple.com/documentation/healthkit/protecting-user-privacy).
