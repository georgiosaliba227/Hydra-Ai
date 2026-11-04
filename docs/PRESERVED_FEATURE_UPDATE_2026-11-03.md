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
