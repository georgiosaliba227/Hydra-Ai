# Hydra AI

**Hackathon track: Startup.**

Hydra AI aims to combine confirmed beverage logging, Meta-powered beverage recognition, and transparent hydration forecasts in an iPhone wellness app.

**Status: planning and onboarding; PR #1 review and approval required before Milestone 1.** Existing code is a small demonstration under `Hydra-Ai-Starter/`, not a complete app. It contains a FastAPI forecast endpoint, three heuristic tests, and a local SwiftUI water counter. No Meta inference, persistence, HealthKit, image recognition, or shared spending enforcement is implemented. Forecast formulas are illustrative and not validated recommendations.

Start with [developer onboarding](docs/DEVELOPER_ONBOARDING.md), [architecture](docs/ARCHITECTURE.md), and [roadmap and approval gates](docs/ROADMAP.md). All agents must read [AGENTS.md](AGENTS.md).

## Planning documents
- [Product requirements](docs/PROJECT_REQUIREMENTS.md)
- [Shared contracts](docs/architecture/CONTRACTS.md)
- [Meta model strategy](docs/META_MODEL_STRATEGY.md)
- [Hydration evidence and design](docs/HYDRATION_MODEL.md)
- [Shared API budget](docs/API_BUDGET.md)
- [Team workflow](docs/TEAM_WORKFLOW.md)
- [Hackathon compliance](docs/HACKATHON_COMPLIANCE.md)
- [Environment inventory](docs/ENVIRONMENT.md)
- [Proposed GitHub issues](docs/ISSUE_PROPOSALS.md)

## Existing starter tests
From the repository root:
```sh
cd Hydra-Ai-Starter
python3 -m unittest discover -s tests -v
```
See onboarding for backend startup. An Xcode project has not yet been created. Root component directories are future destinations; the nested starter remains intact. Its older roadmap describes the demo and is superseded for project planning by the root `docs/ROADMAP.md`.

User-confirmed billing snapshot (2026-10-26): $150.00 in shared project free credits, $0.00 pay-as-you-go balance, and a payment method attached. Credits do not prevent overage billing. No paid API requests are authorized. Keep the $75 notification, $100 approval gate, and $120 cumulative-usage cutoff with a $30 reserve under the $150 absolute ceiling. The persistent shared controller must fail closed; provider alerts and configuration templates are not hard caps. Automatic top-ups are prohibited. Startup team eligibility conditions and remaining personal checks are recorded in the compliance document.
