"""Local-camera / guarded-Wonder composition uses disposable state only."""
from pathlib import Path
import socket
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app

TOKEN = "combined-backend-test-owner-token-0001"


@pytest.mark.parametrize("flag", ["yes", "1", ""])
def test_invalid_coexistence_selector_fails_startup(tmp_path, monkeypatch, flag):
    monkeypatch.setenv("HYDRA_AI_MODE", "mock")
    monkeypatch.setenv("META_BILLABLE_REQUESTS_ENABLED", "false")
    monkeypatch.setenv("HYDRA_WONDER_LIVE", "false")
    monkeypatch.setenv("HYDRA_LOCAL_META_ALLOW_WONDER", flag)
    with pytest.raises(ValueError):
        create_app(tmp_path / "beverages.sqlite3", TOKEN)


def test_coexistence_selector_cannot_be_ignored_in_mock_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_AI_MODE", "mock")
    monkeypatch.setenv("META_BILLABLE_REQUESTS_ENABLED", "false")
    monkeypatch.setenv("HYDRA_WONDER_LIVE", "false")
    monkeypatch.setenv("HYDRA_LOCAL_META_ALLOW_WONDER", "true")
    with pytest.raises(ValueError):
        create_app(tmp_path / "beverages.sqlite3", TOKEN)


@pytest.mark.parametrize("mode,flag,wonder,hydration,billable", [
    ("local_meta", "false", "true", "false", "true"),
    ("local_meta", "true", "false", "false", "false"),
    ("local_meta", "true", "true", "true", "true"),
    ("local_meta", "true", "true", "false", "false"),
    ("guarded_meta", "true", "true", "false", "true"),
])
def test_incompatible_combinations_fail_before_opening_any_store(
        tmp_path, monkeypatch, mode, flag, wonder, hydration, billable):
    monkeypatch.setenv("HYDRA_AI_MODE", mode)
    monkeypatch.setenv("HYDRA_LOCAL_META_ALLOW_WONDER", flag)
    monkeypatch.setenv("HYDRA_WONDER_LIVE", wonder)
    monkeypatch.setenv("HYDRA_META_HYDRATION_ENABLED", hydration)
    monkeypatch.setenv("META_BILLABLE_REQUESTS_ENABLED", billable)
    path = tmp_path / "must-not-be-created.sqlite3"
    with pytest.raises(ValueError):
        create_app(path, TOKEN)
    assert not path.exists()


def combined_client(tmp_path, monkeypatch, *, blocked=False):
    from backend.local_meta import LocalMetaRecognizer
    from test_local_meta import prediction
    from test_wonder_personal_owner_policy import client_for

    def no_network(*args, **kwargs):
        raise AssertionError("Combined integration tests cannot access a network")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    policy_changes = None if blocked else {
        "waive_billing_wait": True,
        "billing_wait_waiver_reference": "synthetic-combined-ongoing-waiver",
        "cross_ledger_clear": False,
        "cross_ledger_reference": None,
        "cross_ledger_checked_at": None,
    }
    old, ledger, _, _, transport = client_for(
        tmp_path, monkeypatch, pending=True, policy_changes=policy_changes)

    class Runtime:
        def recognize(self, jpeg):
            return prediction(), "DASANI\nPURIFIED WATER\n1 LITER"

    monkeypatch.setattr(LocalMetaRecognizer, "from_environment", classmethod(lambda cls: cls(Runtime())))
    monkeypatch.setenv("HYDRA_AI_MODE", "local_meta")
    monkeypatch.setenv("HYDRA_LOCAL_META_ALLOW_WONDER", "true")
    monkeypatch.setenv("HYDRA_META_LEDGER_PATH", str(ledger.path))
    app = create_app(tmp_path / "beverages.sqlite3", "t" * 40)
    app.state.wonder_trends_gateway = old.app.state.wonder_trends_gateway
    return TestClient(app), ledger, transport


