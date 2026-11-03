# US units and automatic context implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development or
> superpowers:executing-plans for the bounded tasks below.

**Goal:** US-first native units and optional one-time setup with consented automatic context refresh.

**Architecture:** Canonical numerical/API units remain unchanged. Separate display
conversion and daily context orchestration from views and existing manual providers.

**Tech stack:** Existing SwiftUI, XCTest, HealthKit, CoreLocation, BackgroundTasks;
no new dependencies or backend deployment.

**Spec:** `docs/superpowers/specs/2026-11-03-us-units-daily-context-design.md`.

## Global constraints

- No raw Health export, automatic Meta calls, invented logs/measurements or goals.
- US defaults: fl oz, °F, lb; API/storage remain mL, °C, kg.
- Separate automatic-weather disclosure; no migration from tap-only consent.
- Background scheduling is best effort; no background location request.
- Preserve edited inputs, exact canonical previews, consent binding and all ledgers.

## Review focus

- Existing metric text must never be reinterpreted after a preference switch.
- Permission revocation/canceled tasks must discard late replies and cached area.
- A cached weather hour must not become a different planned-hour forecast.
- Empty or locked Health must not assert denial or zero activity.
- First-use UI must remain skippable and all existing flows remain reachable.

### Task 1: Unit boundary and app display adoption

Files: new `ios/HydraAI/Data/DisplayUnits.swift`, corresponding XCTest;
beverage/Home/history/analysis/Settings views. Root owns WorkoutForecastView,
BackendSettingsView, RootView and HydraAIApp integration; coordinate before edits.

Interface: `DisplayUnitSystem.us/.metric`; pure conversion methods for volume,
mass and temperature, stable formatting and persisted app preference.

- [ ] Write failing assertions for 8 fl oz =236.5882365mL, 32°F=0°C,
  212°F=100°C, 1lb=0.45359237kg, invalid/nonfinite input and quantity-preserving
  unit-switch round trips. Run selected XCTest and observe failure.
- [ ] Implement the shared boundary, formatter and preference; preserve exact
  canonical payload strings in disclosure views. Adopt display in owned views.
- [ ] Run focused tests, report exact API to root, inspect changes and commit only owned files.

### Task 2: Consented daily context service

Files: new `ios/HydraAI/Data/DailyContext*.swift` and XCTest;
`WorkoutContextProvider.swift`, `WeatherAutofill.swift` and Health clients as needed.
No view/project/ledger edits in this task.

Interface: MainActor `DailyContextCoordinator: ObservableObject`, shared
`workoutContext: WorkoutContextProvider`, published setup/refresh/freshness status;
explicit connect/enable/disable methods; `refreshIfNeeded` foreground/background
mode, and cancel/expiration hooks. Publish exact final signatures to root early.

- [ ] Write failing tests for no automatic permission prompt, new-day eligibility,
  concurrent suppression, locked/empty Health, independent timestamps, no cached
  area in background, permission revocation/cancellation and stale-hour handling.
- [ ] Implement preference/rounded-area storage, no-prompt refresh and privacy
  cleanup with injected clock/providers. No health summary persistence or Meta calls.
- [ ] Run focused tests; report signatures, evidence, limitations and commit owned files.

### Task 3: First-use UI, lifecycle and forecast integration

Files: `HydraAIApp.swift`, `RootView.swift`, `BackendSettingsView.swift`,
`WorkoutForecastView.swift`, new setup/context views, project metadata, relevant
native/UI tests and shared status documents. Root owns this task.

- [ ] Test US form conversion, setup skip/restore, no repeat setup, old tap-only
  consent remaining separate and non-overwrite of edited/previewed requests.
- [ ] Add optional setup, Settings controls and Home context/freshness presentation.
  Register permitted BGAppRefresh identifier and cancellation-safe lifecycle;
  refresh at foreground/day boundary and reschedule background opportunities.
- [ ] Integrate unit conversions in the workout form and context suggestions
  without overwriting edits or sending data automatically.
- [ ] Run full XCTest, relevant Simulator UI flows, pytest as required by repository
  checks, inspect screens, and obtain independent whole-change review.
- [ ] Install/verify the updated physical build when available; update docs with
  actual evidence, commit/push and open a review PR stacked on #73. No merge/deploy.
