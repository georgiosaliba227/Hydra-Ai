"""Mock-first HTTP, privacy, correction and deterministic-accounting coverage."""
import base64
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.recognition import AnalysisRequest, meta_request
from backend.nutrition import IDENTITY, PRODUCT_ID

TOKEN = "test-development-session-token-0000000000"
AUTH = {"Authorization": "Bearer " + TOKEN}
# Minimal JPEG envelope with SOF dimensions; the mock deliberately never decodes pixels.
JPEG = b"\xff\xd8\xff\xc0\x00\x0b\x08\x00\x10\x00\x10\x01\x01\x11\x00\xff\xd9"
IMAGE = base64.b64encode(JPEG).decode()


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "beverages.sqlite3", TOKEN)) as c:
        yield c


def analysis(**changes):
    return {"image_base64": IMAGE, "photo_consent": True, "mock_scenario": "branded"} | changes


def confirmed(**changes):
    return dict(category=IDENTITY, consumed_ml=150, container_ml=355, product_id=PRODUCT_ID,
                consumed_at="2026-10-26T15:00:00Z", timezone="America/New_York", source="confirmed_recognition") | changes


def test_analysis_auth_consent_and_privacy(client, tmp_path, caplog):
    assert client.post("/v1/recognitions", json=analysis()).status_code == 401
    for bad in [False, 1, "true", None]:
        assert client.post("/v1/recognitions", json=analysis(photo_consent=bad), headers=AUTH).status_code == 422
    response = client.post("/v1/recognitions", json=analysis(), headers=AUTH)
    assert response.status_code == 200
    assert response.json()["mode"] == "mock"
    assert response.json()["requires_confirmation"] is True
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/v1/beverages", headers=AUTH).json()["items"] == []
    for path in tmp_path.iterdir():
        assert IMAGE.encode() not in path.read_bytes()
        assert JPEG not in path.read_bytes()
    assert IMAGE not in caplog.text and TOKEN not in caplog.text


@pytest.mark.parametrize("scenario,count", [("branded",1),("generic",1),("ambiguous",0),("missing_nutrition",1)])
def test_scenarios(client, scenario, count):
    result = client.post("/v1/recognitions", json=analysis(mock_scenario=scenario), headers=AUTH).json()
    assert len(result["candidates"]) == count
    for item in result["candidates"]:
        assert item["uncertainty_reasons"] and item["confidence"] in ("low", "medium", "high")


@pytest.mark.parametrize("changes", [{"image_base64":"not base64"},{"image_base64":base64.b64encode(b"not an image").decode()},
    {"image_base64":base64.b64encode(JPEG[:9]+b"\xff\xff"+JPEG[11:]).decode()},
    {"image_base64":base64.b64encode(b"x"*1_048_577).decode()}, {"image_url":"http://private"},
    {"health_records":[1]}, {"mock_scenario":"live"}])
def test_rejects_unbounded_or_private_inputs(client, changes):
    response = client.post("/v1/recognitions", json=analysis(**changes), headers=AUTH)
    assert response.status_code in (413,422)
    assert IMAGE not in response.text


def test_api_failure_is_sanitized_and_retry_does_not_log(client):
    for _ in range(2):
        r = client.post("/v1/recognitions", json=analysis(mock_scenario="failure"), headers=AUTH)
        assert r.status_code == 503 and r.json()["retryable"]
    assert client.get("/v1/beverages", headers=AUTH).json()["items"] == []


def test_confirmation_replay_nutrition_and_summary(client):
    key = str(uuid4()); headers = AUTH | {"Idempotency-Key":key}
    r = client.post("/v1/beverages", json=confirmed(), headers=headers)
    assert r.status_code == 201, r.text
    record = r.json()
    assert record["nutrition"]["sodium_mg"] == 45
    assert record["nutrition"]["carbohydrate_g"] == 39
    assert "coca-cola.com" in record["nutrition"]["provenance"][0]
    assert record["contribution"]["estimated_water_ml"] is None
    assert record["contribution"]["beverage_total_ml"] == 150
    assert record["contribution"]["sodium_mg"] == pytest.approx(45 * 150 / (12 * 29.5735295625))
    assert client.post("/v1/beverages", json=confirmed(), headers=headers).json() == record
    assert client.post("/v1/beverages", json=confirmed(container_ml=500), headers=headers).status_code == 409
    summary = client.get("/v1/summary?date=2026-10-26&timezone=America/New_York", headers=AUTH).json()
    assert summary["beverage_total_ml"] == 150
    assert summary["estimated_water_ml"] is None


@pytest.mark.parametrize("changes", [{"category":"Tea"},{"product_id":"fake"},{"container_ml":None},
    {"consumed_ml":356},{"container_ml":True},{"source":"manual"},{"nutrition":{"water_ml":150}}])
def test_invalid_confirmation(client, changes):
    r = client.post("/v1/beverages", json=confirmed(**changes), headers=AUTH | {"Idempotency-Key":str(uuid4())})
    assert r.status_code == 422


def test_corrected_generic_has_no_stale_nutrition(client):
    r = client.post("/v1/beverages", json=confirmed(category="Tea",product_id=None), headers=AUTH | {"Idempotency-Key":str(uuid4())})
    assert r.status_code == 201
    assert r.json()["nutrition"] is None


def test_offline_payload_has_only_meta_image_and_bounded_output():
    result = meta_request(AnalysisRequest(**analysis()))
    assert result["model"] == "muse-spark-1.3"
    assert result["max_output_tokens"] == 512 and result["store"] is False
    assert "tools" not in result
    assert result["input"][0]["content"][1]["image_url"].startswith("data:image/jpeg;base64,")


def test_milestone_one_pending_fingerprint_remains_compatible(client):
    import hashlib
    import json
    from backend.schemas import CreateBeverageRequest, utc_string
    old = dict(category="water", consumed_ml=250, consumed_at="2026-10-26T15:00:00Z", timezone="America/New_York", source="manual")
    canonical = old | {"consumed_at": utc_string(CreateBeverageRequest(**old).consumed_at)}
    fingerprint = hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    key = str(uuid4())
    record = canonical | {"id":str(uuid4()),"revision":1,"provenance":["user_confirmed_manual"],"nutrition":None,"contribution":{}}
    client.app.state.repository.create("local-demo",key,fingerprint,record)
    replay = client.post("/v1/beverages",json=old,headers=AUTH | {"Idempotency-Key":key})
    assert replay.status_code == 200 and replay.json() == record


def test_malformed_adapter_output_fails_safely(client):
    class BadAdapter:
        def analyze(self, payload):
            return {"candidates":[{"identity":"Coffee","confidence":"certain","uncertainty_reasons":[]}]}
    client.app.state.recognizer = BadAdapter()
    response = client.post("/v1/recognitions",json=analysis(),headers=AUTH)
    assert response.status_code == 503
    assert "Coffee" not in response.text
