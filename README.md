# Hydra AI

Native iPhone wellness prototype for the Meta Global AI Developer Hackathon 2026 **Startup** track. Manual beverage logging connects SwiftUI to FastAPI and SQLite, with deterministic accounting from `ai/hydration`. The integration branch incorporates the existing iOS foundation (PR #2) and calculation engine (PR #4) without merging either GitHub PR automatically.

## Run the prototype

See [prototype setup and demo](docs/PROTOTYPE_SETUP.md) for backend startup, iOS configuration, tests and restart verification. [API contract](docs/architecture/PROTOTYPE_API.md) defines authentication, idempotent logging, pagination and timezone-aware totals.

The dashboard reports **confirmed beverage volume**, not a dehydration measurement or personalized fluid prescription. Composition stays unknown without a verified source. No arbitrary beverage multipliers are used. The older `Hydra-Ai-Starter/` demo remains intact but is not the application's backend or calculation engine.

## Scope and safety

Active development is authorized by both developers as reported in the development chat. The prototype remains for local/private development; public deployment and production authentication are not approved. Camera recognition is unavailable; photos and HealthKit activity remain on device. No AI inference or paid Meta requests are enabled. API startup rejects a non-mock configuration; the shared spending controller remains a future prerequisite for paid calls.

User-confirmed billing: $150 shared project credits, $0 pay-as-you-go balance and an attached payment method. This is not $150 per developer. Keep the $120 cumulative gross-usage cutoff and $30 reserve, with $75 notification and $100 approval gate. Credits do not prevent overage billing. Never enable automatic top-ups.

## Project documents

- [Agent instructions](AGENTS.md)
- [Architecture](docs/ARCHITECTURE.md) and [original draft contracts](docs/architecture/CONTRACTS.md)
- [Product requirements](docs/PROJECT_REQUIREMENTS.md) and [roadmap](docs/ROADMAP.md)
- [Hydration evidence](docs/HYDRATION_MODEL.md) and [engine interfaces](ai/hydration/README.md)
- [Meta strategy](docs/META_MODEL_STRATEGY.md) and [budget policy](docs/API_BUDGET.md)
- [Developer onboarding](docs/DEVELOPER_ONBOARDING.md), [team workflow](docs/TEAM_WORKFLOW.md), [environment inventory](docs/ENVIRONMENT.md)
- [Startup compliance and human checks](docs/HACKATHON_COMPLIANCE.md)
- [Issue proposals](docs/ISSUE_PROPOSALS.md)

Human PR review is required; no automatic merges. Startup participant eligibility, account credit terms and production readiness remain separate verification tasks.
