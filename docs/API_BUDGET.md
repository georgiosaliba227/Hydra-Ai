# Shared Meta API budget design

Status: design only; no gateway, ledger, or enforcement implemented. Paid calls disabled. This run made no Meta inference calls; historical account spending and credits remain unknown.

One $150 ceiling covers both developers and all agents. Track gross estimated charges conservatively until credit accounting and expiry are verified. Codex/tool subscriptions are separate.

| Exposure (settled + unresolved reservations + proposed request) | Policy |
|---|---|
| Below $75 | Only after initial paid-use approval and safeguards |
| Reaches $75 | Notify both developers; persist one threshold event |
| Reaches $100 | Block pending explicit further-spend approval; record approver and scope |
| Reaches $120 | Reject every new billable request, even with $100 approval |
| $120–150 | Safety margin for unresolved charges; no automatic use |
| $150 | Absolute maximum; never intentionally exceed |

Meta explicitly provides alerts, not a hard cap. Verified 2026-10-26: [billing help](https://dev.meta.ai/help/billing/spend-limit-alert). This makes application enforcement and bypass prevention mandatory; paid access remains blocked.

## Required protocol before any billable call
1. Confirm project/account identity, historical usage, credits, expiry, all billable modalities, exact price versions, taxes/fees if applicable, and provider-enforced caps. Audit other keys/tools spending against the same account.
2. Keep the only production credential in a single gateway. Developer clients/agents use gateway credentials, never provider keys; revoke or account for alternate spend paths. Local configuration flags cannot prevent bypass by a separate key.
3. Bound image sizes/counts and preprocessing costs, input tokens, output tokens, and every billed category. Compute a conservative maximum request cost. Unknown or unbounded charge means reject. Proposed initial per-attempt ceiling: $0.25, subject to approval once prices are known.
4. In one SQLite `BEGIN IMMEDIATE` transaction, check policy/approval, unique idempotency key, settled usage and open reservations; reserve the full maximum cost before dispatch. A second request sees this reservation. Block if the proposed exposure reaches a gated threshold without its required approval, or reaches $120 at all.
5. Record dispatch/provider request ID; settle using authoritative usage at the verified prices. Maintain append-only accounting events and audit adjustments. Never silently reduce usage based on optimistic credit assumptions.
6. Timeout or crash after dispatch leaves the reservation outstanding until provider reconciliation proves the charge. Do not free it on a timer. Unknown settlement blocks when remaining capacity is insufficient. Provider idempotency must be verified before retrying ambiguous calls.
7. Proposed maximum one retry for transient failures only; each potentially billed attempt needs its own reservation linked to the parent. No retry on budget/schema/auth/consent failures. A request total cap must cover both attempts.
8. Reconcile provider dashboard usage before a paid session and after tests; unexplained variance disables further calls. Use a kill switch and durable threshold notifications visible to both developers.

## Required approval evidence
Publish price/source timestamp, credits/dashboard evidence without secrets, provider-cap result, a threat model for bypass/concurrent keys, maximum charge bound, race/crash/retry test results, reconciliation results, and explicit initial approval. If strict cutoff cannot be guaranteed, remain mock-only and request risk review. Never enable automatic top-ups.

## Planned tests
Simultaneous requests cannot oversubscribe; duplicate idempotency keys cannot dispatch twice; restart restores outstanding reservations; unavailable/locked/corrupt ledger fails closed; stale/unknown price blocks; ambiguous timeout retains full reservation; thresholds $75/$100/$120 including crossing requests behave correctly; retries obey combined cap; unauthorized callers and alternate paths cannot invoke provider; reconciliation discrepancies trip kill switch. Mock provider only until approval.
