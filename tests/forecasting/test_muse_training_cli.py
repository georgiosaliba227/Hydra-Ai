"""Offline commands cannot accidentally become a model request or serving write."""
import importlib
import json
from pathlib import Path
import socket
import stat
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from test_muse_synthetic import fixture_records, PLAN


def module():
    return importlib.import_module("scripts.muse_simulated_training")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def reject(*args, **kwargs):
        raise AssertionError("No network in offline research tests")
    monkeypatch.setattr(socket.socket, "connect", reject)


def prepared(tmp_path):
    records = tmp_path / "source-fixture.json"
    records.write_text(json.dumps(fixture_records()))
    directory = tmp_path / "prepared"
    module().main(["prepare", "--records", str(records), "--output", str(directory)])
    return directory


def test_prepare_records_hashes_without_a_plan_network_or_existing_file_replacement(tmp_path, capsys):
    directory = prepared(tmp_path)
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    for name in ("base-records.json", "split-manifest.json", "payload-preview.json"):
        assert stat.S_IMODE((directory / name).stat().st_mode) == 0o600
    preview = json.loads((directory / "payload-preview.json").read_text())
    assert preview["personal_data_used"] is preview["dispatch_enabled"] is False
    assert preview["published_token_bound_micro_usd"] < 250000
    before = (directory / "split-manifest.json").read_bytes()
    with pytest.raises(SystemExit):
        module().main(["prepare", "--records", str(tmp_path / "source-fixture.json"), "--output", str(directory)])
    assert (directory / "split-manifest.json").read_bytes() == before


def test_explicit_offline_stub_training_writes_research_only_bundle(tmp_path, capsys):
    pytest.importorskip("sklearn")
    directory = prepared(tmp_path)
    plan = tmp_path / "offline_stub.json"; plan.write_text(json.dumps(PLAN))
    output = tmp_path / "research"
    module().main(["train", "--prepared", str(directory), "--plan", str(plan),
                   "--origin", "offline_stub", "--output", str(output)])
    report = json.loads((output / "evaluation.json").read_text())
    model = json.loads((output / "model.json").read_text())
    assert report["plan_origin"] == model["plan_origin"] == "offline_stub"
    assert report["muse_inference_used"] is False
    assert model["runtime_use"] == "offline_research_only"
    assert (output / "records.json").is_file() and (output / "split-manifest.json").is_file()
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in output.iterdir())


def test_forged_live_claim_and_unconfirmed_generation_never_create_a_ledger(tmp_path):
    directory = prepared(tmp_path)
    plan = tmp_path / "fake-live.json"; plan.write_text(json.dumps({"plan": PLAN}))
    absent = tmp_path / "absent-ledger.sqlite3"
    with pytest.raises(SystemExit):
        module().main(["train", "--prepared", str(directory), "--plan", str(plan), "--origin", "muse_wonder",
                       "--database", str(absent), "--output", str(tmp_path / "bad-output")])
    with pytest.raises(SystemExit):
        module().main(["generate-plan", "--prepared", str(directory), "--database", str(absent),
            "--policy", str(tmp_path / "policy.json"), "--quote", str(tmp_path / "quote.json"),
            "--consent-reference", "test-only", "--output", str(tmp_path / "plan.json")])
    assert not absent.exists() and not (tmp_path / "bad-output").exists()


def test_raw_synthetic_records_cannot_be_written_inside_the_repository(tmp_path):
    directory = prepared(tmp_path)
    plan = tmp_path / "offline_stub.json"; plan.write_text(json.dumps(PLAN))
    forbidden = Path(__file__).resolve().parents[2] / "muse-research-forbidden-output"
    with pytest.raises(SystemExit):
        module().main(["train", "--prepared", str(directory), "--plan", str(plan),
                       "--origin", "offline_stub", "--output", str(forbidden)])
    assert not forbidden.exists()


def test_private_operator_json_preserves_typed_dates_and_rejects_public_files(tmp_path):
    from backend.wonder_personal_owner_policy import OwnerPersonalPolicy, OwnerRiskQuote
    observed = datetime.now(timezone.utc)
    p = OwnerPersonalPolicy(policy_id=str(UUID(int=100)), key_sha256="a"*64,
        account_snapshot_sha256="b"*64, waiver_source_sha256="c"*64,
        legacy_cutoff_attempt_id=str(UUID(int=90)),
        waived_attempts=[{"attempt_id": str(UUID(int=i+1)), "identity_sha256": "d"*64} for i in range(8)],
        account_observed_at=observed)
    q = OwnerRiskQuote(valid_until=observed+timedelta(hours=1), reference="test-only prices",
                       model_access_reference="test-only access")
    pp, qp = tmp_path / "policy.json", tmp_path / "quote.json"
    pp.write_text(p.model_dump_json()); qp.write_text(q.model_dump_json())
    pp.chmod(0o600); qp.chmod(0o600)
    actual_policy, actual_quote = module()._operator_descriptors(pp, qp)
    assert actual_policy.account_observed_at == observed
    assert actual_quote.valid_until == observed+timedelta(hours=1)
    pp.chmod(0o644)
    with pytest.raises(ValueError): module()._operator_descriptors(pp, qp)
