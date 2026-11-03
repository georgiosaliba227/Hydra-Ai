# Hydration Intelligence Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for bounded tasks, with independent ML, backend and iOS agents as explicitly requested by the user. Steps use checkbox syntax.

**Goal:** Extend PR #65 into a reproducible, evidence-grounded numerical and explanation workflow with saved personal measurements.

**Architecture:** Preserve all existing endpoints and UI. Add offline grouped-selection artifacts, protected on-device history, and a nonbillable analysis composition endpoint. Existing Wonder preview, consent, replay and financial controls remain authoritative.

**Tech Stack:** Python/FastAPI, existing training-only scikit-learn, SwiftUI/XCTest.

**Spec:** `docs/superpowers/specs/2026-11-02-hydration-intelligence-design.md`; full user assignment supplied November 2.

## Global constraints

- No paid inference, deployment, private-ledger operations or automatic merge.
- No raw HealthKit export; no camera changes; no new runtime dependencies.
- Study-specific proxies are not physiological truth or drinking requirements.
- Use existing timezone/UTC, strict consent, 32-sample and 128 KiB boundaries.

## Review focus

- Copied or corrupted saved measurements must not become extra independent evidence.
- Changing a backend/credential must not expose history or revive consent.
- Synthetic analyses must never include real logs.
- Completed and planned exercise must not share a fluid-accounting window implicitly.
- Model selection must not optimize on historical test outcomes or hide baseline failures.

### Task 1: Recover and establish baseline (orchestrator)

- [x] Fetch remote branches and inspect PR #65, source commits and project docs.
- [x] Create an isolated branch based on PR #65; preserve main and camera branches.
- [x] Run the current full pytest baseline with pinned backend dependencies (1073 passed, 32 subtests; one elapsed-date fixture corrected).

### Task 2: Grouped model selection (ML agent)

**Files:** versioned additions in `ai/forecasting/`, `tests/forecasting/`, `docs/FORECAST_*`.
**Produces:** reproducible research artifacts/reports; no automatic app population prediction.

- [x] Add failing tests for participant-separated selection, baseline retention and evaluation isolation.
- [x] Implement grouped development validation and historical calibration/test evaluation (explicitly reused holdouts).
- [x] Audit additional primary-source public datasets and record inclusion/exclusion evidence.
- [x] Train on suitable real records, reproduce artifacts, report metrics and limitations; commit.
- [x] Add and independently review regularized within-person research learning with chronological selection, nonshrinking envelopes and synthetic counterexamples. Keep it offline: abrupt-change MAE and drift inclusion do not support promotion.

### Task 3: Persist consented calibration (iOS agent)

**Files:** `ios/HydraAI/Data/CalibrationHistory.swift`, workout view/store and XCTest/UI tests.
**Consumes:** unchanged `WorkoutForecastRequest.Sample`, maximum 32.
**Produces:** opt-in local save/load, inspect/export/delete without stored consent.

- [x] Add failing persistence/privacy/connection/corruption/duplicate tests.
- [x] Implement strict protected atomic history storage and UI controls.
- [x] Connect delete-all, invalidate stale forecasts/previews and preserve PR #65 workflows.
- [x] Run XCTest and targeted simulator persistence UI; commit (history milestone and protected physical storage verified).

### Task 4: Unified nonbillable analysis (backend agent)

**Files:** `backend/hydration_analysis.py`, registration in `backend/app.py`, focused tests.
**Consumes:** existing `WorkoutForecastInput` at `POST /v1/hydration-analysis`.
**Produces:** `hydration-analysis-v1` with numerical forecast, scoped intake/context, eight evidence-labeled sections and existing Wonder preview/replay.

- [x] Add failing contract/privacy/auth/body-limit/time-window tests.
- [x] Implement deterministic composition; abstain on unsupported balance accounting.
- [x] Validate no Meta call or synthetic disclosure, document exact wire contract; commit (32 focused tests and independent scientific review).

### Task 4b: Comprehensive Wonder analysis (backend and iOS agents)

**Files:** `backend/wonder_analysis.py`, new routes and existing gateway/result integration; separate typed iOS client/controller.
**Consumes:** allowlisted aggregates from `hydration-analysis-v1`; exact hash and separate explicit Meta consent.
**Produces:** eight required, vetted fact-specific sections. Muse Wonder selects phrasing; Hydra formats every fact. No arbitrary nonnumeric invention.

- [x] Add schema, strict scaffold/placeholder validation, exact payload reconstruction, mock/recorded replay and adversarial grounding fixtures (52 tests).
- [x] Wire existing financial gateway/transport/shared lock through a new disabled-by-default comprehensive flag; preserve all financial policies and private state.
- [x] Add exact saved replay/export/delete, stale/refusal/unresolved/concurrency and false-flag tests.
- [x] Wire iPhone preview/consent/results with generation guards and no automatic retries; test fixtures and mock simulator behavior (132 XCTest, actual default-off Simulator flow).

### Task 5: Integrate and review (orchestrator plus iOS followup)

- [x] Integrate reviewed agent commits without touching camera branches.
- [x] Display analysis cards in the workout flow and test stale/offline behavior.
- [x] Run full pytest, training checks, XCTest, actual mock-backend simulator flows and inspect screenshots.
- [x] Obtain independent branch review; fix important defects with regression tests.
- [x] Update PROJECT_STATUS, NEXT_ACTIONS, BLOCKERS, DECISION_LOG and scientific evaluation.
- [x] Commit, push, prepare review PR for Amine; report physical/live gates truthfully ([PR #71](https://github.com/georgiosaliba227/Hydra-Ai/pull/71), reviewer requested, no merge).

### Task 6: Fit a personal model in the app workflow (November 3)

**Contract:** `docs/architecture/PERSONAL_RUNTIME_API.md`.

- [x] Implement and test the fixed stationary regularized duration regression,
  earlier-only model selection, domain/freshness gates and conservative envelopes.
- [x] Reproduce software stress evaluation, including baseline wins and failures;
  report synthetic evidence separately from measured study validation.
- [x] Add authenticated v3 forecast/analysis/Wonder routes using one predictor,
  preserving legacy output, consent hashes, shared financial controls and privacy.
- [x] Integrate typed runtime metadata, method/fallback labels and exact numerical
  binding into the iPhone flow; rerun XCTest and real simulator UI.
- [x] Independently review the fit/selection and boundary integration, then run
  physical-device checks when connected and record actual evidence.
- [x] Close the selected-fit UI coverage gap: opt-in Simulator flow loads six
  externally prepared synthetic saved records with fresh consent, displays the
  actual backend fit and matching analysis/preview, then deletes the records.
  Production startup is unchanged; the empty-profile helper refuses nonempty
  histories and does not store consent.
