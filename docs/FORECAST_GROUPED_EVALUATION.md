# Grouped forecasting research audit

Executed November 2, 2026. **The application keeps its existing personal measured-rate median and measurement envelope. Neither real study model is promoted to application serving.** QDE still fails its cohort comparator on the historical test participants. SpectroPhon supports a same-study ridge research candidate, with no independent physiological validation or intake recommendation.

This evaluation reuses the original calibration and test groups. Their earlier scores were already public within the project before this protocol was written. The new scores are a **historical holdout audit**, not a fresh confirmatory result. The selection rule was fixed before running this new real-data evaluation; no test score was used to change the candidate, hyperparameters, folds, features, or thresholds.

Machine-readable evidence is in `ai/forecasting/artifacts/grouped-v2/evaluation.json`. Separate model artifacts in that directory are marked `offline_research_only`. The original four v1 artifacts remain unchanged and reproduced byte-for-byte in the pinned environment after the fitter was extracted for reuse.

## Data and targets

The checksum-verified ingestion produced 280 real records, with no synthetic training rows and no cross-study joins. Raw downloaded files were deleted after numeric sanitization. Normalized individual records remain outside Git.

| Source | Separate target | Development rows / groups | Calibration rows / groups | Historical test rows / groups |
| --- | --- | ---: | ---: | ---: |
| SpectroPhon | Corrected mass-loss proxy, mL | 122 / 120 | 39 / 39 | 39 / 39 |
| QDE | Uncorrected cumulative mass-loss proxy, mL | 48 / 6 | 16 / 2 | 16 / 2 |

Development combines the original training and validation groups. Calibration and test memberships remain fixed. SpectroPhon has 200 records in 198 conservative identity groups, including two apparent repeats; those groups are not a verified count of unique people. Its duration is always 90 minutes. QDE has ten participants with eight cumulative post-baseline observations each during one protocol. These are **not eight independent workouts per person**. Different correction methods and exercise/rest protocols prevent treating the studies as a common physiological label. Details, source attribution and licenses remain in [the data inventory](FORECAST_DATA_INVENTORY.md).

Only pre-exposure duration, initial mass and age are predictors. Duration is required and never imputed; optional mass and age use fold-training medians. Centering, scaling, cohort rate, feature bounds and fitted coefficients/trees use fold-training data only. Participant IDs, post-exercise measurements, target components and biomarkers are excluded. QDE running speed is retained for descriptive subgroup reporting, not added as a tuned predictor.

## Selection fixed before the run

The four candidates retain the original hyperparameters: cohort median loss-rate comparator; ridge with alpha 1; random forest with 32 trees, depth 3 and minimum leaf size 3; gradient boosting with 40 trees, depth 2 and minimum leaf size 3. No new dependency or hyperparameter search was introduced.

Development undergoes three repeats of five grouped folds (or fewer folds if there are fewer than five development groups), seeds 20261028 through 20261030. Every visit of a participant stays together and each participant is held out once per repeat. For each candidate, absolute errors are averaged within participant, then across repeats, then across participants. A person with more correlated rows gets no extra selection vote.

A challenger is eligible only when its mean paired MAE gain over the cohort comparator exceeds one standard error of the participant-averaged gains. The eligible candidate with minimum participant MAE wins; exact ties favor the simpler candidate. Otherwise the cohort comparator remains the selection. This is an engineering conservatism rule, **not a significance test or confidence interval**: fits overlap and errors are dependent. It cannot turn six QDE development participants into strong evidence.

