# Synthetic hydration intelligence API

Version `hydration-explanation-v1`, context `hydration-context-v1`. This review proposal adds the prepared hydration service to the authenticated local backend. It does not authorize real inference, change the active $0.25 camera-first policy, or enable the proposed $2 dual-test policy.

## Configuration and account isolation

`HYDRA_META_HYDRATION_ENABLED=false` is the default. Mock explanations remain available with no key or provider connection. Setting this flag to `true` also requires `META_BILLABLE_REQUESTS_ENABLED=true`; hydration uses only `HYDRA_META_AMINE_API_KEY`, the fixed `aminealichaouche` account and the existing `app.state.meta_ledger` object. It never changes `HYDRA_META_ACCOUNT`, which continues to select the camera account. No account fallback occurs.

A hydration-only configuration may explicitly combine camera `HYDRA_AI_MODE=mock`, the hydration flag `true` and the global billable flag `true`. The camera remains mock. The billable flag alone remains invalid for a mock-only configuration. Startup checks are configuration checks, not verified provider access or spending authorization. Every live request still requires the existing immutable purpose/account/input/price permit, verified bound, shared unresolved-billing/finality checks and authoritative ledger. No HTTP ledger administration is exposed.

## Endpoints

`GET /v1/hydration-capabilities` reports the configured mode (`mock` or `meta_live`), provider/model, synthetic-only scope and account permit requirement. Mode reports configuration, never successful inference.

`POST /v1/hydration-explanations` accepts exactly:

```json
{"mode":"mock","context":{"synthetic":true,"disclosure_consent":true,"beverage_total_ml":750.0,"workout_minutes":30,"temperature_c":24.0,"intake_pattern":"lower_than_recent"}}
```

`mode` is required and must match configured hydration mode. `SyntheticContext` rejects unknown fields, nonfinite/out-of-range numbers and nonliteral synthetic/disclosure attestations. Raw records, identifiers, free text, HealthKit, HR and HRV are unsupported. Existing aggregate fields retain explicit units. `intake_pattern` is an optional synthetic scenario annotation (`higher_than_recent`, `lower_than_recent`, `similar_to_recent`, `missing`); it is not calculated by the model or a validated physiological prediction. Intake totals for constructed synthetic logs can come from `context_from_engine`; caller-provided synthetic aggregates are not independently verified measurements.

Responses contain `version`, `mode`, `provider`, `model`, `account_id`, `attempt_id`, `context`, `signals`, `discarded_signal_count`, `explanations`, `prediction:null` and `missing_information`. Mock responses have null provider/model/account/attempt fields. Live responses name Meta, `muse-spark-1.3`, Amine and the settled attempt. The model selects bounded signal IDs; the server renders reviewed text, rather than presenting it as model-authored prose. Irrelevant selected signals are dropped against the context and counted in `discarded_signal_count` for quality evaluation; a result with no supported signal fails closed. Evaluations must distinguish repaired output from an entirely consistent model selection. No numerical recommendation, diagnosis, hydration multiplier or nutrition value is generated. Engine calculations are unchanged.

All `/v1` endpoints require the existing development bearer token, have `Cache-Control:no-store`, enforce the existing 16 KiB body limit and never persist context or response bodies. Invalid input returns redacted 422; disabled/mismatched live mode, unapproved input, provider error or invalid output returns redacted 503 `hydration_unavailable`, `retryable:false`. No automatic retry or mock fallback follows a failed live request. Model usage is settled before parsing; malformed outputs quarantine the attempt under existing rules. Usage settlement is not invoice finality. A compact observation in the same ledger records the exact returned-result digest, API latency, HTTP status and safe error category; it contains no response body or synthetic context. It links evaluations to usage while distinguishing injected test transports from the official implementation path.

## Verification boundary

Unit/API tests use synthetic contexts, temporary financial databases and fake providers or mocked HTTP. They verify routing, account/ledger isolation, validation, grounding, mode labels and refusal behavior; they do not establish actual model quality, provider-account access, approved spend or billing finality. Exact context/payload hashes must be regenerated after context/schema/prompt changes before any future approval.
