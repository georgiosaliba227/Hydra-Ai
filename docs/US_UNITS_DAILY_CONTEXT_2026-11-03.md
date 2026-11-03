# US units and automatic context — November 3

The owner reported real Health workout import and consented weather autofill on
the installed milestone, then requested American units and first-use setup with
automatic daily context updates. This feature is stacked on PR #73 and preserves
the numerical model, API contracts, spending authority and per-request Meta consent.

## Implemented

- US units by default: **US fl oz, °F and lb**. Settings offers metric. Drinks,
  chosen goal, workout/measurement inputs, history, charts, forecasts and ordinary
  explanation displays convert at the presentation boundary. mg, minutes, kcal
  and percentages keep their existing meaning.
- Canonical mL/kg/°C remain authoritative. Untouched quantities retain exact
  canonical values through rounded display and unit switches; edited beverages
  round once to the existing whole-mL API representation. Intervals round outward
  in the displayed unit. Exact Meta/API disclosures stay labeled canonical data.
- Optional first-use setup offers Health and automatic weather separately;
  either can be skipped and revisited in Settings. Old tap-only weather consent
  never silently enables automatic requests. The new option discloses storing a
  rounded approximate area on this iPhone for Open-Meteo refreshes.
- Automatic checks run at foreground/launch, local-day/timezone notifications,
  periodic active checks and available iOS background refresh. Health uses existing
  read permissions without an automatic authorization sheet. Background weather
  uses the saved rounded area, without a fresh/background location request.
- Health/workout summaries remain in memory on device. Only preference booleans
  and rounded area persist; weather and freshness are in memory. Source disable
  clears its context; weather disable/revocation removes the saved area. No new
  Health export, drink/calibration creation, forecast upload or Meta call occurs
  automatically.
- Current-area weather and planned-hour weather are distinct. The workout form
  fills a still-pristine draft automatically and does not overwrite user edits or
  an already reviewed request. Planned-time changes invalidate imported weather;
  the weather button can use the automatic opt-in without another manual opt-in.
- Home shows context freshness and Settings access alongside the existing score.
  Weather and Health do not add unsupported numerical score multipliers. Missing
  calibration still means insufficient data or the existing research baseline.

## Verification

- **217 XCTest passed** in the final integrated ad-hoc-signed Simulator build. The first
  full run omitted the Simulator entitlement-signing settings and failed Keychain
  checks; proper ad-hoc signing resolved those without a credential-source change.
  All final-review amendments are included in the 217-test run.
- **1,509 pytest +32 subtests passed**, no skips, one existing Starlette/httpx
  deprecation warning. Python source is unchanged by this feature.
- Actual Simulator UI: optional setup skip/non-repeat with Fahrenheit input;
  opted-in labeled sample Health prefill after relaunch; exact US intake/edit/
  chosen-goal/unit-switch/persistence; earlier metric logging/persistence flow;
  default workout/detailed-preview flow; explicit experimental cold-start/model-
  switch reset. These are **six actual Simulator UI flows**.
  These checks use unavailable or disposable synthetic backends, no paid action,
  and guard that actual financial-ledger bytes remain unchanged.
- The US backend flow retained an untouched **250 mL** record displayed as
  **8.5 fl oz**, logged another **8 fl oz**, then showed exactly **487 mL** after
  switching to metric. A chosen **64 fl oz** goal became **1,893 mL**. Normal
  relaunch retrieved the result without injected connection credentials.
- Task reviews resolved unit-token parsing, interval rounding, exact trends
  disclosure, explicit-connection cancellation and in-flight weather/revocation
  races with RED→GREEN regressions. The final combined fix wave also covers
  per-field partial-weather cleanup, cancellation of manual Health imports and
  typed Fahrenheit factor details. Its 89 focused tests and final scoped review
  pass; the whole branch has no outstanding review finding.
- The updated original app was installed and launched on the iPhone with strict
  signature verification and its valid HealthKit profile. The owner reports both
  automatic sources update successfully in US units. A separate **physical saved-
  connection UI test passed in 25.567 seconds**: a normal app launch, with no URL/
  credential overrides and no Save connection action, authenticated against the
  owner backend and showed ready with unverified billing disclosed. Financial
  ledger bytes remained unchanged; no paid action or screenshot was requested.

## Operational limits

iOS chooses whether and when background tasks run; an earliest requested date is
not a delivery guarantee. Locked Health data may be inaccessible. Actual success
times and failures stay visible, with foreground refresh and independent source
backoff. This is not proof of an unattended daily OS delivery on a physical phone.
See [Apple background scheduling](https://developer.apple.com/documentation/backgroundtasks/bgtaskrequest/earliestbegindate)
and [HealthKit privacy](https://developer.apple.com/documentation/healthkit/protecting-user-privacy).

The [physical milestone](PHYSICAL_HYDRATION_CHECK_2026-11-03.md) records scoped
evidence for both installations. Live personal Wonder still needs actual user records and an exact
in-app preview/consent. Scientific personal calibration still needs genuine
comparable measurements, not simulated training records. Mac backend availability
depends on the Mac/LAN; always-on deployment and public release remain unapproved.

The owner subsequently requested profile-guided goal calculation (birthday/age,
height, weight and supplements). That is a separate follow-up; this installed
milestone still uses a user-chosen goal. Published references, total-water versus
beverage distinctions and unsupported supplement adjustments need explicit design
before that follow-up can recommend a starting goal.
