# Prototype SQLite storage

`BeverageRepository(path)` initializes a durable local database without deleting existing records. Backend code owns validation and calculates the complete response before calling `create(owner, key, fingerprint, record)`. The repository stores that response and the canonical-request fingerprint in the same transaction. Replays return the first saved response, including its original UUID. A changed fingerprint raises `IdempotencyConflict`; failed inserts roll back and do not consume a key.

`list_all(owner)` reads one complete owner-scoped snapshot ordered by normalized UTC consumption time descending, then ID descending. The JSON response is preserved; the ordering column separately normalizes equivalent RFC3339 representations. The backend handles pagination and passes complete snapshots to the hydration engine.

Each operation opens/closes its own connection, with a five-second busy timeout, WAL journal and FULL synchronization. Files are created with mode 0600; existing permissions are not changed. SQLite failures and malformed stored JSON raise a generic `StorageUnavailable` without paths, SQL or beverage data. `:memory:` is intentionally rejected because per-operation connections require a persistent file. No Meta client, credentials, network access, auto-pruning or budget ledger exists here.

Keep the database on one host's local filesystem and exclude its database, WAL and SHM files from version control/backups shared publicly. This is single-user prototype storage, not encryption at rest or a distributed database. A server restart with the same path retains entries and replay identities. Deployment, migrations beyond this initial schema, account lifecycle and retention/deletion remain later reviewed work.

From repository root:
```sh
python -m pytest tests/database -q
python -m unittest discover -s tests/database -v
```
Tests cover reopen/replay, concurrent identical and conflicting requests, owner isolation, record-ID collision rollback, temporal ordering, malformed/nonfinite data, sanitized storage failures and private file creation.
