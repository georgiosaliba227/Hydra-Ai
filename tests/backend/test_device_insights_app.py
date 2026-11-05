"""Owner-token features-only factory; ambient live flags cannot construct storage or providers."""
from datetime import date, timedelta
import importlib
import logging
import socket
import sqlite3

from fastapi.testclient import TestClient
import pytest

from ai.assistant import ANSWERS, SUGGESTED
from backend import app as full_backend
from backend.meta_gateway import GitHubNotifier, GuardedMetaGateway
from backend.meta_provider import OfficialMetaTransport
from backend.meta_accounts import AccountLedger
from backend.recognition import MockMetaRecognizer
from backend.wonder_experiment import WonderExperimentLedger, WonderHydrationGateway, WonderMetaTransport
from database.repository import BeverageRepository

TOKEN = "synthetic-owner-features-only-token-0000000000"
AUTH = {"Authorization": "Bearer " + TOKEN}


def trends():
    return {"version": "device-insights-v1", "source": "on_device_summary", "consent_to_process": True,
            "timezone": "UTC", "through_date": "2026-10-28", "goal_ml": None,
            "days": [{"date": (date(2026, 10, 15) + timedelta(days=i)).isoformat(), "total_ml": 0, "drinks": 0} for i in range(14)],
            "categories": [], "time_of_day_ml": {key: 0 for key in ("morning_ml", "afternoon_ml", "evening_ml", "night_ml")}}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Features-only app touched storage, provider construction or network")

    for dependency in (BeverageRepository, AccountLedger, MockMetaRecognizer, OfficialMetaTransport,
                       GuardedMetaGateway, GitHubNotifier, WonderExperimentLedger, WonderHydrationGateway, WonderMetaTransport):
        monkeypatch.setattr(dependency, "__init__", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(full_backend, "create_app", forbidden)
    monkeypatch.chdir(tmp_path)
    # These synthetic ambient values must be ignored, not interpreted as activation or storage configuration.
    for key, value in {"HYDRA_AI_MODE": "guarded_meta", "META_BILLABLE_REQUESTS_ENABLED": "true",
                       "HYDRA_META_HYDRATION_ENABLED": "true", "HYDRA_WONDER_LIVE": "true",
                       "HYDRA_DATABASE_PATH": str(tmp_path / "owner-beverages.sqlite3"),
                       "HYDRA_META_LEDGER_PATH": str(tmp_path / "owner-financial.sqlite3"),
                       "HYDRA_WONDER_RESULTS_DIR": "private-relative-results-must-not-be-loaded",
                       "HYDRA_API_TOKEN": "different-ambient-owner-token-0000000000"}.items():
        monkeypatch.setenv(key, value)
    module = importlib.import_module("backend.device_insights_app")
    app = module.create_device_insights_app(api_token=TOKEN)
    with TestClient(app) as client:
        yield app, client, tmp_path


def test_factory_has_no_storage_or_provider_state_even_with_live_ambient_flags(setup):
    app, client, directory = setup
    assert app.state._state == {}
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["features_only"] is True
    assert health.json()["billable_requests_enabled"] is False
    assert health.json()["provider_dispatch"] is False
    assert health.json()["storage"] == "none"
    assert list(directory.iterdir()) == []


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/v1/device-insights/capabilities", None), ("POST", "/v1/device-insights/trends", trends()),
    ("POST", "/v1/device-insights/assistant", {}), ("GET", "/v1/assistant/questions", None),
    ("POST", "/v1/assistant", {"question_id": "coffee_counts"}),
    ("POST", "/v2/workout-forecasts", {"timezone": "UTC"}),
    ("POST", "/v2/hydration-context-comparison", {"mode": "mock", "scenario": "complete"}),
])
def test_all_feature_routes_accept_only_the_explicit_owner_token(setup, method, path, body):
    _, client, _ = setup
    for headers in ({}, {"Authorization": "Bearer different-ambient-owner-token-0000000000"}):
        assert client.request(method, path, json=body, headers=headers).status_code == 401


