"""Public app integration of an authenticated, nonbillable availability check."""
from fastapi.testclient import TestClient

from backend.app import create_app


def test_readiness_default_is_disabled_and_requires_owner_auth(tmp_path, monkeypatch):
    for key, value in {
        "HYDRA_AI_MODE": "mock", "META_BILLABLE_REQUESTS_ENABLED": "false",
        "HYDRA_META_HYDRATION_ENABLED": "false", "HYDRA_WONDER_LIVE": "false",
        "HYDRA_WONDER_ANALYSIS_ENABLED": "false",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("HYDRA_WONDER_FINANCIAL_POLICY", raising=False)
    token = "readiness-integration-credential-000000000"
    with TestClient(create_app(tmp_path / "beverages.sqlite3", token)) as client:
        path = "/v1/wonder/readiness"
        assert path in client.get("/openapi.json").json()["paths"]
        assert client.get(path).status_code == 401
        response = client.get(path, headers={"Authorization": "Bearer " + token})
        assert response.status_code == 200
        assert response.json() == {
            "version": "wonder-readiness-v1", "configured": False,
            "status": "disabled", "account_id": None, "policy": None,
            "blocked_reasons": ["live_disabled"],
            "all_charge_categories_verified": None,
            "per_request_token_cap_micro_usd": 250000,
        }
        assert client.get("/health").json()["billable_requests_enabled"] is False
