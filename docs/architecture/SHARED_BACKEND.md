# One shared Wonder backend for Georgio and Amine

Status: implemented and tested with fake Meta transports only. No real request
has run. Policy: AGENTS.md, October 29 shared backend paragraph.

## How it works

- **Where things run.** Georgio runs the backend on his Mac, with his Meta key
  and his one ledger. The key never leaves that process, and the ledger never
  leaves his machine.
- **Credentials.** Amine uses his **own** token. The backend knows it only as a
  SHA-256 hash in a private file (`HYDRA_DEVELOPER_CREDENTIALS`). Georgio's
  `HYDRA_API_TOKEN` keeps full access.
- **What Amine's token can reach** (`backend/developer_access.py`, scope
  `wonder`), and nothing else (every other route returns 403):
  - live synthetic Wonder (`/v1/wonder/live`),
  - recorded Wonder comparisons,
  - the assistant, which never includes Georgio's logged total,
  - synthetic workout forecasts.

  It can't reach Georgio's drinks, goal, export, delete-all, trends or spending
  views.
- **Revoking.** Set `"revoked": true` or delete the entry. The file is re-read
  on every request, so no restart is needed. A malformed, shared or missing
  file grants nothing, while the owner token keeps working.
- **Spending.** Amine's requests count against Georgio's existing $30
  experiment allocation. Every request appends an `experiment_case_requested`
  ledger event naming the credential that asked
  (`developer:aminealichaouche:<request id>`). Amine's status view shows only
  the allocation's remaining amount; per-model spending is for the owner.

## Standing synthetic authorization

The allocation may carry `synthetic_dispatch_reference`. With it, each of
Hydra's fixed, server-built synthetic payloads can run without a per-case
approval file:

- 5 workout scenarios,
- 8 suggested questions.

No personal data is involved. Each payload is sent **at most once**. After
that, its saved result replays for free, so this path can spend at most 13
requests, about $0.30 worst case.

Every other spending gate still applies:

- the $30 allocation (never reset; expiry doesn't refund it),
- the $120 account cutoff,
- $0.25 per request,
- one request in flight,
- no retries,
- unresolved billing and freezes block requests,
- the next request waits for the previous one's invoice finality.

A reply rejected after settlement is recorded without freezing, as with trends.

`POST /v1/wonder/live` with
`{"kind": "scenario"|"question", "id": "...", "confirm_billable": true}`
returns `{replayed, saved, result}`. `GET /v1/wonder/live` lists every case,
whether it is recorded, its worst case, and the allocation's current exposure.
Errors follow WONDER_TRENDS_API.md (`wonder_blocked`, `wonder_busy`,
`wonder_attempt_unresolved` with `attempt_id`, `wonder_unavailable`).

## Setup

**Georgio, once:**

1. Restore the account with the PR #53 resume (ACCOUNT_RESUME.md).
2. Run `wonder_admin migrate-schema`. Then
   `wonder_admin templates --account georgiosaliba227`, and record the $30
   allocation with `synthetic_dispatch_reference` filled in and a
   `valid_until` through the hackathon (for example 2026-11-05). Leave
   `trend_dispatch_reference` empty unless you want trends of your own data.
   An allocation is immutable, so choose its validity and standing references
   once. It also can't gain `synthetic_dispatch_reference` later, so record it
   with this field from the start. As far as the docs show, no allocation
   exists in his ledger yet.
3. Save a Wonder quote file (from the same templates output).
4. Create `developers.json` (mode 0600) with the hash Amine sends:

   ```json
   {"version": "developer-credentials-v1", "developers": [
     {"id": "aminealichaouche", "token_sha256": "<hash from Amine>", "scopes": ["wonder"], "revoked": false}]}
   ```

5. Start the backend, bound to this Mac only:

   ```
   read -s HYDRA_META_GEORGIO_API_KEY && export HYDRA_META_GEORGIO_API_KEY
   read -s HYDRA_GITHUB_NOTIFICATION_TOKEN && export HYDRA_GITHUB_NOTIFICATION_TOKEN
   export META_BILLABLE_REQUESTS_ENABLED=true HYDRA_WONDER_LIVE=true HYDRA_WONDER_ACCOUNT=georgiosaliba227 \
     HYDRA_WONDER_LEDGER=/ABS/ledger.sqlite3 HYDRA_WONDER_QUOTE=/ABS/quote.json \
     HYDRA_WONDER_RESULTS_DIR=/ABS/wonder-results HYDRA_DEVELOPER_CREDENTIALS=/ABS/developers.json
   python -m uvicorn backend.app:create_app --factory --host 127.0.0.1 --port 8000
   ```

6. Publish it to Amine over an encrypted private network, never the public
   internet. With Tailscale: `tailscale serve --bg 8000` gives a tailnet-only
   HTTPS address (`https://<mac>.<tailnet>.ts.net`). Share only that machine
   with Amine's Tailscale account. Never use `tailscale funnel`, which is
   public.

**Amine, once:**

1. Make a token and keep it in a password manager:
   `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`.
2. Send Georgio only its hash: `printf %s "<token>" | shasum -a 256`.
3. Join Georgio's shared machine in Tailscale. In the app's Settings, set the
   backend to the `ts.net` address and paste your token. Today and History will
   show "cannot use this feature", because those screens are Georgio's data.
   Use Workout forecast and Ask Hydra instead.
4. Run a case (billable, once):

   ```
   curl -X POST https://<mac>.<tailnet>.ts.net/v1/wonder/live -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" -d '{"kind":"scenario","id":"complete","confirm_billable":true}'
   ```

   The app then shows it under Workout forecast → Muse Wonder (recorded).

**After every request:** Georgio records invoice finality
(`meta_budget_admin record-invoice-finality`) before the next one can run.

## Not verified here

Whether Meta's developer terms allow a teammate to trigger requests through a
backend that holds Georgio's key. The key itself is never shared. Georgio
should confirm this in Meta's API terms or team settings before step 6.
