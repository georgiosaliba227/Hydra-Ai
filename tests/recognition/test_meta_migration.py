"""Migration tests use disposable synthetic ledgers; never the private authority."""
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys

import pytest

from backend.meta_accounts import AccountLedger
from backend.meta_budget import BudgetDenied
from backend.meta_gateway import GuardedMetaGateway
from test_guarded_meta import setup, image, FakeTransport, FakeNotifier, ACCOUNTS, evidence


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Migration must never use a network")
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def old_ledger(tmp_path):
    ledger = setup(tmp_path.resolve())
    result = GuardedMetaGateway(ledger, ACCOUNTS[0], FakeTransport(), FakeNotifier()).analyze(image())
    ledger.attest_account(evidence(ACCOUNTS[1], baseline=15_000_000))
    with sqlite3.connect(ledger.path) as db:
        db.execute("DROP TABLE live_finalities")
        db.execute("UPDATE live_accounts SET frozen=1 WHERE account_id=?", (ACCOUNTS[1],))
        db.execute("INSERT INTO live_notices VALUES(?,?,?,?,?,?)", ("synthetic-notice", ACCOUNTS[0], ACCOUNTS[1], 75, None, None))
        db.execute("CREATE TABLE beverages(id TEXT PRIMARY KEY, content TEXT NOT NULL)")
        db.execute("INSERT INTO beverages VALUES('synthetic-log','private-synthetic-intake')")
    return ledger, result.recognition_id


def snapshot(path):
    with sqlite3.connect(path) as db:
        names = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {name: db.execute('SELECT * FROM "' + name + '" ORDER BY rowid').fetchall() for name in names}


def test_preview_is_read_only_and_contains_no_financial_evidence(tmp_path):
    ledger, _ = old_ledger(tmp_path)
    before = Path(ledger.path).read_bytes()
    names = sorted(path.name for path in tmp_path.iterdir())
    report = ledger.preview_finality_schema()
    assert report["status"] == "migration_required"
    assert report["financial_tables_verified"] == 7 and report["compatible"]
    assert not report["activation_authorized"] and not report["audit_event_added"]
    assert Path(ledger.path).read_bytes() == before
    assert sorted(path.name for path in tmp_path.iterdir()) == names
    assert all(value not in json.dumps(report) for value in ("synthetic-key", "private-synthetic-intake", "15000000", "resp_testonly"))


def test_additive_migration_preserves_every_old_record_and_adds_one_audit_event(tmp_path):
    ledger, attempt = old_ledger(tmp_path)
    before = snapshot(ledger.path)
    result = ledger.migrate_finality_schema(review_reference="synthetic-review-13")
    assert result["status"] == "migrated" and result["audit_event_added"]
    assert result["existing_records_changed"] is False and result["activation_authorized"] is False
    after = snapshot(ledger.path)
    assert set(after) == set(before) | {"live_finalities"}
    assert after["live_finalities"] == []
    for name, records in before.items():
        assert (after[name][:-1] if name == "live_events" else after[name]) == records
    event = after["live_events"][-1]
    assert event[2:] == (None, "finality_schema_migrated", "account-ledger-finality-v1:synthetic-review-13")
    with ledger.transaction() as db:
        with pytest.raises(BudgetDenied):
            ledger.verify_prior_finalities(db)
        with pytest.raises(BudgetDenied):
            ledger.verify_project_unfrozen(db)
    # Migration does not invent invoice finality, release reservations or reset a permit.
    assert before["live_attempts"][0][0] == attempt
    assert after["live_permit"][0][2] == 1
    assert Path(ledger.path).stat().st_mode & 0o777 == 0o600


def test_idempotence_rechecks_schema_without_mutating_file_or_events(tmp_path):
    ledger, _ = old_ledger(tmp_path)
    ledger.migrate_finality_schema(review_reference="synthetic-review")
    before = Path(ledger.path).read_bytes()
    report = ledger.migrate_finality_schema(review_reference="synthetic-repeat")
    assert report["status"] == "already_current" and report["financial_tables_verified"] == 8
    assert not report["audit_event_added"] and Path(ledger.path).read_bytes() == before
    assert ledger.preview_finality_schema()["target_schema_sha256"] == report["target_schema_sha256"]


