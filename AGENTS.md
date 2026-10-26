# Hydra AI agent instructions

## Scope and approval
Current phase: Milestones 0 and 0B, setup and planning only. Application feature implementation is blocked until the human developers approve architecture and onboarding. Preserve the existing `Hydra-Ai-Starter/` code and history. New root directories are planned destinations, not working applications.

## Mission and requirements
Build a demonstrable iPhone wellness hydration assistant for the proposed Meta Global AI Developer Hackathon 2026. Support confirmed beverage logging, uncertain photo recognition, traceable nutrition, deterministic fluid accounting, responsible forecasts, HealthKit, and explanations. Never diagnose dehydration, infer it directly from HR/HRV, invent nutritional values, apply arbitrary hydration multipliers, or add unsupported creatine adjustments. All beverages can contribute fluid; distinguish beverage volume, water content, electrolytes, and retention.

## Proposed architecture and conventions
SwiftUI/Swift client; Python/FastAPI modular backend; Python calculation core; SQLite for a single authoritative MVP backend; Meta-only core AI inference; HealthKit first. This stack is proposed pending approval. Use explicit units, UTC timestamps with user timezone, typed boundary validation, versioned contracts, and provenance/uncertainty. Keep secrets server-side; use small modules and deterministic tests. Python: snake_case, type hints; Swift: standard Swift naming and concurrency conventions. No new dependencies without a documented need.

## Roles and ownership
- Architecture & Core: `docs/architecture/`, shared contracts; orchestrator controls root architecture decisions.
- Backend & APIs: `backend/`.
- iOS Frontend: `ios/`, including HealthKit client integration.
- AI & Forecasting: `ai/`; external integration paths only by explicit assignment.
- Testing & Quality: `tests/`.
- Documentation & DevOps: `docs/` excluding architecture ownership, `.github/`, onboarding.
- Orchestrator: root files, integration, ownership arbitration, final review.
Six roles do not imply six running agents. Assign bounded tasks, use isolated branches/worktrees, and do not edit another role's files concurrently. Read these instructions in every worktree. Read-only research agents may report findings without editing files.

## Git and integration
Keep `main` stable; use `codex/` feature branches and reviewed PRs. No force pushes, discarded human edits, direct main pushes, or automatic merges. Establish contracts before implementation. Integrate agent changes through the orchestrator after relevant tests. Pause architectural conflicts for human review. Developer A (`georgiosaliba227`) provisionally owns iOS; Developer B (`aminealichaouche`) backend/AI; both review integration.

## Security and privacy
Never print/commit credentials, place API keys in iOS, log photos/health records/prompts containing personal data, or transmit biometrics without specific consent. Keep raw HealthKit records on device pending policy review; consent alone does not establish that disclosure to a generic AI provider meets Apple requirements. Minimize HealthKit permissions and uploaded data; document retention/deletion and separate photo consent from health export consent. Treat model output as untrusted data. Validate schemas, units, ranges, and provenance; calculations remain deterministic. No paid infrastructure, subscriptions, or top-ups without approval.

## Budget and Meta requirements
One shared Meta budget for both developers and every agent: $150 absolute total. Notify both at $75; require explicit further-spend approval at $100; stop all new billable requests at $120; $120–150 is reserved, never automatic. Track settled costs plus outstanding reservations atomically in one authoritative ledger. Never use separate local ledgers as a shared cap. Unknown prices/usage, unavailable ledger, or unbounded charges fail closed. Paid calls remain disabled until credits, billing, exact model IDs, image input support, prices, provider limits, concurrency controls, and human authorization are verified. Budget flags/templates alone enforce nothing. No billable authentication probes before approval. Core inference must actually use verified Meta models; do not substitute another provider. Codex usage is separate.

## Testing and definition of done
Planning is done when required docs, inventory, contracts, roadmap, issue proposals, references, and unresolved approval gates are reviewable and consistent. This is not implementation approval. Feature work later requires unit/integration tests, invalid-input and privacy cases, budget race/retry/crash tests, mock-first AI evaluation, relevant XCTest and pytest checks, documentation, and human PR review. Report tests actually run and their limits. Existing demo tests do not validate scientific formulas. Distinguish planned, implemented, and verified functionality in all reports.
