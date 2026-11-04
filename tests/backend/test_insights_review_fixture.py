"""The UI fixture exposes consent controls without ever delegating a trend send."""
from fastapi.testclient import TestClient
from scripts.insights_review_fixture import make_fixture


def test_fake_available_trends_cannot_reach_provider(tmp_path):
    token = "synthetic-ui-review-token-0000000000"
    fixture = make_fixture(tmp_path / "synthetic.sqlite3", token)
    # Reaching the real application on a POST is a fixture defect.
    real = fixture.app
    async def no_post(scope, receive, send):
        assert scope.get("method") != "POST"
        return await real(scope, receive, send)
    fixture.app = no_post
    with TestClient(fixture) as client:
        auth = {"Authorization": "Bearer " + token}
        assert client.get("/health").json()["billable_requests_enabled"] is False
        preview = client.get("/v1/wonder/trends?timezone=UTC", headers=auth).json()
        assert preview["live_available"] is True and preview["explainable"] is True
        assert preview["facts"]["last_7_days"]["total_ml"] == 500
        assert client.get("/__test__/trend-sends", headers=auth).json()["count"] == 0
        assert client.post("/v1/wonder/trends", json={}, headers=auth).status_code == 503
        assert client.get("/__test__/trend-sends", headers=auth).json()["count"] == 1
        assert client.post("/v1/wonder/trends", json={}).status_code == 401


def test_saved_example_uses_a_different_date_window(tmp_path):
    token = "synthetic-ui-review-token-0000000000"
    with TestClient(make_fixture(tmp_path / "synthetic.sqlite3", token, saved_example=True)) as client:
        value = client.get("/v1/wonder/trends?timezone=UTC", headers={"Authorization": "Bearer " + token}).json()
        assert value["latest"]["facts"]["through_date"] != value["facts"]["through_date"]
        assert value["latest"]["payload_sha256"] != value["payload_sha256"]
        assert len(value["latest"]["insights"]) == 3
        assert value["latest"]["facts"]["last_7_days"]["total_ml"] == 500
        assert value["saved"] is None
