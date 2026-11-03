"""Durable single-host beverage storage; no credentials or network operations.

HTTP input validation and calculation belong to the backend. This boundary stores
one already-validated response atomically with its idempotency identity.
"""
from contextlib import closing
from datetime import datetime, timezone
import json
import base64
from pathlib import Path
import sqlite3
from typing import Callable


class IdempotencyConflict(Exception):
    """The same owner/key was already used for a different canonical request."""

    def __init__(self) -> None:
        super().__init__("Idempotency key conflicts with an existing request.")


class BeverageNotFound(Exception):
    """No live record with this owner and ID; deleted records are not found."""


class RevisionConflict(Exception):
    """The caller's revision is stale. `current` is the stored record."""

    def __init__(self, current: dict) -> None:
        super().__init__("Beverage revision conflict.")
        self.current = current


class StorageUnavailable(Exception):
    """Storage is unavailable or corrupt; intentionally excludes path/payload."""

    def __init__(self) -> None:
        super().__init__("Beverage storage is unavailable.")


def _invalid_constant(value: str) -> None:
    raise ValueError("Nonfinite stored value")


def _serialize(record: dict) -> tuple[str, str]:
    payload = json.dumps(record, ensure_ascii=False, allow_nan=False,
                         separators=(",", ":"), sort_keys=True)
    instant = datetime.fromisoformat(record["consumed_at"].replace("Z", "+00:00"))
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("An aware timestamp is required.")
    return payload, instant.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _decode(payload: str) -> dict:
    try:
        value = json.loads(payload, parse_constant=_invalid_constant)
        if not isinstance(value, dict):
            raise ValueError("Invalid stored record")
        return value
    except (TypeError, ValueError):
        raise StorageUnavailable() from None


