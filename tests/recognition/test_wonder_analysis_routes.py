"""Comprehensive Wonder uses existing disposable financial gates; never network."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend import wonder_analysis
from backend.recognition import RecognitionUnavailable
from backend.wonder_experiment import WonderHydrationGateway, WonderMetaTransport
from backend.wonder_hydration import input_bound
from test_guarded_meta import FakeNotifier, evidence
from test_wonder_experiment import attempt_rows, disabled_network, selection_reply
from test_wonder_trends import AMINE, AUTH, TOKEN, amine_quote, amine_setup, client_env, live_env
from test_wonder_workout import live_body

__all__ = ["disabled_network", "client_env"]
PREVIEW, EXPLAIN = "/v1/wonder/analysis/preview", "/v1/wonder/analysis"


@pytest.fixture(autouse=True)
def comprehensive_disabled_by_default(client_env):
    client_env.delenv("HYDRA_WONDER_ANALYSIS_ENABLED", raising=False)


class AnalysisTransport:
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
        facts = wonder_analysis.facts_from_payload(payload)
        selection = {"sections": {key: choices[:3] for key, choices in wonder_analysis.applicable_insights(facts).items()}}
        if self.invalid:
            selection["sections"]["summary"] = ["Drink two litres."]
        return selection_reply(text=json.dumps(selection))


def setup_client(tmp_path, env, *, enabled=True, transport=None):
    authority, ledger = live_env(env, tmp_path)
    if enabled:
        env.setenv("HYDRA_WONDER_ANALYSIS_ENABLED", "true")
    app = create_app(tmp_path / "beverages.sqlite3", TOKEN)
    transport = transport or AnalysisTransport()
    app.state.wonder_trends_gateway = lambda: WonderHydrationGateway(ledger, transport, FakeNotifier())
    return TestClient(app), authority, ledger, transport


def consent(body, view):
    return body | {"payload_sha256": view["payload_sha256"], "consent_to_send": True}


def test_rich_preview_is_nonbillable_and_disabled_even_with_existing_live_configuration(tmp_path, client_env):
    client, authority, _, transport = setup_client(tmp_path, client_env, enabled=False)
    with client:
        body = live_body()
        response = client.post(PREVIEW, json=body, headers=AUTH)
        assert response.status_code == 200, response.text
        view = response.json()
        assert view["live_available"] is view["dispatch_supported"] is False
        assert view["saved"] is None
        denied = client.post(EXPLAIN, json=consent(body, view), headers=AUTH)
        assert denied.status_code == 503
        assert transport.calls == 0 and attempt_rows(authority) == []


def test_rich_once_settled_saved_replayed_exported_and_deleted(tmp_path, client_env):
    client, authority, _, transport = setup_client(tmp_path, client_env)
    with client:
        body = live_body()
        view = client.post(PREVIEW, json=body, headers=AUTH).json()
        assert view["live_available"] is True
        first = client.post(EXPLAIN, json=consent(body, view), headers=AUTH)
        assert first.status_code == 200, first.text
        envelope = first.json()
        result = envelope["result"]
        assert result["version"] == "wonder-analysis-v2" and len(result["sections"]) == 8
        assert result["provenance"]["selection_origin"] == "muse_wonder_selected_scaffolds"
        assert result["provenance"]["text_origin"] == "hydra_vetted_scaffolds_and_facts"
        assert envelope["saved"] is True and envelope["replayed"] is False
        second = client.post(EXPLAIN, json=consent(body, view), headers=AUTH).json()
        assert second == {"saved": True, "replayed": True, "result": result}
        assert transport.calls == 1
        assert len(attempt_rows(authority)) == 1 and attempt_rows(authority)[0][1] == "settled"
        assert client.post(PREVIEW, json=body, headers=AUTH).json()["saved"] == result
        assert client.get("/v1/export", headers=AUTH).json()["wonder_analysis_explanations"] == [result]
        deleted = client.delete("/v1/data?confirm=delete-all-my-data", headers=AUTH).json()
        assert deleted["deleted_analysis_explanations"] == 1
        assert client.get("/v1/export", headers=AUTH).json()["wonder_analysis_explanations"] == []
        assert len(attempt_rows(authority)) == 1  # Personal deletion never resets spending.


def test_changed_included_logs_reject_stale_consent_before_reserving(tmp_path, client_env):
    client, authority, _, transport = setup_client(tmp_path, client_env)
    with client:
        body = live_body()
        view = client.post(PREVIEW, json=body, headers=AUTH).json()
        added = client.post("/v1/beverages", headers=AUTH | {"Idempotency-Key": str(uuid4())}, json={
            "category": "water", "consumed_ml": 200, "consumed_at": datetime.now(timezone.utc).isoformat(),
            "timezone": "UTC", "source": "manual"})
        assert added.status_code == 201
        response = client.post(EXPLAIN, json=consent(body, view), headers=AUTH)
        assert response.status_code == 409 and response.json()["code"] == "analysis_preview_stale"
        assert transport.calls == 0 and attempt_rows(authority) == []


def test_unresolved_attempt_blocks_another_payload_without_retry(tmp_path, client_env):
    transport = AnalysisTransport(fault=OSError("network uncertainty fixture"))
    client, authority, _, _ = setup_client(tmp_path, client_env, transport=transport)
    with client:
        body = live_body()
        view = client.post(PREVIEW, json=body, headers=AUTH).json()
        response = client.post(EXPLAIN, json=consent(body, view), headers=AUTH)
        assert response.status_code == 502 and response.json()["attempt_id"]
        other = deepcopy(body)
        other["exercise"]["duration_minutes"] += 10
        view = client.post(PREVIEW, json=other, headers=AUTH).json()
        assert client.post(EXPLAIN, json=consent(other, view), headers=AUTH).status_code == 409
        assert transport.calls == 1 and len(attempt_rows(authority)) == 1


def test_wrong_key_identity_blocks_before_reservation(tmp_path, client_env):
    transport = AnalysisTransport()
    transport.credential_fingerprint = "e" * 64
    client, authority, _, _ = setup_client(tmp_path, client_env, transport=transport)
    with client:
        body = live_body()
        view = client.post(PREVIEW, json=body, headers=AUTH).json()
        response = client.post(EXPLAIN, json=consent(body, view), headers=AUTH)
        assert response.status_code == 409 and response.json()["code"] == "wonder_blocked"
        assert transport.calls == 0 and attempt_rows(authority) == []


def test_shared_lock_blocks_concurrent_old_or_rich_wonder_requests(tmp_path, client_env):
    transport = AnalysisTransport()
    transport.entered, transport.release = threading.Event(), threading.Event()
    client, authority, _, _ = setup_client(tmp_path, client_env, transport=transport)
    with client, ThreadPoolExecutor(max_workers=2) as pool:
        body = live_body()
        view = client.post(PREVIEW, json=body, headers=AUTH).json()
        running = pool.submit(client.post, EXPLAIN, json=consent(body, view), headers=AUTH)
        try:
            assert transport.entered.wait(3)
            second = client.post(EXPLAIN, json=consent(body, view), headers=AUTH)
            assert second.status_code == 409 and second.json()["code"] == "wonder_busy"
            old_view = client.post("/v1/wonder/workout/preview", json=body, headers=AUTH).json()
            old_response = client.post("/v1/wonder/workout", json=consent(body, old_view), headers=AUTH)
            assert old_response.status_code == 409 and old_response.json()["code"] == "wonder_busy"
        finally:
            transport.release.set()
        assert running.result(timeout=5).status_code == 200
        assert transport.calls == 1 and len(attempt_rows(authority)) == 1


def test_rejected_provider_text_is_not_saved_or_retried(tmp_path, client_env):
    client, authority, _, transport = setup_client(tmp_path, client_env, transport=AnalysisTransport(invalid=True))
    with client:
        body = live_body()
        view = client.post(PREVIEW, json=body, headers=AUTH).json()
        assert client.post(EXPLAIN, json=consent(body, view), headers=AUTH).status_code == 502
        assert client.post(PREVIEW, json=body, headers=AUTH).json()["saved"] is None
        assert client.post(EXPLAIN, json=consent(body, view), headers=AUTH).status_code == 409
        assert transport.calls == 1 and len(attempt_rows(authority)) == 1


def test_tampered_saved_record_is_not_displayed_or_billed_again(tmp_path, client_env):
    client, _, _, transport = setup_client(tmp_path, client_env)
    with client:
        body = live_body()
        view = client.post(PREVIEW, json=body, headers=AUTH).json()
        assert client.post(EXPLAIN, json=consent(body, view), headers=AUTH).status_code == 200
        path = next((tmp_path / "results").glob("analysis-*.json"))
        record = json.loads(path.read_text())
        record["sections"][0]["text"] = "Drink 5000 mL."
        path.write_text(json.dumps(record))
        assert client.post(PREVIEW, json=body, headers=AUTH).json()["saved"] is None
        assert client.post(EXPLAIN, json=consent(body, view), headers=AUTH).status_code == 409
        assert transport.calls == 1


def test_cold_empty_input_synthetic_and_over_cap_never_dispatch(tmp_path, client_env, monkeypatch):
    client, authority, _, transport = setup_client(tmp_path, client_env)
    with client:
        cold = {"timezone": "UTC"}
        view = client.post(PREVIEW, json=cold, headers=AUTH).json()
        assert view["live_available"] is False
        assert client.post(EXPLAIN, json=consent(cold, view), headers=AUTH).status_code == 422
        demo = {"timezone": "UTC", "mode": "synthetic_demo"}
        view = client.post(PREVIEW, json=demo, headers=AUTH).json()
        assert view["live_available"] is False
        assert client.post(EXPLAIN, json=consent(demo, view), headers=AUTH).status_code == 422
        monkeypatch.setattr(wonder_analysis, "worst_case_micro_usd", lambda *_args: 250001)
        body = live_body()
        view = client.post(PREVIEW, json=body, headers=AUTH).json()
        assert view["explainable"] is False
        assert client.post(EXPLAIN, json=consent(body, view), headers=AUTH).status_code == 422
        assert transport.calls == 0 and attempt_rows(authority) == []


@pytest.mark.parametrize("flag", ["yes", "1", "maybe"])
def test_invalid_comprehensive_flag_fails_closed(tmp_path, client_env, flag):
    client_env.setenv("HYDRA_WONDER_ANALYSIS_ENABLED", flag)
    with pytest.raises(ValueError):
        create_app(tmp_path / "data.sqlite3", TOKEN)


@pytest.mark.parametrize("value", [False, 1, "true", None])
def test_explicit_boolean_consent_required(tmp_path, client_env, value):
    with TestClient(create_app(tmp_path / "data.sqlite3", TOKEN)) as client:
        body = live_body()
        view = client.post(PREVIEW, json=body, headers=AUTH).json()
        request = consent(body, view) | {"consent_to_send": value}
        assert client.post(EXPLAIN, json=request, headers=AUTH).status_code == 422


@pytest.mark.parametrize("name", ["synthetic_demo", "personal_cold_start"])
def test_gateway_never_reclassifies_synthetic_or_empty_preview_as_personal_standing_consent(tmp_path, name):
    authority, ledger = amine_setup(tmp_path)
    transport = AnalysisTransport()
    fixture = Path(__file__).parents[1] / "fixtures" / "hydration_analysis" / f"{name}.json"
    facts = wonder_analysis.build_facts(json.loads(fixture.read_text()))
    gateway = WonderHydrationGateway(ledger, transport, FakeNotifier())
    with pytest.raises(RecognitionUnavailable):
        gateway.explain_analysis(facts, amine_quote(), "synthetic_must_not_use_owner_aggregate_case")
    assert transport.calls == 0 and attempt_rows(authority) == []


def test_saved_result_replays_with_new_dispatch_flag_disabled(tmp_path, client_env):
    client, _, _, transport = setup_client(tmp_path, client_env)
    body = live_body()
    with client:
        view = client.post(PREVIEW, json=body, headers=AUTH).json()
        saved = client.post(EXPLAIN, json=consent(body, view), headers=AUTH).json()["result"]
    client_env.setenv("HYDRA_WONDER_ANALYSIS_ENABLED", "false")
    with TestClient(create_app(tmp_path / "beverages.sqlite3", TOKEN)) as offline:
        view = offline.post(PREVIEW, json=body, headers=AUTH).json()
        assert view["live_available"] is False and view["saved"] == saved
        assert offline.post(EXPLAIN, json=consent(body, view), headers=AUTH).json() == {
            "result": saved, "saved": True, "replayed": True}
    assert transport.calls == 1


def test_failed_atomic_publication_leaves_no_partial_and_delete_clears_only_pending_regular_files(tmp_path, client_env, monkeypatch):
    from backend import wonder_results
    client, authority, _, transport = setup_client(tmp_path, client_env)
    with client:
        body = live_body()
        view = client.post(PREVIEW, json=body, headers=AUTH).json()
        def fail_publish(*args, **kwargs):
            raise OSError("publication failed fixture")
        monkeypatch.setattr(wonder_results.os, "link", fail_publish)
        response = client.post(EXPLAIN, json=consent(body, view), headers=AUTH)
        assert response.status_code == 200 and response.json()["saved"] is False
        folder = tmp_path / "results"
        assert list(folder.iterdir()) == []
        orphan = folder / ".pending-owner-fixture"
        unrelated = folder / "owner-note.txt"
        outside = tmp_path / "outside.txt"
        outside.write_text("unrelated owner file")
        symlink = folder / ".pending-symlink-fixture"
        symlink.symlink_to(outside)
        orphan.write_text("aggregate interrupted before publication")
        unrelated.write_text("unrelated content")
        deleted = client.delete("/v1/data?confirm=delete-all-my-data", headers=AUTH)
        assert deleted.status_code == 200
        assert not orphan.exists()
        assert symlink.is_symlink() and outside.read_text() == "unrelated owner file"
        assert unrelated.read_text() == "unrelated content"
        assert transport.calls == 1 and len(attempt_rows(authority)) == 1


def test_synthetic_rich_preview_never_reads_saved_personal_results(tmp_path, client_env, monkeypatch):
    from backend import wonder_analysis_routes
    client, authority, _, transport = setup_client(tmp_path, client_env)
    def forbidden(*_args):
        raise RuntimeError("Personal data access forbidden in synthetic preview")
    monkeypatch.setattr(wonder_analysis_routes, "load_analysis", forbidden)
    monkeypatch.setattr(client.app.state.repository, "list_all", forbidden)
    with client:
        view = client.post(PREVIEW, json={"mode": "synthetic_demo", "timezone": "UTC"}, headers=AUTH)
        assert view.status_code == 200 and view.json()["saved"] is None
        assert transport.calls == 0 and attempt_rows(authority) == []


def test_client_preview_fixture_matches_frozen_clock_route_and_fake_record_is_valid(tmp_path, client_env, monkeypatch):
    from backend import wonder_analysis_routes
    from backend.wonder_results import validate_recorded_analysis
    fixed = datetime(2026, 11, 2, 15, tzinfo=timezone.utc)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)
    monkeypatch.setattr(wonder_analysis_routes, "datetime", Clock)
    fixtures = Path(__file__).parents[1] / "fixtures"
    body = json.loads((fixtures / "hydration_analysis/personal_calibrated.request.json").read_text())
    expected = json.loads((fixtures / "wonder_analysis/personal_calibrated.http_preview.json").read_text())
    with TestClient(create_app(tmp_path / "data.sqlite3", TOKEN)) as client:
        actual = client.post(PREVIEW, json=body, headers=AUTH)
        assert actual.status_code == 200 and actual.json() == expected
        assert actual.headers["cache-control"] == "no-store"
        assert client.post(PREVIEW, json=body).status_code == 401
        assert client.post(PREVIEW, content=" " * (128*1024+1), headers=AUTH).status_code == 413
    envelope = json.loads((fixtures / "wonder_analysis/personal_calibrated.http_result.fake_transport.json").read_text())
    assert validate_recorded_analysis(envelope["result"]) == envelope["result"]


@pytest.mark.parametrize("phase", ["provider", "publication"])
def test_confirmed_deletion_cannot_race_inflight_analysis_or_publication(tmp_path, client_env, monkeypatch, phase):
    from backend import wonder_analysis_routes
    transport = AnalysisTransport()
    entered, release = threading.Event(), threading.Event()
    if phase == "provider":
        transport.entered, transport.release = entered, release
    else:
        original = wonder_analysis_routes.save_result
        def blocked_publication(*args):
            entered.set()
            assert release.wait(5)
            return original(*args)
        monkeypatch.setattr(wonder_analysis_routes, "save_result", blocked_publication)
    client, authority, _, _ = setup_client(tmp_path, client_env, transport=transport)
    with client, ThreadPoolExecutor(max_workers=2) as pool:
        assert client.post("/v1/beverages", headers=AUTH | {"Idempotency-Key": str(uuid4())}, json={
            "category": "water", "consumed_ml": 200, "consumed_at": datetime.now(timezone.utc).isoformat(),
            "timezone": "UTC", "source": "manual"}).status_code == 201
        body = live_body()
        view = client.post(PREVIEW, json=body, headers=AUTH).json()
        running = pool.submit(client.post, EXPLAIN, json=consent(body, view), headers=AUTH)
        try:
            assert entered.wait(3), running.result(timeout=1).text
            deletion = client.delete("/v1/data?confirm=delete-all-my-data", headers=AUTH)
            assert deletion.status_code == 409 and deletion.json()["code"] == "wonder_busy"
            assert len(client.get("/v1/beverages", headers=AUTH).json()["items"]) == 1
        finally:
            release.set()
        assert running.result(timeout=5).status_code == 200
        deletion = client.delete("/v1/data?confirm=delete-all-my-data", headers=AUTH)
        assert deletion.status_code == 200
        assert deletion.json()["deleted_beverages"] == deletion.json()["deleted_analysis_explanations"] == 1
        assert client.get("/v1/export", headers=AUTH).json()["wonder_analysis_explanations"] == []
        assert len(attempt_rows(authority)) == 1


@pytest.mark.parametrize("feature", ["workout", "trends"])
def test_old_personal_wonder_publication_uses_same_deletion_lock(tmp_path, client_env, monkeypatch, feature):
    from backend import wonder_workout_routes, wonder_trend_routes
    from test_wonder_trends import amine_transport, seed, trend_reply
    from test_wonder_workout import reply as workout_reply
    client, authority, ledger, _ = setup_client(tmp_path, client_env, enabled=False)
    module = wonder_workout_routes if feature == "workout" else wonder_trend_routes
    original = module.save_result
    entered, release = threading.Event(), threading.Event()
    def publication(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)
    monkeypatch.setattr(module, "save_result", publication)
    with client, ThreadPoolExecutor(max_workers=2) as pool:
        if feature == "workout":
            body = live_body()
            view = client.post("/v1/wonder/workout/preview", json=body, headers=AUTH).json()
            request = consent(body, view)
            transport = amine_transport(workout_reply())
        else:
            seed(client, days=3)
            view = client.get("/v1/wonder/trends?timezone=UTC", headers=AUTH).json()
            request = {"timezone": "UTC", "payload_sha256": view["payload_sha256"], "consent_to_send": True}
            transport = amine_transport(trend_reply(view["facts"], {
                "summary": "A record of logged beverages.",
                "insights": [{"id": "timing", "text": "Your peak time was {peak_time}."}]}))
        client.app.state.wonder_trends_gateway = lambda: WonderHydrationGateway(ledger, transport, FakeNotifier())
        running = pool.submit(client.post, f"/v1/wonder/{feature}", json=request, headers=AUTH)
        try:
            assert entered.wait(3)
            response = client.delete("/v1/data?confirm=delete-all-my-data", headers=AUTH)
            assert response.status_code == 409 and response.json()["code"] == "wonder_busy"
        finally:
            release.set()
        assert running.result(timeout=5).status_code == 200
        response = client.delete("/v1/data?confirm=delete-all-my-data", headers=AUTH)
        assert response.status_code == 200
        field = "deleted_workout_explanations" if feature == "workout" else "deleted_trend_explanations"
        assert response.json()[field] == 1
        assert transport.calls == 1 and len(attempt_rows(authority)) == 1