def test_capabilities_and_phone_context_work_without_any_repository(setup):
    _, client, directory = setup
    assert client.get("/v1/device-insights/capabilities", headers=AUTH).json() == {
        "version": "device-insights-v1", "history_source": "on_device_summary", "max_days": 14, "provider_dispatch": False}
    assert client.post("/v1/device-insights/trends", headers=AUTH, json=trends()).json()["insights"] == []
    body = {"version": "device-insights-v1", "source": "on_device_summary", "consent_to_process": True,
            "request": {"question_id": "coffee_counts", "context_scope": "today_logged_total", "date": "2026-10-28", "timezone": "UTC"},
            "today_logged_total_ml": 125}
    response = client.post("/v1/device-insights/assistant", headers=AUTH, json=body)
    assert response.status_code == 200
    assert response.json()["intake_context"]["beverage_total_ml"] == 125
    assert "iPhone" in response.json()["intake_context"]["note"]
    assert response.headers["cache-control"] == "no-store"
    assert list(directory.iterdir()) == []


def test_reviewed_questions_work_but_legacy_context_and_recorded_replays_fail_closed(setup):
    _, client, _ = setup
    questions = client.get("/v1/assistant/questions", headers=AUTH)
    assert questions.status_code == 200 and [item["id"] for item in questions.json()["questions"]] == list(SUGGESTED)
    answer = client.post("/v1/assistant", headers=AUTH, json={"question_id": "coffee_counts"})
    assert answer.status_code == 200
    assert answer.json()["answers"][0]["text"] == ANSWERS["coffee_caffeine"].text
    assert answer.json()["intake_context"] is None
    assert client.post("/v1/assistant", headers=AUTH, json={"question_id": "coffee_counts", "context_scope": "today_logged_total",
                       "date": "2026-10-28", "timezone": "UTC"}).status_code == 422
    assert client.post("/v1/assistant", headers=AUTH, json={"question_id": "coffee_counts", "source": "recorded_wonder"}).status_code == 404
    assert client.post("/v2/hydration-context-comparison", headers=AUTH, json={"mode": "recorded", "scenario": "complete"}).status_code == 404


def test_local_workout_and_context_demos_are_stateless_and_nonbillable(setup):
    app, client, directory = setup
    for mode in ("personal", "synthetic_demo"):
        response = client.post("/v2/workout-forecasts", headers=AUTH, json={"mode": mode, "timezone": "UTC"})
        assert response.status_code == 200
        assert response.json()["mode"] == mode and response.json()["synthetic"] == (mode == "synthetic_demo")
        assert response.json()["mock_explanation"] is None
    result = client.post("/v2/hydration-context-comparison", headers=AUTH, json={"mode": "mock", "scenario": "complete"})
    assert result.status_code == 200
    assert result.json()["provenance"]["provider"] is None
    assert result.json()["provenance"]["live_dispatch_enabled"] is False
    assert app.state._state == {} and list(directory.iterdir()) == []


def test_validation_and_internal_errors_do_not_echo_or_log_personal_input(setup, monkeypatch, caplog):
    _, client, _ = setup
    body = trends() | {"profile": {"private-marker": 70}}
    response = client.post("/v1/device-insights/trends", headers=AUTH, json=body)
    assert response.status_code == 422 and "private-marker" not in response.text
    from backend import device_insights

    def fail(*args, **kwargs):
        raise RuntimeError("private-marker")

    monkeypatch.setattr(device_insights, "build_aggregate_facts", fail)
    with caplog.at_level(logging.DEBUG):
        response = client.post("/v1/device-insights/trends", headers=AUTH, json=trends())
    assert response.status_code == 500 and response.json()["code"] == "internal_error"
    assert "private-marker" not in response.text and "private-marker" not in caplog.text
    assert client.post("/v1/device-insights/trends", headers=AUTH, content=b" " * 16_385).status_code == 413


@pytest.mark.parametrize("path", ["/v1/beverages", "/v1/settings", "/v1/recognitions", "/v1/wonder/trends", "/v1/meta/spending"])
def test_features_only_factory_does_not_expose_logging_camera_or_paid_routes(setup, path):
    _, client, _ = setup
    assert client.get(path, headers=AUTH).status_code == 404


@pytest.mark.parametrize("token", [None, "", "x" * 31, "x" * 31 + " ", "x" * 31 + "\n", "é" * 32, 1234])
def test_factory_rejects_tokens_with_the_existing_owner_token_validation(token):
    from backend.device_insights_app import create_device_insights_app
    with pytest.raises(ValueError, match="HYDRA_API_TOKEN"):
        create_device_insights_app(api_token=token)