class BeverageRepository:
    """One connection per operation, with persistent owner-scoped idempotency.

    Use a local filesystem path, not :memory: or network-synced storage. Reopening
    the repository never removes records. SQLite FULL synchronous commits and
    transactions preserve replay information with the corresponding beverage.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if str(path) == ":memory:":
            raise ValueError("A persistent database file is required.")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Create private files without temporarily changing the process umask.
            # Existing file permissions are deliberately left to the operator.
            self.path.touch(mode=0o600, exist_ok=True)
            with closing(self._connect()) as connection, connection:
                # A shared financial authority has its own reviewed journal
                # contract. Backend startup must not silently migrate it to WAL.
                financial = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name IN ('live_accounts','meta_policy')"
                ).fetchone()
                self.feedback_enabled = financial is None
                if financial is None:
                    connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS beverages (
                        id TEXT PRIMARY KEY NOT NULL,
                        owner TEXT NOT NULL,
                        idempotency_key TEXT NOT NULL,
                        fingerprint TEXT NOT NULL,
                        consumed_at TEXT NOT NULL,
                        record_json TEXT NOT NULL,
                        UNIQUE(owner, idempotency_key)
                    )
                """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS beverages_owner_time
                    ON beverages(owner, consumed_at DESC, id DESC)
                """)
                # Owner preferences only (e.g. a user-chosen goal); no health records.
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS settings (
                        owner TEXT PRIMARY KEY NOT NULL,
                        settings_json TEXT NOT NULL
                    )
                """)
                if self.feedback_enabled:
                    connection.execute("""CREATE TABLE IF NOT EXISTS local_recognition_receipts (
                        id TEXT PRIMARY KEY NOT NULL, owner TEXT NOT NULL,
                        created_at TEXT NOT NULL, receipt_json TEXT NOT NULL
                    )""")
                    for table in ("recognition_corrections", "recognition_training_examples"):
                        connection.execute(f"""CREATE TABLE IF NOT EXISTS {table} (
                            beverage_id TEXT PRIMARY KEY NOT NULL, owner TEXT NOT NULL,
                            created_at TEXT NOT NULL, feedback_json TEXT NOT NULL,
                            photo BLOB
                        )""")
                        connection.execute(f"CREATE INDEX IF NOT EXISTS {table}_owner ON {table}(owner,created_at DESC)")
        except (OSError, sqlite3.Error):
            raise StorageUnavailable() from None

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        try:
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA secure_delete=ON")  # Overwrite deleted content on disk.
            return connection
        except sqlite3.Error:
            connection.close()
            raise

    def create(self, owner: str, key: str, fingerprint: str,
               record: dict, *, feedback: dict | None = None) -> tuple[dict, bool]:
        """Commit response and request identity together, or replay the original.

        A response generated by a retry may have another candidate UUID; replay
        returns the originally committed UUID and complete response unchanged.
        Conflicts roll back and never replace the first record.
        """
        payload, sort_time = _serialize(record)
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT fingerprint, record_json FROM beverages "
                    "WHERE owner=? AND idempotency_key=?", (owner, key),
                ).fetchone()
                if row is not None:
                    # A deleted log keeps its key, so a late retry cannot resurrect it.
                    if row[0] != fingerprint or _decode(row[1]).get("deleted"):
                        raise IdempotencyConflict()
                    return _decode(row[1]), False
                connection.execute(
                    "INSERT INTO beverages "
                    "(id,owner,idempotency_key,fingerprint,consumed_at,record_json) "
                    "VALUES (?,?,?,?,?,?)",
                    (record["id"], owner, key, fingerprint, sort_time, payload),
                )
                if feedback is not None:
                    if not self.feedback_enabled:
                        raise StorageUnavailable()
                    metadata={k:v for k,v in feedback.items() if k!="photo_bytes"}
                    serialized=json.dumps(metadata,sort_keys=True,separators=(",", ":"),allow_nan=False)
                    values=(record["id"],owner,feedback["created_at"],serialized)
                    if feedback["remember_for_me"]:
                        connection.execute("INSERT INTO recognition_corrections VALUES(?,?,?,?,NULL)",values)
                    if feedback["share_for_training"]:
                        connection.execute("INSERT INTO recognition_training_examples VALUES(?,?,?,?,?)",(*values,feedback["photo_bytes"]))
                        # Disclosed, bounded staging retention. Never touches a
                        # financial table, beverage, or another owner's examples.
                        connection.execute("DELETE FROM recognition_training_examples WHERE owner=? AND beverage_id NOT IN (SELECT beverage_id FROM recognition_training_examples WHERE owner=? ORDER BY created_at DESC,beverage_id DESC LIMIT 20)",(owner,owner))
            return _decode(payload), True
        except sqlite3.Error:
            raise StorageUnavailable() from None

    def list_all(self, owner: str) -> list[dict]:
        """Read one complete owned snapshot; pagination is a backend concern."""
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    "SELECT record_json FROM beverages WHERE owner=? "
                    "ORDER BY consumed_at DESC, id DESC", (owner,),
                ).fetchall()
            records = [_decode(row[0]) for row in rows]
            return [record for record in records if not record.get("deleted")]
        except sqlite3.Error:
            raise StorageUnavailable() from None

    def correction_for(self, owner: str, source_mode: str, image_sha256: str, candidate_key: str,
                       product_signature: str | None) -> dict | None:
        if not self.feedback_enabled:
            return None
        try:
            with closing(self._connect()) as connection:
                rows=connection.execute("SELECT feedback_json FROM recognition_corrections WHERE owner=? ORDER BY created_at DESC,beverage_id DESC",(owner,)).fetchall()
            records=[_decode(row[0]) for row in rows]
            eligible=[r for r in records if r["source_mode"]==source_mode]
            exact=next((r for r in eligible if r["image_sha256"]==image_sha256 and r["candidate_key"]==candidate_key),None)
            match=exact or (next((r for r in eligible if r["product_signature"]==product_signature),None) if product_signature else None)
            if match is None:
                return None
            return {"identity":match["corrected_identity"],
                    "beverage_type":match.get("corrected_type"),
                    "container_ml":match["corrected_container_ml"] if exact else None,
                    "liquid_ml":match.get("corrected_liquid_ml") if exact else None,
                    "match_basis":"exact_image" if exact else "product_label",
                    "confirmed_at":match["created_at"]}
        except (sqlite3.Error,KeyError,TypeError):
            raise StorageUnavailable() from None

    def export_corrections(self, owner: str) -> tuple[list[dict],list[dict]]:
        if not self.feedback_enabled:
            return [],[]
        try:
            with closing(self._connect()) as connection:
                memories=connection.execute("SELECT beverage_id,feedback_json FROM recognition_corrections WHERE owner=? ORDER BY created_at",(owner,)).fetchall()
                training=connection.execute("SELECT beverage_id,feedback_json,photo FROM recognition_training_examples WHERE owner=? ORDER BY created_at",(owner,)).fetchall()
            return ([{"beverage_id":key,**_decode(value)} for key,value in memories],
                    [{"example_id":key,**_decode(value),"photo_base64":base64.b64encode(photo).decode()} for key,value,photo in training])
        except (sqlite3.Error,TypeError):
            raise StorageUnavailable() from None

    def record_local_recognition(self, owner: str, receipt: dict) -> None:
        if not self.feedback_enabled:
            raise StorageUnavailable()
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("INSERT INTO local_recognition_receipts VALUES (?,?,?,?)",
                                   (receipt["recognition_id"],owner,receipt["created_at"],json.dumps(receipt,allow_nan=False)))
                connection.execute("""DELETE FROM local_recognition_receipts WHERE owner=? AND id NOT IN (
                    SELECT id FROM local_recognition_receipts WHERE owner=? ORDER BY created_at DESC,id DESC LIMIT 100
                )""",(owner,owner))
        except (sqlite3.Error,TypeError,ValueError):
            raise StorageUnavailable() from None

    def local_recognition(self, owner: str, identifier: str) -> dict | None:
        if not self.feedback_enabled:
            return None
        try:
            with closing(self._connect()) as connection:
                row=connection.execute("SELECT receipt_json FROM local_recognition_receipts WHERE owner=? AND id=?",(owner,identifier)).fetchone()
            return _decode(row[0]) if row else None
        except sqlite3.Error:
            raise StorageUnavailable() from None

    def export_local_recognitions(self, owner: str) -> list[dict]:
        if not self.feedback_enabled:
            return []
        try:
            with closing(self._connect()) as connection:
                return [_decode(row[0]) for row in connection.execute("SELECT receipt_json FROM local_recognition_receipts WHERE owner=? ORDER BY created_at,id",(owner,))]
        except sqlite3.Error:
            raise StorageUnavailable() from None

    def _delete_feedback(self, connection: sqlite3.Connection, owner: str, beverage_id: str | None = None) -> None:
        if self.feedback_enabled:
            if beverage_id is None:
                connection.execute("DELETE FROM local_recognition_receipts WHERE owner=?",(owner,))
            for table in ("recognition_corrections","recognition_training_examples"):
                if beverage_id is None:
                    connection.execute(f"DELETE FROM {table} WHERE owner=?",(owner,))
                else:
                    connection.execute(f"DELETE FROM {table} WHERE owner=? AND beverage_id=?",(owner,beverage_id))

    def delete_all(self, owner: str) -> int:
        """Erase every live log's content (keeping keys so retries cannot resurrect) and the owner's settings."""
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                rows = connection.execute("SELECT id, record_json FROM beverages WHERE owner=?", (owner,)).fetchall()
                live = [beverage_id for beverage_id, raw in rows if not _decode(raw).get("deleted")]
                for beverage_id in live:
                    tombstone = json.dumps({"deleted": True, "id": beverage_id}, separators=(",", ":"), sort_keys=True)
                    connection.execute(
                        "UPDATE beverages SET consumed_at='', fingerprint='', record_json=? WHERE owner=? AND id=?",
                        (tombstone, owner, beverage_id),
                    )
                connection.execute("DELETE FROM settings WHERE owner=?", (owner,))
                self._delete_feedback(connection,owner)
            return len(live)
        except sqlite3.Error:
            raise StorageUnavailable() from None

    def get_settings(self, owner: str) -> dict | None:
        try:
            with closing(self._connect()) as connection:
                row = connection.execute("SELECT settings_json FROM settings WHERE owner=?", (owner,)).fetchone()
            return _decode(row[0]) if row is not None else None
        except sqlite3.Error:
            raise StorageUnavailable() from None

    def put_settings(self, owner: str, settings: dict) -> dict:
        payload = json.dumps(settings, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute(
                    "INSERT INTO settings (owner, settings_json) VALUES (?, ?) "
                    "ON CONFLICT(owner) DO UPDATE SET settings_json=excluded.settings_json", (owner, payload),
                )
            return _decode(payload)
        except sqlite3.Error:
            raise StorageUnavailable() from None

    def update(self, owner: str, beverage_id: str, revision: int,
               build: Callable[[dict], dict]) -> dict:
        """Replace one live record if `revision` is current; `build` returns the new record.

        `build` may raise ValueError to reject the change; nothing is written then.
        """
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT record_json FROM beverages WHERE owner=? AND id=?", (owner, beverage_id),
                ).fetchone()
                current = _decode(row[0]) if row is not None else None
                if current is None or current.get("deleted"):
                    raise BeverageNotFound()
                if current["revision"] != revision:
                    raise RevisionConflict(current)
                record = build(current)
                if record["id"] != beverage_id or record["revision"] != revision + 1:
                    raise ValueError("Updates keep the ID and advance the revision by one.")
                payload, sort_time = _serialize(record)
                connection.execute(
                    "UPDATE beverages SET consumed_at=?, record_json=? WHERE owner=? AND id=?",
                    (sort_time, payload, owner, beverage_id),
                )
            return _decode(payload)
        except sqlite3.Error:
            raise StorageUnavailable() from None

    def delete(self, owner: str, beverage_id: str, revision: int | None = None) -> None:
        """Erase the record's content, keeping only its ID and idempotency identity.

        With `revision`, a stale caller cannot delete a newer correction.
        """
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT record_json FROM beverages WHERE owner=? AND id=?", (owner, beverage_id),
                ).fetchone()
                current = _decode(row[0]) if row is not None else None
                if current is None or current.get("deleted"):
                    raise BeverageNotFound()
                if revision is not None and current["revision"] != revision:
                    raise RevisionConflict(current)
                tombstone = json.dumps({"deleted": True, "id": beverage_id}, separators=(",", ":"), sort_keys=True)
                # The key alone blocks resurrection; the content fingerprint is erased too.
                connection.execute(
                    "UPDATE beverages SET consumed_at='', fingerprint='', record_json=? WHERE owner=? AND id=?",
                    (tombstone, owner, beverage_id),
                )
                self._delete_feedback(connection,owner,beverage_id)
        except sqlite3.Error:
            raise StorageUnavailable() from None
