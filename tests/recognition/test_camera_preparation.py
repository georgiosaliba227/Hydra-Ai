"""Exact-image preparation uses synthetic files only and forbids every sender."""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3

import pytest

from backend.meta_accounts import ACCOUNTS, AccountLedger, ControlledPermit, FirstPermit
from backend.meta_camera_preparation import prepare_camera
from backend.meta_provider import request_payload
from backend.meta_images import sanitized_jpeg
from backend.recognition import AnalysisRequest
from test_guarded_meta import JPEG, HASH, evidence, price, future, setup


@pytest.fixture(autouse=True)
def no_sending(monkeypatch):
    def refused(*args, **kwargs):
        pytest.fail("Read-only camera preparation attempted a sender or mutation")
    monkeypatch.setattr(socket.socket, "connect", refused)
    monkeypatch.setattr("http.client.HTTPSConnection.request", refused)
    monkeypatch.setattr("backend.meta_provider.OfficialMetaTransport.generate", refused)
    monkeypatch.setattr("backend.meta_gateway.GitHubNotifier.deliver", refused)


@pytest.fixture
def files(tmp_path):
    directory = tmp_path.resolve()
    ledger = setup(directory)
    env = directory / "backend.env"
    database = Path(ledger.path)
    env.write_text(f"HYDRA_META_GEORGIO_API_KEY=synthetic-key\nHYDRA_META_ACCOUNT={ACCOUNTS[0]}\n"
                   f"HYDRA_DATABASE_PATH={database}\nHYDRA_GITHUB_NOTIFICATION_TOKEN=synthetic-notification-key\n"
                   "HYDRA_AI_MODE=mock\nMETA_BILLABLE_REQUESTS_ENABLED=false\n")
    env.chmod(0o600)
    image = directory / "prepared.jpg"
    image.write_bytes(JPEG)
    image.chmod(0o600)
    return env, database, image


def blocked(report, name):
    return report["gates"][name]["status"] == "blocked"


