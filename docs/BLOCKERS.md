# Hydra AI blockers

Updated October 29, 2026. Record each blocker once; revisit only when new evidence arrives. Continue independent work from NEXT_ACTIONS.md.

## Top blocker: no way to lift an account freeze

Update (account resume PR): a reviewed resume command now exists
([ACCOUNT_RESUME.md](architecture/ACCOUNT_RESUME.md)). It lifts a freeze only
after every attempt has matching invoice finality, and it keeps all history and
spent permits. It also replaces PR #14's `RiskEvidence` with fresh `Evidence`,
which removes the Wonder incompatibility described below. What remains is human:
Georgio writes the approval and evidence files, both developers approve them,
and he runs it on his real ledger. Timeouts or replies without usage still
cannot be resumed.

October 29 update: this now blocks **Georgio's** account only. Wonder trend
explanations can run on Amine's account through a ledger file of his own
(WONDER_TRENDS_API.md), which Georgio's freeze doesn't touch. Two checks remain:
Georgio's camera invoice must be final first (AGENTS.md project-wide rule).
Georgio reports he has recorded that finality (relayed 2026-10-29). He still
needs to confirm that his ledger does not also attest Amine's account.

Every attempt that ends in usage settlement, a failure or (on PR #14) a
successful risk-policy request freezes that account, and
`verify_project_unfrozen` then blocks **all** project admission and dispatch,
on both accounts. No code on `main` or PR #14 ever clears `frozen`; PR #14's
`reconcile_risk_invoice` records finality but explicitly does not unfreeze.
After Georgio's first camera request, no further Meta request (including the
Wonder demo recordings) can run until the developers decide how spending may
resume.

Independent read-only analysis of PR #14 (2026-10-29, merged tree 824 tests
passed) confirms its controls hold and adds three facts:

- After the PR #14 request, that ledger is frozen permanently; nothing sets
  `frozen=0`, `spent=0` or removes attempts.
- The Wonder experiment cannot use that ledger even if unfrozen: it reads
  account evidence as `Evidence`, but PR #14 stores `RiskEvidence`, and
  `attest_account` refuses to replace existing evidence. Conversely, any Wonder
  attempt blocks `approve_risk_test`.
- A timeout, or a reply with a provider ID but no usage, leaves the attempt
  `unresolved` and permanently unreconcilable: `reconcile_risk_invoice` and
  `record_invoice_finality` both reject it.

So a real Wonder demo needs a human decision on one of: (a) a reviewed resume
path plus Wonder support for `RiskEvidence` on the same ledger, or (b) a
separate authoritative ledger for the Wonder experiment. (b) must still respect
AGENTS.md: one authoritative ledger per account, never independent active
copies, with the old ledger's history carried into the new account baseline.

Proposed, not implemented: an explicit `resume_account(account, references)`
operator command that succeeds only when every attempt on that account has
recorded invoice finality, no attempt is unresolved or billing-pending, any
overrun is recorded truthfully, both developers' review references are given
and a fresh spending approval exists; it records an immutable audit event and
never resets permits or history. Build it after PR #14 merges, since both touch
`backend/meta_accounts.py`.

## Wonder hydration intelligence

- **Input bound (resolved).** Policy `canonical-payload-bytes-v1` bounds input at
  payload bytes plus 256 tokens, about $0.025–$0.027 per request, instead of the
  full-context $4.20. Settlement freezes the account if the provider exceeds it.
- **Project freeze.** The PR #14 camera request's invoice finality is unresolved,
  which blocks every new request on any account.
- **Activation.** The live adapter and the operator `run-case` command exist,
  but `LIVE_SCHEMA` is not migrated into the private ledger and no approved
  case, current evidence or spending approval exists. No HTTP route dispatches.
- **Physical device.** New screens (edit/delete, Ask Hydra, goal, recorded
  Wonder, export and delete-all) are verified on the simulator only.

## Current forecasting limits

- PR #13 is now merged (`700fe6d`). The new forecasting changes require their own
  human review; the older integration-review row below is historical.
