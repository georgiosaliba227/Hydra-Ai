# Use Hydra's offline iPhone camera

This prototype bundles `dinov2-small-beverage-v1`, a compact Meta image model
with a beverage-category head, plus local Apple Vision label reading. Neither
recognition nor local saving needs the Mac, Wi-Fi, a server token or a Meta key.
The signed build still needs to be installed on the phone first.

## After installation

1. Open Hydra → Settings. Enable **On this iPhone (works offline)** and tap
   **Save connection**. Your server settings, server history and legacy demo
   history remain separate. An existing unresolved pending save must be
   reconciled before changing destinations.
2. Open Camera and take or choose a drink photo. Show the printed size clearly.
3. Enable **Allow this photo to be analyzed on this iPhone**, then tap
   **Analyze on this iPhone**. No backend or Meta-upload consent is needed for
   this mode because the photo stays on the phone.
4. Review **Your drink**. Confirm means the whole drink was finished under the
   displayed assumption. Use Edit to correct the name/type/size or choose a
   different amount. In Edit, **Container size (optional)** can be corrected in
   mL/US fl oz/L or cleared. **Amount to log** is separate. Editing a full-container
   size updates that assumed amount; partial amounts stay separate. The original
   photo suggestion is preserved. Unknown sizes remain blank until you enter one.
5. Confirm, then check Today and History. Close/reopen Hydra to check persistence.
   Settings offers local goal, JSON export and deletion of this mode's records.

For physical verification, enable airplane mode (including Wi-Fi off), repeat
capture/analyze/review/save, then terminate/reopen the app and check the saved
entry. This is a remaining physical-device check, not a claim already verified.

## What the prototype can support

- Twelve category outputs: beer, coffee, energy drink, juice, milk, other,
  plant milk, soda, sports drink, tea, water and wine. Sparse classes are limited.
- A small deterministic brand vocabulary from readable text; otherwise an
  editable category/unknown name. It does not identify every brand or variant.
- Unambiguous printed metric sizes or explicitly US fluid-ounce declarations.
  Serving-only, multipack, conflicting or ambiguous declarations remain unknown.
- Protected local drink records, original model suggestion, confirmed corrected
  name/type/capacity/amount, explicit consumption assumption, safe retry and
  restart persistence. Local records and on-device pending writes are excluded
  from device backups. Photos and unrelated background OCR are not retained.

Category accuracy on the existing product-separated held-out cohort was 50/75
(67%); this is experimental category recognition, not brand/size accuracy. The
scores are uncalibrated and displayed as low confidence. The model has no validated
general non-beverage rejection or natural-glass accuracy. Size labels establish
capacity, not remaining liquid or consumption; nutrition and water content remain
unknown without sourced composition. No training or automatic correction reuse
runs on this path. Existing server correction/training controls remain separate.

## Verification and build handoff

Verified in the simulator: real bundled Core ML + OCR, generated 500 mL label,
Confirm/Edit, corrected type/name, local save and persistence after a normal
restart without a backend configuration. Model input/output/identity, missing
model, corrupt store, idempotency, local export/delete, stale results and ambiguous
label boundaries have unit tests. A simulator analysis took approximately 0.8–1.6s
on the Mac; this is not physical iPhone performance evidence.

The signed generic iPhone build uses the existing Hydra team/profile and bundle
identifier. Install in place; do not uninstall Hydra or erase its container.
The owner completed wireless pairing through Xcode 27 Device Hub. The signed
update was installed in place over Wi-Fi on the registered iPhone 17 Pro and its
process launched successfully. The signed `.app`, source/signature manifest and
UI proof remain staged in the owner's private `on-device-camera-20261104` directory.
Saving the local mode, physical airplane-mode recognition/save and force-close/
reopen persistence are awaiting the owner's final device check. No physical
latency or recognition-accuracy claim is made.

Development details and model source/metrics are in
`docs/architecture/ON_DEVICE_CAMERA.md` and `ai/on_device/README.md`. Weights,
license and model notice are bundled; no model download occurs at runtime.
