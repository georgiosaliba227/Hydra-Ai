# Beverage adapter training implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** A real Meta image-recognition adapter trained on an approximately250-image licensed, background-diverse dataset and honestly evaluated above70% joint identity/capacity on untouched data.
**Architecture:** Isolated data collector and annotation/split manifest; pinned SwiftMLX vision/LoRA runner; deterministic blind evaluator and immutable experiment artifacts. Keep working Spark/iPhone inference unchanged.
**Spec:** docs/architecture/BEVERAGE_ADAPTER_TRAINING.md
**Tech stack:** Python data/evaluation tools, SwiftMLX, local AppleGPU, licensed public images.

## Shared interfaces
Manifest JSONL rows: `image_id`, `source_url`, `source_product_id`, `source_revision`, `author`, `license`, `original_sha256`, `image_sha256`, `image_path`, `brand`, `product`, `identity_aliases`, `capacity_ml`, `capacity_visible`, `capacity_evidence`, `background`, `review_status`, `split`. Paths relative to an explicit data root; no answer in model prompt.
Predictions JSONL: `image_id`, `model_id`, `base_revision`, `adapter_sha256`(nullable for baseline), `prompt_sha256`, `outcome`, `brand`, `product`, `capacity_ml`, `latency_ms`, `error`(sanitized). Missing/failed predictions count as failures.

## Tasks
- [ ] Collect candidate metadata/images with attribution and hashes; review at least250 and freeze product-grouped150/25/75 splits with varied real backgrounds.
- [ ] Implement/test scorer and split leakage checks, exact capacity/joint success and confidence intervals. Lock aliases before inference.
- [ ] Build pinned MLX Meta loader, image inference and actual LoRA update/save/reload preflight under24GB. Record memory and training artifacts.
- [ ] Run baseline, train and validate; choose checkpoint using validation only. Score untouched test, preserve all failures, continue legitimate iterations if below70%.
- [ ] Package reproducible model/metrics and review PR; report actual success and limits. Do not declare goal complete without dataset, weights and measured test evidence.
