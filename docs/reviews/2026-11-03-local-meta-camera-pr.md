# Connect the trained local Meta model to Hydra camera

The selected beverage adapter could only run through the offline experiment runner. Hydra now has an explicit `local_meta` backend/client mode that sends an owned prepared photo to the owner's Mac, runs the pinned Muse Glimmer base and selected LoRA, and automatically opens the existing Confirm/Edit review. It is distinguished from hosted Spark and mock mode throughout the client.

Printed metric capacity must agree between the trained model and local Apple Vision label reading. Unreadable/conflicting evidence remains unknown. Only corroborated literal size spans survive OCR into receipts; remaining liquid and actual consumption are not inferred. The existing full-container assumption, volume editing, hydration engine, personal corrections and separately opted-in local training staging remain intact.

The credential-free runtime serializes both native workers under a child-inherited process lease, enforces bounded execution/resource guards, and removes temporary photos/features. Local receipts live in the beverage database with export/deletion and durable confirmation replay. Hosted inference is disabled in local mode; the financial ledger is unchanged. No training weights, images, tokens, provider credentials or private receipts are included in this PR.

Validation:

- Complete pytest: 1,318 passed, 5 skipped, 58 subtests; one existing FastAPI/httpx deprecation warning.
- Signed simulator XCTest: 102 passed.
- Isolated iPhone simulator UI test: passed using the real trained local model and owned one-litre photo; exact capacity, explicit full-container assumption, enabled Confirm, editable name/volume, and Cancel without logging verified.
- Signed generic iPhone build: succeeded with the existing development team.
- Real local HTTP analysis: one-litre Dasani example recognized with exact 1000mL capacity, approximately 50sec, no beverage saved.
- Independent source review found three issues (orphan-worker lease, excess OCR retention, confirmed-receipt eviction); regressions were watched fail and pass, fixes were reviewed with no remaining material finding.

Physical iPhone installation remains blocked: the paired, unlocked phone reports an unavailable trusted wireless tunnel; attempted installation returned CoreDeviceError4016. No physical-device test or install success is claimed. The local runtime is active and the new signed app is ready for USB or a working paired wireless connection. See `docs/LOCAL_META_CAMERA_SETUP.md`.

This branch is stacked on `codex/beverage-adapter-training`; preserve that dependency during review. The previous GitHub integration rejected PR creation with403, so this file also provides a manual review handoff. Do not merge or enable hosted requests as part of local-camera testing.
