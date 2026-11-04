# Combined Camera and Hydration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the working local camera and deliver the hydration stack in one iPhone app and owner backend.

**Architecture:** Merge current main `27cc907` into a fresh branch from hydration `1c28dad`. Keep the saved port-8771 connection and existing camera database/runtime; explicitly opt in to independently guarded Wonder coexistence without changing admission or provider consent.

**Tech Stack:** Existing FastAPI/Python, SQLite and SwiftUI/XCTest; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-03-combined-camera-hydration-design.md`

## Global Constraints

- Preserve private stores, ledger, holds, owner waivers, pinned camera runtime and saved URL/token; no silent migration/reset.
- No hosted camera fallback, automatic personal Meta call, retry, deployment or automatic GitHub merge.
- Canonical mL and precise finite date validation; display units remain a presentation preference.
- Keep experimental fitting off by default and preserve supported insufficient-data responses.
- Mock-only automated checks; avoid Simulator memory contention during local-camera demos.

## Review Focus

- A stale coexistence flag with the wrong mode must fail startup: Task 1 invalid-mode matrix.
- Camera photo/confirmation must never dispatch Wonder or change finance: Task 1 combined mocked flow with byte comparison.
- Rounded US label review must retain exact canonical mL and historical consumption date: Task 2 native/UI tests.
- Date non-finiteness must fail without losing reference-epoch adjacent precision: Task 2 both date suites.
- App update must retain the saved camera connection and private store identity: Task 3 status-only physical check/metadata receipt.

### Task 1: Combine backend histories and prove provider isolation

**Files:** `backend/app.py`, `AGENTS.md`, `tests/recognition/test_combined_backend.py`, `tests/recognition/test_wonder_workout.py` and automatically merged camera additions.

**Interfaces:** Retain `create_app(db_path=None, api_token=None) -> FastAPI`, `RequestGuard`, `LocalMetaRecognizer`, existing Wonder `LiveConfig` and owner authority. Add only the validated default-false environment selector described in the spec.

- [ ] Write invalid-selector tests before implementation; run them to establish behavioral failure against the old configuration handling.
- [ ] Merge `origin/main` locally. Resolve app conflicts by combining v3/analysis auth/body bounds with camera opt-in-photo bounds and correction export; retain the hydration publication/delete lock and all route installs. Combine both dated AGENTS histories.
- [ ] Implement the explicit selector without changing Wonder factories, policy or camera recognizer selection.
- [ ] With disposable fixtures/fake runtime/transports, verify exact combined admission, rejected flag combinations, camera no-network/unchanged-ledger behavior, protected v1/v3 previews, no-consent/stale rejection, one fake send and free replay; blocked Wonder must not disable local camera.
- [ ] Run focused recognition/analysis/owner-policy tests, then the full Python suite. Review and commit the backend union with native merge resolutions once Task 2 checks pass.

### Task 2: Preserve both native workflows

**Files:** conflict paths in `BeverageRow`, `BeverageLog`, `HydrationContextComparison`, `IntakeHistoryForecast`, `RecognitionConfirmationView`, `WorkoutForecastView`, `BackendSettingsView`; semantically merged `BeverageStore`, `HTTPBeverageService`, `EditBeverageView`; `RecognitionEntryDraft`, date helpers and camera UI tests as needed.

**Interfaces:** Keep camera extended `BeverageStore.add`/feedback/assumption types and hydration stores/generation guards. Use `DisplayUnits`, canonical draft quantities, existing UI launch/metric helpers and both date helper names.

- [ ] Resolve native conflicts preserving the camera whole-drink draft, editable historical date, correction/training consent, guided goal, local deletion and all hydration sections. Keep sourced nutrition only while `draft.keepsProductMatch` is true.
- [ ] Add/run regressions for US exact-capacity review and unit switching plus adjacent/nonfinite date boundaries before making their minimal corrections. Preserve old API quantities, hashes and feedback.
- [ ] Run all native XCTest. Adapt old camera-only UI fixtures to explicit metric mode and add a US review regression; keep the local-inference test excluded.
- [ ] Run actual synthetic Simulator flows for camera confirmation/correction, guided goal/context, forecast cold start and detailed Wonder preview/replay; inspect screens and capture private evidence. No real data or provider runtime.
- [ ] Obtain an independent combined-diff review and resolve concrete findings. Commit verified integration, retaining ancestry of both feature heads.

### Task 3: Preserve live runtime and deliver a reviewable build

**Files:** private combined launcher/evidence outside Git; `docs/PROJECT_STATUS.md`, `docs/NEXT_ACTIONS.md`, `docs/BLOCKERS.md`, `docs/DECISION_LOG.md`, combined evidence report.

**Interfaces:** Existing owner token (compared equal in memory), camera database and runtime config, authoritative Wonder ledger/policy/quote/results paths, original signed app identifier.

- [ ] Stage a private combined launcher and rollback receipt; verify the camera server has no active inference before replacement. Keep both private beverage stores separate, preserve camera diagnostics and avoid printing credentials or health values.
- [ ] Verify startup/read-only capabilities and fresh-or-blocked Wonder readiness with unchanged financial bytes and personal-row digests. A blocked freshness check is truthful and must be renewed from genuine evidence before inference.
- [ ] After the announced preservation step, carry over only the previously confirmed goal integer if the camera store still has none; verify both drink histories, source settings and financial bytes unchanged, and retain a private status-only receipt.
- [ ] Build and verify HealthKit signing; install in place without reset or connection injection. Check the saved connection/capabilities without dispatch; ask only necessary status-only owner questions after the correct build is installed.
- [ ] Update accurate status/evidence, push a review branch/PR for Amine, and verify publication. Keep the actual personal preview/consent/result/replay and genuine measurement requirements explicit until established.
