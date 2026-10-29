# Muse Wonder hydration intelligence — mock-only contract

Version `wonder-hydration-context-v1`. Proposed by Amine on 2026-10-28, before
implementation, for review by Georgio. It is additive: v1 explanations, the
camera path and every financial module keep their current behavior. Nothing here
authorizes a live request, migrates a ledger or changes a spending limit.

## Decisions this contract records

- `muse-wonder-1.0` Standard is the only Meta model for hydration
  intelligence. Spark is no longer a hydration candidate; Wonder is not compared
  against other models unless both developers change this decision.
- Camera recognition keeps `muse-spark-1.3` Standard unchanged.
- A future live Wonder request is charged to Georgio's conditional $30 experiment
  allocation (`hydration-v2-georgio-30usd`), never to Amine's account. The
  existing v1 synthetic explanation path (`HYDRA_META_HYDRATION_ENABLED`, fixed to
  Amine, Spark-only ledger prices) is left in place and disabled by default; it is
  not the Wonder path.
- The $20 Spark / $10 Wonder soft targets inside the $30 ceiling are unchanged
  here. Whether the Spark target still applies once hydration is Wonder-only is
  an open question for Georgio.

## Verified public facts (dev.meta.ai, checked 2026-10-28)

- Model ID `muse-wonder-1.0`, Standard tier only, in preview. Contributor mode is
  unavailable for Wonder.
- Prices per million tokens: input $4.00, cached input $0.20, output $20.00.
  Spark 1.3 Standard is $1.25 / $0.15 / $4.25.
- Wonder and Spark "take the same requests on the same endpoints"; switching is a
  model ID change. Wonder lists structured output and accepts reasoning effort
  `minimal` through `max`.
- Context window 1,048,576 tokens. `max_output_tokens` bounds reasoning plus
  visible output. The docs do not state how reasoning tokens are billed, so every
  generated token is priced as output.

Public pages do not establish account access, available credits or an
all-inclusive charge bound.

## Request

`backend/wonder_hydration.py` builds a deterministic Responses payload from a
server-owned V2 scenario (`complete`, `missing_measurements`,
`contradictory_mass`, `changing_conditions`, `biometrics_and_supplements`). No
caller context, personal measurement, HealthKit value, free text or account
selector is accepted.

```json
{"model": "muse-wonder-1.0", "store": false, "stream": false, "background": false,
 "max_output_tokens": 512, "reasoning": {"effort": "minimal"},
 "text": {"format": {"type": "json_schema", "name": "hydration_context_selection",
                     "strict": true, "schema": "<Selection schema>"}},
 "input": [{"role": "user", "content": [{"type": "input_text",
            "text": "<reviewed V2 prompt> Context: <canonical scenario JSON>"}]}]}
```

The scenario JSON holds the synthetic context and the authoritative numerical
prediction. `payload_sha256` is the SHA-256 of the canonical payload; any change
to prompt, schema, scenario or model changes it and needs fresh input approval.

## Response handling

The reply must be HTTP 200 with `model == "muse-wonder-1.0"`,
`status == "completed"`, no `error` or `incomplete_details`, exactly one completed
assistant message (reasoning items ignored) and one `output_text` of at most 4,096
characters. That text must be strict JSON matching `Selection`, then pass the
existing `validate_selection`: only supported enum IDs, no omitted contradiction
or required uncertainty, and matching numerical abstention. Anything else is
rejected; there is no repair, retry or mock fallback.

Accepted selections render through the existing reviewed text. The numerical
prediction is copied from the deterministic engine, never from model output.
Live provenance would read `mode: meta_live`, `provider: Meta`,
`model: muse-wonder-1.0`, account `georgiosaliba227` and the ledger attempt ID.
Until a live adapter exists, every response is `mode: mock` with null provider,
model, account and attempt.

## Cost bounds

`worst_case_micro_usd(input_tokens, output_tokens)` prices input at $4 and output
at $20 per million, rounded up, with no cache discount. The existing transport
bounds input at the full context minus the output budget (1,048,064 tokens),
because it never converts bytes into guessed token counts. At Wonder prices that
is about $4.20 per request, which exceeds the $0.25 per-attempt cap, the $2
camera risk policy and 42% of the $10 Wonder target. **A live Wonder request
therefore cannot be admitted under current rules.** Unblocking it needs one of:

1. A provider-verified input token count, once the count endpoint's billing
   status is confirmed.
2. A reviewed text-only bound, for example canonical UTF-8 bytes of the input plus
   a fixed template allowance. This assumes no tokenizer emits more tokens than
   bytes and must be independently reviewed before it is used for admission.

**Adopted (2026-10-28, both developers via Amine):** option 2 as policy
`canonical-payload-bytes-v1`. The bound is the byte length of the canonical
payload JSON (the same serialization the dispatch ticket hashes, which already
includes schema, keys and quoting) plus 256 tokens for provider framing. The
five scenarios bound at 3,623–4,144 tokens, about $0.025–$0.027 per request
including 512 output tokens. Settlement freezes the account if the provider
reports more input tokens than the bound, so a wrong assumption stops spending
after one request. `preview` still reports the full-context figure.

## Live adapter (`backend/wonder_experiment.py`)

Implemented and tested with fake transports only.

