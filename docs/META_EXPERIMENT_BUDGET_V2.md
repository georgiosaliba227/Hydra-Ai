# Georgio’s $30 Meta hydration experiment allocation — V2

October 28, 2026. The updated user instruction replaces the earlier proposed $10 allocation with **$30 total on Georgio’s account**, with planning targets of $20 Muse Spark1.3 Standard and $10 Muse Wonder1.0 Standard. These targets are soft allocations; they never authorize separate $30 pools, automatic model/account fallback, or additional spending. Existing account-specific controls and history remain authoritative.

**Implemented and tested: inert review-only accounting. Live batch execution remains unavailable.** No private spending ledger was opened, modified, copied, migrated or reset by this work. No authenticated provider probe, billable request, account credit verification, deployment or top-up occurred. User authorization of an experimental allocation does not establish provider guarantees, current credits, model access, reviewed policy transition or data-disclosure consent.

## What the implementation does

`backend/meta_experiments.py` accepts an existing `AccountLedger` authority, not a path or independent balance store. Its proposed tables and immutable triggers sit alongside the existing financial history. There is no production schema installer: only disposable tests install the DDL. The module’s transactions open existing owned mode0600 ledger files, reject symlinks/sidecars, verify database integrity and exact financial/experiment DDL, and use the existing atomic transaction mechanism. Unknown financial triggers, missing immutable guards and malformed historical amounts fail closed.

A single fixed allocation identity prevents requesting another allowance under another experiment name. Approval evidence is immutable, with identical re-import idempotent. Account identity and credential fingerprint must match current existing Georgio evidence. Amine cannot be selected, and Amine’s balances, approvals and permits are not changed. A project-wide freeze or any unresolved previous invoice from either account blocks admission.

`reserve_review_only` atomically writes the reservation into existing `live_attempts` and an immutable experiment link. It records an incompatible `experiment_review_only` state: existing dispatch, network-ticket claim, settlement and finality APIs cannot turn this reservation into live inference. The module returns `dispatch_enabled:false`, never a network-capable ticket. It has no transport, HTTP route, environment activation switch, settlement or release method.

Aggregate consumption counts the greater of reserved and actual gross cost for every linked attempt across both models and all retries. Finalized lower charges do not replenish the allocation. This deliberately conservative rule ensures the immutable $30 authorization cannot be reused. A maximum exactly reaching $30 is allowed; an admission exceeding it is denied. The first review-only reservation after a crash remains unresolved and blocks every next attempt until genuine reconciliation; no timeout refunds are implemented. Test-only synthetic provider finalities exercise later admissions; they are not production evidence.

Per-request exposure stays at or below the unchanged $0.25 legacy `CAP`, with up to512 total output tokens. This is a conservative initial policy choice, not a promise that any real model request can satisfy that bound. A full-context worst-case quote may exceed it and must be rejected. Every input binds its payload hash and explicit input-approval reference. Retries are never automatic: at most two attempts per case, a new attempt UUID, same model/payload/case, finality of the previous attempt and an explicit retry approval are required. All retry reservations consume the same $30 allocation.

The legacy first-test and dual-test permit implementations remain untouched. No limit is raised, spent permit reset, credential rotated or historical amount overwritten.

## Account and pricing gates

Admission checks the account’s reconciled historical gross and all authoritative attempts. It queues notices to both developers at $75, requires separate Georgio further-spend evidence at $100, rejects new admission reaching $120 and retains the $150 absolute gross ceiling. Undelivered notices block further admissions. Current verified credits limit new exposure but never offset gross spending or transfer between accounts. Unknown, negative, fractional, malformed, over-bound or unreconciled history denies admission.

The official [Meta pricing reference](https://dev.meta.ai/docs/pricing-rate-limits) lists these Standard rates, in USD per million tokens:

| Model | Input | Cached input | Output |
| --- | --- | --- | --- |
| Muse Spark1.3 | 1.25 | 0.15 | 4.25 |
| Muse Wonder1.0 | 4.00 | 0.20 | 20.00 |

Reservations use uncached input pricing with integer upward rounding plus an explicitly reviewed bound for every additional charge category. The source prices alone do not verify account-specific billing, model availability, internal/reasoning charges, failed-request exposure, taxes/fees, credit restrictions or invoice finality. Quote descriptors must include current model-access and all-charge evidence references. Such descriptors remain operator attestations; code cannot independently establish their truth. Price changes require a separate reviewed snapshot and implementation update.

## What remains before live evaluation

1. Human review of the proposed schema, allocation identity, policy transition, accounting code and gateway integration. The new schema is not installed in the private authority; existing legacy migration inspection intentionally does not accept these added triggers.
2. An independently reviewed live batch adapter and explicit existing-only schema migration. Neither is implemented here, and no activation command is provided. Live dispatch must recheck all evidence immediately before send and preserve project-wide one-in-flight/finality semantics.
3. Reconcile every prior account attempt and provider invoice, verify available Georgio credits and expiry/grant restrictions, bind the selected credential to the provider account, verify access to each exact Standard model, and establish all-inclusive per-request bounds.
4. Genuine developer reviews, proof of notification delivery, an approved finite case manifest and output limit, and separate exact-input disclosure consent under applicable data-use/retention terms. Initial cases should use reviewed synthetic context; actual HealthKit records remain excluded.
5. A human-approved live policy transition, exact case count and model schedule within the single $30 aggregate, the existing account cutoffs and verified per-attempt maxima. The $20/$10 planning targets may not expand the aggregate. Any retry needs separate explicit approval and prior billing finality.

Because this phase is inert, passing tests is not a claim that live financial safeguards are complete or independently verified. Until the above is implemented and verified, the real provider path stays disabled.

## Verification

Behavioral tests cover immutable allocation identity, replay/new-name attempts, Amine denial, known/unknown prices, all-charge bounds, missing evidence, per-request limits, both-model aggregate exhaustion, soft targets, lower-cost finality without replenishment, explicit retry ancestry, concurrency, crash/reopen, rollback after insertion, unresolved Amine attempts, $75 notices, $100 further approval, $120/$150 bounds, credit exhaustion, missing/modified schema, corrupt amounts and old gateway/settlement/finality rejection. All fixtures use temporary synthetic authoritative ledgers; no private database is opened.

Run:

```sh
python -m pytest -q tests/recognition/test_meta_experiments.py
python -m pytest -q tests/recognition
python -m pytest -q tests
```

Local verification for this budget commit: **49 experiment tests** within **584 maintained tests and 32 subtests passed**; one offline-training dependency group skipped in the application environment, and one existing Starlette/httpx deprecation warning. No iOS code changed. Independent read-only financial review found no blocker within the inert scope. A finite approved case manifest is still required before a live adapter could prevent re-identifying a retry as a new case.

The implementation contract and staged plan are in [META_EXPERIMENT_API.md](architecture/META_EXPERIMENT_API.md). The parent integration report records actual test counts for the final combined commit.
