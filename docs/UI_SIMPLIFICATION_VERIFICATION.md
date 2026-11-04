# Simpler Insights verification

The user selected the guided workout design on November 3, 2026. This change
implements that design in the native SwiftUI app; the earlier browser preview
was illustrative. Review PR: [#79](https://github.com/georgiosaliba227/Hydra-Ai/pull/79), left unmerged.

## Implemented experience

- Workout: workout → conditions → review/result, with separate past-measurement
  and simulated-demo sheets. Back preserves the draft. Leaving or changing the
  backend clears session measurements, consent and results.
- Muse: saved summary and its own date window first; complete additional
  insights and sources are available on demand. A separate data review includes
  every typed fact, recipient, account/cost bound and default-off consent.
- Ask Hydra: three initial questions, optional answer settings and per-answer
  sources. Recorded answers remain labeled and cannot include today's log.
- Today: logging, volume and recent drinks, plus one Insights entry. History
  retains the full previous-week report under Logging details; the weekly chart
  still says that days without logs represent unknown intake.
- Accessibility: wrapping feature rows at accessibility text sizes, local
  keyboard focus/validation in the measurement sheet, and availability-guarded
  suppression of iOS 26's bottom scroll-edge fade where it reduced text contrast.

## Verification performed

All backend data was disposable and synthetic. Provider credentials were
excluded from test processes. No Meta request or private financial-ledger
operation was performed.

- Maintained Python suite: **1,322 passed, 5 skipped, 58 subtests passed**.
  Command: `python -m pytest -q tests` using the existing project environment.
  One existing FastAPI/Starlette TestClient httpx deprecation warning remains.
- Preserved starter suite: **3 passed**, run from `Hydra-Ai-Starter`.
- Full iOS unit suite: **103 passed, 0 failures**, including cancellation,
  consent, invalid response and forecast boundary cases. Latest result:
  `/tmp/hydra-simplify-review-unit-green.xcresult`.
- Native UI checks on iPhone 17 Pro / iOS 26.5: the 14 functional cases in
  `/tmp/hydra-simplify-final-ui.log` passed. They cover step/back preservation,
  missing-field focus, required personal-processing consent, clearing on leave,
  simulated results separate from logged consumption, complete Muse review,
  no send on review open/dismiss, reset consent on reopen, older saved result
  dates, full insights, assistant sources/recorded settings, largest accessibility
  text navigation, logging goals and history editing.
- Manual logging/relaunch persistence and history editing passed separately
  after moving the full history report into its disclosure.
- The synthetic personal-workout check produced 700 mL with a 645–755 mL range
  from supplied fixture measurements. This verifies the UI/request/result path,
  not physiological accuracy or a drinking requirement.

The initial native accessibility audit exposed text contrast failures near the
floating tab bar. The scroll-edge fade was removed on supported OS versions and
Today's redundant count label was removed. Audit thresholds and existing
exemptions were not weakened. The final audit passed on Settings, Today, History and Ask Hydra
(1 native test, 0 failures; `/tmp/hydra-simplify-contrast-complete-2.log`).
The largest-text Insights/workout audit also passed in the functional run.
On iPhone SE (3rd generation) / iOS 26.5 in dark mode, **4/4 native
cases passed**, covering navigation, guided validation/back, largest-text
reachability/audit, and the saved Muse window/full insights. Screenshots were
exported and visually inspected for wrapping and readable primary controls;
`/tmp/hydra-simplify-compact-dark.log` records the run.

## Reproducing safe review interactions

`scripts/insights_review_fixture.py` runs an isolated loopback mock backend with
disposable synthetic data. `--saved-example` adds an intentionally older saved
Muse explanation. Its fake review capability allows UI verification of the
consent control; every trends POST is counted and rejected before provider
delegation. `/__test__/trend-sends` requires the generated test token.
`tests/backend/test_insights_review_fixture.py` verifies those boundaries.

Use `--unavailable-demo` alongside `--saved-example` to verify the real server
response when the simulated artifact is missing; repository artifacts are not
modified.

The opt-in native tests use `HYDRA_E2E_BACKEND_URL`, `HYDRA_E2E_API_TOKEN` and,
for consent/saved-result tests, `HYDRA_E2E_REVIEW_BACKEND_URL`. Use only local
disposable test backends. Never commit test tokens or private `.xctestrun` files.

## Execution decisions

1. Implement in the existing isolated worktree, using one final independent
   review after the user chose Guided. Cost: fewer independent reviews during
   intermediate edits; native tests and the final review cover the whole change.
2. Work on independent assistant presentation while baseline UI checks ran
   against the pre-change binary. Cost: attribution would be unclear if baseline
   binaries were mixed; the baseline build remained separate.
3. Add a fake, nonbillable review capability because ordinary mock mode cannot
   expose live-style consent. Cost: this verifies interaction rather than actual
   paid inference. All POSTs are rejected before provider delegation.
4. Move the full history report behind Logging details and remove Today's
   redundant count. Cost: detailed statistics take one additional tap.
5. Commit the related native views and their shared navigation tests together.
   The three logical plan tasks were implemented with individual failing checks
   before changes, then verified as a combined flow. Cost: a larger review diff.

## Limits

These are simulator and synthetic-data checks. They do not establish physical
device usability, a complete spoken VoiceOver walkthrough, physical HealthKit
behavior, physiological validity, or a real Meta/account/billing round trip.
No dependencies, backend contracts, calculations, camera behavior, HealthKit
permissions, credentials or spending policies changed.

## Independent review

The fresh whole-branch review found five important issues. Each was accepted:
use the navigation-bar Back for the previous workout step; consume processing
consent per submission; reset the optional today-total context when leaving Ask;
accept the keyboard's decimal separator without guessing grouping or accepting
nonfinite input; and distinguish an unavailable demo from missing personal
measurements. Each issue was reproduced before its fix. The strict decimal-parser regression
now passes in the 103-test full unit suite. Navigation Back, guided validation
and the largest-text flow also pass on the compact dark iPhone SE (3/3 cases)
after the changes. The full affected native run executed 19 cases: 18 passed, and the personal
case failed only because its last assertion assumed the text cursor appended
to a field (iOS inserted at the beginning). Consent reset and sample preservation
already passed before that assertion. The test now compares the actual changed
duration; its targeted rerun passed (1/1, 0 failures) in
`/tmp/hydra-simplify-reviewed-personal-green.log`. Every one of the 19 affected
cases therefore has a passing result on the final product implementation.
No product change occurred between the broad run and targeted rerun.
`/tmp/hydra-simplify-reviewed-ui-green.log` contains the complete run.

Two minor findings are deferred: the optional JSON facts display omits explicit
null keys, although every nonnil value and the unknown goal are visible in the
complete readable review; and accessibility-size field labels could use their
own row to wrap less. Both remain available for follow-up review.

The reviewer declined to assess spoken physical-device VoiceOver order,
physiological accuracy and real Meta billing. Those limits stand: the synthetic
native audit and controller/contract tests support the UI claims here; they do
not support claims about those external behaviors. The cost is that physical
usability and real-world/provider behavior remain unverified.

The reviewed fix pass is complete: the five important findings have RED→GREEN
regressions, the maintained Python suite passes 1,322 tests (5 skips, 58 subtests),
and the iOS unit suite passes 103 tests. Native screenshots were inspected on
iPhone 17 Pro in light mode and iPhone SE in dark mode, including accessibility
text sizes. No additional whole-suite rerun followed the test-only caret fix;
all unaffected cases already passed on the same product code.
