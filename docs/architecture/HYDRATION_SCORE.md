# Experimental Home hydration score

November 3, 2026. The owner chose **Experimental combined-data score** after
being offered a transparent research rubric, own-goal progress, or a
physiological estimate. This additive Home feature is not a renamed goal ring.
Its product-defined rubric is unvalidated: it does not estimate body-water
percentage, dehydration, adequacy, or a drinking requirement.

## Numerical contract: `hydration-research-score-v1`

```text
T = min(today's confirmed logged beverage mL / current chosen goal mL, 1)
C = sum(min(each previous local day's logged mL / current goal mL, 1)) / 7
M = min(valid distinct manual calibration sessions, 6) / 6
score = floor(50*T + 30*C + 20*M + 0.5)
```

Contributions remain unrounded until the final sum: 0–50, 0–30 and 0–20 points.
Above-goal volume earns no extra points. The current, explicitly user-chosen
goal is the retrospective reference for all seven previous local calendar days;
historical goal versions are unavailable. This does not imply those were the
user's goals then. Six sessions reuses the experimental fitting minimum as a
product milestone, not a physiological threshold. More records do not imply
narrower intervals or improved accuracy.

An empty successfully loaded day earns no **recorded-consistency points**;
actual consumption remains unknown. Valid empty manual history has zero
measurement-support points. Failed, corrupt, stale, loading, pending-mutation or
unavailable inputs never become zero. No goal means `goal_required`, with a link
to existing goal setup. A number requires a successfully loaded complete beverage
list, known current goal, and readable validated manual history. Filter future
logs and use timezone-aware local dates, including DST. Existing manual
protocol/error/chronology/duplicate validation defines session eligibility.
Count all valid distinct sessions without claiming comparability to a planned
workout. Planned workouts and simulated history earn no measurement points.

## Home and contextual analysis

Home displays **Hydration score**, **Experimental**, score `/100`, each component,
local date/current-goal reference, method/version and missing-data state. Use
neutral styling without medical green/red classification or body-water imagery.
Visible meaning: **Logged goal alignment, consistency and measurement support —
not hydration status or a drinking requirement**.

`Why this score?` exposes the formula, weights and inputs. Broader workout,
weather and beverage-composition context is available through the existing
comprehensive analysis workflow, linked directly from this card. These sources
receive no invented numerical weights. Raw HealthKit stays on device. Only the
validated manual-session count is needed for this score. Recalculate after
edits, deletion, goal/configuration changes, refresh, timezone/day/foreground
changes. A saved explanation always describes its dated snapshot.

## Exact preview and Muse explanation

Add authenticated `POST /v1/wonder/score/preview` and `POST /v1/wonder/score`.
Request: timezone, `measurement_count` (strict integer 0–32),
`processing_consent: true`. Backend confirmed logs/current goal determine T/C;
the validated device count determines M. No raw measurements, HealthKit, free
text or synthetic history are uploaded. Return exact versioned aggregate facts,
reproducible contributions/score, hash/token bound, live/account readiness and
saved result. Native validates against its own snapshot and displays the entire
fact tree before separate Meta consent. Changing data/day/source/connection/goal
invalidates preview/consent.

Facts contain exactly: version, local_date, timezone, goal_ml, today_ml,
previous_days (seven dated totals and logged flags), measurement_count,
components (today_points, consistency_points, measurement_points), score,
`research_only: true`. No seconds timestamp enters the payload hash. Validate
all derived fields from inputs. All numbers remain Hydra-owned. The richer
workout/weather eight-section analysis remains a separately previewed flow.

Muse's bounded strict response selects supported finding IDs and writes one
short number-free explanation per selected finding. Reject numbers, diagnosis,
medical or drinking prescriptions; Hydra independently renders fixed component
figures. Label live prose **Muse Wonder explanation**. Deterministic fallback
text must never be attributed to Muse. Explain the three components, capped
extra-volume rewards, unknown unlogged intake and unvalidated meaning.

Reuse the shared Wonder lock, exact consent/hash, single-send gateway, same
ledger, readiness, budgets and finality. Add allowlisted `personal_home_score`
purpose, never an arbitrary prompt. Default verified mode remains default.
Risk mode shares existing blockers. Preview never sends/writes financial rows.
Use `score-` protected saved results with existing export/delete and shared
publication/deletion lock. Replay is free. No retry after possible admission.
This contract does not authorize another paid request.

## Verification and limits

Test rounding/boundaries, seven local dates/DST, future logs, empty/unavailable,
changed goals, duplicate/corrupt histories, synthetic isolation, strict request
types, malicious output, consent/hash, replay/deletion/races and default-off
financial behavior. Run XCTest and actual Simulator Home/details/preview UI.
Later real observations may evaluate an explicit prospective target; synthetic
results do not establish personal or clinical accuracy.

[NATA](https://pmc.ncbi.nlm.nih.gov/articles/PMC5634236/) supports qualified
measurements, not these product weights. Published WUT research and
[Adams et al.](https://pubmed.ncbi.nlm.nih.gov/38967358/) likewise do not validate
them. This is an openly unvalidated research rubric, not physiological inference.
