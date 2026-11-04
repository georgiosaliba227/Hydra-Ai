# Simpler workouts and Muse insights

Status: Guided layout implemented. See [native verification](../../UI_SIMPLIFICATION_VERIFICATION.md) for evidence and limits.

## Intent

Help someone understand what a feature does, take the next step, and read the
result without processing a page of setup, research, and implementation details.
The user specifically identified workouts and Muse AI as too complicated.

## Current experience

Reviewed against `origin/main` at `27cc907`:

- Insights presents three large feature cards, each with an explanation and two
  additional claims, followed by Apple Health and another disclaimer.
- Workout is a single Form containing an introduction, synthetic demo, recorded
  Wonder response, workout fields, conditions, calibration, submission, results,
  and research comparisons. Numbered headers do not actually separate steps.
- Trends shows introduction/how-it-works, every result card, provenance, another
  data preview, consent and cost information on the same scrolling screen.
- Ask Hydra puts optional context and recorded Wonder controls alongside the
  core question flow, and repeats evidence and limitation text for answers.
- Today repeats the three Insights destinations and a previous-week report.

## Goals

- One obvious main task on each screen.
- Short labels and one-sentence descriptions.
- Keep the result, its essential uncertainty, and its meaning together.
- Show optional controls and supporting evidence when someone requests them.
- Preserve clear demo labels, data preview, explicit consent, and safeguards.
- Retain native SwiftUI, the existing teal theme, accessibility and Dynamic Type.

No backend contract, model, calculation, AI policy, budget, credential, camera,
HealthKit access, or data-retention changes. No dependency additions. No request
is made merely by moving between workout steps or opening the Muse review.

Avoid hiding essential uncertainty, implying simulated results are personal,
truncating generated answers, or making a medical or drinking recommendation.

## Approaches

1. **Guided workout with results first elsewhere — recommended.** Replace the
   long workout form with three focused steps and move calibration into a
   dedicated sheet. Simplify Insights and Muse using the same principle of one
   task at a time. More navigation, substantially less competing content.
2. **Compact single page.** Keep workout setup on one screen and collapse its
   optional areas. Faster for experienced users, but fields and prerequisites
   still compete with results on smaller phones.

The user selected “Guided steps: workout → conditions → result” after the
clickable preview and written design were shared. Guided is the implementation
direction; Compact remains a considered alternative.

## Screen design

### Insights

Show a title, one short subtitle, and three compact navigation rows:

- **Your trends** — Patterns in your drink log. Small Muse AI label.
- **Plan a workout** — Estimate workout sweat loss.
- **Ask Hydra** — Answers to common drink questions.

Keep Apple Health as a quieter row below these. Show a single actionable
connection message when needed, with a route to Settings. Move provider/model
explanations to the destination's details. Preserve the existing tab structure.

### Workout

Keep the title “Plan a workout”. Show a small textual progress indicator, the
current step title, and a single primary action. Back preserves the draft.

1. **Your workout.** Activity, duration and intensity; start date/time is
   available in a compact “Starts” row. “Continue” validates only these inputs.
   A secondary “Try a demo” action opens a separate demo mode, never pre-fills
   the personal draft or becomes its result.
2. **Conditions.** Temperature and humidity, with units always visible. A
   “Past measurements” row opens the existing manual measurement workflow in
   a sheet. Show the count and explain that comparable measurements are needed
   for a personal estimate. Keep the comparable-conditions confirmation with
   an expandable description of what must match. Continue validates weather.
3. **Review & estimate.** A compact workout/conditions summary with Edit actions.
   Explain missing measurements or comparability before submission; don't
   pretend that entering duration and weather alone is enough. Calibration
   consent remains default-off and visible here, required before processing any
   measurements. Consent identifies backend processing and session-only storage.
   The primary action submits only the existing request contract.

