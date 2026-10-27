# Meta model strategy

Public documentation rechecked 2026-10-27; Startup track selected. Updated user report: separate $150 allocations for each developer, independently unverified and not transferable; model-specific account access is unverified. Credits do not authorize inference or prevent overages. The $120 cumulative-usage cutoff and $30 reserve remain unchanged. Mock recognition and an offline payload builder are implemented; a guarded transport is now implemented but real dispatch remains blocked by the verified maximum-cost gate; no live calls. See [Milestone 2](MILESTONE_2.md).

| Feature | Proposed model | Status |
|---|---|---|
| Beverage photo candidates and container interpretation | `muse-spark-1.3` Standard | image input documented; evaluate with consented fixtures after approval |
| Grounded explanations and assistant | `muse-spark-1.3` Standard | proposed; deterministic core owns numbers |
| Low-cost alternative | `muse-spark-1.3-contributor` | not default: training-data terms conflict with sensitive inputs |
| Segmentation | `sam-3.1` | optional, deferred |
| Complex reasoning | `muse-wonder-1.0` | deferred; separate cost justification required |
| Self-hosting | Muse Spark Open | deferred; hardware/license feasibility not established |

## Verified public API facts
Meta's base URL is `https://api.meta.ai/v1`; official examples use bearer authentication and `MODEL_API_KEY`. Hydra proposes `META_MODEL_API_KEY`, mapped by a future adapter. Prefer direct HTTP to keep the endpoint explicit. [Overview](https://dev.meta.ai/docs/overview)

Spark 1.3 supports image input and text output; Responses examples use `input_image`. Image token use depends on resolution. A token-count endpoint is documented, but its billing status must be verified before calling it. [Image understanding](https://dev.meta.ai/docs/image-understanding)

## Price snapshot, USD (reverify before use)
| Model | Input / million tokens | Cached input / million | Output / million |
|---|---:|---:|---:|
| Spark 1.3 Standard | 1.25 | 0.15 | 4.25 |
| Spark 1.3 Contributor | 0.10 | 0.002 | 0.20 |
| Wonder 1.0 | 4.00 | 0.20 | 20.00 |

SAM: $2.50/1,000 images; $0.20/1,000 video frames, minimum 50 frames per video request. Search grounding: $2.50/1,000 queries in addition to tokens. Contributor allows submitted content and responses to be used for model training; Standard does not. Standard is not a claim of zero retention. Rate limits are shared per team. [Official pricing](https://dev.meta.ai/docs/pricing-rate-limits)

Spark Open is not hosted on Model API and requires substantial hardware (published checkpoints approximately 1.65 TB BF16 or 537 GB NVFP4); its Muse license and acceptable-use terms need review. [Spark Open](https://dev.meta.ai/docs/muse-spark-open)

## Evaluation and activation gate
Use synthetic/consented drink fixtures across branded, homemade, ambiguous, partially consumed and multiple-container images. Measure category accuracy, uncertainty quality, schema validity, correction rate, and cost; do not call a visual volume estimate ground truth. Verify exact deployed model ID and record provider usage without raw sensitive payloads. Validate output against the shared contracts; model nutrition requires source lookup. No OpenAI/Anthropic/Google substitution for core inference.

Before activation: verify account availability and accepted hackathon rules, current prices and maximum request charges, retention terms, budget controls, and human approval. Contributor requires a separate data-policy review and is not approved for health/photo data. Keep raw HealthKit records on device pending policy review. See API_BUDGET.md.
