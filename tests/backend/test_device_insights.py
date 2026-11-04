"""Ephemeral phone summaries: synthetic in-process requests, no stored history or network."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import logging
import os
import socket

import pytest
from fastapi.testclient import TestClient

from ai.assistant import ANSWERS
from backend.app import create_app
from backend.wonder_trends import build_facts, validate_facts

TOKEN = "synthetic-device-insights-test-token-000000"
AUTH = {"Authorization": "Bearer " + TOKEN}
BASE = "/v1/device-insights"


class ForbiddenAccess:
    def __getattr__(self, name):
        pytest.fail("Ephemeral insights accessed saved state or a provider: " + name)


@pytest.fixture
def client(tmp_path, monkeypatch):
    for name in tuple(os.environ):
        if name.startswith(("HYDRA_", "META_")) or name == "MODEL_API_KEY":
            monkeypatch.delenv(name)
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("Network forbidden"))
    app = create_app(db_path=tmp_path / "synthetic.sqlite3", api_token=TOKEN)
    for name in ("repository", "meta_ledger", "recognizer", "hydration_service", "wonder_trends_gateway"):
        setattr(app.state, name, ForbiddenAccess())
    with TestClient(app) as client:
        yield client


def trend_body():
    start = date(2026, 10, 15)
    days = [{"date": (start + timedelta(days=i)).isoformat(), "total_ml": 0, "drinks": 0} for i in range(14)]
    for i, volume, count in ((0, 500, 2), (7, 1000, 1), (13, 500, 1)):
        days[i].update(total_ml=volume, drinks=count)
    return {"version": "device-insights-v1", "source": "on_device_summary", "consent_to_process": True,
            "timezone": "UTC", "through_date": "2026-10-28", "days": days, "goal_ml": 900,
            "categories": [{"category": "coffee", "total_ml": 100}, {"category": "water", "total_ml": 1900}],
            "time_of_day_ml": {"morning_ml": 100, "afternoon_ml": 400, "evening_ml": 1000, "night_ml": 500}}


def assistant_body(**request):
    return {"version": "device-insights-v1", "source": "on_device_summary", "consent_to_process": True,
            "request": {"question_id": "coffee_counts"} | request}


def set_path(body, path, value):
    for key in path[:-1]:
        body = body[key]
    body[path[-1]] = value


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/capabilities", None), ("POST", "/trends", trend_body()),
    ("POST", "/assistant", assistant_body()),
])
def test_every_device_insights_route_requires_owner_auth(client, method, path, body):
    assert client.request(method, BASE + path, json=body).status_code == 401


def test_capabilities_are_authenticated_and_explicitly_nonbillable(client):
    response = client.get(BASE + "/capabilities", headers=AUTH)
    assert response.status_code == 200
    assert response.json() == {"version": "device-insights-v1", "history_source": "on_device_summary",
                               "max_days": 14, "provider_dispatch": False}
    assert response.headers["cache-control"] == "no-store"


def test_aggregate_facts_match_existing_engine_without_creating_fake_records(client):
    response = client.post(BASE + "/trends", headers=AUTH, json=trend_body())
    assert response.status_code == 200
    # Independent synthetic events establish parity; production receives aggregates only.
    records = [{"consumed_at": at, "category": category, "consumed_ml": volume} for at, category, volume in (
        ("2026-10-15T08:00:00Z", "coffee", 100), ("2026-10-15T13:00:00Z", "water", 400),
        ("2026-10-22T18:00:00Z", "water", 1000), ("2026-10-28T23:00:00Z", "water", 500))]
    result = response.json()
    expected = build_facts(records, 900, "UTC", date(2026, 10, 28))
    assert result["facts"] == expected == validate_facts(result["facts"])
    canonical = json.dumps(expected, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    assert result["payload_sha256"] == hashlib.sha256(canonical.encode()).hexdigest()
    assert result["version"] == "device-insights-v1" and result["source"] == "on_device_summary"
    assert result["provenance"] == {"mode": "deterministic", "provider": None, "model": None,
                                    "history_source": "on_device_summary", "storage": "ephemeral"}
    assert "2000" in result["summary"]
    assert 1 <= len(result["insights"]) <= 3
    assert all(item["id"] in expected["applicable_insights"] for item in result["insights"])
    assert all(set(item) == {"id", "title", "text"} for item in result["insights"])


def test_canonical_digest_ignores_input_order_and_categories_tie_by_name(client):
    body = trend_body()
    body["categories"] = [{"category": "water", "total_ml": 1000}, {"category": "coffee", "total_ml": 1000}]
    first = client.post(BASE + "/trends", headers=AUTH, json=body)
    assert first.status_code == 200
    body["days"].reverse(); body["categories"].reverse()
    second = client.post(BASE + "/trends", headers=AUTH, json=body)
    assert first.json() == second.json()
    assert [item["category"] for item in second.json()["facts"]["categories"]] == ["coffee", "water"]


def test_empty_history_returns_no_records_summary_without_falling_back_to_server(client):
    body = trend_body()
    for day in body["days"]:
        day.update(total_ml=0, drinks=0)
    body.update(goal_ml=None, categories=[], time_of_day_ml={name: 0 for name in body["time_of_day_ml"]})
    response = client.post(BASE + "/trends", headers=AUTH, json=body)
    assert response.status_code == 200
    result = response.json()
    assert result["insights"] == [] and "no drinks" in result["summary"].lower()
    assert result["facts"]["last_7_days"]["total_ml"] == 0
    assert result["facts"]["applicable_insights"] == []
    assert len(result["payload_sha256"]) == 64


@pytest.mark.parametrize("path,value", [
    (("version",), "other"), (("source",), "server_history"), (("consent_to_process",), False),
    (("consent_to_process",), 1), (("consent_to_process",), "true"),
    (("days", 0, "total_ml"), 500.0), (("days", 0, "total_ml"), "500"),
    (("days", 1, "total_ml"), False), (("days", 0, "total_ml"), -1),
    (("days", 0, "total_ml"), 1_000_000_001), (("days", 0, "drinks"), 2.0),
    (("days", 1, "drinks"), False), (("days", 0, "drinks"), 1001), (("days", 0, "drinks"), -1),
    (("days", 0, "drinks"), 0), (("days", 1, "drinks"), 1),
    (("categories", 0, "total_ml"), 100.0), (("categories", 0, "total_ml"), 0),
    (("categories", 0, "category"), "a private brand"), (("categories", 0, "category"), "energy_drink"),
    (("time_of_day_ml", "morning_ml"), 100.0), (("time_of_day_ml", "morning_ml"), "100"),
    (("goal_ml",), 900.0), (("goal_ml",), True), (("goal_ml",), 99), (("goal_ml",), 10001),
    (("timezone",), "Mars/Base"), (("through_date",), "2026-02-30"),
    (("through_date",), "9999-12-31"), (("through_date",), "2026-10-27"),
    (("days", 0, "date"), "2026-02-30"), (("days", 0, "date"), "2026-10-16"),
    (("categories", 0, "total_ml"), 101), (("time_of_day_ml", "morning_ml"), 101),
    (("photo_base64",), "private-photo-marker"), (("profile",), {"weight_kg": 75}),
    (("healthkit",), {"steps": 5000}), (("token",), "private-token-marker"),
    (("days", 0, "consumed_at"), "private-timestamp-marker"),
    (("categories", 0, "brand"), "private-brand-marker"), (("time_of_day_ml", "extra"), 0),
])
def test_trends_rejects_invalid_private_or_inconsistent_fields(client, path, value):
    body = trend_body(); set_path(body, path, value)
    response = client.post(BASE + "/trends", headers=AUTH, json=body)
    assert response.status_code == 422
    assert "private-" not in response.text


@pytest.mark.parametrize("change", [
    lambda body: body.pop("consent_to_process"), lambda body: body.update(days=body["days"][:-1]),
    lambda body: body["days"].append(body["days"][0]),
    lambda body: body["categories"].append(deepcopy(body["categories"][0])),
    lambda body: body.update(categories=[{"category": "water", "total_ml": 1}] * 13),
    lambda body: body["days"][0].pop("drinks"), lambda body: body["time_of_day_ml"].pop("night_ml"),
])
def test_missing_consent_and_incomplete_or_duplicate_collections_are_rejected(client, change):
    body = trend_body(); change(body)
    assert client.post(BASE + "/trends", headers=AUTH, json=body).status_code == 422


def test_total_window_bound_is_enforced_even_when_buckets_are_individually_valid(client):
    body = trend_body()
    for day in body["days"]:
        day.update(total_ml=100_000_000, drinks=1)
    body["categories"] = [{"category": "water", "total_ml": 700_000_000}, {"category": "other", "total_ml": 700_000_000}]
    body["time_of_day_ml"] = {name: 350_000_000 for name in body["time_of_day_ml"]}
    assert client.post(BASE + "/trends", headers=AUTH, json=body).status_code == 422


def one_drink_body(volume=1):
    body = trend_body()
    for day in body["days"]:
        day.update(total_ml=0, drinks=0)
    body["days"][-1].update(total_ml=volume, drinks=1)
    body["categories"] = [{"category": "water", "total_ml": volume}]
    body["time_of_day_ml"] = {name: 0 for name in body["time_of_day_ml"]}
    body["time_of_day_ml"]["afternoon_ml"] = volume
    return body


def test_maximum_conserved_window_volume_is_accepted(client):
    response = client.post(BASE + "/trends", headers=AUTH, json=one_drink_body(1_000_000_000))
    assert response.status_code == 200
    assert response.json()["facts"]["last_7_days"]["total_ml"] == 1_000_000_000


@pytest.mark.parametrize("path", [("days", 13, "total_ml"), ("days", 13, "drinks"),
                                  ("categories", 0, "total_ml"), ("time_of_day_ml", "afternoon_ml")])
@pytest.mark.parametrize("value", [True, 1.0, "1"])
def test_nonstrict_ones_are_rejected_even_when_all_totals_would_still_conserve(client, path, value):
    body = one_drink_body(); set_path(body, path, value)
    assert client.post(BASE + "/trends", headers=AUTH, json=body).status_code == 422


@pytest.mark.parametrize("zone,status", [("Pacific/Kiritimati", 200), ("America/Adak", 422)])
def test_future_window_uses_requested_timezone_instead_of_server_calendar(client, monkeypatch, zone, status):
    from backend import device_insights

    instant = datetime(2026, 11, 4, 12, 30, tzinfo=timezone.utc)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

    monkeypatch.setattr(device_insights, "datetime", FixedDatetime)
    body = one_drink_body()
    body.update(timezone=zone, through_date="2026-11-05")
    for i, day in enumerate(body["days"]):
        day["date"] = (date(2026, 10, 23) + timedelta(days=i)).isoformat()
    assert client.post(BASE + "/trends", headers=AUTH, json=body).status_code == status


@pytest.mark.parametrize("total", [0, 1_000_000_000])
def test_assistant_returns_phone_context_and_reviewed_answers_only(client, total):
    body = assistant_body(context_scope="today_logged_total", date="2026-10-28", timezone="UTC")
    body["today_logged_total_ml"] = total
    response = client.post(BASE + "/assistant", headers=AUTH, json=body)
    assert response.status_code == 200
    answer = response.json()
    assert answer["version"] == "assistant-v1" and answer["topics"] == ["coffee_caffeine"]
    assert answer["answers"][0]["text"] == ANSWERS["coffee_caffeine"].text
    assert answer["provenance"] == {"mode": "local_rules", "provider": None, "model": None, "answer_origin": "reviewed_text"}
    assert answer["intake_context"]["beverage_total_ml"] == total
    assert "iphone" in answer["intake_context"]["note"].lower()
    assert "not a hydration measurement" in answer["intake_context"]["note"].lower()


def test_assistant_no_context_accepts_omitted_or_null_total_and_escalates_urgent_text(client):
    body = assistant_body(); body["request"] = {"question": "I fainted after running"}
    for include_null in (False, True):
        if include_null: body["today_logged_total_ml"] = None
        response = client.post(BASE + "/assistant", headers=AUTH, json=body)
        assert response.status_code == 200
        answer = response.json()
        assert answer["topics"][0] == "urgent" and answer["escalation"] is True
        assert answer["intake_context"] is None


@pytest.mark.parametrize("path,value", [
    (("consent_to_process",), False), (("consent_to_process",), 1),
    (("request", "source"), "recorded_wonder"), (("request", "source"), "meta_live"),
    (("request", "question_id"), "made_up"), (("request", "question"), "coffee?"),
    (("request", "heart_rate"), 80), (("request", "profile"), {"age": 30}),
    (("profile",), {"weight_kg": 70}), (("today_logged_total_ml",), 250),
    (("request", "date"), "2026-10-28"), (("request", "timezone"), "UTC"),
])
def test_assistant_rejects_provider_source_private_fields_and_unconsented_context(client, path, value):
    body = assistant_body(); set_path(body, path, value)
    assert client.post(BASE + "/assistant", headers=AUTH, json=body).status_code == 422


@pytest.mark.parametrize("total", [None, True, False, 250.0, "250", -1, 1_000_000_001])
def test_assistant_context_requires_a_strict_bounded_integer(client, total):
    body = assistant_body(context_scope="today_logged_total", date="2026-10-28", timezone="UTC")
    body["today_logged_total_ml"] = total
    assert client.post(BASE + "/assistant", headers=AUTH, json=body).status_code == 422


@pytest.mark.parametrize("changes", [
    {"date": "2026-02-30"}, {"date": "2026-2-03"}, {"timezone": "Mars/Base"},
])
def test_assistant_context_date_and_timezone_must_be_real(client, changes):
    body = assistant_body(context_scope="today_logged_total", date="2026-10-28", timezone="UTC")
    body["request"].update(changes); body["today_logged_total_ml"] = 250
    assert client.post(BASE + "/assistant", headers=AUTH, json=body).status_code == 422


def test_ephemeral_requests_never_persist_or_log_question_and_oversized_body_is_refused(client, tmp_path, caplog):
    before = {str(path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    body = assistant_body(); body["request"] = {"question": "coffee private-question-marker"}
    with caplog.at_level(logging.DEBUG):
        assert client.post(BASE + "/trends", headers=AUTH, json=trend_body()).status_code == 200
        response = client.post(BASE + "/assistant", headers=AUTH, json=body)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert "private-question-marker" not in caplog.text
    assert {str(path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before
    assert client.post(BASE + "/trends", headers=AUTH, content=b" " * 16_385).status_code == 413
