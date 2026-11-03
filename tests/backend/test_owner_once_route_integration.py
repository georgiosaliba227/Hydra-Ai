"""The recorded synthetic viewer never enables a paid route."""
from fastapi.testclient import TestClient

from backend.app import create_app


def test_owner_once_replay_is_registered_without_live_configuration(tmp_path, monkeypatch):
    for key, value in {
        "HYDRA_AI_MODE": "mock",
        "META_BILLABLE_REQUESTS_ENABLED": "false",
        "HYDRA_META_HYDRATION_ENABLED": "false",
        "HYDRA_WONDER_LIVE": "false",
        "HYDRA_WONDER_ANALYSIS_ENABLED": "false",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("HYDRA_WONDER_OWNER_ONCE_RESULT", raising=False)
    token = "owner-once-route-test-credential-00000000"
    with TestClient(create_app(tmp_path / "beverages.sqlite3", token)) as client:
        path = "/v1/wonder/owner-once/result"
        assert path in client.get("/openapi.json").json()["paths"]
        assert client.get(path).status_code == 401
        response = client.get(path, headers={"Authorization": "Bearer " + token})
        assert response.status_code == 404
        assert client.get("/health").json()["billable_requests_enabled"] is False
