# Combined camera and hydration experience — November 3, 2026

## Installed implementation

`codex/combined-camera-hydration` combines merged camera PR #75 (`27cc907`)
with the hydration stack through PR #77 (`1c28dad`). Local merge `4b2ac8e`
contains the combined product; `8078493` adds test-only/plan clarifications.
The complete original app was built with valid HealthKit signing, installed in
place and launched normally on the paired iPhone. No uninstall/reset or launch
URL/token injection was used. The owner subsequently confirmed both the Home
goal/score in US units and the trained Meta camera mode. This is a scoped status
check, not a new image-inference or personal Wonder result.

The backend now serves both feature sets on the existing camera port 8771 with
the same owner token, camera beverage database, pinned model/runtime/OCR and
numeric camera diagnostics. The former hydration service on 8029 was stopped;
its database remains unchanged. No image inference or Meta request was made for
this integration. The Simulator and owned disposable fixture servers were
stopped after testing to free resources for local-camera use.

## Data and provider boundaries

The owner tokens were compared in memory and match. Startup preserved all rows
in both beverage databases, the camera runtime configuration and financial-ledger
bytes. The camera store had no goal; after announcing the preservation step,
only the previously owner-confirmed goal integer was adopted there. Its drinks,
corrections, receipts and contributed-photo rows were unchanged. The source
database was unchanged. Body answers, HealthKit records, manual measurements and
connection-scoped on-device profiles were not migrated or exported.

`HYDRA_LOCAL_META_ALLOW_WONDER` defaults false. Explicit true allows local camera
and live Wonder to coexist only with compatible mode/features and the existing
global billable gate. It changes no Wonder credential, budget, freshness,
preview/consent, publication, retry or replay rule. Camera still selects only the
local recognizer; its native child environment remains restricted to the
existing noncredential allowlist. Comprehensive dispatch retains its separate
flag, including saved replay when dispatch is disabled.

US presentation now also covers camera review, supported capacity, presets and
correction text. Canonical integer mL and original printed-label evidence remain
unchanged. Camera full-drink assumptions, optional partial amounts, correction
memory and separate training opt-in remain. Historical consumption time and
manufacturer-sourced nutrition are available in Edit; changing identity/type
removes the suggested product match. Date helpers combine finite checks with
reference-epoch precision.

## Verification

- Full Python: **1768 passed, 58 subtests, four skipped**, one existing
  Starlette/httpx deprecation warning. Skips are optional offline image/dataset
  collection checks requiring Pillow/DuckDB; neither is an application runtime
  dependency. No dataset download or new dependency was introduced.
- Native: **276 XCTest passed**, zero failures. New precision, nonfinite-date
  and camera unit-retention cases failed before their corrections and passed
  afterward. Invalid coexistence settings and combined fake-provider cases also
  followed observed failing/passing runs.
- Six distinct actual Simulator flows passed across the final scoped runs:
  US local-camera review/Confirm/Edit; cold-start comprehensive Wonder plus free
  replay; correction memory with separate training opt-in; unknown size entered
  inline in US fl oz; guided goal and populated Home; automatic sample-Health
  prefill after relaunch. All records/model responses were synthetic fixtures.
- The US camera case saved **exactly 1000 mL**, independently checked through the
  disposable backend, while displaying 33.8 fl oz and retaining the full-container
  assumption. The Wonder case kept numerical `insufficient_data`, displayed all
  eight validated sections and replayed its saved result. The disposable ledger
  gained one fake attempt, with no second attempt for replay. Actual financial
  ledger bytes were unchanged during all UI runs.
- Generated screenshots were exported and visually inspected. Earlier failed
  UI runs exposed lazy offscreen form rows, fixture correction-memory reuse and
  a triple-tap/keyboard layout issue in the old test helper. Test visibility,
  fixture isolation and single-focus replacement were corrected; no model or
  consent bypass was added.
- Fresh independent integration review found **no Critical or Important defect**.
  One minor remains: the camera date picker is present and selected-date handling
  is preserved, but selecting an older date through that control was not exercised
  in the combined UI run. No historical-date UI round-trip claim is made.
- Strict signature, HealthKit entitlement, unexpired provisioning and inclusion
  of the paired phone were checked. Backend startup/capabilities, goal preservation
  and installation/normal launch have private status-only receipts. No personal
  values, private photos, device diagnostics or credentials were published.
- GitHub checks for `1de7d76` passed: Python 3.13, Python 3.14 and iOS unit tests.

## Remaining checks

At 00:18 UTC on November 4 (November 3 locally), the authenticated read-only
runtime check reports Wonder **ready**. The owner supplied a fresh current
available-credit report; it is recorded privately as owner-attested, not an
operator-visible billing balance. Authenticated account identity, the existing
credential binding and published pricing were checked separately. The renewal
appended one authorization event and retained the original policy/quote end times,
all previous rows, holds, limits, frozen flag and risk-waiver references. It made
no provider request. Current payable balance, final gross charges and cross-ledger
billing status remain unverified. The new account-observation window ends at
01:14:49 UTC November 4; readiness must be checked again for a later send.

The owner still needs to preview the exact personal aggregates, consent and
verify one actual eight-section response and
saved replay. The operator cannot supply that consent or fabricate actual drinks
or calibration history. Genuine comparable workout measurements are still absent;
experimental fitting stays off by default. Scientific accuracy, unattended iOS
background execution and always-on hosting are not established by these tests.

The old camera-only installation helper remains a rollback artifact and can
replace this combined build/configuration. Use the new private combined launcher
and signed-build receipts for this milestone; do not run the old helper over it
without deliberately restoring that older scope.
