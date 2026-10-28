# First real Meta camera test — October 28, 2026

The owner-authorized, exact-image request completed through the guarded
`OfficialMetaTransport` with HTTP 200 and `muse-spark-1.3` Standard. The model
identified water, read “WATER 250 mL”, and explicitly recognized the image as a
synthetic illustration rather than a real product. No physical iPhone camera
capture or real-product accuracy claim is established by this operator test.

Exactly one network-send claim and one provider request were recorded. The
provider response, usage, latency and request identifier are retained privately.
The backend process returned to mock immediately; persisted configuration remains
mock/false. The immutable permit is spent. The account remains frozen with the
token reservation held until independently verified final billing is available.
A successful response is not an invoice-finality guarantee.

Two local startup issues were resolved before the first network attempt:
the dedicated environment needed the already-existing backend session token,
and beverage initialization silently changed the shared financial authority to
WAL. The latter now preserves a financial database's existing journal mode.
The same authority was restored with SQLite checkpoint/journal-mode operations,
with all pre-existing table records and file identity verified unchanged. No
permit or attempt was reset. Local startup failures had zero ledger attempts
and did not send or retry a Meta request.

The runtime policy is documented in
[FIRST_CAMERA_RISK_POLICY.md](architecture/FIRST_CAMERA_RISK_POLICY.md).
The new policy was explicitly authorized by the account owner; Amine's prior
integration approval was reported by the owner, not represented as a new review
of this follow-up code. A review PR is provided separately; nothing is merged
or deployed automatically.

Validation: 515 pytest tests and 32 subtests passed, with the existing
Starlette/httpx deprecation warning. This includes 30 risk-policy tests,
the real sender with mocked HTTP, session restoration, financial journal
preservation, concurrency, timeout/expiry and invoice-overrun cases.
No Swift changes or new XCTest/physical-device run were performed.

