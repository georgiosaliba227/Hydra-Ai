# Beverage adapter training implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** A real Meta image-recognition adapter trained on an approximately250-image licensed, background-diverse dataset and honestly evaluated above70% joint identity/capacity on untouched data.
**Architecture:** Isolated data collector and annotation/split manifest; pinned SwiftMLX vision/LoRA runner; deterministic blind evaluator and immutable experiment artifacts. Keep working Spark/iPhone inference unchanged.
**Spec:** docs/architecture/BEVERAGE_ADAPTER_TRAINING.md
**Tech stack:** Python data/evaluation tools, SwiftMLX, local AppleGPU, licensed public images.

## Shared interfaces
Manifest JSONL rows: `image_id`, `source_url`, `source_product_id`, `source_revision`, `author`, `license`, `original_sha256`, `image_sha256`, `image_path`, `brand`, `product`, `identity_aliases`, `capacity_ml`, `capacity_visible`, `capacity_evidence`, `background`, `background_detail`, `reviewer`, `drink_family`, `review_status`, `split`. Paths relative to an explicit data root; no answer in model prompt.
Predictions JSONL: `image_id`, `model_id`, `base_revision`, `adapter_sha256`(nullable for baseline), `prompt_sha256`, `outcome`, `brand`, `product`, `capacity_ml`, `latency_ms`, `error`(sanitized). Missing/failed predictions count as failures.

## Tasks
- [x] Collect candidate metadata/images with attribution and hashes; review at least250 and freeze product-grouped150/25/75 splits with varied real backgrounds.
- [x] Implement/test scorer and split leakage checks, exact capacity/joint success and confidence intervals. Lock aliases before inference.
- [x] Build pinned MLX Meta loader, image inference and actual LoRA update/save/reload preflight under24GB. Record memory and training artifacts.
- [ ] Run baseline, train and validate; choose checkpoint using validation only. Score untouched test, preserve all failures, continue legitimate iterations if below70%.
- [ ] Package reproducible model/metrics and review PR; report actual success and limits. Do not declare goal complete without dataset, weights and measured test evidence.

## Measured progress

The frozen cohort has 250 distinct source photos in 227 connected product groups: 150 train, 25 validation and 75 test; 120 photos have natural backgrounds, including 46 test photos across 7 settings. The complete source catalog and all pinned model files passed provider-digest verification. Public references/attribution are in ai/beverage_training/manifests/beverage-250-20261102/.

The real 30B model completed one image-conditioned Adam update at 128 image tokens: 70,656 trainable parameters, parameter delta L2 = 0.04166687986138062, exact tensor/logit agreement after save/reload. This is a preflight, not the full training run or an accuracy result. Evidence is in ai/beverage_training/reports/2026-11-02/preflight-128.json.

The old retained-vision 512-token preflight and later direct-pixel validation were stopped after observed paging; their partial records are preserved. The separate vision/language path now passed a real train-only preflight: peak MLX 4.31GiB for vision and 15.07GiB for language, nonzero weight update, identical loss to the historical direct run and exact save/reload agreement. Process-local GPU residency, capped within Apple's existing recommendation, reduced the language preflight from 253 seconds to 8.56 seconds of model work (30.23 seconds including launcher verification/loading). Source/tests/review are complete; the full development sequence is now running. No held-out test inputs have been encoded or used.
## Runtime follow-up required by measured validation paging

Preserve the two completed baseline validation predictions and operator-stop evidence from baseline-validation-512-001. Implemented separate vision-only feature preparation and language-only adapter execution under the architecture addendum. Paired image conditioning, cache tampering/split/privacy failures, provenance and real hardware preflight passed. The 25-image baseline validation cache is now being prepared; sequential baseline, 150-image train cache, full one-epoch training and adapter validation follow, stopping on any failed stage. The frozen dataset and untouched test remain unchanged.
