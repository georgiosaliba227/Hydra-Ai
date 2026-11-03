# Personal Wonder with the owner's accepted financial uncertainty

November 3, 2026. This completes the regular personal-analysis admission path;
the earlier one-use synthetic test remains a separate, consumed authorization.
The owner waived the eight legacy unresolved attempts and accepted unverified
provider charges "for all requests". Neither statement establishes invoice
finality, zero gross spending, a higher allocation or permission to transmit
unreviewed personal data. The newly completed ninth request was not part of the
legacy waiver and requires genuine finality before another paid request.

The owner also needs to collect actual calibration measurements and requested
Muse-generated simulated training data. Simulated training remains separate from
real personal history and independent measured-data evaluation. A bounded,
operator-only `synthetic_training_plan` purpose may use this same financial
authority after its gates pass; it must not create another ledger or direct
provider bypass.

## Additive policy and unchanged verified admission

Keep the strict verified `Evidence`, `ExperimentQuote`, numerical models,
personal fact/consent contracts and existing verified gateway unchanged. Add an
explicit `HYDRA_WONDER_FINANCIAL_POLICY=owner_accepted_risk` choice; the default is
`verified`. Unknown choices fail startup. The risk choice uses an absolute
`HYDRA_WONDER_OWNER_POLICY_FILE` draft/descriptor, the existing ledger/quote/result
path variables, and Georgio's server-only credential. No automatic fallback.

Introduce `OwnerRiskQuote`, `OwnerPersonalPolicy`, `OwnerPersonalAuthority` and
`OwnerPersonalWonderGateway` in small modules. `LiveConfig.read_quote()`,
`new_gateway()` and `readiness()` select their types. The regular trends,
workout and comprehensive routes use these hooks; v3 shares the comprehensive
installer. Disable the synthetic-scenario/assistant live route in personal-risk
mode. Existing saved results continue to replay while admission is blocked.

## Truthful authorization and finances

- Bind the existing account/key fingerprint, original $30 allocation and $120
  account cutoff, dated account/price observations, genuine notification and
  cross-ledger status references, standing personal-data authorization, owner
  legacy-waiver reference and accepted-extras reference. Never substitute a
  fabricated Amine review, verified-extra flag or invoice.
- A read-only operator prepare command writes a private, visibly incomplete
  draft. Missing references/status remain null/false. An authorization is
  recorded only with complete genuine references; the runtime may load an
  incomplete draft to show blocked readiness, but cannot reserve from it.
- Store authorization and per-attempt bindings as append-only events in the
  existing authoritative ledger. Keep every old row, amount, evidence record,
  permit, finality and the original frozen flag. Do not initialize/migrate a
  replacement authority or reset spending.
- Exempt only the eight explicit pre-test legacy attempt IDs, bound to their
  original identity and reservation metadata. New requests, including the
  ninth one-use test, require matching recorded finality. Refuse active sends,
  later financial failures, changed credentials, expired observations/quotes,
  malformed or missing ledger linkage, and duplicate payloads/retries.
- Reserve $0.25 of token exposure per request, only when the published-rate
  byte/input/output bound fits it. Count all previous holds conservatively
  against the same $30 allocation and account exposure; reject exposure reaching
  $75 until notification/checkpoint review. Credits never offset gross counts.
  Unverified extras remain explicitly unbounded and owner-accepted; these local
  counters are not a hard provider cap.
- Use one durable reservation and one-use network-send claim under the same
  SQLite lock. Recheck identity, policy, finality and exact payload at claim.
  The existing fixed-origin sender has no retries/tools/account rotation.
- Record usage-derived token estimates separately. Keep actual charge null and
  the full hold in `billing_pending` until genuine final charges are imported.
  Malformed usage, timeout, cancellation/crash and missing result keep the hold
  and stop later admission. Never resend a consumed payload after a save failure.
- Financial rows/events contain hashes, consent references and bounded request
  metadata, never raw measurements, drink descriptions or provider prompts.

## Existing personal endpoints and safe research purpose

Gateway methods `explain_trends`, `explain_workout` and `explain_analysis` use the
existing allowlisted payload builders, parsers, renderers and live result
constructors. Inputs are computed aggregate facts; raw HealthKit/measurement
requests never reach the transport. Every personal dispatch is bound to the
exact fresh in-app preview/hash/consent. Keep all numerical authority and saved
result export/deletion behavior unchanged.

The transport ticket validates the semantic purpose as well as payload hash,
input bound and credential. Supported purposes are `personal_trends`,
`personal_workout`, `personal_analysis`, and, only with its separate genuine
owner-reference, `synthetic_training_plan`. The last purpose is operator-only
and validates a fixed, versioned public/synthetic scenario-plan payload before
dispatch. No arbitrary prompt or synthetic training HTTP route is added.

## Readiness and native presentation

Add authenticated, read-only `GET /v1/wonder/readiness`. It performs no provider
request, financial write or permission change. Exact response:

```text
version: "wonder-readiness-v1"
configured: boolean
status: "disabled" | "blocked" | "ready"
account_id: "georgiosaliba227" | "aminealichaouche" | null
policy: "verified" | "owner_accepted_risk" | null
blocked_reasons: array of unique supported reason codes
all_charge_categories_verified: boolean | null
per_request_token_cap_micro_usd: 250000
```

Supported reasons: `live_disabled`, `owner_policy_not_recorded`,
`owner_policy_invalid`, `quote_expired`, `account_observation_stale`,
`cross_ledger_status_unverified`, `notification_delivery_unverified`,
`current_invoice_finality_required`, `request_in_flight`,
`financial_failure_requires_review`, `budget_exhausted`,
`verified_financial_checks_required`, `storage_unavailable`.

`ready` requires configured=true and no blockers; disabled requires
configured=false. Do not expose credential fingerprints, private paths, raw
account evidence, provider IDs or measurements. Under owner-risk mode,
`all_charge_categories_verified` is always false. Missing/expired evidence never
becomes verified merely because the backend is configured.

Personal previews keep their existing wire shapes and computed explainability,
but advertise live availability only when this policy's readiness passes. Do
not hide saved replay. The native app adds an explicit GET-only Settings
availability check with human-readable blockers; the detailed-analysis card
points there when live analysis is unavailable. It must not offer another paid
request as a workaround for unresolved state.

## Verification and activation

Test a disposable ledger with eight waived legacy attempts and the ninth pending
one: zero sends. Supply test-only genuine-shaped finality and complete refs,
then exercise all existing personal endpoints with fake transport, strict
grounding, one send and free replay. Cover races, duplicate hashes, old holds,
changed keys/waivers, cross-ledger/quote staleness, later errors, malicious output,
export/deletion, v3 and unchanged verified/default-off behavior. Include a
Simulator readiness/preview flow that remains blocked without financial writes.

Actual activation remains conditional on genuine ninth-request finality,
current cross-ledger/account references and exact personal-data consent. No
second paid request is authorized by engineering tests or a fabricated fixture.
