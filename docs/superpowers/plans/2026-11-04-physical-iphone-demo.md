# Physical iPhone Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans task by task. Track verification and commits in the plan ledger.

**Goal:** Deliver a real physical-iPhone demo video using an isolated simulated account, with verified local model and GitHub source pushed before recording.

**Architecture:** A separate signed bundle `com.georgiosaliba.hydraai.demo` runs the same app and local recognizer. A guarded resumable seeder populates its own sandbox; a stateless demo backend uses a fresh private runtime token. The owner records the physical camera/UI with native screen recording and no Mac sharing; source is frozen/pushed first.

**Tech Stack:** Existing SwiftUI/Core ML, Python/FastAPI, Xcode, native iPhone recorder and installed FFmpeg. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-04-physical-iphone-demo-design.md`, approved by the owner for approximately three minutes.

## Global Constraints

- Entire final footage originates on the physical iPhone. No simulator or generated app-screen substitution.
- Preserve production app, records, credentials, private ledgers and full-backend history.
- Visible `DEMO · simulated data`; exact demo bundle ID guards seeding/reset.
- No paid/provider requests or real HealthKit reads in the demo. Runtime development token stays outside source and logs.
- Verify source/model on GitHub before the owner starts final recording; do not claim `main` is updated or submit terms.

## Review Focus

- Crash/clock rollback during first seed: resume stable records; no duplicate/future entries.
- Relaunch after editing/deleting: never silently reseed or replace the demo user's changes.
- Production bundle or corrupt marker: fail before mutation; never reset owner's account.
- Offline camera: bundled inference/confirmation persists; failed backend cannot block it.
- Recording: no real data, credentials, misleading AI/scientific claims, or remote sharing during camera operation.

### Task 1: Guarded demo identity, plan and seeder

Files: create `ios/HydraAI/Data/DemoAccount.swift` and `ios/HydraAITests/DemoAccountTests.swift`.

Interfaces: `DemoAccount.bundleIdentifier`, `DemoAccount.isActive`, `DemoAccount.permits(bundleIdentifier:)`; `DemoSeedPlan.make(now:zone:)` with entries containing stable UUID/request pairs, daily goal3000, fictional GoalProfile, fourteen days and today's total2250. `@MainActor DemoAccountSeeder.init(service:LocalBeverageService, profiles:GoalProfileStore, markerURL:URL)`; `prepare(bundleIdentifier:now:zone:) async throws -> DemoSeedPlan`; `reset(bundleIdentifier:now:zone:) async throws -> DemoSeedPlan`.

- [ ] Test RED: production guard performs no writes; plan14days/today2250/no future dates; stable IDs; prepare/relaunch preserve changes; interrupted initialization resumes; reset only own supplied local services; corrupt/symlink marker fails closed.
- [ ] Implement versioned protected marker with initializing/ready/resetting state. Persist anchor before per-record operations; existing idempotent local mutations resume safely. Save profile/goal only during initialization. A ready marker never reseeds on relaunch.
- [ ] Run focused XCTest GREEN, review and commit.

### Task 2: Reproducible build and model verification

Files: create `scripts/verify_bundled_model.py`, `scripts/build_iphone_demo.py`, `tests/test_demo_bundle_tools.py`.

Interfaces: verifier checks source hashes/bytes, actual Git blobs, compiled app weights/metadata/licenses and optionally signature; emits credential-free JSON. Builder creates the exact demo bundle/display name with HealthKit entitlement omitted for demo, using current project and caller's DerivedData/team; no installation, credentials or environment dumps.

- [ ] Test RED with tiny temporary fixtures: mismatched/missing weight, wrong bundle ID, bad metadata and LFS pointer rejected; correct evidence accepted. Build command includes exact `.demo` ID and `Hydra Demo` display name.
- [ ] Implement, run focused Python GREEN, review and commit. Root verifies actual model/app separately.

### Task 3: App composition and visible isolation (root)

Files: modify `HydraAIApp.swift`, `RootView.swift`, `BeverageStore.swift`, `BackendSettingsView.swift`, `HealthActivityPermissionView.swift`; create `Features/Demo/DemoAccountView.swift`, `HydraAIUITests/DemoAccountUITests.swift`.

- [ ] Observe UI RED: isolated demo build lacks seeded totals/badge.
- [ ] Demo-only startup forces on-device logging, waits for seeding before rendering RootView, persists an explicitly provisioned optional demo connection, and preserves it on ordinary relaunch.
- [ ] Add persistent simulated-account banner, demo-only explicit reset, model-local status and no HealthKit request/read path. Normal bundle remains unchanged. Do not expose a production flag that redirects owner records.
- [ ] UI GREEN: demo2250→manual2500→restart2500→explicit reset2250; protected normal account remains separate; real model Analyze/Confirm and aggregate backend flows work. Run full native/Python checks and review.

### Task 4: Submission and recording handoff

Files: update `README.md`, `docs/SUBMISSION_DRAFT.md`; create `docs/PHYSICAL_DEMO_RUNBOOK.md`, `docs/DEMO_SOURCE_VERIFICATION.md`.

- [ ] Rewrite stale claims using actual local DINOv2/Apple OCR and current tested features; label other models/results historical or experimental. Include model license/provenance and remaining portal/eligibility checks without inventing confirmation.
- [ ] Write three-minute physical tap order, sample-data disclosure, rehearsal/reset, native recorder and private transfer instructions; no owner secrets or data.
- [ ] Build/sign/verify/install Hydra Demo alongside Hydra; provision fresh stateless demo backend/runtime token without printing or committing it; rehearse on device.
- [ ] Push all source/setup/docs and verify remote commit/model blob; record its timestamp before filming.
- [ ] Owner records entire physical walkthrough with screen sharing off. Receive original file, inspect, trim/caption/export playable MP4, verify content/duration/privacy, and deliver artifact. Keep goal active until actual video exists and is reviewed.
