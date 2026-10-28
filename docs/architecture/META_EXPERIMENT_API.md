# Meta hydration experiment budget V2 — inert accounting contract

Established before implementation, 2026-10-28. The user’s updated $30 Georgio allocation supersedes the original $10 proposal. This contract implements review-only accounting in disposable fixtures. It does not authorize or provide a live batch adapter, migration, dispatch ticket, API route or operator activation command. Camera work remains paused.

## Authority and immutable allocation

`ExperimentBudget(authority: AccountLedger)` accepts the existing authority object only. It cannot initialize a database, copy a ledger, reset evidence or install its proposed schema. All proposed rows share the existing `AccountLedger` SQLite transaction and existing `live_attempts`/`live_events` history.

Exactly one allocation row is allowed, with fixed identity `hydration-v2-georgio-30usd`, account `georgiosaliba227`, hard aggregate 30,000,000 USD microdollars. Re-importing identical evidence is idempotent; changing/replacing the row is rejected. A new experiment name cannot create another allocation. Spark 20,000,000 and Wonder 10,000,000 are soft planning targets; exceeding a model target is reported but cannot increase the shared $30 maximum. No Amine account admission, key switching, credit pooling or credit offsets.

`ExperimentApproval` contains expiry, verified key fingerprint, both developer review references, owner/spending authorization and explicit policy-transition reference. Approval descriptors remain human attestations, not independent provider verification. Existing account evidence must be current, account/key bound and not frozen. Live activation remains impossible even when all fixture attestations are supplied.

## Review-only reservation

`reserve_review_only(request: ExperimentRequest) -> dict` atomically checks and inserts a durable proposed reservation. A request binds a canonical attempt UUID, case UUID, approved payload SHA256, model quote, input/output token bounds, per-attempt maximum and optional explicit retry ancestry/approval. Initial policy ceiling is at most the unchanged legacy `CAP` of $0.25 per attempt; this does not raise any existing permit limit. Outputs are at most512 tokens. Quotes require exact known Standard model identity, reviewed current public token prices and an independently attested all-charge overhead bound; unknown fields, prices or charge categories deny admission.

Known model reference prices (USD per million tokens): Spark1.3 Standard input1.25/output4.25; Wonder1.0 Standard input4/output20. Cached discounts are not used for a reservation. Public reference pricing does not establish account access, available credits or all-inclusive provider guarantees.

Aggregate exposure is the sum of `max(reserved, actual)` for all linked attempts and retries across both models. Finalized lower actual charges never replenish this allocation; accounting is deliberately conservative. Gross actual above a reservation remains counted and frozen via existing controls. Account exposure separately includes its reconciled historical baseline and all legacy/new actual-or-reserved attempts. New admission reaching $120 is denied; $150 remains an absolute gross ceiling; $100 requires explicit further-spend evidence. At $75, notices for both developers are queued in the same transaction. Missing delivered notices block admission. Existing verified credits bound new exposure without reducing gross accounting.

Any prior unfinalized attempt anywhere in the project denies new admission. Existing project freeze and invoice-finality validation apply unchanged. This enforces one in flight and crash persistence. Retries require a new attempt UUID, same case/model/payload, prior finalized ancestry and an explicit retry approval; no automatic retry or reused dispatch occurs. Maximum two attempts per case is a conservative local policy.

The attempt state is `experiment_review_only`, which cannot pass existing `mark_dispatched` or `claim_send`. This module never transitions that state into a sending state, settles costs, releases reservations or writes finality evidence. Tests alone populate synthetic finality fixtures to exercise successive admissions. Proposed schema DDL is exposed for review and installed only by tests; production installation needs a separate reviewed migration.

## Implementation and verification plan

1. Add strict descriptors, fixed allocation identity and schema proposal in `backend/meta_experiments.py`; tests first cover wrong account, duplicate grants, missing/invalid evidence, unsupported model/pricing and expiry.
2. Implement same-authority atomic reservation and snapshot; tests cover $30 across both models/retries, soft targets, $75/$100/$120 thresholds, credits, unavailable schema/storage, rollback and concurrent contenders.
3. Verify crash/reopen, project-wide unresolved billing, no Amine changes, and old dispatch methods rejecting new states. No private ledger or actual provider calls.
4. Document implemented accounting versus unimplemented live activation in `docs/META_EXPERIMENT_BUDGET_V2.md`; run targeted recognition tests and maintained Python suite before commit.

Review focus: duplicate allocation identities; authoritative ledger reopening after a crash; retry charges across model targets; unknown costs and stale evidence; old dispatch methods consuming new reservations. Every case is pinned by behavioral tests.
