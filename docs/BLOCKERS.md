# Hydra AI blockers

Updated October 27, 2026. Record each blocker once; revisit only when new evidence arrives. Continue independent work from NEXT_ACTIONS.md.

| Blocker | Needed evidence / decision | Owner / affected work |
| --- | --- | --- |
| Human integration review | Review existing PR #13 and the exact Meta-first changes; humans decide merge order for #9/#10/#11/#13. The previous missing-PR blocker is resolved | Georgio and Amine; reviewed activation/main integration |
| Live Meta cost and policy | Provider-backed whole-request gross bound including internal/failed/timeout/extra charges; current full-context token allowance exceeds $0.25. A $2 proposal is not permission to replace the first-test limit | Selected account owner + both reviewers; live dispatch only; [Issue #8](https://github.com/georgiosaliba227/Hydra-Ai/issues/8) |
| Account evidence and approvals | Authenticated selected-account/key mapping, credits/expiry/restrictions, gross/pending usage across keys, custody, notification delivery, exact request/image consent and expiring spending authorization | Selected owner; no credentials or private evidence in GitHub |
| Invoice finality / reconciliation | Authenticated final request billing and reviewed finality evidence. Mismatched, unknown or extra charges remain frozen; new gate implementation does not establish provider truth | Both reviewers + provider; any next attempt |
| Authoritative schema activation | Review the new finality schema and operational migration separately before use with the existing permanent ledger | Humans; current ledger remains unchanged, all live settings disabled |
| Physical integration verification | Owned-image export/share byte equality and camera/HealthKit permission paths on an actual iPhone; synthetic mock-only backend first | Georgio; final device/demo verification |
| Scientific recommendations | Approved population, method, measurement quality and calibration evidence before daily needs/targets or drinking prescriptions | Both developers; conditional arithmetic is not validated future coverage |
| Startup eligibility and portal | Each developer's acceptance/eligibility, rule agreement, authorized active-employee representative, portal fields/rights/access/video requirements | Both developers; final submission |
| Possible unpublished overlapping work | Amine confirms any unpublished branch touching assigned paths; GitHub coordination posted | Amine; stop only if an actual irreconcilable conflict appears |

For the immediate Meta milestone, use the consolidated exact activation checklist in [META_FIRST_DELIVERY.md](META_FIRST_DELIVERY.md). Current local preflight confirms Georgio's key loads without a provider request; it reports missing local account/key evidence, notification credential, finality schema and configured authority-path match. These are actionable configuration/evidence gaps, not a request to repeat earlier inventories. No private settings were changed.

The prepared [Meta support inquiry](META_BILLING_SUPPORT_INQUIRY.md) remains unsent. The user authorized GitHub coordination, not provider/organizer messages. No repeat request for permission is needed for ordinary mock coding/testing/docs.

## Known local limitations

A beverage timestamp accepted within the existing 60-second clock-skew allowance can temporarily make the strict forecast endpoint return 422 until that timestamp passes. Logging remains available; native forecast errors must remain separate. No future event is silently counted as already consumed.

The preserved starter is a historical demo with separate tests and unapproved heuristics. Existing Starlette/httpx TestClient deprecation warning is nonblocking; no dependency change was made solely to silence it. No GitHub CI result is claimed from local test output.
