# Personal Wonder Risk Admission Implementation Plan

> **For agentic workers:** Use test-first bounded parallel implementation with independent final review.

**Goal:** Prepare the full personal Wonder path under the owner's standing risk
acceptance without faking evidence or replacing it with a synthetic demo.

**Architecture:** Add typed owner-risk authorization/quote/gateway beside the
existing verified policy; reuse every personal fact/consent/result contract.
Expose read-only readiness and keep actual admission blocked by missing evidence.

**Tech Stack:** Existing Python/FastAPI/SQLite/SwiftUI; no new dependencies.

**Spec:** `docs/architecture/WONDER_PERSONAL_OWNER_POLICY.md`.

## Global Constraints

- One existing ledger, $30 allocation, unchanged account cutoffs and old holds.
- No raw HealthKit export, fake finality/verified flags/reviews, retries or fallback.
- Without the later opt-in waiver, ninth finality/current cross-ledger refs remain
  activation gates. The owner's explicit later ongoing waiver preserves unknown
  status and holds, with checked usage/output/publication required.
- Synthetic training records never become personal measurement history.
- No new billable operation during implementation or mock verification.

## Review Focus

- A legacy waiver cannot silently include a newly unresolved request.
- An incomplete draft can boot previews/readiness but cannot reserve or send.
- One transport purpose cannot consume another purpose's ticket.
- Saved replay survives disabled/blocked admission and creates no new charge.
- UI state must distinguish configured from admissible without exposing secrets.

## Task 1: Typed authority, gateway and existing-route integration

Files: additive backend owner-policy/gateway modules, operator script, LiveConfig
hooks, readiness installer, existing personal-route hooks and focused tests.

- [x] Write failing tests for old8/ninth-pending, policy/quote/source validation,
  budget/races/duplicates, typed ticket purpose and each existing personal flow.
- [x] Implement the spec without modifying strict verified evidence/quote models.
- [x] Run focused tests and full pytest; check verified/default-off compatibility.
  Final integrated rerun follows the additive Home score below.

## Task 2: Native readiness

Files: new typed GET-only readiness service/model/Settings section and tests.

- [x] Test exact wire shape, state/reason invariants, no secret fields, auth,
  unavailable/error responses and no automatic retries.
- [x] Implement an explicit availability check and accurate unavailable copy.
- [x] Run XCTest and a real Simulator blocked-readiness/personal-preview flow.

## Task 3: Muse simulated training preparation

- [x] Establish a separate scientific scenario-plan/simulation/training contract
  from the existing generators, preserving measured-data evaluation.
- [x] Build strict payload/parser and reproducible offline fixture tests; connect
  its operator-only purpose to the same authority, never a separate provider path.
- [x] Keep real-Muse generation pending until actual admission gates pass.

## Task 3b: Owner-selected experimental Home score

The owner selected a transparent experimental combined-data rubric. See the
frozen `docs/architecture/HYDRATION_SCORE.md`: 50 recorded current-goal points,
30 recorded-consistency points, 20 manual-measurement-support points. These
weights are product rules, not physiological inference or learned accuracy.

- [x] Freeze semantics, inputs, missingness and numerical/AI responsibility.
- [x] Implement mirrored local/server calculation and a distinct Home card.
- [x] Add exact aggregate preview/consent, guarded Wonder explanation and replay.
- [x] Verify local dates/DST, strict types, corrupted/missing data, edits,
  provenance, shared financial finality and export/deletion.
- [x] Verify actual Simulator Home/details/preview and complete native suite.

## Task 4: Review and staged operation

- [x] Independent review, meaningful regression fixes and full relevant suites.
- [x] Prepare genuine configuration; verify default ninth-pending blocking, then
  separately verify the later explicitly opted-in waiver and ready status without
  inventing financial certainty. Read-only UI leaves ledger bytes unchanged.
- [x] Generate one actual Muse public simulation plan, train and byte-reproduce
  all five research outputs, preserve every pre-existing financial row/hold.
- [x] Commit/push [review PR #73](https://github.com/georgiosaliba227/Hydra-Ai/pull/73),
  request Amine's review, and report actual limits. No automatic merge/deployment.

Ruling: Existing autonomy and parallel-work instructions apply. Physical work is
deferred at the owner's request. No invented measurements will satisfy the real
personal-calibration requirement; Muse-generated simulations train a separately
labeled research artifact.
