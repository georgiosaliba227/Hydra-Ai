# End-to-end integration review

## Authorization and source preservation

The user's full development authorization supersedes the previous planning-only and component-ownership restrictions. This milestone implements the local manual-log → API → SQLite → hydration-accounting → native-dashboard flow. It does not authorize paid inference, public deployment, automatic PR merges or overwriting concurrent work.

The integration branch starts from approved main and incorporates PR #2 (`39f142a`, iOS foundation) and PR #4 (`68794ab`, hydration engine) locally. Their original branches and worktrees remain untouched. Local integration is not a GitHub merge or evidence of human approval.

## PR #4 readiness

Review of the current PR found no recorded human reviews or CI checks. Its calculation module is suitable for backend adapter evaluation, but required human review and merge authorization are not established. Keep PR #4 open for review; do not merge automatically.

The orchestrator verified 46 engine tests with 32 pytest subtests. The engine remains unchanged by this integration: confirmed beverage volume is counted without category multipliers; water composition stays unknown when unsourced; daily aggregation uses the requested local calendar date; personalized requirement forecasts remain `insufficient_data`. Workout mass-balance calculations are estimates, not drinking prescriptions. Tests establish arithmetic and software behavior, not clinical validity, measurement quality or nutrition-source correctness.

## Implemented integration boundaries

`backend.app.create_app(db_path=None, api_token=None)` provides a testable application factory; `backend.main:app` is the runtime entrypoint. Authenticated `/v1/beverages` supports confirmed manual creation and paginated history; `/v1/summary` returns complete engine-derived daily accounting. `/health` reports mock mode and disabled billable requests. Input validation, idempotency, error envelopes, timestamp normalization and the single-user development authentication boundary are documented in [PROTOTYPE_API.md](architecture/PROTOTYPE_API.md).

`database.repository.BeverageRepository` stores the stable response and canonical-request fingerprint under an atomic owner/idempotency-key constraint. Identical retries return the original response; conflicting payloads fail. Separate SQLite connections and transactions preserve records across process restarts. `list_all(owner)` supplies a complete owned snapshot; pagination is never used as the input to daily totals. Backend maps persisted records into the unchanged `ai.hydration` interfaces.

No provider client is implemented. Startup rejects enabled billable requests or non-mock AI mode. The shared $150 ceiling, $120 operational cutoff and $30 reserve remain policy; the paid-inference budget controller is not implemented or validated by these beverage tests.

## Verification status

| Check | Result |
|---|---|
| Combined backend, database and engine suite | 108 tests passed: 49 API + 13 database + 46 engine; engine includes 32 subtests |
| Engine arithmetic, DST and numerical regressions | Passed; not clinical validation |
| API/database behavior | Authentication, validation, duplicate replay/conflict, concurrency, persistence, timezone/DST, pagination and mock-only guard tests passed |
| iOS build and XCTest | Ad-hoc signed simulator build passed; 11 XCTest cases passed on iPhone 17 Pro / iOS 26.5 |
| Native app → live backend → persistence | iPhone 18 Pro / iOS 27 simulator manually saved 250 mL; HTTP and SQLite confirmed one record; backend process restart and app refresh retained it |
| Runtime outage handling | Backend stopped: visible connection error; restart + refresh recovered original total |
| Native UI test + relaunch without injected configuration | Passed on iPhone 18 Pro / iOS 27: Settings saved to Keychain, +125 mL logged, total 375 mL; terminated/relaunched with no overrides, same total and no pending duplicate |
| Physical iPhone camera/HealthKit/device networking | Not verified by this review |

## Remaining gates

- Human reviews of dependency PRs and the integration PR; no automatic merges.
- Physical iPhone signing, installation, networking and permission checks; simulator results must be reported separately.
- Production authentication, multi-user identity, TLS/hosting, data retention/deletion, backup and operational monitoring before any public deployment. The local development token is not a production account system.
- Scientific approval of personalized daily requirements and source/measurement standards before introducing targets, water-content estimates or workout guidance beyond the existing engine's limits.
- Explicit separate approval and a tested centralized, persistent, fail-closed spending controller before any paid Meta request. No top-ups or subscriptions are authorized.
- Hackathon participant-specific eligibility, representative status, submission details and credit expiry/coverage remain human verification tasks in [HACKATHON_COMPLIANCE.md](HACKATHON_COMPLIANCE.md).

## Issues found and resolved during integration

