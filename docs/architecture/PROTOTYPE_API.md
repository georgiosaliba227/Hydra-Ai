# End-to-end prototype API (integration contract)

Authorized local prototype, version 1. Milestone 2 extensions are specified in [RECOGNITION_API.md](RECOGNITION_API.md); its consented mock-image upload and confirmed-recognition fields supersede the original no-image/manual-only limitations below. Refines CONTRACTS.md; only the endpoints below are implemented this milestone. Existing ai/hydration engine stays unchanged. No Meta client or paid requests. Local/private development only; no public deployment.

## Authentication and transport
Backend requires `HYDRA_API_TOKEN` (random, at least 32 characters) and `HYDRA_DATABASE_PATH` (default ./database/hydra.sqlite3). Every /v1 request uses Authorization: Bearer <local development token>; server maps it to a fixed `local-demo` owner. No user-id request field. This single-user development credential is NOT a Meta key. Client configures backend URL and credential at runtime, stores credential in Keychain, and never embeds it in source. Local HTTP allowed only for loopback/private LAN development; use HTTPS otherwise. No health records or images are transmitted. GET /health is public and returns status plus ai_mode=mock and billable_requests_enabled=false. Startup rejects non-mock AI mode or true billable flags.

## POST /v1/beverages
Required `Idempotency-Key`: UUID. JSON (extra fields forbidden):
```json
{"category":"water","consumed_ml":250,"consumed_at":"2026-10-26T15:00:00Z","timezone":"America/New_York","source":"manual"}
```
Consumption: strict integer 1..5000 mL (UI domain bound, not physiological guidance). Category: trimmed nonempty text <=80 chars. Timestamp: explicit RFC3339 offset, year >=2000, no later than server now +60 seconds. Valid IANA timezone. Source manual only. Offset represents an instant; stored timezone is metadata and not an offset-consistency assertion. No arbitrary nutrition input this milestone; composition remains unknown.

201 new / 200 identical replay: flat log fields `id` UUID, `revision` 1, `category`, `consumed_ml` integer, `consumed_at` UTC RFC3339, `timezone`, `source`, `provenance` array, `nutrition` null, `contribution` engine output. Same owner/key with changed canonical request gives 409 idempotency_conflict. Validate and calculate before commit; response persisted/reconstructed deterministically. Retry the exact pending request with the SAME key after ambiguous failure; client persists pending payload/key until success across restarts. Never silently replace an unresolved request with another payload or key.

## GET /v1/beverages
Query `limit` default 100, 1..200; optional `cursor` opaque string. Return `{items:[log...], next_cursor:null|string}` ordered newest consumption first, ID tie-break. Cursor/keyset must not omit existing older items on concurrent inserts. Client follows pagination for complete history. Owner always server-assigned. No date filter in this first version; use summary endpoint for authoritative daily accounting.

## GET /v1/summary?date=YYYY-MM-DD&timezone=America/New_York
Return `{local_date, timezone, beverage_total_ml, estimated_water_ml, log_revisions, provenance, uncertainty_reasons, method_version:"hydration-accounting-v1", forecast_status:"insufficient_data"}`. Use ai.hydration.summarize_day over complete owned snapshot (not a page); timezone calendar dates handle DST. Null physical-water estimate for any unknown composition. No personalized goal/remaining requirement or category multiplier. Dashboard uses this server total.

## Errors
Every error has `{code,message,request_id,retryable}` without sensitive values. 401 unauthorized; 422 invalid_request; 409 idempotency_conflict; 503 storage_unavailable (retryable). Unexpected internal errors: 500 internal_error, no traceback/body echo. No request body/authorization logging. Request bodies <=16 KiB. No recognition/assistant route calls external inference; unsupported routes 404.

## Database interface (internal; ownership database agent)
`database.repository.BeverageRepository(path)` creates schema. `create(owner: str, key: str, fingerprint: str, record: dict) -> tuple[dict,bool]` returns persisted record and created flag in one transaction, raises `IdempotencyConflict` if fingerprint differs. `list_all(owner)->list[dict]` consistent snapshot ordered consumed_at DESC, id DESC; backend paginates (MVP scale). Record JSON contains whole stable response including engine contribution; fingerprint hashes canonical validated input only. Store normalized UTC timestamps for deterministic ordering. `StorageUnavailable` wraps SQLite failures without sensitive details. Durable uniqueness on (owner,key) and records ID, connections per operation for safe threading, atomic transaction, no automatic record pruning. No global network-synced database.

## Verification
API round trip, replay/conflict/concurrent writes, restart persistence, cross-owner repository isolation and API auth, extra/invalid fields, full history/summary, UTC/local midnight and DST, errors and blocked AI flags. iOS URLSession contract tests, persisted pending mutation retry, failure state, and actual simulator backend logging/relaunch. Physical iPhone verification reported separately.
