# Proposed GitHub issues

Drafts only; not published. Each implementation issue depends on architecture/onboarding approval.

| ID / title | Proposed owner | Dependencies | Acceptance criteria |
|---|---|---|---|
| P0 Approve architecture and onboarding | Both | planning docs | record decisions and resolve blocking questions |
| P1 Verify official hackathon and Meta access | Both | official event link/account dashboard | rules, dates, team, exact models, pricing/credits evidenced |
| P2 Freeze v1 contracts and starter migration | Architecture & Core | P0 | reviewed schema/fixtures and migration preserving history |
| P3 Create Xcode app and manual dashboard | Developer A | P2 | buildable project, confirmed mL entry, manual fallback |
| P4 Persist owned beverage logs | Developer B | P2 | validated CRUD, timezone/idempotency, authorization tests |
| P5 Implement shared spending gateway | Developer B + QA | P1/P2 | atomic caps, crash/retry tests, reconciliation and kill switch |
| P6 Review deterministic hydration method | AI & Forecasting + Both | evidence review | approved assumptions, uncertainty, units, edge-case tests |
| P7 Meta image recognition and confirmation | Developer B + A | P3/P5; paid gate | verified model, provenance, schema validation, no auto-log |
| P8 HealthKit minimal activity import | Developer A | P0/P3 | permissions, denial flow, minimal aggregates, no default health export |
| P9 Nutrition/weather provenance adapters | Developer B | provider approval | source timestamps, caching, missing-data behavior |
| P10 Grounded assistant and forecasts | Developer B + A | P6/P8/P9 | deterministic numbers, consented context and reasons |
| P11 CI and end-to-end evaluation | QA + DevOps | P2 onward | mock-only CI, budget/privacy/contracts, XCTest/pytest |
| P12 Demo and submission | Both | verified rules + M4 | install/demo script, licenses, actual Meta-use evidence |
