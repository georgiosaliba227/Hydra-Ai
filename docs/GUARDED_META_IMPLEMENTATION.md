# Guarded Meta implementation and account update — 2026-10-27

> Policy update: [dual controlled test preparation](META_DUAL_TESTS.md). The new $2/account policy is proposed and disabled pending exact approvals; older $0.25 statements below describe legacy policy/history, which remains enforced for legacy permits.

Implementation on existing branch `codex/meta-beverage-recognition`, PR #7. No duplicate PR, deployment, live Meta request, account activation, billing setting change or automatic merge. No real images were sent to Meta. No genuine financial authority/baseline/approval was initialized; tests use disposable synthetic evidence and fake providers.

## Implemented files / behavior

- `backend/meta_provider.py` and `backend/meta_images.py`: metadata removal and official Responses format, strict structured category/brand/product/container/confidence fields, fixed HTTPS origin/path, no redirects/proxies/retries, one JPEG, 512 output-token cap, no tools/Files/SAM/history/background. Strict duplicate-field/non-finite JSON rejection, refusals/incomplete/malformed/API failure handling. Actual sender requires a persisted exact-payload, one-use dispatch ticket with matching account credential and its own token upper bound. No model nutrition.
- `backend/meta_accounts.py`: two independent logical ledgers in one authoritative private SQLite file, account/provider/key binding, independent evidence/credits/expiry/gross accounting, no pooling or rotation, immutable per-attempt price/model snapshots, UTC events, atomic singleton first-test permit, credit-exhaustion/75/100/120/150 checks, persistent dispatch/send state, trusted transport usage settlement and fail-closed reconciliation. Project totals are incomplete/unknown when an account is unverified; credits are not added together.
- `backend/meta_gateway.py`: every actual send requires approval, matching image hash, a verified <=$0.25 maximum, a reservation, delivered threshold notices and a one-use ticket. One project-wide first request; no second request/retry. Unsuccessful output is accounted before parsing; missing usage/crashes keep full reservations. Selected account/credential never falls back. GitHub notices target both developers, require delivery receipts and block dispatch on delivery failure. Tests never invoke the real notifier.
- `backend/app.py`, `recognition.py`, `schemas.py`, `meta_budget.py`: authenticated capability/spending/notices reads, live/mode consent validation, sanitized non-retryable live errors, successful settled recognition receipts checked before log provenance, backward-compatible manual fingerprints, legacy shared-ledger bypass disabled in v2. Default remains mock/false.
- iOS camera/result/confirmation, HTTP service, pending request/store and permission/Settings text: explicit Meta disclosure and retention wording; mode-specific labels; no automatic retry; mode mismatch rejected; live results require recognition IDs; confirmed receipt survives pending-save retry; no health/location export. No provider keys in iOS.
- `scripts/meta_budget_admin.py`, `.env.example`, `docs/budget/first-test.disabled.json`: private local evidence tooling and disabled templates. No network/admin HTTP endpoints, resets or unverifiable cost-based refunds. Account evidence/approvals are operator-recorded human attestations; the software does not claim to authenticate billing dashboards or human review truth.
- Tests: mocked provider bodies, concurrent processes/threads, interrupted send/timeout, provider errors/refusals/incomplete/malformed outputs, missing/over-bound usage, pricing changes/expiry, exhausted credits, account/key separation, failed reservations, corrupt/locked DB, missing credentials, notices, one-use tickets, live receipts/provenance and iOS consent behavior.

## Hard financial blocker, intentionally enforced

Follow-up cost review corrected the original $1.312896 reservation: the 1,048,576-token context is shared. The conservative bound is now 1,048,064 input tokens plus <=512 output tokens, costing **$1.312256 before any other charges** at reviewed public Standard prices. It exceeds the preserved **$0.25** first-test ceiling. Both gateway and actual network-ticket checks refuse dispatch. Flags, a key, a low-bound synthetic ticket or a human approval reference cannot bypass that bound. A smaller provider-backed bound or separately reviewed, verified preflight accounting method is required; no guessed pixel multiplier is accepted.

Public pricing remains $1.25/M input, $0.15/M cached input and $4.25/M output. [Pricing](https://dev.meta.ai/docs/pricing-rate-limits), [Responses](https://dev.meta.ai/docs/protocols/responses), [structured output](https://dev.meta.ai/docs/structured-output), [token counting](https://dev.meta.ai/docs/token-counting). Approximate image costs are not verified maximum exposure. No token-count/authentication probe was sent.

## Account verification / approvals still required

Both developers separately report $150 allocations. For EACH account, remaining balance, expiry, gross usage, payment/overage terms, exact model access, credit coverage, grant/hackathon eligibility and exclusive key custody remain independently unverified. No combined $300 authorization is inferred. Each account has a $120 operational cutoff and $150 absolute ceiling; $100 further approval and $75 notices are account-specific. Public event material was reviewed; individual participant/grant evidence is still required. No terms were accepted or payment settings changed.

Before a real request: resolve the cost-bound blocker, verify the selected account and all alternate spend paths, review notification credential/permissions and account reconciliation operations, obtain Georgio and Amine's code/privacy/budget review, selected account owner's explicit authorization, image-owner consent for the exact synthetic image, and spending authority's explicit one-request approval (named account, image SHA256, price version, <=$0.25 gross maximum, <=512 output tokens, one in flight, no retries/tools/Files/SAM, short expiry). Additional approval is required if that account reaches $100; $120 cannot be overridden. Other accounts need their own authorization; changing keys/accounts is not a retry strategy.

The program cannot constrain direct spending through keys outside its gateway. Exclusive key custody and retiring other spend paths are human/account operational evidence, not a flag. Unresolved bills cannot be cleared with caller/operator-supplied usage figures: the available reconciliation-reference command audits evidence only and leaves dispatch frozen pending authoritative provider reconciliation. First-test permits cannot be reset or automatically renewed.

## Verification

- Maintained backend/domain suites: 228 passed + 32 subtests; existing Starlette/httpx deprecation warning.
- Preserved starter suite: 3 passed from its own directory.
- Signed iOS simulator unit suite: 22 passed (includes live-consent refusal before network, live receipt validation and pending payload encoding).
- Mock-backend UI regression: 2 passed; physical-only cases skip in simulator runs.
- Live-mode UI simulation: 1 passed against a loopback server using ONLY an injected fake Meta transport and generated test image. Verified both consents, Meta label/receipt and 125 mL confirmed daily contribution. The test runner refuses real/billable servers for this mode. Initial consent-control scrolling/tap issues were fixed in the test harness; no failed iteration is counted as a pass.
- No new dependency, live accuracy/billing verification or new physical-device live-consent test is claimed. Earlier physical mock testing remains historical evidence in PHYSICAL_IPHONE_TESTING_2026-10-27.md.

Follow-up investigation, evidence, additional both-account tests and the conditional first-test procedure: [final readiness report](META_LIVE_READINESS_2026-10-27.md).
