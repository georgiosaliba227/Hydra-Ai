# Physical demo source verification — November 4, 2026

## Application source

App code commit: [3b9663bcb24fbeeec23503905b2bfc719e735745](https://github.com/georgiosaliba227/Hydra-Ai/commit/3b9663bcb24fbeeec23503905b2bfc719e735745).
Submission branch: [codex/physical-demo-submission](https://github.com/georgiosaliba227/Hydra-Ai/tree/codex/physical-demo-submission).
Documentation commits may follow without changing the app. The final branch HEAD must be remotely verified before filming; main is not the feature source.

## Verified locally

- Signed device build succeeded for separate bundle com.georgiosaliba.hydraai.demo, display name Hydra Demo, Apple development team DH2JX3X8S9. Strict signature verification passed. Its signed entitlements contain no HealthKit or shared Keychain access group.
- [Machine-readable model evidence](evidence/physical-demo-model-20261104.json) verifies the committed real binary blobs, compiled model, notices and report. Source model package: 43,426,113 bytes. Compiled weights: 43,281,240 bytes; SHA-256 372571e222751cdc766bf7de3aa36f0beee01fbb0d1c64db4079e8ab261ce20f. The model is packaged in the app; no runtime model downloader is used.
- Full Python suite before the Swift-only container fix: **1480 passed, 5 optional skips, 58 subtests passed**, one existing FastAPI/Starlette deprecation warning, 25.94 seconds.
- Full native XCTest suite: **217 passed**, zero failures, on an ad hoc signed iOS 27.2 simulator.
- New demo UI regression: **1 passed**, 37.637 seconds. It verifies visible simulated-data disclosure, 2250 mL seed, quick-add to 2500, persistence through relaunch, explicit reset to 2250, and unchanged separate normal-app total. Initial missing-demo UI and ambiguous reset-selector failures were observed before the final passing run.
- Separate read-only core and final integration reviews returned no actionable material findings. Reviewers did not claim to run tests.
- A fresh development token starts an independent private-LAN stateless features runtime on port 8773. Authenticated health reports features_only, provider_dispatch=false, storage=none, billable_requests_enabled=false. It uses immutable backend source 8dd0c3b128afe4c1aeab24d5a18b5cf072aa61f4, which is included in this branch history. No production credentials, database or financial ledger are copied.

## Remaining physical and remote evidence

The corrected signed separate demo app was successfully installed wirelessly on the physical iPhone 17 Pro (iOS 27.2), alongside the unchanged normal bundle. Its app code commit 3b9663bcb24fbeeec23503905b2bfc719e735745 was verified on GitHub with git ls-remote at 2026-11-05T00:59:44Z; its reachable model weight blob is 0a5aef886a0a1489d24ae801e0316e717f9104ba (43,281,240 bytes). The final documentation follow-up is pushed and its HEAD checked again before the owner’s take.

The initial physical startup exposed an ancestor-metadata check outside the iOS container. Fixes 5d0d721 and 3b9663b bound marker/profile checks to trusted app home while preserving descendant symlink/corruption protections. Their focused RED→GREEN suites passed 11 and 18 tests. The combined native suite passed 217, and the repeated demo UI regression passed. Separate read-only reviews of both fixes found no material issues. The corrected remote launch was blocked by phone lock; the owner is asked to unlock and open Hydra Demo directly. Phone UI/backend rehearsal and the actual recorded video remain pending. Simulator tests are not final demo footage. Previous owner-confirmed offline analysis/persistence applies to the normal app, not this new demo installation.

The owner records the physical iPhone with Mac sharing off. All account history/profile values in Hydra Demo are fictional; no real Health data is requested. Follow the [three-minute runbook](PHYSICAL_DEMO_RUNBOOK.md). Preserve the original recording before export; record actual duration and privacy review only after inspecting the received file.

The owner's submission target is **8:30 PM ET**. This evidence does not claim portal submission, terms acceptance, a PR, a main merge, public deployment or scientific validation.

Storage-boundary rationale: Apple documents [iOS file access within the app sandbox](https://developer.apple.com/library/archive/documentation/FileManagement/Conceptual/FileSystemProgrammingGuide/FileSystemOverview/FileSystemOverview.html). The new tests simulate denied ancestor metadata and reject escapes before any probe.
