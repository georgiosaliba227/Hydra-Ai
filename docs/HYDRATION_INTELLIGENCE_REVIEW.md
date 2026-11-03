# Hydration intelligence review handoff

November 3, 2026. Branch `codex/hydration-intelligence-complete` extends Amine's
PR #65 at `c8e4a77`. Review the changes against `codex/workout-flow-integration`;
main does not yet contain that dependency. Camera PRs #66–#70 are separate.
No automatic merge, deployment, provider request or private financial operation
is part of this work.

Published as [PR #71](https://github.com/georgiosaliba227/Hydra-Ai/pull/71), with
Amine requested as reviewer. It is intentionally stacked on PR #65 rather than
reapplying that contribution in a main-based diff. Retarget after the dependency
is integrated by the developers. The review worktree is preserved.

## Behavior delivered for review

Manual calibration history can be explicitly saved, revisited, exported and
deleted on the phone. Protected atomic files are scoped to the backend connection
through device-only Keychain identities, excluded from backup and capped at the
existing 32-record request limit. Backend-processing and Meta consent are fresh
actions; neither is stored with history. Corrupt or unavailable history cannot be
silently overwritten. Delete-all clears local histories even when the backend
cannot be reached and reports partial server deletion honestly.

The local analysis combines numerical exercise-loss proxies with logged intake,
known composition, activity/environment context, uncertainty and eight evidence
sections. A future workout is never subtracted as an incurred loss. Narrow
intake-minus-measured-exercise-loss accounting requires actual completed,
time-aligned measurements and matching consumed volume; it is not full fluid
balance, total body hydration or a drinking prescription.

Comprehensive Muse Wonder integration lets the model rank applicable findings in
eight sections. The server and phone reconstruct vetted prose from validated
facts; arbitrary model numbers or unsupported free text cannot replace the
calculation. Preview shows the exact minimized aggregates and reference cost,
then requires separate consent to that exact payload. Reference prices are not
verified live quotes. Saved exact-hash replay avoids another dispatch. Unknown
attempt outcomes remain quarantined without an automatic retry. The separate
comprehensive feature flag is false by default, with all prior financial gates
still required.

## Numerical evidence

The three study targets remain separate. No participant records or raw workbooks
are committed; no study artifact is automatically a personal physiological prior.

| Experiment | Records / groups | Development decision | Held-out MAE, mL |
| --- | --- | --- | ---: |
| SpectroPhon intake-corrected mass-loss proxy | 200 / 198 conservative identity groups | Ridge alpha 1 | 71.41 versus refitted cohort 85.72 |
| QDE cumulative uncorrected mass-loss proxy | 80 / 10 people | Boosting selected by fixed grouped rule; not promoted to app | 315.09 versus cohort 281.28 |
| EPL intake-corrected mass-loss proxy | 31 / 31 people, two disjoint sessions | Retain learned cohort rate; forest gain too small | 355.70 |

SpectroPhon and QDE holdouts were already published in earlier work and are
explicitly historical reused audits, not independent confirmation. EPL has only
six test and six calibration participants, so its empirical envelope has no
finite nominal 90% conformal guarantee. Shared session weather, duration and
cohort are confounded. Neither these results nor software sensitivity tests
establish general physiology, drinking requirements or longitudinal accuracy.

Reports and reproducible artifacts:

- [Grouped evaluation](FORECAST_GROUPED_EVALUATION.md), including leakage controls,
  model-selection heuristic, missingness, domain and sensitivity checks.
- [EPL evaluation](FORECAST_EPL_EVALUATION.md), including CC BY 4.0 attribution,
  pinned source digest, independently reproduced artifacts and shifted-session
  diagnostic. The source has no repeated individuals or individual error bounds.
- [Data inventory](FORECAST_DATA_INVENTORY.md), with additional public sources
  admitted or excluded based on their actual files, protocol and reuse terms.
- [Offline temporal learner](FORECAST_PERSONAL_LEARNING_RESEARCH.md). Its gradual
  synthetic improvement, abrupt-change regression and poor drift inclusion are
  reported together. This calendar-time model remains offline.

The additive stationary runtime model and its verification are governed by the
[personal runtime contract](architecture/PERSONAL_RUNTIME_API.md). Runtime fitting
is a different hypothesis from the offline temporal learner. Its own chronological
selection and baseline fallback do not establish independent personal accuracy.
Real, dated, protocol-confirmed repeated workouts remain needed for prospective
evaluation. Synthetic scenarios are software tests only.
The stationary fitted candidate's frozen synthetic abrupt-shift MAE is 70.49 mL
versus the baseline's 57.73 mL; all ten invented trajectories deteriorate in that
scenario. Its small stationary gains do not override this failure. The app keeps
the existing baseline by default and exposes v3 through an explicit experimental
choice. See [runtime evaluation](FORECAST_PERSONAL_RUNTIME.md) for every scenario,
including failed gradual-drift inclusion and baseline retention.

## Verification record

The following are completed milestone evidence, before the additive runtime
integration. They must not be represented as tests of subsequent code changes.

- Full Python integration suite: 1,237 passed and 32 subtests; then 63 focused
  Wonder analysis tests passed after the fractional-duration correction. One
  existing Starlette/httpx deprecation warning remains.
- Native rich-analysis milestone: 132 XCTest passed on iPhone 17 Pro / iOS 26.5
  simulator. Actual local mock-backend WorkoutFlow UI passed after the renderer
  fix, including sample Health import, context-only heart rate, weather consent
  off, local cards, explicit comprehensive preview and absence of live controls.
- Persistent history UI passed actual save, termination/relaunch, restoration,
  fresh consent, selective deletion and a second relaunch with no saved record.
- Offline rehearsal: all ten groups passed with zero network attempts. Preserved
  starter: three tests passed. Study artifacts independently reproduced exactly.
- Independent reviews found and fixed protected-history overwrite/privacy cases,
  plan-versus-completed accounting, mismatched context, arbitrary rendered prose,
  inapplicable insight IDs and saved-publication/deletion races. Regression tests
  were observed failing before the fixes.

The integrated numerical/v3 backend suite now passes **1,278 tests plus 32
subtests**. Independent reviewers passed 14 numerical tests, 100 additional
selected-model probes, byte-for-byte synthetic reproduction, 45 focused API
tests and six redirected fake-transport gateway scenarios. These checks overlap
with the full suite and are not additional independent accuracy observations.

Physical milestone: **132 XCTest passed** on iPhone 17 Pro / iOS 27.2 after an
isolated non-strict Date comparison crash was corrected in the temporary test
copy. The copy used a separate identifier and omitted HealthKit for available
local signing. The original app was preserved. See the
[physical report](PHYSICAL_HYDRATION_CHECK_2026-11-03.md) for the red probe, exact
scope and local artifacts. Final v3 native checks use Simulator at the user's
request; physical UI and production HealthKit permissions remain unverified.

Final native integration: **145 XCTest and three actual mock-backend Simulator UI
flows passed**. The default workflow and explicit experimental cold-start path
exercise separate rich-preview consent, disabled live controls and clearing
results/consent when switching models. The additional selected-fit test loads six
saved synthetic measurements through the actual app, requires fresh processing
consent, and displays the backend's fitted **442 mL [280–700]** result. Its local
analysis and separately consented rich preview repeat those numbers. Live actions
are absent, and all six records are deleted through the app before the test ends.
The history was prepared only in an empty synthetic Simulator profile, using
`scripts/prepare_runtime_ui_fixture.py`; production startup is unchanged. The
helper's nonempty-history refusal was also executed and confirmed nonmutating.
This is real app/backend execution with invented measurements, not real-person
accuracy or live Muse Wonder evidence.

Selected-fit UI artifact (one test, 198.544 seconds, zero failures):
`/Users/georgiosaliba/Library/Developer/Xcode/DerivedData/HydraAI-grtpiouhpncseiertdarvygufccy/Logs/Test/Test-HydraAIEndToEnd-2026.11.03_01-24-10--0500.xcresult`.
Log: `/tmp/hydra-selected-runtime-ui-enabled.log`. Its separate default-off gate
check passed with one expected skip. Screenshots were visually inspected for
readability; the original two workout UI flows remain separately recorded below.

Final UI artifact:
`/Users/georgiosaliba/Library/Developer/Xcode/DerivedData/HydraAI-cncabecfdzawlmawinijecnmjgbo/Logs/Test/Test-HydraAIEndToEnd-2026.11.03_00-59-17--0500.xcresult`.
Final source-worktree unit artifact:
`/tmp/hydra-runtime-ios/Logs/Test/Test-HydraAI-2026.11.03_00-58-14--0500.xcresult`.
Fresh integrated-branch verification after the final native cherry-pick passed
**1,278 Python tests plus 32 subtests** and **145 XCTest**. Local logs:
`/tmp/hydra-intelligence-final-python.log` and
`/tmp/hydra-intelligence-final-ios-unit.log`; final integrated native artifact:
`/tmp/hydra-intelligence-final-ios/Logs/Test/Test-HydraAI-2026.11.03_01-03-12--0500.xcresult`.
The preserved starter passes three tests, and the offline rehearsal passes all
ten groups with zero network attempts. One pre-existing Starlette/httpx warning
remains. These are executed local checks, not a GitHub CI result.

Native review found and fixed both a valid partial-validation fallback rejection
and an impossible fitted-fold count. A real backend fixture covers the former;
the latter was observed red before its guard fix. Twelve complete response
fixtures reproduce the manually normalized input provenance. No outstanding
numerical, API or native review finding remains. No live Wonder quality, current
account balance, billing finality or clinical validity is inferred from these
software checks.

The first GitHub iOS build used Xcode 26.6 and found a compiler name-resolution
conflict between the duration formatting helper and a later local `duration`
string. Explicitly qualifying the helper as `Self.duration` preserves output and
supports that compiler. A fresh local **145 XCTest passed** after the correction:
`/tmp/hydra-intelligence-ci-compat-ios-unit.log`, with artifact
`/tmp/hydra-intelligence-final-ios/Logs/Test/Test-HydraAI-2026.11.03_01-08-48--0500.xcresult`.
The PR's check runs record the remote result separately; no runner or verification
was disabled to hide the failure.

## Review boundaries

The numerical engine is authoritative. Keep research labels, explicit provenance,
missing-data abstention, duration/environment comparability and conservative
uncertainty. A fitted coefficient is not a validated hydration measurement.
Population cold starts remain insufficient data. Raw HealthKit stays on device.

All provider, allocation, identity, exact-input disclosure, pricing and invoice
finality gates require separate current evidence before any billable experiment.
This branch neither inspects nor modifies the permanent financial ledger. The
appropriate next live test must be owner-authorized and one-use under the current
policy; there is no silent account switching or automatic retry.
