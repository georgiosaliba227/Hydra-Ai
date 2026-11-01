# Camera correction workflow verification — November 1, 2026

Base: `3f258cefec1cafe987c69383053609da921cf5d3` (`origin/main`).
Scope: [camera corrections contract](architecture/CAMERA_CORRECTIONS_API.md).

The app displays the original recognition details and supported visible-liquid
ranges, offers Confirm/Edit, and requires actual consumed mL before logging.
Personal corrections are applied as separate suggestions. Default-off training
consent stages bounded examples locally for future review; it does not train a
model or send a dataset to Meta.

## Results

- Full Python suite: **1,092 passed, 32 subtests passed, one skipped, one failed**.
  The failure is the previously reproduced baseline
  `tests/recognition/test_wonder_workout.py::test_invalid_requests_are_rejected[<lambda>11]`:
  its fixed “future” date is now past, producing 409 rather than 422. It is not
  changed here; this branch is not eligible for automatic merging.
- All **20** new camera-correction Python tests passed, including transaction
  rollback, concurrent idempotent replay, explicit training consent, JPEG
  sanitization/hash validation, owner isolation, deletion, retention, live
  receipt association, mock/live separation and financial-history preservation.
- Native Swift unit suite: **86 tests passed** on the iPhone 17 Pro simulator.
- Synthetic camera-correction UI case passed: edit identity/capacity, require
  actual consumption, verify training defaults off, explicitly opt in, confirm
  125 mL, and show the personal correction (including a separately corrected
  240 mL in that exact photo) beside the next original suggestion.
- Both existing backend UI cases passed: manual log/restart persistence and
  photo confirmation with only the actual consumed amount counted.
- The fake-provider live-consent UI case passed: separate Meta disclosure,
  consent reset, distinct duplicate alternatives, receipt-bound confirmation
  and 125 mL counted. This local simulation cannot call Meta.
- Signed physical iPhone 17 Pro build and installation succeeded. After the
  initial locked-device launch block, the owner confirmed Hydra was open, and
  the mock backend served authenticated camera analysis successfully. Physical
  Confirm/Edit behavior and a new live recognition have not been independently
  verified.
- Independent backend/privacy review found no blocking issues.

Synthetic test providers forbid real network dispatch. No new billable request
was made for this feature. The owned physical-test backend runs mock mode with
billable inference disabled and advertises correction-memory/training support.
A read-only check found the same existing attempts, holds and frozen-account
state; no private financial ledger migration or reconciliation was performed.

## Limits and next physical check

Unlock the phone, open Hydra, refresh Camera analysis mode, and use the mock flow
to check Confirm/Edit and actual consumed mL. A default-off training contribution
is optional and retains the selected photo on the user's backend. Do not use it
for photos whose sharing rights have not been confirmed.

A real Muse check of the changed volume-estimate schema still requires the
existing account/billing gates and a separately approved one-use permit. Neither
this implementation nor the physical installation enables that request. Photo
estimates remain uncertain; opaque or unsupported fill stays unknown. These
tests do not demonstrate model accuracy or physiological validity.
