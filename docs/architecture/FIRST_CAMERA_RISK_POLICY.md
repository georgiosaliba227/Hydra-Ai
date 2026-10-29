# First camera request: accepted provider billing risk

Policy version: `georgio-first-camera-risk-v1`. Owner authorization: October 28,
2026, “FINAL META LIVE TEST AUTHORIZATION POLICY”, plus the owner's confirmation
that neither key was used in the preceding hour, all other use is stopped, and
disclosure consent includes the free-credit product-improvement terms.

This is a one-time exception for Georgio's first project camera attempt. It
does not authorize Amine, another image, recurring inference, retries, account
fallback, tools, Files, SAM, or automatic top-ups. The exact normalized image is
`c7bbab98d7ee9a1c41e4f6cb5a2dc62b336a81f717893995ce8cc7cf9a33edd8`.
Legacy $0.25 and dual-test permits retain their existing rules.

## Financial contract

Three values stay distinct:

- Token reservation: full-context 1,048,064 uncached input tokens and at most 512
  combined reasoning/output tokens at Muse Spark 1.3 Standard rates: $1.312256.
- Intended authorized spend: $2. Admission checks use this larger amount.
- Total provider charge bound: unknown, represented by null. The owner's explicit
  acceptance of residual charges is recorded separately; unknown extras are
  never represented as zero or independently verified.

The account evidence must contain authenticated current credits, known gross
usage, known pending usage, credential association, stopped alternate spending,
reviewed disclosure terms and a notification delivery reference. This exception
reviews the actual promotional-credit terms; it makes no new claim about either
developer's hackathon eligibility or the origin of the grant. This exception
refuses nonzero/unknown pending usage and outstanding requests. Billing snapshots
expire within 15 minutes and are revalidated through the network-send claim.
The $2 admission amount must leave $30 of available credits. Gross admission
still rejects reaching $120 and requires separate approval at $100; $75 queues
notices to both developers. None of these controls guarantees a provider charge
cap or prevents an unexpected provider overrun.

The authenticated dashboard can lag by an hour. Record the observed reporting
range and distinguish gross usage from balance due after credits. An owner
confirmation of stopped activity bridges the reporting lag; never infer zero
pending activity from a displayed $0 balance due. Unknown credit expiration may
remain null only under this fresh-snapshot policy; do not invent an expiry date.

RiskEvidence and RiskPermit are separate typed records. Evidence explicitly
records unverified additional charge categories and a null extra-charge bound.
The permit binds the serialized account evidence hash, exact image, account,
price version, owner/disclosure/review references, risk acceptance and expiry.
It cannot be imported if any project permit or attempt already exists. No
existing account baseline, permit, spent flag or attempt is reset. The existing
SQLite schema, atomic reservations and one-use dispatch tickets are retained.

## Execution and reconciliation

`scripts.meta_camera_once` requires an explicit execution flag and an existing
immutable risk permit. It reads the existing private disabled backend config,
constructs the guarded backend in one dedicated process and invokes its real
gateway exactly once. It does not expose a server or exercise the physical
iPhone UI. The persistent config stays mock/false. Its finally block restores
mock mode even on provider errors. The private result file is exclusively
created before dispatch; it contains the bounded provider reply, parsed result,
latency and ledger observation, never the submitted image, prompt or keys.

After valid provider usage, token cost is recorded separately and the attempt
stays `billing_pending`, with its reservation held and the account frozen.
Valid beverage recognition can be returned while billing remains unresolved.
Errors, missing usage, crashes and timeouts keep the hold; no retry is authorized.
Known provider request IDs survive missing usage.

Only independently verified request-level final charges may be imported using
`reconcile-risk-invoice`. Final gross charges may differ from token arithmetic.
An overrun must be recorded truthfully, including charges over $2 or the observed
credit balance. Reconciliation never unfreezes the project, resets the permit
or enables a second request. Missing provider finality stays unresolved.

Operator commands: `attest-risk-account`, `record-price`,
`approve-risk-test`, `reconcile-risk-invoice`, all through the existing private
`scripts.meta_budget_admin` interface. These commands record evidence, not
authenticate its truth. Never import synthetic test fixtures into the authority.

## Validation

Synthetic tests cover the fixed image, account isolation, pending/unknown/stale
billing, credit reserve, $75/$100/$120 gates, concurrency, delivery failure,
timeouts, crashes, expired dispatch, token-bound substitution, immutable permits,
known request IDs with missing usage, actual overrun reconciliation, read-only
preparation, and an official-transport runner with mocked HTTP that restores
mock mode. They do not establish a real provider result or invoice finality.

