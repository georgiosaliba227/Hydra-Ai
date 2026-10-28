# Forecasting v2: longitudinal calibration and comparative evidence

## Decision

**No real-world predictive improvement is established in v2.** Existing research
models, participant splits, fitted preprocessing, and study artifacts are frozen.
The existing v1 numerical baseline remains available and unchanged. The new v2
method is an explicitly experimental option for caller-supplied chronological
personal history, not a replacement clinically validated model.

Synthetic gradual/abrupt-change scenarios show lower point error with the new
rule. **Stable-history error gets slightly worse, and gradual-change interval
coverage is only 45.45%.** These are reasons to retain the baseline and avoid
claims that the new method reliably predicts physiology or supplies a calibrated
future prediction interval.

## Frozen real-data comparison

These are the previously evaluated results, read from
`ai/forecasting/artifacts/evaluation.json`; no test labels were used to tune a new
model, window, prior, or threshold. No real-data retraining took place in v2.

| Study / candidate | Validation MAE, mL | Test MAE, mL | Test RMSE, mL | Test bias, mL |
| --- | ---: | ---: | ---: | ---: |
| QDE cohort-rate comparator | 284.84 | 314.22 | 477.48 | -289.06 |
| QDE ridge | 288.32 | 449.18 | 487.76 | +118.03 |
| QDE random forest | 237.02 | 337.80 | 495.78 | -254.14 |
| QDE gradient boosting, selected on validation | 151.51 | 331.60 | 517.69 | -300.72 |
| SpectroPhon cohort-rate comparator | 71.71 | 84.35 | 119.21 | +9.92 |
| SpectroPhon ridge, selected on validation | 54.72 | 71.79 | 96.10 | -20.36 |

The QDE selected model is worse than its cohort comparator by 17.39 mL MAE on the
frozen test set. That is an observed result, not proof of a causal mechanism or a
reason to reselect on that test. The cohort comparator remains a research
reference; it is not silently substituted for the existing deterministic personal
calibration engine in the product.

### Why the QDE result is fragile

- Ten participants contribute 80 cumulative observations; the split contains
  **four training, two validation, two calibration, and two test participants**.
  Eight correlated observations from one person are not eight independent people.
- The target is uncorrected cumulative scale-mass loss during exercise plus rest
  periods, not pure sweat or a fluid requirement. Intake is absent by protocol;
  urine and other mass changes are not fully accounted for. Scale accuracy alone
  does not quantify all target error.
- The selected model's two test participants have very different errors. Running
  speed, protocol workload, individual sweat patterns, and other missing factors
  could matter, but this sample cannot isolate their effects. The fitted model
  uses duration, initial mass, and age; no claim of validated environmental or
  heart-rate effects follows.
- Only two calibration participants cannot establish the intended 90% conformal
  quantile. The artifact correctly uses an empirical envelope, with no nominal
  coverage claim. Observed test record coverage is 81.25%, whereas simultaneous
  participant coverage is 50%.
- Subject grouping avoids interval leakage, and study targets remain separate.
  This does not establish external validity: there is no independent compatible
  study validation. Combining the 200 differently corrected SpectroPhon records
  with QDE would not solve that problem.

These diagnoses are limitations and plausible explanations, not independently
confirmed causal findings. Study methods, permissions, measured-vs-derived
quantities, and source count discrepancies remain documented in
[the dataset inventory](FORECAST_DATA_INVENTORY.md). No new participant data or
identifiers were acquired for v2.

## Longitudinal numerical interface

`ai.forecasting.longitudinal.predict_longitudinal(exercise, samples,
generated_at=...)` accepts the same validated `Exercise` and `SweatSample` objects
as the original engine. The caller owns, separates by person, and retains history.
The function has **no disk, database, network, Meta, or financial-ledger access**.
It does not persist automatic learning or export HealthKit records. A UI/backend
integration must truthfully distinguish supplied history from stored history.

Behavior is fixed before evaluation:

1. Validate timestamps and order observations by UTC, including daylight-saving
   folds. Historical observations must strictly precede generation time. Copied
   same-time measurements with different IDs are rejected; the existing engine
   continues to reject duplicate event IDs, missing measurement protocols,
   inconsistent mass balance, invalid inputs and unusable error bounds.
2. Use exact existing activity/intensity/environment matching and explicit
   comparability confirmation. Different or missing conditions do not establish
   comparable evidence. No HR/HRV, caffeine, creatine, or thirst multiplier exists.
3. With no usable comparable measurements, return `insufficient_data`. With one or
   two, retain the baseline point and disclose limited history. The threshold is
   an engineering rule, not an evidence-based claim of physiological sufficiency.
4. With at least three usable comparable observations, project the median of the
   **most recent five** measured rates to the planned duration. Five is a fixed
   illustrative engineering window, not chosen by maximizing test results. No
   population prior or Bayesian shrinkage was invented: the study proxies cannot
   justify a transferable prior for fully corrected personal measurements.
