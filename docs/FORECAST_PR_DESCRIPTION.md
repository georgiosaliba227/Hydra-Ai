# Add measured-data forecasting research and iPhone calibration

Prepared review text for the pushed `codex/hydration-forecast-ml` branch targeting
`main`. PR creation is pending repository-collaborator access: connector creation
returned 403, CLI creation returned `must be a collaborator`, and the inspected
Chrome GitHub session was signed out. Do not change credentials/permissions or
claim a PR exists. [Open branch comparison](https://github.com/georgiosaliba227/Hydra-Ai/compare/main...codex/hydration-forecast-ml?expand=1).

Hydra now has a reproducible exercise-data forecasting pipeline and a separate iPhone workout screen. Existing beverage accounting, camera behavior, personal forecast engine, HealthKit and guarded Meta services are preserved.

@aminealichaouche — please review the target definitions, participant grouping, uncertainty, consent/privacy boundaries and native integration. Refs #15. No automatic merge or deployment.

## Behavior

- Verify files/licenses for all six requested sources. Preprocess 200 SpectroPhon records (198 conservative groups) and 80 QDE records (10 participants), stripping direct identifiers and keeping incompatible mass-loss proxy targets separate. Identity-bearing raw workbook deleted; no raw or individual normalized data committed.
- Compare cohort-rate baseline, ridge, random forest and gradient boosting with participant-disjoint fit/validation/calibration/test sets. Commit reproducible JSON models and separate real/synthetic evaluation. Synthetic descendants stay grouped by real-training anchor.
- Add authenticated POST /v1/workout-forecasts and iPhone display. Personal mode uses consented transient measurements with the existing deterministic mass-balance envelope and a median estimate. Cold starts remain insufficient_data. Explicit demo mode uses only a server-owned simulated workout and the trained synthetic artifact.
- Show version, provenance, inputs, uncertainty and limitations separately from actual consumption. Stale results are invalidated. A scoped 128 KiB transport cap supports the 32-sample contract.
- Exercise existing Meta interpretation through local synthetic mock signals only. No actual health records sent to providers; no private ledger, credential, spending policy or live activation changed.

## Scientific result and limits

SpectroPhon validation-selected ridge test MAE/RMSE: 71.79/96.10 mL on 39 held-out groups. QDE selected boosting: 331.60/517.69 mL on two held-out subjects, worse than the 314.22 mL-MAE cohort baseline. QDE cannot support a finite nominal 90% interval with only two calibration subjects. These are study-specific proxy tasks, not pure sweat or required intake.

Both real-trained artifacts remain offline research only. The synthetic demo provides no physiological validation. Personal calibration is session-based and deterministic; no persisted longitudinal learning or daily drinking recommendation is claimed. Temperature/intensity generalization and compatible external-study validation are unavailable.

## Validation

- Integrated application suite: 535 pytest tests + 32 subtests passed; one optional training module skipped in the runtime environment.
- Pinned offline forecasting environment: 39 tests passed, including training and overlapping ingestion/runtime tests. All four artifacts independently reproduced byte-for-byte; RuntimeWarnings-as-errors reproduction passed.
- Preserved starter: 3 tests passed.
- iPhone 18 Pro / iOS 27 simulator: 47 XCTest unit tests and 3 UI integration tests passed; 4 physical/live opt-ins skipped. Final forecast UI rerun passed and screenshot visually checked.
- Independent scientific and integration review; found/fixed maximum-sample request-size mismatch. Existing Starlette/httpx deprecation warning remains.

No physical-device verification of this screen, real Meta inference, paid compute, production deployment or clinical validation.

Review documents: docs/FORECAST_DATA_INVENTORY.md, docs/FORECAST_MODEL.md, docs/FORECAST_EVALUATION.md, docs/architecture/WORKOUT_MODEL_API.md and docs/PROJECT_STATUS.md.
