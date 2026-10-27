# Camera activation preparation — October 27, 2026

**Status: local preparation completed; real Meta inference remains blocked.** This report is not spending, image-disclosure, deployment or merge authorization. Keep `HYDRA_AI_MODE=mock` and `META_BILLABLE_REQUESTS_ENABLED=false` until the evidence and explicit approvals below are complete.

## Code and integration

PR #7 is merged at `424f9fe862a6730c25b023256e296e79cc08d9b3`. This follow-up starts from PR #10 head `cac4b674bbcc69b3a8c04a4b8b3e1e251916e7f0`. The separate `codex/meta-camera-activation` branch preserves main and all other developers' branches.

At inspection, PRs #9 (`61f94e5`), #10 (`cac4b67`) and #11 (`8ee883a`) were open and individually mergeable. Each had no submitted GitHub review and no check/status results. Amine is already requested on #10; verbal approval is not a submitted review. Pairwise Git merge-tree checks were clean, which does not establish semantic compatibility or passing CI.

Human review/merge order: #10, then this follow-up against its resulting base. #11 forecasting is independent, not a camera prerequisite. #9 retains useful billing/counting/privacy findings but its activation evidence still describes the historical $0.25 policy; reconcile that wording with the separately proposed `dual-test-v1` before merging it. No PR was merged here.

The policy distinction is intentional: legacy singleton permits remain <=$0.25 and cannot be reset or silently upgraded. The proposed new policy allows at most $2 for one Georgio camera attempt and a separately approved Amine synthetic-context attempt. It is disabled and not permission to spend. Georgio-first preparation needs Georgio's authenticated account evidence; Amine's account/key is unnecessary for that request. Both developers' code/privacy/financial review is still required. Global concurrency and unresolved-billing locks apply across both accounts.

## Permanent ledger and private preparation

The authorized schema-only initialization was performed at:

`/Users/georgiosaliba/Library/Application Support/HydraAI/private/meta.sqlite3`

The preflight checked file nonexistence including dangling symlinks; registered Hydra worktrees, HydraAI Application Support and `/private/tmp/*hydra*` locations contained no conflicting financial authority. Four application databases contained beverage tables only; unrelated SQLite files were Xcode build/results databases. This bounded local inventory does not prove absence of remote provider spending, another host, renamed databases elsewhere or alternate keys.

The new file was exclusively created with no symlink following and umask 077, then initialized through the existing admin command with outbound sockets blocked. It is an owned mode-0600 regular file under mode-0700 private directories. SQLite integrity check passed. All seven financial tables are empty: `live_accounts`, `live_prices`, `live_permit`, `controlled_permits`, `live_attempts`, `live_events`, `live_notices`. A reservation without evidence was denied and left all tables empty. No zero spending baseline was inferred; no account, price, permit, approval or fixture evidence was imported.

Private deliberately invalid templates are in `private/activation-preparation/`: `account.UNVERIFIED.json`, `price.UNREVIEWED.json`, `permit.UNAPPROVED.json`, and `backend.DISABLED.env`. They cannot authorize a request and contain no actual keys. The existing physical-demo launch configuration still selects its temporary synthetic beverage database; it was not restarted, repointed or copied into the permanent ledger. Use only one active financial authority for this project.

The existing private `backend-georgio.env` is an owned mode-0600 regular file with a nonempty Georgio credential field. No credential value was printed or committed; presence is not verification of account binding, model access or validity. The previous physical-demo `/health` endpoint was unreachable during this run, so its current process state was not verified. New local test servers used explicit mock or fake-provider settings only.

## Public provider evidence and remaining cost gate

