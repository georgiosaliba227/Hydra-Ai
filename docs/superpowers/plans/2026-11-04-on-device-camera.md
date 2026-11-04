# On-device Camera MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Execute continuously under the owner's accepted MVP scope.

**Goal:** A focused Meta-based camera that analyzes, reviews and saves drinks on the iPhone without a Mac or network.

**Architecture:** Bundle a frozen DINOv2 Small plus trained beverage head as Core ML; use local Apple Vision OCR with conservative capacity parsing. Add explicit on-device recognition and an isolated real local store, retaining existing server and demo paths.

**Tech Stack:** SwiftUI, Core ML, Vision, Foundation; isolated Python training/conversion tools.

**Spec:** `docs/architecture/ON_DEVICE_CAMERA.md`

## Global Constraints

- iOS 17 minimum; Meta core image model; no iPhone package dependency.
- No hosted inference, runtime weight downloads, automatic fallback, financial edits, training photos or health export.
- Keep dataset splits; report empirical category results, not brand/size recognition accuracy.
- Capacity is not remaining liquid or consumption; preserve unknowns, original prediction and confirmed assumptions.
- Preserve backend credentials/history and separate legacy mock data; no automatic data movement.

## Review Focus

- Serving/multipack/conflicting label quantities must not become container capacity.
- Offline saves must remain real records, durable/idempotent and never reach HTTP.
- Mode changes or delayed analysis must not save against another destination.
- Missing/bad model or non-beverage evidence must not trigger server fallback or pretend confidence.
- Private photos and unrelated OCR must not persist or enter logs.

### Task 1: Train/export a compact Meta category model

Files: `ai/on_device/`, `scripts/train_on_device_beverage.py`, `tests/on_device/`, bundled model metadata under `ios/HydraAI/Resources/`.
Interface: Core ML image input `image` RGB224×224; output `scores` Float32 `[1,12]`; fixed ordered drink-family labels in metadata. Image input scale1/255, internal ImageNet normalization; full-image square resize, no crop.

- [ ] Write/run failing dataset/split and classification-selection tests.
- [ ] Verify existing public image hashes; train head using train only, select on validation, evaluate test once; retain provenance and results.
- [ ] Export Core ML, compare Python/Core ML scores, record package/source hashes and installable-size evidence.
- [ ] Commit code, metadata/reports and reproducible export instructions; keep large build artifacts out of Git where appropriate.

### Task 2: Local inference, conservative labels and real local persistence

Files: `ios/HydraAI/Features/Camera/OnDevice*.swift`, `ios/HydraAI/Data/LocalBeverageService.swift`, `APIConfiguration.swift`, `BeverageStore.swift`, `Domain/BeverageLog.swift`, corresponding XCTest.
Interfaces: `OnDeviceRecognizer.analyze(jpeg: Data) async throws -> RecognitionResult`; mode `on_device`, model `dinov2-small-beverage-v1`. Add optional on-device storage configuration with backward-compatible decoding; local logs retain original recognition metadata without photos or unrelated OCR.

- [ ] Add/run failing tests for printed sizes, unavailable inference, local restart/idempotency/export/delete and provenance.
- [ ] Implement bounded serialized inference and pure deterministic label parsing with explicit units.
- [ ] Implement separate protected real local storage and destination binding, preserving legacy demo/backend paths.
- [ ] Run focused XCTest; commit.

### Task 3: Camera/review/settings integration and verification

Files: camera presentation/session/view, confirmation view, backend settings, UI tests, setup docs.
Interface: explicit on-iPhone mode works without capabilities HTTP; Confirm saves into local store and always requires user review; server paths keep their own controls.

- [ ] Add/run failing mode/stale-session and offline camera UI tests.
- [ ] Wire on-device analysis, source/consent copy, local export/delete and source provenance into existing Confirm/Edit.
- [ ] Run complete pytest/XCTest, real model simulator case, signed generic device build and fresh whole-branch review.
- [ ] Stage signed app, install in place and verify airplane-mode/restart when phone reachable; report exact physical limits.
- [ ] Commit verified branch and prepare review handoff without merging/deployment.
