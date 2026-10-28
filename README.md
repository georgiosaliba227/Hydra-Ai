# Hydra AI

Native iPhone wellness prototype for the Meta Global AI Developer Hackathon 2026 **Startup** track. Manual beverage logging connects SwiftUI to FastAPI and SQLite, with deterministic accounting from `ai/hydration`. The existing integration is merged through PR #13 (`700fe6d`); see the [project status](docs/PROJECT_STATUS.md).

**Current engineering priority: V2 contextual/hybrid hydration research, supplied longitudinal calibration histories, and a guarded $30 Georgio-only experimental budget.** Camera development is paused; existing camera behavior is preserved. All live Meta requests remain disabled for this phase. The [workout model contract](docs/architecture/WORKOUT_MODEL_API.md) distinguishes measured outcomes, research proxy targets, personal calibration, and synthetic demonstrations. The earlier [Meta activation handoff](docs/META_FIRST_DELIVERY.md) remains a separate gated workstream.

## Run the prototype

See [prototype setup and demo](docs/PROTOTYPE_SETUP.md) for backend startup, iOS configuration, tests and restart verification. [API contract](docs/architecture/PROTOTYPE_API.md) defines authentication, idempotent logging, pagination and timezone-aware totals.

The dashboard reports **confirmed beverage volume**, not a dehydration measurement or personalized fluid prescription. Composition stays unknown without a verified source. No arbitrary beverage multipliers are used. The older `Hydra-Ai-Starter/` demo remains intact but is not the application's backend or calculation engine.

## Scope and safety

Active development is authorized by both developers as reported in the development chat. The prototype remains for local/private development; public deployment and production authentication are not approved. Camera recognition works with a mock backend and explicit confirmation; selected photos are sent to the configured local backend only after consent. Prepared JPEG export supports review of exact bytes. A guarded Meta adapter and persistent separate-account budget controls are implemented, but all billable requests remain disabled. Raw HealthKit records remain on device. Local forecasts report descriptive intake history and conditional exercise-loss estimates; daily physiological targets remain unavailable.

Updated user report: each developer has a separate $150 allocation, independently unverified. Never pool credits or rotate accounts to bypass limits. Each account keeps its $120 gross cutoff, $30 reserve, $75 notices and $100 additional-approval gate. No spending is authorized; one project-wide first-test gate remains. See docs/API_BUDGET.md. Credits do not prevent overage billing. Never enable automatic top-ups.

## Project documents

- [Current status](docs/PROJECT_STATUS.md), [next actions](docs/NEXT_ACTIONS.md), [decisions](docs/DECISION_LOG.md), and [blockers](docs/BLOCKERS.md)
- [Agent instructions](AGENTS.md)
- [Architecture](docs/ARCHITECTURE.md) and [original draft contracts](docs/architecture/CONTRACTS.md)
- [Product requirements](docs/PROJECT_REQUIREMENTS.md) and [roadmap](docs/ROADMAP.md)
- [Hydration evidence](docs/HYDRATION_MODEL.md) and [engine interfaces](ai/hydration/README.md)
- [Forecast dataset inventory and licenses](docs/FORECAST_DATA_INVENTORY.md), [model and reproduction](docs/FORECAST_MODEL.md), and [separate real/synthetic evaluation](docs/FORECAST_EVALUATION.md)
- [Meta strategy](docs/META_MODEL_STRATEGY.md) and [budget policy](docs/API_BUDGET.md)
- [Developer onboarding](docs/DEVELOPER_ONBOARDING.md), [team workflow](docs/TEAM_WORKFLOW.md), [environment inventory](docs/ENVIRONMENT.md)
- [Startup compliance and human checks](docs/HACKATHON_COMPLIANCE.md)
- [Issue proposals](docs/ISSUE_PROPOSALS.md)

Human PR review is required; no automatic merges. Startup participant eligibility, account credit terms and production readiness remain separate verification tasks.

V2 review work and live gates: [design](docs/HYDRATION_V2_PLAN.md), [aggregate experiment controls](docs/META_EXPERIMENT_BUDGET_V2.md), and [longitudinal evidence](docs/FORECAST_V2_EVALUATION.md). The $20 Spark / $10 Wonder split is a soft planning target within one $30 ceiling. All live experiment dispatch remains disabled; actual provider quality, latency, usage and billing have not been measured.
