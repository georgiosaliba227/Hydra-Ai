# Hydra AI blockers

Updated October 28, 2026. Record each blocker once; revisit only when new evidence arrives. Continue independent work from NEXT_ACTIONS.md.

## Wonder hydration intelligence

- **Cost bound.** The transport bounds input at the full context (1,048,064
  tokens). At Wonder's $4 input / $20 output per million tokens that is about
  $4.20 per request: above the $0.25 per-attempt cap, the $2 camera risk policy,
  and 42% of the $10 Wonder target. The canonical scenario payloads are
  3.4–3.9 KB, about $0.026 per request if a byte-based bound is approved. Needs a
  reviewed decision (see architecture/WONDER_HYDRATION_API.md).
- **Project freeze.** The PR #14 camera request's invoice finality is unresolved,
  which blocks every new request on any account.
- **No live adapter.** `ExperimentBudget` is review-only by design; the Wonder
  dispatch path is unimplemented.
- **Unconfirmed decisions.** Georgio has not yet confirmed Wonder-only, the
  account choice, or the soft-target split; any unpublished Codex work is unknown.

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
