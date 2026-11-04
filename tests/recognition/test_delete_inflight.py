"""Delete-all cannot complete while an explanation can still persist personal data."""
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from test_wonder_trends import (
    AUTH, TOKEN, amine_transport, client_env, consent, disabled_network,
    explanation, fake_live, live_env, seed, trend_reply,
)
from test_wonder_workout import consent as workout_consent, live_body, reply

__all__ = ["client_env", "disabled_network"]


@pytest.mark.parametrize("feature", ["trends", "workout"])
@pytest.mark.parametrize("stage", ["provider", "persistence"])
def test_delete_all_waits_for_explanation_to_finish(tmp_path, client_env, monkeypatch, feature, stage):
    _, ledger = live_env(client_env, tmp_path)
    app = create_app(tmp_path / "data.sqlite3", TOKEN)
    entered, release = threading.Event(), threading.Event()
    with TestClient(app) as client:
        seed(client)
        if feature == "trends":
            view = client.get("/v1/wonder/trends", params={"timezone": "UTC"}, headers=AUTH).json()
            body = consent(view)
            transport = amine_transport(trend_reply(view["facts"], explanation()))
        else:
            request = live_body()
            view = client.post("/v1/wonder/workout/preview", json=request, headers=AUTH).json()
            body = workout_consent(view, request)
            transport = amine_transport(reply())
        fake_live(app, ledger, transport)
        if stage == "provider":
            original = transport.generate
            target, name = transport, "generate"
        else:
            from backend import wonder_trend_routes, wonder_workout_routes
            target = wonder_trend_routes if feature == "trends" else wonder_workout_routes
            name = "save_result"
            original = target.save_result

        def paused(*args, **kwargs):
            entered.set()
            assert release.wait(timeout=10), "Explanation test was not released"
            return original(*args, **kwargs)

        monkeypatch.setattr(target, name, paused)
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(client.post, f"/v1/wonder/{feature}", json=body, headers=AUTH)
            try:
                assert entered.wait(timeout=10), "Explanation did not reach the intended boundary"
                deleting = client.delete("/v1/data", params={"confirm": "delete-all-my-data"}, headers=AUTH)
            finally:
                release.set()
            response = pending.result(timeout=10)
        assert deleting.status_code == 409, "Deletion must not claim success before a later personal-data write"
        assert deleting.json()["code"] == "wonder_busy"
        assert len(client.get("/v1/export", headers=AUTH).json()["beverages"]) == 10
        assert response.status_code == 200 and response.json()["saved"] is True
        assert client.delete("/v1/data", params={"confirm": "delete-all-my-data"}, headers=AUTH).status_code == 200
        exported = client.get("/v1/export", headers=AUTH).json()
        assert exported["beverages"] == []
        assert exported["wonder_trends"] == []
        assert exported["wonder_workout_explanations"] == []
