"""Context V2 boundary tests; labels are software fixtures, not clinical evidence."""
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app

AUTH = {"Authorization": "Bearer context-v2-local-test-token-00000000000000"}

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_AI_MODE", "mock")
    monkeypatch.setenv("META_BILLABLE_REQUESTS_ENABLED", "false")
    monkeypatch.setenv("HYDRA_META_HYDRATION_ENABLED", "false")
    with TestClient(create_app(db_path=tmp_path / "local.sqlite3", api_token=AUTH["Authorization"][7:])) as client:
        yield client


def test_context_comparison_requires_auth_and_preserves_numerical_authority(client):
    payload = {"mode": "mock", "scenario": "complete"}
    assert client.post("/v2/hydration-context-comparison", json=payload).status_code == 401
    response = client.post("/v2/hydration-context-comparison", json=payload, headers=AUTH)
    assert response.status_code == 200
    result = response.json()
    assert result["version"] == "hydration-context-comparison-v2"
    assert result["systems"]["A"]["prediction"] == result["systems"]["C"]["prediction"]
    assert result["systems"]["B"]["prediction"] is None
    assert result["provenance"]["provider"] is result["provenance"]["model"] is None
    assert result["provenance"]["live_dispatch_enabled"] is False
    assert response.headers["cache-control"] == "no-store"

@pytest.mark.parametrize("change", [{"mode": "meta_live"}, {"context": {"weight": 70}},
    {"scenario": "user_supplied"}, {"candidate_model": "arbitrary"}, {"account": "georgiosaliba227"},
    {"heart_rate": 80}, {"healthkit_records": []}, {"daily_goal_ml": 2000}, {"prompt": "private"}])
def test_refuses_live_personal_and_arbitrary_context(client, change):
    response = client.post("/v2/hydration-context-comparison", json={"mode": "mock", "scenario": "complete"} | change, headers=AUTH)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
    assert "private" not in response.text


def test_context_scenarios_surface_contradictions_missingness_and_abstention(client):
    def scenario(name):
        response = client.post("/v2/hydration-context-comparison", json={"mode": "mock", "scenario": name}, headers=AUTH)
        assert response.status_code == 200
        return response.json()
    missing = scenario("missing_measurements")
    assert missing["systems"]["A"]["prediction"]["status"] == "insufficient_data"
    assert missing["systems"]["B"]["interpretation"]["numerical_abstention"] is True
    assert "calibration_measurements" in missing["systems"]["B"]["interpretation"]["missing_information"]
    conflict = scenario("contradictory_mass")
    assert "negative_mass_balance" in conflict["systems"]["B"]["interpretation"]["contradictions"]
    assert conflict["systems"]["C"]["prediction"]["value_ml"] is None
    bio = scenario("biometrics_and_supplements")
    assert "biometrics_not_dehydration" in bio["systems"]["B"]["interpretation"]["uncertainty"]
    assert "supplements_no_automatic_adjustment" in bio["systems"]["B"]["interpretation"]["uncertainty"]


def test_structured_outputs_cannot_override_numbers_or_add_diagnoses():
    from backend.hydration_context_v2 import build_scenario, mock_selection, validate_selection
    context, prediction = build_scenario("complete")
    valid = mock_selection(context, prediction)
    assert validate_selection(valid, context, prediction)
    for field in ("daily_goal_ml", "hydration_percent", "diagnosis", "prediction", "explanation"):
        with pytest.raises(ValueError):
            validate_selection(valid | {field: "unsupported"}, context, prediction)
    unsupported = valid | {"contradictions": ["negative_mass_balance"]}
    with pytest.raises(ValueError):
        validate_selection(unsupported, context, prediction)
    with pytest.raises(ValueError):
        validate_selection(valid | {"numerical_abstention": True}, context, prediction)


def test_wonder_is_the_only_candidate_and_has_no_observed_usage_or_cost(client, monkeypatch):
    import socket
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("network forbidden"))
    for payload in ({"mode": "mock", "scenario": "complete"},
                    {"mode": "mock", "scenario": "complete", "candidate_model": "muse-wonder-1.0"}):
        response = client.post("/v2/hydration-context-comparison", json=payload, headers=AUTH)
        assert response.status_code == 200
        result = response.json()
        assert result["provenance"]["candidate_model"] == "muse-wonder-1.0"
        assert result["provenance"]["model_identity_verified"] is False
        assert all(value is None for value in result["provider_observations"].values())
    spark = {"mode": "mock", "scenario": "complete", "candidate_model": "muse-spark-1.3"}
    assert client.post("/v2/hydration-context-comparison", json=spark, headers=AUTH).status_code == 422


