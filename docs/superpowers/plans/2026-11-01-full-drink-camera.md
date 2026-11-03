# Full-drink Camera Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Connect beverage recognition and supported size evidence to confirmed logging that defaults to consuming the entire liquid.

**Architecture:** Keep the guarded Meta gateway and explicit confirmation. Parse metric label capacity separately, prefill the whole-liquid estimate, and persist the user's assumption through the existing idempotent hydration engine.

**Tech Stack:** Existing Python/FastAPI/SQLite and SwiftUI; no new dependencies.

**Spec:** `docs/architecture/CAMERA_CORRECTIONS_API.md` (November 1 full-drink assignment).

## Global Constraints

- Preserve budget gates, authoritative financial history, one-use controls and no retries.
- No new billable call, private-ledger mutation, automatic training or health export.
- Capacity, visible liquid and user-assumed consumption stay distinct; confirmation is required.
- Unknown/ambiguous evidence stays unknown; never promise universal recognition accuracy.
- Extend the existing isolated `codex/camera-confirm-feedback` branch and draft PR.

## Review Focus

- Serving-size text must not become bottle capacity (Task 1).
- A known container with hidden fill must not silently become liquid present (Task 2).
- Unknown capacity must not force invented size when liquid amount is confirmed (Task 2).
- Partial consumption and later edits must not retain full-drink provenance (Task 2).
- Fake-provider UI evidence must not be reported as a successful new Meta call (Task 3).

### Task 1: Label capacity evidence

**Files:** new `backend/label_volume.py`; modify `backend/app.py`, `backend/recognition.py`; test `tests/recognition/test_label_volume.py`.
**Interface:** `label_capacity_ml(text: str | None) -> int | None`; additive `label_capacity_ml` candidate field.

- [x] Write failing parser/API tests for 500 mL, 0.75 L, net versus serving text, conflicting units, invalid/out-of-range values, and separation from original model capacity.
- [x] Observe failure, implement bounded deterministic extraction and response enrichment, then run the focused tests to green.

### Task 2: Whole-liquid confirmation and provenance

**Files:** modify schemas/app/store/domain/recognition confirmation and result; beverage row; backend/Swift tests.
**Interfaces:** optional `consumption_assumption` = `entire_liquid` / `full_container`; `RecognitionCandidate.wholeLiquidMl: Int?`; unknown capacity allowed on a confirmed liquid amount. `RecognitionEntryDraft` owns editable name/type and unit-aware volume; `beverage_type` persists independently from display name. Automatically present Confirm/Edit after analysis, with secondary details and learning controls under Edit.

- [x] Write failing API and Swift tests for prefill midpoint/correction, no capacity-to-fill substitution, known capacity bound, full-container equality, idempotent persistence, manual-source rejection, assumption clearing after correction, type memory, unit conversion and presets.
- [x] Observe failure, implement form defaults/partial toggle/full-container action plus provenance/history display, then run focused tests to green.

### Task 3: Integration and physical readiness

**Files:** update synthetic UI tests, verification report and PR description; existing private mock launcher only.

- [x] Run Swift unit tests and synthetic UI flows proving all-liquid defaults, partial correction, raw model/label/personal distinctions and deterministic totals.
- [x] Run full pytest; identify any baseline failure separately. Build/install the signed iPhone app and verify the owned backend remains mock/false.
- [x] Obtain a fresh read-only whole-change review; commit/push and update draft PR with evidence and unresolved live-test gates.
- [x] Revalidate billing/permit prerequisites read-only before any real dispatch. Without finality and a fresh exact-image approval, do not send; keep the full goal active and report the exact remaining gate.

Verified outcome: all implementation/nonbillable checks completed; the full live goal remains active because final billing evidence and a fresh exact-image paid authorization are unavailable. No real dispatch was made. Physical testing additionally required a finite-timestamp compatibility fix; see the verification report.
