"""Actual offline runtime integration; synthetic measurements are not validation."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import socket
import json
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from ai.forecasting import personal_runtime as runtime

from backend.app import create_app
from backend.workout_forecasts import WorkoutForecastInput

NOW = datetime(2026, 11, 3, 15, tzinfo=timezone.utc)
AUTH = {"Authorization": "Bearer actual-personal-runtime-local-test-token-0000"}
WRAPPER = {"timezone", "mode", "mock_explanation", "explanation_policy"}


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


def request_body(losses=(300., 500., 400., 500., 400., 500.)):
    conditions = {"activity": "running", "intensity": "moderate", "temperature_c": 22., "humidity_percent": 55.}
    return {"mode": "personal", "timezone": "UTC", "calibration_processing_consent": True,
        "exercise": {"event_id": str(UUID(int=999)), "starts_at": (NOW+timedelta(hours=1)).isoformat(),
                     "duration_minutes": 60., "conditions": conditions, "comparable_conditions_confirmed": True},
        "samples": [{"event_id": str(UUID(int=index+1)),
            "observed_at": (NOW-timedelta(days=2*(len(losses)-index)-1)).isoformat(), "conditions": conditions,
            "measurement": {"pre_mass_kg": 70., "post_mass_kg": 70.-loss/1000., "consumed_ml": 0., "urine_ml": 0.,
                "duration_minutes": 60., "protocol_confirmed": True, "provenance": ["invented_runtime_boundary_fixture"]},
            "errors": {"pre_mass_kg": .01, "post_mass_kg": .01, "consumed_ml": 0., "urine_ml": 0.,
                "duration_minutes": 0., "provenance": ["invented_instrument_error_fixture"]}}
            for index, loss in enumerate(losses)]}


@pytest.fixture
def client(tmp_path, monkeypatch):
    for key in ("META_BILLABLE_REQUESTS_ENABLED", "HYDRA_META_HYDRATION_ENABLED", "HYDRA_WONDER_LIVE", "HYDRA_WONDER_ANALYSIS_ENABLED"):
        monkeypatch.setenv(key, "false")
    monkeypatch.setenv("HYDRA_AI_MODE", "mock")
    monkeypatch.delenv("HYDRA_WONDER_RESULTS_DIR", raising=False)
    import backend.workout_forecasts as forecast
    import backend.hydration_analysis as analysis
    import backend.wonder_analysis_routes as wonder
    for module in (forecast, analysis, wonder):
        monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(socket, "create_connection", lambda *_a, **_k: pytest.fail("No provider connection"))
    with TestClient(create_app(tmp_path / "runtime.sqlite3", AUTH["Authorization"][7:])) as client:
        yield client


@pytest.mark.parametrize("selected", [False, True])
def test_actual_runtime_selected_or_retained_matches_every_v3_boundary(client, selected):
    body = request_body() if selected else request_body((400.,)*6)
    request = WorkoutForecastInput.model_validate(body)
    expected = runtime.predict_personal_runtime(request.exercise.engine(), tuple(sample.engine() for sample in request.samples), generated_at=NOW)
    forecast = client.post("/v3/workout-forecasts", json=body, headers=AUTH)
    analysis = client.post("/v3/hydration-analysis", json=body, headers=AUTH)
    preview = client.post("/v3/wonder/analysis/preview", json=body, headers=AUTH)
    assert forecast.status_code == analysis.status_code == preview.status_code == 200
    numerical = {key: value for key, value in forecast.json().items() if key not in WRAPPER}
    assert numerical == analysis.json()["numerical_forecast"] == expected
    if selected:
        assert numerical["value_ml"] == pytest.approx(441.6666666666667)
        assert numerical["learning"]["selected_method"] == "regularized_duration_rate"
        assert numerical["interval_kind"] == "personal_runtime_measurement_error_envelope"
        assert preview.json()["facts"]["forecast"]["value_ml"] == 442.
    else:
        assert numerical["value_ml"] == 400.
        assert numerical["learning"]["selected_method"] == "existing_personal_baseline"
        assert numerical["learning"]["reason"] == "baseline_retained_after_validation"
    assert numerical["learning"]["storage"] == "request_memory_only"
    assert preview.json()["numerical_contract"] == "personal-runtime-api-v3"


def test_actual_completed_measurement_bypasses_fitting_on_all_v3_routes(client):
    body = request_body()
    actual = deepcopy(body["samples"][-1])
    actual.update(event_id=body["exercise"]["event_id"], observed_at=(NOW-timedelta(hours=1)).isoformat())
    body["exercise"].update(starts_at=(NOW-timedelta(hours=2)).isoformat(), actual=actual)
    forecast = client.post("/v3/workout-forecasts", json=body, headers=AUTH).json()
    analysis = client.post("/v3/hydration-analysis", json=body, headers=AUTH).json()
    preview = client.post("/v3/wonder/analysis/preview", json=body, headers=AUTH).json()
    assert forecast["value_ml"] == 500.
    assert forecast["learning"]["reason"] == "actual_measurement_preserved"
    assert forecast["learning"]["selected_method"] == "existing_personal_baseline"
    assert analysis["numerical_forecast"]["value_ml"] == preview["facts"]["forecast"]["value_ml"] == 500.


@pytest.mark.parametrize("name", ["selected", "fallback", "synthetic"])
def test_native_frozen_v3_fixtures_match_actual_runtime_routes(client, name):
    folder = Path(__file__).parent / "fixtures" / "personal_runtime_v3"
    body = json.loads((folder / (name+".request.json")).read_text())
    for suffix, route in (("forecast", "/v3/workout-forecasts"), ("analysis", "/v3/hydration-analysis"),
                          ("preview", "/v3/wonder/analysis/preview")):
        expected = json.loads((folder / (name+"."+suffix+".json")).read_text())
        response = client.post(route, json=body, headers=AUTH)
        assert response.status_code == 200 and response.json() == expected


def test_real_runtime_cold_start_abstains_with_null_fit_bounds_and_no_live_disclosure(client):
    body = {"timezone": "UTC"}
    forecast = client.post("/v3/workout-forecasts", json=body, headers=AUTH).json()
    analysis = client.post("/v3/hydration-analysis", json=body, headers=AUTH).json()
    preview = client.post("/v3/wonder/analysis/preview", json=body, headers=AUTH).json()
    assert forecast["status"] == "insufficient_data" and forecast["value_ml"] is None
    assert forecast["learning"]["reason"] == "baseline_unavailable"
    assert forecast["learning"]["supported_duration_minutes"] == {"minimum": None, "maximum": None}
    assert forecast["learning"]["training_sha256"] is None
    assert analysis["numerical_forecast"]["learning"] == forecast["learning"]
    assert preview["live_available"] is preview["explainable"] is False
