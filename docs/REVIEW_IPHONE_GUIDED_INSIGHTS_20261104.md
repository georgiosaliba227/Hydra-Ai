# iPhone goal setup and connected insights review

Branch: `codex/iphone-guided-insights`. The signed application source is
`4321f28cfd7d296f0c02d5eabc86ac710c10c385`; later commits change only verification
tests and documentation. The separately staged features backend uses
`8dd0c3b128afe4c1aeab24d5a18b5cf072aa61f4` and has the same backend code.

The owner requested a filled water circle, one-button local photo analysis and
backend features while preserving the phone's records. Research of individualized
goal methods included 2026 studies and did not establish a validated personal
beverage requirement from the requested profile inputs. The owner then selected
a clearly labelled adult starting reference, reviewed and confirmed by the user.
See [evidence](research/INDIVIDUALIZED_GOAL_EVIDENCE.md) and the
[goal policy](architecture/GUIDED_GOAL_POLICY.md).

First use, Today and Settings offer the setup. Age/source applicability select the
published adult row; optional body/supplement answers receive no new coefficient.
Confirmation saves the selected destination's goal, and its water fill follows
that goal. Custom goals and skipping remain available. Profile answers stay in
protected, backup-excluded, separately scoped local storage. Deleting the phone's
data preserves other connection profiles; global profile deletion is explicit.

On-device Analyze needs no extra checkbox. Photo selection does not run inference;
review/confirmation and separate server/provider consent paths remain intact.

An independently enabled connection supports the phone's own aggregate Trends,
contextual Ask Hydra and existing local workout calculations. The owner-only
features app opens no database or financial ledger and cannot dispatch a provider.
Summary transfer requires an explicit review/send action. No individual drink
names, photos, identifiers, timestamps, profile or HealthKit records are sent.
See [device boundary](architecture/DEVICE_INSIGHTS_API.md). Existing full-backend
history and financial processes were left separate.

## Verification

- Full Python: **1457 passed**, five optional-dependency skips, 58 subtests; one
  existing Starlette/httpx deprecation warning.
- Full native XCTest: **202 passed**, zero failures.
- Seven relevant simulator UI flows passed: phone aggregate Trends/contextual
  Ask/workout/restart; reference confirmation/profile restart and adopted-goal
  water progress; under-19 abstention with custom confirmation; camera size
  correction; half/full water pixels; real offline inference/edit/confirm/restart;
  one-button Analyze. Expected RED regressions were observed before the fixes.
- Independent code reviews completed; connection-capture, no-context availability
  and profile deletion-scope findings were fixed and regression-tested.
- Signed generic iPhone build passed strict signature, team/profile expiry and
  registered-phone checks. It is staged privately for in-place installation.
- Owner LAN backend health and authenticated capability checks passed without
  sending personal data. The signed update was installed in place successfully over Wi-Fi. Phone
  backend connection and owner goal confirmation are still being verified; the
  earlier owner-confirmed offline test applies to the prior build.

Evidence bundles/logs remain in private temporary directories
`hydra-guided-connected-final-unit`, `hydra-guided-connected-e2e-final`,
`hydra-guided-connected-e2e`, and `hydra-guided-connected-pytest`. The signed app,
source/signature manifest and owner backend connection verification are in the
owner's private `on-device-insights-20261104` directory, outside Git.

## Review delivery

The branch was pushed. PR creation failed through the GitHub connector with
HTTP403 (`Resource not accessible by integration`) and through the existing CLI
authentication with `must be a collaborator`. No PR or reviewer notification was
created; credentials were not switched. Open a review from the
[pushed branch](https://github.com/georgiosaliba227/Hydra-Ai/compare/main...codex/iphone-guided-insights).
No merge or billable provider request was performed.