def test_existing_invoice_records_are_preserved_on_repeat(tmp_path):
    from test_controlled_tests import finality
    ledger, attempt = old_ledger(tmp_path)
    ledger.migrate_finality_schema(review_reference="synthetic-review")
    value = finality(ledger, attempt)
    with sqlite3.connect(ledger.path) as db:
        db.execute("INSERT INTO live_finalities VALUES(?,?,?)", (attempt, value.model_dump_json(), "2026-10-28T00:00:00+00:00"))
    before = snapshot(ledger.path)
    assert ledger.migrate_finality_schema(review_reference="synthetic-repeat")["status"] == "already_current"
    assert snapshot(ledger.path) == before


def test_corrupt_sqlite_page_fails_integrity_check_without_repair(tmp_path):
    ledger, _ = old_ledger(tmp_path)
    path = Path(ledger.path)
    data = bytearray(path.read_bytes())
    page_size = int.from_bytes(data[16:18], "big")
    data[page_size] = 255  # Invalid page-two btree type; retain valid DB header.
    path.write_bytes(data)
    before = path.read_bytes()
    for operation in (ledger.preview_finality_schema, lambda: ledger.migrate_finality_schema(review_reference="synthetic-review")):
        with pytest.raises(BudgetDenied):
            operation()
        assert path.read_bytes() == before


@pytest.mark.parametrize("sql", [
    "DROP TABLE controlled_permits",
    "ALTER TABLE live_accounts ADD COLUMN unexpected TEXT",
    "CREATE TABLE live_finalities(attempt_id TEXT,evidence TEXT,recorded_at TEXT)",
    "CREATE VIEW live_finalities AS SELECT id AS attempt_id FROM live_attempts",
    "CREATE TABLE live_unknown(id TEXT)",
    "CREATE INDEX unusual_financial_index ON live_events(reference)",
    "CREATE TRIGGER alter_account AFTER INSERT ON live_events BEGIN UPDATE live_accounts SET frozen=0; END",
])
def test_partial_incompatible_or_triggered_schema_fails_without_writes(tmp_path, sql):
    ledger, _ = old_ledger(tmp_path)
    with sqlite3.connect(ledger.path) as db:
        db.execute(sql)
    before = Path(ledger.path).read_bytes()
    for operation in (ledger.preview_finality_schema, lambda: ledger.migrate_finality_schema(review_reference="synthetic-review")):
        with pytest.raises(BudgetDenied):
            operation()
        assert Path(ledger.path).read_bytes() == before


def test_existing_finality_schema_constraints_are_verified_not_merely_table_name(tmp_path):
    ledger, _ = old_ledger(tmp_path)
    with sqlite3.connect(ledger.path) as db:
        db.execute("CREATE TABLE live_finalities(attempt_id TEXT PRIMARY KEY,evidence TEXT NOT NULL,recorded_at TEXT)")
    with pytest.raises(BudgetDenied):
        ledger.migrate_finality_schema(review_reference="synthetic-review")


def test_rollback_after_create_leaves_old_schema_records_and_permits_unchanged(tmp_path, monkeypatch):
    ledger, _ = old_ledger(tmp_path)
    before = snapshot(ledger.path)
    def fail(*args):
        raise RuntimeError("private synthetic error must not escape")
    monkeypatch.setattr(ledger, "event", fail)
    with pytest.raises(BudgetDenied, match="Schema operation refused") as error:
        ledger.migrate_finality_schema(review_reference="synthetic-review")
    assert "private synthetic" not in str(error.value)
    assert snapshot(ledger.path) == before
    assert ledger.preview_finality_schema()["status"] == "migration_required"