5. Keep the entire existing historical measurement envelope. Also compute each
   past one-step error using only rates available before that observation; the
   maximum absolute rate error, scaled to planned duration, may widen the range
   around the current center. The final range is the union. No narrow uncertainty
   is manufactured merely because the sample count grows.
6. Preserve a completed actual outcome through the original engine; a learned
   point never overwrites it. Personal estimates remain separate from consumption,
   net balance, daily requirements, and recommended drinking.

The result retains v1 numeric fields/units and adds `longitudinal_history` counts,
UTC first/last timestamps, method, and caller-retention status. Planned adaptive
results use model version `personal-longitudinal-v2` and range kind
`historical_error_envelope`. Actual results preserve the original actual-result
model/range semantics. No numeric confidence percentage is supplied.

Old observations are not silently decayed or forgotten. The recent-window center
can respond to change, but the full-history range remains conservative relative
to the old measurement envelope. It may still fail to cover new changes: neither
known instrument bounds nor historical residuals capture all future variation.
Staleness, acclimatization, clothing and unreported context remain limitations.

## Chronological synthetic evaluation

Reproduce without scientific/ML dependencies or network calls:

```sh
python3 -m ai.forecasting.longitudinal --output /tmp/hydra-longitudinal-evaluation-v2.json
```

Seed `20261029`; four separately labeled software scenarios; ten invented users
per scenario, twelve 60-minute workouts per user. Each forecast is made at workout
start using only earlier completed samples; only after prediction is its mass
outcome revealed and scored. The evaluator assumes planned duration and conditions
were known beforehand. It never passes current post-workout mass, intake, or target
loss to either forecasting function. Histories stay separated by participant.

Scenario assumptions are **invented test trajectories**, not empirical physiology:
base rates `300 + 20*user` mL/h; uniform ±15 mL observation noise; assumed ±10 g
bounds per weighing; gradual +35 mL/h each workout; abrupt +250 mL/h after six;
condition-shift changes the condition label after six. The association with a
new temperature label is a test of matching and abstention, not a temperature
response formula. No study holdout values informed these scenarios.

| Scenario | Scored / attempted | Baseline MAE | Adaptive MAE | Baseline RMSE | Adaptive RMSE | Baseline range coverage | Adaptive range coverage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Stable | 110 / 120 | 8.51 | 8.81 | 10.28 | 10.68 | 99.09% | 99.09% |
| Gradual change | 110 / 120 | 121.47 | 88.17 | 134.23 | 92.53 | 9.09% | 45.45% |
| Abrupt change | 110 / 120 | 136.91 | 73.35 | 180.03 | 128.65 | 90.91% | 90.91% |
| Condition shift | 100 / 120 | 7.68 | 7.68 | 9.39 | 9.39 | 98.00% | 98.00% |

Errors are mL. Coverage is empirical inclusion of the simulated noisy mass-balance
outcome among scored predictions, **not a calibrated nominal prediction interval**.
The initial workout abstains; condition-shift scenarios also abstain at the first
workout under unmatched conditions. The JSON report includes bias, prediction
coverage, per-user error changes, ordered prediction records, and all assumptions.
The fixed rule was not selected on these results. Stable regression is retained;
no iteration sought to turn every metric positive.

No real longitudinal performance result is reported: QDE intervals are cumulative
within one protocol, and SpectroPhon lacks a verified dated sequence of comparable
fully corrected individual workouts. Those records cannot be repurposed as
independent repeated calibration visits. User-calibration evaluation is supported
by the same prequential function but has **not** been run on actual user health
records in this execution.

## System A / B / C interpretation

A is the unchanged existing numerical baseline. B is contextual interpretation,
whose explanations have separate groundedness/abstention evaluation and do not
supply a numerical outcome. C may expose this experimental chronological numerical
option alongside guarded interpretation. Any numerical difference between A and C
comes from the explicit recent-history rule, **never from a Meta-authored number**.
If C combines explanation with the unchanged A calculation, its numbers must
remain identical. No live Meta model comparison or paid call is part of this
numerical evaluation, and no real improvement is attributed to Meta.

## Validation and limits

New tests cover cold start, fixed recent-history behavior, interval containment,
order invariance, daylight-saving chronology, incomplete/unmatched samples,
duplicate-copy rejection, future observations, actual-outcome preservation,
prequential label withholding, and deterministic simulation. Existing v1 tests and
research artifacts remain in place. The standard `pytest tests` suite is the
product suite; bare `pytest` also collects the archived starter project and fails
at `Hydra-Ai-Starter/tests/test_forecast.py` (`ai.forecast` import collision).
That pre-existing collection issue is reported, not hidden or changed here.

Executed in this worktree: 11 new tests passed; product suite 546 passed,
1 skipped, 32 subtests passed, with the existing Starlette/httpx deprecation
warning. The isolated starter suite passed 3 tests. The skipped product module
requires the optional offline ML-training environment; no retraining is performed
by the v2 adapter.

Scientific next steps require independent repeated comparable measurements,
predeclared evaluation, and honest prospective coverage results. Better synthetic
scores alone do not justify production promotion, numerical recommendations,
external health-data disclosure, or paid Meta use.
