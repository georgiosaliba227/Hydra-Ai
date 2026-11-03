# Combined camera and hydration build

## Intent and authorization

Continue the owner's full iPhone hydration-intelligence mission while preserving
the separately verified trained-camera experience. The owner authorized autonomous
implementation, testing, parallel reviews and review PRs, not automatic GitHub
merges. The camera chat has now released its exclusive phone check: owner-reported
success agrees with numeric local stage diagnostics totaling about 32 seconds.
Camera PR #75 is merged as `27cc907`; the hydration stack through PR #77 is at
`1c28dad`. Earlier build-specific physical evidence remains scoped to those builds.

## Approach

Use a local integration branch combining both histories, one complete native app,
and the currently saved camera backend on port 8771. The existing owner tokens
were compared in memory and match; no new phone token or URL is needed. The
camera beverage database is the active store. Preserve the hydration database and
connection-scoped profiles separately; do not silently migrate personal records.

Separate per-feature URLs would introduce another connection/consent model.
Switching between the old builds loses features. Those approaches do not satisfy
the existing request for one combined experience. Choosing the current camera
connection as active is the implementer's preservation choice, not a claim that
the owner approved a private-data migration.

## Boundaries

- Keep the camera's pinned local runtime/model/adapter/OCR and Confirm/Edit flow.
  No retraining, hosted photo fallback or extra image inference for integration.
- Keep canonical mL APIs and evidence while showing US units by preference.
  Untouched rounded display must preserve exact canonical amounts.
- Keep on-device Health/weather/profile/calibration boundaries, explicit first-
  use permissions, local stores, stale-connection guards and protected deletion.
- Preserve owner Wonder authority, account-specific ledger, all holds, waivers,
  limits, fresh observations, exact preview/consent, no retries and free replay.
  No personal provider request is authorized by backend startup or this merge.
- Add default-false `HYDRA_LOCAL_META_ALLOW_WONDER`. True is valid only with
  `HYDRA_AI_MODE=local_meta`, `HYDRA_WONDER_LIVE=true`, legacy hydration false,
  and the existing global billable/live-feature consistency rule. Strictly
  validate its boolean. It only allows coexistence; all Wonder admission stays
  unchanged. Local camera always selects `LocalMetaRecognizer` and never a hosted
  recognizer. Without the explicit flag, retain the local-only startup guard.
- Keep comprehensive-analysis dispatch's existing independent flag, including
  saved replay when that flag is disabled. Do not require that flag for startup.
- Keep numerical cold-start abstention and experimental default off. Detailed
  Wonder may explain supported facts/missing information without a numerical
  workout forecast. Simulated rows never become real personal history.
- Preserve exact reference-date precision plus finite-date checks across both
  date helper APIs. Preserve camera feedback/training exports and hydration
  publication/deletion locking. No new dependencies.
- Keep local Simulator tests paused during actual local-camera demos. Run mock
  integration checks without loading the 30B runtime or triggering any provider.

## Verification and delivery

Test combined mode admission and invalid configurations, owner-only route access,
camera/financial isolation, blocked Wonder with working camera, exact consent and
saved replay using disposable stores and fake transports. Retain both backend
suites and all native tests. Exercise synthetic camera US conversion, guided
goal/context, forecast cold start, comprehensive preview/consent/replay and
correction/deletion through actual Simulator UI. Inspect the resulting screens.

Before operating port 8771, capture private metadata/digests, verify no active
inference, preserve a rollback launcher and both databases, and stage the combined
launcher from the existing camera runtime plus Wonder environment. Startup must
not change financial bytes or personal rows. Check capabilities/readiness without
inference. Then install the HealthKit-signed original bundle without uninstall or
reset, preserving its saved connection. Actual Health/weather/private-profile and
personal Wonder outcomes still need scoped owner-assisted status-only checks.

Prepare a new review PR based on the hydration head, with main ancestry included;
do not merge automatically or claim scientific validation, personal-data success,
unattended background delivery or always-on hosting from mock tests.
