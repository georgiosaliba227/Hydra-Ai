# iPhone launch compatibility investigation

## Reproduction and cause

The signed app installed successfully on the iPhone 17 Pro running iOS 27.2 beta (24B5089g), but exited about one second after launch. A successful `devicectl` launch request did not prove the app remained open.

Three builds (Debug, fresh Debug, and Release) produced the same failure. Each crash reported `CODESIGNING / Invalid Page`, a null program counter, and a return address in `IntakeHistoryForecast.validate` at the history-window date comparison. Symbolication and Release disassembly identified the preceding instruction as a call to Foundation's weak-imported `Date.>=` symbol. The Xcode 27.2 SDK back-deploys that new symbol only before iOS 27.2; the early 27.2 beta takes the new-symbol path and attempts to call null. Mac signature verification passed for all three builds.

## Change

Compare `Date.timeIntervalSinceReferenceDate` values directly wherever the client used `Date.>=` or `Date.<=`. This matches the SDK's fallback implementation and preserves inclusive/exclusive bounds, timezone-aware calendar calculation, and rejection of invalid/nonfinite consumption dates. The history, beverage creation/correction, longitudinal metadata, and workout-form paths share the compatibility fix. No saved configuration or drink records were changed.

## Checks

- Signed iOS 26.5 simulator unit suite: **88 passed**, including new history-window boundaries across the November daylight-saving change and creation/correction date bounds (including NaN rejection).
- Simulator UI regression: **1 passed** (`testOfflineDrinkLoggingFillsGoalAndSurvivesRelaunch`), covering confirmed logging, changing liquid fill, completion, and relaunch persistence with synthetic local records.
- Signed Release device build: passed; `codesign --verify --deep --strict` passed. Its UUID is `104EA35D-81CF-38A6-9DC0-FCC617226633`; neither new Date comparison symbol remains in the executable's imports.
- In-place install on the paired iPhone: passed. Existing application data was retained; no uninstall or reset.
- Initial unsigned iOS 27.0 simulator invocation: 84 passed, 4 failed (three Keychain credential errors without code signing, and a temporary-file cleanup error in `CameraSessionTests.testChangedStoreGenerationRejectsOldReceiptBeforeCreatingPendingLog`). The signed supported simulator invocation above passed the full suite.
- Full pytest with the existing project virtual environment: **1,072 passed, 1 skipped, 1 failed**. The unchanged failure is `tests/recognition/test_wonder_workout.py::test_invalid_requests_are_rejected[<lambda>11]`; its fixed October 30 sample is no longer future-dated, so the response is 409 instead of 422. No Python files changed.
- Independent read-only code review: no actionable findings; scalar comparisons match the SDK fallback and no direct Date `>=`/`<=` calls remain in app sources.

## Physical verification status

The repaired build is installed. Normal launch and sustained-process/relaunch checks are pending an unlocked iPhone: iOS currently rejects the launch request with `Locked`. A targeted physical XCTest invocation was also blocked before execution by the lock and was cancelled. Do not report the physical launch as verified until the phone is unlocked and both checks complete.

Crash reports and console output remain outside the repository. No raw personal records, credentials, live inference, or budget-ledger changes were involved.
