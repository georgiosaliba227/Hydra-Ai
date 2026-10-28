# Workout forecasting evaluation — October 28, 2026

These are local, reproducible **research results**, not validated physiological forecasts. Real studies measure different mass-loss proxies; no score is presented as pure sweat-loss or drinking-requirement accuracy. All comparison values below are mL. Machine-readable splits, metrics, subgroup results and calibration curves are in `ai/forecasting/artifacts/evaluation.json`.

## Real data: independent held-out participants

| Study / target | Fit / validation / calibration / test groups | Selected on validation | Test rows | MAE | RMSE | Bias |
| --- | --- | --- | --- | --- | --- | --- |
| SpectroPhon, corrected mass-loss proxy | 81 / 39 / 39 / 39 | Ridge | 39 | 71.79 | 96.10 | −20.36 |
| QDE, cumulative uncorrected mass-loss proxy | 4 / 2 / 2 / 2 | Gradient boosting | 16 | 331.60 | 517.69 | −300.72 |

SpectroPhon has 200 records in 198 conservative identity groups; 82 training records and 40 validation records reflect repeated measurements kept together. Its 90-minute duration is constant, so the model cannot establish duration effects. QDE has 80 records from only ten subjects; records within a subject are cumulative and correlated, not 80 independent subjects. Active exercise minutes exclude rest while measured mass loss includes rests.

| Candidate | SpectroPhon validation MAE | SpectroPhon test MAE / RMSE | QDE validation MAE | QDE test MAE / RMSE |
| --- | --- | --- | --- | --- |
| Cohort median-rate comparator | 71.71 | 84.35 / 119.21 | 284.84 | **314.22 / 477.48** |
| Ridge | **54.72** | **71.79 / 96.10** | 288.32 | 449.18 / 487.76 |
| Random forest | 73.33 | 81.02 / 101.77 | 237.02 | 337.80 / 495.78 |
| Gradient boosting | 70.53 | 79.15 / 98.09 | **151.51** | 331.60 / 517.69 |

QDE’s validation-selected boosting model performs **worse than the cohort-rate comparator on the untouched test subjects**. It remains the recorded validation choice; choosing the test winner would introduce selection bias. This is evidence against claiming a reliable upgrade. SpectroPhon’s improvement is limited to one same-study split and target, with unresolved participant-linkage and protocol limitations.

The existing deterministic engine is a distinct comparator. It returns `insufficient_data` without a previous comparable personal measurement and independent error bounds; these study records cannot supply that prospective input. Its cold-start prediction coverage is zero and MAE is undefined. Reconstructing a target from post-workout mass would leak the answer and is not a valid forecasting baseline. The learned cohort-rate comparator does not replace that engine.

## Intervals, calibration and robustness

SpectroPhon calibrates maximum absolute residuals over 39 held-out participant groups. A nominal 90% split-conformal radius is 197.53 mL. Test row and simultaneous participant coverage are both 94.87% (37/39). This depends on exchangeable same-source participants; it does not establish external, clinical or temperature-specific calibration.

QDE has only two calibration subjects. A finite 90% conformal rank is unavailable, so its 748.31 mL radius is an empirical calibration envelope **without a nominal coverage guarantee**. Test row coverage is 81.25% (13/16), while simultaneous participant coverage is only 50% (one of two). Counting correlated rows alone would overstate evidence.

| Robustness check | SpectroPhon | QDE |
| --- | --- | --- |
| Missing mass + age test MAE / RMSE | 82.74 / 118.81 | 278.44 / 399.52 |
| Missing mass + age interval row coverage | 87.18% | 93.75% empirical |
| Test rows outside training feature min/max | 1 | 8 |
| Outside-range MAE / RMSE | 99.65 / 99.65 | 33.48 / 37.98 |

The outside-range samples are sparse opportunistic checks, not validated OOD robustness. Better QDE missing-input scores do not justify a post-hoc feature choice. There is no independent compatible study holdout, environmental-temperature/humidity subgroup, or measured relative-intensity outcome. QDE workload-speed strata are reported separately in JSON but contain very few subjects. No temperature/intensity generalization claim is possible.

## Synthetic evaluation — separate from real results

After the inventory and real target definitions, the generator produced 480 synthetic scenarios (120 artificial profiles × four workouts). Baseline mass/age and proxy-rate anchors come only from SpectroPhon’s real training partition. Clones share source-anchor split groups: 64 groups split as 28 training, 12 validation, 12 calibration and 12 test. Therefore 120 profiles do not mean 120 independent people. Real test labels never inform generation or selection.

| Candidate | Validation MAE | Synthetic test MAE / RMSE |
| --- | --- | --- |
| Cohort median rate | 112.17 | 90.63 / 130.25 |
| Ridge, selected | **80.27** | 68.60 / 102.20 |
| Random forest | 82.69 | 70.84 / 107.40 |
| Gradient boosting | 84.89 | 67.68 / 104.95 |

The selected ridge test has 64 scenarios in 12 anchor groups, 98.44% row coverage and 91.67% simultaneous anchor-group coverage. As with real selection, the test-best MAE model does not replace the validation-selected model. Missing mass/age MAE is 89.00 mL; outside-training-range MAE is 139.72 mL over seven scenarios. These scores verify behavior against generated labels only and provide **no physiological accuracy evidence**. Context temperatures, humidity, intensity and supplements have no modeled causal effects.

## Verification actually performed

- 33 forecasting runtime/training tests passed in the pinned Python 3.13 offline environment. Covers units/metrics, grouping, re-identified exact duplicates, no study/target/origin pooling, invalid numbers, future/duplicate calibration samples, cold start, measured adaptation, corrupted artifacts, fixture-only demo and independence of test labels from fitting/selection/calibration.
- Both real sources and the synthetic experiment were reproduced twice; all four JSON artifacts compared byte-for-byte equal in the pinned environment.
- JSON predictions matched fitted sklearn implementations for every source row plus missing-feature probes. Tree comparison inputs preserve sklearn float32 behavior. Checks reject nonfinite outputs.
- Final full reproduction passed with `RuntimeWarning` treated as an error. Earlier batched ridge parity probes produced local NumPy/Accelerate floating-point warnings despite finite parity results; single-request-shaped parity probes resolved these warnings without changing artifacts.
- Data ingestion, backend and native-app checks are reported separately by their owning integration work. No physical-device test, paid call, live Meta explanation, external population validation or clinical study was performed by this pipeline.

There is enough evidence to ship a transparent research demonstration and keep the existing measured personal fallback. There is not enough evidence to ship a generic learned sweat-loss forecast or a fluid-intake recommendation.