- The existing Debug configuration did not define DEBUG; fixed it so simulator-only environment overrides work. Release remains without that flag.
- Unsigned simulator builds could not write Keychain. Use ad-hoc simulator signing; no plaintext credential fallback was added. A focused Keychain test and full signed suite pass.
- A root-directory test invocation of the preserved starter can hit its legacy package import collision; its tests are deliberately run separately from Hydra-Ai-Starter.
- Starlette emits a TestClient/httpx deprecation warning; tests pass. Review a compatible test-client upgrade separately.

Runtime database verification after UI test: exactly two records (250 mL manually logged and 125 mL from the UI test), 375 mL total. The opt-in UI test passed with zero failures; no physical iPhone run is claimed. Backend was stopped and restarted once using the same SQLite file; the existing record survived. All runtime data is synthetic and outside the repository.

## Independent PR #5 review — 2026-10-26

Reviewed dependency heads #2 `39f142a9494d2f743ca2e46529d04d20d98d2041`, #4 `68794ab788e87fb081db181a0bb37227c52cbbd2`, and integration head `f0b32950a45f0efcd9765c2a18afc0ae7f2a44ac` plus the corrective commit containing this report. Worktree was clean before review; no existing edits were replaced.

### Findings and fixes

- **P1 fixed — public HTTP credential exposure:** `APIConfiguration.validatedURL` discarded nonnumeric hostname labels before deciding whether an address was private. A public DNS name such as `127.attacker.0.0.1` passed the local HTTP check. Require exactly four numeric labels for IPv4, retaining loopback/private-range checks. Regression tests reject mixed public hostnames and accept intended LAN/loopback hosts. Tokens now reject non-ASCII, whitespace and control characters before entering HTTP headers.
- **Device installation blocker:** an actual signed generic iOS build fails because HydraAI has no development team. An unsigned arm64 iPhoneOS 27 build succeeds, establishing compilation only. No signed physical-device installation or runtime test is claimed.
- **Deployment limitation:** the bearer token maps to one fixed `local-demo` owner. Constant-time credential comparison and repository owner scoping work; this does not provide separate user accounts. Local HTTP exposes credentials/data to the trusted LAN; use synthetic data and HTTPS outside this controlled development setup. Production identity, TLS, retention/deletion and operational controls remain required before public deployment.
- **Operational limitations:** history/summary load the complete owned SQLite snapshot in memory, appropriate only for MVP scale. Pending mutations deliberately block new logs after unresolved errors; permanent validation/conflict or corrupt-file recovery needs operator assistance. No automatic fresh-key retry or silent offline fallback is added. No GitHub CI checks were reported on #5; local evidence below is not a CI result.

### Dependencies, duplicates and conflict analysis

Both dependency heads are actual ancestors of #5, not separately reimplemented copies. `git diff` against #4 for `ai/hydration/` and `tests/hydration/` is empty. `backend/app.py` imports `BeverageLog`, `calculate_contribution`, and `summarize_day` from `ai.hydration`; creation calls the contribution function, and summary calls the engine over the complete stored snapshot. The explicitly selected offline service sums beverage volume locally for its separate demo; it is not the backend calculation path. The preserved starter has no changes and is not the new runtime.

#2 introduces iOS files; #4 introduces only engine/tests. Their paths are disjoint and `git merge-tree --write-tree` combines their current heads without conflict. #5 intentionally changes the following #2 paths or adds integration files in the same tree; these are integrated replacements/additions, not parallel applications:

- `ios/Configuration/Info.plist`
- `ios/HydraAI.xcodeproj/project.pbxproj`
- `ios/HydraAI.xcodeproj/xcshareddata/xcschemes/HydraAI.xcscheme`
- `ios/HydraAI.xcodeproj/xcshareddata/xcschemes/HydraAIEndToEnd.xcscheme`
- `ios/HydraAI/Components/LoggedVolumeCard.swift`
- `ios/HydraAI/Data/APIConfiguration.swift`
- `ios/HydraAI/Data/BeverageService.swift`
- `ios/HydraAI/Data/BeverageStore.swift`
- `ios/HydraAI/Data/HTTPBeverageService.swift`
- `ios/HydraAI/Domain/BeverageLog.swift`
- `ios/HydraAI/Features/Dashboard/DashboardView.swift`
- `ios/HydraAI/Features/History/HistoryView.swift`
- `ios/HydraAI/Features/Logging/ManualLogView.swift`
- `ios/HydraAI/Features/Settings/BackendSettingsView.swift`
- `ios/HydraAI/Health/HealthActivityPermissionView.swift`
- `ios/HydraAI/HydraAIApp.swift`
- `ios/HydraAI/RootView.swift`
- `ios/HydraAITests/HTTPIntegrationTests.swift`
- `ios/HydraAIUITests/BackendEndToEndTests.swift`
- `ios/README.md`

