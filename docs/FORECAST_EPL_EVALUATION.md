# EPL exercise mass-loss research evaluation

Executed November 2, 2026. A third, separately trained real-data experiment now uses the EPL fluid-balance study. **The fixed selection rule retains its learned cohort-rate baseline.** More complex candidates did not establish sufficient development improvement. The application still serves its existing personal measurement engine; this model is offline research only.

The main held-out scores below are the first model scores generated for these prespecified test participants in this work. The protocol and candidate hyperparameters were fixed before the run. They establish a small same-study result conditional on supplied duration, not independent physiological validation, a drinking target, or longitudinal personal learning. No models or targets were pooled across studies.

## Source and measurement contract

Source: Wee Lun Foo et al., [Fluid Balance and Sweat Sodium Study Data](https://figshare.com/articles/dataset/Fluid_Balance_and_Sweat_Sodium_Study_Data/28498148), DOI 10.6084/m9.figshare.28498148, **CC BY 4.0**, with attribution to Foo, Tester, Markakis, Sabou, Close, McCubbin and Morton (2025). Original study: [Should sports scientists and coaches provide sodium supplementation to professional soccer players? Insights from English premier league players](https://journals.sagepub.com/doi/full/10.1177/17479541251353603), DOI 10.1177/17479541251353603. The study's nutritional recommendations and modeled quantities are not imported.

The pinned [public XLSX](https://ndownloader.figshare.com/files/52631492) is 166,216 bytes, SHA256 `b7c0ca278355ab9c37a4eed4b22d0be4e67964929eaf5914edf24ede9fb396df`. The loader verifies both size and hash before parsing. It uses standard-library OOXML reading without executing formulas, macros or external relationships. The download is bounded and requires an owned private cache outside the checkout. Normalized per-person records also remain outside Git. The raw file was deleted after successful preprocessing.

| Session | Independent people | Reported duration | Shared temperature | Shared relative humidity |
| --- | ---: | ---: | ---: | ---: |
| Conditioning session | 14 | 84 min | 19°C | 45% |
| Match-day-minus-two session | 17 | 75 min | 23°C | 67% |

These are **31 different people**, not repeated workouts for the same people. Every source identifier in the two admitted sheets has the anonymous `Participant N` form; the two sets are disjoint. The adapter emits study-prefixed numeric IDs and no participant names. The demographic worksheet, unused rows, GPS outputs and modeled fields are not copied.

All 31 rows contain age, baseline/end body mass, intake and a source loss/rate pair. The imported target is `intake_corrected_mass_loss_proxy_ml`:

```text
loss_proxy_mL = (pre_mass_kg - post_mass_kg + consumed_fluid_L) * 1000
```

The methods document towel-dried minimal-clothing mass, bottle-weighed intake, prior voiding and **no urination during training**. Zero urine is a reported protocol observation, not an invented missing value. Respiratory and metabolic mass changes were ignored, and clothing effects and individual measurement error remain unresolved. No independent per-person error bounds are supplied. This is an intake-corrected mass-balance proxy, not direct pure sweat or total body hydration. The loader checks every target reconstruction within 0.000001 mL and every loss/duration-rate relation within 0.00000001 L/h. Missing caches, duplicate/nonanonymous IDs, changed headers/context or inconsistent target/rate values fail closed without printing raw cells.

Only **duration, initial mass and age** enter the existing four-candidate training pipeline. Post mass and consumed fluid derive/check the label but are absent from normalized predictor fields. Weather is retained as explicitly shared session context and is not a model feature. No modeled TBW, sodium requirement, plasma sodium estimate, patch chemistry or current-session GPS metric enters a prediction.

The source reports session duration, but does not establish that 84/75 minutes were fixed and known prospectively. Evaluation therefore conditions on retrospectively supplied duration as if supplied for a plan. It does not demonstrate verified pre-workout availability. Weather, duration, intensity and session cohort change together, preventing causal interpretation of environmental differences.

## Fixed participant-grouped design

Seed 20261028 creates disjoint groups: **19 development, six calibration and six test participants**, one record each. Development combines the original splitter's train/validation membership; all calibration/test people remain excluded from fitting and model selection. Three repeated five-fold participant-grouped development validations fit their own medians, standardization and model parameters. Fixed candidates are:

- Cohort median loss rate multiplied by supplied duration.
- Ridge, alpha 1.
- Random forest, 32 trees, depth 3, minimum leaf size 3.
- Gradient boosting, 40 trees, depth 2, minimum leaf size 3.

A challenger must have mean paired participant MAE gain greater than one participant-level standard error before it can displace the comparator. Repeated errors are averaged within person first; overlapping folds are not independent replications. This is an engineering heuristic, not a confidence interval or significance test. Eligible minimum participant MAE wins, with simplicity resolving exact ties. No test outcome or session-shift score changes selection or hyperparameters.

| Candidate | Development participant MAE, mL | Gain over baseline, mL | Gain standard error, mL | Eligibility |
| --- | ---: | ---: | ---: | --- |
| Cohort baseline | 444.11 | 0.00 | 0.00 | **Selected** |
| Ridge | 466.93 | −22.82 | 61.83 | No |
| Random forest | 439.81 | +4.31 | 34.76 | No |
| Gradient boosting | 489.36 | −45.25 | 51.41 | No |

The forest's tiny point improvement is insufficient under the predefined rule. It is not promoted because it is more complex. The refitted selected rate is 22.345238095238095 mL/min, fitted to development outcomes only; it is a learned study comparator, not a fixed biological coefficient or fluid-intake requirement. The model and machine report are `ai/forecasting/artifacts/epl-v1/model.json` and `evaluation.json`.

## Held-out result and uncertainty

| Selected cohort baseline | Value |
| --- | ---: |
| Test participants / records | 6 / 6 |
| MAE | 355.70 mL |
| RMSE | 464.80 mL |
| Bias | −241.07 mL |
| Empirical calibrated radius | 1,475.11 mL |
| Observed row / simultaneous participant inclusion | 6/6 / 6/6 |

With only six calibration people, `ceil((6+1)*0.90)=7` exceeds the available scores. **There is no finite nominal 90% conformal interval.** The maximum observed calibration error is an empirical envelope, and six covered test people do not establish reliable 100% future coverage. Numerical reports retain `nominal_coverage: null`. Calibration curves at 50/80/90% are reported separately; the unsupported 90% quantile remains null.

One naturally out-of-training-range test participant has MAE 120.00 mL and is inside the empirical envelope; this single case cannot establish OOD validity. Missing mass, missing age, both missing, and the ±1 kg/±1 year sensitivity probes leave the selected point unchanged because the retained cohort-rate model does not use those covariates. This does not establish robustness of the rejected multivariable candidates, or to missing duration. Duration remains required.

The test contains two people from session one (MAE 294.00 mL) and four from session two (MAE 386.55 mL). These tiny same-session subgroups do not support weather-specific or activity-wide accuracy claims. There are only two shared environmental contexts, not 31 independent climate experiments.

## Prespecified shifted-session sensitivity

Separate fixed-candidate fits train on all people in one session and predict all different people in the other. There is **no candidate selection, tuning or interval calibration** in this diagnostic. It was specified before these scores were generated and did not alter the main result. It reuses people also appearing in the main partitions, so it is an additional sensitivity analysis, not another independent replication.

| Direction | Training / target people | Candidate | MAE, mL | RMSE, mL | Bias, mL |
| --- | ---: | --- | ---: | ---: | ---: |
| Session one → two | 14 / 17 | Cohort | 507.68 | 671.03 | −352.05 |
| Session one → two | 14 / 17 | Ridge | 427.10 | 511.68 | −69.06 |
| Session one → two | 14 / 17 | Forest | 442.54 | 530.56 | −114.84 |
| Session one → two | 14 / 17 | Boosting | 464.81 | 542.68 | −39.53 |
| Session two → one | 17 / 14 | Cohort | 474.06 | 589.10 | +346.74 |
| Session two → one | 17 / 14 | Ridge | 409.69 | 470.29 | −16.02 |
| Session two → one | 17 / 14 | Forest | 383.05 | 442.88 | +55.20 |
| Session two → one | 17 / 14 | Boosting | 399.41 | 467.11 | −42.09 |

Every target person in each direction is outside the source session's single-duration range. Different duration, conditions, intensity and participant composition move together. Lower diagnostic error for a complex model does not select it, establish a weather effect, or override the development-only baseline decision. No interval coverage is claimed from one training session. No SpectroPhon transfer result or cross-study pooling is manufactured.

## Reproduction and limits

The optional commands leave the original two-study CLI and frozen artifacts unchanged. Use the existing pinned Python 3.13 offline training dependencies; the backend has no new dependency.

```sh
python3.13 -m venv /tmp/hydra-epl-venv
/tmp/hydra-epl-venv/bin/python -m pip install -r ai/forecasting/requirements-training.txt pytest==8.3.5
/tmp/hydra-epl-venv/bin/python -m ai.forecasting.epl_ingestion --download --cache-dir /tmp/hydra-epl-cache --output /tmp/hydra-epl-records.json --delete-raw
/tmp/hydra-epl-venv/bin/python -m ai.forecasting.epl_evaluation --records /tmp/hydra-epl-records.json --output /tmp/hydra-epl-result
/tmp/hydra-epl-venv/bin/python -m pytest tests/forecasting -q
```

To produce repository-owned research artifacts explicitly, the only admitted directory inside existing artifacts for this command is `ai/forecasting/artifacts/epl-v1`. JSON contains model parameters, aggregate errors, split evidence and hashes, not individual outcomes or raw records. Source file, source target/rate reconciliation, fitted-library JSON parity and deterministic reproduction are checked. The source is a narrow elite male professional-football cohort; six test people and two sessions cannot establish general physiology, longitudinal learning, calibrated future uncertainty or intake planning. No Meta request, private user data, ledger access, deployment or application serving change occurs.

Executed verification in this isolated branch: **71 forecasting tests passed**, including 12 new ingestion/evaluation cases. The full Python suite ran **1,107 passed and one failed**: the same previously identified `tests/recognition/test_wonder_workout.py::test_invalid_requests_are_rejected[<lambda>11]` date fixture (expected 422, received 409), already corrected separately on the integration branch. This work does not modify that unrelated test. The existing Starlette/httpx deprecation warning remains. Both EPL model/report files reproduced byte-for-byte in a second fixed-protocol run; all four original v1 outputs also reproduced byte-for-byte and every tracked earlier artifact was unchanged. Compilation and `git diff --check` passed. The public raw cache was empty after processing, and normalized local records had mode 0600. No iPhone/simulator/live-Meta verification is claimed by this ML-only work.
