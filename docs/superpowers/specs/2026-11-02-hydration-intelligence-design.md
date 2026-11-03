# Hydration intelligence continuation

The November 2 user assignment authorizes autonomous implementation and parallel
work, continuing PR #65 (`c8e4a77`), without automatic merge. Preserve its HealthKit,
weather and Wonder flow and leave camera PRs #66–#70 separate.

## Approach and constraints

Extend the existing SwiftUI/FastAPI/SQLite/Python implementation. Replacing it or
deploying a new service adds risk without improving evidence. Population study
models remain offline research until their target and population support app use.
The personal engine may abstain; loss never becomes a required intake amount.
Separate measured, derived, predicted, simulated and Meta-generated information.
No new runtime dependency, paid call, credential change or private ledger operation.

1. Preserve the historical study artifacts. Add versioned model-selection evidence
   from participant-grouped development validation, untouched calibration/test sets,
   baseline comparisons and domain/missing-input checks. Retain a simpler model
   when development evidence cannot support complexity. Additional sources require
   measured compatible targets, clear reuse terms and participant provenance.
2. Retain manual calibration on the iPhone only after an explicit save action,
   scoped to its backend connection. Protect atomic storage, validate reloaded
   records, cap the existing request at 32, and support export and deletion. Saved
   history never saves processing consent or Meta consent. Corruption fails visibly.
3. Add a nonbillable versioned analysis endpoint using the existing workout request.
   Combine deterministic intake context, personal workout estimates, environmental
   context, uncertainty, missing measurements and the existing Wonder preview/replay.
   Planned loss is never counted as a completed loss or total-body hydration.
   Simulated analyses never read personal intake. The backend keeps no calibration.
4. Present the analysis in the existing workout screen, keeping numerical authority
   and the exact preview/consent/hash/replay gates of the existing Wonder endpoints.

The current Muse Wonder model is the sole explanation model. No model comparison,
new billing path or automatic retry is introduced. Comprehensive local analysis
must clearly identify which parts Wonder actually received and explained.

## Verification and delivery

Test boundary validation, privacy, stale/duplicate history, cold starts, shifted
conditions, missingness and baseline retention. Run full pytest, pinned training
tests/reproduction, XCTest and targeted simulator UI workflows. Inspect actual
simulator screenshots. Physical-device and live-provider verification require
available hardware and separately satisfied account/input/billing gates; record
them as unverified when unavailable. Publish a review branch and PR for Amine,
with scientific results, exact checks and unresolved limits in shared status docs.