Public documentation was re-read October 27: [models](https://dev.meta.ai/docs/models), [image input](https://dev.meta.ai/docs/image-understanding), [Responses](https://dev.meta.ai/docs/protocols/responses), [reasoning](https://dev.meta.ai/docs/reasoning), and [Standard pricing](https://dev.meta.ai/docs/pricing-rate-limits). `muse-spark-1.3` supports JPEG data URLs in `input_image.image_url`; the context is 1,048,576 tokens and the output cap includes reasoning plus visible output. Standard prices are $1.25/M input, $0.15/M cached input, $4.25/M output.

Reserving 1,048,064 uncached input tokens and 512 output tokens gives **$1.312256 in conservative single-pass token exposure**, not an expected bill or all-inclusive provider guarantee. The $2 proposal leaves **$0.687744** for all independently bounded additional charges. Internal invocations, failed/partial/timeout/provider-retry charging, fees/taxes/rounding and authenticated billing finality remain unresolved. [Provider terms](https://dev.meta.ai/legal/terms-of-service) and [spend alerts](https://dev.meta.ai/help/billing/spend-limit-alert) do not establish a $2 hard cap. Promotional credits are not protection from gross overage.

The [support inquiry](META_BILLING_SUPPORT_INQUIRY.md) now states the proposed unapproved $2 ceiling and asks for these missing facts. It remains unsent. No Meta authentication, token count, model request or billing change was performed. A provider response must be evaluated, not merely recorded as verification.

## Exact-image preparation

A locally rendered, nonsensitive synthetic bottle illustration is privately prepared as `private/camera-candidate.jpg`, with source and manifest alongside it. It is clearly marked as an illustration, not a real product; it can test the request path but cannot validate real-photo recognition accuracy or nutritional truth. No actual image belonging to another person was selected. Georgio has not consented to sending this candidate to Meta.

Source candidate: 86,813 bytes; metadata-normalized bytes: 82,537. Normalized SHA256:

`c7bbab98d7ee9a1c41e4f6cb5a2dc62b336a81f717893995ce8cc7cf9a33edd8`

This source fingerprint must **not** be reused after iPhone re-encoding. The camera follow-up prepares JPEG bytes once, offers an explicit export for review, and uses those same bytes for Analyze. Select the candidate on the iPhone (or a different owned nonsensitive beverage), export the prepared JPEG to the trusted operator, and run the existing normalization/fingerprint command on that export. The backend strips JPEG APP/EXIF/XMP/IPTC/comments again before permit checking and transmission. A changed selection clears consent and results. A mismatch is rejected before dispatch, never repaired by changing an existing permit.

The export is an explicit system share action, not an automatic save or upload. Choose a private destination under the owner's control; any exported copy is then managed by that destination. Keep the selected photo/session until its approval and attempt; a new selection/export requires its own hash verification.

## Verification

Initial unchanged PR #10 backend suite: **251 passed plus 32 subtests**, with one existing Starlette/httpx deprecation warning. It covers invalid inputs, schema/privacy handling, account isolation, one-use permits, policy mixing, $75/$100/$120 boundaries, process races, crash/timeout reservation retention and no retries. The ledger agent's additional targeted mock subset passed **24 tests**. No test results were imported into the permanent ledger.

The updated native fake-provider consent flow passed on the iPhone 18 Pro / iOS 27 simulator: export availability, capability refresh preserving the image, both disclosure consents, stable candidate identity, confirmed consumed-volume logging, and reset on the next photo. Real Meta transport and GitHub notification delivery were replaced by functions that fail if called; only loopback fake-provider requests were made. Simulator tests do not replace physical-device confirmation or prove provider billing/account facts. Transfer through a physical device's chosen share destination has not been exercised; verify the received file's fingerprint rather than assuming a share service preserves bytes.

The prepared-image implementation passed **25 iOS unit tests**, including a GPS/private-EXIF fixture that verifies metadata removal and byte equality between export and the HTTP request. A heuristic credential scan covered 59 reachable Git commits / 267 unique blobs and 126 tracked files; no likely real secrets were found. Two matches were explicit test fixtures. This scan cannot establish absence in unreachable objects, ignored files or external stores. No provider credential identifiers or provider hostname were found in iOS; its local backend authentication token remains separate.

Independent code review also caught an outstanding library transfer that could replace a newer camera selection; accepting a selection now invalidates the older library item. That asynchronous physical/iCloud race was reviewed statically, not reproduced on a physical phone. No dependencies or inference/budget contracts changed.

After that fix, ordinary native mock end-to-end tests passed **2 tests** (manual persistence and photo consent/correction/confirmed volume), with **4 opt-in live/physical tests skipped** as intended. The live-consent test was run separately against the fake provider as described above. Local logs: `/tmp/hydra-activation-unit.log`, `/tmp/hydra-activation-fake-ui-final.log`, `/tmp/hydra-activation-mock-ui.log`. `git diff --check` passed. A final read-only check confirmed the permanent ledger remains intact and all seven tables empty.

## Conditional first-request procedure — do not activate yet

1. Amine records a GitHub review of the exact #10 head and this follow-up; Georgio completes his own review. Humans merge only after resolving review feedback. Do not activate an unreviewed worktree.
2. Georgio supplies private authenticated account/team identity and key fingerprint binding, Standard model access, current credits/expiry/coverage, gross historical and pending spend across keys, grant terms, retention, additional-charge bounds and billing reconciliation/finality. Inventory alternate spending paths and establish exclusive gateway custody. Verify GitHub notification credential/delivery for both developers without making a Meta request. A locally present key is not authenticated identity/access evidence.
3. Establish an enforceable whole-request gross bound <=$2. If terms cannot bound every category, keep mock mode. Do not reduce the full-context reservation based on JPEG size, estimated tokens or a promotional credit balance.
4. Keep the backend mock/false. Export the exact prepared JPEG and fingerprint it locally (this command reads an image and sends nothing):

   ```sh
   python -m scripts.meta_budget_admin \
     --database '/Users/georgiosaliba/Library/Application Support/HydraAI/private/meta.sqlite3' \
     image-fingerprint --image '/absolute/private/exported-prepared-photo.jpg'
   ```

5. Obtain Georgio's explicit exact-image disclosure and one-request spending authorization, binding `georgiosaliba227`, `camera`, `dual-test-v1`, `muse-spark-1.3` Standard, that normalized hash, reviewed price/evidence references and a UTC expiry. Maximum combined output 512; maximum gross exposure <=$2; one project-wide request in flight; no retries/history/hosted tools/Files/SAM. Both developers' review references must be real. No approval is issued by this document or by an on-screen consent toggle alone.
6. Only with genuine evidence, populate private JSON according to `Evidence`, `Price`, and `ControlledPermit` in `backend/meta_accounts.py`; use `attest-account`, `record-price`, and **`approve-controlled-test`** with the permanent path. Do not use `approve-first-test` for the proposed policy, reinitialize the database, reset history, or import Amine fixture data. Administrative commands record attestations; they do not verify their truth.
7. After final explicit authorization, use private backend-only environment injection: `HYDRA_DATABASE_PATH` selects this permanent ledger, `HYDRA_META_ACCOUNT=georgiosaliba227`, the verified Georgio key is in `HYDRA_META_GEORGIO_API_KEY`, and the notification/session credentials are supplied securely. Only then select `HYDRA_AI_MODE=guarded_meta` and `META_BILLABLE_REQUESTS_ENABLED=true` for that one backend. Use the reviewed local-network startup instructions; do not expose an unauthenticated server or put keys in shell arguments, iOS or GitHub. Tap **Refresh analysis mode**, which preserves the prepared image and resets consent/results; reconfirm exact exported bytes if the app/session must be reopened.
8. With the exact approved photo selected, confirm backend and Meta disclosure and tap Analyze **once**. Review identity and quantity before logging. Immediately return to mock/false, preserve every ledger record, and reconcile authenticated request ID/usage/invoice finality. Do not retry a timeout, crash, invalid result or uncertain bill. The existing recovery command records a reference only; it cannot clear frozen/unresolved charges. Additional recovery may need separately reviewed implementation.

The next human action is evidence collection plus recorded code review, not an API call. The first live attempt remains blocked until all listed gates pass.
