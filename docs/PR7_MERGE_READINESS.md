# PR #7 review and next-milestone checklist

Reviewed 2026-10-27: full feature diff at `87aedfc` against remote `main` (`9c73ecb`), including the original camera/mock workflow and guarded integration. Review outcome: **no merge-blocking defect found for a human-reviewed merge with the existing mock/false defaults. Not approved for live activation, paid inference, deployment or automatic merge.** This is a source/local-test review, not a penetration test or provider-billing certification.

Cleanup follow-up: the two original iOS findings below are now implemented with regression coverage; financial controls/defaults are unchanged. Final cleanup verification is recorded in the follow-up section. The original source-review reference above remains historical.

## Findings and scope

| Area | Finding / consequence |
|---|---|
| Security | `/v1` authentication, bounded bodies/JPEGs, extra-field rejection, no remote image URL fetches, fixed TLS provider origin, no redirects/retries, sanitized API errors. Provider keys are server-only; no new dependency. Test credentials/images are synthetic. No remotely callable budget admin/settlement route. |
| Budget | Separate account baselines, credits, expiry, key binding, reservations, usage and notices in one authoritative SQLite file. Atomic admission, one immutable project-wide permit, per-account $75/$100/$120/$150 gates and unresolved-charge blocking. Real sender rechecks the exact-payload one-use ticket and its own over-cap bound. Mock mode never constructs a real provider transport or notification sender. |
| Failures/reconciliation | Reservations persist after crash/timeout; known usage is accounted before output parsing. Missing usage or over-bound charges freeze spending; manual evidence references do not release funds. Notice failures leave durable pending records. Authenticated provider billing reconciliation remains a live-activation dependency. |
| API compatibility | Existing manual requests and idempotency fingerprints remain compatible; tests replay pre-Milestone-2 pending records. New confirmation fields are optional for manual logs; confirmed photos require explicit capacity/consumption. Existing database tables require no destructive migration. New capability and financial reads are authenticated. |
| iOS/privacy | Camera denial/manual fallbacks, photo selection, consent gating, metadata redraw/strip, uncertain candidates, user correction, confirmation and pending-save persistence remain intact. Separate Meta consent and settled receipts are tested with fakes. HealthKit stays on device; no zero-retention claim. Release build excludes DEBUG photo fixtures. |
| Regression/test limits | All maintained backend/domain suites and starter suite pass; simulator unit/UI checks pass. No new physical-device or real-provider test. No CI workflow/check is configured/reported. Existing one-user trusted-local-network prototype restrictions remain; this review does not authorize public deployment. |

### Original findings — resolved in cleanup

- **R1 — distinct candidate row identity.** `ios/HydraAI/Features/Camera/RecognitionResult.swift:17` uses beverage identity as the SwiftUI ID. Valid live alternatives can share the same product name while differing in capacity or uncertainty; `ForEach(result.candidates)` then receives duplicate IDs. Use stable per-response candidate IDs or indexed rows and test duplicate-name selection. Current mock scenarios contain at most one candidate. Resolution: a stored client-only UUID now identifies each decoded/created candidate, including identical alternatives, and survives view updates/value copies without changing wire fields. Unit coverage verifies distinct/stable IDs; a fake-provider UI regression selects both same-name alternatives and checks their capacities.
- **R2 — mode-aware header.** `ios/HydraAI/Features/Camera/CameraCaptureView.swift:174` always says “try mock analysis,” including configured Meta mode. The analysis button, source/result labels and separate Meta consent are accurate; update this header and test it before activation. Resolution: shared mode-specific wording now drives the header, source caption, analysis button, result and confirmation labels. Unknown/unverified mode gets neutral wording. Unit and mock/fake-provider UI regressions cover these states.
- Private ledger-directory ownership, all alternate API-key spending paths, genuine approval evidence, retention terms and authoritative billing reconciliation require operator/provider verification before live use. A mode flag or an attestation string cannot independently prove those facts. Do not copy a ledger to establish another authority.

The original review made no cost optimization or production iOS changes; the subsequently authorized cleanup implements R1/R2 only. The recognition contract's historical mock-only wording was clarified to point unambiguously to the implemented guarded extension.

## Executed verification

