# Hydra AI blockers

## November 3 — latest remaining gaps

- **Real iPhone:** a fresh original-bundle build has valid HealthKit signing, but
  installation/real permissions/workout import/weather/final screens remain
  deferred by the owner. Four actual Simulator flows and 167 unit tests pass;
  these do not establish hardware behavior.
- **Real personal evidence:** the owner needs to collect measurements. Actual
  Muse-guided simulation/training is complete and byte-reproduced, but synthetic
  rows cannot fill personal history or validate real-person accuracy. The Home
  score is an explicitly unvalidated 50/30/20 product rubric.
- **Actual personal Meta flow:** the owner-local backend now reports ready and
  both a real comprehensive synthetic response and real public-only simulation
  plan exist. Own-record disclosure still needs exact preview/consent and a
  recorded verification in the app; no raw HealthKit disclosure is introduced.
- **Billing uncertainty is accepted, not resolved:** the owner explicitly waived
  ongoing billing waits/unknown Amine status, keeping every hold and the same
  $30 allocation. It no longer blocks the configured owner-risk path after all
  other checks pass. Default verified mode retains its gates. Final invoices and
  provider extras remain unverified; a failed/incomplete attempt still blocks.
- **Integration/hosting:** stacked review branches are unmerged. No always-on
  deployment is approved; local access depends on the Mac/LAN and current
  observations. Readiness truthfully blocks after evidence expires.

The newer owner-risk policy supersedes older operational blockers only within
its explicit scope; historical reports below remain unchanged evidence.

## November 3 operational update

Valid HealthKit signing for the original app identifier is now locally verified;
the updated app builds with its entitlement intact. The owner chose Simulator,
so installation and real workout/permission/weather checks remain pending.

The owner waived prior billing waits for one controlled synthetic Wonder test and
accepted unverified extras for all requests without increasing spending limits.
One real eight-section response validated and was saved; actual charges remain
unverified and all historical financial records were preserved. The new native
viewer is read-only. Ordinary ongoing personal dispatch remains separately
configured/default-off; this one-use exception does not grant another send.
See [actual test report](WONDER_OWNER_TEST_2026-11-03.md). Real personal calibration
measurements and prospective accuracy evidence remain missing.

## November 3 evidence gaps

- **Independent personal accuracy:** a stationary model now fits earlier manual
  measurements through v3 research routes, but real dated repeat-workout validation
  is missing. Frozen synthetic abrupt shifts worsen MAE; keep the existing default
  and an explicit experimental option. The temporal learner remains offline. More
  records do not establish better accuracy or calibrated future coverage.
- **Independent population evidence:** the three study targets are incompatible.
  SpectroPhon's reused same-study holdout is not external validation; QDE loses to
  its comparator; EPL retains its baseline and has only six test people. No
  validated drinking requirement or body-hydration percentage follows.
- **Physical HealthKit and final UI:** the connected iPhone passed 132 milestone
  unit tests after a reproduced Date-comparison crash was corrected in a temporary
  copy. Available signing lacks HealthKit for the separate bundle. Production
  HealthKit permissions, physical UI and final v3 hardware behavior remain
  unverified; the user requests Simulator for remaining tests. See the physical
  report rather than treating the earlier connection failure as current.
- **Live comprehensive Wonder evidence:** mock/checked-template tests do not
  establish actual model usefulness, account authorization, pricing or project-wide
  invoice finality. Comprehensive dispatch remains separately off by default. No
  provider request or private financial operation was attempted.
- **Human integration review:** v3/date compatibility integration, 145 native
  tests and three actual Simulator flows pass, including a fitted forecast from
  six saved synthetic records through local analysis, preview and deletion. Numerical/backend/native reviews
  have no outstanding findings, and the integrated 1,284-test Python suite passes.
  [PR #71](https://github.com/georgiosaliba227/Hydra-Ai/pull/71) is open with Amine
  requested as reviewer. PR #65 remains its dependency; human merge is required.

Earlier dated account reports below are historical and may conflict; current user
instructions and fresh private evidence govern future live operation.

Updated October 29, 2026. Record each blocker once; revisit only when new evidence arrives. Continue independent work from NEXT_ACTIONS.md.

## Top blocker: no way to lift an account freeze

Update (PR #14 on main): Georgio's resume template shows the camera attempt is
still `billing_pending` with no final charge. The earlier relayed report that
its finality was recorded was therefore incorrect. `reconcile-risk-invoice` now
ships on main, and the template prints the exact finality file to fill in
(ACCOUNT_RESUME.md step 1). Reconciling comes before preview and resume.

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
