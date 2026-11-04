# Guided beverage goal — November 3, 2026

Current installation scope: the signed combined product `4b2ac8e` is installed
and launched normally, after release of the camera check. It retains the guided
goal and local-camera features. Only the existing owner-confirmed goal integer
was carried into the previously goal-free camera backend after an explicit
notice; body/profile answers remain in their original on-device scope. The
post-update owner Home/camera check is pending. See the
[combined report](COMBINED_EXPERIENCE_2026-11-03.md).

Earlier installation scope: the camera chat restored its PR #75 build and
backend on the same phone. The guided-goal owner-assisted pass below remains
valid for source `84b7ba6`, but does not describe that restored camera build.
Hydration installs/relaunches, saved connection changes and local Simulator/UI
runs are held during its exclusive check. See the [physical scope update](PHYSICAL_HYDRATION_CHECK_2026-11-03.md).

The owner requested age/birthday, height, weight and supplement questions when
setting a goal. The new Settings/Home flow collects those answers locally,
calculates an approximate published adult beverage starting reference, and
requires explicit confirmation before changing the backend goal. Custom goals
remain available. The guided calculator is reachable offline, with storage and
backend confirmation disabled there.

## Evidence and limits

The reviewed [policy](architecture/GUIDED_GOAL_POLICY.md) uses the National
Academies' adult beverage rows directly: Men 3000 mL (101.4 US fl oz), Women
2200 mL (74.4 US fl oz), age 19+. The separate food-inclusive total-water
references are explanatory only. This is a population starting reference, not a
measured personal requirement, minimum, or hydration-status estimate.

Unknown/declined source group or applicability, under-19 age,
pregnancy/breastfeeding and clinician-directed fluid management produce no
automatic number. Height, weight and supplements are optional context and apply
no coefficient, including no creatine addition. Forecasts and Home's experimental
product score retain their existing separate meanings.

## Data and failure behavior

Birthday or self-entered age, canonical body measurements and supplement answers
remain on device. Profiles use connection-scoped protected atomic files, are
excluded from backups, and require an explicit local-storage action. Export and
current/all-profile deletion are explicit. No new HealthKit permission is added.
Only the confirmed integer goes through existing `PUT /v1/settings`; profile
answers never enter that API or a Meta request.

Invalid nonempty optional input remains invalid across unit changes. Edits
invalidate the reviewed candidate. Goal writes serialize with one another and
with deletion; reconnecting cannot release an outstanding write. Late responses
cannot update another connection. A failed confirmation preserves the local
profile and explains that the backend may have accepted the goal.

## Verification

- 254 native XCTest passed, including model, protected storage, draft, optional
  input, exact goal-only HTTP JSON, connection changes and both deletion/write
  orderings. New lifecycle tests first failed against the old behavior.
- Full pytest: 1509 passed +32 subtests; one existing Starlette/httpx warning.
- GitHub checks passed for verified documentation head `9391b19`: [iOS](https://github.com/georgiosaliba227/Hydra-Ai/actions/runs/41733190841) and [Python 3.13/3.14](https://github.com/georgiosaliba227/Hydra-Ai/actions/runs/41733190577). Later edits document the build mismatch and cold-start finding; no product code changed.
- Three actual Simulator UI flows pass (125.889 seconds total): custom-goal
  progress; offline age-only calculation with storage/confirmation disabled;
  US birthday/height/weight/creatine review, explicit confirmation, populated
  Home score and profile restoration after relaunch. Fixtures were invented,
  backend disposable, and actual financial ledger bytes unchanged. Earlier
  failed UI runs exposed native disclosure identifier inheritance, an obscured
  menu tap, and a contaminated pending-drink fixture; each was corrected before
  the passing final run.
- Independent model/store/UI and whole-branch review completed. Findings about
  ranges, stale local actions and mutation ordering were fixed and rereviewed.
- The complete app built with valid HealthKit signing and installed over the
  existing original bundle without uninstall/reset. Programmatic launch timed
  out while the device was unavailable for UI control; owner-assisted guided-form
  confirmation subsequently passed: the owner reported Goal confirmed and Home
  score appears. No personal values were requested. The final signed build was installed again after
  the presentation/test-isolation fixes, with strict signature verification.

Earlier US-unit/automatic-context verification remains separately recorded in
[its report](US_UNITS_DAILY_CONTEXT_2026-11-03.md). No new Meta inference,
financial-ledger mutation, synthetic real-profile seed, merge or deployment was
made for this feature. Genuine calibration measurements still need collection;
the actual personal aggregate-preview/consent/Wonder/replay flow remains open.

An earlier read-only check returned `account_observation_stale` while the Mac
was locked. Once it became available, the authenticated billing observation and
official pricing were genuinely renewed, preserving every existing financial row
and event and appending only one fresh immutable policy authorization. Runtime
readiness then reported ready. That account observation expires at 6:35:49 p.m. EST
on November 3 and needs rechecking before a later send. The usage dashboard was blank, so no fresh usage or
invoice-finality claim was created. Standing accepted-risk/invoice-wait waivers
remain unchanged. The owner has been asked to perform the actual personal
preview/consent/analysis flow on the phone; no operator-side provider request was
sent.

## Review handoff

[PR #77](https://github.com/georgiosaliba227/Hydra-Ai/pull/77),
`codex/guided-hydration-goal`, is stacked on PR #76 with Amine requested as
reviewer. Swift source used for this installed milestone is `84b7ba6`; later
handoff edits are docs only. The camera-restored phone currently needs a combined
build before another hydration verification.
No automatic merge was performed.
