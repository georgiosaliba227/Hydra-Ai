# Resuming a frozen account

Status: implemented and tested on synthetic ledgers, including PR #14's real
camera flow in a scratch merge (approve → send → settle → reconcile → resume →
Wonder case). Nobody has run it on the real private ledger. Do that only after
Georgio approves the exact approval and evidence files below.

## Why it exists

Every settlement, failure or PR #14 risk request freezes the account, and a
frozen account blocks every request in that ledger. Before this change, no code
ever lifted a freeze. Georgio's account has been frozen since his camera
request.

## What it does

`backend/meta_resume.py` and its operator script
`scripts/meta_account_resume.py` (no HTTP route) offer two commands:

- `preview` is read-only. It lists every blocker for this exact approval and
  evidence.
- `resume` lifts the freeze only if `preview` would pass. In one locked
  transaction it:
  - replaces the account's evidence with the fresh evidence,
  - sets its anchor to that evidence's gross,
  - clears `frozen`,
  - appends one `account_resumed` event. The event records the approval, the
    **previous evidence verbatim** (for example PR #14's `RiskEvidence`), the
    previous anchor and the new evidence's hash.

It never touches attempts, finalities, permits, notices or earlier events. A resumed ledger also
never approves another first-test or dual-test permit (`verify_never_resumed`), and the command refuses
a ledger with any trigger beyond the reviewed Wonder immutability triggers. An overrun acknowledged in a
resume no longer blocks Wonder for that exact attempt; any other overrun still blocks new admissions.
A spent permit stays spent, so PR #14's one-time camera permit can never be
reused. The $30 experiment allocation and its limits are unchanged.

## Blockers (each one stops the resume)

| Blocker | Meaning |
| --- | --- |
| `unspent_permit_would_reactivate` | A first-test or controlled permit is unspent; resuming would reopen it |
| `key_changed_not_acknowledged` | The fresh evidence binds a different API key; reviewers must set `new_key_acknowledged` |
| `account_not_frozen` | Nothing to resume. This also makes a repeat or concurrent resume a no-op refusal |
| `attempt_not_finalized:<id>` | Some attempt in the ledger (any account) is not settled with matching invoice finality. A timeout or a reply without usage cannot be reconciled, so it blocks permanently |
| `reconciled_attempts_do_not_match_ledger` | The approval must name every attempt on the account, with its exact provider ID and final charge |
| `overrun_not_acknowledged` | A final charge exceeded its reservation; reviewers must set `overrun_acknowledged` |
| `undelivered_notices` | A $75 notice hasn't reached both developers |
| `evidence_gross_below_recorded_spending` | Fresh provider gross must include everything already recorded |
| `account_at_operational_cutoff` | The new exposure would reach $120 |
| `evidence_names_another_provider_account`, `key_belongs_to_another_account`, `account_not_attested` | Identity checks |

How exposure is counted: earlier attempts are counted on top of the new
anchor. A charge already included in the fresh dashboard gross is therefore
counted twice. That overstates spending, never understates it.

## Files the reviewers prepare (mode 0600, outside Git)

**`resume-approval.json`** (`ResumeApproval`, valid for at most 24 hours):

```json
{"version": "account-resume-v1", "account_id": "georgiosaliba227",
 "reconciled_attempts": [{"attempt_id": "<uuid>", "provider_id": "resp_...", "final_gross_micro_usd": 0}],
 "overrun_acknowledged": false,
 "provider_reconciliation_reference": "<where the final invoice was checked>",
 "spending_approval_reference": "<new approval for further requests>",
 "georgio_review_reference": "...", "amine_review_reference": "...",
 "reason": "...", "valid_until": "<ISO time within 24h>"}
```

**`fresh-evidence.json`** (`Evidence`, the same fields as `attest-account`):
current gross, credits remaining and key hash from Meta's billing page. The
Wonder ledger requires `all_charge_categories_verified: true` and an
`extra_charge_bound_micro_usd`.

## Steps for Georgio's account

1. If the camera attempt is still `billing_pending`, run
   `meta_budget_admin reconcile-risk-invoice` (PR #14) with its final invoice.
   Georgio reports this is done.
2. Write the two files. Get the attempt ID, provider ID and final charge from
   `meta_budget_admin view` or the reconciliation record.
3. Stop the backend, so the ledger has no `-wal` or `-journal` file; the command
   refuses to open a ledger that has one. Then run
   `python -m scripts.meta_account_resume preview --database /ABS/ledger --approval ... --evidence ...`
   until `would_resume` is `true`.
4. Both developers approve the exact files. Then run the same command with
   `resume`.
5. For Wonder on this ledger: `wonder_admin migrate-schema`, then record the
   $30 allocation (WONDER_TRENDS_API.md).
