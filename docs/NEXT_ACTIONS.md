# Hydra AI next actions

## Next actions — October 29 (Amine)

| Order | Action / owner | Completion evidence |
| --- | --- | --- |
| 1 | Amine: review PR #14 (Georgio's first camera request policy) | Submitted GitHub review on `b3eda64` |
| 2 | Georgio + provider: invoice finality for the PR #14 camera request | Reconciled billing evidence; unblocks any further request |
| 2b | Both: decide how a frozen account may resume after verified reconciliation (see BLOCKERS top item); then implement and review it | Decision in DECISION_LOG; reviewed `resume_account` command |
| 3 | Operator: finality migration, then `wonder_admin.py migrate-schema`, record the $30 allocation | Migration audit events; `preview-schema` reports `already_current` |
| 4 | Both: approve one Wonder case per demo item: one scenario (`prepare --scenario complete`) and one suggested question (`prepare --question-id hot_weather`) | Recorded `ApprovedCase`s with spending and live-dispatch references |
| 5 | Operator: `run-case --confirm-billable` for each approved case, then record invoice finality | `complete.json` and `assistant-hot_weather.json` replay in the app |
| 6 | Georgio: physical-iPhone pass over History edit/delete, Ask Hydra, goal progress and the recorded Wonder sections | Device notes and screenshots |
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