def test_mock_benchmark_uses_fixed_labels_and_separates_numerical_from_contextual():
    from backend.hydration_context_v2 import benchmark_context
    result = benchmark_context()
    assert result["evidence_kind"] == "hand_labeled_synthetic_mock_cases"
    assert result["real_meta_observations"] == 0
    assert result["numerical_improvement_claimed"] is False
    assert result["systems"]["A"]["contextual_metrics"] is None
    assert result["systems"]["B"]["numerical_metrics"] is None
    assert result["systems"]["C"]["numerical_equal_to_A"] is True
    assert result["systems"]["B"]["contextual_metrics"]["unsupported_claims"] == 0
    assert result == benchmark_context()


def test_scorer_detects_unsupported_selections_and_omitted_uncertainty():
    from backend.hydration_context_v2 import score_selection, EXPECTED
    fabricated = {"factors": ["heart_rate_context"], "missing_information": [], "contradictions": [],
        "uncertainty": [], "measurement_suggestions": []}
    score = score_selection(fabricated, EXPECTED["complete"])
    assert score["unsupported_claims"] == 1
    assert score["uncertainty_complete"] is False


def test_v2_workout_api_synthetic_comparison_cannot_change_numbers(client):
    response = client.post("/v2/workout-forecasts", json={"timezone": "UTC", "mode": "synthetic_demo"}, headers=AUTH)
    assert response.status_code == 200
    value = response.json()
    for system in ("A", "C"):
        prediction = value["context_comparison"]["systems"][system]["prediction"]
        assert prediction["value_ml"] == value["value_ml"]
        assert prediction["lower_ml"] == value["lower_ml"]
        assert prediction["upper_ml"] == value["upper_ml"]
    assert value["mock_explanation"] is None
    assert client.post("/v2/workout-forecasts", json={"timezone": "UTC"}).status_code == 401


def test_v2_personal_history_never_reaches_contextual_adapter(client, monkeypatch):
    from backend import hydration_context_v2
    monkeypatch.setattr(hydration_context_v2, "compare_context", lambda *a, **k: pytest.fail("personal context must not enter adapter"))
    response = client.post("/v2/workout-forecasts", json={"timezone": "UTC"}, headers=AUTH)
    assert response.status_code == 200
    value = response.json()
    assert value["status"] == "insufficient_data"
    assert value["model_version"] == "personal-longitudinal-v2"
    assert value["context_comparison"] is None
    assert value["longitudinal_history"]["total_samples"] == 0
    assert value["longitudinal_history"]["history_retained_by_caller"] is True


def test_v2_personal_calibration_requires_consent_and_exposes_session_history(client):
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4
    now = datetime.now(timezone.utc)
    conditions = {"activity": "running", "intensity": "moderate", "temperature_c": 20.0, "humidity_percent": 50.0}
    payload = {"timezone": "UTC", "mode": "personal", "exercise": {"event_id": str(uuid4()),
        "starts_at": (now + timedelta(hours=1)).isoformat(), "duration_minutes": 60.0,
        "conditions": conditions, "comparable_conditions_confirmed": True}, "samples": []}
    for index, post_mass in enumerate((69.5, 69.4, 69.3)):
        payload["samples"].append({"event_id": str(uuid4()), "observed_at": (now - timedelta(days=3-index)).isoformat(),
            "conditions": conditions, "measurement": {"pre_mass_kg": 70.0, "post_mass_kg": post_mass,
                "consumed_ml": 0.0, "urine_ml": 0.0, "duration_minutes": 60.0, "protocol_confirmed": True,
                "provenance": ["test_fixture_not_real_person"]}, "errors": {"pre_mass_kg": 0.01,
                "post_mass_kg": 0.01, "consumed_ml": 0.0, "urine_ml": 0.0, "duration_minutes": 0.0,
                "provenance": ["synthetic_test_bounds"]}})
    assert client.post("/v2/workout-forecasts", json=payload, headers=AUTH).status_code == 422
    payload["calibration_processing_consent"] = True
    response = client.post("/v2/workout-forecasts", json=payload, headers=AUTH)
    assert response.status_code == 200
    result = response.json()
    assert result["model_version"] == "personal-longitudinal-v2"
    assert result["value_ml"] == 600.0
    assert result["longitudinal_history"]["total_samples"] == 3
    assert result["longitudinal_history"]["comparable_samples"] == 3
    assert result["context_comparison"] is result["mock_explanation"] is None
    assert client.get("/v1/beverages", headers=AUTH).json()["items"] == []
