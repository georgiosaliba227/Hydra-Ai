# Architecture

Status: planning PR #1 merged; full development authorization received for the local end-to-end prototype. See architecture/PROTOTYPE_API.md for implemented interface refinements. No paid AI or public deployment authorized.

## Architecture baseline
Use one SwiftUI iPhone client, one modular FastAPI backend, a deterministic Python calculation module, and SQLite on one backend host. Keep the existing nested starter intact until a separately reviewed migration. Prefer an HTTP adapter for Meta once the actual API contract is verified; do not install a guessed SDK.

```text
SwiftUI + HealthKit (local permissions and aggregates)
  -> authenticated FastAPI API
     -> beverage log / forecast core -> SQLite
     -> recognition / explanation adapter
        -> single budget gateway + authoritative SQLite ledger -> verified Meta API
     -> approved nutrition/weather adapters with cache and provenance
```

The gateway can be a module of the same service: no microservices are needed. Both developers' model traffic must use this single service. SQLite is acceptable only on one host with local storage and transactional locking; independent SQLite copies or a network-synced file cannot coordinate spending. If multiple hosts become necessary, review a transactional shared database before enabling paid calls.

## Boundaries
- `ios/`: camera, confirmation, dashboard, local state and HealthKit. Keys never shipped here.
- `backend/`: API validation, authentication, persistence, ownership, request limits and orchestration.
- `ai/`: deterministic contribution/forecast core, Meta adapter, schema validation and evaluation fixtures.
- `integrations/`: approved nutrition/weather adapters; HealthKit remains client-side.
- `database/`: future schema/migrations; separate health records from accounting data.
- `tests/`: unit, contract, budget concurrency, integration and privacy tests.
- `scripts/`: future developer tooling; `.github/workflows/`: future reviewed CI.

## Data and failure handling
Persist confirmed logs with user ownership, consumed volume, timestamps, timezone, provenance, and optional nutrients. Keep estimates separate from observed inputs. Forecasts include method version, input provenance, uncertainty and reasons for changes. Store photos ephemerally and delete after processing by default; retention duration and deletion behavior need approval before implementation. Do not log health payloads or model prompts.

Network/model errors leave manual logging usable. Invalid model JSON, unknown pricing, unavailable ledger or consent denial blocks AI calls. No remote deployment until authentication, transport security, retention/deletion and hosting costs have been reviewed. Local development binds to loopback; device testing needs a separately configured private development connection.

## Tradeoffs and open decisions
SwiftUI suits HealthKit and camera but needs Xcode project/signing setup. SQLite minimizes operations but requires one authoritative host. The starter's heuristic forecast cannot become the production algorithm by renaming it. A verified vision-capable Meta endpoint is a dependency, not an assumption. Weather/product provider, hosting, identity mechanism, baseline method, model ID and remaining participant/submission checks are unresolved.

Shared interfaces: [contracts](architecture/CONTRACTS.md). Budget protocol: [API budget](API_BUDGET.md). Approval gates: [roadmap](ROADMAP.md).

## Local prototype implementation

The integration uses the existing PR #2 SwiftUI app and PR #4 calculation engine, preserving both branch histories. FastAPI authenticates a runtime-configured single-user development token, persists idempotent confirmed manual logs in SQLite, and obtains daily totals from the unchanged engine. URLSession sends logs and reads complete history/server summaries. Physical water composition stays unknown; no personalized target is inferred. Provider calls are absent and non-mock startup settings fail closed. See PROTOTYPE_SETUP.md for local-only operational limits.
