# Hydra AI project status

Updated October 29, 2026. Shared current status for Georgio and Amine; historical milestone reports remain evidence for their named commits, not current completion claims. See [next actions](NEXT_ACTIONS.md), [decisions](DECISION_LOG.md), and [blockers](BLOCKERS.md).

## Current state — October 29 (Amine)

`main` includes PRs #18–#49. GitHub Actions runs the pytest suite on Python 3.13
and 3.14, the offline rehearsal, the starter tests and, for iOS changes, the 64
XCTest unit tests on every PR (mock-only, no secrets).
One real Meta request has run: Georgio's single Muse Spark 1.3 camera request,
recorded on unmerged PR #14; its invoice finality is pending, which blocks every
new request project-wide. No Wonder request has run.

| Area | Status | PRs | Evidence (local unless noted) |
| --- | --- | --- | --- |
| Edit and delete logs (MVP 1) | Merged | #24, #25, #39 | 24 API tests incl. stale-revision delete; UI test logs 137 mL, edits to 211 mL, deletes, checking server totals |
| Export and delete all data | Merged | #42 | 3 API tests incl. erased content; UI test deletes all and sees a zero total |
| Accessibility | Hard audit failures fixed | #41 | Opt-in Xcode accessibility audit on four screens; 37 near-pass items logged for polish |
| Independent code review | Findings fixed | #38 | Busy-ledger settlement, run-case messaging, replay provenance, hostile result files, deletion privacy |
| Demo tooling | Merged | #35, #40, #43 | Submission draft, synthetic seed script, 10-group offline rehearsal, README diagram |
| User-chosen daily goal | Merged | #33 | 10 API tests; UI test shows progress on Today |
| Ask Hydra assistant (MVP 7) | Merged, local rules | #26–#28, #31 | 35 API tests incl. urgent escalation and no question storage; UI test |
| Wonder hydration explanations | Code merged, not run live | #18–#23 | Mock and fake-transport tests; 2 deliberate safeguard breaks caught |
| Wonder assistant topic selection | Code merged, not run live | #29, #30 | 21 + 4 tests; replay validated against reviewed answers |
| Wonder explains your trends, either account | PR open, not run live | this PR | 80 tests (facts, placeholder text checks, Amine $100 cutoff, wrong key or account refused before reservation, route, replay, delete-all); 5 XCTest; UI test; setup dry run on a scratch ledger; independent review findings fixed |
| CI | Merged | #32 | GitHub Actions: 774+ tests, rehearsal and starter tests pass on Linux |
| Nutrition catalogue | Unchanged (one product) | — | Live camera results never map to catalogue products; deferred with camera work |

Latest local verification on `main` (`b4dc4f3`): **795 pytest passed, 1 skipped,
32 subtests**; offline rehearsal **10/10 groups**; starter **3 passed**; **64 XCTest**
and **8 UI tests passed** (4 opt-in physical/live cases skipped) on the iPhone 18 Pro Max
simulator against a local mock backend. Not verified: any physical iPhone run
of the new screens, any live Wonder request, clinical or physiological validity.

## V2 review branch — October 28

`codex/hydration-intelligence-v2` extends the unmerged forecasting branch. The
$30 Georgio-only experiment allocation supersedes the proposed $10; $20 Spark /
$10 Wonder remain soft targets. The new financial module has only review-state
reservations and no private-ledger migration or live dispatch. Amine and the
existing finance modules/history remain untouched.

Implemented: supplied chronological calibration histories, UTC/DST ordering,
conservative historical envelopes, synthetic prequential comparison, strict
mock contextual A/B/C contracts, additive v2 endpoints and native display.
QDE artifacts/splits remain frozen; no independently validated real improvement.
Mock labels cannot rank Meta models; provider latency/tokens/billing stay null.

Integrated verification: **613 pytest tests + 32 subtests passed**, one optional
training module skipped and the existing Starlette warning. The pinned training
environment separately passed **50 forecasting tests** (overlapping runtime and
ingestion tests included). **50 XCTest tests** and **one targeted V2 UI test**
passed; its screenshot was visually inspected. The contextual benchmark reproduced
exactly and the longitudinal scenarios regenerated independently. Independent
reviews covered financial accounting and contextual/native numerical authority.

