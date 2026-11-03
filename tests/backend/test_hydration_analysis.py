"""The local analysis preserves numbers, privacy, temporal scope and Wonder replay."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import socket
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app

AUTH = {"Authorization": "Bearer local-hydration-analysis-test-token-0000"}
CONDITIONS = {"activity": "running", "intensity": "moderate", "temperature_c": 20.0, "humidity_percent": 60.0}


@pytest.fixture
def client(tmp_path, monkeypatch):
    for key in ("META_BILLABLE_REQUESTS_ENABLED", "HYDRA_META_HYDRATION_ENABLED", "HYDRA_WONDER_LIVE"):
        monkeypatch.setenv(key, "false")
    monkeypatch.setenv("HYDRA_AI_MODE", "mock")
    with TestClient(create_app(tmp_path / "analysis.sqlite3", AUTH["Authorization"][7:])) as client:
        yield client


def payload(now=None):
    now = now or datetime.now(timezone.utc)
    return {"timezone": "UTC", "mode": "personal", "calibration_processing_consent": True,
            "exercise": {"event_id": str(uuid4()), "starts_at": (now + timedelta(hours=1)).isoformat(),
                         "duration_minutes": 30.0, "conditions": deepcopy(CONDITIONS),
                         "comparable_conditions_confirmed": True},
            "samples": [{"event_id": str(uuid4()), "observed_at": (now - timedelta(days=1)).isoformat(),
                         "conditions": deepcopy(CONDITIONS), "measurement": {
                             "pre_mass_kg": 70.0, "post_mass_kg": 69.0, "consumed_ml": 400.0,
                             "urine_ml": 0.0, "duration_minutes": 60.0, "protocol_confirmed": True,
                             "provenance": ["synthetic_test_weighing"]},
                         "errors": {"pre_mass_kg": 0.05, "post_mass_kg": 0.05, "consumed_ml": 10.0,
                                    "urine_ml": 0.0, "duration_minutes": 0.0,
                                    "provenance": ["synthetic_test_instrument_bounds"]}}]}


def post(client, body):
    return client.post("/v1/hydration-analysis", json=body, headers=AUTH)


def add_log(client, at, volume=300, category="Water"):
    result = client.post("/v1/beverages", headers=AUTH | {"Idempotency-Key": str(uuid4())}, json={
        "category": category, "consumed_ml": volume, "consumed_at": at.isoformat(),
        "timezone": "UTC", "source": "manual"})
    assert result.status_code == 201, result.text
    return result.json()


def test_cold_start_keeps_absent_measurement_and_logged_intake_distinct(client):
    response = post(client, {"timezone": "UTC"})
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["version"] == "hydration-analysis-v1"
    assert value["research_only"] is True and value["text_origin"] == "deterministic_local"
    assert value["numerical_forecast"]["status"] == "insufficient_data"
    assert value["intake"]["beverage_volume_ml"] == 0
    assert value["intake"]["completeness"] == "unverified"
    assert value["intake"]["water_ml"] is None
    assert value["exercise_accounting"]["value_ml"] is None
    assert value["wonder"]["preview"] is value["wonder"]["saved"] is None
    assert [s["id"] for s in value["sections"]] == [
        "summary", "workout_loss", "activity", "environment", "beverages", "trends", "uncertainty", "measurement"]
    assert all(s["facts"] and s["text"] and s["evidence_status"] for s in value["sections"])


def test_forecast_numbers_and_existing_wonder_preview_are_preserved(client):
    body = payload()
    result = post(client, body)
    assert result.status_code == 200, result.text
    value = result.json()
    forecast = value["numerical_forecast"]
    assert forecast["value_ml"] == 700
    assert (forecast["lower_ml"], forecast["upper_ml"], forecast["units"]) == (645, 755, "mL")
    assert forecast["model_version"] == "personal-longitudinal-v2"
    original = client.post("/v1/wonder/workout/preview", json=body, headers=AUTH).json()
    assert value["wonder"]["preview"] == {k: v for k, v in original.items()
                                            if k not in ("saved", "live_available", "account_id")}
    assert value["exercise_accounting"]["status"] == "unavailable"
    assert value["exercise_accounting"]["lower_ml"] is None
    assert "pre_mass_kg" not in result.text
    assert client.get("/v1/beverages", headers=AUTH).json()["items"] == []


def test_personal_analysis_and_synthetic_demo_cannot_dispatch_or_touch_financial_state(client, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Analysis cannot open a provider connection or reserve funds")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(client.app.state.meta_ledger, "reserve_first", forbidden)
    client.app.state.wonder_trends_gateway = forbidden
    add_log(client, datetime.now(timezone.utc) - timedelta(minutes=5), 837, "private-entry")
    assert post(client, payload()).status_code == 200
    monkeypatch.setattr(client.app.state.repository, "list_all", forbidden)
    response = post(client, {"timezone": "UTC", "mode": "synthetic_demo"})
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["numerical_forecast"]["synthetic"] is True
    assert value["intake"]["status"] == "unavailable_in_synthetic"
    assert value["intake"]["beverage_volume_ml"] is None
    assert value["wonder"]["provider_called"] is False
    assert value["wonder"]["saved"] is None
    assert "837" not in response.text and "private-entry" not in response.text
    assert all(s["evidence_status"] == "synthetic" for s in value["sections"])


def test_day_window_uses_timezone_and_filters_future_or_other_day_logs(client, monkeypatch):
    import backend.hydration_analysis as analysis
    fixed = datetime(2026, 11, 2, 0, 30, tzinfo=timezone.utc)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)
    monkeypatch.setattr(analysis, "datetime", Clock)
    add_log(client, datetime(2026, 11, 1, 5, 0, tzinfo=timezone.utc), 250)
    add_log(client, datetime(2026, 11, 1, 3, 59, tzinfo=timezone.utc), 500)
    # Storage can contain a shortly future log; it is excluded from observed totals.
    add_log(client, datetime(2026, 11, 2, 0, 31, tzinfo=timezone.utc), 700)
    value = post(client, {"timezone": "America/New_York"}).json()
    assert value["intake"]["local_date"] == "2026-11-01"
    assert value["intake"]["start_utc"] == "2026-11-01T04:00:00.000000Z"
    assert value["intake"]["end_utc"] == "2026-11-02T00:30:00.000000Z"
    assert value["intake"]["beverage_volume_ml"] == 250
    assert value["intake"]["water_ml"] is None  # No invented category water fraction.
    assert value["sections"][5]["facts"]["logged_days"] == 1


@pytest.mark.parametrize("change", [
    {"timezone": "Invalid/Zone"}, {"prompt": "do not echo this"}, {"healthkit_records": []},
    {"heart_rate": 70}, {"calibration_processing_consent": 1}, {"mode": "meta_live"},
    {"samples": [{}] * 33}, {"beverage_total_ml": 2000},
])
def test_invalid_requests_fail_closed_without_echo(client, change):
    response = post(client, {"timezone": "UTC"} | change)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
    assert "do not echo this" not in response.text


def test_auth_no_store_and_actual_transport_limit(client):
    assert client.post("/v1/hydration-analysis", json={"timezone": "UTC"}).status_code == 401
    response = post(client, {"timezone": "UTC"})
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-request-id"]
    headers = AUTH | {"Content-Type": "application/json"}
    assert client.post("/v1/hydration-analysis", content=" " * (128 * 1024 + 1), headers=headers).status_code == 413
    body = payload()
    seed = body["samples"][0]
    body["samples"] = []
    for index in range(32):
        sample = deepcopy(seed)
        sample["event_id"] = str(uuid4())
        sample["observed_at"] = (datetime.now(timezone.utc) - timedelta(days=index + 1)).isoformat()
        sample["measurement"]["provenance"] = ["🌊" * 100] * 4
        sample["errors"]["provenance"] = ["🌊" * 100] * 4
        body["samples"].append(sample)
    # Serialize as real UTF-8, rather than counting unicode scalar values as bytes.
    response = client.post("/v1/hydration-analysis", content=json.dumps(body, ensure_ascii=False).encode(), headers=headers)
    assert response.status_code == 200, response.text


def test_history_consent_future_and_duplicate_measurements_are_rejected(client):
    body = payload()
    assert post(client, body | {"calibration_processing_consent": False}).status_code == 422
    future = deepcopy(body)
    future["samples"][0]["observed_at"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert post(client, future).status_code == 422
    duplicate = deepcopy(body)
    duplicate["samples"].append(deepcopy(duplicate["samples"][0]))
    assert post(client, duplicate).status_code == 422
    assert post(client, body | {"mode": "synthetic_demo"}).status_code == 422


def test_missing_bounds_and_changed_conditions_abstain_instead_of_adjustment(client):
    body = payload()
    body["samples"][0].pop("errors")
    value = post(client, body).json()
    assert value["numerical_forecast"]["value_ml"] is None
    assert "usable_measurements_with_error_bounds" in value["missing_inputs"]
    body = payload()
    body["exercise"]["conditions"]["temperature_c"] = 38.0
    value = post(client, body).json()
    assert value["numerical_forecast"]["status"] == "insufficient_data"
    assert value["environmental_context"]["temperature_c"] == 38
    assert value["environmental_context"]["context_only"] is True
    assert value["calibration"]["comparable_samples"] == 0


def test_started_workout_is_stale_and_cannot_be_subtracted_or_explained_as_plan(client):
    body = payload()
    body["exercise"]["starts_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    value = post(client, body).json()
    assert value["numerical_forecast"]["value_ml"] is None
    assert "actual_measurement_for_started_exercise" in value["missing_inputs"]
    assert value["exercise_accounting"]["value_ml"] is None
    assert value["wonder"]["status"] == "not_applicable"


def test_unexpected_model_error_returns_sanitized_failure(client, monkeypatch):
    import backend.hydration_analysis as analysis
    def broken(*args, **kwargs):
        raise RuntimeError("private-health-input")
    monkeypatch.setattr(analysis, "predict_longitudinal", broken)
    response = post(client, payload())
    assert response.status_code == 503
    assert "private-health-input" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_documented_composition_has_per_nutrient_coverage_without_invented_subtotals(client, monkeypatch):
    import backend.hydration_analysis as analysis
    now = datetime(2026, 11, 2, 15, tzinfo=timezone.utc)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz) if tz else now.replace(tzinfo=None)
    monkeypatch.setattr(analysis, "datetime", Clock)
    first = add_log(client, now-timedelta(minutes=5), 200)
    second = add_log(client, now-timedelta(minutes=4), 100)
    repository = client.app.state.repository
    # A repository-owned source snapshot, not caller-authored analysis nutrition.
    records = repository.list_all("local-demo")
    by_id = {record["id"]: record for record in records}
    by_id[first["id"]]["nutrition"] = {
        "basis_ml": 100., "water_ml": 95., "sodium_mg": 20., "potassium_mg": 10.,
        "carbohydrate_g": None, "provenance": ["test_manufacturer_composition"]}
    by_id[second["id"]]["nutrition"] = {
        "basis_ml": 100., "water_ml": 90., "sodium_mg": 15., "potassium_mg": None,
        "carbohydrate_g": None, "provenance": ["test_second_composition"]}
    # Inject the already reviewed composition at the repository read boundary;
    # the real conversion and existing contribution engine still run.
    from unittest.mock import patch
    with patch.object(repository, "list_all", return_value=list(by_id.values())):
        value = post(client, {"timezone": "UTC"}).json()
    assert value["intake"]["beverage_volume_ml"] == 300
    assert value["intake"]["water_ml"] == 280
    composition = value["intake"]["composition"]
    assert composition["sodium_mg"] == 55
    assert composition["sodium_status"] == "complete"
    assert composition["potassium_mg"] is None
    assert composition["potassium_status"] == "partial"
    assert composition["status"] == "partial"
    assert set(composition["provenance"]) == {"test_manufacturer_composition", "test_second_composition"}


def test_completed_workout_accounting_is_separate_from_daily_intake(client, monkeypatch):
    import backend.hydration_analysis as analysis
    fixed = datetime(2026, 11, 2, 15, tzinfo=timezone.utc)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)
    monkeypatch.setattr(analysis, "datetime", Clock)
    body = payload(fixed)
    body["samples"] = []
    body["exercise"]["starts_at"] = "2026-11-02T13:00:00Z"
    body["exercise"]["duration_minutes"] = 60.
    actual = payload(fixed)["samples"][0]
    actual["event_id"] = body["exercise"]["event_id"]
    actual["observed_at"] = "2026-11-02T14:00:00Z"
    actual["measurement"].update(post_mass_kg=69.6, consumed_ml=300.)
    body["exercise"]["actual"] = actual
    add_log(client, datetime(2026, 11, 2, 13, 30, tzinfo=timezone.utc), 300)
    add_log(client, datetime(2026, 11, 2, 12, tzinfo=timezone.utc), 900)
    value = post(client, body).json()
    assert value["intake"]["beverage_volume_ml"] == 1200
    assert value["numerical_forecast"]["value_ml"] == 700
    assert value["numerical_forecast"]["personalization_status"] == "measured_actual"
    assert value["exercise_accounting"]["logged_beverage_volume_ml"] == 300
    assert value["exercise_accounting"]["value_ml"] == -400
    assert value["wonder"]["preview"] is None


def test_exact_saved_wonder_explanation_replays_and_tampered_text_is_rejected(client, tmp_path):
    from backend.wonder_results import save_result
    from backend.wonder_workout import validate_explanation, workout_result
    body = payload()
    view = post(client, body).json()["wonder"]["preview"]
    facts = view["facts"]
    checked = validate_explanation({
        "summary": "Your planned workout is {planned_workout}.",
        "insights": [{"id": "refine_estimate", "text": "Record {suggested_measurement}."}]}, facts)
    saved = workout_result(facts, checked, account="georgiosaliba227", attempt_id=str(uuid4()),
        observations={"latency_ms": 1, "input_tokens": 1, "output_tokens": 1,
                      "usage_derived_cost_micro_usd": 1, "billed_cost_usd": None},
        generated_at=datetime.now(timezone.utc).isoformat())
    directory = tmp_path / "saved"
    directory.mkdir(mode=0o700)
    path = save_result(directory, saved)
    before = path.read_bytes()
    client.app.state.wonder_results_dir = directory
    value = post(client, body).json()
    assert value["wonder"]["saved"] == saved
    assert value["wonder"]["preview"]["payload_sha256"] == saved["payload_sha256"]
    assert value["wonder"]["provider_called"] is False
    assert value["text_origin"] == "deterministic_local"
    assert value["wonder"]["saved"]["provenance"]["text_origin"] == "muse_wonder_checked"
    assert path.read_bytes() == before  # Replay does not rewrite stored text or request history.
    changed = deepcopy(body)
    changed["exercise"]["duration_minutes"] = 40.
    assert post(client, changed).json()["wonder"]["saved"] is None
    tampered = deepcopy(saved)
    tampered["summary"] = "Drink 5000 mL immediately."
    path.write_text(json.dumps(tampered))
    value = post(client, body).json()
    assert value["wonder"]["saved"] is None
    assert value["wonder"]["reason"] == "saved_result_unavailable"


def test_missing_synthetic_artifact_abstains_without_personal_fallback(client, monkeypatch, tmp_path):
    import ai.forecasting.predict as runtime
    monkeypatch.setattr(runtime, "ARTIFACT_DIR", tmp_path)
    value = post(client, {"timezone": "UTC", "mode": "synthetic_demo"}).json()
    assert value["numerical_forecast"]["status"] == "insufficient_data"
    assert value["numerical_forecast"]["value_ml"] is None
    assert value["intake"]["beverage_volume_ml"] is None
    assert value["wonder"]["preview"] is None

