# Milestone 2 — mock Meta beverage recognition

Implemented for local review on `codex/meta-beverage-recognition`. No deployment, live provider transport, billable requests or automatic merge. Human review by both developers is required. The existing manually tested iPhone baseline is user-reported. Milestone 2 physical-device results and remaining coverage are now recorded in [the physical iPhone report](PHYSICAL_IPHONE_TESTING_2026-10-27.md).

## Implemented

The existing SwiftUI camera and PhotosPicker now lead to explicit upload consent, metadata-free resizing/JPEG encoding, an authenticated backend mock analysis, and an editable confirmation form. Demo scenarios are visibly synthetic: branded US cola, generic coffee, ambiguous/no match, missing nutrition, and service failure. Pixels are not recognized by the mock. Capacity is a suggestion with qualitative, uncalibrated confidence; actual consumption is never inferred or prefilled. Every field must be confirmed. Cancellation, failed analysis and ambiguous results create no log. Corrections remove the suggested product match. Analysis errors offer retry/manual logging; no automatic analysis retries.

Confirmed recognition uses the existing pending payload/idempotency key, SQLite record, deterministic calculation and daily-summary workflow. Pending submissions survive restarts without storing the image. Existing Milestone 1 manual fingerprints remain compatible. The small local nutrition catalogue retrieves the exact US Coca-Cola Original variant's manufacturer snapshot (45 mg sodium, 39 g carbohydrate per 12 US fl oz; verified 2026-10-27). Basis conversion uses the US fluid ounce definition, not the rounded container estimate. Other brands, markets and generic recipes have unknown nutrition. Water content remains unknown, including for cola: no invented multipliers or retention estimates. Broader catalogue coverage is future work.

API details: [recognition contract](architecture/RECOGNITION_API.md). There are no new dependencies. JPEG input is envelope/dimension-checked for the mock, not fully decoded on the server; a future live adapter requires a reviewed decoder/normalization strategy before accepting arbitrary third-party image clients.

## Meta selection and evidence

Public Meta documentation rechecked **2026-10-27**, without authenticated API probes:

