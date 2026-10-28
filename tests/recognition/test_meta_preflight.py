import hashlib
import json
import os
import socket
import sqlite3

import pytest

from scripts.meta_preflight import inspect_configuration, read_private_environment


@pytest.fixture
def files(tmp_path, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("Preflight must not connect to network")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    root = tmp_path.resolve()
    env = root / "backend.env"
    env.write_text("HYDRA_META_GEORGIO_API_KEY=private-test-key\nHYDRA_META_ACCOUNT=georgiosaliba227\n")
    env.chmod(0o600)
    ledger = root / "ledger.sqlite3"
    with sqlite3.connect(ledger) as db:
        db.execute("CREATE TABLE live_accounts(account_id TEXT, evidence TEXT)")
    ledger.chmod(0o600)
    return env, ledger


def test_preflight_is_read_only_redacted_and_does_not_authorize(files):
    env, ledger = files
    before = ledger.read_bytes()
    result = inspect_configuration(env, ledger, "georgiosaliba227")
    assert result["credential_locally_loadable"] is True
    assert result["credential_binding"] == "unverified"
    assert result["finality_schema_present"] is False
    assert result["configured_mock"] is True
    assert result["configured_billable_disabled"] is True
    assert result["activation_authorized"] is False
    assert result["provider_authentication_performed"] is False
    assert ledger.read_bytes() == before
    assert "private-test-key" not in json.dumps(result)
    assert hashlib.sha256(b"private-test-key").hexdigest() not in json.dumps(result)


def test_matching_local_binding_is_not_authenticated_access(files):
    env, ledger = files
    with sqlite3.connect(ledger) as db:
        db.execute("INSERT INTO live_accounts VALUES (?, ?)", ("georgiosaliba227", json.dumps({"key_sha256": hashlib.sha256(b"private-test-key").hexdigest()})))
    result = inspect_configuration(env, ledger, "georgiosaliba227")
    assert result["credential_binding"] == "matches_local_attestation"
    assert result["activation_authorized"] is False


@pytest.mark.parametrize("evidence", [None, [], 17, "private-invalid-content"])
def test_malformed_account_attestation_is_redacted_and_fails_closed(files, evidence):
    env, ledger = files
    with sqlite3.connect(ledger) as db:
        db.execute("INSERT INTO live_accounts VALUES (?, ?)", ("georgiosaliba227", json.dumps(evidence)))
    result = inspect_configuration(env, ledger, "georgiosaliba227")
    assert result["credential_binding"] == "unverified"
    assert not result["activation_authorized"]
    assert "private-invalid-content" not in json.dumps(result)


def test_missing_ledger_is_never_created(files):
    env, ledger = files
    ledger.unlink()
    assert not inspect_configuration(env, ledger, "georgiosaliba227")["ledger_readable_private"]
    assert not ledger.exists()


def test_existing_finality_schema_reported_without_migration(files):
    env, ledger = files
    with sqlite3.connect(ledger) as db:
        db.execute("CREATE TABLE live_finalities(attempt_id TEXT, evidence TEXT, recorded_at TEXT)")
    before = ledger.read_bytes()
    assert inspect_configuration(env, ledger, "georgiosaliba227")["finality_schema_present"]
    assert ledger.read_bytes() == before


def test_no_shell_execution_or_environment_mutation(files):
    env, _ = files
    marker = env.parent / "executed"
    env.write_text(f"HYDRA_META_GEORGIO_API_KEY='$(touch {marker})'\n")
    before = dict(os.environ)
    assert read_private_environment(env)["HYDRA_META_GEORGIO_API_KEY"].startswith("$(touch ")
    assert not marker.exists()
    assert dict(os.environ) == before


@pytest.mark.parametrize("kind", ["permissions", "symlink", "duplicate", "shell"])
def test_invalid_private_configuration_refused(files, kind):
    env, _ = files
    if kind == "permissions":
        env.chmod(0o644)
    elif kind == "symlink":
        original = env.with_suffix(".original")
        env.rename(original)
        env.symlink_to(original)
    elif kind == "duplicate":
        env.write_text("KEY=a\nKEY=b\n")
    else:
        env.write_text("source another.env\n")
    with pytest.raises(ValueError):
        read_private_environment(env)


def test_other_account_cannot_inherit_georgio_key(files):
    env, ledger = files
    result = inspect_configuration(env, ledger, "aminealichaouche")
    assert not result["credential_locally_loadable"]
    assert not result["configured_camera_account_matches"]
    assert result["hydration_account_is_fixed_to_amine"]
