# Live Wonder on Hydra's fixed synthetic cases

Status: implemented and tested with fake Meta transports only. No real request
has run.

The backend's owner can send each of Hydra's fixed, server-built synthetic
payloads to Muse Wonder once, without a separate approval file for each:

- 5 workout scenarios,
- 8 suggested questions.

No personal data is involved. After a payload has run once, its saved result
replays for free. So this path spends at most 13 requests in total, about
$0.30 in the worst case.

It runs on whichever account the backend is started with
(`HYDRA_WONDER_ACCOUNT`). Each account uses its own single ledger:

- Amine's ledger, with the $20 allocation (account cutoff $100),
- or Georgio's ledger, with the $30 allocation.

Only the backend's own `HYDRA_API_TOKEN` is accepted. There is no shared or
cross-computer access. The earlier restricted developer tokens (PR #54) were
withdrawn on October 29.

## Turning it on

Record the allocation with `synthetic_dispatch_reference` filled in. Get the
allocation from `wonder_admin templates --account <id>` and import it with
`record-allocation`. An allocation is immutable, so it can't gain this field
later; record it with the field from the start. All other setup is in
WONDER_TRENDS_API.md: the ledger, the evidence, the quote, the key entered with
`read -s`, and `HYDRA_WONDER_LIVE=true`.

Every other spending gate still applies:

- the allocation (never reset),
- the account cutoff,
- $0.25 per request,
- one request in flight,
- no retries,
- unresolved billing and freezes block requests,
- the next request waits for the previous one's invoice finality.

AGENTS.md also requires that no request starts while any attempt on either
account has unresolved billing. Georgio's camera invoice must therefore be
reconciled first (ACCOUNT_RESUME.md step 1), even for a request on Amine's
account.

## API

`POST /v1/wonder/live` with
`{"kind": "scenario"|"question", "id": "...", "confirm_billable": true}`
returns `{replayed, saved, result}`.

`GET /v1/wonder/live` lists every case, whether it is recorded, its worst case,
and the allocation's current exposure.

Each request appends an `experiment_case_requested` ledger event. Errors follow
WONDER_TRENDS_API.md: `wonder_blocked`, `wonder_busy`,
`wonder_attempt_unresolved` with `attempt_id`, and `wonder_unavailable`. After
a request, record its invoice finality
(`meta_budget_admin record-invoice-finality`) before the next one.

## First live results (2026-10-29)

Two scenario requests reached Muse Wonder and settled: `complete` for
$0.011108 and `missing_measurements` for $0.007784. Neither froze the ledger.
Hydra rejected both replies. In the saved `missing_measurements` reply,
Wonder repeated codes, added a factor that scenario doesn't support, and left
out two required uncertainty notes. At that point the schema offered every
code for every scenario.

Since then, each scenario's schema (`scenario_schema`) offers only the codes
that scenario supports, and only for the fields Wonder chooses: factors,
missing information and measurement suggestions. Hydra fills in the required
uncertainty notes, contradictions and numerical abstention itself. Repeated
codes or topics count once. A field or code that isn't offered is still
rejected. These changes give each scenario a new payload hash, so each one
gets one send under the standing approval. The allocation limit still caps
total spending.