The result replaces the review content in step 3. An available estimate shows
the value, mL, “Estimated sweat loss”, the returned range and its essential
qualification. Keep “Not a drinking target” beside the result. An insufficient
result shows “More measurements needed” plus the specific missing information
in readable terms and “Add measurements”; never a zero or placeholder estimate.
The backend remains authoritative on sufficiency; do not hardcode a sample-count
threshold in the UI. A user with no samples can see the prerequisite before
submitting, while the existing insufficient-data response remains supported.

The measurement sheet retains every currently required value and error bound,
the protocol confirmation, duplicate prevention, 32-sample ceiling, removal,
validation, units and consent. Group “Workout measurements” and “Measurement
accuracy”; neither unknown measurements nor unknown error bounds become zero.
Protocol details are expanded when adding a measurement. This is an advanced
task with necessary detail, separated from everyday workout setup.

Demo mode has its own result view, “SIMULATED · not your measurements” next to
the result, and a secondary “Recorded Muse explanation” action. Loading a
recorded explanation must say it was recorded and sends nothing to Meta. Its
text must not appear as a personal explanation. Research/mock comparisons and
provider telemetry belong in demo details, never the personal result body.

“About this estimate” holds model, input factors, provenance and full limitations.
Essential interval qualifications stay outside this disclosure. Preserve the
experimental qualification for longitudinal-history ranges. On input edits,
invalidate the result; on leaving the flow or changing backend, cancel tasks and
clear all session measurements, consent and results. Changing backend must also
reset any open sheet and return to the first step so stale consent cannot persist.

### Your trends / Muse

Without a saved explanation, show one short introduction, the 14-day window and
“Review data & explain”. With a saved explanation, lead with its summary and
the first complete insight. “More insights” reveals the remaining complete
insights. Keep the explanation's own date window visible so an older explanation
cannot be mistaken for the current preview.

“Review data & explain” opens a dedicated review sheet. It lists the actual
14-day summary and an expandable **complete payload**: all daily totals/counts,
every category including the remainder, time-of-day totals, goal, date window,
timezone, and other facts actually sent. The current preview only shows the top
three categories; the redesigned review must not claim that abbreviated display
is the exact full payload. Render this from the typed TrendFacts value rather
than creating a new payload or recomputing numbers.

The account/cost bound, Meta recipient, explicit default-off consent, and
“Explain my trends” action stay together and visible in the review. Opening it
does not consent or send. No live action is offered if capabilities are
unavailable. Already-explained data shows its saved result without another
submission. Errors explain the next available action; never add automatic retry.
Closing/reopening the sheet or changing the backend resets consent. Prevent a
second submission while explaining. A result is accepted only through the
existing digest and controller validation. Preserve late-response invalidation.

Keep a short note that drink logs do not measure hydration visible with results.
“Sources & details” holds full limitations, model, provenance, and existing
billing observations; no developer telemetry competes with the main explanation.

### Ask Hydra

Show the question input and Ask action first, then three suggested questions.
“All questions” reveals the rest. Move optional today's-log context and recorded
Wonder mode into “Answer options”. Label recorded mode persistently when active.
Never include today's total in recorded mode, as required by its existing API.
In ordinary mode the optional total remains default-off.

Answers remain full text. Keep urgent-answer styling and instructions directly
visible. Put links under an accessible “Sources” disclosure for each answer.
Keep any limitation essential to interpreting an answer visible; provenance and
repeated implementation explanations go under details. Invalidate old answers
and pending tasks when inputs, mode, or backend change.

### Today

Keep logged volume, quick logging, and recent drinks as the main content. Replace
the three repeated feature entries with one “Explore insights” link. Existing
destination identifiers/tests are updated to navigate through Insights. Move the
previous-week report into History, where WeeklyVolumeView already lives; retain
the full report and its missing-log qualification under a collapsed “Logging
details” disclosure there rather than removing it. The weekly chart keeps a short
missing-log qualification visible.
Do not change logging, totals, goals, pending submissions, camera, or settings.

## Implementation boundaries and builder decisions