Runtime dependencies are declared in `backend/requirements.txt`; setup separately installs pytest/httpx for tests. Existing environment passed `pip check`; no missing runtime dependency was observed. iOS uses Apple frameworks and no external package. A fresh global Python lacked pytest; verification used the existing workspace `.venv`, as documented here rather than claiming a clean-environment install.

Safest order after human review: **#4 → #2 → #5**. #2 and #4 can technically swap because they are independent. Prefer ancestry-preserving merges for dependency PRs so #5's diff narrows naturally. If maintainers squash/rebase dependency PRs, reconcile #5 against the resulting main, inspect its entire diff and rerun checks before merging. Do not copy files from #2 over #5: that would lose network/retry integration. Recheck current remote heads before any future merge. No PR was merged during this review.

### Verification rerun

- Python 3.14 workspace venv: `python -m pytest tests -q`: **108 passed, 32 subtests passed**. Includes API authentication/strict validation/body limits/safe errors, engine/DST arithmetic, repository concurrency, duplicate/conflicting key replay, ambiguous committed-response recovery and backend restart persistence. `pip check`: no broken requirements. Starlette/httpx deprecation warning remains.
- Preserved starter, run from its own directory: **3 passed**.
- Xcode **27.0 (27A266a)**, iPhone 18 Pro simulator / iOS **27.0**: ad-hoc signed `HydraAI` build/test **13 passed**, including two new configuration regressions. Simulator result bundle remains local at `/tmp/hydra-pr5-review/Logs/Test/`.
- Generic physical iOS destination: normal signed build **failed: development team required**; `CODE_SIGNING_ALLOWED=NO` build **succeeded**. An unsigned build cannot establish device install readiness or Keychain/HealthKit behavior.
- Native `HydraAIEndToEnd` UI scheme: **1 passed** against a separate loopback backend with a fresh random runtime token and empty synthetic SQLite database. Logged 125 mL, relaunched without injected configuration, recovered the same 125 mL total; direct SQLite inspection found exactly **one** row. The temporary backend was stopped after testing. Backend-restart/ambiguous-response recovery is separately covered by Python integration tests; this UI run exercises app restart.
- All PR commit patches were scanned for common provider/GitHub/AWS/private-key patterns: no matches. Changed paths contain no committed `.env`, databases, certificates, photo artifacts or result bundles. Manual inspection of test fixtures/network paths found synthetic beverages and no real health records, committed runtime credentials or Meta keys. This bounded scan is not a guarantee against every possible secret format.
- No outbound provider client was added or invoked. Mock-only and billable-disabled startup guards remain in place; no paid authentication probes or Meta requests were made.

### Physical iPhone and Meta gates

The code is ready for a controlled synthetic-data device smoke test **after signing/provisioning and local connectivity are configured**; it is not currently a verified installable device build. Select the developers' team, confirm bundle ID/profiles and HealthKit entitlement, enable device Developer Mode/trust, and install a signed build. Use a reachable backend address (phone loopback is not the Mac), explicitly configure private LAN binding/firewall or HTTPS and test local-network allow/deny. Exercise Keychain persistence, foreground/background and app/backend restart, offline pending replay with exactly one stored entry, camera/photo allow/deny/cancel, and optional step-read HealthKit allow/deny/no-data. Verify photos and HealthKit stay on device. Test on the intended minimum iOS version as well as the available latest simulator; iOS 17 runtime behavior was not exercised here.

Before Meta integration, obtain human integration/contract review; settle photo consent and retention/deletion policy and Apple health-data restrictions; keep raw HealthKit on device. Verify exact Meta model IDs, image support, prices, credits/expiry, billing/limits, concurrency and human spend authorization. Implement and test one centralized persistent fail-closed budget ledger with atomic settled costs plus outstanding reservations, bounded request charges and race/retry/crash reconciliation. Shared limits remain notify at $75, require further approval at $100, stop new billable requests at $120, preserve $30 reserve under $150 absolute total. Add mock-first schema/provenance/uncertainty and invalid-output evaluation before connecting inference. Core calls must use verified Meta models; no alternate provider or arbitrary hydration multiplier. Keep billable requests disabled until all these gates are met.
