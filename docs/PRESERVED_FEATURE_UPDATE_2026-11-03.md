# Preserve the installed feature set while applying final fixes

The final-check fixes were merged into `main` by PR #80 (`3ac7207`). The phone
and Mac backend were running the broader `codex/combined-camera-hydration`
variant at `7708a2c`, including guided goals, hydration scores, personal runtime
and combined local-camera/Wonder features. The user selected preservation of
those features instead of replacing that installation with exact `main`.

`codex/preserve-combined-latest` backports the applicable PR #80 fixes onto that
installed feature set. It leaves its screens, US/metric units, calibration/profile
stores, model pins, backend contracts and financial/provider configuration intact.
It does not merge the older combined feature branch wholesale into `main`.

The combined backend already held the Wonder lock from facts through persistence
and used that lock for delete-all, including comprehensive analyses and scores.
That implementation is retained. The backport adds camera receipt generation
invalidation across deletion, revokes displayed/delayed receipts in the client,
and prevents synthetic manual placeholders from being submitted as authentic
model correction references. It also carries the Connection heading contrast
and wrapping empty-History fixes.

## Verification

- Combined baseline: 1,741 Python tests passed, 10 optional skips, 58 subtests.
- Backport: 1,746 Python tests passed, 10 optional skips, 58 subtests.
- Full native unit suite: 277 passed, zero failures.
- Local-camera receipt resurrection failed before the backport and passes after
  it. The new client deletion XCTest had three failing assertions before the
  fix and passes afterward. Four Wonder deletion races pass against the retained
  combined implementation.
- The new standalone local-camera native regression passes on a disposable
  loopback fixture, confirming a 240 mL save and no blocked pending entry.
- Independent read-only review found no important preservation regression and
  independently ran 274 targeted tests successfully.

Raw evidence is retained locally under `/tmp/hydra-final-checks/` with the
`preserve-` and `preserved-` prefixes. The initial native UI attempt encountered
a simulator preflight/launch error; the dedicated simulator was rebooted and
the regression passed. Tests use disposable synthetic records and fake providers;
no provider inference or private-ledger modification is part of these checks.

The optional skips are offline dependency/environment checks; no dependency was
added. Existing prediction/scientific limitations and real-provider readiness
requirements remain unchanged. A passing local integration test does not renew
financial authorization, supply personal-data consent or establish health accuracy.

## Device/runtime delivery

The signed preserved-feature build is **308**, from source revision `627cf5b`.
It was installed in place on the paired owner phone; no uninstall, URL override,
token injection or data-reset operation was used. The private backend now runs
an immutable staged copy of the same revision. Startup verified unchanged
database rows, financial-ledger bytes, model configuration and connection-file
bytes. Existing provider configuration was preserved; no financial authority
was renewed and no inference was requested.

The additional synthetic guided-goal/profile-relaunch/Home-score native check
passed, as did the exact one-litre US camera review. The extra
`CombinedExperienceUITests.testColdStartStillOffersConsentedDetailedWonderAndFreeReplay`
rerun initially lacked the logged evidence required by the real API and correctly
offered no send action. After supplying an invented prior-day drink, its rerun
was stopped because XCTest repeatedly waited 60 seconds for app-idle/animation
notifications. No fake provider call had begun. No passing result is claimed for
that extra rerun; the comprehensive API/grounding/replay tests still pass.

PR #81 targets the existing combined feature branch and passes GitHub's Python
3.13, Python 3.14 and iOS unit checks. PR #80 remains the merged fix on `main`.
Final normal launch and protected on-device file verification await the owner
unlocking the phone: iOS explicitly refused launch while it was locked. The
installed-build check already confirms build 308. Private operation receipts
and the previous signed build are retained for recovery.
