# Camera workflow verification — November 1, 2026

Base: `3f258cefec1cafe987c69383053609da921cf5d3` (`origin/main`).
Scope: [camera contract](architecture/CAMERA_CORRECTIONS_API.md) and the owner's
expanded full-drink / simple Confirm-or-Edit assignment.

Analysis automatically presents a compact photo/name/volume review. Confirm
logs the proposed supported whole-liquid volume under the user's explicit
assumption; Edit exposes name/type, presets, mL / US fl oz / litres and a partial
amount toggle. Unknown liquid is not silently replaced by capacity. An explicit
full-container choice records a different assumption. Unknown capacity stays
unknown, including when a user's corrected volume contradicts an old estimate.

Personal corrections remain separate from original Muse suggestions. Default-off
training consent stages the latest 20 owned photo/correction examples locally;
it never trains a model or sends a dataset to Meta automatically. Consumption
assumptions are not vision-training targets.

## Verified evidence

- Full Python suite: **1,127 passed, 32 subtests passed, one skipped**. The former
  sole baseline failure used a fixed date that was no longer future. Its one-line
  fixture correction now always supplies actual tomorrow; the failing case was
  observed first and passed after correction. No workout production logic changed.
- Offline demo rehearsal passed with zero network/financial-ledger attempts.
  Its allowlist includes the new user-data tables and checks they remain empty
  without explicit correction/training consent. All three preserved starter
  tests also passed.
- **55 focused backend tests** passed for metric label extraction, declaration of
  full consumption, name/type memory, privacy, transaction rollback, idempotent
  replay, retention/deletion, receipt binding and financial-history isolation.
- Native Swift suite: **94 tests passed**, including midpoint/default behavior,
  no capacity-to-fill substitution, exact-image corrections, bounded unit
  conversion, presets and partial amounts.
- **Three new native UI cases passed**: immediate Confirm/Edit with a 200 mL
  estimate; editing name/type and 16.9 US fl oz to 500 mL; preset/partial entry
  logging only 125 mL. Review/Edit screenshots were exported and visually checked.
- Both existing backend UI cases passed: manual logging/restart persistence and
  unknown-size photo confirmation with a separately entered consumed amount.
- The correction/training UI case passed: the training switch defaults off,
  explicit opt-in stages a synthetic photo, and a subsequent analysis displays
  personal name/liquid corrections separately from the original suggestion.
- The fake-provider live-consent UI case passed with separate Meta disclosure,
  consent reset, stable duplicate alternatives, receipt binding and confirmed
  logging. The seven simulator UI cases used no real provider transport.
- Independent whole-change review found one Important serving-size parsing issue.
  Five failing regression fixtures reproduced it; the fix rejects serving,
  portion, per-quantity and nutrition text while retaining explicit net capacity.
  The reviewer reran all 55 focused tests and reported no remaining Critical or
  Important finding.
- **Both physical iPhone 17 Pro UI cases passed**: whole-liquid review/Confirm
  and name/type + US fl oz editing. An isolated synthetic database received
  exactly 200 mL coffee and a user-edited 500 mL sports drink. These are generated
  photo/mock tests, not new Muse recognition results or actual consumption.
  Test teardown restored the owner's normal backend connection after each case.
- Physical testing first reproduced a crash at a missing weak-linked Foundation
  `Date >=` operator on this iOS 27.2 device. Finite timestamp comparisons now
  preserve inclusive bounds in save/edit and related refresh validations. Two
  new date-boundary tests pass; the rebuilt binary has no Date >=/<= imports.
  The exact previously crashing physical cases passed after the fix. Independent
  review found no remaining Critical or Important issue in this compatibility fix.
- Signed build/install and signature verification succeeded. The owned normal
  backend was restarted with current code and verified **mock / billable=false**.
  Temporary synthetic servers were stopped after the successful runs.

## Still unverified / live gate

No new billable request was made for this feature. A read-only operator check
found existing unresolved billing, frozen-account status and no invoice-finality
evidence. No financial record, used permit, hold or limit was changed. The
authenticated overview's rounded balance does not establish final per-request
charges. The authenticated CSV contains aggregate daily/series metrics, not
per-request final charges or invoice-finality evidence. Payment activity exposes
only the existing pending card transaction. Detailed account evidence remains private.

A real iPhone Meta recognition/size result remains unverified. The next dispatch
requires authenticated final billing evidence and the existing reviewed
reconciliation process, followed by a fresh exact-image one-use authorization.
The previous permits cannot be reused. This implementation does not promise
universal visual recognition accuracy or infer physiological hydration status.
