# Muse Wonder trend explanations

Status: implemented and tested with fake Meta transports only. No real request
has run. Policy: AGENTS.md, October 29 Wonder trends policy.

## What it does

The user opens **Today → Your trends · Muse Wonder** on the iPhone. The backend
computes facts about the last 14 local days of logged drinks
(`backend/wonder_trends.py`, `TrendFacts`):

- daily totals and drink counts,
- this week versus last week (totals, averages, logged days, change in percent),
- the user's own goal and how many of the last 7 days reached it,
- the share of each drink type (top 12),
- volume by time of day.

The screen shows those facts as "What would be sent to Meta". Nothing is sent
until the user turns on the consent toggle and taps **Explain my trends**.
Muse Wonder 1.0 then chooses 1 to 3 insights that apply and writes one or two
sentences for each, plus a one-sentence summary.

Wonder cannot write numbers. It writes placeholders such as `{week_total}`,
`{weekly_change}` or `{goal_met_days}`, and Hydra fills in the exact values,
for example "You logged {week_total}, {weekly_change}." becomes "You logged
13600 mL, 21% more than the week before." Direction and quantity come from
Hydra too, so Wonder can't misstate them.

The server rejects the whole reply, without repair or retry, if the wording
contains any of these:

- a digit or a number word ("three", "double", "half"), or a unit;
- a comparison or quantity word ("more", "fell", "most", "every", "never");
- diagnostic, medical, judging or prescriptive wording ("hydrated", "symptom",
  "diabetes", "headache", "cause", "should", "try", "consider", "recommend",
  "good", "bad");
- an unknown placeholder, or a goal placeholder when no goal is set;
- an insight the facts don't support;
- too much text, extra fields, line breaks or links.

The stored result keeps both Wonder's template and Hydra's rendered text.
Replay re-checks the template and renders it again.

## API

`GET /v1/wonder/trends?timezone=<IANA zone>` previews a request. Nothing is sent.

```
{version, facts, explainable, payload_sha256, input_bound_tokens,
 worst_case_micro_usd, live_available, account_id, saved, latest}
```

- `saved` is the stored explanation of exactly this payload, if one exists.
- `latest` is the newest valid stored explanation.

`POST /v1/wonder/trends` with
`{timezone, payload_sha256, consent_to_send: true}` asks for an explanation.

The response is `{replayed, saved, result}`:
- If the stored result for this payload already exists, it is returned with
  `replayed: true` and no charge.
- Otherwise the backend sends one request and stores the validated result
  write-once as `trends-<payload_sha256>.json`.

The same data is never paid for twice. Saved trend results are included in
`GET /v1/export` and removed by `DELETE /v1/data`; the ledger keeps only
payload hashes and amounts. Errors:

| Status | Code | Meaning |
| --- | --- | --- |
| 409 | `trends_preview_stale` | The log changed since the preview; preview again |
| 409 | `wonder_blocked` | A spending gate refused before reservation; nothing was sent |
| 409 | `wonder_busy` | Another request is in progress |
| 422 | `trends_insufficient_data` | No drinks logged in the window |
| 502 | `wonder_attempt_unresolved` | The request failed after reservation; the response includes `attempt_id`. Do not retry; reconcile it |
| 503 | `wonder_unavailable` | Live Wonder is not configured |

## Spending controls (unchanged)

Every request goes through `WonderExperimentLedger` in one private ledger file:

- a cap of $0.25 per request (a typical trend request is about $0.02–0.03 worst case),
- one request in flight,
- invoice finality for every earlier attempt before the next one,
- a $75 notice to both developers,
- a key and account that match the ledger's allocation and evidence, checked
  at startup and again before each reservation, so a wrong key is refused
  without reserving or freezing anything,
- unresolved-billing and frozen-account blocks,
- settlement from Meta's reported usage,
- no retries.

The ledger's single allocation names the only account it may charge:

| Account | Allocation | Account cutoff |
| --- | --- | --- |
| `georgiosaliba227` | `hydration-v2-georgio-30usd`, $30 | $120 |
| `aminealichaouche` | `wonder-amine-20usd`, $20 | $100 (of the reported $150) |
| `georgiosaliba227` (owner override: Georgio's key on Amine's Mac) | `wonder-georgio-key-amine-mac-20usd`, $20, adjustable up to $85 with `wonder_admin set-limit` | $120 |

The quote and the API key must belong to that same account, or the request is
refused before anything is reserved.

Trend requests need a standing approval: `trend_dispatch_reference` on the
allocation. Each request then records its own case, bound to the exact payload
the user consented to.

A reply rejected *after* settlement is recorded as `experiment_output_rejected`
and does not freeze the account, because its charge is already known from
usage. Anything that leaves the charge uncertain still freezes it: over-bound
usage, missing usage or a timeout.

## Setting up live use on Amine's account

Run these from the repository root. Keep every file below private (mode 0600,
outside Git).

1. **Billing check (human).** Georgio confirms that his camera request's
   invoice is final. AGENTS.md forbids starting any request while an attempt on
   either account has unresolved billing. Georgio also confirms that his ledger
   does not attest Amine's account (`meta_budget_admin view`).
2. **Create Amine's ledger:**
   `python -m scripts.meta_budget_admin --database /ABS/amine-ledger.sqlite3 init`
3. **Attest the account.** Write an `Evidence` JSON file (mode 0600) from Meta's
   billing page. Include `key_sha256`, current gross usage and remaining
   credits. Then run `... attest-account --evidence-file /ABS/evidence.json`.
   Get the key hash without printing the key:
   `printf %s "$HYDRA_META_AMINE_API_KEY" | shasum -a 256`.
4. **Add the Wonder tables:**
   `python -m scripts.wonder_admin migrate-schema --database /ABS/amine-ledger.sqlite3 --reference "<review note>"`
5. **Allocation and quote.** Run
   `python -m scripts.wonder_admin templates --account aminealichaouche`. Fill in
   every `REQUIRED` field. Then run
   `... record-allocation --descriptor allocation.json` and save the quote as
   its own file.
6. **Results folder:** `mkdir -m 700 /ABS/wonder-results`
7. **Start the backend.** Set these variables in your own terminal; never put
   them in chat or Git:

   ```
   read -s HYDRA_META_AMINE_API_KEY && export HYDRA_META_AMINE_API_KEY
   read -s HYDRA_GITHUB_NOTIFICATION_TOKEN && export HYDRA_GITHUB_NOTIFICATION_TOKEN
   export META_BILLABLE_REQUESTS_ENABLED=true HYDRA_WONDER_LIVE=true \
     HYDRA_WONDER_ACCOUNT=aminealichaouche HYDRA_WONDER_LEDGER=/ABS/amine-ledger.sqlite3 \
     HYDRA_WONDER_QUOTE=/ABS/quote.json HYDRA_WONDER_RESULTS_DIR=/ABS/wonder-results
   ```

   Startup fails closed if any of them is missing, or if the key doesn't belong
   to the selected account.
8. **In the app:** open Your trends, check the preview, turn on consent and tap
   **Explain my trends**. That is one request.
9. **Before the next request:** once Meta's invoice for it is final, record
   `InvoiceFinality` with `meta_budget_admin record-invoice-finality`. Until
   then, further requests are refused (`wonder_blocked`), and saved results
   keep replaying for free.

Georgio's account works the same way, with `--account georgiosaliba227` and
`HYDRA_META_GEORGIO_API_KEY`. However, his account already has a ledger, and a
second active ledger for the same account is not allowed. He has to wait for
the freeze decision in BLOCKERS.md.
