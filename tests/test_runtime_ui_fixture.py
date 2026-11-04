"""The developer fixture helper must never replace another saved history."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from uuid import UUID

import pytest


@pytest.fixture
def setup_helper(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "scripts/prepare_runtime_ui_fixture.py"
    spec = importlib.util.spec_from_file_location("runtime_ui_fixture_helper", source)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    profile = UUID(int=777)
    folder = tmp_path / "Library/Application Support/HydraAI/manual-calibration-v1"
    folder.mkdir(parents=True)
    target = folder / (str(profile).upper() + ".json")
    target.write_text(json.dumps({"version": 1, "profile": str(profile), "records": []}))
    target.chmod(0o600)
    monkeypatch.setattr(helper.subprocess, "check_output", lambda *_a, **_k: str(tmp_path))
    monkeypatch.setattr(helper.subprocess, "run", lambda *a, **_k: subprocess.CompletedProcess(a, 0))

    def invoke(expected=profile, *, omit=False):
        args = [str(source), "--simulator", "synthetic-simulator", "--confirm-synthetic-fixture"]
        if not omit:
            args += ["--expected-profile", str(expected)]
        monkeypatch.setattr(sys, "argv", args)
        return helper.main()

    return helper, target, profile, invoke


def test_fixture_requires_a_profile_pinned_by_synthetic_setup(setup_helper):
    _, target, _, invoke = setup_helper
    before = target.read_bytes()
    with pytest.raises(SystemExit):
        invoke(omit=True)
    assert target.read_bytes() == before


def test_wrong_pinned_profile_is_rejected_without_changing_history(setup_helper):
    _, target, _, invoke = setup_helper
    before = target.read_bytes()
    with pytest.raises(SystemExit):
        invoke(UUID(int=778))
    assert target.read_bytes() == before


def test_matching_empty_profile_gets_only_invented_records_without_consent(setup_helper):
    _, target, profile, invoke = setup_helper
    invoke()
    saved = json.loads(target.read_text())
    assert set(saved) == {"version", "profile", "records"}
    assert UUID(saved["profile"]) == profile and saved["version"] == 1
    assert len(saved["records"]) == 6
    assert {UUID(row["event_id"]) for row in saved["records"]} == {UUID(int=i) for i in range(1, 7)}
    assert all(row["measurement"]["provenance"] == ["user_entered_manual_weighing"] for row in saved["records"])
    assert target.stat().st_mode & 0o777 == 0o600


def test_nonempty_history_is_preserved_even_with_the_correct_pin(setup_helper):
    _, target, _, invoke = setup_helper
    saved = json.loads(target.read_text())
    saved["records"] = [{"existing_record": "preserve"}]
    target.write_text(json.dumps(saved))
    before = target.read_bytes()
    with pytest.raises(SystemExit):
        invoke()
    assert target.read_bytes() == before


def test_save_finishing_during_app_termination_is_not_overwritten(setup_helper, monkeypatch):
    helper, target, _, invoke = setup_helper

    def finish_save(*args, **kwargs):
        saved = json.loads(target.read_text())
        saved["records"] = [{"finishing_save": "preserve"}]
        target.write_text(json.dumps(saved))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(helper.subprocess, "run", finish_save)
    with pytest.raises(SystemExit):
        invoke()
    assert json.loads(target.read_text())["records"] == [{"finishing_save": "preserve"}]


def test_failed_app_termination_cannot_change_even_an_empty_history(setup_helper, monkeypatch):
    helper, target, _, invoke = setup_helper
    before = target.read_bytes()
    monkeypatch.setattr(helper.subprocess, "run", lambda *a, **_k: subprocess.CompletedProcess(a, 1))
    with pytest.raises(SystemExit):
        invoke()
    assert target.read_bytes() == before
