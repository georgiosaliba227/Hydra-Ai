"""Recorded Wonder result validation and replay; synthetic fixtures, no network or ledger."""
from copy import deepcopy
import json
import os
import socket
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.hydration_context_v2 import build_scenario, comparison_result, supported_selection
from backend.wonder_results import load_recorded, save_result, validate_recorded

AUTH = {"Authorization": "Bearer wonder-results-local-test-token-000000000"}


@pytest.fixture(autouse=True)
def disabled_network(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("network forbidden"))


def recorded(scenario="complete"):
    context, prediction = build_scenario(scenario)
    provenance = {"mode": "meta_live", "provider": "Meta", "model": "muse-wonder-1.0", "candidate_model": "muse-wonder-1.0",
                  "candidate_tier": "Standard", "model_identity_verified": True, "live_dispatch_enabled": True,
                  "interpretation_origin": "meta_selection_and_reviewed_text", "account_id": "georgiosaliba227",
                  "attempt_id": str(uuid4())}
    observations = {"latency_ms": 812, "input_tokens": 900, "output_tokens": 120,
                    "usage_derived_cost_micro_usd": 6000, "billed_cost_usd": None}
    return comparison_result(scenario, prediction, supported_selection(context, prediction), provenance, observations)


@pytest.fixture
def results_dir(tmp_path):
    directory = tmp_path / "results"
    directory.mkdir(mode=0o700)
    return directory


def test_valid_record_round_trips_and_is_write_once(results_dir):
    result = recorded()
    path = save_result(results_dir, result)
    assert path.stat().st_mode & 0o777 == 0o600
    assert load_recorded(results_dir, "complete") == result
    with pytest.raises(FileExistsError):
        save_result(results_dir, recorded())
    assert load_recorded(results_dir, "missing_measurements") is None


@pytest.mark.parametrize("tamper", [
    lambda r: r["systems"]["A"]["prediction"].update(value_ml=9999.0),
    lambda r: r["systems"]["C"]["prediction"].update(value_ml=9999.0),
    lambda r: r["systems"]["B"]["interpretation"].update(factors=["heart_rate_context"]),
    lambda r: r["systems"]["B"]["interpretation"]["reviewed_text"]["factors"].append("Drink 3 litres."),
    lambda r: r["provenance"].update(model="muse-spark-1.3"),
    lambda r: r["provenance"].update(mode="mock"),
    lambda r: r["provenance"].update(account_id="aminealichaouche"),
    lambda r: r["provenance"].update(attempt_id="not-a-uuid"),
    lambda r: r["provider_observations"].update(billed_cost_usd=0.01),
    lambda r: r["provider_observations"].update(input_tokens=-1),
    lambda r: r.update(scenario="user_supplied"),
    lambda r: r.update(extra="field"),
])
def test_tampered_records_are_rejected(results_dir, tamper):
    result = deepcopy(recorded())
    tamper(result)
    with pytest.raises(ValueError):
        validate_recorded(result)
    (results_dir / "complete.json").write_text(json.dumps(result))
    os.chmod(results_dir / "complete.json", 0o600)
    with pytest.raises(ValueError):
        load_recorded(results_dir, "complete")


def test_shared_or_relative_directories_are_refused(tmp_path, results_dir):
    os.chmod(results_dir, 0o755)
    with pytest.raises(ValueError):
        save_result(results_dir, recorded())
    with pytest.raises(ValueError):
        load_recorded(results_dir.relative_to(tmp_path), "complete")


def client(tmp_path, monkeypatch, results=None):
    monkeypatch.setenv("HYDRA_AI_MODE", "mock")
    monkeypatch.setenv("META_BILLABLE_REQUESTS_ENABLED", "false")
    monkeypatch.setenv("HYDRA_META_HYDRATION_ENABLED", "false")
    if results is None:
        monkeypatch.delenv("HYDRA_WONDER_RESULTS_DIR", raising=False)
    else:
        monkeypatch.setenv("HYDRA_WONDER_RESULTS_DIR", str(results))
    return TestClient(create_app(db_path=tmp_path / "local.sqlite3", api_token=AUTH["Authorization"][7:]))


def test_recorded_mode_replays_only_validated_results(tmp_path, monkeypatch, results_dir):
    body = {"mode": "recorded", "scenario": "complete"}
    with client(tmp_path, monkeypatch) as unconfigured:
        assert unconfigured.post("/v2/hydration-context-comparison", json=body, headers=AUTH).status_code == 404
    with client(tmp_path, monkeypatch, results_dir) as api:
        assert api.post("/v2/hydration-context-comparison", json=body).status_code == 401
        assert api.post("/v2/hydration-context-comparison", json=body, headers=AUTH).status_code == 404
        result = recorded()
        save_result(results_dir, result)
        response = api.post("/v2/hydration-context-comparison", json=body, headers=AUTH)
        assert response.status_code == 200 and response.json() == result
        assert response.headers["cache-control"] == "no-store"
        (results_dir / "complete.json").write_text(json.dumps(result | {"scenario": "complete", "extra": 1}))
        assert api.post("/v2/hydration-context-comparison", json=body, headers=AUTH).status_code == 404
        mock = api.post("/v2/hydration-context-comparison", json={"mode": "mock", "scenario": "complete"}, headers=AUTH)
        assert mock.json()["provenance"]["mode"] == "mock"
        assert api.post("/v2/hydration-context-comparison", json={"mode": "meta_live", "scenario": "complete"},
                        headers=AUTH).status_code == 422


def test_relative_results_directory_is_a_configuration_error(tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        client(tmp_path, monkeypatch, "relative/results")
