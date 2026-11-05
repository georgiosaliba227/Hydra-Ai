# Physical demo source verification — November 4, 2026

## Source freeze

Pre-upload recheck on **November 4, 2026, 8:49 PM ET**: fetched GitHub refs
match `main` at `3ac7207` and the physical demo branch at `e6c6ce9`.
The additive `codex/preupload-review-20261104` branch refreshes shared status,
blockers and next actions while preserving the installed app source below.
Fresh full Python verification: **1480 passed, 5 skipped, 58 subtests** in
25.26 seconds. Fresh full native unit suite: **217 passed**, zero failures.
Preserved starter tests: **3 passed**. Offline rehearsal: **10 groups passed,
zero network attempts**. Strict signed bundle/model/blob verification passed
again. Raw local evidence is `/tmp/hydra-preupload-pytest-20261104.log`,
`/tmp/hydra-preupload-native-20261104.xcresult`, and
`/tmp/hydra-preupload-model-20261104.json`.

The pre-upload documentation update was pushed as `94bbc97` and matched the
remote branch on a fresh `git ls-remote` check. PR publication was attempted
again: the connected GitHub integration returned HTTP 403, and the existing
CLI identity returned `must be a collaborator`. At that checkpoint no PR or
reviewer notification was created, and no merge occurred. The prepared description is retained at
`/tmp/hydra-preupload-pr-20261104.md`.
The owner then explicitly requested integration into `main`. Existing Git
push credentials authenticated as the repository owner without changing any
credentials, and [PR #82](https://github.com/georgiosaliba227/Hydra-Ai/pull/82)
was created successfully. Fresh pre-merge verification passed again:
**1480 pytest, 5 optional skips, 58 subtests; 217 XCTest, zero failures**.
Evidence: `/tmp/hydra-premerge-pytest-20261104.log` and
`/tmp/hydra-premerge-native-20261104.xcresult`. The follow-up edits only
documentation. The PR records the actual merge status and commit.

Installed app code: [cf0088e4c5fca07d525c7a09a88b5ab179089322](https://github.com/georgiosaliba227/Hydra-Ai/commit/cf0088e4c5fca07d525c7a09a88b5ab179089322).
Submission branch: [codex/physical-demo-submission](https://github.com/georgiosaliba227/Hydra-Ai/tree/codex/physical-demo-submission).
The app commit was verified with git ls-remote at **2026-11-05T01:21:16.456Z**, before filming. Its reachable model weight blob is 0a5aef886a0a1489d24ae801e0316e717f9104ba (43,281,240 bytes). This final evidence-only follow-up is pushed and its new HEAD checked before the take. The earlier main revision lacked this feature source; PR #82 integrates it.

## Local model and signed app

The separate Apple-development-signed bundle is **com.georgiosaliba.hydraai.demo**, display name **Hydra Demo**, team DH2JX3X8S9. Strict signature verification passed. Its entitlements contain no HealthKit or shared Keychain access group.

[Machine-readable evidence](evidence/physical-demo-model-20261104.json) verifies actual committed binary blobs, compiled model, report and bundled notices. Source model package: **43,426,113 bytes**. Compiled weights: **43,281,240 bytes**, SHA-256 **372571e222751cdc766bf7de3aa36f0beee01fbb0d1c64db4079e8ab261ce20f**. The Meta DINOv2 category model is packaged in the app; Apple Vision OCR is separate. No runtime model download is used.

## Verification actually run

- Full Python suite before the Swift-only physical fixes: **1480 passed, 5 optional skips, 58 subtests passed**; one existing FastAPI/Starlette deprecation warning, 25.94 seconds. Python source has not changed since that run.
- Latest full ad hoc signed iOS 27.2 simulator XCTest suite: **217 passed**, zero failures, 3.797 seconds of test execution.
- Prior demo isolation UI regression at d09d093: **1 passed**, 37.858 seconds. Visible demo disclosure, 2250 mL seed, quick-add to 2500, relaunch persistence, explicit reset to 2250 and unchanged separate normal-app total all passed.
- Storage-boundary focused RED→GREEN suites: **11 demo tests and 18 profile tests**. They simulate denied metadata outside trusted app home and reject root/sibling/escape paths before probes, while retaining descendant symlink, corruption, consent and deletion protections.
- A real phone crash was symbolicated to DemoAccount.swift:55 and the weak Foundation Date.<= stub. Both inclusive comparisons now use the existing finite-timestamp DateBoundary helper. Inspection of the latest signed ARM64 executable completed successfully and found **zero weak Foundation Date operator imports**.
- Separate read-only core, integration, storage-fix and date-fix reviews reported no actionable material findings. Reviewers did not claim to run tests.

Apple documents [iOS file access within the app sandbox](https://developer.apple.com/library/archive/documentation/FileManagement/Conceptual/FileSystemProgrammingGuide/FileSystemOverview/FileSystemOverview.html). Initial physical failures are retained as evidence rather than represented as passing checks.

## Physical phone and optional backend

The corrected app installed and launched on the physical iPhone 17 Pro (iOS 27.2), alongside the unchanged normal Hydra bundle. The owner confirmed that Today opens with **DEMO · simulated data** and **2250/3000 mL**. The owner then reported remaining mL-only camera fields. The latest update applies the saved unit preference to camera amounts/presets and canonical goal entry, and selects US once for this demo. Its new simulator UI regression passed in **47.803 seconds**, verifying 16.9 fl oz display, exact 500 mL confirmation, preset unit retention, and goal persistence through relaunch. An observed RED run showed 500 mL instead of 16.9 fl oz before the fix. The phone unit update and backend rehearsal await owner confirmation; the actual video remains pending. Simulator tests are not final demo footage.

A fresh private development token configures an independent stateless private-LAN features runtime on port 8773, from immutable backend source **8dd0c3b128afe4c1aeab24d5a18b5cf072aa61f4** included in branch history. Authenticated health reports features_only, provider_dispatch=false, storage=none and billable_requests_enabled=false. No production credential, database or financial ledger is copied. No provider request is made.

## Recording handoff

Follow the [three-minute physical runbook](PHYSICAL_DEMO_RUNBOOK.md). The owner uses the iPhone recorder with Mac sharing off; all profile/history values in Hydra Demo are fictional and no real Health data is requested. Preserve the actual original before trimming/export. Duration, contents and privacy review can only be recorded after receiving and inspecting the file.

The owner’s target is **8:30 PM ET**. This evidence does not claim a completed video, portal submission, terms acceptance, PR, main merge, public deployment or scientific validation.

The owner then identified a separate hard-coded dashboard goal label. The final unit pass converts the circle, goal progress, quick-add, drink rows, history/manual/edit forms, Trends, Ask and workout result summaries through the shared formatter. Latest US UI regression includes Today accessibility units and goal-progress text, in addition to exact 500 mL confirmation and goal persistence; it passed in 47.803 seconds after a RED “Logged today, 0 milliliters” failure. Full native suite passed 217 again. Read-only review found no material issues. Printed photo label text retains its original evidence units. Final physical display confirmation and the actual recording remain pending.
