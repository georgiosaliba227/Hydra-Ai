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

- [x] Write/run failing dataset/split and classification-selection tests.
- [x] Verify existing public image hashes; train head using train only, select on validation, evaluate test once; retain provenance and results.
- [x] Export Core ML, compare Python/Core ML scores, record package/source hashes and installable-size evidence.
- [x] Commit code, metadata/reports and reproducible export instructions; keep large build artifacts out of Git where appropriate.

### Task 2: Local inference, conservative labels and real local persistence

Files: `ios/HydraAI/Features/Camera/OnDevice*.swift`, `ios/HydraAI/Data/LocalBeverageService.swift`, `APIConfiguration.swift`, `BeverageStore.swift`, `Domain/BeverageLog.swift`, corresponding XCTest.
Interfaces: `OnDeviceRecognizer.analyze(jpeg: Data) async throws -> RecognitionResult`; mode `on_device`, model `dinov2-small-beverage-v1`. Add optional on-device storage configuration with backward-compatible decoding; local logs retain original recognition metadata without photos or unrelated OCR.

- [x] Add/run failing tests for printed sizes, unavailable inference, local restart/idempotency/export/delete and provenance.
- [x] Implement bounded serialized inference and pure deterministic label parsing with explicit units.
- [x] Implement separate protected real local storage and destination binding, preserving legacy demo/backend paths.
- [x] Run focused XCTest; commit.

### Task 3: Camera/review/settings integration and verification

Files: camera presentation/session/view, confirmation view, backend settings, UI tests, setup docs.
Interface: explicit on-iPhone mode works without capabilities HTTP; Confirm saves into local store and always requires user review; server paths keep their own controls.

- [x] Add/run failing mode/stale-session and offline camera UI tests.
- [x] Wire on-device analysis, source/consent copy, local export/delete and source provenance into existing Confirm/Edit.
- [x] Run complete pytest/XCTest, real model simulator case, signed generic device build and fresh whole-branch review.
- [x] Stage signed app and strict signature/profile verification; report exact physical limits.
- [x] Install signed update in place and launch on registered physical iPhone over Wi-Fi after owner-completed Device Hub pairing.
- [x] Verify physical airplane-mode recognition/save and force-close/reopen persistence; owner confirmed both worked with Wi-Fi off.
- [x] Commit verified branch and prepare review handoff without merging/deployment.

Final code verification: 1,336 pytest passed, 5 skipped, 58 subtests; 129 signed simulator XCTest passed; two real-model UI cases passed. Four independent-review Important groups and source-copy issue fixed with regression tests. The signed app is staged privately and installed/launched wirelessly on the registered phone. A focused physical model/OCR XCTest passed; the owner separately confirmed offline analysis/save with airplane mode on and Wi-Fi off, and entry persistence after force-close/reopen.

Follow-up: owner reported that Today's circle does not fill. Investigate goal configuration and rendering without inventing a daily requirement or changing consumption records.

### Follow-up: water inside Today's progress circle

The owner clarified the desired behavior: water should fill inside the circle.
The existing outline renders at 50% and 100% in a visual UI test; the missing
behavior is the interior fill. Add a translucent bottom-aligned fill behind the
number, clipped to the circular interior, using the same existing user-goal ratio.
Clamp the visible level to 0...1; no goal stays empty, and over-goal progress stays
full. Preserve the outline, goal values, total, accessibility and record storage.

- [x] Observe the interior visual assertion fail before changing product code.
- [x] Add the bounded interior fill and verify 50%/100% rendered pixels.
- [x] Run relevant XCTest/UI checks and build/sign: 129 XCTest, three UI tests, full pytest 1,336/5 skipped; signed device build verified.
- [x] Install the water-fill update in place when the paired phone reconnects; devicectl installation succeeded for the registered owner phone.

The visual test waits on rendered pixels so the water animation can finish. A
fresh disposable iPhone 17 Pro/iOS 27.2 simulator is used for final UI verification,
with a known synthetic 500 mL record; no owner data or goal is changed. Out-of-range
test setup fails explicitly instead of skipping the visual assertions.

The signed `14d083c` update installed in place over Wi-Fi. Automatic app opening
was denied only because the phone was locked; the owner can unlock and open Hydra
normally. Water rendering was verified in the simulator; the physical offline
camera/save/restart verification remains the owner's preceding check on `f7057a7`,
with camera and storage code unchanged by this dashboard-only follow-up.
