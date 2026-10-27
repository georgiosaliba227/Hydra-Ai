# Developer onboarding

**Current application:** use [PROTOTYPE_SETUP.md](PROTOTYPE_SETUP.md) for the integrated native app/backend. The starter instructions below are preserved as historical setup and are not the new application entrypoint.

Status: local starter setup verified on Developer A's current Mac only. Developer B's environment, remote collaboration and Meta onboarding remain unverified. Planning PR #1 is merged and cross-component prototype development is authorized.

## Clone and branch
```sh
git clone https://github.com/georgiosaliba227/Hydra-Ai.git
cd Hydra-Ai
git switch -c codex/your-task
```
Read AGENTS.md. Existing code is under `Hydra-Ai-Starter/`; root component folders are planned destinations. Check the intended GitHub account with `gh auth status` locally; never paste tokens. This run's active account could not read repository metadata via gh; Git transport could read origin. Verify access as the intended account before publishing; confirm collaborator access independently.

## Python setup (repository root)
Python 3.14.2 worked on the inspected Mac; compatibility on other machines is not yet verified. Do not replace a working Python/Xcode install unnecessarily.
```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r Hydra-Ai-Starter/backend/requirements.txt pytest httpx
```
Dependencies currently use broad ranges; capture a reviewed reproducible lock during foundation work. No Meta SDK is needed during planning; direct HTTP integration is proposed after endpoint review.

## Start existing backend
From repository root after activation:
```sh
cd Hydra-Ai-Starter
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```
Open http://127.0.0.1:8000/docs. Running inside the nested `backend/` directory as the old starter README suggests can fail to import `ai`; use the starter root above. Only `/health` and `/forecast` exist. Forecast values are demo heuristics.

## Tests
From the starter root with the repository venv activated:
```sh
python -m unittest discover -s tests -v
python -m pytest tests -q
```
Three existing tests passed, and in-process API smoke checks covered health, forecast and invalid input. There is no current XCTest suite. Tests do not establish scientific validity or working Meta/HealthKit integration.

## iOS setup
Inspect `xcode-select -p`, `xcodebuild -version`, and `swift --version`. Source files live in `Hydra-Ai-Starter/ios/HydraAI/`; no `.xcodeproj` exists, so there is no current build/run command. After architecture approval, create a SwiftUI iOS App target, add these sources, choose the team's bundle ID/signing, and run on an available simulator. Camera/HealthKit capabilities, purpose strings and physical-device testing belong to later implementation. Do not claim Apple Watch or HealthKit is connected.

## Secure Meta onboarding checklist
1. Startup track: both developers verify acceptance, age/majority and personal eligibility. Appoint an authorized active-employee startup representative; see HACKATHON_COMPLIANCE.md. Team participation is supported by the rules, but personal eligibility is not established by GitHub usernames.
2. User-confirmed dashboard snapshot: $150.00 shared project credits, $0.00 pay-as-you-go balance, attached payment method (2026-10-26). Verify exact expiry/coverage, historical gross usage, overage terms and team membership; do not infer zero usage from zero balance. Preserve the $120 cumulative-usage cutoff/$30 reserve. Never enable automatic top-ups or share credentials/card details.
3. Verify `muse-spark-1.3` availability, image support and prices against META_MODEL_STRATEGY.md. Choose Standard pending privacy review.
4. Copy `.env.example` to `.env` only when configuring the later backend. Keep keys server-side. Proposed variables: `META_MODEL_API_KEY`, `META_BASE_URL`, `META_MODEL_ID`, `META_BILLABLE_REQUESTS_ENABLED`, `HYDRA_AI_MODE`, `HYDRA_BUDGET_GATEWAY_URL`, optional `WEATHER_API_KEY`. No current code reads or enforces these variables.
5. Implement and test the single authoritative budget gateway with mocks after architecture approval. Meta alerts are not hard caps. Both local clients must share its ledger.
6. Review reconciliation and race/crash tests, establish bounded maximum cost and obtain explicit paid-test approval.
7. Only then run a minimal synthetic bounded authentication/inference test and verify dashboard usage. Authentication tests can be billable; none ran here.

## Collaboration and troubleshooting
Pull main regularly into your own branch; preserve human edits; open reviewed PRs and never auto-merge. See TEAM_WORKFLOW.md and local issue proposals. Main branch protection is proposed, not configured.

- `No module named ai`: run backend/tests from `Hydra-Ai-Starter` with the repository venv active.
- Missing FastAPI/pytest: verify `python` resolves to `.venv/bin/python` and install the documented requirements.
- Missing Xcode project: expected planning-stage limitation; do not infer a build failure.
- Missing HealthKit data: use manual inputs; empty reads do not prove denial.
- Budget service unavailable/unknown price: remain mock-only; do not bypass with a local provider key.
- GitHub metadata lookup fails: verify identity/access; do not switch accounts or overwrite remotes blindly.