def test_local_plan_reuses_exact_payload_and_never_authorizes(files, monkeypatch):
    env, database, image = files
    before = {path.name: path.read_bytes() for path in database.parent.iterdir() if path.is_file()}
    environment_before = dict(os.environ)
    def no_mutations(*args, **kwargs):
        pytest.fail("No financial transaction, reservation or initialization permitted")
    for name in ("transaction", "reserve_first", "initialize_accounts", "approve_first_test", "approve_controlled_test"):
        monkeypatch.setattr(AccountLedger, name, no_mutations)
    report = prepare_camera(env, database, image)
    request = AnalysisRequest(image_base64=base64.b64encode(JPEG).decode(), photo_consent=True,
                              meta_photo_consent=True, mode="meta_live")
    digest = hashlib.sha256(json.dumps(request_payload(request), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert report["normalized_image_sha256"] == HASH
    assert report["canonical_payload_sha256"] == digest
    assert report["reservation"]["input_bound_tokens"] == 1_048_064
    assert report["reservation"]["output_bound_tokens"] == 512
    assert report["reservation"]["code_rate_token_reference_micro_usd"] == 1_312_256
    assert report["reservation"]["locally_attested_total_bound_micro_usd"] == 1_312_256
    assert report["policy"]["active_first_request_cap_micro_usd"] == 250_000
    assert report["policy"]["proposed_disabled_cap_micro_usd"] == 2_000_000
    assert blocked(report, "active_cost_ceiling")
    assert not blocked(report, "existing_policy_validation")
    assert report["dispatch_authorized"] is False and report["provider_authentication_performed"] is False
    assert report["network_requests_sent"] == 0 and report["ledger_mutations_performed"] is False
    assert {path.name: path.read_bytes() for path in database.parent.iterdir() if path.is_file()} == before
    assert dict(os.environ) == environment_before
    raw = json.dumps(report)
    for private in ("synthetic-key", "synthetic-notification-key", evidence().key_sha256,
                    evidence().provider_account_reference, "synthetic-dashboard-only", "synthetic-one-request-approval", str(database)):
        assert private not in raw


def test_metadata_normalization_matches_gateway(files):
    env, database, path = files
    data = JPEG[:2] + b"\xff\xe1\x00\x0aPRIVATE!" + JPEG[2:]
    path.write_bytes(data)
    report = prepare_camera(env, database, path)
    assert report["normalized_image_sha256"] == HASH
    assert not blocked(report, "exact_image_consent")
    assert "PRIVATE!" not in json.dumps(report)


def test_different_image_hash_does_not_reuse_consent(files):
    env, database, path = files
    path.write_bytes(JPEG.replace(b"\x00\x10\x00\x10", b"\x00\x11\x00\x10"))
    report = prepare_camera(env, database, path)
    assert report["normalized_image_sha256"] != HASH
    assert blocked(report, "exact_image_consent")


def test_missing_ledger_is_not_created_and_no_baseline_invented(files):
    env, database, path = files
    database.unlink()
    report = prepare_camera(env, database, path)
    assert not database.exists()
    assert blocked(report, "authoritative_ledger_readable")
    assert report["reservation"]["locally_attested_total_bound_micro_usd"] is None


def test_empty_ledger_gives_specific_missing_evidence(files):
    env, database, path = files
    with sqlite3.connect(database) as db:
        db.execute("DELETE FROM live_accounts")
        db.execute("DELETE FROM live_permit")
    report = prepare_camera(env, database, path)
    assert blocked(report, "account_evidence")
    assert blocked(report, "permit_schema_current")
    assert blocked(report, "credential_binding")
    assert report["reservation"]["locally_attested_token_quote_micro_usd"] is None


@pytest.mark.parametrize("mutation", ["wrong_account", "wrong_key", "expired", "nan", "duplicate", "wrong_model", "missing_price", "spent", "whitespace_consent"])
def test_invalid_evidence_never_passes_relevant_gate(files, mutation):
    env, database, image = files
    expected = "account_evidence"
    with sqlite3.connect(database) as db:
        raw = json.loads(db.execute("SELECT evidence FROM live_accounts").fetchone()[0])
        if mutation == "wrong_account":
            raw["account_id"] = ACCOUNTS[1]
        elif mutation == "wrong_key":
            raw["key_sha256"] = "b" * 64
            expected = "credential_binding"
        elif mutation == "expired":
            raw["valid_until"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        elif mutation == "nan":
            raw["gross_micro_usd"] = float("nan")
        elif mutation == "wrong_model":
            value = json.loads(db.execute("SELECT snapshot FROM live_prices").fetchone()[0])
            value["model"] = "unexpected-model"
            db.execute("UPDATE live_prices SET snapshot=?", (json.dumps(value),))
            expected = "bound_price_evidence"
        elif mutation == "missing_price":
            db.execute("DELETE FROM live_prices")
            expected = "bound_price_evidence"
        elif mutation == "spent":
            db.execute("UPDATE live_permit SET spent=1")
            expected = "permit_account_unused"
        elif mutation == "whitespace_consent":
            value = json.loads(db.execute("SELECT permit FROM live_permit").fetchone()[0])
            value["image_owner_consent_reference"] = "   "
            db.execute("UPDATE live_permit SET permit=?", (json.dumps(value),))
            expected = "exact_image_consent"
        serialized = json.dumps(raw)
        if mutation == "duplicate":
            serialized = serialized[:-1] + ',"gross_micro_usd":0}'
        db.execute("UPDATE live_accounts SET evidence=?", (serialized,))
    report = prepare_camera(env, database, image)
    assert blocked(report, expected)
    assert report["dispatch_authorized"] is False


def test_wrong_selected_account_never_uses_amine_key(files):
    env, database, image = files
    report = prepare_camera(env, database, image, ACCOUNTS[1])
    assert blocked(report, "camera_account") and blocked(report, "configured_account")
    assert blocked(report, "credential_binding")


def test_proposed_dual_policy_is_not_activated(files):
    env, database, image = files
    with sqlite3.connect(database) as db:
        original = json.loads(db.execute("SELECT permit FROM live_permit").fetchone()[0])
        db.execute("DELETE FROM live_permit")
        original.update(policy_version="dual-test-v1", purpose="camera", maximum_micro_usd=2_000_000)
        db.execute("INSERT INTO controlled_permits(account_id,permit) VALUES(?,?)", (ACCOUNTS[0], json.dumps(original)))
    report = prepare_camera(env, database, image)
    assert blocked(report, "active_permit_policy")
    assert blocked(report, "active_cost_ceiling")
    assert report["policy"]["proposed_policy_authorized"] is False


def test_other_account_frozen_and_pending_attempts_block(files):
    env, database, image = files
    with sqlite3.connect(database) as db:
        other = evidence(ACCOUNTS[1])
        db.execute("INSERT INTO live_accounts(account_id,evidence,anchor_gross,frozen) VALUES(?,?,0,1)", (ACCOUNTS[1], other.model_dump_json()))
        db.execute("INSERT INTO live_attempts(id,account_id,price,reserved,state,input_bound,created_at) VALUES('synthetic-pending',?,?,1000,'sending',1000,'2026-10-27T00:00:00+00:00')", (ACCOUNTS[1], price().model_dump_json()))
    report = prepare_camera(env, database, image)
    for name in ("project_unfrozen", "prior_invoice_finality", "prior_billing_resolved", "first_project_request_unused"):
        assert blocked(report, name)


@pytest.mark.parametrize("kind", ["env_permissions", "image_permissions", "ledger_permissions", "env_symlink", "image_symlink", "ledger_symlink", "image_invalid", "image_oversized", "schema", "wal", "sidecar"])
def test_invalid_private_files_and_schema_fail_closed(files, kind):
    env, database, image = files
    target = env if kind.startswith("env_") else database if kind.startswith("ledger_") else image
    gate = "private_environment" if kind.startswith("env_") else "authoritative_ledger_readable" if kind.startswith("ledger_") else "prepared_jpeg"
    if kind.endswith("permissions"):
        target.chmod(0o644)
    elif kind.endswith("symlink"):
        original = target.with_suffix(".original")
        target.rename(original)
        target.symlink_to(original)
    elif kind == "image_invalid":
        image.write_bytes(b"private-invalid-image")
    elif kind == "image_oversized":
        image.write_bytes(b"x" * 1_048_577)
    elif kind == "schema":
        with sqlite3.connect(database) as db:
            db.execute("DROP TABLE live_finalities")
        gate = "ledger_schema"
    elif kind == "wal":
        with sqlite3.connect(database) as db:
            db.execute("PRAGMA journal_mode=WAL")
        gate = "authoritative_ledger_readable"
    else:
        Path(str(database) + "-journal").write_bytes(b"synthetic-hot-journal")
        gate = "authoritative_ledger_readable"
    before = {entry.name: entry.read_bytes() for entry in database.parent.iterdir() if entry.is_file()}
    report = prepare_camera(env, database, image)
    assert blocked(report, gate)
    after = {entry.name: entry.read_bytes() for entry in database.parent.iterdir() if entry.is_file()}
    assert after == before
    assert "private-invalid-image" not in json.dumps(report)


def test_shell_text_is_never_executed(files):
    env, database, image = files
    marker = env.parent / "executed"
    env.write_text(f"HYDRA_META_GEORGIO_API_KEY='$(touch {marker})'\n")
    report = prepare_camera(env, database, image)
    assert not marker.exists()
    assert blocked(report, "credential_locally_loadable")
    assert str(marker) not in json.dumps(report)
