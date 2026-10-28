# Local workout forecasting research v1

Implemented October 28, 2026. This adds reproducible offline models and a conservative application adapter; it does not replace the working accounting engine or enable Meta billing. See the [dataset inventory](FORECAST_DATA_INVENTORY.md) and [evaluation](FORECAST_EVALUATION.md).

## Separate targets and serving policy

1. The real research models forecast study-specific **mass-loss proxies in mL**, using the approximate 1 kg = 1 L water conversion. SpectroPhon corrects for recorded drinking but lacks urine/non-sweat correction. QDE does not correct urine or non-sweat loss and measures cumulative loss including rests. Their targets are not interchangeable. Neither artifact is exposed as a validated personal sweat predictor.
2. Actual consumption remains the existing confirmed-beverage accounting and descriptive logged history. No model of future behavior is claimed from these workout studies or sparse NHANES recalls.
3. Daily physiological requirements remain `insufficient_data`. There is no learned drinking target or automatic loss-to-intake conversion.

The personal application mode calls the existing `exercise_loss` envelope, including comparable-condition checks, timestamps, dry-weighing protocol, consumption/urine measurements, independent error bounds and exact unit arithmetic. A point estimate is the median of usable historical measured rates projected to the planned duration; an actual completed measurement replaces the plan. New measurements update the median and observed envelope. This is deterministic measured calibration, not population-model or clinical personalization. It stores no records. Cold start, incompatible conditions or missing uncertainty inputs return `insufficient_data`; feedback is context only.

## Real training design

The pipeline trains each study separately on only pre-exposure duration, initial mass and age. No post-workout mass, wrist-device outcome, biomarker, intake correction, subject identifier or target component enters predictors. QDE running speed is preserved for subgroup reporting but is excluded from this small model; speed is workload, not interchangeable with individual relative intensity. Environmental temperature/humidity are absent in both real datasets. SpectroPhon duration is constant at 90 minutes; it cannot identify duration response.

Participants are deterministically shuffled with seed 20261028. Train, validation, calibration and test partitions are disjoint; every visit stays with its participant group. SpectroPhon's repeated locally matched identities are kept in the same conservative group (198 groups, not a proven count of unique people). Exact repeated measurement payloads under new IDs are rejected for review. The importer’s unresolved spelling/linkage limitations still apply. No study or synthetic/real pooling is permitted.

Candidates are a learned cohort median-rate comparator, ridge (alpha 1), random forest (32 trees, depth 3, leaf minimum 3) and gradient boosting (40 trees, depth 2, leaf minimum 3). Feature imputation, centering and scaling are fit on training only. Minimum validation MAE selects the artifact; test and calibration do not influence fit or selection. Test results for all candidates are retained even when the selected model underperforms a baseline. No complex neural model is justified by these data.

Uncertainty uses maximum absolute residual per calibration participant, not per correlated row. The finite-sample rank is `ceil((n_calibration_groups+1)*0.90)`. If this exceeds available groups, there is no finite nominal 90% interval: the maximum observed calibration residual is reported as an **empirical envelope without a coverage guarantee**. The reported finite conformal intervals assume exchangeable participant groups within their source; coverage is neither clinical reliability nor cross-study generalization. Calibration curves at nominal 50/80/90%, row coverage and simultaneous participant coverage are recorded separately.

## Synthetic scenarios

The inventory and target definitions were completed before generation. Only SpectroPhon's real **training partition** anchors simulated rate/mass/age combinations; validation, calibration and test participants do not shape them. Seed 8317 generates 120 artificial profiles with deidentified mass/age covariates bootstrapped from real training anchors with four workouts each. Profiles copied from the same source anchor share a split group, so bootstrap clones cannot cross synthetic partitions. The resulting 64 anchor groups are not 120 independent human participants.