- Accessible exercise studies supply mass-loss proxies, not direct sweat collection
  or daily intake requirements. Missing environment/intensity and differing
  protocols prevent a generalization claim. Cold starts without comparable personal
  calibration remain `insufficient_data`.
- Public source metadata does not guarantee privacy or unique participants:
  preprocessing removes identifiers and conservatively groups repeated source
  identities. The source inventory records actual file counts and licensing limits.
- Simulator tests do not replace physical-device verification of the new forecast
  screen. Personal calibration is transient and not clinically validated.
- Camera work is paused. This branch does not inspect or modify the private ledger
  and does not resolve the earlier live-provider gates recorded below. Consult
  current [Issue #8](https://github.com/georgiosaliba227/Hydra-Ai/issues/8) for that
  separate workstream; historical rows are not a fresh audit of its private state.

## Earlier Meta workstream blockers — historical

| Blocker | Needed evidence / decision | Owner / affected work |
| --- | --- | --- |
| Human integration review | Review existing PR #13 and the exact Meta-first changes; humans decide merge order for #9/#10/#11/#13. The previous missing-PR blocker is resolved | Georgio and Amine; reviewed activation/main integration |
| Live Meta cost and policy | Provider-backed whole-request gross bound including internal/failed/timeout/extra charges; current full-context token allowance exceeds $0.25. A $2 proposal is not permission to replace the first-test limit | Selected account owner + both reviewers; live dispatch only; [Issue #8](https://github.com/georgiosaliba227/Hydra-Ai/issues/8) |
| Account evidence and approvals | After Georgio's sign-in, selected account billing/credit/model and all-key/all-model usage views were inspected. Full historical/pending gross baseline, finality, key binding, funding-specific content-use/expiry/grant terms, custody, notification delivery and exact-image/spending approval remain unresolved. Keep private dashboard/financial details outside GitHub | Georgio + provider; Amine's separate evidence is deferred until he is ready |
| Invoice finality / reconciliation | Authenticated final request billing and reviewed finality evidence. Mismatched, unknown or extra charges remain frozen; new gate implementation does not establish provider truth | Both reviewers + provider; any next attempt |
| Authoritative schema activation | Explicit existing-only migration code/tests and read-only preview are ready; preview confirms the seven-table predecessor is compatible and needs migration. Both developers separately review the operation before execution via META_LEDGER_MIGRATION.md; never use init again | Humans; actual ledger remains unchanged, all live settings disabled |
| Physical integration verification | Owned-image export/share byte equality and camera/HealthKit permission paths on an actual iPhone; synthetic mock-only backend first | Georgio; final device/demo verification |
| Scientific recommendations | Approved population, method, measurement quality and calibration evidence before daily needs/targets or drinking prescriptions | Both developers; conditional arithmetic is not validated future coverage |
| Startup eligibility and portal | Each developer's acceptance/eligibility, rule agreement, authorized active-employee representative, portal fields/rights/access/video requirements | Both developers; final submission |
| Possible unpublished overlapping work | Amine confirms any unpublished branch touching assigned paths; GitHub coordination posted | Amine; stop only if an actual irreconcilable conflict appears |

For the immediate Meta milestone, use the consolidated exact activation checklist in [META_FIRST_DELIVERY.md](META_FIRST_DELIVERY.md). Current local preflight confirms Georgio's key loads without a provider request; it reports missing local account/key evidence, notification credential, finality schema and configured authority-path match. These are actionable configuration/evidence gaps, not a request to repeat earlier inventories. No private settings were changed.

The prepared [Meta support inquiry](META_BILLING_SUPPORT_INQUIRY.md) remains unsent. The user authorized GitHub coordination, not provider/organizer messages. No repeat request for permission is needed for ordinary mock coding/testing/docs.

## Known local limitations

A beverage timestamp accepted within the existing 60-second clock-skew allowance can temporarily make the strict forecast endpoint return 422 until that timestamp passes. Logging remains available; native forecast errors must remain separate. No future event is silently counted as already consumed.

The preserved starter is a historical demo with separate tests and unapproved heuristics. Existing Starlette/httpx TestClient deprecation warning is nonblocking; no dependency change was made solely to silence it. No GitHub CI result is claimed from local test output.
