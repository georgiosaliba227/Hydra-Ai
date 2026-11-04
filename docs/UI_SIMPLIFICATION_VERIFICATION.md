# Simpler Insights verification

The user selected the guided workout design on November 3, 2026. This change
implements that design in the native SwiftUI app; the earlier browser preview
was illustrative. The branch is intended for an unmerged review PR.

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

- Maintained Python suite: **1,321 passed, 5 skipped, 58 subtests passed**.
  Command: `python -m pytest -q tests` using the existing project environment.
  One existing FastAPI/Starlette TestClient httpx deprecation warning remains.
- Preserved starter suite: **3 passed**, run from `Hydra-Ai-Starter`.
- Full iOS unit suite: **102 passed, 0 failures**, including cancellation,
  consent, invalid response and forecast boundary cases. Latest result:
  `/tmp/hydra-simplify-final-unit-2.xcresult`.
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
Compact dark-mode results are recorded below when complete.

## Reproducing safe review interactions

`scripts/insights_review_fixture.py` runs an isolated loopback mock backend with
disposable synthetic data. `--saved-example` adds an intentionally older saved
Muse explanation. Its fake review capability allows UI verification of the
consent control; every trends POST is counted and rejected before provider
delegation. `/__test__/trend-sends` requires the generated test token.
`tests/backend/test_insights_review_fixture.py` verifies those boundaries.

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
