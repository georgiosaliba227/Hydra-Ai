# Connect the trained local Meta model to Hydra camera

The selected beverage adapter could only run through the offline experiment runner. Hydra now has an explicit `local_meta` backend/client mode that sends an owned prepared photo to the owner's Mac, runs the pinned Muse Glimmer base and selected LoRA, and automatically opens the existing Confirm/Edit review. It is distinguished from hosted Spark and mock mode throughout the client.

Printed metric capacity must agree between the trained model and local Apple Vision label reading. Unreadable/conflicting evidence remains unknown. Only corroborated literal size spans survive OCR into receipts; remaining liquid and actual consumption are not inferred. Confirm follows the owner’s convention that logging means the drink was finished. Known supported size/whole-drink quantity prefills direct Confirm/Edit; unknown size gets an inline Drink size field. A different amount is optional inside Edit. The existing assumption provenance, volume editing, hydration engine, personal corrections and separately opted-in local training staging remain intact.

The credential-free runtime serializes both native workers under a child-inherited process lease, enforces bounded execution/resource guards, and removes temporary photos/features. Local receipts live in the beverage database with export/deletion and durable confirmation replay. Hosted inference is disabled in local mode; local camera makes no financial-ledger writes or hosted provider requests. No training weights, images, tokens, provider credentials or private receipts are included in this PR.

Validation:

- Complete pytest: 1,318 passed, 5 skipped, 58 subtests; one existing FastAPI/httpx deprecation warning.
- Signed simulator XCTest: 102 passed.
- Finished-drink review: two new synthetic UI cases passed (direct whole-drink Confirm/Edit; inline unknown size with US fl oz conversion and logging), plus three existing confirmation/edit/partial scenarios. Raw-photo estimates remain secondary.
- Updated signed build installed in place and launched normally on the physical iPhone; no new inference was initiated for this UI-only update.
- Isolated iPhone simulator UI test: passed using the real trained local model and owned one-litre photo; exact capacity, explicit full-container assumption, enabled Confirm, editable name/volume, and Cancel without logging verified.
- Signed generic iPhone build: succeeded with the existing development team.
- Physical iPhone: installed/opened over USB, trained-model mode confirmed, real photo recognition and Edit/Confirm completed. The saved user-approved amount matched deterministic beverage contribution; personal correction persisted and shared training remained off. The label size in this photo remained unknown and the user supplied the quantity; this is not a successful automatic-size-reading claim.
- Real local HTTP analysis: one-litre Dasani example recognized with exact 1000mL capacity, approximately 50sec, no beverage saved.
- Independent source review found three issues (orphan-worker lease, excess OCR retention, confirmed-receipt eviction); regressions were watched fail and pass, fixes were reviewed with no remaining material finding.

The signed build is installed and verified on the physical iPhone over USB. The local backend was refreshed to the home Wi-Fi address and verified in `local_meta` mode with billable requests disabled. The owner confirmed the saved entry and trained-model connection persisted after a normal app restart. User photos, corrected drink records, quantities, receipt identifiers and image hashes remain private. See `docs/LOCAL_META_CAMERA_SETUP.md`.

This branch is stacked on `codex/beverage-adapter-training`; preserve that dependency during review. The previous GitHub integration rejected PR creation with403, so this file also provides a manual review handoff. Do not merge or enable hosted requests as part of local-camera testing.
