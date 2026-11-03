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
- [ ] Run the current full pytest baseline with pinned backend dependencies.

### Task 2: Grouped model selection (ML agent)

**Files:** versioned additions in `ai/forecasting/`, `tests/forecasting/`, `docs/FORECAST_*`.
**Produces:** reproducible research artifacts/reports; no automatic app population prediction.

- [ ] Add failing tests for participant-separated selection, baseline retention and evaluation isolation.
- [ ] Implement grouped development validation and untouched calibration/test evaluation.
- [ ] Audit additional primary-source public datasets and record inclusion/exclusion evidence.
- [ ] Train on suitable real records, reproduce artifacts, report metrics and limitations; commit.

### Task 3: Persist consented calibration (iOS agent)

**Files:** `ios/HydraAI/Data/CalibrationHistory.swift`, workout view/store and XCTest/UI tests.
**Consumes:** unchanged `WorkoutForecastRequest.Sample`, maximum 32.
**Produces:** opt-in local save/load, inspect/export/delete without stored consent.

- [ ] Add failing persistence/privacy/connection/corruption/duplicate tests.
- [ ] Implement strict protected atomic history storage and UI controls.
- [ ] Connect delete-all, invalidate stale forecasts/previews and preserve PR #65 workflows.
- [ ] Run XCTest and targeted simulator persistence UI; commit.

### Task 4: Unified nonbillable analysis (backend agent)

**Files:** `backend/hydration_analysis.py`, registration in `backend/app.py`, focused tests.
**Consumes:** existing `WorkoutForecastInput` at `POST /v1/hydration-analysis`.
**Produces:** `hydration-analysis-v1` with numerical forecast, scoped intake/context, eight evidence-labeled sections and existing Wonder preview/replay.

- [ ] Add failing contract/privacy/auth/body-limit/time-window tests.
- [ ] Implement deterministic composition; abstain on unsupported balance accounting.
- [ ] Validate no Meta call or synthetic disclosure, document exact wire contract; commit.

### Task 5: Integrate and review (orchestrator plus iOS followup)

- [ ] Integrate reviewed agent commits without touching camera branches.
- [ ] Display analysis cards in the workout flow and test stale/offline behavior.
- [ ] Run full pytest, training checks, XCTest, actual mock-backend simulator flows and inspect screenshots.
- [ ] Obtain independent branch review; fix important defects with regression tests.
- [ ] Update PROJECT_STATUS, NEXT_ACTIONS, BLOCKERS, DECISION_LOG and scientific evaluation.
- [ ] Commit, push, prepare review PR for Amine; report physical/live gates truthfully.
