# One physical camera request — owner exception, November 1, 2026

Policy `georgio-physical-camera-once-risk-v1` records the owner's explicit chat
approval of the exported beverage photo, free-credit terms, $2 intended maximum,
unknown extra provider charges, and proceeding despite the original unresolved
camera bill. The owner separately confirmed that all other account use is stopped
and no other inference is pending. This exception applies once only. It provides
no absolute provider charge guarantee and no authority for another image or call.

`PhysicalCameraLedger` appends the new immutable approval as an event in the
existing authoritative ledger. No schema migration, reset, account unfreeze,
replacement evidence, old-permit update or invoice-finality claim occurs. It
binds the exact normalized image and complete provider payload fingerprints,
original attempt's full row fingerprint, original account/key identity, fresh
price and billing evidence, notification reference and explicit owner acceptance.
Only the unchanged, named original billing-pending attempt is excepted. Any
additional attempt or another frozen account denies admission.

The full-context token reservation remains $1.312256 at the currently verified
Standard rates and 512 combined output tokens. The $2 intention is used for
admission. The original $1.312256 hold remains counted. Admission additionally
holds the maximum $85 allocation permitted on the other Mac, preserving the
account-wide cushion despite that ledger being inaccessible. Fresh rounded
dashboard observations are recorded as observations and conservative admission
bounds, never precise invoice costs. Credits do not offset gross accounting.
The $100 checkpoint refuses this exception rather than assuming further-spend
authority; the $120 operational cutoff and $150 allocation remain unchanged.
Notices to both developers remain required at $75 measured gross exposure.

Reservation, dispatch marking and the transport's final send claim each use
the existing SQLite atomic transaction. One approval and one reservation event
are permitted. The existing exact `DispatchTicket` is consumed before the
official transport's sole network operation. Approval expiry, account/key,
payload fingerprint, original hold and notice delivery are rechecked. A crash,
timeout or lost response never releases money or permits a retry. The original
gateway and all default app processes retain their existing fail-closed policy.

The explicit operator server reads the existing private legacy credential file
into process memory, never creates a new provider-key file, and uses the original
financial authority alongside a separate local test-beverage database. The phone
receives only the existing backend session token. Only its owner can access it.
No public arm route exists. One process lock protects the request, and every
success or failure restores mock mode before returning the response. Provider
reply, usage, identifiers and latency are retained privately; photos, request
bodies, prompts and credentials are absent from server logs. Confirmation still
requires the actual consumed quantity before hydration logging.

Validation: 134 focused nonbillable tests passed, including 24 new tests for
this policy and the HTTP service. They cover preserved history/freeze/old spent
permit, image/payload substitution, wrong account/key, concurrency, restart,
expired dispatch, credits/checkpoints, fake official HTTP, timeout holds and
automatic return to mock. The final broad suite run had 1,096 passing tests, 32 passing
subtests, one skip and one unrelated existing workout-date validation failure;
the same failure was reproduced with the unchanged main app module. It is not
reported as an all-green full suite. No Swift source changed.

One real provider request was subsequently made using the approved physical
camera export through the operator gateway. The phone submission had first
failed admission without any reservation or provider send. The operator request
received HTTP 200 with provider status `incomplete` and reason
`max_output_tokens`; the strict parser accepted no recognition or logging
receipt. The one authorization is consumed, both reservations remain held, and
the authority stays frozen. Private evidence preserves response, usage, latency,
identifiers and exact image fingerprint. This run establishes provider receipt
of a physical camera export, not a completed in-app recognition flow.

The test also exposed retry advice being computed after the one-use process
returned to mock. The HTTP error handler now uses the original request mode:
failed live requests continue to report `retryable: false` after disarming.
Focused HTTP regressions verify both provider failure and stale live submissions.

## Separately approved 1,024-token retest

The owner subsequently authorized exactly one additional request for the same
photo, 1,024 combined output tokens, $2 intended spend and possible extra charges,
retaining both unresolved holds. `georgio-physical-camera-retest-risk-v1` has its
own immutable approval/reservation event names. It does not renew either old
permit. Both previous attempt rows and the previous physical permit events are
fingerprint-bound and must remain unchanged. Any additional attempt denies this
exception. The original freeze stays set.

The trusted `RetestTransport` builds and validates the fixed 1,024-token payload;
HTTP clients cannot select this transport or supply a cap. Standard remains the
same fixed origin, one-use ticket, no tools and no automatic retries. Reserving
1,047,552 input tokens plus 1,024 combined output tokens costs $1.313792 at the
verified Standard rates, within the $2 intended amount. The combined retained
reservations after admission are $3.938304. The $85 other-Mac allocation hold,
credit cushion, notification and account cutoffs remain enforced.

Only this new reservation can settle usage above 512 tokens up to 1,024. All
default transports, previous permits and ordinary ledger settlement retain the
512-token cap. An incomplete or over-limit response keeps the new hold; it never
causes another send. The same process guard restores mock mode immediately.
