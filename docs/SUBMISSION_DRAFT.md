# Hydra AI — submission draft

Working copy for the Meta Global AI Developer Hackathon 2026, Startup track,
updated November 4, 2026. The verified event-page deadline is **November 4,
9 PM ET**. Signed-in portal fields, video duration/upload requirements and
participant eligibility remain unverified; see [compliance status](HACKATHON_COMPLIANCE.md).
The owner must review and submit; this document accepts no terms. The owner
has set an earlier working deadline of **8:30 PM ET**.

## One line

Hydra AI turns a drink photo into an editable log on your iPhone, using bundled
Meta DINOv2 and Apple label reading, with transparent goals and reviewed wellness
explanations.

## Problem and audience

People who want to understand their drinking habits need convenient logging
without false precision. A photo can help identify a beverage and printed size,
but it cannot prove how much someone drank or measure their hydration. Hydra
makes that uncertainty visible and keeps the user in control of the record.

## Current prototype

- Analyze a real photo offline using bundled Core ML and Apple Vision OCR.
  Review the suggestion, edit name/type/container size/amount, then Confirm.
  Unknown capacity stays unknown until supported or entered.
- Save confirmed drinks in protected local storage, preserve the original model
  suggestion separately, quick-add a drink and edit/delete History entries.
- Show volume against a confirmed goal. Guided setup labels a published adult
  starting reference and source; custom goals are available. Neither is a
  measured personal requirement. Body/supplement inputs add no unsupported
  adjustment.
- Optionally connect to a stateless features backend while keeping photos and
  drink records local. Trends previews fourteen-day aggregates before sending;
  patterns are deterministic. Ask supplies reviewed answers/evidence, optionally
  using today's total. Workout estimates are conditional ranges, with a
  separately labelled simulated example.
- Keep raw HealthKit records on the phone. The recording uses fictional data
  and shows Apple Health privacy controls only; no real records are read.

The circle measures confirmed **beverage volume**, not water content or
dehydration. Nutrition stays unknown without a verified source. All beverages
can contribute fluid; no arbitrary caffeine penalty, hydration multiplier or
creatine adjustment is applied.

## Meta AI contribution

| Component | Actual role in this demo | Limits |
| --- | --- | --- |
| Meta DINOv2 Small, frozen backbone + Hydra category head | Bundled FP16 Core ML inference on the iPhone; no runtime model download | Experimental categories, uncalibrated scores, user confirmation required |
| Apple Vision OCR + deterministic parser | Local printed-size reading and explicit-unit validation | Capacity is not remaining liquid or consumption; ambiguous sizes remain unknown |
| Deterministic accounting and reviewed content | Totals, confirmed-goal progress, Trends, Ask and workout calculations | No hosted generative AI invocation in this demo |

The phone model scored **50/75 (66.7%) category accuracy** on the existing
product-separated held-out cohort. This small, mostly packaged-beverage set
does not validate general non-beverage rejection, natural-glass accuracy,
nutrition or medical performance. No personal photos or health records trained
this model. The [notice](../ios/HydraAI/Resources/OnDeviceModel-NOTICE.txt) and
[model documentation](../ai/on_device/README.md) record source revision,
modifications, data attribution and upstream licensing. DINOv2's Apache-2.0
license is included; no new project-wide license grant is made here.

## Technical depth and verification

SwiftUI/Swift, Core ML and Apple Vision run local capture/review/logging.
`LocalBeverageService` preserves original suggestions and confirmed entries in
protected storage. Optional owner-only FastAPI features are stateless and cannot
dispatch providers or open the historical database/financial ledger. The wider
repository retains its separate SQLite backend and guarded research paths.

**Prior baseline, November 4, 2026:** 1457 pytest passed, 5 skipped, 58 subtests;
202 native XCTest; 7 relevant simulator UI flows. See the
[guided-insights review](REVIEW_IPHONE_GUIDED_INSIGHTS_20261104.md). Earlier
physical evidence includes bundled inference/OCR on a generated label and
owner-observed offline analysis, confirmation and restart persistence. These
checks verify implementation behavior, not scientific or clinical validity.
**New Hydra Demo checks:** 1480 pytest passed/5 skipped/58 subtests, 217 native
XCTest and 1 demo isolation UI flow passed. The separate signed device build and
bundled model verification passed. Physical rehearsal and final video remain pending. Record actual results in [source verification](DEMO_SOURCE_VERIFICATION.md).

## Separate historical experiments

Hosted Muse Spark/Wonder integrations and recorded responses remain research
paths. A separate Mac-only Muse Glimmer 30B adapter achieved 63/75 joint full
identity/exact-capacity success on its frozen test set; that is **not** the
phone category model's result. Forecast studies have their own proxy targets
and limitations. These experiments do not establish app nutrition accuracy,
physiological ground truth or a drinking requirement. This recording uses no
new paid/provider request and does not present a recorded hosted answer as
current inference.

## Physical recording and source handoff

Follow the [three-minute runbook](PHYSICAL_DEMO_RUNBOOK.md). The separate
**Hydra Demo** bundle (`com.georgiosaliba.hydraai.demo`) visibly labels
**DEMO · simulated data** and starts with fourteen fictional days, 2250 mL today
and a 3000 mL confirmed demo goal. Demonstrate real offline camera capture,
review/confirm a simulated 500 mL entry, quick-add 250 mL to fill the circle,
edit History, reconnect for Trends/Ask/Workout and show privacy controls.
The entire recording originates on the physical iPhone using its built-in
screen recorder with Mac sharing off. The owner operates physical taps;
preserve the original before trimming/captions/export on the Mac.

Source branch:
[`codex/physical-demo-submission`](https://github.com/georgiosaliba227/Hydra-Ai/tree/codex/physical-demo-submission).
**App source commit: 3b9663b; actual video artifact remains pending.** Push and verify all code, setup,
docs and actual model blobs before owner recording; record the commit and
verification timestamp in [the handoff](DEMO_SOURCE_VERIFICATION.md).
`main` is not the submission feature source. Earlier PR creation failed with
HTTP 403; no successful PR, reviewer notification or merge is claimed.

## Owner checks before submission

- Replace pending evidence with the verified source commit and actual reviewed
  video; confirm portal length/format/access requirements before export.
- Confirm both developers' eligibility/acceptance and the Startup representative's
  employment and authority under the rules.
- Review third-party attribution and submission rights. Existing notices are
  evidence, not a completed legal audit or a new root license.
- Retain synthetic-data disclosure, model uncertainty and wellness limits. Do
  not expose tokens, personal records or private ledger files.