Reuse HydraStyle and existing controllers. Use small SwiftUI subviews for the
workout step body, calibration sheet, result and trend review. State belongs to
the parent flow; sheet dismissal alone does not discard a workout draft. The
builder may choose exact spacing, SF Symbols and local state types. Use current
field validation and boundary limits, surface errors beside the relevant action,
and focus the first invalid field. Do not invent default weather or measurements.

Native sheets need a visible Close/Done action and support Dynamic Type. Labels
wrap; primary controls have at least 44-point tap targets. VoiceOver reads step
progress, result units, disclosure state and validation feedback. Do not rely on
color or small badges alone to distinguish demo, recorded and personal results.
Avoid custom animations; honor Reduce Motion for any transitions.

## Verification and acceptance

- Unit tests: existing Swift controller/request/validation suites, especially
  cancellation, invalid response, consent and stale response cases.
- UI tests against a local synthetic/mock backend: compact Insights navigation,
  steps/back/edit, invalid input, calibration sheet and default-off consent,
  explicit demo path and unchanged consumed total, insufficient-data state,
  trend preview before consent, no live action on mock backend, sources and
  optional answer controls. Test opening/dismissing review does not send.
- Visual checks on small and large iPhones, light/dark appearance, accessibility
  text sizes and VoiceOver order; capture representative screenshots.
- Full pytest and relevant XCTest before a review PR, with no live Meta calls.
- Document what was actually verified; simulator checks do not establish
  scientific accuracy, physical HealthKit behavior or physical-device usability.

Success: a new user can identify each feature's purpose and next action on its
first screen; the workout never shows all steps and demos together; personal
results show their meaning/range/qualification together; Muse details are one
intentional action away and sending always requires a complete review and consent.

## Design review record

- A fresh SwiftUI builder review reported “nothing important left” after reading
  this design. This is a design-completeness check, not a code review.
- The chat includes an interactive design sample with Guided and Compact
  alternatives. Its numbers, navigation and result placeholders are illustrative;
  it has no backend connection, personal data, or provider requests.
- Manually checked in the browser: missing-duration feedback, steps 1–3,
  preservation of a 45-minute draft when editing, Insights/Trends navigation,
  default-off review consent, disabled explanation preview before consent and
  consent reset after cancel/reopen. Inspected the review at a 320-pixel browser
  width and corrected the heading layout.
- The preceding design-stage checks happened before product implementation.
  The user subsequently selected Guided, and implementation proceeded in the
  existing SwiftUI app. Implementation verification is recorded separately.

## Implementation baseline

Verified on the unchanged product at `350f1b7` before implementation:

- Full maintained Python suite: **1,319 passed, 5 skipped**, plus 58 passing
  subtests. The one warning is the existing FastAPI/Starlette TestClient httpx
  deprecation; no dependencies were changed. Command:
  `/Users/georgiosaliba/Desktop/Hydra-Ai/.venv/bin/python -m pytest -q tests`.
- iOS unit suite: **102 tests passed, 0 failures**, using Xcode's iOS 26.5
  iPhone 17 Pro simulator and ad-hoc signing. Command:
  `xcodebuild -project ios/HydraAI.xcodeproj -scheme HydraAI -destination
  'platform=iOS Simulator,id=91E9720B-63F2-4A99-8982-5BF28B810F66'
  -derivedDataPath /tmp/hydra-simplify-baseline-derived
  -resultBundlePath /tmp/hydra-simplify-baseline-unit.xcresult
  CODE_SIGN_IDENTITY=- CODE_SIGNING_ALLOWED=YES -only-testing:HydraAITests
  -parallel-testing-enabled NO -collect-test-diagnostics never test`.
- Both commands exited successfully. Local logs are
  `/tmp/hydra-simplify-baseline-pytest.log` and
  `/tmp/hydra-simplify-baseline-xctest.log`; the XCTest result bundle is at the
  path above. These temporary artifacts are not part of the review commit.
- These are baseline results for existing code, not proof of the redesign.
  Native UI automation, physical-device checks and the proposed accessibility
  acceptance checks remain to be performed after implementation.