See [review handoff](HYDRATION_V2_REVIEW.md), [experiment controls](META_EXPERIMENT_BUDGET_V2.md)
and [longitudinal evidence](FORECAST_V2_EVALUATION.md). Missing live engineering,
review, account evidence and consent gates are explicit; no paid requests occurred.

## Forecasting implementation baseline — October 28

The latest fetched `main` is `700fe6d`, which merged PR #13. The user then authorized
isolated ML implementation on `codex/hydration-forecast-ml`, coordinated through
[Issue #15](https://github.com/georgiosaliba227/Hydra-Ai/issues/15). Camera development
is paused. All work below is for human review, with no deployment or automatic
merge. Earlier Meta handoffs below are historical and are not a fresh audit of
private financial state.

The branch is pushed. PR creation is currently blocked by GitHub access: the
connector returned 403 and the CLI account is not a collaborator; Chrome is signed
out. The complete [prepared PR description](FORECAST_PR_DESCRIPTION.md) is saved
for the owner/collaborator to publish. Amine is tagged in Issue #15; a review issue
is not a pull request. No PR creation or human approval is claimed.

- Verified actual files and reuse conditions for all six requested data sources.
  The ingestion pipeline produces 200 SpectroPhon corrected-mass-proxy records
  (198 conservative participant groups) and 80 QDE uncorrected-mass-proxy records
  (10 participants). Direct identifiers are stripped; repeated source identities
  remain grouped. The raw identity-bearing workbook was deleted after preprocessing.
  No raw or normalized individual records are committed. See [inventory](FORECAST_DATA_INVENTORY.md).
- Trained and compared cohort-rate, ridge, forest and boosting candidates using
  disjoint fit/validation/calibration/test participants. Real tasks are separate.
  SpectroPhon ridge test MAE is 71.79 mL; QDE selected boosting test MAE is 331.60 mL
  and is worse than its 314.22 mL baseline. Both artifacts are offline research
  models, not generic physiological forecasts. See [evaluation](FORECAST_EVALUATION.md).
- Generated a separate 480-scenario synthetic experiment from real training
  anchors only. Bootstrap relatives share split groups; synthetic accuracy does
  not establish real-world accuracy. JSON artifacts reproduce byte-for-byte in
  the pinned offline environment. New numerical dependencies are training-only.
- Added `/v1/workout-forecasts` and a separate iPhone screen for explicit synthetic
  demonstration or consented manual measured calibration. Personal samples are
  transient; median/envelope updates are deterministic, not persisted longitudinal
  ML. Cold starts and daily requirements remain `insufficient_data`. Existing
  logging, camera, HealthKit, Meta services and private ledgers are preserved.
- Meta explanation integration is exercised through reviewed local mock signals
  on server-owned synthetic context only. No real health record reaches Meta;
  live model quality is unverified and all billable calls remain disabled.

### Verification of the forecasting branch

- Integrated Python application suite: **535 passed, 32 subtests passed**, one
  optional training module skipped because that environment has no scikit-learn;
  the existing Starlette/httpx deprecation warning remains.
- Dedicated pinned Python 3.13 forecasting suite: **39 passed**, including the
  skipped training module and overlapping ingestion/runtime tests. All four
  artifacts independently rebuilt and compared byte-for-byte; full reproduction
  also passed with `RuntimeWarning` treated as an error.
- Preserved starter: **3 passed** in its own directory.
- iOS simulator: **47 XCTest unit tests passed**; **3 integration UI tests passed**
  (manual logging/restart, mock camera, forecast demo leaves intake unchanged),
  **4 physical/live opt-ins skipped**. A final targeted forecast UI rerun passed
  after plain-language range labels; its screenshot was visually checked.
- Independent review checked scientific target separation and leakage, and
  consent/stale-result/privacy handling. It found and fixed a 32-sample/body-limit
  mismatch with an endpoint-specific 128 KiB cap and maximum-provenance tests.

No physical iPhone test of the new screen, external-population validation, real
Meta call, private-ledger modification, or physiological/clinical validation was
performed. Training/proxy limitations and reproduction instructions are in the
[model documentation](FORECAST_MODEL.md). Human review and physical-device testing
remain necessary; there is no learned drinking recommendation.

## Earlier integration record — historical

`main` is `424f9fe` (merged #7). PR #12 was human-merged into #10 on October 27; #10 is `77a3ff4`, #11 `8ee883a`, and #9 `61f94e5`. These heads are combined in existing [integration PR #13](https://github.com/georgiosaliba227/Hydra-Ai/pull/13), initially `be4e492`. Meta-first implementation starts from that head on an isolated branch and preserves every source branch and worktree. No GitHub PR is automatically merged. Amine was notified on #13; unpublished work remains unknown.

The latest user instruction makes real Muse Spark 1.3 Standard camera and synthetic hydration inference the highest engineering priority. Unrelated UI and speculative features are deferred. **Neither real inference has run; the milestone remains incomplete.** Safe backend wiring, evaluation and request evidence are implemented for review. The single actionable activation checklist is [META_FIRST_DELIVERY.md](META_FIRST_DELIVERY.md).

## October 28 resumption

Fetched branches and inspected #9/#10/#11/#13. At resumption `codex/meta-first-delivery`, `origin/codex/meta-first-delivery` and PR #13's `origin/codex/roadmap-integration` were identical at `ef7dc94cc1888cf9699852e65e1b92732359955a`; the working tree was clean. All source proposal heads were already included, and main remained `424f9fe`. No duplicate merge or cherry-pick of completed development was needed. Georgio confirms Amine made no development changes since the previous session. Continue this same integration PR, preserving every earlier commit and requiring human review.

The tested October 28 implementation is `ae019876f43d9cddeed9a7772a2f8557160f205a`, pushed identically to `codex/meta-first-delivery` and `codex/roadmap-integration`. Subsequent handoff-only documentation commits do not change that tested code. GitHub reports #13 open and mergeable. The [complete current review description](https://github.com/georgiosaliba227/Hydra-Ai/pull/13#issuecomment-6472453361) tags Amine, and Issue #8 is updated. CLI metadata/reviewer editing was denied because `georgiosaliba-lgtm` lacks `UpdatePullRequest`; the PR description remains empty, so the review material is posted in its conversation. No credential/access changes or automatic merge occurred.

New safe work: reject blank model identity/explanation fields; give live camera errors fixed no-retry guidance; bind camera capabilities, consent, delayed results and confirmation receipts to backend configuration generations; add explicit existing-only finality migration preview/execution tools; and prepare exact-image, read-only request plans using the same payload, cost arithmetic and financial validators. The real permanent ledger remains unmigrated and unmodified. See [one-request procedure](META_CAMERA_ONE_REQUEST.md) and [migration contract](META_LEDGER_MIGRATION.md).

Georgio's server key again passed local loading without disclosure or an API call. The existing private configuration still selects mock mode, disables billing/hydration, lacks account/key attestation and notification configuration, and does not yet select the authoritative ledger. After user sign-in, the selected account's dashboard, billing, credit and all-key/all-model usage views were inspected read-only. This advances account evidence but does not establish a complete historical/pending gross baseline, key/account binding, grant expiry/terms, or billing finality. Account-specific funding/content-use terms also require review before image consent. Private dashboard identifiers, financial/payment details and screenshots remain outside GitHub. No evidence was fabricated or imported; no account setting was changed.

| Area | Implemented / verified | Remaining |
| --- | --- | --- |
| Manual logging | SwiftUI → authenticated local backend → SQLite; deterministic volume accounting; prior physical-iPhone baseline recorded | Repeat final integrated flow on physical device |
| Camera | Mock recognition, explicit confirmation, prepared JPEG reuse/export and separate Meta consent; #12 is in #10 | Actual share-destination byte verification and an authorized, bounded live request |
| Meta hydration | Authenticated synthetic-only backend endpoint, Amine-only live service, explicit independent enable flag; model selects bounded signals rendered with reviewed text | Separately approved synthetic input/account/request after camera billing finality; no real model quality claim |
| Evaluation | Reproducible offline recognition/explanation scoring and ledger-linked result digest, latency, usage and billing evidence | Actual observations and human labels/reviews; mock fixture metrics are harness tests only |
| Budget | Separate account ledgers, guarded one-use permits, reservation/race/crash controls; integration fixes global freeze and adds explicit invoice finality | Human code review and external account/provider evidence; no live approval |
| Forecast | Local authenticated conditional exercise-loss arithmetic and descriptive history; impossible completion timing fixed | Native history-only display verified on simulator; no daily physiological target approved |
| HealthKit | On-device steps permission/client | Physical permission tests; raw data export remains prohibited |
| Delivery | Offline mock rehearsal passes; four shared status documents maintained | Human eligibility/portal verification, demo capture and submission |

## Verification record

- October 28 combined changes: **485 maintained pytest tests + 32 subtests passed**; **3 preserved-starter tests passed** from the starter's own working directory. **41 XCTest unit tests passed** on the existing iPhone 18 Pro / iOS 27 simulator. Integrated UI: **2 mock tests passed, 4 opt-in cases skipped**, and **1 dedicated loopback fake-provider consent/confirmation test passed**. The synthetic evaluation report reproduced exactly and the seven-group offline rehearsal passed. Independent review found no additional actionable defects in the generation/receipt fixes or targeted migration. One existing Starlette/httpx deprecation warning and existing Xcode/fixture diagnostics remain; no new dependencies or physical-device/real-model verification.
- Meta-first combined changes: **410 pytest tests + 32 subtests**, **31 XCTest unit tests**, and **1 loopback fake-provider camera consent/confirmation UI test passed**. Offline evaluation reproduced its committed synthetic report; real camera/hydration observations remain zero. The seven-group offline rehearsal also passed. See [implementation and activation handoff](META_FIRST_DELIVERY.md) for precise scope and remaining requirements.
- Combined baseline before new review fixes: **291 pytest tests and 32 subtests passed**; one existing Starlette/httpx deprecation warning.
- Earlier integration baseline: **330 tests and 32 subtests passed**; **3 preserved-starter tests passed separately**. Includes account-freeze races, missing/corrupt invoice finality, privacy and completed-workout UTC/DST regressions. One existing Starlette/httpx warning remains.
- The offline `scripts/rehearse_demo.py` passed all seven groups with networking blocked, a temporary beverage-only database and no financial ledger use.
- Native history integration: **31 unit tests passed** on iPhone 18 Pro / iOS 27 simulator. Combined-backend UI run: **2 passed, 4 opt-in cases skipped**; dedicated fake-provider consent run: **1 passed**. The focused consent test verifies reset after both consents were granted; prepared image export remains available. Dashboard screenshot visually checked at default simulator sizing with no clipping. Existing test/compiler and simulator diagnostic warnings did not fail assertions; no new physical-device test is claimed.
- Permanent private ledger was checked read-only: owned regular file 0600, private parents 0700, integrity `ok`, all seven existing financial tables empty. No baseline, prices, permits, approvals or requests were fabricated. Empty tables do not prove zero provider spending. It was not copied, reset, migrated or configured into a server.
- No deployment, provider authentication/count/inference request, image disclosure, billing change or automatic merge occurred.

Tests establish software behavior and arithmetic, not scientific prediction validity, clinical efficacy, account balances or provider charge guarantees. Earlier physical-device evidence is in [the device report](PHYSICAL_IPHONE_TESTING_2026-10-27.md).

The official [event page](https://dev.meta.ai/events/global-hackathon) was rechecked October 27 and still lists November 4 at 9 PM ET as the submission deadline, subject to organizer updates. The waiver could not be freshly retrieved; participant eligibility and portal fields remain unverified.

Independent review: separate agents reviewed budget, forecast and camera/native paths with non-overlapping edits; a second reviewer checked the new finality gates without finding a blocking defect. Human approval is still required. The one known clock-skew forecast limitation is recorded in BLOCKERS.md.

Review handoff: [existing PR #13](https://github.com/georgiosaliba227/Hydra-Ai/pull/13), with [Meta-first coordination](https://github.com/georgiosaliba227/Hydra-Ai/pull/13#issuecomment-6450854995). Its human creation resolves the previous missing-PR blocker. CLI comments work; connected owner integration writes return 403. Review-branch updates use ordinary fast-forward pushes without force. Source PRs remain open, except previously merged #12.
