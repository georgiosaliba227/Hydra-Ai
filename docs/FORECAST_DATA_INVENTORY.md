# Forecasting data inventory — verified 2026-10-28

The inventory and target definitions were completed before synthetic generation. Files were downloaded and inspected locally; listings alone do not establish training suitability. No participant records are joined across studies. ML results are research comparisons, not physiological or clinical validation. The numerical ingestion pipeline uses only the Python standard library.

## Targets and inclusion policy

| Task | Available evidence | Decision |
| --- | --- | --- |
| A: workout fluid loss | Corrected and uncorrected scale mass proxies; no fully corrected gold standard | Train separate study/target models; never relabel either target as pure sweat, fluid requirement, net balance, or dehydration diagnosis |
| B: consumption behavior | NHANES recalls; existing confirmed app logs | Keep existing descriptive intake forecast separate; no fabricated future-consumption labels |
| C: conditional fluid requirements | No suitable outcome in these sources | `insufficient_data`; no trained intake recommendation |

No effects for caffeine, creatine, HR, HRV, sleep, thirst, or electrolytes are learned from absent measurements. Neither selected workout study reports ambient temperature/humidity in the ingested records. Those factors cannot support validated adjustment or temperature-stratified accuracy.

## SpectroPhon DBM Subject Data, version 1 — included with limitations

