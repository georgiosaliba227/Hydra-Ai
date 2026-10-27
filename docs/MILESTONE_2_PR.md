## Summary

Adds the Milestone 2 mock photo-recognition workflow to the merged manual-logging prototype. Users capture/select a photo, explicitly consent to sending a resized metadata-free JPEG to the local backend, review synthetic branded/generic/ambiguous candidates, correct identity/capacity, and confirm the actual amount consumed. Only confirmation creates a durable idempotent log and updates the existing deterministic hydration accounting. A 300 mL container with 125 mL consumed contributes 125 mL.

Backend analysis is authenticated, size/schema bounded and transient. Nutrition is independently retrieved from a small manufacturer-sourced US-product catalogue; unmatched products and unknown water fractions remain unknown. Corrections remove stale product matches. Existing Milestone 1 pending/manual fingerprints stay compatible. Camera capture/PhotosPicker build on the existing native implementation; hardware verification is still required.

Adds a persistent SQLite gross-spend ledger with atomic reservations, expiring verified-price policy, explicit approval evidence, duplicate dispatch denial, bounded retries, crash/restart retention and fail-closed settlement/reconciliation behavior. Thresholds: durable notification event at $75, further-approval gate at $100, reject admission reaching $120. This is tested ledger infrastructure, not an enabled account-wide gateway; notification delivery and exclusive key custody remain live-activation blockers. There is no provider transport, provider credential loading, billable call, deployment or automatic merge.

## Model verification / live gates

Public Meta docs rechecked 2026-10-27: `muse-spark-1.3` Standard accepts image input and returns text; selected for future recognition. Documented Standard pricing: input $1.25/M, cached input $0.15/M, output $4.25/M tokens. `sam-3.1` accepts images/video and returns segmentation masks/boxes; deferred, not a nutrition or physical-volume estimator. An offline Responses payload builder exists; account access, image charge bounds, retention, live response parsing/evaluation and exclusive gateway dispatch must be reviewed before activation. No authenticated or billable probes were made.

See docs/MILESTONE_2.md and docs/architecture/RECOGNITION_API.md for the complete contract, source links, privacy/retention limits and activation checklist. Before live use: reconcile actual shared gross usage/credits and alternate spend paths, verify current account/model/pricing and complete request cost bounds, wire all dispatch/settlement through one authoritative ledger, deliver alerts/reconcile provider usage, and obtain explicit initial billable-use approval. The $30 reserve remains untouched.

## Validation

- Maintained pytest suite: 148 passed + 32 subtests (one existing Starlette/httpx deprecation warning).
- Preserved starter suite from its own directory: 3 passed.
- Ad-hoc signed iOS simulator unit suite: 19 passed, including 6 recognition tests.
- Opt-in native UI suite against a fresh synthetic local backend: 2 passed, including consent, required confirmation, corrected identity and consumed-volume accounting; existing manual logging/relaunch also passed.
- Budget tests cover race/replay, retries, real process exit/restart, missing/locked/corrupt ledgers, stale prices, conflicting/over-bound settlement, kill switch and threshold boundaries.
- `git diff --check` and iOS Meta-key/provider-endpoint source scan passed.
- Root-wide pytest collection must keep the preserved starter package isolated as documented. Simulator Keychain tests require ad-hoc signing. No physical camera, live model accuracy, scientific formula validation or live billing verification is claimed.

Refs #6. @aminealichaouche please review backend/AI interfaces, catalogue provenance and shared-budget semantics. Georgio to review iOS and repeat physical iPhone testing for this workflow. Human review from both developers is required before merge.
