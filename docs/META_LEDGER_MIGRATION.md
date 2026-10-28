# Explicit finality-schema migration

This implementation adds the existing `live_finalities` definition to an older, already initialized account ledger. It is a prerequisite for later reviewed invoice-finality imports, not approval for spending, a billable probe, photo disclosure, a second request or the proposed $2 policy. No migration of the real private ledger has been performed by this work.

The operator must use the one authoritative gateway database, keep all billable feature flags disabled, and stop backend and other ledger-writing processes for the maintenance window. Both developers must review the migration and its exact target before execution. Do not run `init` again, create a replacement database, copy an active authority, delete sidecars, reset permits or fabricate invoice evidence.

Preview uses SQLite read-only/query-only mode and does not create files, add tables or change records:

```sh
python -m scripts.meta_budget_admin --database /absolute/private/meta.sqlite3 preview-finality-schema
```

After human review, the separate explicit operation is:

```sh
python -m scripts.meta_budget_admin --database /absolute/private/meta.sqlite3 migrate-finality-schema --reference REVIEW_REFERENCE
python -m scripts.meta_budget_admin --database /absolute/private/meta.sqlite3 preview-finality-schema
```

Replace `REVIEW_REFERENCE` with a bounded, nonsecret review identifier. Never put credentials, provider account IDs, financial evidence or health data in it. Output reports schema status, the target DDL fingerprint and verification count; it exposes no account evidence, balances, keys, response content or private path. `migration_required` identifies the seven-table predecessor. `migrated` means the table and audit event committed together. `already_current` means all eight financial table definitions were verified; a repeat does not insert another event or rewrite existing records. None of these statuses verifies provider access, billing evidence or activation authority.

The operation requires an existing owned mode-0600 regular file at an absolute path with no symlink components or hard links. It accepts the known rollback-journal SQLite layout only. Both preview and migration verify database integrity and exact known financial table definitions, including column types, defaults, nullability, primary keys, uniqueness and the singleton permit check. Unknown or partial financial schemas, malformed existing finality tables, triggers and nonstandard financial indexes are rejected. Unrelated beverage tables remain untouched. WAL databases, leftover journal/WAL/shared-memory files, unsafe permissions, missing files and unavailable writer locks fail closed. These conditions need separately reviewed recovery or schema adaptation; this command does not repair them or remove files.

Migration opens with `mode=rw` (never create), takes `BEGIN IMMEDIATE`, rechecks the schema, creates only `live_finalities(attempt_id TEXT PRIMARY KEY, evidence TEXT NOT NULL, recorded_at TEXT NOT NULL)` and appends one `finality_schema_migrated` event, then commits atomically with synchronous FULL. Existing account evidence, prices, permits and spent flags, attempts, usage, costs, reservations, freezes, notices and previous events are preserved. The new finality table is empty: prior unsettled or unfinalized billing continues to block admission. Existing valid finality records are preserved on an idempotent repeat.

Synthetic tests cover read-only preview, complete record preservation, constraints, malformed/partial schemas, an audit-write failure rollback, process death between table creation and audit insertion, refusal of the resulting journal, idempotence, contention, unsafe paths and CLI separation. SQLite recovery in the crash test is limited to a disposable synthetic fixture. No test proves provider invoice finality, account authorization or successful real Meta inference.
