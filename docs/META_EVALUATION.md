# Meta recognition and hydration evaluation

This implements an **offline scoring harness**, not a live batch sender. The bundled seven-case dataset is synthetic; six handcrafted observations exercise correct answers, brand and volume errors, abstention, repetition, a provider failure and one missing result. `evaluation/synthetic-report.json` is reproducible harness output. **Actual Meta camera runs: 0. Actual Meta hydration runs: 0.** Neither synthetic accuracy nor mock latency measures Meta performance.

Run from the repository with the existing backend Python environment:

```sh
python -m scripts.evaluate_meta --dataset evaluation/synthetic-dataset.json --observations evaluation/synthetic-observations.json
python -m pytest -q tests/evaluation
```

The command sends nothing, imports no credentials, never opens image files and does not initialize, copy, migrate or write any financial ledger. `--output /absolute/new-report.json` creates a private aggregate-only report and refuses overwrite. Without it, aggregate JSON goes to stdout. File/schema/evidence errors produce a generic message without printing input data.

## Reproducible measurement

Every rate reports its numerator, denominator and value. Empty denominators are `null`, never zero or perfect accuracy. Missing observations are `not_run_cases`; errors are counted separately. Each case has one observation; repeat trials need separate case IDs and separate approved attempts. The same provider attempt cannot be counted twice.

| Measure | Definition and limits |
| --- | --- |
| Category and brand top-1/top-k | Case-insensitive exact normalized label/alias match; top-k uses up to three returned candidates. Denominator is successful cases with identifiable ground truth. Errors and unattempted cases remain separately visible. |
| Container capacity | Top-candidate absolute error in ml, absolute percentage error, prediction coverage. Ground truth comes from a readable label or independent measurement. This never measures amount consumed. |
| Uncertainty | Category/brand abstention when the approved image cannot identify that field; any capacity claim without visible support; wrong category among high-confidence predictions. Confidence is uncalibrated. |
| Hallucinations | Unsupported brand/category/capacity flags plus explicit reviewer labels for invented identity/nutrition, medical claims and numerical recommendations. Missing human reviews remain unscored; no lexical heuristic establishes medical safety. |
| Hydration relevance | Signal precision against allowed signals, recall of required signals, and all-required coverage where the rubric specifies required signals. `discarded_signal_count` and `raw_signal_supported_fraction` expose distinct unsupported selections removed by context grounding; repaired output precision alone is not raw-model relevance. Explanation strings must exactly match reviewed text for returned signals. Model-written diagnoses/numbers cannot be accepted as successful gateway output. |
| Consistency | Exact signal-set agreement across successful cases in a predeclared equivalent-context group; only groups with at least two results count. No additional calls are made. |
| Explanation quality | Human 1–5 score with an explicit reviewer reference; report count/mean/median. Suggested anchors: 1 irrelevant or misleading, 3 relevant but omits material uncertainty, 5 relevant, consistent and clear about missing information. Review context privately. |
| Latency | API transport latency from ledger evidence for live attempts; mock latency is fixture data. Mean, median and nearest-rank p95 with sample count. Small n does not establish service performance. |
| Usage and cost | Input/output/cached/total tokens from ledger records only. Usage-derived settled token cost and separately reviewed final gross billing are distinct known subtotals with counts. Missing usage/cost stays unknown. Account totals remain separate; aggregate spending never represents transferable credits. |

## Private dataset preparation

Prepare a small controlled set; run only the single separately authorized first request initially. Later cases stay unrun until policy, account approvals and prior billing finality permit them. The evaluation command cannot authorize or dispatch any case.

| Planned case | Ground truth to record privately before running |
| --- | --- |
| Clear owned beverage label | Category, exact brand aliases and readable capacity; avoid personal background content. |
| Unbranded cup | Category only where supported; no visible brand; measured capacity may be recorded for error analysis but mark `capacity_visible:false` when not identifiable in the image. |
| Ambiguous/occluded beverage | Leave unidentifiable category/brand arrays empty and capacity absent; expected abstention. |
| Synthetic intake with missing composition | Required `composition_missing`, allowed `review_intake`; no water-content invention. |
| Synthetic exercise/weather context | Required applicable contextual signals; no fluid prescription or dehydration diagnosis. |
| Synthetic individual-pattern context | Use the bounded `intake_pattern` context contract and require `intake_pattern_context` when applicable; no new physiological targets. |

Use `Dataset` in `ai/evaluation/models.py` as the versioned manifest schema. A private camera case sets `source:"private_owned_input"`, an exact normalized prepared-JPEG `input_sha256`, and a non-sensitive `truth_reference`. A hydration case binds the canonical `context_fingerprint`, not the bytes of an arbitrary JSON encoding. Populate ground truth from actual reviewed evidence; do not substitute illustrative fixture labels or all-zero hashes. No real photos, private outputs, account IDs, evidence references or private manifests belong in Git. The report contains aggregates only.

Observations use `meta-evaluation-observations-v1`: `case_id`, `mode`, `outcome`, exact parsed gateway `result` for success, and `attempt_id` for a claimed live run. Camera HTTP output may contain catalogue `candidate.nutrition`; this is the **only** enrichment stripped before matching the gateway digest. The remaining result must match exactly, including the recognition ID. Hydration uses the exact gateway response, including signals, mode and context. Explicit reviewer labels are optional. Input observations do not accept token counts, costs, provider IDs or claimed billing finality.

Store live manifests and observations as owned regular files with mode 0600, outside Git. After an approved attempt, provide the **existing authoritative ledger path** explicitly:

```sh
python -m scripts.evaluate_meta --dataset /private/dataset.json --observations /private/observations.json --authoritative-ledger /absolute/private/existing-meta.sqlite3 --output /private/new-aggregate-report.json
```

The reader verifies the recorded attempt, account/workstream, exact input fingerprint, parsed output digest, transport classification, provider usage and cost math. Injected test transports cannot count as real results. Successful output requires settled usage; invoice finality remains separately labelled. A transport failure may remain billed/unknown and never receives success scores. The ledger is opened read-only. Legacy attempts missing observation events remain unavailable rather than gaining fabricated evidence.

The operator must independently identify the authoritative ledger and preserve its custody. An arbitrary local database is not proof of a provider response. Even the shipped HTTPS transport can be mocked in tests; passing a synthetic test ledger to the live evaluator is prohibited. Local transport records establish the implementation path; owner/provider evidence and reviewed invoice finality supply external verification. This harness does not authenticate provider dashboards, collect approvals, release reservations, change financial policy, or establish scientific/clinical validity.

## Demonstration evidence

Before real inference, show the report's `meta_live.status:"not_run"`. After authorized inference, show the provider-linked attempt privately, its exact evaluated output and the corresponding `meta_live` scores; identify any missing final invoice as pending. Keep the iPhone identity/consumption confirmation step and deterministic fluid totals. Report unsuccessful cases and unknown values. Do not describe this small controlled sample as a validated recognition benchmark or a medical hydration predictor.
