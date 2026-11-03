# Owner Single Wonder Test Implementation Plan

> **For agentic workers:** Use test-first implementation and independent final review.

**Goal:** Run one explicitly authorized, clearly synthetic comprehensive Wonder
test while preserving all prior financial history, then replay it in Simulator.

**Architecture:** Operator-only event-backed one-use authority in the existing
ledger; existing transport/scaffold validator; read-only authenticated replay.

**Tech Stack:** Existing Python/FastAPI/SQLite and SwiftUI; no new dependencies.

**Spec:** `docs/architecture/WONDER_OWNER_ONCE.md`.

## Global Constraints

- No financial mutation or network send during development/testing.
- No real records, fabricated invoice finality, unfreezing, retries or fallback.
- $0.25 token reservation; published-token bound $0.059960; extras unverified.
- Explicit owner acknowledgement of unverified extras is required for live use.
- Synthetic identity and normal personal-result validation remain intact.

## Review Focus

- Concurrent consumption, crash and a second process must never send twice.
- A changed credential, historical financial snapshot or payload must refuse.
- Malformed usage/output must retain its reservation and never offer retry.
- A changed replay file must fail validation without touching the ledger.
- The viewer must not present synthetic evidence or token cost as personal/final.

## Task 1: Operator authority and replay producer

Files: `backend/wonder_owner_once.py`, `scripts/wonder_owner_once.py`,
`backend/wonder_owner_once_routes.py`, `tests/recognition/test_wonder_owner_once.py`.

- [ ] Write failing tests for one-send success, preservation, race, wrong key/hash,
  stale snapshot/expiry, active send, cutoff, failed/invalid usage and replay.
- [ ] Run the tests and verify expected missing-feature failures.
- [ ] Implement the exact spec, exposing `install_owner_once_routes(app)` and a
  CLI with read-only prepare plus explicit authorize/run commands.
- [ ] Run targeted tests, then the full pytest suite with no outbound network.

## Task 2: Native replay viewer

Files: new native owner-test models/view/tests and one existing navigation hook.

- [ ] Write failing validation tests for the exact envelope and tampered section,
  personal mode, false finality/cost claims and malformed receipt.
- [ ] Implement explicit GET-only loading and vetted local reconstruction.
- [ ] Run XCTest and an actual Simulator replay workflow against the backend.

## Task 3: Integration and controlled operation

- [ ] Integrate the default-off authenticated replay route in `backend/app.py`.
- [ ] Independent review; fix material findings with regression tests.
- [ ] Verify complete pytest/XCTest results, commit and publish a review PR.
- [ ] With owner risk acknowledgement, prepare/record one exact private permit,
  run once through the real transport, validate/save the response and replay it.
- [ ] Record actual outcomes and limits; keep all paid backend flags disabled.

Ruling: Earlier autonomy instructions apply to this execution; no repeated design
or implementation-method approval is requested. The user chose Simulator, so the
physical installation remains pending and is not claimed as verified.
