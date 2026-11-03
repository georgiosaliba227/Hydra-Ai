"""Home score dispatch uses only fake transports and disposable ledgers."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import threading
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend import wonder_score
from backend.wonder_experiment import WonderHydrationGateway, WonderMetaTransport
from backend.wonder_hydration import input_bound
from test_guarded_meta import FakeNotifier, evidence
from test_wonder_experiment import attempt_rows, disabled_network, selection_reply
from test_wonder_trends import AMINE, AUTH, TOKEN, client_env, live_env

__all__ = ["disabled_network", "client_env"]
PREVIEW, EXPLAIN = "/v1/wonder/score/preview", "/v1/wonder/score"
BODY = {"timezone": "UTC", "measurement_count": 2, "processing_consent": True}


class ScoreTransport:
    def __init__(self, *, fault=None, invalid=False):
        self.credential_fingerprint = evidence(AMINE).key_sha256
        self.calls, self.fault, self.invalid = 0, fault, invalid
        self.entered = self.release = None

    def input_bound(self, payload):
        WonderMetaTransport.validate_payload(self, payload)
        return input_bound(payload)

    def generate(self, payload, ticket):
        ticket.claim(payload, input_bound=self.input_bound(payload), credential_fingerprint=self.credential_fingerprint)
        self.calls += 1
        if self.entered is not None:
            self.entered.set()
            assert self.release.wait(5)
        if self.fault:
            raise self.fault
        facts = wonder_score.facts_from_payload(payload)
        choices = wonder_score.allowed_texts(facts)
        value = {"insights": [{"id": name, "text": choices[name][0]} for name in wonder_score.REQUIRED_IDS]}
        if self.invalid:
            value["insights"][0]["text"] = "Drink more water."
        return selection_reply(text=json.dumps(value))


def setup_client(tmp_path, env, *, enabled=True, transport=None):
    authority, ledger = live_env(env, tmp_path)
    env.setenv("HYDRA_WONDER_ANALYSIS_ENABLED", "true" if enabled else "false")
    app = create_app(tmp_path / "beverages.sqlite3", TOKEN)
    transport = transport or ScoreTransport()
    app.state.wonder_trends_gateway = lambda: WonderHydrationGateway(ledger, transport, FakeNotifier())
    client = TestClient(app)
    return client, authority, transport


def set_goal(client, value=2000):
    assert client.put("/v1/settings", json={"daily_beverage_goal_ml": value}, headers=AUTH).status_code == 200


def consent(view, body=BODY):
    return body | {"payload_sha256": view["payload_sha256"], "consent_to_send": True}


def test_default_off_preview_and_processing_consent_never_reserve(tmp_path, client_env):
    client, authority, transport = setup_client(tmp_path, client_env, enabled=False)
    with client:
        set_goal(client)
        view = client.post(PREVIEW, json=BODY, headers=AUTH).json()
        assert view["live_available"] is False
        assert view["facts"]["score"] == 7  # Valid empty drink log; manual count2.
        assert client.post(EXPLAIN, json=consent(view), headers=AUTH).status_code == 503
        assert transport.calls == 0 and attempt_rows(authority) == []


@pytest.mark.parametrize("field,value", [("measurement_count", True), ("measurement_count", 2.0),
    ("measurement_count", 33), ("processing_consent", 1), ("processing_consent", False), ("timezone", "Bad/Zone")])
def test_strict_score_request_rejects_invalid_types_before_dispatch(tmp_path, client_env, field, value):
    with TestClient(create_app(tmp_path / "data.sqlite3", TOKEN)) as client:
        set_goal(client)
        assert client.post(PREVIEW, json=BODY | {field: value}, headers=AUTH).status_code == 422


def test_missing_goal_requires_setup_and_unknown_or_synthetic_fields_are_rejected(tmp_path, client_env):
    with TestClient(create_app(tmp_path / "data.sqlite3", TOKEN)) as client:
        response = client.post(PREVIEW, json=BODY, headers=AUTH)
        assert response.status_code == 422 and response.json()["code"] == "goal_required"
        for field in ("mode", "healthkit", "calibration_history", "facts"):
            assert client.post(PREVIEW, json=BODY | {field: "synthetic_demo"}, headers=AUTH).status_code == 422


def test_settled_score_saved_replayed_exported_deleted_without_spending_reset(tmp_path, client_env):
    client, authority, transport = setup_client(tmp_path, client_env)
    with client:
        set_goal(client)
        view = client.post(PREVIEW, json=BODY, headers=AUTH).json()
        assert view["live_available"] is True
        response = client.post(EXPLAIN, json=consent(view), headers=AUTH)
        assert response.status_code == 200, response.text
        envelope = response.json()
        assert envelope["saved"] is True and envelope["replayed"] is False
        result = envelope["result"]
        assert result["provenance"]["text_origin"] == "hydra_reviewed_selected_by_muse"
        assert client.post(EXPLAIN, json=consent(view), headers=AUTH).json() == {
            "replayed": True, "saved": True, "result": result}
        assert client.post(PREVIEW, json=BODY, headers=AUTH).json()["saved"] == result
        assert client.get("/v1/export", headers=AUTH).json()["wonder_score_explanations"] == [result]
        deleted = client.delete("/v1/data?confirm=delete-all-my-data", headers=AUTH).json()
        assert deleted["deleted_score_explanations"] == 1
        assert client.get("/v1/export", headers=AUTH).json()["wonder_score_explanations"] == []
        assert transport.calls == 1 and len(attempt_rows(authority)) == 1


def test_changed_goal_manual_count_or_logs_reject_exact_stale_hash_without_admission(tmp_path, client_env):
    client, authority, transport = setup_client(tmp_path, client_env)
    with client:
        set_goal(client)
        view = client.post(PREVIEW, json=BODY, headers=AUTH).json()
        changed = BODY | {"measurement_count": 3}
        assert client.post(EXPLAIN, json=consent(view, changed), headers=AUTH).json()["code"] == "score_preview_stale"
        set_goal(client, 1800)
        assert client.post(EXPLAIN, json=consent(view), headers=AUTH).status_code == 409
        view = client.post(PREVIEW, json=BODY, headers=AUTH).json()
        response = client.post("/v1/beverages", json={"category": "water", "consumed_ml": 200,
            "consumed_at": datetime.now(timezone.utc).isoformat(), "timezone": "UTC", "source": "manual"},
            headers=AUTH | {"Idempotency-Key": str(uuid4())})
        assert response.status_code == 201
        assert client.post(EXPLAIN, json=consent(view), headers=AUTH).status_code == 409
        assert transport.calls == 0 and attempt_rows(authority) == []


@pytest.mark.parametrize("value", [1, False, "true", None])
def test_meta_consent_must_be_fresh_explicit_boolean(tmp_path, client_env, value):
    client, authority, transport = setup_client(tmp_path, client_env)
    with client:
        set_goal(client)
        view = client.post(PREVIEW, json=BODY, headers=AUTH).json()
        assert client.post(EXPLAIN, json=consent(view) | {"consent_to_send": value}, headers=AUTH).status_code == 422
        assert transport.calls == 0 and attempt_rows(authority) == []


def test_unknown_provider_outcome_is_not_retried_and_blocks_new_score(tmp_path, client_env):
    client, authority, transport = setup_client(tmp_path, client_env, transport=ScoreTransport(fault=OSError("fake offline")))
    with client:
        set_goal(client)
        view = client.post(PREVIEW, json=BODY, headers=AUTH).json()
        response = client.post(EXPLAIN, json=consent(view), headers=AUTH)
        assert response.status_code == 502 and response.json()["attempt_id"]
        changed = BODY | {"measurement_count": 3}
        other = client.post(PREVIEW, json=changed, headers=AUTH).json()
        assert client.post(EXPLAIN, json=consent(other, changed), headers=AUTH).status_code == 409
        assert transport.calls == 1 and len(attempt_rows(authority)) == 1


def test_score_dispatch_holds_shared_lock_through_publication_and_blocks_deletion(tmp_path, client_env):
    transport = ScoreTransport()
    transport.entered, transport.release = threading.Event(), threading.Event()
    client, authority, _ = setup_client(tmp_path, client_env, transport=transport)
    with client, ThreadPoolExecutor(max_workers=2) as pool:
        set_goal(client)
        view = client.post(PREVIEW, json=BODY, headers=AUTH).json()
        running = pool.submit(client.post, EXPLAIN, json=consent(view), headers=AUTH)
        try:
            assert transport.entered.wait(3)
            assert client.post(EXPLAIN, json=consent(view), headers=AUTH).json()["code"] == "wonder_busy"
            assert client.delete("/v1/data?confirm=delete-all-my-data", headers=AUTH).json()["code"] == "wonder_busy"
        finally:
            transport.release.set()
        assert running.result(timeout=5).json()["saved"] is True
        assert len(attempt_rows(authority)) == transport.calls == 1


def test_untrusted_provider_prose_is_rejected_and_never_saved_or_retried(tmp_path, client_env):
    client, authority, transport = setup_client(tmp_path, client_env, transport=ScoreTransport(invalid=True))
    with client:
        set_goal(client)
        view = client.post(PREVIEW, json=BODY, headers=AUTH).json()
        assert client.post(EXPLAIN, json=consent(view), headers=AUTH).status_code == 502
        assert client.post(PREVIEW, json=BODY, headers=AUTH).json()["saved"] is None
        assert client.post(EXPLAIN, json=consent(view), headers=AUTH).status_code == 409
        assert transport.calls == 1 and len(attempt_rows(authority)) == 1


def test_publication_keeps_shared_lock_until_immutable_file_is_linked(tmp_path, client_env, monkeypatch):
    from backend import wonder_results
    entered, release = threading.Event(), threading.Event()
    original_link = wonder_results.os.link

    def paused_link(source, target, **kwargs):
        if str(target).split("/")[-1].startswith("score-"):
            entered.set()
            assert release.wait(5)
        return original_link(source, target, **kwargs)

    monkeypatch.setattr(wonder_results.os, "link", paused_link)
    client, authority, transport = setup_client(tmp_path, client_env)
    with client, ThreadPoolExecutor(max_workers=2) as pool:
        set_goal(client)
        view = client.post(PREVIEW, json=BODY, headers=AUTH).json()
        running = pool.submit(client.post, EXPLAIN, json=consent(view), headers=AUTH)
        try:
            assert entered.wait(3)
            denied = client.delete("/v1/data?confirm=delete-all-my-data", headers=AUTH)
            assert denied.status_code == 409 and denied.json()["code"] == "wonder_busy"
            assert len(list((tmp_path / "results").glob(".pending-*"))) == 1
        finally:
            release.set()
        assert running.result(timeout=5).json()["saved"] is True
        assert len(list((tmp_path / "results").glob("score-*.json"))) == 1
        assert len(attempt_rows(authority)) == transport.calls == 1