[Michael Kirby, 2021, DOI 10.17632/jt22782wjh.1](https://data.mendeley.com/datasets/jt22782wjh/1), CC BY 4.0. Attribution permits adaptation including statistical ML; it does not independently establish participant consent or privacy adequacy.

The actual 134,859-byte XLSX contains **200 subject blocks**, although its landing page advertises 240 volunteers in a 90-minute exercise regimen. Local numeric inspection finds ages 19–54 and corrected losses 127–800 mL. Three scale readings and their mean appear at initial/intermediate/final observations. Stored total loss agrees within 1 mL with `(initial_mean_kg - final_mean_kg)*1000 + initial_water_ml - final_water_ml` for all 200 blocks. Water readings behave as remaining bottle volume; this interpretation is checked against the published corrected target. Urine/non-sweat correction is not provided.

Exported target: `corrected_mass_loss_proxy_ml`. Predictors: initial mass, age, 90-minute protocol duration. Wrist-device estimates and target components are excluded from predictors. Repeated intervals are not manufactured from undocumented timing.

**Privacy defect:** the supposedly unidentified workbook contains names. The importer never exports names or name hashes. It conservatively groups equal locally normalized private keys and all missing keys before assigning sequential study IDs: 200 records, **198 split groups**, not a verified unique-person count. Two groups each have two records. Spelling variants remain a possible unresolved linkage limitation. Raw XLSX remains outside the repository, is never sent to Meta, and should be deleted with `--delete-raw` after preprocessing.

## Quantitative Dehydration Estimation, version 1.0.0 — separate proxy task

[PhysioNet QDE, DOI 10.13026/C23082](https://physionet.org/content/qde/1.0.0/), Open Data Commons Attribution License 1.0. Attribute the database and relevant original research when reusing or reporting models. The file is 14,419 bytes: 90 observations from 10 anonymous subjects. Removing baseline targets leaves 80 cumulative observations; all intervals of each participant must remain in one split.

Protocol: eight 15-minute treadmill bouts, eight-minute measurement breaks, no fluid intake. Scale accuracy is reported as ±5 g. Age, height, running speed, mass, impedance, temperatures and laboratory markers are present. The importer uses initial mass, age, active exercise duration and speed; post-baseline scale/biomarker measurements never become predictors. Ambient temperature is not skin/ear temperature.

Target `body_mass_loss_proxy_ml` = baseline minus subsequent scale mass ×1000, using the conventional approximate kg-to-L water equivalence. This includes rest-period and non-sweat losses and lacks urine correction. Active duration excludes rests; target losses do not. It is not equivalent to the SpectroPhon target, and the studies must not be pooled as the same task. Ten people are inadequate for broad generalization or stable subgroup calibration.

Required original attribution: Ring, Lohmueller, Rauh & Eskofier (2015), *On sweat analysis for quantitative estimation of dehydration during physical exercise*, EMBC, 7011–7014; Also cite Pollard, T., Moody, B. E., Lehman, L., Gow, B., Fernandes, C., Xie, C., Johnson, A., Mark, R. G., & Heldt, T. (2026), *PhysioNet as a global platform for biomedical research*, Nature Health, https://doi.org/10.1038/s44360-026-00096-z. No biomarker-based hydration diagnosis is implemented.

## CDC NHANES 2017–2018 dietary intake — inventory only

[Official DR1TOT_J documentation](https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/DR1TOT_J.htm) and the actual 11,722,480-byte XPT were retrieved. The codebook reports 8,704 participant records, 7,484 reliable recalls, and 7,641 complete day-one intakes including breast-milk reports. These counts come from the codebook; the XPT was downloaded but not decoded by this dependency-free workout pipeline.

Food/beverage intake is interviewer-assisted 24-hour **self-report**, with nutrient/water quantities derived from food composition. Plain-water variables are in grams; total moisture and beverage volume are not interchangeable. This is not workout sweat loss or an observed required intake. Two recall days are not long personal time series. Survey weights, strata and clustering are necessary for representative statistical results.

[NCHS Data User Agreement](https://www.cdc.gov/nchs/policy/data-user-agreement.html) restricts use to statistical analysis/reporting and prohibits re-identification and linking to individually identifiable records. Statistical ML exploration is within the stated purpose; deploying individual decision models is not automatically established by that permission. No training inclusion or cross-dataset linkage here.

## Activity Skunk, Zenodo v2 — unsuitable for a fluid-loss target

[Alfonso Barragán Carmona, DOI 10.5281/zenodo.18153233](https://zenodo.org/records/18153233) and [record metadata](https://zenodo.org/api/records/18153233) establish CC BY 4.0. Actual CSV: 599,670 bytes, **16,099 rows, 14 hashed-user groups**, differing from the description's 11,625 records. Columns: intensity, heartRate, steps, hour, minute, activity, hashUser. README defines intensity 0–255, HR in bpm with a special `1` carry-forward code, and device-assigned activity categories. Activities and faulty HR are not reference truth.

No fluid intake, body-mass change, urine, sweat-loss or required-intake target exists. Age is described for the sample but not included per row. Suitable for separately attributed activity-data robustness work, **excluded from hydration training**. Do not join its anonymous users to other studies.

## USDA FoodData Central Foundation Foods, April 2026 — composition only

[Official downloads](https://fdc.nal.usda.gov/download-datasets/) and [licensing](https://fdc.nal.usda.gov/api-guide/) establish public-domain/CC0 data with requested USDA attribution. Actual JSON ZIP downloaded: 469,303 bytes; **395 food records**, no human participants. Nutrient entries include explicitly named units and composition amount; retain food IDs, data type and analytical provenance before beverage conversion. Food composition is neither intake behavior nor retained body water. No API key or paid service used. Existing nutrition implementation is preserved; this file is not a workout-label source.

## University of Costa Rica exercise hydration — excluded for startup reuse

[Aragón Vargas, Garzón Mosquera & Montoya Arroyo, 2023 dataset](https://kerwa.ucr.ac.cr/items/e54ba394-ddd6-49f1-bf5a-44d8c8b98878) and its variable-description PDF identify 16 subject codes, three conditions (water, milk, no drink), 90-minute exercise, pre/post mass kg, fluid/urine mL, temperature °C and relative humidity %. Sweat-volume estimate corrects mass change for intake and urine, but remains a mass-balance estimate. Actual 51,248-byte XLSX downloaded, with two worksheets; rows were not normalized or trained.

The live item and PDF specify **CC BY-NC-SA 4.0** (an older search snippet reported embargo). Noncommercial reuse is not a sufficient permission basis for this startup product. Excluded from shipped artifacts and training pending separate reuse permission; no request was sent to authors. It offers more complete measurement context but a small repeated-measures sample cannot establish general recommendations.

## Reproduction, privacy, and audit

`data/forecasting/sources.json` records URLs, file hashes, retrieval date and decisions. The two included-source hashes are enforced before parsing. Downloads are explicit and bounded, raw cache must be outside this repository, and CLI errors never include raw rows. The XLSX importer reads only approved cells, does not evaluate formulas/macros, and outputs only numerical measurements and anonymous study IDs. Public source data are not user HealthKit data; neither is sent to a third-party model provider.

```sh
python3 -m ai.forecasting.ingestion --download --cache-dir /tmp/hydra-public-studies --output /tmp/hydra-normalized.json --delete-raw
```

Output contains 280 records: 200 corrected-proxy records, 80 uncorrected-proxy records. The normalized row schema includes record/participant/study IDs, `synthetic: false`, target name/value/unit suffix, duration, baseline mass, age, optional speed, null ambient conditions, method, license and source SHA256. Preserve grouping and source distinctions in all splits. No raw study files or individual derived measurements are committed; reproducibility uses download hashes and transformations.
