# Owner-authorized single synthetic Wonder test

November 3, 2026. Georgio explicitly directed the agent to continue in Simulator
and ignore the prior unresolved billing attempts. That overrides the prior
finality wait for this one test only. It does not make those attempts final or
establish zero gross usage. The owner separately accepted unverified provider
charges "for all requests" after reviewing the fixed test's $0.059960 published
token bound. This acknowledgement also applies to future requests; allocation
and account limits are unchanged. The operator authorization implemented here
still consumes only one request. It does not enable ordinary ongoing admission.

## Authorization and accounting

Implement an operator-only `wonder-owner-once-v1` policy in the existing private
ledger. Leave ordinary camera/Wonder admission unchanged. Preserve the original
account evidence, frozen flag, permits, attempts, reservations and finalities.
Never manufacture current Evidence, final charges or Amine review references.

One append-only authorization event binds Georgio's existing key fingerprint,
one fixed synthetic comprehensive-analysis payload, current published token
prices, expiry within one hour, the exact prior financial snapshot, the owner's
waiver reference and explicit acceptance of unverified extras. Atomically consume
it with one new attempt and a $0.25 token reservation. No second authorization,
retry or automatic fallback. Existing reservations count toward the $30 experiment
and $120 account ceilings; reject exposure reaching $75 to avoid any notification
exception. Refuse unexpected financial changes and any genuinely active send.

Published rates are $4 input/$20 output per million tokens. The fixed payload's
byte-based input bound is 4,750 tokens and output maximum 2,048 tokens, giving a
published-token upper bound of $0.059960. These are token bounds, not a guarantee
about unverified provider extras. Never mark all charge categories verified.

Use the existing fixed-origin transport with a dedicated one-use ticket. Record
response usage and provider ID privately. Keep actual/final charges null and the
account frozen. A reply remains billing-pending; missing/malformed usage or a
timeout remains unresolved. Preserve the full reservation in either case. A
validation failure never permits another send. Synthetic replies may be retained
privately for validation without uploading any personal records.

## Fixed scientific input and result

Build only `WorkoutForecastInput(mode="synthetic_demo",
timezone="America/New_York")`, with no user logs and generated time
`2026-11-03T12:00:00Z`. Use `build_analysis`, `wonder_analysis.build_facts` and
`analysis_payload`. Exact payload hash:
`12ef839f44757b452034632ef91c50ff44455e6c02c99104230f4c46d02ab34c`.
Retain `synthetic_demo` throughout. Validate the eight ranked sections using
`parse_selection` and `checked_result`; do not pass synthetic observations
through the personal live-result constructor.

Save an owned 0600 result file in an owned 0700 directory. Public API replay is
read-only, owner-authenticated, default unavailable, and never dispatches:
`GET /v1/wonder/owner-once/result`. Configure only an absolute private result path
with `HYDRA_WONDER_OWNER_ONCE_RESULT`; no HTTP authorization or run endpoint.

The exact response envelope is:

```text
version: "wonder-owner-once-result-v1"
mode: "synthetic_demo"
generated_at: UTC ISO8601 string
result: existing wonder_analysis.checked_result shape
receipt:
  account_id: "georgiosaliba227"
  attempt_id: canonical UUID
  model: "muse-wonder-1.0"
  payload_sha256: fixed hash above
  input_tokens, output_tokens, cached_tokens: nonnegative integers
  usage_derived_cost_micro_usd: nonnegative integer (not a final charge)
  token_reservation_micro_usd: 250000
  published_token_bound_micro_usd: 59960
  provider_invoice_final: false
  provider_extras_bounded: false
  state: "billing_pending"
```

Only a valid, completed, grounded reply with valid usage produces this envelope.
The read endpoint reconstructs/validates the saved result; missing, changed or
malformed records return unavailable without financial changes.

The native viewer fetches this endpoint explicitly, labels it a real Muse Wonder
response on simulated data, reconstructs section text from existing vetted
scaffolds, and states that the final invoice is unverified. It must never label
the invented observations as the user's history, save them to calibration, or
loosen validation of ordinary personal results. Repeated viewing makes no paid
request. The one-use exception does not enable continuing live personal analysis.
