# Hydra AI

Hydra AI aims to combine confirmed beverage logging, Meta-powered beverage recognition, and transparent hydration forecasts in an iPhone wellness app.

**Status: planning and onboarding; architecture approval pending.** Existing code is a small demonstration under `Hydra-Ai-Starter/`, not a complete app. It contains a FastAPI forecast endpoint, three heuristic tests, and a local SwiftUI water counter. No Meta inference, persistence, HealthKit, image recognition, or shared spending enforcement is implemented. Forecast formulas are illustrative and not validated recommendations.

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

No paid API requests are authorized. One shared Meta ceiling is $150, with a $100 approval gate and $120 automatic stop. Configuration templates do not enforce those controls.
