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
- Ninth-attempt finality and genuine cross-ledger refs remain activation gates.
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

- [ ] Write failing tests for old8/ninth-pending, policy/quote/source validation,
  budget/races/duplicates, typed ticket purpose and each existing personal flow.
- [ ] Implement the spec without modifying strict verified evidence/quote models.
- [ ] Run focused tests and full pytest; check verified/default-off compatibility.

## Task 2: Native readiness

Files: new typed GET-only readiness service/model/Settings section and tests.

- [ ] Test exact wire shape, state/reason invariants, no secret fields, auth,
  unavailable/error responses and no automatic retries.
- [ ] Implement an explicit availability check and accurate unavailable copy.
- [ ] Run XCTest and a real Simulator blocked-readiness/personal-preview flow.

## Task 3: Muse simulated training preparation

- [ ] Establish a separate scientific scenario-plan/simulation/training contract
  from the existing generators, preserving measured-data evaluation.
- [ ] Build strict payload/parser and reproducible offline fixture tests; connect
  its operator-only purpose to the same authority, never a separate provider path.
- [ ] Keep real-Muse generation pending until actual admission gates pass.

## Task 4: Review and staged operation

- [ ] Independent review, meaningful regression fixes and full relevant suites.
- [ ] Prepare genuine private configuration/draft; confirm ninth pending blocks
  every send and readiness displays actual blockers without financial mutation.
- [ ] Commit/push review PR, coordinate with Amine, and report actual limits.

Ruling: Existing autonomy and parallel-work instructions apply. Physical work is
deferred at the owner's request. No invented measurements will satisfy the real
personal-calibration requirement; Muse-generated simulations train a separately
labeled research artifact.
