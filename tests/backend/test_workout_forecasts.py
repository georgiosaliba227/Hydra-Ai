"""Model boundary integration: no network, private ledger, or measurement persistence."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import socket
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app

AUTH = {"Authorization": "Bearer test-only-local-workout-token-00000000"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_AI_MODE", "mock")
    monkeypatch.setenv("META_BILLABLE_REQUESTS_ENABLED", "false")
    monkeypatch.setenv("HYDRA_META_HYDRATION_ENABLED", "false")
    with TestClient(create_app(db_path=tmp_path / "test.sqlite3", api_token=AUTH["Authorization"][7:])) as client:
        yield client


def personal_payload():
    now = datetime.now(timezone.utc)
    conditions = {"activity": "running", "intensity": "moderate", "temperature_c": 20.0, "humidity_percent": 60.0}
    return {
        "timezone": "UTC", "mode": "personal", "calibration_processing_consent": True,
        "exercise": {"event_id": str(uuid4()), "starts_at": (now + timedelta(hours=1)).isoformat(),
            "duration_minutes": 30.0, "conditions": conditions, "comparable_conditions_confirmed": True},
        "samples": [{"event_id": str(uuid4()), "observed_at": (now - timedelta(days=1)).isoformat(),
            "conditions": conditions,
            "measurement": {"pre_mass_kg": 70.0, "post_mass_kg": 69.0, "consumed_ml": 400.0,
                "urine_ml": 0.0, "duration_minutes": 60.0, "protocol_confirmed": True,
                "provenance": ["test_fixture_not_real_person"]},
            "errors": {"pre_mass_kg": 0.05, "post_mass_kg": 0.05, "consumed_ml": 10.0,
                "urine_ml": 0.0, "duration_minutes": 0.0, "provenance": ["test_fixture_bounds"]}}],
    }


def post(client, payload):
    return client.post("/v1/workout-forecasts", json=payload, headers=AUTH)


def test_auth_and_cold_start(client):
    assert client.post("/v1/workout-forecasts", json={"timezone": "UTC"}).status_code == 401
    response = post(client, {"timezone": "UTC"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    value = response.json()
    assert value["status"] == "insufficient_data"
    assert value["value_ml"] is value["lower_ml"] is value["upper_ml"] is None
    assert value["mock_explanation"] is None
    assert value["synthetic"] is False
    assert value["units"] == "mL"
    assert value["quantity"] == "estimated_sweat_loss"


def test_fixed_demo_is_labeled_and_never_calls_provider(client, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No external connection or live provider")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    from backend.hydration_intelligence import HydrationIntelligence
    monkeypatch.setattr(HydrationIntelligence, "explain", forbidden)
    monkeypatch.setattr(client.app.state.meta_ledger, "reserve_first", forbidden)
    result = post(client, {"timezone": "UTC", "mode": "synthetic_demo"})
    assert result.status_code == 200, result.text
    value = result.json()
    assert value["synthetic"] is True
    assert value["mode"] == "synthetic_demo"
    assert value["status"] == "estimated"
    assert 0 <= value["lower_ml"] <= value["value_ml"] <= value["upper_ml"]
    explanation = value["mock_explanation"]
    assert explanation["mode"] == "mock"
    assert explanation["provider"] is explanation["model"] is explanation["attempt_id"] is explanation["prediction"] is None
    assert explanation["context"]["synthetic"] is True
    assert explanation["context"]["estimated_sweat_loss_ml"] == value["value_ml"]
    assert client.get("/health").json()["billable_requests_enabled"] is False


def test_manual_calibration_uses_existing_engine_and_no_explanation_export(client, monkeypatch):
    from backend.hydration_intelligence import MockHydrationIntelligence
    monkeypatch.setattr(MockHydrationIntelligence, "explain", lambda *_: pytest.fail("No personal data to explanation adapter"))
    payload = personal_payload()
    response = post(client, payload)
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["status"] == "estimated"
    assert value["lower_ml"] == 645 and value["upper_ml"] == 755
    assert value["value_ml"] == 700
    assert value["sample_count"] == 1
    assert value["synthetic"] is False and value["mock_explanation"] is None
    # Forecasting is not beverage logging and does not persist health input.
    assert client.get("/v1/beverages", headers=AUTH).json()["items"] == []
    assert "pre_mass_kg" not in response.text


@pytest.mark.parametrize("changes", [
    {"mode": "real"}, {"mode": "meta_live"}, {"timezone": "Invalid/Zone"},
    {"calibration_processing_consent": 1}, {"heart_rate": 70}, {"hrv": 22},
    {"healthkit_records": []}, {"body_mass_kg": 70}, {"prompt": "private health"},
    {"samples": [{}] * 33}, {"beverage_total_ml": 2000},
])
def test_invalid_private_and_unsupported_fields_redacted(client, changes):
    result = post(client, {"timezone": "UTC"} | changes)
    assert result.status_code == 422, result.text
    assert result.json()["code"] == "invalid_request"
    assert "private health" not in result.text


def test_consent_synthetic_isolation_and_time_validation(client):
    payload = personal_payload()
    denied = payload | {"calibration_processing_consent": False}
    assert post(client, denied).status_code == 422
    assert post(client, payload | {"mode": "synthetic_demo"}).status_code == 422
    assert post(client, {"mode": "synthetic_demo", "timezone": "UTC", "calibration_processing_consent": True}).status_code == 422
    future = deepcopy(payload)
    future["samples"][0]["observed_at"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert post(client, future).status_code == 422
    ambiguous = deepcopy(payload)
    ambiguous["samples"][0]["observed_at"] = "2026-10-27T12:00:00"
    assert post(client, ambiguous).status_code == 422
    wearable = deepcopy(payload)
    wearable["exercise"]["duration_source"] = "wearable_aggregate"
    assert post(client, wearable).status_code == 422
    duplicate = deepcopy(payload)
    duplicate["samples"].append(duplicate["samples"][0])
    assert post(client, duplicate).status_code == 422


def test_missing_error_bounds_does_not_create_precision(client):
    payload = personal_payload()
    payload["samples"][0].pop("errors")
    response = post(client, payload)
    assert response.status_code == 200
    assert response.json()["status"] == "insufficient_data"
    assert response.json()["value_ml"] is None


@pytest.mark.parametrize("field,value", [("duration_minutes", -1.0), ("duration_minutes", True),
    ("duration_minutes", "NaN"), ("duration_minutes", 1441.0)])
def test_invalid_workout_numbers_fail_closed(client, field, value):
    payload = personal_payload()
    payload["exercise"][field] = value
    response = post(client, payload)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
    assert "test_fixture" not in response.text


def test_demo_unavailable_artifact_remains_insufficient_without_numeric_claim(client, monkeypatch, tmp_path):
    import ai.forecasting.predict as runtime
    monkeypatch.setattr(runtime, "ARTIFACT_DIR", tmp_path)
    response = post(client, {"timezone": "UTC", "mode": "synthetic_demo"})
    assert response.status_code == 200
    value = response.json()
    assert value["status"] == "insufficient_data"
    assert value["value_ml"] is value["lower_ml"] is value["upper_ml"] is None
    assert value["mock_explanation"]["prediction"] is None
    assert value["mock_explanation"]["context"]["estimated_sweat_loss_ml"] is None


@pytest.mark.parametrize("provenance_style", ["native", "ascii", "utf8"])
def test_all_32_bounded_samples_fit_forecast_transport(client, provenance_style):
    payload = personal_payload()
    original = payload["samples"][0]
    samples = []
    for index in range(32):
        sample = deepcopy(original)
        sample["event_id"] = str(uuid4())
        sample["observed_at"] = (datetime.now(timezone.utc) - timedelta(days=index + 1)).isoformat()
        if provenance_style != "native":
            character = "m" if provenance_style == "ascii" else "🌊"
            sample["measurement"]["provenance"] = [character * 100] * 4
            sample["errors"]["provenance"] = [character * 100] * 4
        else:
            sample["measurement"]["provenance"] = ["user_entered_manual_weighing"]
            sample["errors"]["provenance"] = ["user_reported_instrument_error_bounds"]
        samples.append(sample)
    payload["samples"] = samples
    response = post(client, payload)
    assert response.status_code == 200, response.text
    assert response.json()["sample_count"] == 32


def test_workout_body_limit_is_bounded_without_changing_other_routes(client):
    headers = AUTH | {"Content-Type": "application/json"}
    oversized = " " * (128 * 1024 + 1)
    assert client.post("/v1/workout-forecasts", content=oversized, headers=headers).status_code == 413
    # The existing personal-history endpoint retains its 16 KiB limit.
    assert client.post("/v1/forecasts", content=" " * (16 * 1024 + 1), headers=headers).status_code == 413