Durations 30/45/60/90/120 minutes, context temperatures 18/24/30°C, humidity 35/50/75%, categorical intensity, consumption 0/150/300 mL, 10% missing mass/age and bounded ±40 mL label noise are **software scenario choices**, not estimated population distributions, measured sensor accuracy or validated physiological effects. Mass is constructed to obey `(pre−post)*1000 + consumed − urine`; latent and noisy labels are separate. Urine is explicitly zero only in these synthetic scenarios. The anchor proxy rate’s reinterpretation as simulated loss is an explicit simulation assumption.

Temperature, humidity, intensity, caffeine, creatine, thirst, sleep, HR, HRV and electrolyte context do not alter the numerical label. No automatic physiological effect is invented. The demonstration is intended to exercise missing data, individual heterogeneity, uncertainty and UI plumbing. It cannot validate physiology. Synthetic model selection and evaluation remain separate from both real tasks.

`synthetic_demo` accepts no user exercise, samples or mass. Its server-owned fixture is 60 minutes, 70 kg, age 30, 24°C, 50% humidity and moderate intensity. The artifact is trained on simulated labels, with prominent synthetic provenance. Existing Meta mock explanations may explain this fixture using bounded signals; no actual health record is sent to Meta and live calls remain disabled.

## Dependencies, reproducibility and artifacts

Training requires scikit-learn for established ridge/tree implementations, with pinned NumPy/SciPy/joblib/threadpoolctl dependencies in `ai/forecasting/requirements-training.txt`. These are offline development dependencies, not backend runtime requirements. The application evaluates repository-owned JSON arithmetic and trees using the standard library; no pickle, executable model download or remote inference occurs.

```sh
python3.13 -m venv /tmp/hydra-forecast-venv
/tmp/hydra-forecast-venv/bin/pip install -r ai/forecasting/requirements-training.txt pytest==8.3.5
python3 -m ai.forecasting.ingestion --download --cache-dir /tmp/hydra-public-studies --output /tmp/hydra-normalized.json --delete-raw
/tmp/hydra-forecast-venv/bin/python -m ai.forecasting.reproduce --records /tmp/hydra-normalized.json
/tmp/hydra-forecast-venv/bin/python -m pytest tests/forecasting
```

Artifacts record source attribution/hash, canonical normalized-dataset hash, separate fitted-partition hash, model version, feature bounds, split evidence, parameters, seed and library versions. The output includes separate real artifacts (`spectrophon-v1.json`, `qde-v1.json`), `synthetic_demo.json` and `evaluation.json`. Raw files and normalized individual rows are deliberately not committed. Reproduction uses the checksum-verified source downloads. JSON exported predictions are checked against fitted sklearn models for every source row and missing-feature probes; tree inputs use sklearn’s float32 comparison behavior. Fixed-seed reruns in the pinned local environment reproduced all artifacts byte-for-byte. Cross-platform bit identity is not guaranteed.

This work is not externally validated; broader populations, hotter/cooler conditions, different intensity, acclimatization, clothing, equipment, illness and medication contexts remain untested. The app does not diagnose dehydration or calculate a fluid requirement from HR/HRV, supplements or a model result.

## References and attribution

- Michael Kirby (2021), [SpectroPhon DBM Subject Data v1](https://data.mendeley.com/datasets/jt22782wjh/1), DOI 10.17632/jt22782wjh.1, CC BY 4.0. Local adaptation strips identity columns, derives proxy mL and conservative grouping.
- [Quantitative Dehydration Estimation v1.0.0](https://physionet.org/content/qde/1.0.0/), DOI 10.13026/C23082, ODC Attribution 1.0; Ring, Lohmueller, Rauh & Eskofier (2015), *On sweat analysis for quantitative estimation of dehydration during physical exercise*, EMBC, 7011–7014. Adaptation derives cumulative baseline-mass-loss proxies and keeps participants grouped.
- [NATA 2017 position statement, Table 2](https://pmc.ncbi.nlm.nih.gov/articles/PMC5634236/): measured mass-balance equation; source of the existing deterministic engine, not validation of these regressions.
- [scikit-learn model evaluation guidance](https://scikit-learn.org/stable/modules/cross_validation.html): grouped evaluation; implementation uses explicit deterministic participant partitions.
