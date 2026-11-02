# Camera cutoff policy implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

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
- [x] Add failing tests for repeated requests with old unresolved holds, cutoff boundary, history preservation, race, replay, invalid usage, wrong credential and payload substitution.
- [x] Implement controller and run focused tests.

### Task 2: Gateway and activation
**Files:** backend/meta_gateway.py, backend/meta_provider.py, backend/app.py, scripts/meta_camera_cutoff.py, tests/recognition/test_camera_cutoff.py.
**Interfaces:** explicit `HYDRA_META_CAMERA_POLICY=georgio-camera-cutoff-v1`, 1024-output Standard transport, private activation command; default old behavior unchanged.
- [x] Add failing fake-HTTP and authenticated app tests, including consent, two sequential requests and confirmed logging.
- [x] Implement and run full pytest, offline rehearsal and existing starter tests.

### Task 3: Real verification
- [x] Review full diff and private read-only exposure; activate additive policy without changing old rows.
- [x] Run one real verification with the approved photo, preserve response/usage/latency and full reservation.
- [x] Connect the physical app to the explicit owner backend; verify capabilities and Confirm/Edit; report actual results and limits.

## Verification completed November 2, 2026

The owner confirmed the live result appeared on the physical iPhone. The authoritative gateway has a second successful official-provider request and the owned beverage store has exactly one confirmed entry bound to that receipt. Its confirmed quantity equals the deterministic hydration-engine beverage volume. Container capacity and water content remain unknown; no model-inferred size or consumption is claimed. The $120 cutoff path remains enabled, all historical holds remain accounted, and no prior financial rows were reset.

Local full suite: 1,155 passed, 32 subtests passed, one skipped. Hosted Python 3.13/3.14, offline rehearsal and preserved starter checks passed at implementation commit18b9192. Earlier physical Confirm/Edit tests passed; the latest live display and save now also have user confirmation and durable backend evidence.