| Check | Actual result |
|---|---|
| Maintained Python suites | 228 passed + 32 subtests; existing Starlette/httpx deprecation warning |
| Starter Python suite, separate directory | 3 passed |
| Signed simulator unit suite, iPhone 18 Pro / iOS 27 | 22 passed |
| Mock-backend UI suite | 2 passed; 4 skipped (three physical-only and one separately run fake-live case) |
| Separate loopback fake-provider consent UI | 1 passed; real Meta and notification transports forbidden |
| Release simulator build | Passed, ad-hoc signed; no new physical build/install |
| Diff/main compatibility | `git diff --check` clean; remote main is an ancestor; GitHub reported CLEAN/MERGEABLE before documentation commit |

UI runs use generated synthetic data and the simulator-only verbose-diagnostics workaround. Assertions and result bundles remain enabled. No image, count request, authentication probe or inference went to Meta; no billing/account settings changed.

## Provider-backed billing evidence

Official pages were rechecked without authenticated account/API calls. No new evidence establishes a guaranteed <=$0.25 whole-request gross charge. The existing $1.312256 conservative token reservation remains unchanged and above the limit; unverified other charges independently block admission. No typical image cost, pixel formula or count result was promoted into an authorization guarantee.

| Topic | What the official material establishes | Remaining gap |
|---|---|---|
| Image input | Inline JPEG via `input_image` is supported; image-token contribution varies with preprocessing/model/resolution. Image guide offers approximate examples and recommends preflight estimates. | No enforced resolution-to-billable-token maximum for the exact deployed request. [Image guide](https://dev.meta.ai/docs/image-understanding) |
| Counting | Count endpoint tokenizes rendered context including media/template. Dedicated guide separates accounting usage from context occupancy; hosted tools can accumulate usage across iterations. | No explicit guaranteed billing ceiling/validity contract for our exact tool-free request, nor independently verified count-call fees/retention. [Counting guide](https://dev.meta.ai/docs/token-counting) |
| Output/context | `max_output_tokens` includes reasoning and visible output and shares the context window with input. | An output cap alone does not cap total gross charges at $0.25. [Responses](https://dev.meta.ai/docs/protocols/responses) |
| Model/pricing | Standard ID `muse-spark-1.3`; public rates $1.25/M input, $0.15/M cached input, $4.25/M output. Search costs extra; generated images and SAM have separate pricing. No tools/image generation/SAM are in Hydra's request. | Confirm selected account's effective rates and all fee/tax/internal-processing categories. Do not apply generation/SAM image prices to Spark image understanding. [Pricing](https://dev.meta.ai/docs/pricing-rate-limits) |
| Self-service controls | Spend alerts email the account owner and do not stop usage or remove overage liability; payment thresholds trigger collection, not admission denial. | No self-service atomic gross hard cap documented. [Alerts](https://dev.meta.ai/help/billing/spend-limit-alert), [billing](https://dev.meta.ai/help/billing/api-bill) |
| Other billing arrangements | Terms §13.2(iii) mentions a maximum spending limit for invoice billing; §13.1 makes account rates/taxes relevant; §13.3 says promotional credits can expire. | No evidence either developer is eligible/enrolled, no concurrency/overshoot guarantee, no per-request quote, and no expiry/coverage proof for either account. This is a question for Meta, not a new safeguard or permission to change billing. [Terms](https://dev.meta.ai/legal/terms-of-service) |

The documentation therefore does **not yet establish a reliable pre-dispatch all-inclusive bound within our authorization**. The image-guide/counting-guide distinction and invoice-limit semantics need provider clarification. A concise [Meta support inquiry](META_BILLING_SUPPORT_INQUIRY.md) is drafted and **not sent**; sending requires the owner's separate instruction.

## Next milestone checklist

### 1. Code safe to merge with live inference disabled

- [x] Review the full branch against main for security, privacy, contract and persistence regressions.
- [x] Keep `HYDRA_AI_MODE=mock`, `META_BILLABLE_REQUESTS_ENABLED=false`, blank selected account and blank provider keys in committed defaults.
- [x] Preserve independent account ledgers, no pooling/rotation, all thresholds, one-request $0.25 gate and no retries.
- [x] Run backend/domain/starter tests, iOS unit tests, mock UI and Release build; record opt-in limitations.
- [x] Complete the separate fake-provider UI check for this review.
- [ ] Amine and Georgio review the latest PR and any concurrent changes; a human decides whether/when to merge. Merge does not authorize activation or deployment.

### 2. Account and billing verification — never pooled

| Required evidence | georgiosaliba227 | aminealichaouche |
|---|---|---|
| Remaining $150 credits, provider/team identity, expiry and coverage | Owner reports $150; independently unverified | Owner reports $150; independently unverified |
| Gross baseline, unresolved charges and all keys/spending paths | Pending independently | Pending independently |
| Billing/overage/payment/tax terms and actual model rates/access | Pending independently | Pending independently |
| Hackathon/grant eligibility and usage restrictions | Pending independently | Pending independently |
| Standard retention/data terms and gateway-only credential custody | Pending independently | Pending independently |

- [ ] Obtain provider-backed whole-request cost evidence and authoritative request-ID reconciliation method; review the written answer against this exact request/model/version.
- [ ] Verify notification permissions/delivery and private durable ledger storage without enabling inference. Provider alerts remain supplementary.

### 3. Human approvals

- [ ] Both developers approve code, budget and privacy changes, separately from the merge decision.
- [ ] The selected account owner explicitly authorizes that account; no implied authorization for the other account.
- [ ] The image owner approves transmission of the exact synthetic image to Meta under reviewed retention terms.
- [ ] The spending authority explicitly approves one named account, normalized-image hash, immutable price/policy version, expiry, <=$0.25 gross maximum, <=512 combined output tokens, one in flight, no tools/Files/SAM/history/retries.
- [ ] If selected-account exposure reaches $100, obtain its additional approval. No approval overrides its $120 operational cutoff or $150 absolute ceiling. $75 notices go to both developers.

### 4. Requirements for the first live Meta request

- [x] Resolve R1/R2 above and add duplicate-name selection/mode-header regressions; repeat local checks as recorded below.
- [ ] Implement and review the provider-backed bound at both gateway and sender; prove it covers every charge and stays <=$0.25. Do not weaken the current refusal while evidence is missing.
- [ ] Record genuine account, price and approval evidence in the one authoritative ledger; never initialize a genuine account using synthetic tests or an assumed-zero baseline.
- [ ] Independently verify all account gates and that no unresolved prior attempt exists. Keep the other account inactive; no rotation/fallback.
- [ ] After explicit approval only, load the selected server key privately, enable exactly one approved backend attempt and obtain both iPhone consents. No API keys in GitHub/iOS.
- [ ] Reconcile the single attempt using authenticated provider evidence, restore mock/false, preserve unresolved reservations and never retry ambiguity. Confirm/correct beverage details before logging.

The detailed conditional procedure remains in [META_LIVE_READINESS_2026-10-27.md](META_LIVE_READINESS_2026-10-27.md). It has not been executed.

## Final cleanup verification

- Python: 228 maintained tests + 32 subtests passed; 3 starter tests passed separately.
- iOS simulator unit suite: 24 passed, including stable/distinct candidate IDs and mock/live/unverified source wording.
- Mock UI: 2 passed; 4 skipped (three physical-only and one separately run fake-provider case).
- Fake-provider UI regression: 1 passed, selecting both same-name Tea alternatives (300/450 mL), verifying distinct IDs remain stable after dismissing a sheet, checking live labels/consents and logging 125 mL. Real Meta/notification senders are explicitly forbidden.
- Release simulator build passed. No physical-device regression run is claimed.
- Backend, pricing, budget admission and committed configuration were not modified. Defaults remain mock/false; each account's $120 cutoff, $100 approval, $75 notices and $150 ceiling are unchanged. The one-request $0.25 maximum remains enforced and real inference remains blocked.
- A credential-signature scan of all six existing feature commits plus working changes found no matches; no `.env`, key/certificate, database or populated `.xctestrun` is tracked. Changed source/test data was reviewed as synthetic; no selected photos, health records, credentials or genuine account approval evidence were added. This is a scoped source/history check, not a guarantee against every possible secret format.
- Final merge recommendation: ready for human-reviewed merge with live inference disabled, after Amine reviews the final diff. All executed local checks pass. Account/billing evidence and explicit approvals remain activation prerequisites. No paid calls, deployment or automatic merge.
