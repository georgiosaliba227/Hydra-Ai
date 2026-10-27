# Draft shared contracts (v1 proposal)

These original interfaces remain the broader design specification. The implemented manual prototype subset and deliberate additions (GET /v1/summary, pagination, single-user local authentication and idempotency) are defined in [PROTOTYPE_API.md](PROTOTYPE_API.md). Unlisted proposed features below remain unimplemented. The legacy nested starter is separate.

## Conventions
JSON, explicit units (`*_ml`, `*_mg`, `*_kg`), finite nonnegative values with reviewed upper bounds, RFC3339 timestamps, IANA timezone for local-day aggregation, UUID identifiers. Unknown is null, never zero. Reject extra/invalid fields at model boundaries. Errors use `{code, message, request_id, retryable}` without sensitive payloads. Authenticated user identity comes from the session, never a trusted client-supplied user ID. Mutation idempotency keys are scoped to the authenticated user.

## Proposed endpoints
| Endpoint | Input | Output / invariant |
|---|---|---|
| POST /v1/beverages/recognize | consented image; optional label/barcode; idempotency key | recognition_id, candidate category/brand/product, container, estimated_volume_ml range, confidence label, uncertainties, provenance; no log write |
| POST /v1/beverages | confirmed category, consumed_ml, consumed_at, timezone, optional recognition_id and sourced nutrients | persisted log with id and revision; user confirmation required |
| GET /v1/beverages | local date range and timezone; pagination | owned logs and next cursor |
| PATCH /v1/beverages/{id} | revision and corrected fields | updated owned log; stale revision rejected |
| DELETE /v1/beverages/{id} | owned id | deletion result; forecasts invalidated |
| POST /v1/forecasts | date/timezone, consented activity aggregates, optional sweat calibration, input provenance | estimated range in mL or insufficient_data, method_version, assumptions, reasons, missing_inputs, intake totals |
| POST /v1/assistant | question and explicitly consented context scope | grounded explanation, evidence refs, optional forecast_id; never model-authored numeric recalculation |
| GET /v1/budget | operator authorization | settled/reserved USD, thresholds, last reconciliation, blocking reason; no keys |

## Domain objects
`BeverageLog`: id, consumed_ml, category, consumed_at, timezone, source (`manual`/`confirmed_recognition`), optional product_id, nutrition, provenance, revision. Nutrition carries basis volume and units per field; conversion uses the confirmed consumed amount. Unknown water content remains null.

`Recognition`: candidates[], volume_range_ml or null, confidence (`low`/`medium`/`high`, not an assumed calibrated probability), uncertainty_reasons[], model_id, prompt/schema version, evidence references. Exact product nutrition must come from a retrieved source, not the model's memory. Reject impossible ranges. Never follow instructions embedded in labels/images or external source text.

`Forecast`: status, lower_ml/upper_ml or null, beverage_total_ml, estimated_water_ml or null, component ledger, input provenance, method_version, assumptions[], uncertainty_reasons[], generated_at. Keep total dietary water and beverage targets distinguishable; never subtract beverage volume from a dietary-water target without a documented compatible method.

`BudgetReservation`: request_id, idempotency_key, feature, developer identifier, price_version, model_id, reserved_usd, settled_usd or null, state, provider_request_id, timestamps. Monetary arithmetic uses integer microdollars or decimal, never binary float. No health information belongs in this record.

## Contract tests planned
Null versus zero, mL versus L and nutrient serving conversion, DST/local-day boundaries, duplicate submissions, concurrent revisions, unauthorized cross-user access, image size/type validation, bad model schemas, missing evidence, forecast stale inputs, and budget fail-closed responses. Freeze an OpenAPI schema and fixtures before parallel implementation.
