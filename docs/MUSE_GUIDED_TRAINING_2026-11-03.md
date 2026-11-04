# Actual Muse-guided synthetic training — November 3, 2026

One real `muse-wonder-1.0` Standard request selected the bounded simulation
recipe. Hydra then generated numerical labels and trained the research model.
This is distinct from the earlier offline-stub run; neither dataset represents
the owner's actual measurements. The result stays excluded from personal
serving and never replaces the existing iPhone baseline.

## Provenance and inference

- Fixed public-only payload SHA256:
  `291df38fc74751e3347db1935d9326bcb084818e4e12106a48bfdf34d23ae7e4`.
- Muse selected weight **1** for each of base, missing covariates, wide noise
  and outlier recipes. It supplied no physiological coefficients or loss labels.
- Provider reported 230 input / 219 output tokens and 2,683 ms latency. The
  published-rate token estimate is **$0.005300**, below the prepared $0.019308
  bound. Actual final charge remains null; the complete $0.25 reservation stays
  held. No retries, tools, personal records or HealthKit uploads occurred.
- The owner explicitly extended the billing-wait waiver to ongoing Wonder.
  Unknown billing/status remained unverified, not clear/final. The existing
  authoritative ledger recorded the exact policy, consent, usage, checked output
  and publication linkage. Every pre-existing financial row was checked unchanged.
- Model origin was verified against that ledger read-only before training;
  a standalone JSON file cannot establish a live Muse origin.

Current [Meta prices](https://dev.meta.ai/docs/pricing-rate-limits), checked on
November 3, are $4 input / $20 output per million Wonder Standard tokens. These
local token counters are not a hard cap on owner-accepted unverified extras.

## Frozen experiment

The public SpectroPhon source contains 200 records. Only its existing real TRAIN
anchors seed the simulator; no study rows were sent to Muse. QDE is excluded.
Source attribution/license, seeds and hashes are in the
[compact actual-run report](../ai/forecasting/research_artifacts/muse_live_guided_v1.json).

Before the Meta request, the 960-row base cohort's assignments were frozen:

| Partition | Base rows | Source-anchor groups |
| --- | ---: | ---: |
| Train | 448 | 33 |
| Validation | 156 | 15 |
| Calibration | 172 | 15 |
| Test | 184 | 15 |

Muse's recipe added 1,792 TRAIN-only rows, totaling **2,752 simulated records**.
All holdouts remained unchanged. Source-anchor groups remain separated across
partitions, including every simulated clone. Duplicate screening/resampling
consults TRAIN only; it cannot change augmentation in response to held-out rows.
Validation MAE alone selected random forest: 32 trees, depth 3, minimum leaf 3,
seed 20261103, one worker. Cohort, ridge and boosting comparisons are retained.
Boosting's lower test MAE was not used to override the validation selection.

| Frozen synthetic test (184 rows) | Unaugmented control | Actual Muse-guided |
| --- | ---: | ---: |
| MAE, mL | 92.18 | 80.26 |
| RMSE, mL | 126.56 | 102.73 |
| Bias, mL | −35.81 | −3.22 |
| Row interval inclusion | 88.04% | 97.83% |

Row inclusion is not participant-simultaneous coverage or validated future
coverage. Both are reported separately in the JSON. Long-duration stress MAE
worsens to **450.23 mL**, with only **31.52%** row interval inclusion; the model
is unsuitable for unguarded extrapolation. Context-only weather/intensity changes
produce zero numerical change, as designed. Missingness, noise and contamination
are invented software stress assumptions, not measured population distributions.

The base and augmented experiments share an artificial generator. These errors
measure that software experiment, not a new person's fluid loss, physiological
hydration, or a required drinking amount. The independently collected real-study
evaluations remain separate. Simulations do not satisfy the six-real-session
experimental-fitting minimum.

## Reproduction

The actual saved plan was reused for a second offline run: **all five JSON files
matched byte-for-byte**, with zero additional provider requests. Hashes are in
the compact report. Row-level data, provider/attempt identifiers, credentials
and private ledger paths are excluded from Git.

```sh
python -m scripts.muse_simulated_training prepare --records /ABS/PUBLIC_RECORDS.json --output /ABS/NEW_PREPARED
python -m scripts.muse_simulated_training train --prepared /ABS/NEW_PREPARED --plan /ABS/ACTUAL_SAVED_PLAN.json --origin muse_wonder --database /ABS/EXISTING_AUTHORITY.sqlite3 --output /ABS/NEW_RESEARCH_OUTPUT
```

Use the existing Python 3.13 research environment with scikit-learn. Live-plan
generation is a separate, explicitly billable, once-only operator command;
reproducing training never calls Meta. The earlier offline-stub result (67.16 mL
MAE) used different recipe weights and must not be reported as this live result.
