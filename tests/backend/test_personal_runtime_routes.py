"""V3 boundary integration with an explicit nonbillable predictor dependency."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import socket
import sys
from types import ModuleType
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from ai.forecasting.longitudinal import predict_longitudinal
from backend.app import create_app

AUTH = {"Authorization": "Bearer personal-runtime-api-fixture-token-00000"}
NOW = datetime(2026, 11, 3, 15, tzinfo=timezone.utc)
CONDITIONS = {"activity": "running", "intensity": "moderate", "temperature_c": 22., "humidity_percent": 55.}
ROUTES = ("/v3/workout-forecasts", "/v3/hydration-analysis", "/v3/wonder/analysis/preview", "/v3/wonder/analysis")
WRAPPER = {"timezone", "mode", "mock_explanation", "explanation_policy"}


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


def payload(count=1):
    samples = []
    for index in range(count):
        samples.append({"event_id": str(UUID(int=index+1)), "observed_at": (NOW-timedelta(days=2*index+1)).isoformat(),
            "conditions": deepcopy(CONDITIONS), "measurement": {"pre_mass_kg": 70., "post_mass_kg": 69.,
                "consumed_ml": 400., "urine_ml": 0., "duration_minutes": 60., "protocol_confirmed": True,
                "provenance": ["synthetic_api_fixture"]},
            "errors": {"pre_mass_kg": .05, "post_mass_kg": .05, "consumed_ml": 10., "urine_ml": 0.,
                "duration_minutes": 0., "provenance": ["synthetic_api_error_bounds"]}})
    return {"timezone": "UTC", "mode": "personal", "calibration_processing_consent": True,
        "exercise": {"event_id": str(UUID(int=999)), "starts_at": (NOW+timedelta(hours=1)).isoformat(),
            "duration_minutes": 30., "conditions": deepcopy(CONDITIONS), "comparable_conditions_confirmed": True},
        "samples": samples}


def stub_predictor(exercise, samples=(), *, generated_at):
    """Software routing fixture, never evidence for the fitted numerical method."""
    result = predict_longitudinal(exercise, samples, generated_at=generated_at)
    selected = len(samples) >= 6 and exercise is not None and exercise.actual is None and result["status"] == "estimated"
    if selected:
        result.update(model_version="personal-runtime-rate-v1", value_ml=833.3333333333334,
            lower_ml=700.12, upper_ml=900.12, interval_kind="personal_runtime_measurement_error_envelope",
            personalization_status="fitted_personal_rate", data_sufficiency="earlier_own_measurements_research_only")
    result.update(research_only=True, generated_at=generated_at.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        learning={"version": "personal-runtime-rate-v1",
        "selected_method": "regularized_duration_rate" if selected else "existing_personal_baseline",
        "reason": "selected_by_earlier_error_comparison" if selected else "insufficient_comparable_history",
        "training_samples": len(samples), "validation_folds": 3 if selected else 0,
        "fitted_rate_ml_per_hour": 1666.6666666666667 if selected else None, "ridge_alpha": 1.,
        "supported_duration_minutes": {"minimum": 30., "maximum": 60.} if selected else {"minimum": None, "maximum": None},
        "baseline_mae_ml": 100. if selected else None, "candidate_mae_ml": 50. if selected else None,
        "paired_gain_ml": 50. if selected else None, "gain_standard_error_ml": 1. if selected else None,
        "training_sha256": "f"*64 if selected else None, "cadence_max_gap_seconds": 172800. if selected else None,
        "storage": "request_memory_only", "validation_origin": "earlier_own_measurements", "nominal_coverage": None})
    return result


@pytest.fixture
def client(tmp_path, monkeypatch):
    for key in ("META_BILLABLE_REQUESTS_ENABLED", "HYDRA_META_HYDRATION_ENABLED", "HYDRA_WONDER_LIVE", "HYDRA_WONDER_ANALYSIS_ENABLED"):
        monkeypatch.setenv(key, "false")
    monkeypatch.setenv("HYDRA_AI_MODE", "mock")
    monkeypatch.delenv("HYDRA_WONDER_RESULTS_DIR", raising=False)
    runtime = ModuleType("ai.forecasting.personal_runtime")
    runtime.predict_personal_runtime = stub_predictor
    monkeypatch.setitem(sys.modules, "ai.forecasting.personal_runtime", runtime)
    import backend.workout_forecasts as workout
    import backend.hydration_analysis as analysis
    import backend.wonder_analysis_routes as wonder
    import backend.schemas as schemas
    for module in (workout, analysis, wonder, schemas):
        monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(socket, "create_connection", lambda *_a, **_k: pytest.fail("No network"))
    with TestClient(create_app(tmp_path / "local.sqlite3", AUTH["Authorization"][7:])) as client:
        yield client


def post(client, route, body):
    return client.post(route, json=body, headers=AUTH)


def test_all_v3_boundaries_require_auth_and_bounded_no_store_transport(client):
    for route in ROUTES:
        assert client.post(route, json={"timezone": "UTC"}).status_code == 401
        response = client.post(route, content=" "*(128*1024+1), headers=AUTH)
        assert response.status_code == 413
        assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("count", [1, 6])
def test_v3_routes_share_exact_predictor_output_and_metadata(client, count):
    body = payload(count)
    result = post(client, ROUTES[0], body)
    assert result.status_code == 200, result.text
    forecast = result.json()
    assert forecast["research_only"] is True
    assert forecast["learning"]["selected_method"] == ("regularized_duration_rate" if count == 6 else "existing_personal_baseline")
    analysis = post(client, ROUTES[1], body)
    assert analysis.status_code == 200, analysis.text
    analysis = analysis.json()
    assert analysis["version"] == "hydration-analysis-v3"
    assert analysis["numerical_forecast"] == {key: value for key, value in forecast.items() if key not in WRAPPER}
    assert "learning" not in analysis  # Metadata has one numerical owner.
    assert analysis["wonder"]["preview"] is analysis["wonder"]["saved"] is None
    preview = post(client, ROUTES[2], body)
    assert preview.status_code == 200, preview.text
    facts = preview.json()["facts"]
    assert facts["version"] == "wonder-analysis-facts-v2"
    if count == 6:
        assert facts["forecast"] == {"status": "estimated", "value_ml": 833., "lower_ml": 700., "upper_ml": 901.,
            "interval_kind": "personal_runtime_measurement_error_envelope"}
        assert forecast["value_ml"] == 833.3333333333334
    else:
        assert facts["forecast"]["value_ml"] == forecast["value_ml"] == 700.
    assert facts["workout_comparison"]["typical_duration_minutes"] == 60
    assert preview.headers["cache-control"] == "no-store"
    assert preview.json()["live_available"] is preview.json()["dispatch_supported"] is False
    assert preview.json()["numerical_contract"] == "personal-runtime-api-v3"


def test_v3_never_computes_old_workout_wonder_and_strips_fitting_metadata_from_provider_payload(client, monkeypatch):
    import backend.hydration_analysis as local
    from backend.wonder_analysis import analysis_payload
    monkeypatch.setattr(local, "_wonder", lambda *_a, **_k: pytest.fail("V3 must not run a second predictor"))
    monkeypatch.setattr(local, "load_workout", lambda *_: pytest.fail("V3 must not replay legacy prediction text"))
    for route in ROUTES[1:3]:
        response = post(client, route, payload(6))
        assert response.status_code == 200, response.text
    facts = post(client, ROUTES[2], payload(6)).json()["facts"]
    disclosure = json.dumps(analysis_payload(facts))
    for excluded in ("training_sha256", "fitted_rate_ml_per_hour", "ridge_alpha", "validation_folds", "pre_mass_kg", "event_id", "observed_at", "f"*64):
        assert excluded not in disclosure


def test_v3_synthetic_keeps_existing_engine_without_runtime_or_personal_reads(client, monkeypatch):
    runtime = sys.modules["ai.forecasting.personal_runtime"]
    monkeypatch.setattr(runtime, "predict_personal_runtime", lambda *_a, **_k: pytest.fail("No fitting a synthetic demo"))
    monkeypatch.setattr(client.app.state.repository, "list_all", lambda *_: pytest.fail("No personal log read"))
    import backend.wonder_analysis_routes as rich
    monkeypatch.setattr(rich, "load_analysis", lambda *_: pytest.fail("No personal saved-result read"))
    body = {"timezone": "UTC", "mode": "synthetic_demo"}
    original = post(client, "/v1/workout-forecasts", body).json()
    current = post(client, ROUTES[0], body)
    assert current.status_code == 200, current.text
    assert current.json() == original
    assert post(client, ROUTES[1], body).json()["intake"]["beverage_volume_ml"] is None
    assert post(client, ROUTES[2], body).json()["saved"] is None


def test_old_routes_and_hashes_do_not_invoke_new_predictor(client, monkeypatch):
    runtime = sys.modules["ai.forecasting.personal_runtime"]
    monkeypatch.setattr(runtime, "predict_personal_runtime", lambda *_a, **_k: pytest.fail("Legacy engines must be preserved"))
    body = payload()
    for route in ("/v1/workout-forecasts", "/v2/workout-forecasts", "/v1/hydration-analysis", "/v1/wonder/analysis/preview"):
        assert post(client, route, body).status_code == 200
    # This frozen existing fixture exercises exact legacy facts, options and hash.
    fixtures = Path(__file__).parents[1] / "fixtures"
    request = json.loads((fixtures / "hydration_analysis/personal_calibrated.request.json").read_text())
    request["exercise"]["starts_at"] = (NOW+timedelta(hours=1)).isoformat()
    old = post(client, "/v1/wonder/analysis/preview", request).json()
    assert "learning" not in json.dumps(old)
    assert old["facts"]["forecast"]["interval_kind"] == "historical_error_envelope"
    assert old == json.loads((fixtures / "wonder_analysis/personal_calibrated.http_preview.json").read_text())


@pytest.mark.parametrize("change", [{"engine": "legacy"}, {"predictor": "trained"}, {"healthkit_records": []},
    {"calibration_processing_consent": False}, {"calibration_processing_consent": 1}, {"timezone": "Bad/Zone"}])
def test_v3_cannot_select_an_engine_or_upgrade_processing_consent(client, change):
    body = payload() | change
    for route in ROUTES[:3]:
        response = post(client, route, body)
        assert response.status_code == 422
        assert response.json()["code"] == "invalid_request"


def test_v3_exact_hash_consent_default_disabled_and_stale_logs(client):
    body = payload(6)
    preview = post(client, ROUTES[2], body).json()
    request = body | {"payload_sha256": preview["payload_sha256"], "consent_to_send": True}
    assert post(client, ROUTES[3], request).status_code == 503
    assert post(client, ROUTES[3], request | {"consent_to_send": 1}).status_code == 422
    assert post(client, ROUTES[3], request | {"payload_sha256": "0"*64}).status_code == 409
    result = client.post("/v1/beverages", headers=AUTH | {"Idempotency-Key": str(uuid4())}, json={
        "category": "water", "consumed_ml": 200, "consumed_at": (NOW-timedelta(minutes=1)).isoformat(),
        "timezone": "UTC", "source": "manual"})
    assert result.status_code == 201
    assert post(client, ROUTES[3], request).json()["code"] == "analysis_preview_stale"


def test_v3_exact_saved_result_replays_while_live_disabled_and_delete_erases_it(client, tmp_path):
    from backend import wonder_analysis as rich
    from backend.wonder_results import save_result
    body = payload(6)
    view = post(client, ROUTES[2], body).json()
    selection = {"sections": {section: choices[:3] for section, choices in rich.applicable_insights(view["facts"]).items()}}
    result = rich.analysis_result(view["facts"], selection, account="georgiosaliba227", attempt_id=str(UUID(int=123)),
        generated_at=NOW.isoformat(), observations={"latency_ms": 0, "input_tokens": 1, "output_tokens": 1,
            "usage_derived_cost_micro_usd": 1, "billed_cost_usd": None})
    directory = tmp_path / "results"
    directory.mkdir(mode=0o700)
    save_result(directory, result)
    client.app.state.wonder_results_dir = directory
    client.app.state.wonder_trends_gateway = lambda: pytest.fail("No second dispatch for a saved result")
    replay = post(client, ROUTES[3], body | {"payload_sha256": view["payload_sha256"], "consent_to_send": True})
    assert replay.status_code == 200 and replay.json() == {"replayed": True, "saved": True, "result": result}
    assert client.get("/v1/export", headers=AUTH).json()["wonder_analysis_explanations"] == [result]
    assert client.delete("/v1/data?confirm=delete-all-my-data", headers=AUTH).json()["deleted_analysis_explanations"] == 1


def test_v3_descriptive_comparisons_use_ties_even_rounding_without_another_predictor(client):
    body = payload(2)
    body["exercise"]["duration_minutes"] = 30.5
    body["samples"][0]["measurement"]["duration_minutes"] = 60.
    body["samples"][1]["measurement"]["duration_minutes"] = 61.
    for item in [body["exercise"], *body["samples"]]:
        item["conditions"].update(temperature_c=22.5, humidity_percent=55.5)
    response = post(client, ROUTES[2], body)
    assert response.status_code == 200, response.text
    comparison = response.json()["facts"]["workout_comparison"]
    assert comparison == {"planned_duration_minutes": 30, "typical_duration_minutes": 60,
        "planned_temperature_c": 22, "typical_temperature_c": 22,
        "planned_humidity_percent": 56, "typical_humidity_percent": 56}


def test_v3_all_bounded_utf8_samples_fit_transport_and_future_or_duplicate_history_is_rejected(client):
    body = payload(32)
    for sample in body["samples"]:
        sample["measurement"]["provenance"] = ["🌊"*100]*4
        sample["errors"]["provenance"] = ["🌊"*100]*4
    for route in ROUTES[:3]:
        response = client.post(route, content=json.dumps(body, ensure_ascii=False).encode(),
            headers=AUTH | {"Content-Type": "application/json"})
        assert response.status_code == 200, response.text
    future = payload()
    future["samples"][0]["observed_at"] = (NOW+timedelta(seconds=1)).isoformat()
    duplicate = payload()
    duplicate["samples"].append(deepcopy(duplicate["samples"][0]))
    for invalid in (future, duplicate):
        for route in ROUTES[:3]:
            assert post(client, route, invalid).status_code == 422


def test_runtime_failure_never_falls_back_or_discloses_private_exception_text(client, monkeypatch):
    runtime = sys.modules["ai.forecasting.personal_runtime"]
    def broken(*_args, **_kwargs):
        raise RuntimeError("private-fitting-observations")
    monkeypatch.setattr(runtime, "predict_personal_runtime", broken)
    client.app.state.wonder_trends_gateway = lambda: pytest.fail("Runtime failure must not dispatch")
    for route in ROUTES[:3]:
        response = post(client, route, payload())
        assert response.status_code in (500, 503)
        assert "private-fitting-observations" not in response.text
        assert response.json()["code"] == "internal_error"
    assert post(client, "/v2/workout-forecasts", payload()).status_code == 200