- `LIVE_SCHEMA` adds an immutable `experiment_cases` manifest to the proposed
  experiment DDL. It is installed only by tests; the private ledger needs a
  separate reviewed migration.
- `ApprovedCase` binds one case UUID to one exact payload hash and model, with
  input-consent, live-dispatch and spending references and an expiry. One case
  per payload; no update or delete.
- `WonderExperimentLedger` reuses every `ExperimentBudget` admission check ($30
  aggregate, $0.25 per attempt, $75/$100/$120, credits, freeze, prior finality,
  one in flight) and additionally requires the approved case. States:
  `experiment_reserved` → `experiment_dispatched` (one-use nonce) →
  `experiment_sending` → `settled`, or `unresolved` with the account frozen.
  Legacy camera dispatch, send and settlement accept none of these states, and
  review-only reservations cannot be dispatched.
- Settlement prices usage at the reserved quote. Cached tokens, a nonzero extra
  charge bound, a wrong model, a malformed ID or usage are recorded as unresolved
  and freeze the account. Usage above the reserved bounds settles and freezes.
  Settlement ends in `settled`, so the existing invoice-finality gate applies
  before any next request.
- `WonderMetaTransport` reuses the fixed-origin, no-retry official sender but
  accepts only exact Wonder scenario payloads and experiment tickets.
- `WonderHydrationGateway.explain(scenario, case_id, quote, input_reference)`
  reserves, delivers pending $75 notices, dispatches, settles, then validates the
  selection. Any failure after reservation quarantines the attempt; there is no
  retry or mock fallback. Results carry `mode: meta_live`, the Wonder model,
  Georgio's account, the attempt ID, latency, tokens and the usage-derived cost;
  `billed_cost_usd` stays null until invoice finality.

## Operator procedure (`scripts/wonder_admin.py`)

None of these sends a Meta request. Every ledger command opens an existing
owned 0600 ledger only, with the same checks as the finality migration.

1. `prepare --scenario <name>` prints the cost preview and an `ApprovedCase`
   template with the exact payload hash. Humans fill in expiry and references.
2. Run the existing finality migration first (`meta_budget_admin.py
   migrate-finality-schema`); it refuses ledgers that already have triggers.
3. `preview-schema --database <abs path>`, then `migrate-schema --database
   <abs path> --reference <review>` adds only missing `LIVE_SCHEMA` objects
   (version `experiment-live-v1`) and one audit event. Unknown triggers,
   indexes, `experiment_*` objects, altered DDL or an old financial schema are
   refused. Repeats report `already_current`.
4. `record-allocation --descriptor approval.json` imports the immutable $30
   `ExperimentApproval`; `record-case --descriptor case.json` imports one
   `ApprovedCase`.
5. **Billable.** `run-case --database <abs> --scenario <name> --case-id <uuid>
   --descriptor quote.json --input-reference <ref> --results-dir <abs private dir>
   --confirm-billable`, with `HYDRA_META_GEORGIO_API_KEY` and
   `HYDRA_GITHUB_NOTIFICATION_TOKEN` exported in that shell only. It runs the
   gateway once and writes `<scenario>.json` (mode 0600, write-once) into the
   results directory. Without `--confirm-billable` it refuses before touching the
   ledger. Afterwards, record invoice finality before any next case.

## Replay for the app and demo

`POST /v2/hydration-context-comparison` with `{"mode": "recorded", "scenario":
...}` returns the saved result when `HYDRA_WONDER_RESULTS_DIR` names an absolute,
owned, private directory. It never dispatches. A record is served only if
rebuilding it from the deterministic scenario, its re-validated selection and its
provenance reproduces it exactly; otherwise, or when nothing is recorded, the
response is 404. Replays carry the original `meta_live` provenance, attempt ID,
tokens, latency and usage-derived cost; `billed_cost_usd` stays null.

## Review hardening (2026-10-29)

An independent review found no double-send, missing-reservation or
under-counting path. Fixed from its findings: a busy ledger at settlement now
retries the local write (never the network request) so the provider's reply ID
and usage are recorded and failures still quarantine; `run-case` failures name
the reserved attempt and never claim nothing was sent; recorded comparisons
must carry exactly the live provenance; result files must be regular, bounded
JSON objects. Known and accepted: the payload hash covers sorted-key JSON while
the transport sends the same content unsorted (same bytes length and content).

## Still not implemented

- No HTTP route or environment switch dispatches; only the operator `run-case`
  command can, after every ledger gate passes.
- No private ledger has been migrated; no approved case, quote or spending
  approval exists, and no real Wonder request has run.
- No ranking or quality claim. Mock selections are rule-based fixtures.

## iPhone client

The Workout forecast screen has a "Muse Wonder · recorded live result" section.
Its button calls `recordedWonderComparison`, which posts `mode: "recorded"` and
never asks the backend to dispatch. `validateRecorded()` requires `meta_live`
Wonder provenance on Georgio's account with a UUID attempt, all four observation
values present and nonnegative, null `billed_cost_usd`, identical A/C numbers, a
null B prediction and the existing strict interpretation checks. A 404 shows
"No recorded Muse Wonder result is available yet." Connection changes and
leaving the screen discard late replies. The mock A/B/C copy now names Wonder
as the hydration model.
