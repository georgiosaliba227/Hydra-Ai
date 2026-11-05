# Hydra AI

An iPhone wellness prototype for the Meta Global AI Developer Hackathon 2026,
Startup track. The current camera runs **bundled Meta DINOv2 Small with a trained
beverage-category head, plus Apple Vision OCR**, entirely on the iPhone.
Photos suggest; the user reviews and confirms what to log.

## Current app

- **Offline camera and logging:** Core ML category suggestions, conservative
  printed-size parsing, Confirm/Edit, manual quick-add, History edit/delete and
  restart persistence. `LocalBeverageService` protects the phone's separate local
  records, including the original suggestion and confirmed details. Photos are
  not retained or used for training on this path.
- **A goal the user confirms:** review a labelled published adult starting
  reference and its source, or choose a custom goal. The water circle represents
  logged beverage volume against that goal. Optional body and supplement answers
  introduce no numerical adjustment.
- **Optional backend features:** keep camera/logging local while connecting to
  the owner-only stateless features backend. Trends previews phone aggregates
  before sending and calculates patterns deterministically. Ask Hydra supplies
  reviewed, sourced answers, optionally with today's total. Workout calculates a
  conditional loss range or a labelled simulated example. This runtime opens no
  database or financial ledger and cannot call an AI provider.
- **Privacy controls:** local export/deletion and separately scoped goal profiles.
  Raw Apple Health records remain on the phone. The submission demo shows privacy
  controls only and requests no real HealthKit records.

Confirmed beverage volume, printed capacity, assumed whole-drink consumption,
water content and physiological hydration are different quantities. Unknown
composition stays unknown without a verified source. Hydra does not diagnose
dehydration, infer it from HR/HRV or turn exercise loss into a daily drinking
prescription. Missing logs mean unknown intake.

## Run and demonstrate

Use [offline camera setup](docs/ON_DEVICE_CAMERA_SETUP.md) for the current local
camera, [prototype setup](docs/PROTOTYPE_SETUP.md) for the wider backend, and the
[physical demo runbook](docs/PHYSICAL_DEMO_RUNBOOK.md) for the submission recording.
The [device insights contract](docs/architecture/DEVICE_INSIGHTS_API.md) defines
the aggregate boundary; the [goal policy](docs/architecture/GUIDED_GOAL_POLICY.md)
defines reference review and confirmation.

The **Hydra Demo** bundle (`com.georgiosaliba.hydraai.demo`) has a separate
sandbox and visible **DEMO · simulated data** label. It starts with fourteen days
of fictional records, 2250 mL today and a confirmed 3000 mL demo goal. Explicit
reset is for rehearsal; relaunch preserves changes. Demo isolation and signed-build checks passed; installation and final physical
recording status are tracked in the
[source verification handoff](docs/DEMO_SOURCE_VERIFICATION.md).

Submission source is the feature branch
[`codex/physical-demo-submission`](https://github.com/georgiosaliba227/Hydra-Ai/tree/codex/physical-demo-submission),
with app code commit **3b9663b** and source-freeze evidence in that handoff. All source, setup, docs and
actual model blobs must be pushed and remotely verified **before** owner recording.
Do not use `main` as feature evidence. Earlier PR creation returned HTTP 403;
no successful PR or merge is claimed.

## Evidence and model provenance

The November 4, 2026 guided-insights baseline recorded **1457 pytest passed,
5 skipped, 58 subtests; 202 native XCTest; 7 relevant simulator UI flows**.
These are prior results, not results for the new isolated demo build. See the
[baseline review](docs/REVIEW_IPHONE_GUIDED_INSIGHTS_20261104.md). An earlier
physical check passed bundled inference/OCR on a generated label; the owner
separately verified offline analysis, confirmation and persistence. This does
not establish general recognition accuracy or clinical validity.

The phone category model scored **50/75 (66.7%)** on the product-separated
held-out cohort. Scores are uncalibrated; general non-beverage rejection and
natural-glass accuracy are unvalidated. OCR reads supported printed declarations,
not remaining liquid or consumption. See [model development](ai/on_device/README.md)
and the [on-device contract](docs/architecture/ON_DEVICE_CAMERA.md).

The bundled [notice](ios/HydraAI/Resources/OnDeviceModel-NOTICE.txt) pins
`facebook/dinov2-small` revision `ed25f3a31f01632728cabb09d1542f84ab7b0056`.
The backbone is Apache-2.0; its [license](ios/HydraAI/Resources/DINOv2-LICENSE.txt)
is included. The notice records the reviewed Open Food Facts cohort's image
attribution and CC-BY-SA-3.0/ODbL-1.0 provenance. No training photos are bundled;
no personal photos or health records trained this model. These upstream notices
do not grant a new project-wide license.

## Separate historical and research paths

The repository retains guarded hosted Muse Spark/Wonder integrations, recorded
responses, a Mac-only Muse Glimmer 30B adapter experiment and public-study
forecasting experiments. They are separate from this phone demo. The 30B
adapter's **63/75 joint identity/capacity** result does not describe the phone
category model, OCR, nutrition accuracy or medical validation. See the
[30B review](docs/reviews/2026-11-03-beverage-adapter-pr.md) and
[forecast evaluation](docs/FORECAST_EVALUATION.md).

This demo activates no paid AI. Existing account-specific permissions, historical
holds and cutoff policies remain unchanged; see [agent instructions](AGENTS.md),
[camera cutoff policy](docs/architecture/CAMERA_CUTOFF_POLICY.md) and
[budget documentation](docs/API_BUDGET.md). Hosted credentials stay server-side.

## Submission status

The [submission draft](docs/SUBMISSION_DRAFT.md) describes current features and
remaining checks. The event page's verified deadline is November 4, 2026,
9 PM ET; signed-in portal fields, video limit, participant eligibility and
acceptance requirements still need owner verification. See
[compliance status](docs/HACKATHON_COMPLIANCE.md). No submission, terms acceptance,
public deployment or legal audit is claimed.
