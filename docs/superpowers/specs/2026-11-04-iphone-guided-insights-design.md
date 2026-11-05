# Guided setup, direct local analysis and connected insights

## Latest owner steering

The owner requested research and validation of a new individualized goal method
first. The evidence assessment (including 2026 studies) did not establish a
validated profile-to-beverage-goal method. After reviewing that result, the owner
explicitly selected **a clearly labelled adult starting reference, reviewed and
confirmed by the user**, while individualized goal research continues. Restore
the earlier method under that label; never present it or a water-turnover proxy
as a measured personal requirement. No numerical supplement adjustment is added.

The owner requested restoring the earlier biometric setup, making the circle fill
from its saved goal, removing the local photo permission checkbox, and connecting
Trends, Ask Hydra and related backend features. The supplied Today screenshot
shows no saved goal. The water renderer itself is already tested and installed.

## Confirmed interim setup design

Reuse the reviewed goal/profile implementation from `codex/preserve-combined-latest`
(`e9b8dde`, originating at `84b7ba6`) without importing the unrelated financial or
model policy stack. Collect age/birthday, source applicability, optional height,
weight and supplement context during setup. Generate the existing published adult
starting reference, show its source and assumptions, and let the user adopt/edit
it. Height, weight and supplements do not receive invented numerical coefficients.
This remains a starting reference, not a validated individual requirement.

Profiles remain protected on the phone. Give on-device logging its own stable
profile scope; preserve existing server-scoped profiles without copying them.
Adopting a reference saves through the selected logging service, so local mode
updates its local goal and circle without a backend. Offer setup on first use and
from Today/Settings. Keep custom goals and the option to skip.

## Analyze by tapping Analyze

In on-device mode the Analyze tap expresses the analysis request. Remove the
extra local toggle and use the short Analyze title. Keep OS camera permission,
Confirm/Edit, stale-session checks, one analysis in flight and separate server/
Meta consent paths. Selecting a photo never starts inference automatically.

## Connect backend features independently

Keep camera/logging/history/goal/export/delete local in on-device mode. Add a
separate optional backend connection for insights. Do not simply display the
server's separate history as the phone's history. Establish a bounded versioned
ephemeral aggregate-input contract before implementing phone-log insights:
explicitly requested local drink summaries, no photos, profiles, raw HealthKit,
recognition receipts, record migration or persistence. Use the existing nonbillable
reviewed assistant and deterministic calculations. Paid explanation actions keep
their existing preview/consent/budget gates; this work makes no provider calls.

## Approach and verification

Selected implementation approach: restore the existing goal modules narrowly,
then adapt their destination boundary. A wholesale branch merge would import
hundreds of unrelated files and financial policy changes; replacing profile setup
with a new heuristic would discard the prior reviewed method. The routing and
ephemeral-summary boundary are implementation choices by the integrator.

Verify setup-to-circle and one-button real local inference in simulator UI tests;
test profile protection/scoping and mutation/stale-result guards. Test insights
with synthetic payloads through the real backend and reject unknown/private input
fields. Run relevant XCTest and the full Python suite, review the integration,
build/sign and install in place. Distinguish physical checks from simulator tests.