After that decision, candidates are refitted on development, the selected model is calibrated, and the historical test is scored. Failure of the selected candidate against its comparator blocks promotion; it does not trigger test-based reselection. Fold memberships, fit hashes, aggregate scores and paired-gain evidence are recorded. The design follows [grouped cross-validation and training-only preprocessing guidance](https://scikit-learn.org/stable/modules/cross_validation.html); the explicit repeated group iterator is deterministic and unit tested.

| Study / candidate | Development participant MAE, mL | Paired gain over cohort, mL | Gain standard error, mL | Eligible |
| --- | ---: | ---: | ---: | --- |
| SpectroPhon cohort | 95.46 | 0.00 | 0.00 | Reference |
| SpectroPhon ridge | **65.81** | 29.65 | 5.99 | Selected |
| SpectroPhon random forest | 72.68 | 22.78 | 6.41 | Yes |
| SpectroPhon gradient boosting | 71.14 | 24.32 | 6.04 | Yes |
| QDE cohort | 247.73 | 0.00 | 0.00 | Reference |
| QDE ridge | 259.93 | −12.20 | 65.55 | No |
| QDE random forest | 214.57 | 33.17 | 21.01 | Yes |
| QDE gradient boosting | **174.36** | 73.37 | 71.98 | Selected; marginal eligibility |

The stronger grouping rule does not eliminate QDE instability. Its boosting gain barely exceeds the heuristic threshold. That unfavorable result is preserved rather than changing the threshold after seeing it.

## Historical holdout outcomes

| Study / candidate | Rows / groups | MAE, mL | RMSE, mL | Bias, mL | Promotion decision |
| --- | ---: | ---: | ---: | ---: | --- |
| SpectroPhon ridge | 39 / 39 | 71.41 | 94.95 | −11.80 | Offline research; independent validation required |
| SpectroPhon refitted cohort | 39 / 39 | 85.72 | 119.84 | +15.76 | Reference only |
| QDE boosting | 16 / 2 | 315.09 | 447.27 | −218.50 | Fails cohort comparison; no promotion |
| QDE refitted cohort | 16 / 2 | **281.28** | **411.46** | −203.56 | Research reference retained |

For these test groups, participant MAE and row MAE coincide because every participant has the same row count within a study. That equality need not hold in other data. The QDE result is a clear reason not to promote complexity; the research artifact truthfully preserves the development-selected challenger for audit. “Baseline retained” does **not** mean that the iPhone now serves a population cohort model. Its personal engine remains separate and unchanged.

The previous published errors were SpectroPhon ridge 71.79 mL and QDE boosting 331.60 mL versus its 314.22 mL comparator. The new fits use more development data, so differences from those values do not isolate an algorithm improvement. No claim of improved physiological accuracy follows from a sub-mL change on reused participants.

## Intervals and robustness

Calibration uses maximum absolute residual per participant, not per row. With 39 SpectroPhon calibration groups, the finite 90% split-conformal rank produces radius 190.18 mL. Historical test inclusion is 36/39 = 92.31% for both rows and simultaneous participant coverage. This relies on exchangeable same-source participant groups, and does not guarantee coverage under missing or shifted measurements.

QDE has only two calibration participants. Its 628.52 mL maximum residual is an **empirical envelope without nominal 90% coverage**. Historical test inclusion is 13/16 rows = 81.25%, but only one of two participants has every interval covered: 50% simultaneous participant coverage. The machine report correctly leaves unsupported 80% and 90% conformal quantiles null. Repeated cumulative readings cannot supply missing independent calibration participants.

| Test with existing calibrated radius | SpectroPhon MAE / row inclusion | QDE MAE / row inclusion |
| --- | --- | --- |
| All original inputs | 71.41 / 92.31% | 315.09 / 81.25% |
| Mass missing | 85.77 / 87.18% | 289.76 / 81.25% |
| Age missing | 71.66 / 92.31% | 303.78 / 81.25% |
| Both missing | 84.87 / 87.18% | 278.44 / 81.25% |

These remove features from measured test records without refitting. Lower QDE error under missing inputs is not evidence that missingness helps generally; only two people were tested. Reduced SpectroPhon inclusion under missing mass shows that full-input interval calibration does not automatically transfer.

Naturally outside the final training feature bounds: one SpectroPhon test participant, MAE 82.64 mL, covered by the radius; zero QDE test participants, so its OOD metrics are undefined. One case cannot establish OOD robustness. Software sensitivity probes of ±1 kg input mass or ±1 year input age give maximum point shifts of 6.64 mL for ridge and 238.55 mL for QDE boosting. Those amplitudes are declared software probes, not measured sensor error distributions or physiological response effects. The large tree response reinforces caution.

QDE test workload strata each contain one person: 10 km/h has MAE 533.59 mL and 5/8 rows covered; 7.2 km/h has MAE 96.59 mL and 8/8 covered. This cannot separate speed from participant effects or validate intensity-specific accuracy. Both studies lack ingested measured ambient conditions and relative intensity; no weather coefficient or environment-stratified claim is supportable.

## Longitudinal and model scope

No existing real dataset supplies a verified, dated series of comparable, independently corrected workouts per participant. SpectroPhon's apparent identity repeats do not establish such histories. QDE can support exploratory **within-session** sequential estimation, but using its cumulative observations as independent longitudinal workouts would misstate the evidence. It was not repurposed that way. Real held-out workout personalization and transferable hierarchical priors remain unvalidated.

The existing [chronological evaluator and synthetic findings](FORECAST_V2_EVALUATION.md) remain separate. No actual user HealthKit records were acquired, exported or used here. Synthetic histories can check chronology, abstention and interval widening, but cannot validate adaptation to measured human changes. More observations do not establish narrower uncertainty.

Neural networks add unjustified capacity for 198 uncertain identity groups in one source and ten participants in the other. Nested hyperparameter optimization would further deplete the tiny QDE sample; this audit instead evaluates fixed candidates with repeated development-only grouped validation and separately held calibration/test groups. Cross-study validation is unavailable because target definitions differ. Nothing here estimates total body hydration, daily requirements, or a numerical drinking prescription.

## Additional public-source review

The follow-up search used original dataset repositories and research publications. It did not find a source ready to pool into either existing target. No additional raw participant dataset was committed or sent to a model provider.

| Primary source checked | Verified information | Decision |
| --- | --- | --- |
| [SpectroPhon DBM for ML](https://data.mendeley.com/datasets/bcp7snw4vr/1), McHale, Nnamoko and Sreeharsha, 2025, CC BY 4.0 | Versions derive from the same original participants and introduce extrapolated features and threshold-based labels. | Excluded as independent measured evidence; no duplicate population or invented outcome added. |
| [Individual eccrine gland rates](https://data.mendeley.com/datasets/25x3sncn8w/1), Buono, 2022, CC BY 4.0 | 500 forearm glands from five people; nL/min/gland. | Local gland secretion is not whole-body workout loss. No unsupported conversion. |
| [Physiological measurements](https://figshare.com/articles/dataset/Physiological_measurements/22811900), Dubé et al., CC BY 4.0; [study](https://pmc.ncbi.nlm.nih.gov/articles/PMC10703874/) | Ten participants, heat exposure before/after acclimation, weight change and whole-body rate. | Passive heating protocol differs from exercise. Kept separate; not training evidence for this workout target. Metadata only; numeric file not ingested. |
| [Kruijt et al. exercise thermoregulation supplement](https://doi.org/10.6084/m9.figshare.30530683), 2025, CC BY 4.0 verified through [repository metadata](https://api.figshare.com/v2/articles/30530683) | 44 people: 15 EHS, 14 MH, 15 healthy controls; 60-minute cycling test. Local first-table inspection found age, time, WBSR, ambient temperature/RH and workload headers. | Promising separate-cohort research candidate, not yet normalized/trained. Clinical selection, correction protocol, and missing baseline body-mass predictor need a dedicated study adapter/cohort audit. Only table headers/dimensions inspected; no raw file retained. |
| [Baker et al. microfluidic study](https://rogersgroup.northwestern.edu/files/2020/sciadvgssi.pdf), 2020, CC BY 4.0 | Reports a 312-person field/lab modeling task using an exercise sweat patch and other inputs. | Participant-level reusable training table was not verified; supplement retrieval was unavailable in this run. Regional sweat measured during exercise is not an available pre-workout predictor. A research follow-up candidate, not ingested. |

Existing noncommercial Costa Rica data remains excluded from startup artifacts. Reuse licenses alone do not prove consent, de-identification or compatibility. A new measured source should be normalized and evaluated as its own protocol before any compatibility claim.

## Reproduction and verification

Use the existing pinned training dependencies and an isolated Python 3.13 environment. No new numerical dependency is required.

```sh
python3.13 -m venv /tmp/hydra-ml-evidence-venv
/tmp/hydra-ml-evidence-venv/bin/python -m pip install -r ai/forecasting/requirements-training.txt pytest==8.3.5
/tmp/hydra-ml-evidence-venv/bin/python -m ai.forecasting.ingestion --download --cache-dir /tmp/hydra-ml-evidence-cache --output /tmp/hydra-ml-evidence-records.json --delete-raw
/tmp/hydra-ml-evidence-venv/bin/python -m ai.forecasting.grouped_evaluation --records /tmp/hydra-ml-evidence-records.json --output /tmp/hydra-grouped-v2
/tmp/hydra-ml-evidence-venv/bin/python -m pytest tests/forecasting -q
```

The CLI refuses the frozen artifact directory as its output. JSON models use no pickle or executable payload. Every fitted candidate is checked against sklearn predictions before export, including missing-feature probes. A repeat run is a reproducibility check of the fixed protocol, not another opportunity for selection or tuning. The artifacts contain aggregate errors, study group/split IDs and hashes, not participant outcomes or individual predictions.

Executed checks in this worktree: all 59 forecasting tests passed. Bare `pytest -q` ran 1,096 tests: 1,095 passed and one unrelated existing date-fixture test failed, `tests/recognition/test_wonder_workout.py::test_invalid_requests_are_rejected[<lambda>11]` (expected 422, received 409). Its fixed October fixture no longer represents a future session at the current wall clock; the integration branch owns that correction. The run also emitted the existing Starlette/httpx deprecation warning. No Swift or physical-device test is claimed by this ML-only change.

Two fixed-protocol grouped runs produced byte-identical model and evaluation JSON files. Separately, the extracted fitter reproduced all four original v1 artifacts byte-for-byte. Raw source cache was empty after `--delete-raw`. Compilation and `git diff --check` passed. Tests explicitly cover the red/green addition of baseline retention and paired-gain selection, grouping/all-visit isolation, equal-participant weighting, calibration/test target isolation, fit-only imputation/bounds, missing duration rejection, deterministic repeated evaluation and mismatched audit-source rejection.


## Follow-up repeated-exercise source audit

A further read-only audit checked actual public files and study protocols. No new source was normalized, trained, pooled, or enabled in the personal engine.

**Shaw et al., Figshare [19762828](https://figshare.com/articles/dataset/Data_from_Effectiveness_of_Short-Term_Isothermic-Heat_Acclimation_4_days_on_Physical_Performance_in_Moderately_Trained_Males/19762828), CC BY 4.0: deferred as a separate proxy candidate.** The downloaded 47,395-byte workbook (SHA256 `761a6c073fd6d64c41da2b76d2ed62653829134b0f5c2a8f700754f7e8696b63`) contains genuine participant rows, not summary-only tables: matching anonymous numeric IDs across HST1/HST2/HST3, with 11/12/12 complete baseline/end mass pairs. One pair has mass gain and must not be silently clipped or corrected. A second sheet has ten matched people at Day1/Day4. No absolute dates, consumed/urine volumes, instrument-error bounds, or actual early-stop durations appear in these fields. Visit order is ordinal, not a fabricated dated history. The [original paper](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0270093) specifies 90-minute planned HST cycling at 35°C/60% RH and heat-acclimation exposures at 40°C/60% RH. It describes carrying final observations forward when HST participants did not complete 90 minutes; this does not establish that mass outcomes themselves were imputed, but the observed-duration gate remains unresolved. No-fluid intake is explicit for acclimation, not clearly established for HST. Environmental setpoints are protocol context rather than per-visit measured workbook fields. Reuse permission is adequate; target correction and observation-window evidence are inadequate for treating these as corrected personal loss/rate measurements. At most, this supports a separately defined ordered visit mass-change-proxy investigation after explicit review. It does not validate the corrected personal engine.

**Foo et al., Figshare [28498148](https://figshare.com/articles/dataset/Fluid_Balance_and_Sweat_Sodium_Study_Data/28498148), CC BY 4.0: suitable-looking separate supervised source, excluded from longitudinal evidence.** The actual 166,216-byte XLSX (SHA256 `b7c0ca278355ab9c37a4eed4b22d0be4e67964929eaf5914edf24ede9fb396df`) has baseline/end mass, fluid intake, derived loss, and session-level duration/weather. Its two sessions contain 14 and 17 disjoint anonymous participant IDs, matching the [paper's 31-player description](https://journals.sagepub.com/doi/full/10.1177/17479541251353603). There are no repeated participants to train or test personal learning. The paper documents intake correction, no urination, and omitted respiratory/metabolic correction. Observed GPS work is a post-session outcome, not an available pre-workout feature. A future adapter should verify cached/formula target reconstruction and allowlist columns; it must exclude the workbook's modeled plasma sodium, assumed body-water fraction and proposed sodium requirements. No physiological recommendations are imported from that paper.

**McGregor et al., Abertay [10.57995/3dw0-d534](https://rke.abertay.ac.uk/en/datasets/data-for-the-effects-of-heat-acclimation-on-physiological-respons/), CC BY: incompatible measured target.** Both the 771,425-byte XLSX and 154,713-byte README were downloaded using the repository's public `/ws/files/` links. The workbook has repeated exercise conditions, but explicit sweat headers use local units `mg/cm²/min`. Whole-body mass-balance loss, intake/urine correction and a corresponding outcome history were not established; local patch data cannot be scaled into whole-body loss without unsupported assumptions. Exclude from this target.

**Kirby et al., Figshare [15047670](https://doi.org/10.6084/m9.figshare.15047670.v1), CC BY 4.0: aggregate supplement only.** The downloaded 79,294-byte DOCX contains three training/physiology/performance tables with means, SDs and statistical comparisons, not participant-linked repeated outcome rows. The [original study](https://link.springer.com/article/10.1186/s40798-021-00342-6) has pre/post exercise tests, but the inspected public supplement does not supply the raw records needed here. A passive intervention with an exercise outcome is not itself disqualifying; absent individual data is the gate.

Kruijt's 44-person clinical-cohort supplement remains single-exercise-test evidence without a verified repeated-workout sequence. The [46-person Dutch military repeated-heat study](https://www.tandfonline.com/doi/full/10.1080/00140139.2025.2595643) explicitly states that raw data are not public because participant consent limits disclosure. No author contact, consent workaround, or private data access was attempted. Public source files were kept outside Git for inspection, then deleted; only sanitized source metadata, hashes and inclusion decisions were retained. The audit does not establish that no suitable dataset exists, only that these checked candidates do not yet meet the complete longitudinal target contract.
