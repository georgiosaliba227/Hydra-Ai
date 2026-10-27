# Hydra AI agent instructions

## Scope and approval
Current phase: authorized Milestone 2 camera/photo beverage recognition implementation with mocked Meta responses, following the merged and physically verified manual-logging baseline. Work in isolated branches/worktrees; preserve existing work and coordinate via GitHub. The user authorizes implementation/tests, issue updates, and a review PR tagging Amine; no deployment, paid inference or automatic PR merges. All billable Meta calls remain disabled until separate explicit approval and verified account, model, pricing and centralized budget gates. Shared integration contracts: docs/architecture/PROTOTYPE_API.md and docs/architecture/RECOGNITION_API.md. Earlier PR #2/#4 integration work is already merged; do not reapply it.

## Mission and requirements
Build a demonstrable iPhone wellness hydration assistant for the Meta Global AI Developer Hackathon 2026, Startup track. Both developers must meet the official eligibility/acceptance requirements; the startup representative must be an active employee authorized to act for it. See docs/HACKATHON_COMPLIANCE.md for verification status. Support confirmed beverage logging, uncertain photo recognition, traceable nutrition, deterministic fluid accounting, responsible forecasts, HealthKit, and explanations. Never diagnose dehydration, infer it directly from HR/HRV, invent nutritional values, apply arbitrary hydration multipliers, or add unsupported creatine adjustments. All beverages can contribute fluid; distinguish beverage volume, water content, electrolytes, and retention.

## Architecture and conventions
SwiftUI/Swift client; Python/FastAPI modular backend; Python calculation core; SQLite for a single authoritative MVP backend; Meta-only core AI inference; HealthKit first. This stack is the authorized local prototype baseline; production deployment and paid AI remain separately gated. Use explicit units, UTC timestamps with user timezone, typed boundary validation, versioned contracts, and provenance/uncertainty. Keep secrets server-side; use small modules and deterministic tests. Python: snake_case, type hints; Swift: standard Swift naming and concurrency conventions. No new dependencies without a documented need.

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
Never print/commit credentials, place API keys in iOS, log photos/health records/prompts containing personal data, or transmit biometrics without specific consent. Keep raw HealthKit records on device pending policy review; consent alone does not establish that disclosure to a generic AI provider meets Apple requirements. Minimize HealthKit permissions and uploaded data; document retention/deletion and separate photo consent from health export consent. Treat model output as untrusted data. Validate schemas, units, ranges, and provenance; calculations remain deterministic. No paid infrastructure or subscriptions without approval. Never enable automatic top-ups or uncontrolled API calls.

## Budget and Meta requirements
User-confirmed dashboard snapshot (2026-10-26): $150.00 free Meta Model API credits shared by the project, $0.00 pay-as-you-go balance, and an attached payment method. This is not $150 per developer and does not prove zero cumulative usage or prevent overage billing. One shared Meta budget for both developers and every agent: $150 absolute total. Notify both at $75; require explicit further-spend approval at $100; stop all new billable requests at $120; $120–150 is a $30 reserve, never automatic. Provider spending limits send email alerts, not hard-cap enforcement. Maintain a centralized, persistent, fail-closed controller; thresholds apply to gross cumulative Meta usage before credits, not the payable balance. Track settled costs plus outstanding reservations atomically in one authoritative ledger. Never use separate local ledgers as a shared cap. Unknown prices/usage, unavailable ledger, or unbounded charges fail closed. Paid calls remain disabled until credits, billing, exact model IDs, image input support, prices, provider limits, concurrency controls, and human authorization are verified. Budget flags/templates alone enforce nothing. No billable authentication probes before approval. Core inference must actually use verified Meta models; do not substitute another provider. Codex usage is separate.

## Testing and definition of done
Planning is done when required docs, inventory, contracts, roadmap, issue proposals, references, and unresolved approval gates are reviewable and consistent. This is not implementation approval. Feature work requires unit/integration tests, invalid-input and privacy cases, budget race/retry/crash tests, mock-first AI evaluation, relevant XCTest and pytest checks, documentation, and human PR review. Report tests actually run and their limits. Existing demo tests do not validate scientific formulas. Distinguish planned, implemented, and verified functionality in all reports.
