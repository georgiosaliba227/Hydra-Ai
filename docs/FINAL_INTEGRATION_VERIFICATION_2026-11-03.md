# Final local integration verification — November 3, 2026

Checked the latest merged application at `5ceb016` (PR #79), in the isolated
`codex/final-integration-checks` worktree. The original Desktop checkout was
clean but 80 commits behind this baseline and was preserved.

## Findings addressed

1. **Standalone camera details could permanently block logging.** The manual
   fallback invented an original model candidate for correction feedback. A
   local recognition receipt correctly rejected it, but the client had already
   persisted an immutable pending save. Feedback is now offered only for an
   authentic result candidate. The independent native regression failed at
   confirmation before the fix and saves 240 mL with no pending request after it.
2. **Delete-all could be followed by restored personal data.** Wonder now holds
   its shared lock from facts/replay lookup through persistence. Delete-all
   refuses with 409 while that operation can still save. A local camera result
   crossing a successful deletion is invalidated before receipt persistence.
   Five deterministic backend race regressions failed before these fixes and
   pass afterward; they use disposable databases and fake providers.
3. **Old camera results survived deletion in the client.** A successful delete
   now invalidates registered receipts and the controller generation before
   refresh. A previously displayed or delayed result cannot become a pending
   request using a deleted receipt. The new XCTest failed before the fix and
   passes afterward.
4. **Native accessibility issues.** The Connection heading uses primary text
   contrast. Empty History uses separately wrapping title and description
   instead of the system empty-state layout flagged as clipped. The existing
   audit passes without changing its thresholds or exemptions. Screenshots of
   the original failures and final empty History were visually inspected.
5. **UI test data dependency.** The trends-review test now logs its own synthetic
   drink rather than depending on data left by earlier tests, including delete-all.

## Verification evidence

All application data used for this check was disposable and synthetic. Test
processes received a clean environment without provider credentials. No private
ledger was read, copied or changed, no paid request was made, and nothing was
deployed. Financial-ledger tests use temporary synthetic ledgers only.

| Check | Result |
| --- | --- |
| Maintained Python suite, Python 3.14 | 1,327 passed, 5 skipped; 58 subtests passed |
| Offline forecasting training, existing Python 3.13 environment | 14 passed |
| Preserved starter suite | 3 passed |
| Full iOS unit suite | 104 passed, 0 failures |
| Unsigned iPhone Release build | Build succeeded for generic iOS device |
| Offline demo rehearsal | All 10 groups passed; zero network attempts and no financial-ledger use |
| Native accessibility and delete-all rerun | 2 passed |
| Standalone local-camera details regression | Passed after observed failing confirmation |
| Genuine correction memory and independent trends review | 2 passed |
| Fake hosted-provider consent and receipt confirmation | 1 passed; no real provider transport |

Native tests ran with Xcode 27.2 on dedicated iPhone 17 Pro / iOS 26.5
simulators. The broad run executed 33 cases: 19 passed, 12 opt-in cases skipped,
and two cases failed (the two accessibility assertions and missing trends test
data above). Both affected cases subsequently passed on the corrected tree.
The broad run also verified manual logging/relaunch persistence, mock camera
confirmation, goals, history edits/deletion, assistant answers/sources, guided
personal workout consent and draft handling, simulated workouts separated from
consumption, largest accessibility text navigation, saved trends and consent reset.
No second complete broad UI run is claimed.
Across these runs, 24 distinct native functional/audit cases have passing evidence.

Raw local evidence is in `/tmp/hydra-final-checks/`: `pytest-final.log`,
`offline-training.log`, `unit-final2.xcresult`, `device-release.log`,
`rehearsal-final.log`, `ui-normal.xcresult`, `ui-audit.xcresult`,
`ui-local-camera-green.xcresult`, `ui-reviewed.xcresult`, and `fake-consent.log`. An initial final
unit attempt hit a simulator launch/preflight error; after rebooting the dedicated
simulator, the full 104-test suite passed. The earlier failing test results are
retained beside the successful results.

Independent review reproduced the integration defects, checked the fixes and
found no remaining important issue in the touched paths. It independently ran
230 focused backend checks successfully.

## Limits

The Python skips cover the optional offline training module and four image/data
collection checks requiring Pillow/duckdb. The training module's 14 tests were
then run successfully in its existing numerical environment; those four optional
collection checks remain unverified. One existing Starlette/httpx deprecation
warning remains. No dependencies were added.

These checks establish local software integration, not physiological validity,
real model accuracy, provider billing/account readiness, physical camera/Photos
permissions, physical HealthKit behavior, or a spoken VoiceOver walkthrough.
Weather autofill, last-workout import and live Wonder workout hooks remain
explicitly disabled by the existing flow configuration; this check does not
enable or claim those integrations. The deletion lock/generation guarantee is
for the existing single-process local prototype, not a multi-worker deployment.
Physical-device smoke testing and public-release review remain separate.
