# Home hydration score — target definition and evidence

The owner added a Home-screen hydration score derived from combined data and AI
analysis to the active goal. This is an additional requirement; the existing
user-goal progress ring does not, by itself, satisfy it. The score's intended
meaning was asked explicitly while personal Wonder and simulated-training work
continues. No arbitrary physiological percentage or learned accuracy is approved
by that UI request.

## Candidate meanings under review

1. **Measurement-anchored research signal index.** Count contemporaneous
   weight/reference, first-void urine-color and thirst signals under a documented
   reference protocol. The published WUT research uses a small signal count;
   missing, stale, incomparable or threshold-uncertain observations cannot become
   zero. A usual-weight average is not automatically an established hydration
   baseline. Logged intake, workouts, weather and other HealthKit context can
   enrich the explanation without arbitrary numerical weights.
2. **Combined-data predictive research index.** Define a prospective target,
   such as the next qualified check-in's signal count, using only earlier logged
   intake, completed activity, conditions and measurements. This requires real
   dated observations and chronological validation against persistence and
   personal-frequency baselines. Simulated labels can test engineering but
   cannot calibrate a real-person hydration estimate.
3. **Own-goal progress.** The explicit ratio of confirmed beverage volume to
   the user's chosen beverage goal. This is already largely implemented and has
   a clear behavioral meaning. It is a narrower option requiring the owner's
   selection; it must not be relabeled as combined physiological hydration.

No candidate implies total body-water percentage, a diagnosis, a required intake
or an arbitrary hydration multiplier. A matched completed-workout intake/loss
ratio is useful context but is not all-day hydration state.

## Shared implementation requirements

- Place a distinct **Hydration score** card on Home, with method/version,
  provenance, timestamp and current/partial/unavailable state visible.
- Freeze the target, input protocol, units, missingness/error handling,
  eligibility and exact calculation before implementation. Do not let Muse invent
  the number. Use AI to explain supported findings, missing data and uncertainty.
- Integrate all available relevant sources with their roles explicit: confirmed
  drink totals/composition, actual versus planned workouts, available individual
  measurements, consented environmental context and validated saved AI analysis.
  Context fields need not all change the numeric score without evidence.
- Distinguish observed, inferred and simulated data. Never train/score personal
  history as if a Muse-generated record were an actual measurement.
- Keep raw HealthKit records on device. Require explicit processing and exact
  aggregate-preview consent for any backend/Meta data flow. Store opt-in manual
  records with the same protection, export/deletion and connection boundaries as
  the existing calibration history.
- Invalidate stale scores/explanations after edits, new data, timezone/day or
  connection changes and deletion. Unknown inputs remain unknown.
- Verify boundary/error/timing cases and the actual Home UI; a research score
  must not become a green/red medical classification or a hidden drinking target.

## Primary evidence

[NATA's position statement](https://pmc.ncbi.nlm.nih.gov/articles/PMC5634236/)
supports multiple contemporaneous indicators and qualified reference
measurements, not an intake-only status estimate.
[Keefe et al.](https://www.cambridge.org/core/journals/british-journal-of-nutrition/article/weight-urine-colour-and-thirst-venn-diagram-is-an-accurate-tool-compared-with-urinary-and-blood-markers-for-hydration-assessment-at-morning-and-afternoon-timepoints-in-euhydrated-and-freeliving-individuals/C0D9FDFD4A482C9A930CB5703253393C)
studied the WUT framework in a defined protocol/population; its accuracy varies
with comparator and measurement conditions.
[Adams et al.](https://pubmed.ncbi.nlm.nih.gov/38967358/) does not supply portable
app coefficient weights, and
[Anderson et al.](https://doi.org/10.1159/000520317) reports validation limitations
for models using body mass, urine color and thirst. These papers do not validate
a universal 0–100 score from the app's current logs/workouts/weather alone.

The Home requirement remains incomplete until its intended target is settled,
implemented and verified. This design inventory is not a completion claim.
