# Simpler Insights Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Reduce reading and competing choices across workouts, Muse, Ask Hydra and Today.

**Architecture:** Keep existing SwiftUI controllers and API boundaries. Give workouts real step state with separate calibration/demo sheets; give Muse a focused result screen and separate data review. Reuse HydraStyle and native navigation.

**Tech Stack:** SwiftUI, XCTest, existing Python/FastAPI backend; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-03-simpler-insights-design.md`

## Global Constraints

- No backend contract, model, calculation, AI policy, budget, credential, camera, HealthKit access, or data-retention changes.
- No request is made merely by moving between workout steps or opening the Muse review.
- Preserve explicit consent, invalidation, units, simulated/recorded labels and essential uncertainty.
- Use full generated/reviewed text and native Dynamic Type; primary controls have at least 44-point tap targets.
- Keep all verification nonbillable, against disposable synthetic data only.

## Review Focus

- Back/edit after a result must preserve the draft and invalidate stale estimates.
- Changing backend or leaving a flow must dismiss sheets, clear measurements and reset consent.
- A saved Muse result may cover older facts than the current preview; show its own window.
- Small phones and accessibility text must wrap without hiding primary actions.
- Optional recorded assistant picks must never acquire today's logged-total context.

## Task 1: Guided workout

**Files:** Modify `ios/HydraAI/Features/Forecast/WorkoutForecastView.swift`; create `WorkoutDraft.swift` and `WorkoutResultView.swift` beside it; modify `ios/HydraAIUITests/WorkoutForecastUITests.swift`.

**Interfaces:** Consume existing `WorkoutForecastController`, `RecordedWonderController`, `WorkoutForecastRequest`. Produce `WorkoutDraft` validation/request construction and `WorkoutResultView(result: WorkoutForecast)` reused by the separate demo. No API changes.

- [x] Add `testWorkoutStepsValidateAndPreserveDraft`: assert one step at a time, missing duration error, valid Continue, missing weather error, Back retains duration, calibration opens separately, review explains missing measurements.
- [x] Run that UI test on a loopback mock backend; expect failure because the step Continue action is absent.
- [x] Implement 3 steps, focused input errors, review summary/Edit actions, calibration sheet, separate demo sheet and result view. Keep optional hooks disabled. Invalidate/cancel on input/backend changes; preserve draft while sheets open; reset whole flow on leaving/backend change.
- [x] Update demo regression to open the demo, verify simulated labeling/range and unchanged logged volume; open research details intentionally.
- [x] Run workout UI tests and existing workout unit tests; expect pass. Capture screenshots, then commit.

## Task 2: Focused Muse and assistant

**Files:** Modify `ios/HydraAI/Features/Trends/TrendsView.swift`, create `TrendDataReview.swift` beside it; modify `ios/HydraAI/Features/Assistant/AssistantView.swift`, `ios/HydraAIUITests/TrendsUITests.swift`, `AssistantUITests.swift`.

**Interfaces:** Consume `TrendPreview`, `TrendFacts`, `WonderTrendsController`, `AssistantController`; produce `TrendDataReview(preview: TrendPreview, controller: WonderTrendsController, connected: Bool, explain: () -> Void)` with locally owned consent. Keep existing request validation and digest checks.

- [x] Add UI checks for explicit review entry, complete-data disclosure, default-off consent/no live action on mock, cancel/reopen, and collapsed assistant options/sources. Run before implementation; expect missing review/options entry failures.
- [x] Implement results-first trends, first complete insight plus More insights, correct saved-result window, separate review with all typed facts, account/cost/consent together, no request on open/dismiss and reset consent on dismissal/backend change.
- [x] Implement 3 assistant suggestions plus All questions, Answer options, recorded mode indicator and per-answer Sources. Retain urgent and essential limitation text.
- [x] Run trends/assistant UI cases and existing controller/unit cases; expect pass. Capture screenshots and commit.

## Task 3: Simplify entry points and finish verification

**Files:** Modify `ios/HydraAI/Features/Insights/InsightsView.swift`, `Dashboard/DashboardView.swift`, `History/HistoryView.swift`, add a reusable `ios/HydraAI/Components/IntakeHistoryCard.swift`; update affected UI navigation and `ios/README.md`.

**Interfaces:** Reuse `FeatureRow`, `HydraDisclosure`, `BeverageStore`. Move the existing previous-seven-days card intact into History. Today uses one `exploreInsights` link; destination IDs remain on Insights rows.

- [x] Add a UI assertion that Today has one Insights entry and Insights exposes 3 compact destinations; update affected existing tests to use the new route. Run before shell changes; expect missing Explore insights.
- [x] Replace verbose hub cards, duplicate Today destinations and repeated footer explanations; retain logging, goal, pending-delivery and history coverage behavior.
- [x] Run all maintained pytest, full iOS unit suite and affected opt-in UI suite on the mock backend. Inspect light/dark, small/large simulator layouts and accessibility text. Fix functional/accessibility issues; document limits.
- [x] Update docs and plan verification record. Commit, request one fresh whole-branch code review and address important findings with regression coverage.
- [x] Create an unmerged review PR for Amine: https://github.com/georgiosaliba227/Hydra-Ai/pull/79.

## Execution record

- User selected “Guided steps: workout → conditions → result” after the preview and design were shared. Implement this layout directly; routine code organization remains the builder's decision.
- Native execution chosen to keep the tightly related SwiftUI changes in one context, followed by one independent review.
- Existing baseline: 1,319 pytest passed / 5 skipped; 102 XCTest passed. These precede implementation and do not verify the redesign.

- Implementation validation: 1,322 Python tests / 5 skips / 58 subtests; starter 3;
  iOS unit 103. Nineteen affected native UI cases, separate persistence/history-edit,
  final main-screen accessibility audit and four compact dark-mode UI cases pass.
  See `docs/UI_SIMPLIFICATION_VERIFICATION.md` for exact scope and limits.
