# Issue #8 — live activation evidence review

Reviewed 2026-10-27 against merged main `424f9fe` (PR #7). **Blocked pending provider evidence and human approval.** This is preparation only. No Meta API call, billing change, credential probe, token-count request or support message was made. Both accounts remain separate; live inference remains disabled.

## Preflight finding

[Meta's counting guide](https://dev.meta.ai/docs/token-counting) and [endpoint reference](https://dev.meta.ai/docs/api-reference/responses/count-input-tokens) document `POST https://api.meta.ai/v1/responses/input_tokens`. It accepts supported Responses fields, requires model/input and returns an integer count. It tokenizes initial rendered context, including media; it does not generate, execute hosted tools, store a response or record generation usage. It validates supported initial request structure, not later tool iterations. Counts depend on the selected model and deployment. History is resolved through `previous_response_id`; conversation resources are unsupported. Hydra forbids both history and tools.

**Non-generating: yes. Safe/zero-charge preflight for Hydra today: not established.** No generation usage does not establish no charge of any kind. The reviewed reference has no explicit zero-price promise or endpoint-specific RPM/TPM/concurrency allocation. Other providers' compatible endpoint policies are not evidence for Meta. Do not call it as an authentication probe.

[Pricing](https://dev.meta.ai/docs/pricing-rate-limits) publishes team-wide limits, shared across keys; it does not specify a dedicated counting quota. Obtain counting endpoint quota/error/retry semantics from Meta. Hydra's no-retry policy remains in force regardless of generic backoff guidance.

## Conflicting billing descriptions

The counting guide/reference include injected scaffolding in rendered counts and distinguish occupancy from billed usage. The pricing page's rate-limit note instead says injected steering is excluded from both usage and counting endpoints. This conflict must be resolved by Meta for the selected account/model/deployment. Neither description provides a binding count-to-invoice upper-bound guarantee. A count is therefore not accepted as a billing authorization or a replacement for the transport's conservative bound.

## Privacy of a second upload

Counting transmits the image and prompt to Meta even without generation. No stored response is not a promise that request content, safety logs or telemetry are never retained. [Terms §§4–5](https://dev.meta.ai/legal/terms-of-service), last updated October 9, describe content/usage retention and Standard processing; Standard excludes model training but is not a blanket zero-retention arrangement. Review endpoint-specific retention, deletion, subprocessors and applicable processor terms with each owner. Obtain image-owner consent explicitly covering counting and inference as separate disclosures. Use an owned synthetic beverage image without people, location or health information; strip metadata. No HealthKit records, secrets, request bodies or images belong in support messages, GitHub or logs. `store:false` cannot substitute for this review.

## Defensible reservation method — conditional design, not implemented

The current real transport returns `1,048,576 − 512 = 1,048,064` as its input bound. Gateway quotation and sender ticket validation enforce the same bound. The account ledger rounds token cost upward in integer microdollars, adds the independently verified extra-charge maximum, reserves atomically, and retains unresolved attempts. At the currently published Standard rates this reserves **$1.312256 before additional charges**, so it cannot pass $0.25 admission. Existing code is intentionally unchanged.

A smaller bound is defensible only with one of these provider-backed mechanisms:

1. A binding, authenticated request quote or enforced request dollar/input ceiling that rejects before exceeding its all-inclusive gross maximum; or
2. Written provider assurance that, for the exact canonical single-shot payload, billable input cannot exceed a measured count plus a specified finite adjustment. It must cover image preprocessing, schema/prompt overhead, internal invocations, deployment changes and the interval between counting and inference. A model alias alone does not pin preprocessing. If Meta cannot pin versions, require an enforceable quote expiry or drift-safe worst-case bound.

Required calculation in microdollars:

`R = ceil((I_bound × 1,250,000 + 512 × 4,250,000) / 1,000,000) + E`

`E` covers every additional gross fee, tax, rounding/minimum charge and any authorized preflight exposure conservatively allocated to this test. Use uncached rates; credits never reduce `R`. Provider evidence must also confirm the 512 limit covers every billable reasoning/output token and bound failed/partial/timeout/internal-retry charges. Reject unknown categories. For `E=0`, maximum input is **198,259 tokens** (`R=250,000`); 198,260 requires 250,001 microdollars. Positive `E` lowers that threshold. This arithmetic is not evidence that any image qualifies.

Before dispatch, reserve `R <= 250,000` against only the chosen account and require `existing gross + settled + unresolved reservations + R < 120,000,000`. Preserve $75 notices to both developers, $100 account-specific further approval and the $150 absolute ceiling. Never pool credits or fall back to another account.

If counting is proven free and separately authorized, it can precede the sole inference. If it has any charge, do not silently add it: current authorization does not permit extra billable calls. Require a separate explicit scope decision, include its exposure, and reconcile it before inference. A free count still needs disclosure approval. No endpoint is added until these conditions are satisfied.

Future implementation must bind authentic evidence to account identity, credential fingerprint, canonical payload/image hashes, model/deployment, price/policy versions and expiry; reject client counts, stale/mutated payloads, deployment drift, missing evidence and unsupported fields. Validate the same bound in gateway and sender. Repeat mock-only race/crash/timeout, mutation, expiry, over-bound and reconciliation tests before review. Usage from a successful sample or invoice can validate reconciliation, but cannot retrospectively authorize a first request or guarantee the next one. A local timeout/cancellation is not a billing cap.

## Evidence each account owner must provide

Georgio (`georgiosaliba227`) and Amine (`aminealichaouche`) each provide a separate dated evidence packet, independently reviewed by both developers. Use authenticated dashboard exports/screenshots and provider support references privately; retain public summaries and opaque references only. Never paste keys or private billing/account identifiers into GitHub. A checkbox or self-authored JSON is an attestation, not independent provider verification.

| Required evidence, separately for each owner | Acceptance requirement |
| --- | --- |
| Provider account/team/project identity and ownership | Authenticated identity, authority to use it, and private mapping from selected server key fingerprint to that exact provider account; no billable probe |
| Credit/grant record | Current balance, expiry/timezone, allocation source, covered models/fees, hackathon/startup restrictions, overage behavior; reported $150 is unverified |
| Gross usage baseline | All historical gross charges before credits, pending/delayed usage and outstanding requests across every key/project in the billing scope; dated reconciliation reference, no assumed zero |
| Billing/rates | Exact Standard model access, applicable account rates/currency, taxes/fees/minimums/rounding, payment/prepaid/overage terms, no automatic top-ups; alert is not a hard cap |
| Provider bound and reconciliation | Written guarantee or binding quote satisfying the method above, validity/deployment scope, counting fee/quota terms, failed/lost-response charge bounds, authenticated request-ID billing records and finality timing |
| Privacy review | Current Standard designation, counting and inference retention/deletion terms, processor/subprocessor review and image-owner consent covering applicable disclosures |
| Operational custody | One authoritative private durable gateway ledger, exclusive controlled key use, inventory of alternate spending paths and outstanding work, both-developer notification delivery; no active ledger copies |
| Human approvals | Both developer code/privacy/financial reviews; that account owner's explicit authorization; spending authority's one-request approval; exact-image consent; references with expiry bound to selected account/image/price/policy |

Only the selected account can receive the project-wide one-use permit. The other stays disabled and unverified until its own packet passes; its owner must not share credentials to combine accounts. Raw keys stay server-side under approved custody. Any key-sharing arrangement must be reviewed against Meta Terms §3.1. Provider alerts and invoice payment thresholds cannot substitute for local admission bounds ([spend-alert help](https://dev.meta.ai/help/billing/spend-limit-alert)).

## Next concrete step

Each owner collects their account packet without API calls. Review the [unsent Meta inquiry](META_BILLING_SUPPORT_INQUIRY.md), including the conflicting counting descriptions, then obtain explicit authorization before sending it through the selected owner's support session. Obtain Meta's written all-inclusive bound and counting charge/privacy/quota confirmation. Only after evidence passes, implement/review the bound at both gateway and sender, run fault tests, and obtain an expiring, exact-account/exact-image one-request approval. Keep `HYDRA_AI_MODE=mock` and `META_BILLABLE_REQUESTS_ENABLED=false` throughout preparation. Do not raise $0.25 or $120 to bypass the blocker. Issue #8 remains open.

## Validation of this preparation change

Documentation only; no runtime, iOS or configuration changes. `python -m pytest tests/recognition -q`: **120 passed**, one existing Starlette/httpx deprecation warning. `git diff --check` passed. No new iOS, physical-device, provider billing or live recognition test was run. Existing PR #7 verification is historical evidence, not a new result.
