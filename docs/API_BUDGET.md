# Account-specific Meta budget architecture (v2)

> Policy update: [dual controlled test preparation](META_DUAL_TESTS.md). The new $2/account policy is proposed and disabled pending exact approvals; older $0.25 statements below describe legacy policy/history, which remains enforced for legacy permits.

Updated 2026-10-27. This supersedes the earlier single shared-$150 assumption. The user reports two individual allocations; neither has been independently verified. This update authorizes NO spending and NO automatic key/account rotation.

| Account | Reported credit allocation | Current remaining / expiry | Gross usage / billing / hackathon grant terms | Authorization |
|---|---:|---|---|---|
| georgiosaliba227 | $150 | Unverified | Unverified independently | None |
| aminealichaouche | $150 | Unverified | Unverified independently | None |

The older October 26 dashboard snapshot ($150 credits, $0 payable, attached payment method) is historical evidence, not proof about both accounts or current gross usage. The available billing view redirects to a public page; no account secrets, authenticated probes, billing changes or Meta requests were used to establish these figures. Each owner must independently verify account/team identity, remaining credits, expiry, coverage, overage behavior, tax/fee categories, exact model access and grant/hackathon restrictions. A zero payable balance does not mean zero gross usage. [Meta billing alerts](https://dev.meta.ai/help/billing/spend-limit-alert) are not hard caps.

## Authority and account isolation

`backend/meta_accounts.py` implements separate logical account ledgers in ONE authoritative local SQLite file at the server gateway. Every attempt, reservation, provider receipt, notice and reconciliation event has an account identity. Each account has its own verified historical gross baseline, remaining-credit snapshot, expiry, provider-account reference, credential SHA256 binding and evidence expiry. Reusing the same provider identity/key across the two account records is refused. The server loads ONLY the explicitly selected account's credential; missing keys never cause fallback to the other account. No developer-local independent copies can be active authorities.

Project reporting sums gross usage/reservations, not credits. Missing account evidence is reported as incomplete/unknown, not zero usage. Credits are never transferable or pooled; unused B credits cannot fund A. No combined $300 spending authorization exists. Default mode remains mock with all billable requests disabled.

| Per-account exposure (gross baseline + settled costs + unresolved reservations + proposed maximum) | Enforcement |
|---|---|
| Reaches $75 | Durable notices for BOTH developers; delivery receipts required before dispatch |
| Reaches $100 | Explicit additional approval reference for THIS account required |
| Reaches $120 | Always reject new dispatch; the account's $30 reserve is untouched |
| $150 | Absolute gross ceiling, additionally checked; credits never offset gross accounting |

The first test has a stricter PROJECT-WIDE immutable singleton permit: one selected account, one approved metadata-normalized JPEG SHA256, both developer reviews, selected-account-owner authorization reference, spending-authority reference, image-owner consent reference, exact reviewed price version, expiry, $0.25 ceiling, one attempt and no retry. The permit is consumed in the atomic reservation transaction; it cannot be reset/reissued through the provided API/CLI. Any unresolved attempt in either account blocks another request. There is no HTTP admin/approval/settlement API.

## Spending protocol

1. Independently verify each account before using it; record only true owner-reviewed evidence through the private local operator CLI. Evidence is a human attestation, not an automated assertion that the dashboard was authenticated. Set private file permissions and exclusive gateway key custody; revoke/disable or otherwise account for all alternate spend paths. No software can enforce the cap against a separate provider key spending outside the gateway.
2. Review an immutable Standard-model price snapshot (USD microdollars, integer ceiling rounding), then an account/image-bound first-test approval. No raw images/prompts/credentials are stored. Per-attempt price/model snapshot, provider counts/ID and UTC events persist.
3. Quote with the selected trusted transport's proven input upper bound and 512 maximum output tokens, plus verified additional charge bound. HTTP clients cannot supply token counts, usage, prices, accounts or API keys to influence admission. Fixed prompt/schema, one bounded JPEG, no tools/history/Files/SAM/background and no automatic retries.
4. `BEGIN IMMEDIATE` atomically checks credit exhaustion, per-account gates, project permit, unresolved charges, evidence expiry, and image hash before reserving the full maximum. Missing/locked/corrupt/unconfigured storage denies admission. Legacy shared-ledger mutation is disabled when v2 is present. Legacy nonzero usage cannot be silently imported, split or ignored: retain and reconcile the old authority before establishing new account baselines.
5. Deliver each pending developer notice through the fixed-repository GitHub notifier and persist its receipt. Notification failure blocks Meta dispatch. An ambiguous notification may duplicate a human notice if manually redelivered; it cannot authorize an extra Meta call. Tests use a fake notifier; no alert has been sent as part of tests.
6. Persist dispatch state and an exact-payload one-use ticket. The real transport independently rechecks the ticket, selected credential and its own input bound before its sole HTTPS POST. Redirects/proxies/retries/arbitrary endpoints are unsupported. A crash anywhere after reservation retains the full unresolved amount; no timer releases it.
7. Derive charges ONLY from the authenticated transport's top-level provider usage and the immutable per-attempt price snapshot; never model-generated/client-supplied usage or operator-provided cost figures. Store only allowlisted counts, not raw response/prompt/image content. Settle known usage before parsing recognition, including billed refusals/malformed/incomplete responses. Known over-bound usage is recorded and freezes the account. Missing/uncertain usage retains the reservation and freezes dispatch.
8. Reconcile against the account's provider dashboard before/after the approved attempt. `record_reconciliation_reference` records evidence but DOES NOT treat manual amounts as verified billing, release reservations or unfreeze accounts. An authenticated provider reconciliation/import path is not available yet; unresolved attempts therefore remain blocked for human/provider review. No optimistic zero-cost refunds or retry after ambiguity.

## Current hard blocker: $0.25 maximum exposure

The official transport uses the documented 1,048,576-token context shared between input and output. Reserving 512 output tokens leaves at most 1,048,064 input tokens. Reviewed Standard rates give a conservative **$1.312256** token-cost bound before any other charges ($1.310080 input + $0.002176 output). The earlier $1.312896 reservation double-counted 512 context positions and has been corrected without changing the authorization limit. That exceeds **$0.25**, so the real transport CANNOT dispatch, even with flags, keys, account evidence and a permit. It independently checks this bound at the network boundary; a synthetic low-bound ticket cannot be used with the real sender.

A smaller provider-enforced/documented whole-request bound must be verified and code-reviewed before the first real test. Do not substitute a guessed pixel/byte-to-token multiplier. The token-count endpoint measures context and is not automatically a verified billing contract; its fees, media disclosure and cost relationship must be verified before any use. No preflight request was made. Existing illustrative ~1280px costs around $0.004/image are estimates, not admission guarantees. [Pricing](https://dev.meta.ai/docs/pricing-rate-limits), [token counting](https://dev.meta.ai/docs/token-counting).

## Local operator tools (no network)

Use `python -m scripts.meta_budget_admin --database /absolute/private/ledger.sqlite3 init`, then `attest-account`, `record-price`, `approve-first-test` with individually reviewed mode-0600 JSON evidence files matching `Evidence`, `Price`, `FirstPermit` schemas. `view` reports isolated account totals; `reconciliation-reference` only adds an audit reference. No resets, live calls, key creation or billing settings changes are implemented. Do not initialize a genuine account with a synthetic/assumed zero baseline. `.env.example` and `docs/budget/first-test.disabled.json` remain disabled/incomplete templates.

## Required human sign-off

Each account owner separately confirms credits/expiry/billing, gross usage, identity/key binding, grant eligibility and exclusive spend paths. Georgio and Amine review PR #7 and the live/financial/privacy changes. The image owner approves the exact synthetic image being disclosed to Meta under reviewed retention terms. The authorized spending decision-maker explicitly approves ONE request for ONE named account, fixed Standard model, verified maximum <=$0.25, <=512 output tokens, one in flight, no tools/Files/SAM/retries, and a short expiry. Additional $100 approval is separate and account-specific when applicable; no approval overrides $120. No human spending or account activation approval has been recorded by this task.

## Executed verification (2026-10-27)

228 maintained Python tests + 32 subtests passed; 3 isolated starter tests passed. Signed simulator unit suite: 22 passed. Default UI suite: 2 passed, 4 opt-in cases skipped (three physical-only, one live simulation); the separate local fake-provider Meta-consent UI case passed. Concurrent thread/process tests admit only one project permit. Fault tests cover dispatch crashes/timeouts, price/credit expiry, account/key isolation, HTTP failures, missing/over-bound usage, corrupt/locked databases and alert failures. Real sender cannot use a synthetic cheaper ticket. No actual Meta/GitHub notification calls were made by tests. See [implementation report](GUARDED_META_IMPLEMENTATION.md).

## Final cost investigation and conditional procedure

See [final readiness and one-request procedure](META_LIVE_READINESS_2026-10-27.md). Minimal reasoning and compact schema reduce unnecessary work without claiming a new image-token guarantee. Preflight counts are not accepted as billing evidence; no count or inference request was sent. Live activation remains blocked.
