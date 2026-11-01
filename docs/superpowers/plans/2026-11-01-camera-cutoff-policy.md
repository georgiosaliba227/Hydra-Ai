# Camera cutoff policy implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable repeated owner-initiated Meta camera analysis under the retained $120 cutoff, preserving all spending history.
**Architecture:** An additive ledger adapter owns this new policy and its requests; the existing one-use policies stay intact. The same guarded gateway, transport and receipt/logging contracts enforce privacy and single network sends.
**Tech Stack:** Python/FastAPI, SQLite, existing Swift camera client.
**Spec:** docs/architecture/CAMERA_CUTOFF_POLICY.md

## Global constraints
- No old hold, permit or frozen flag reset; no fabricated baseline or final invoice.
- Georgio only; cutoff rejects reaching $120; external allocation held at its approved maximum $85.
- No retries, account fallback, tools or key in iOS. Explicit photo consent stays required.

## Review focus
- Concurrent admission near cutoff: only one request can reserve/send.
- Crash/timeout: full hold survives process restart, ticket cannot replay.
- Existing financial history: activation is additive and old gates stay closed.
- Provider usage/overrun: invalid usage never releases funds or invents final billing.
- Exact payload/key: tampering between reservation and network claim cannot send.

### Task 1: Additive controller
**Files:** backend/meta_camera_cutoff.py, tests/recognition/test_camera_cutoff.py.
**Interfaces:** CutoffCameraLedger.activate(policy), quote, reserve_first, mark_dispatched, claim_send, settle_provider_reply, quarantine; existing DispatchTicket and receipt contract.
- [ ] Add failing tests for repeated requests with old unresolved holds, cutoff boundary, history preservation, race, replay, invalid usage, wrong credential and payload substitution.
- [ ] Implement controller and run focused tests.

### Task 2: Gateway and activation
**Files:** backend/meta_gateway.py, backend/meta_provider.py, backend/app.py, scripts/meta_camera_cutoff.py, tests/recognition/test_camera_cutoff.py.
**Interfaces:** explicit `HYDRA_META_CAMERA_POLICY=georgio-camera-cutoff-v1`, 1024-output Standard transport, private activation command; default old behavior unchanged.
- [ ] Add failing fake-HTTP and authenticated app tests, including consent, two sequential requests and confirmed logging.
- [ ] Implement and run full pytest, offline rehearsal and existing starter tests.

### Task 3: Real verification
- [ ] Review full diff and private read-only exposure; activate additive policy without changing old rows.
- [ ] Run one real verification with the approved photo, preserve response/usage/latency and full reservation.
- [ ] Connect the physical app to the explicit owner backend; verify capabilities and Confirm/Edit; report actual results and limits.
