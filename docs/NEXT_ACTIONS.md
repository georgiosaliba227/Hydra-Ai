# Hydra AI next actions

## November 3 — latest operational handoff

1. Review [PR #73](https://github.com/georgiosaliba227/Hydra-Ai/pull/73),
   `codex/wonder-personal-risk-admission`, stacked on PR #72; preserve
   PR #65/#71/#72 dependencies and human merge. Home research score, ongoing
   owner-risk admission and actual Muse-guided research training are implemented
   and verified. Camera branches remain separate.
2. Physical installation remains deferred at the owner's request. When chosen,
   install the updated HealthKit-signed original bundle and verify real workout
   import, permission prompts, weather and final Home/analysis screens. Do not
   repeat requests for the owner to stay awake or reconnect during Simulator work.
3. On the real profile, choose a personal beverage goal and log actual drinks.
   Collect protocol-confirmed manual workout measurements with error bounds;
   at least six qualified comparable records are needed for experimental fitting,
   which may still retain the baseline. Never import simulated training rows as
   actual history or interpret the product score as body hydration.
4. The local owner backend is configured for personal Wonder under the explicitly
   accepted uncertainty. Each new personal disclosure still requires exact in-app
   aggregate preview and fresh Meta consent. Verify the actual personal-data flow
   when records/phone are available; the controlled eight-section synthetic test
   and public-only training plan are not that verification.
5. Preserve all reservations and invoice-unknown labels. Recheck readiness and
   renew genuine account/price observations if expired; reuse standing human
   references without inventing new approvals or resetting counters. A failure or
   missing usage/publication still requires review. Mac hosting works while awake
   on the same LAN; an always-on deployment remains separately unapproved.

See [actual Muse training](MUSE_GUIDED_TRAINING_2026-11-03.md) and the
[personal policy](architecture/WONDER_PERSONAL_OWNER_POLICY.md). Older next steps
below retain their dated evidence and do not override the newer explicit waiver.

## November 3 operational follow-up

1. Review `codex/wonder-owner-once`, stacked on PR #71. Preserve the explicit
   owner waiver, ordinary gateway controls and the existing financial records.
   Do not automatically merge or deploy.
2. When the owner chooses a physical pass, install the already HealthKit-signed
   combined app, connect its owner-authenticated local backend, and verify actual
   HealthKit/workout import, permission prompts and weather on the phone.
3. Use Settings → Recorded Wonder test to revisit the real synthetic eight-section
   response without a new charge. Its usage-based estimate is not final billing.
   Ongoing personal live use needs its own configured admission path; the
   singleton operator test is consumed.
4. Enter actual comparable manual workout measurements in the app when available.
   Keep the default baseline and research labels; never substitute this test's
   synthetic observations for personal calibration.

## November 3 continuation

1. Review [PR #71](https://github.com/georgiosaliba227/Hydra-Ai/pull/71) with Amine, preserving PR #65 as its
   dependency and requiring human merge. Native experimental mode, the Date
   correction, 145 XCTest and three actual mock Simulator flows are verified,
   including the selected fit from saved synthetic history through deletion.
   Screens were inspected; camera branches remain separate.
2. Collect consented, dated, protocol-confirmed repeat workouts with consumed fluid,
   urine and independently supported error bounds for prospective personal-model
   evaluation. Do not retune against the published synthetic failures or describe
   historical-error envelopes as calibrated future coverage.
3. Retain the current baseline default. Evaluate the stationary v3 model only as
   explicit research; the calendar-time learner remains offline. Keep the three
   real-study targets separate and study artifacts out of personal serving.
4. When the developers have a suitable Xcode account/profile, verify the original
   HealthKit entitlement and permission path on hardware. Physical milestone
   storage tests passed in a separate bundle; final v3 and UI checks use Simulator
   at the user's request. Do not ask the user to stay awake for further tests.
5. After separately verified account identity, exact-payload disclosure, price,
   budget authority and project-wide invoice finality, perform an explicitly
   authorized one-use Wonder request and evaluate actual groundedness/usefulness.
   No private state was audited or modified here; older assertions below cannot
   substitute for current evidence.

## Next actions — Georgio's key on Amine's Mac, $20 (October 29, Amine)

Owner override in AGENTS.md. Spending is recorded as Georgio's account.

| Order | Action / owner | Completion evidence |
| --- | --- | --- |
| 1 | ~~Georgio: agree to the shared key~~ (he may also resume his own $30 ledger; Amine's limit is capped at $85 so both stay under $120) | Done, relayed 2026-10-29 |
| 2 | Amine: create the ledger for `georgiosaliba227` with `wonder-georgio-key-amine-mac-20usd`, both standing references; gross = dashboard + $1.312256 camera reservation | `preview-schema` is `already_current`; allocation recorded |
| 3 | Amine: start the backend with `HYDRA_META_GEORGIO_API_KEY` (entered with `read -s`), run one case, then record its invoice finality | Saved result replays in the app |
| 4 | Amine, any time: `wonder_admin set-limit --database ... --limit-usd <N> --reference <why>` (at most $85) | `experiment_limit_changed` event |

## Next actions — Wonder trends, October 29 (Amine)

Wonder can now explain the user's own 14-day trends on either account
([WONDER_TRENDS_API.md](architecture/WONDER_TRENDS_API.md)). This is the
fastest path to a real Wonder request, because Amine's account gets its own
ledger and isn't affected by Georgio's freeze.

| Order | Action / owner | Completion evidence |
| --- | --- | --- |
| 1 | ~~Amine: review and merge the Wonder trends PR~~ | Done: PR #51 merged as `d669781`, CI green |
| 2 | Georgio: confirm the camera request's invoice is final, and that his ledger does not attest Amine's account | Finality: Georgio reports he recorded it (relayed by Amine, 2026-10-29; not independently verified, his ledger is private). Still open: confirm with `meta_budget_admin view` that his ledger has no `aminealichaouche` row |
| 3 | Amine: set up his ledger (setup steps 2–6 in WONDER_TRENDS_API.md) from his Meta billing page | `preview-schema` reports `already_current`; allocation recorded |
| 4 | Amine: start the backend live on his account; in the app, preview, consent and explain once | Saved `trends-<hash>.json`; screenshot of the result with tokens and cost |
| 5 | Amine: record invoice finality before any second request | `record-invoice-finality` succeeds |

## Next actions — October 29 (Amine), earlier

| Order | Action / owner | Completion evidence |
| --- | --- | --- |
| 1 | Amine: review PR #14 (Georgio's first camera request policy) | Submitted GitHub review on `b3eda64` |
| 2 | Georgio + provider: invoice finality for the PR #14 camera request | Reconciled billing evidence; unblocks any further request |
| 2b | Both: decide how a frozen account may resume after verified reconciliation (see BLOCKERS top item); then implement and review it | Decision in DECISION_LOG; reviewed `resume_account` command |
| 3 | Operator: finality migration, then `wonder_admin.py migrate-schema`, record the $30 allocation | Migration audit events; `preview-schema` reports `already_current` |
| 4 | Both: approve the two Wonder demo cases in [WONDER_DEMO_APPROVAL.md](WONDER_DEMO_APPROVAL.md) (exact hashes, ~$0.04 worst case total) | Recorded `ApprovedCase`s with spending and live-dispatch references |
| 5 | Operator: `run-case --confirm-billable` for each approved case, then record invoice finality | `complete.json` and `assistant-hot_weather.json` replay in the app |
| 6 | Georgio: physical-iPhone pass using [PHYSICAL_IPHONE_CHECKLIST.md](PHYSICAL_IPHONE_CHECKLIST.md) (12 steps, no Meta calls) | Dated device report with screenshots |
| 7 | Both: demo video, eligibility checks and submission before Nov 4, 9 PM ET | Submitted entry |

## Current forecasting assignment — October 28

Camera development is paused by the latest user request. PR #13 is merged at
`700fe6d`; do not reapply its features or treat its old review gate as still open.
Review the additive forecasting branch and [Issue #15](https://github.com/georgiosaliba227/Hydra-Ai/issues/15).
The current work is public dataset verification/deidentification, separate study
and synthetic experiments, personal calibration, and backend/iPhone integration.
Use the [model contract](architecture/WORKOUT_MODEL_API.md), data inventory, model
card and evaluation report as the review package. Human review, physical iPhone
verification of the new screen, and external validation remain required before
broader use. Generic physiological predictions and daily intake requirements stay
unavailable without suitable evidence. All billable Meta requests remain disabled;
this work does not change the private ledger or resolve provider gates.

## Earlier Meta workstream handoff — historical

Updated October 28, 2026 after state restoration and additional camera safeguards. Meta-first and integration branches were already identical at `ef7dc94`; use existing PR #13 without reapplying completed development. The immediate milestone is verified Meta inference in both workstreams, measured results and the existing iPhone camera workflow. Unrelated UI and speculative development remain deferred.

Implementation `ae01987` is pushed to both branches and tested: 485 maintained pytest + 32 subtests, 3 starter, 41 XCTest, 2 mock UI and 1 fake-provider consent UI passed; 4 opt-in UI cases skipped. The ledger preview is compatible and read-only. Do not repeat those completed checks without a new code change or concern. Review the [posted PR #13 handoff](https://github.com/georgiosaliba227/Hydra-Ai/pull/13#issuecomment-6472453361); CLI permissions blocked editing PR metadata, so its conversation holds the full description. The next required progress is human review plus the private evidence/consent steps below.

| Order | Action / owner | Completion evidence |
| --- | --- | --- |
| 1 | Both developers: review the current PR #13 camera/parser/generation fixes and additive migration | Exact reviewed commit; migrate only the existing permanent ledger after separate operational review, using META_LEDGER_MIGRATION.md; never init/copy/reset it |
| 2 | Georgio + provider: finish the private selected-account evidence | Reconcile historical/pending gross billing and account-specific funding/content-use terms from authenticated evidence; bind the local key/account, verify credit expiry/grant terms and notice delivery; preserve dashboard details privately |
| 3 | Georgio + both reviewers: complete exact-input and cost authorization | Export actual iPhone-prepared JPEG, run read-only scripts.meta_camera_prepare, resolve every gate. The full-context token reference is $1.312256 before extras, above active $0.25; $2 remains an unapproved proposal. Exact-image disclosure and expiring named-account/input/model/price/policy spending approval remain mandatory |
| 4 | Operator + both reviewers: execute once, reconcile and evaluate the camera result | Official request ID, ledger-linked output digest, observed latency/tokens, usage-derived cost distinguished from final billing; human identity/consumption confirmation on iPhone |
| 5 | Amine + both reviewers: separately authorize synthetic hydration context and a later request | Amine account evidence, exact context fingerprint and explicit policy permitting the additional request; prior camera invoice finality first; no account fallback |
| 6 | Both developers: evaluate hydration relevance/consistency and record the real Meta demo | Real and mock results separated, errors and missing results included, deterministic calculations and all spending safeguards preserved |

Backend/API/evaluation implementation and mock tests proceed without waiting for paid activation. Current gates and commands are consolidated in [META_FIRST_DELIVERY.md](META_FIRST_DELIVERY.md). Do not repeat completed financial inventories or reinitialize/copy the authoritative ledger. Keep support inquiry unsent until explicitly authorized. Final device verification and submission eligibility remain necessary but do not displace Meta integration work.