def test_process_crash_refuses_pending_journal_and_sqlite_rolls_back_in_fixture(tmp_path):
    ledger, _ = old_ledger(tmp_path)
    before = snapshot(ledger.path)
    script = """import os,sys
from backend.meta_accounts import AccountLedger
ledger=AccountLedger(sys.argv[1])
def crash(db,*args):
 db.execute('PRAGMA cache_size=1')
 db.execute('INSERT INTO live_events(at,kind,reference) VALUES(?,?,?)',('synthetic','synthetic-crash','x'*32768))
 os._exit(23)
ledger.event=crash
ledger.migrate_finality_schema(review_reference='synthetic-crash')
"""
    run = subprocess.run([sys.executable, "-c", script, ledger.path], capture_output=True, text=True)
    assert run.returncode == 23 and run.stdout == run.stderr == ""
    assert Path(ledger.path + "-journal").exists()
    for operation in (ledger.preview_finality_schema, lambda: ledger.migrate_finality_schema(review_reference="synthetic-review")):
        with pytest.raises(BudgetDenied):
            operation()
    # Explicit SQLite recovery ONLY for this disposable fixture. The operator
    # command intentionally performs no recovery of the real financial ledger.
    assert snapshot(ledger.path) == before
    assert ledger.preview_finality_schema()["status"] == "migration_required"
    assert ledger.migrate_finality_schema(review_reference="synthetic-after-recovery")["status"] == "migrated"


@pytest.mark.parametrize("kind", ["missing", "symlink", "parent_symlink", "public", "unowned", "corrupt", "hardlink", "wal", "sidecar"])
def test_unsafe_storage_never_creates_or_changes_database(tmp_path, monkeypatch, kind):
    root = tmp_path.resolve()
    ledger, _ = old_ledger(root)
    path = Path(ledger.path)
    if kind == "missing":
        path.unlink()
    elif kind == "symlink":
        alternate = root / "alias.sqlite3"
        alternate.symlink_to(path)
        ledger = AccountLedger(alternate)
    elif kind == "parent_symlink":
        alternate = root / "alias-directory"
        alternate.symlink_to(root, target_is_directory=True)
        ledger = AccountLedger(alternate / path.name)
    elif kind == "public":
        path.chmod(0o644)
    elif kind == "unowned":
        monkeypatch.setattr("backend.meta_accounts.os.getuid", lambda: path.stat().st_uid + 1)
    elif kind == "corrupt":
        path.write_bytes(b"not sqlite; private contents")
    elif kind == "hardlink":
        os.link(path, root / "hardlink.sqlite3")
    elif kind == "wal":
        with sqlite3.connect(path) as db:
            assert db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    elif kind == "sidecar":
        Path(str(path) + "-journal").write_bytes(b"interrupted synthetic work")
    before = path.read_bytes() if path.exists() else None
    for operation in (ledger.preview_finality_schema, lambda: ledger.migrate_finality_schema(review_reference="synthetic-review")):
        with pytest.raises(BudgetDenied):
            operation()
        assert (path.read_bytes() if path.exists() else None) == before


def test_busy_ledger_refused_without_schema_or_balance_mutation(tmp_path):
    ledger, _ = old_ledger(tmp_path)
    before = snapshot(ledger.path)
    with sqlite3.connect(ledger.path) as db:
        db.execute("BEGIN IMMEDIATE")
        with pytest.raises(BudgetDenied):
            ledger.migrate_finality_schema(review_reference="synthetic-review")
    assert snapshot(ledger.path) == before


@pytest.mark.parametrize("reference", ["", " ", "a" * 201, "secret\nvalue", " review", None])
def test_explicit_bounded_review_reference_required(tmp_path, reference):
    ledger, _ = old_ledger(tmp_path)
    before = Path(ledger.path).read_bytes()
    with pytest.raises(BudgetDenied):
        ledger.migrate_finality_schema(review_reference=reference)
    assert Path(ledger.path).read_bytes() == before


def test_cli_preview_then_explicit_migration_are_distinct(tmp_path):
    ledger, _ = old_ledger(tmp_path)
    command = [sys.executable, "-m", "scripts.meta_budget_admin", "--database", ledger.path]
    preview = subprocess.run(command + ["preview-finality-schema"], capture_output=True, text=True, check=True)
    assert json.loads(preview.stdout)["status"] == "migration_required"
    refused = subprocess.run(command + ["migrate-finality-schema"], capture_output=True, text=True)
    assert refused.returncode != 0 and "Traceback" not in refused.stderr
    migrated = subprocess.run(command + ["migrate-finality-schema", "--reference", "synthetic-cli-review"], capture_output=True, text=True, check=True)
    assert json.loads(migrated.stdout)["status"] == "migrated"
    assert "synthetic-key" not in preview.stdout + refused.stderr + migrated.stdout