- [Models](https://dev.meta.ai/docs/models): `muse-spark-1.3` supports images and text output. Select Standard mode; Contributor permits use of submitted content for training. Account-specific model availability remains unverified.
- [Image understanding](https://dev.meta.ai/docs/image-understanding): Responses API accepts `input_image` with inline base64 data URL. `backend.recognition.meta_request` constructs an offline reviewable payload, fixes the model, disables response storage, bounds output to 512 tokens and enables no tools. There is no send function. `store:false` is not a zero-retention guarantee.
- [Structured output](https://dev.meta.ai/docs/structured-output): JSON schema is documented. Future live adapter must extract and validate complete, non-truncated responses; enforce strict schema and enrich nutrition separately. Current mock output is validated, but is not a live-provider parser/evaluation.
- [Segmentation](https://dev.meta.ai/docs/media-segmentation): exact model ID `sam-3.1` (some product text says `sam-3-1`); image/video input returns boxes and masks. It cannot establish beverage composition or physical volume from scale-free imagery. Deferred; no SAM calls or dependencies.
- [Pricing](https://dev.meta.ai/docs/pricing-rate-limits): Spark Standard input $1.25/M tokens, cached input $0.15/M, output $4.25/M. SAM $2.50/1,000 images; $0.20/1,000 frames, minimum 50 frames per video request. Team-shared limits are not a spending cap. Image tokenization/total charge bounds and account terms still require verification before activation.

## Budget controller status

`backend.meta_budget.MetaBudget` implements an operator-initialized, persistent SQLite ledger in integer USD microdollars. `BEGIN IMMEDIATE` serializes checks/reservations across threads/process connections. Durable historical gross baseline, explicit approval evidence, expiring price version, settled charges and outstanding reservations determine admission. Unique attempt IDs cannot dispatch twice, even after restart. Maximum $0.25/attempt, two attempts/$0.50 per parent. Every retry needs a new reservation. No timer releases ambiguous reservations. Settlement above the bound records the actual charge and freezes admission. Missing/unapproved/expired policy, locked/corrupt/unavailable ledger, unknown cost and frozen policy deny admission. Existing ledgers cannot be reset via initialization.

At $75, one durable `notify_both_75_pending` event identifies both developers. Delivery/acknowledgement still needs wiring before live use. At $100, admission blocks without recorded further-spend approval. Exposure reaching $120 always blocks; $30 reserve remains untouched. Price validity/charge maxima must be verified by the gateway operator; the ledger does not establish provider billing facts.

This is tested ledger infrastructure, **not an enabled account-wide spending gateway**. The mock does not reserve money or create a zero historical baseline. No budget/admin HTTP routes exist. Live transport is absent and startup rejects billable/live flags regardless of credentials. Only a future single gateway with exclusive provider-key custody and one authoritative durable ledger may dispatch; copies on developer machines cannot enforce the shared cap. No raw token/image/provider-key fields are stored in this ledger.

## Privacy and retention

Photos remain in app memory until consented analysis; the app redraws pixels at <=1600 pixels per side, <=1 MiB JPEG. Original filename/EXIF/GPS is omitted. Consent covers this backend mock upload only, not future Meta/HealthKit disclosure. Backend request bodies are bounded (recognition <=1,400,000 bytes; others <=16 KiB), authenticated and never logged or persisted. No Files API, URLs, provider uploads or model prompts containing health records are used. Images may remain in runtime memory until released; secure erasure is not claimed. App clears the photo after discard/success. Confirmed identity, amounts, timestamps, source and sourced nutrition follow normal local-log persistence. No automatic log pruning or deletion API is added: operators must stop the test backend and remove its dedicated SQLite database (including WAL/SHM) to delete local test history, and remove the app to delete sandbox data. Keychain entries can survive app removal: revoke the development credential server-side and reset the dedicated test simulator when needed. Do not use real personal health data in review databases.

## Live activation requirements / blockers

1. Human review/approval of this PR and a separately reviewed live adapter. See the physical iPhone report for completed camera/selection/permission checks and remaining coverage.
2. Reconcile actual cumulative gross usage, credit validity/coverage, project identity and every alternate key/spend path for both developers. Do not assume the $0 payable balance means $0 gross usage.
3. Verify account access to exact Standard model, image billing/token-count behavior, every billable category, safe input/output cost bound, provider limits and retention terms. Do not probe billable endpoints yet.
4. Establish exclusive server-side key custody and the single authoritative ledger; connect reservation/settlement to every dispatch/retry. Deliver threshold notices to both developers and implement provider reconciliation/kill-switch operations. Durable pending notice alone is not notification delivery.
5. Obtain explicit initial live-spend approval (and further-spend approval before $100). Verify price validity, concurrency, ambiguous usage reconciliation and request caps end to end before enabling a transport.
6. Run consented mock-first recognition evaluation, then a separately approved bounded live evaluation. Unit tests do not measure model accuracy, volume accuracy, nutrition catalogue completeness or scientific hydration validity.

## Verification

Commands/results are recorded in the PR. Maintained tests live under `tests/`. Run preserved starter tests separately from `Hydra-Ai-Starter/` because it has a separate `ai` package. Simulator uses ad-hoc signing so Keychain tests work. Ordinary recognition XCTest includes HTTP payload/consent/failure/schema validation, photo preprocessing, confirmation bounds and pending photo-request recovery. Opt-in UI tests use a DEBUG-only synthetic-image fixture; no production fixture button is compiled. The full camera hardware and system PhotosPicker interactions remain physical-device checks.

### Executed 2026-10-27

| Check | Result |
|---|---|
| `python -m pytest tests -q` (existing local virtualenv) | 148 passed, 32 subtests; existing Starlette/httpx deprecation warning |
| `python -m pytest -q` from `Hydra-Ai-Starter/` | 3 passed |
| `HydraAI` signed simulator XCTest scheme, iPhone 18 Pro / iOS 27.0 | 19 passed, including 6 new recognition tests |
| `HydraAIEndToEnd` opt-in signed simulator UI suite, fresh mock backend/test database | 2 passed: manual logging/relaunch and consented mock photo correction/confirmation; 300 mL capacity / 125 mL consumed increases total by 125 mL |
| `git diff --check` | Passed |
| iOS source scan for Meta key/provider endpoint configuration | No matches; backend development credential remains runtime-only/Keychain |

The first broad root pytest collection encounters the preserved starter package collision; both suites pass when run at their documented roots. An unsigned simulator run fails the existing Keychain test; the required ad-hoc signed run passes. UI iterations exposed the missing number-pad dismissal and label truncation; keyboard Done and persistent short mL labels are implemented. The final UI test targets the switch control directly. UI image input is a DEBUG-only synthetic fixture, not hardware camera/PhotosPicker automation. No live Meta accuracy or billing behavior was tested; no billable calls were made.

### Review handoff

Feature branch and tests are pushed. GitHub PR creation is blocked by credentials: CLI GraphQL/REST return `must be a collaborator`; the connected GitHub integration returns HTTP 403 `Resource not accessible by integration`. The available browser has no signed-in GitHub session. No PR was created and main was not changed. The prepared PR description is [MILESTONE_2_PR.md](MILESTONE_2_PR.md). [Open the branch comparison to create the PR](https://github.com/georgiosaliba227/Hydra-Ai/compare/main...codex/meta-beverage-recognition?expand=1) using a collaborator account with pull-request write access. Issue #6 tracks the review handoff and tags Amine. This GitHub access blocker is separate from live Meta approval.