@pytest.mark.parametrize("version", ["v1", "v3"])
def test_camera_and_consented_wonder_share_routes_without_cross_dispatch(tmp_path, monkeypatch, version):
    from test_local_meta import photo, confirmation
    from test_wonder_workout import live_body

    client, ledger, transport = combined_client(tmp_path, monkeypatch)
    auth = {"Authorization": "Bearer " + "t" * 40}
    path = f"/{version}/wonder/analysis"
    body = live_body()
    before = Path(ledger.path).read_bytes()
    with client:
        for endpoint in [path + "/preview", path]:
            assert client.post(endpoint, json=body).status_code == 401
            assert client.post(endpoint, json=body, headers={"Authorization": "Bearer other-owner"}).status_code == 401
        assert client.post("/v1/recognitions", json=photo()).status_code == 401
        capabilities = client.get("/v1/recognition-capabilities", headers=auth).json()
        assert capabilities["mode"] == "local_meta"
        assert capabilities["dispatch_requires_account_permit_and_verified_bound"] is False
        result = client.post("/v1/recognitions", json=photo(), headers=auth)
        assert result.status_code == 200, result.text
        saved = client.post("/v1/beverages", json=confirmation(result.json()),
                            headers=auth | {"Idempotency-Key": str(uuid4())})
        assert saved.status_code == 201, saved.text
        assert saved.json()["consumed_ml"] == 1000
        assert Path(ledger.path).read_bytes() == before and transport.calls == 0
        view = client.post(path + "/preview", json=body, headers=auth)
        assert view.status_code == 200, view.text
        assert view.json()["live_available"] is True
        payload = body | {"payload_sha256": view.json()["payload_sha256"], "consent_to_send": True}
        assert client.post(path, json=payload | {"consent_to_send": False}, headers=auth).status_code == 422
        stale = client.post(path, json=payload | {"payload_sha256": "0" * 64}, headers=auth)
        assert stale.status_code == 409
        assert transport.calls == 0 and Path(ledger.path).read_bytes() == before
        explained = client.post(path, json=payload, headers=auth)
        assert explained.status_code == 200, explained.text
        assert explained.json()["saved"] is True and explained.json()["replayed"] is False
        assert len(explained.json()["result"]["sections"]) == 8
        after = Path(ledger.path).read_bytes()
        replay = client.post(path, json=payload, headers=auth)
        assert replay.json() == {"result": explained.json()["result"], "saved": True, "replayed": True}
        assert transport.calls == 1 and Path(ledger.path).read_bytes() == after


def test_blocked_wonder_does_not_disable_local_camera(tmp_path, monkeypatch):
    from test_local_meta import photo
    from test_wonder_workout import live_body

    client, ledger, transport = combined_client(tmp_path, monkeypatch, blocked=True)
    auth = {"Authorization": "Bearer " + "t" * 40}
    before = Path(ledger.path).read_bytes()
    with client:
        assert client.get("/v1/wonder/readiness", headers=auth).json()["status"] == "blocked"
        assert client.post("/v1/recognitions", json=photo(), headers=auth).status_code == 200
        body = live_body()
        view = client.post("/v1/wonder/analysis/preview", json=body, headers=auth).json()
        assert view["live_available"] is False
        refused = client.post("/v1/wonder/analysis", headers=auth, json=body | {
            "payload_sha256": view["payload_sha256"], "consent_to_send": True})
        assert refused.status_code == 409
        assert transport.calls == 0 and Path(ledger.path).read_bytes() == before


def test_combined_saved_replay_survives_comprehensive_dispatch_disabled(tmp_path, monkeypatch):
    from test_wonder_workout import live_body

    client, ledger, transport = combined_client(tmp_path, monkeypatch)
    auth = {"Authorization": "Bearer " + "t" * 40}
    body = live_body()
    with client:
        view = client.post("/v1/wonder/analysis/preview", json=body, headers=auth).json()
        payload = body | {"payload_sha256": view["payload_sha256"], "consent_to_send": True}
        response = client.post("/v1/wonder/analysis", json=payload, headers=auth)
        assert response.status_code == 200, response.text
        saved = response.json()["result"]
    monkeypatch.setenv("HYDRA_WONDER_ANALYSIS_ENABLED", "false")
    before = Path(ledger.path).read_bytes()
    with TestClient(create_app(tmp_path / "beverages.sqlite3", "t" * 40)) as restarted:
        view = restarted.post("/v1/wonder/analysis/preview", json=body, headers=auth).json()
        assert view["live_available"] is False and view["saved"] == saved
        replay = restarted.post("/v1/wonder/analysis", json=payload, headers=auth)
        assert replay.json() == {"result": saved, "saved": True, "replayed": True}
    assert transport.calls == 1 and Path(ledger.path).read_bytes() == before
