# Ephemeral on-iPhone drink summaries for backend insights

Version: `device-insights-v1`. This additive boundary supports the owner's request
to use Trends and Ask Hydra while camera/logging remain on the iPhone. It does
not synchronize records, replace the authoritative local store, store submitted
summaries, access the backend's unrelated history, or dispatch a provider request.
The user explicitly enables the optional backend connection with disclosure that
requested insights send drink summaries/questions to their owner backend. Raw
photos, OCR, identifiers, profile/biometric/HealthKit fields and credentials never
appear in the insight body. Existing owner-token authentication and body limits
apply. Responses and request bodies are not logged or cached.

## Capabilities

`GET /v1/device-insights/capabilities` (authenticated, no personal data):

```
{version: "device-insights-v1", history_source: "on_device_summary",
 max_days: 14, provider_dispatch: false}
```

## Trends

`POST /v1/device-insights/trends` accepts only:

```
{version: "device-insights-v1", source: "on_device_summary",
 consent_to_process: true, timezone: <IANA>, through_date: "YYYY-MM-DD",
 days: [{date: "YYYY-MM-DD", total_ml: <integer>, drinks: <integer>} ...],
 goal_ml: <integer or null>,
 categories: [{category: <canonical type>, total_ml: <integer>} ...],
 time_of_day_ml: {morning_ml, afternoon_ml, evening_ml, night_ml}}
```

- Exactly 14 unique consecutive Gregorian days ending at `through_date`.
- All mL values are strict integers in 0...1,000,000,000; reject booleans/floats.
  Drink counts are strict integers in 0...1000; zero volume iff zero drinks.
  The total across days, categories and time buckets must match and remain in
  the same bounded range. A goal is nil or a strict integer in 100...10,000.
- At most 12 unique categories, with positive volumes: `beer`, `coffee`, `energy`,
  `juice`, `milk`, `other`, `plant_milk`, `soda`, `sports`, `tea`, `water`, `wine`.
  The phone maps user-entered names to a known beverage type or `other`; names,
  brands and free-text fields are not transmitted.
- Time buckets use the existing backend convention in the requested timezone:
  morning05:00–11:59, afternoon12:00–16:59, evening17:00–21:59, night otherwise.
- Reject impossible dates, invalid zones, unknown fields, duplicate categories,
  inconsistent totals/counts, missing/false consent and oversized bodies. Reject
  future through-dates relative to the requested zone; historical windows work.

The server computes the existing `wonder-trends-facts-v1` facts from these
aggregates, including weeks, shares, goal days and applicable insight IDs. Reuse
the tested deterministic derivation/validation; do not construct fake records or
infer timestamps. The response is:

```
{version: "device-insights-v1", source: "on_device_summary",
 facts: <TrendFacts>, payload_sha256: <canonical fact digest>,
 summary: <deterministic text>,
 insights: [{id, title, text} ...],
 provenance: {mode: "deterministic", provider: null, model: null,
              history_source: "on_device_summary", storage: "ephemeral"}}
```

Return at most three factual insights; an empty history has an empty insight
list and a no-records summary. Do not call the text Muse/Meta-generated or imply
physiological adequacy, a diagnosis, recommended intake or causal effects.
The existing paid Wonder trend endpoints and permits remain separate. A local
summary must never fall back to the backend's different drink history.

## Contextual Ask Hydra

`POST /v1/device-insights/assistant` accepts:

```
{version: "device-insights-v1", source: "on_device_summary",
 consent_to_process: true, request: <existing AssistantRequest>,
 today_logged_total_ml: <strict integer or null>}
```

The nested request accepts existing validated question/question ID and local-rule
context fields. This endpoint accepts only `source: local_rules` (or its existing
default), never recorded/live provider dispatch. When context_scope is
`today_logged_total`, date/timezone and the nonnegative bounded integer total
must all exist and be valid; otherwise all context fields/total must be absent.
Return the existing validated `assistant-v1` reviewed-rule answer shape. If
context is present, the returned total must equal the submitted phone total and
the note explicitly identifies this iPhone's confirmed log, not server history.
Never query the repository or store the question, context or answer. Existing
no-context questions and separately selected recorded replays remain available
through their existing nonbillable endpoints.

## iPhone routing and acceptance

The insights connection is independent of the local logging destination. It is
off until explicitly configured; opening the app or choosing a photo uploads
nothing. Backend failure cannot block camera/local saves or change the selected
store. Configuration changes cancel/ignore stale insight results. Building a
snapshot reads the selected local logs and goal with generation checks, and
transmits only on the requested feature action after the connection disclosure.
Profile goal calculation stays local; only the adopted goal integer can be part
of the snapshot. Workout calculations retain their existing explicit manual-
input consent and never receive raw HealthKit exports through this boundary.

Test route authentication, strict schema/privacy rejection, deterministic parity,
empty history, date/timezone boundaries, repository/provider non-access and no
persistence. Client tests must cover source routing, no backend-history fallback,
failed requests preserving local logging and stale-connection invalidation.
