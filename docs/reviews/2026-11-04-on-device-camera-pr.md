# Run beverage camera recognition entirely on iPhone

Hydra's trained 30B adapter required the owner's Mac. This adds an explicit
**On this iPhone** mode with a bundled compact Meta DINOv2 beverage-category head,
local Apple Vision label reading, existing Confirm/Edit and protected real local
logging. After installation, camera analysis and confirmation need no Mac,
network, server token or Meta key. Existing server settings/history and synthetic
demo data remain separate; there is no automatic HTTP fallback or migration.

Unambiguous printed sizes can prefill a full-container assumption. Complete OCR
context is checked before parsing: serving qualifiers, preparation instructions,
multipacks and conflicting metric/ounce sizes stay unknown. Edit independently
corrects or clears container capacity in mL/US fl oz/L and keeps the logged amount
separate; original photo suggestions remain preserved with model provenance.
Local records and pending writes are protected, excluded from backup, idempotent,
exportable/deletable and readable after a device-clock rollback. No photos or
unrelated OCR persist. No automatic correction reuse or training runs locally.

The frozen backbone and trained head are a separate model from the 30B adapter.
The 43.4 MB Core ML package, model notice and Apache 2 license are bundled. Training
uses the existing reviewed public 150/25/75 train/validation/test split; source
revision, hashes, selection and full predictions are recorded. Held-out category
top1 was 50/75 (67%); fixed abstention thresholds suggested 57/75, 41 correct. These
are category-only results, not general brand/size accuracy. Scores stay labeled
uncalibrated/low confidence; open-world and natural-glass accuracy are unvalidated.

Validation:

- Complete pytest: 1,336 passed, 5 skipped, 58 subtests; existing FastAPI/httpx warning.
- Signed simulator XCTest: 129 passed, including real bundled Core ML + OCR.
- Two real-inference simulator UI cases passed: size correction downward/upward/
  clear with independent amount; Analyze→Edit→Confirm→normal restart persistence.
- Signed generic iPhone build and staged copy pass strict code-signature checks;
  the existing profile includes the owner's phone. No credentials were changed.
- Exact trained-head/weight reproducibility and three-case FP16 Core ML parity
  passed. Simulator analysis around 0.8–1.6s is not physical latency evidence.
- Fresh independent source review found label ambiguity/OCR truncation, missing
  independent capacity correction, backup policy and clock-rollback issues.
  Reproductions were observed fail, fixes integrated, and full checks passed.

The owner completed wireless Device Hub pairing. The signed update was installed
in place over Wi-Fi on the registered iPhone 17 Pro and launched successfully.
The signed build and UI proof remain staged privately. A focused physical-device
XCTest passed on iPhone 17 Pro/iOS 27.2: the real bundled model and OCR analyzed a
generated label in about 2.9s with wireless debugging connected (one test, zero
failures). The original signed app was restored in place afterward. Physical
airplane-mode analysis/save and force-close/reopen checks are awaiting the owner;
real-camera accuracy and general performance remain unverified. No hosted calls, financial-ledger changes, public
deployment or merge are part of this PR.

@aminealichaouche — please review the local persistence and recognition boundary.
Setup: `docs/ON_DEVICE_CAMERA_SETUP.md`. Model evidence: `ai/on_device/README.md`.

Review handoff: branch `codex/iphone-offline-camera` is pushed. Both creation routes were denied: GitHub connector403 (Resource not accessible by integration) and existing CLI GraphQL (must be a collaborator). No PR was created. The pushed branch and this exact review text remain available for an authorized collaborator to open the PR. No credentials or account settings were changed.
