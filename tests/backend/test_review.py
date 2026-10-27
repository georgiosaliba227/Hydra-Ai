"""Independent integration review: failure recovery, replay and query semantics."""
from concurrent.futures import ThreadPoolExecutor
import asyncio
import json
import sqlite3
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from backend.app import create_app
from database.repository import StorageUnavailable

TOKEN = "synthetic-review-local-token-000000000000"
AUTH = {"Authorization": "Bearer " + TOKEN}


def body(**changes):
    return {"category": "water", "consumed_ml": 125,
            "consumed_at": "2025-10-26T15:00:00Z",
            "timezone": "UTC", "source": "manual", **changes}


@pytest.fixture
def setup(tmp_path):
    path = tmp_path / "review.sqlite3"
    app = create_app(db_path=path, api_token=TOKEN)
    with TestClient(app) as client:
        yield app, client, path


def post(client, data=None, key=None):
    return client.post("/v1/beverages", json=body() if data is None else data,
                       headers=AUTH | {"Idempotency-Key": key or str(uuid4())})


def test_canonical_replay_after_whitespace_and_equivalent_offset(setup):
    _, client, _ = setup
    key = str(uuid4())
    original = post(client, body(category=" water ", consumed_at="2025-10-26T11:00:00-04:00"), key)
    replay = post(client, body(), key)
    assert original.status_code == 201
    assert replay.status_code == 200
    assert replay.json() == original.json()
    assert original.json()["consumed_at"] == "2025-10-26T15:00:00.000000Z"


def test_concurrent_conflicting_api_requests_have_one_winner(setup):
    _, client, _ = setup
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(lambda i: post(client, body(consumed_ml=i + 1), key), range(12)))
    assert sum(r.status_code == 201 for r in responses) == 1
    assert sum(r.status_code == 409 for r in responses) == 11
    winner = next(r.json() for r in responses if r.status_code == 201)
    assert client.get("/v1/beverages", headers=AUTH).json()["items"] == [winner]


def test_atomic_commit_survives_lost_http_response(setup, monkeypatch):
    app, client, path = setup
    original_create = app.state.repository.create
    key = str(uuid4())

    def commit_then_fail(*args, **kwargs):
        original_create(*args, **kwargs)
        raise RuntimeError("simulated transport interruption with private detail")

    monkeypatch.setattr(app.state.repository, "create", commit_then_fail)
    failure = post(client, key=key)
    assert failure.status_code == 500
    assert "private" not in failure.text
    # Restart simulates an ambiguous response; replay must recover the first row.
    with TestClient(create_app(db_path=path, api_token=TOKEN)) as restarted:
        response = post(restarted, key=key)
        assert response.status_code == 200
        saved = restarted.get("/v1/beverages", headers=AUTH).json()["items"]
        assert saved == [response.json()]


def test_storage_failure_is_retryable_and_does_not_echo_path(setup, monkeypatch):
    app, client, _ = setup

    def unavailable(owner):
        raise StorageUnavailable()

    monkeypatch.setattr(app.state.repository, "list_all", unavailable)
    for url in ("/v1/beverages", "/v1/summary?date=2025-10-26&timezone=UTC"):
        response = client.get(url, headers=AUTH)
        assert response.status_code == 503
        data = response.json()
        assert data["code"] == "storage_unavailable" and data["retryable"] is True
        assert response.headers["X-Request-ID"] == data["request_id"]
        assert response.headers["Cache-Control"] == "no-store"
        assert "sqlite" not in response.text


def test_corrupt_database_response_is_not_returned_to_client(setup):
    _, client, path = setup
    post(client)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE beverages SET record_json=?", ("private-malformed-content",))
    response = client.get("/v1/beverages", headers=AUTH)
    assert response.status_code == 503
    assert "private-malformed-content" not in response.text


def test_repository_owner_rows_do_not_leak_via_api(setup):
    app, client, _ = setup
    saved = post(client).json()
    other = {**saved, "id": str(uuid4()), "consumed_ml": 5000}
    app.state.repository.create("another-owner", "another-key", "another-fingerprint", other)
    assert client.get("/v1/beverages", headers=AUTH).json()["items"] == [saved]
    summary = client.get("/v1/summary?date=2025-10-26&timezone=UTC", headers=AUTH).json()
    assert summary["beverage_total_ml"] == 125


def test_tied_timestamps_paginate_without_duplicates_or_omissions(setup):
    _, client, _ = setup
    saved = [post(client).json() for _ in range(9)]
    expected_ids = sorted([r["id"] for r in saved], reverse=True)
    ids, cursor = [], None
    while True:
        params = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        response = client.get("/v1/beverages", params=params, headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        ids.extend(r["id"] for r in data["items"])
        cursor = data["next_cursor"]
        if cursor is None:
            break
    assert ids == expected_ids


@pytest.mark.parametrize("timezone_name,date_value,instants,expected", [
    ("Australia/Lord_Howe", "2025-04-06", [
        "2025-04-05T12:59:59Z", "2025-04-05T13:00:00Z",
        "2025-04-05T14:45:00Z", "2025-04-05T15:15:00Z",
        "2025-04-06T13:29:59Z", "2025-04-06T13:30:00Z"], 500),
    ("Pacific/Apia", "2011-12-30", [
        "2011-12-30T09:59:59Z", "2011-12-30T10:00:00Z"], 0),
])
def test_non_hour_dst_and_skipped_calendar_date(setup, timezone_name, date_value, instants, expected):
    _, client, _ = setup
    for instant in instants:
        assert post(client, body(consumed_at=instant)).status_code == 201
    result = client.get("/v1/summary", params={"date": date_value, "timezone": timezone_name}, headers=AUTH)
    assert result.status_code == 200
    assert result.json()["beverage_total_ml"] == expected


@pytest.mark.parametrize("content", [
    '{"consumed_ml":NaN}',
    '{"consumed_ml":Infinity}',
    'null',
    '[]',
])
def test_nonobject_and_nonfinite_json_fails_without_persistence(setup, content):
    _, client, _ = setup
    result = client.post("/v1/beverages", content=content,
                         headers=AUTH | {"Idempotency-Key": str(uuid4()), "Content-Type": "application/json"})
    assert result.status_code == 422
    assert client.get("/v1/beverages", headers=AUTH).json()["items"] == []


def test_chunked_body_limit_without_content_length(setup):
    app, _, _ = setup

    async def request():
        sent = []
        incoming = iter([
            {"type": "http.request", "body": b"x" * 9000, "more_body": True},
            {"type": "http.request", "body": b"y" * 9000, "more_body": False},
        ])
        async def receive():
            return next(incoming)
        async def send(message):
            sent.append(message)
        await app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                   "method": "POST", "scheme": "http", "path": "/v1/beverages",
                   "raw_path": b"/v1/beverages", "query_string": b"", "root_path": "",
                   "headers": [(b"authorization", ("Bearer " + TOKEN).encode())],
                   "client": ("127.0.0.1", 1111), "server": ("127.0.0.1", 8000)}, receive, send)
        return sent

    messages = asyncio.run(request())
    assert messages[0]["status"] == 413
    assert json.loads(messages[1]["body"])["code"] == "request_too_large"
