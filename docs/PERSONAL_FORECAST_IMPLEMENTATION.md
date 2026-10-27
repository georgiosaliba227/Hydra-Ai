# Personal exercise-loss forecasting implementation — October 27, 2026

Separate branch `codex/personal-workout-forecast`, based on main 424f9fe, independently reviewable from PR #10. This implements useful local numerical exercise estimates and an authenticated product API; no iPhone forecasting screen or live Meta interpretation is claimed.

## Implemented behavior

`POST /v1/forecasts` reads the complete owned current beverage snapshot. Existing engine functions supply today's confirmed beverage and estimated physical-water totals, provenance and log revisions. Historical logged-day totals over a caller-selected 1–90 day window provide descriptive ranges, with missing dates and unverified logging completeness explicitly reported. Unknown composition remains null. A logged-day minimum/maximum never becomes a physiological need or expected future intake.

For a planned exercise, the new pure core can propagate a person's prior confirmed weighing-protocol measurements into a **conditional sweat-loss envelope** under explicitly comparable conditions. For a completed exercise, its actual measurement replaces its planned component. Never sum planned and actual versions or add exercise losses to an unapproved daily baseline. Daily requirements remain `insufficient_data`, with no target, deficit or remaining-volume advice. Feedback does not change the arithmetic.

The existing mass-balance equation is retained: `(pre_kg - post_kg) × 1000 + intake_ml - urine_ml`. If independently supplied absolute error bounds are `e_pre`, `e_post`, `e_intake`, `e_urine`, propagate `e_loss = (e_pre + e_post) × 1000 + e_intake + e_urine`. The measured loss interval is `[max(0,loss-e_loss), loss+e_loss]`. For positive duration interval `[d-e_d,d+e_d]`, rate bounds are `[loss_lower×60/(d+e_d),loss_upper×60/(d-e_d)]`; then multiply by planned minutes/60. Envelope the eligible intervals across observations. Outward rounding prevents floating point narrowing an exact arithmetic bound. Missing error bounds are not assumed zero. A zero bound is accepted only as a caller-supplied attestation supported by its provenance; software cannot authenticate instrument calibration or unmeasured physiological losses.

Independent synthetic fixture: mass 70→69 kg, 400 mL consumed, zero urine, 60 minutes gives 1,400 mL/hour. ±0.05 kg at each weighing and ±10 mL intake yield ±110 mL loss; a comparable 30-minute plan produces **645–755 mL estimated exercise loss**. This example is an arithmetic test, not advice to drink that amount. The existing NATA runner example also remains in the maintained suite.

## Scientific scope and limits

The [2017 NATA position statement](https://pmc.ncbi.nlm.nih.gov/articles/PMC5634236/) and [NATA's publication announcement](https://www.nata.org/press-release/nata-publishes-new-fluid-replacement-physically-active-position-statement-journal-athletic-training) support individual measurement and consideration of exercise conditions. They do not validate Hydra's new conditional envelope as a personalized predictive model. The range above is our transparent interval propagation under stated assumptions; it is not a published/calibrated confidence or prediction interval. Repeated observations do not prove future coverage. Unknown systematic error, unrecorded mass changes and changing sweat rates remain limitations.

Activity, intensity, temperature and humidity must match exactly; no scientifically unsupported coefficient or tolerance was invented. The caller must additionally confirm comparable equipment, wind/solar exposure, acclimatization and other relevant conditions. Missing environment/intensity/comparability or usable calibration returns `insufficient_data`. The core can accept a provenance-labeled wearable duration locally, but HTTP wearable export is rejected until separate privacy review. The current iPhone reads steps only and does not supply these measurements.

There is no new baseline formula, dehydration diagnosis, heart-rate/HRV inference, arbitrary beverage-water fraction, retention multiplier or creatine adjustment. Sourced nutrition accounting is unchanged. Raw-input labels denote reported measurements; derived sweat/water quantities are estimates. No Meta-generated number enters the core. PR #10's synthetic explanation path remains separate; automatically sending this forecast/history to Meta would change the approved exact input and is not implemented.

## Product and privacy contract

See [wire/core contract](architecture/PERSONAL_FORECAST_API.md). The new route is local-session authenticated with finite bounded schemas and generic no-value errors. Processing any weighing sample requires explicit calibration-processing consent separate from image/Meta disclosure. HealthKit raw records, arbitrary health text and raw HR/HRV fields are rejected. Results have no-store headers; raw sample masses/volumes are not echoed or persisted, and no AI/provider call occurs. Existing local development server access controls still apply; this is not a production identity/hosting design.

No cache is persisted. Each request recomputes log revisions; callers must discard prior results after any change. The client can inspect the new endpoint through the backend's existing local API explorer. Legacy summary/logging APIs remain unchanged. Default mode remains mock/false. No billing configuration or Meta payload is modified by this PR.

## Validation

- Main-based branch: **268 tests plus 32 subtests passed** across maintained recognition, hydration, backend and database suites. One existing Starlette/httpx deprecation warning. Tests verify independent interval fixtures, duration error propagation, historical envelopes and composition, actual-replaces-planned, duplicates/future events, DST folds, missing calibration/environment, explicit consent, raw/wearable export rejection, authentication/no-store and socket-blocked operation.
- `git diff --check` passed.
- Combined PR #10 + forecasting verification is recorded below after local integration testing. No hosted PR merge is performed.
- No new iOS/XCTest/device run, clinical/forecast calibration study, provider billing/account verification or live Meta request. New functionality is backend/core only. No dependencies added.

## Remaining live-test actions

PR #10's [review report](https://github.com/georgiosaliba227/Hydra-Ai/blob/codex/meta-dual-test-readiness/docs/PR10_REVIEW_2026-10-27.md) contains the full separate-owner checklist. Georgio provides authenticated account/credit/gross-spend/access/key-binding evidence and exact owned image approval. Amine independently provides his own packet and exact synthetic context approval; both review code/privacy/financial controls. Only after provider-backed gross exposure and reconciliation are verified should they record genuine one-use permits with short UTC expiry. The proposed ceiling remains $2/account, with $75 notices, $100 further approval, rejection reaching $120 and $150 gross absolute ceiling. No account pooling, rotation or fallback.

Public [Meta pricing](https://dev.meta.ai/docs/pricing-rate-limits) and [models](https://dev.meta.ai/docs/models) were re-read October 27: Muse Spark 1.3 Standard, $1.25/M uncached input, $4.25/M output. These do not verify access or credits on either private account. The conservative full-context token bound is still $1.312256 before other charges, leaving at most $0.687744 under the proposed $2 ceiling. Provider clarification is still needed for any undocumented additional/internal/failed-request charges and billing finality. Nonzero/uncertain extras cannot be reconciled by guessing from tokens; the current gateway freezes. No counting probe or support message was sent, and no live approval is inferred from this report.
