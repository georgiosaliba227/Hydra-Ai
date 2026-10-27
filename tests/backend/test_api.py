"""Real repository + engine + HTTP boundary tests; no external services."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import socket
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app

TOKEN = 'test-only-local-development-token-00000000'
AUTH = {'Authorization': f'Bearer {TOKEN}'}


def payload(**changes):
    data = dict(category='coffee', consumed_ml=250, consumed_at='2025-10-26T15:00:00Z',
                timezone='America/New_York', source='manual')
    return data | changes


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path / 'test.sqlite3'), api_token=TOKEN)) as c:
        yield c


def post(client, data=None, key=None):
    return client.post('/v1/beverages', json=data or payload(),
                       headers=AUTH | {'Idempotency-Key': key or str(uuid4())})


def summary(client, date='2025-10-26', zone='America/New_York'):
    return client.get('/v1/summary', params={'date': date, 'timezone': zone}, headers=AUTH)


def test_round_trip_uses_engine_and_preserves_unknown_composition(client):
    response = post(client)
    assert response.status_code == 201, response.text
    log = response.json()
    assert log['contribution']['beverage_total_ml'] == 250
    assert log['contribution']['estimated_water_ml'] is None
    assert log['nutrition'] is None
    assert log['revision'] == 1
    assert client.get('/v1/beverages', headers=AUTH).json()['items'] == [log]
    result = summary(client).json()
    assert result['beverage_total_ml'] == 250
    assert result['estimated_water_ml'] is None
    assert result['forecast_status'] == 'insufficient_data'
    assert result['method_version'] == 'hydration-accounting-v1'
    assert 'water_content_unknown' in result['uncertainty_reasons']


def test_restart_replay_and_conflict(tmp_path):
    path = str(tmp_path / 'persist.sqlite3')
    key = str(uuid4())
    with TestClient(create_app(db_path=path, api_token=TOKEN)) as first:
        saved = post(first, key=key).json()
    with TestClient(create_app(db_path=path, api_token=TOKEN)) as second:
        replay = post(second, key=key)
        assert replay.status_code == 200
        assert replay.json() == saved
        conflict = post(second, payload(consumed_ml=300), key=key)
        assert conflict.status_code == 409
        assert conflict.json()['code'] == 'idempotency_conflict'
        assert len(second.get('/v1/beverages', headers=AUTH).json()['items']) == 1
        assert summary(second).json()['beverage_total_ml'] == 250


def test_simultaneous_duplicate_creates_one_record(client):
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=8) as pool:
        replies = list(pool.map(lambda _: post(client, key=key), range(12)))
    assert [r.status_code for r in replies].count(201) == 1
    assert all(r.status_code in (200, 201) for r in replies)
    assert len({r.json()['id'] for r in replies}) == 1
    assert summary(client).json()['beverage_total_ml'] == 250


@pytest.mark.parametrize('change', [
    {'consumed_ml': 0}, {'consumed_ml': -1}, {'consumed_ml': 5001},
    {'consumed_ml': True}, {'consumed_ml': '250'}, {'consumed_ml': 1.5},
    {'category': ''}, {'category': '   '}, {'category': 'x' * 81},
    {'timezone': 'no/such_timezone'}, {'consumed_at': '2025-01-01T12:00:00'},
    {'consumed_at': '1999-12-31T23:59:59Z'},
    {'consumed_at': (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()},
    {'source': 'confirmed_recognition'}, {'user_id': 'other'},
    {'nutrition': {'water_ml': 250}}, {'consumed_at': 1700000000},
])
def test_invalid_request_never_persists(client, change):
    response = post(client, payload(**change))
    assert response.status_code == 422, response.text
    assert set(response.json()) == {'code', 'message', 'request_id', 'retryable'}
    assert client.get('/v1/beverages', headers=AUTH).json()['items'] == []


def test_auth_and_invalid_idempotency(client):
    for path in ['/v1/beverages', '/v1/summary?date=2025-10-26&timezone=UTC']:
        assert client.get(path).status_code == 401
        assert client.get(path, headers={'Authorization': 'Bearer wrong'}).status_code == 401
    assert client.post('/v1/beverages', json=payload()).status_code == 401
    for key in ['', 'not-uuid']:
        r = client.post('/v1/beverages', json=payload(), headers=AUTH | {'Idempotency-Key': key})
        assert r.status_code == 422


@pytest.mark.parametrize('date,instants,expected', [
    ('2025-03-09', ['2025-03-09T04:59:59Z', '2025-03-09T05:00:00Z',
                    '2025-03-10T03:59:59Z', '2025-03-10T04:00:00Z'], 500),
    ('2025-11-02', ['2025-11-02T03:59:59Z', '2025-11-02T04:00:00Z',
                    '2025-11-02T05:30:00Z', '2025-11-02T06:30:00Z',
                    '2025-11-03T04:59:59Z', '2025-11-03T05:00:00Z'], 1000),
])
def test_new_york_dst_calendar_boundaries(client, date, instants, expected):
    for instant in instants:
        assert post(client, payload(consumed_at=instant)).status_code == 201
    assert summary(client, date).json()['beverage_total_ml'] == expected


def test_requested_timezone_controls_date_not_log_timezone(client):
    post(client, payload(consumed_at='2025-10-26T02:00:00Z', timezone='Asia/Tokyo'))
    assert summary(client, zone='UTC').json()['beverage_total_ml'] == 250
    assert summary(client).json()['beverage_total_ml'] == 0
    assert summary(client, '2025-10-25').json()['beverage_total_ml'] == 250


def test_pagination_and_summary_do_not_use_only_first_page(client):
    for i in range(5):
        assert post(client, payload(consumed_ml=100, consumed_at=f'2025-10-26T1{i}:00:00Z')).status_code == 201
    first = client.get('/v1/beverages', params={'limit': 2}, headers=AUTH).json()
    assert len(first['items']) == 2 and first['next_cursor']
    # A newer concurrent insert must not shift the older-page boundary.
    post(client, payload(consumed_ml=100, consumed_at='2025-10-26T20:00:00Z'))
    ids = [x['id'] for x in first['items']]
    cursor = first['next_cursor']
    while cursor:
        page = client.get('/v1/beverages', params={'limit': 2, 'cursor': cursor}, headers=AUTH).json()
        ids += [x['id'] for x in page['items']]
        cursor = page['next_cursor']
    assert len(ids) == len(set(ids)) == 5
    assert summary(client).json()['beverage_total_ml'] == 600


@pytest.mark.parametrize('path', [
    '/v1/summary?date=bad&timezone=UTC', '/v1/summary?date=2025-10-26&timezone=bad',
    '/v1/beverages?limit=0', '/v1/beverages?limit=201', '/v1/beverages?cursor=bad',
])
def test_bad_query(client, path):
    r = client.get(path, headers=AUTH)
    assert r.status_code == 422
    assert r.json()['code'] == 'invalid_request'


def test_large_and_malformed_bodies(client):
    r = client.post('/v1/beverages', content='x' * 17000, headers=AUTH | {'Content-Type': 'application/json'})
    assert r.status_code in (413, 422)
    r = client.post('/v1/beverages', content='{"secret":"do-not-echo",', headers=AUTH | {'Content-Type': 'application/json'})
    assert r.status_code == 422
    assert 'do-not-echo' not in r.text


def test_ai_disabled_and_no_outbound_connections(client, monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('Outbound network forbidden')
    monkeypatch.setattr(socket.socket, 'connect', denied)
    assert post(client).status_code == 201
    assert summary(client).status_code == 200
    health = client.get('/health').json()
    assert health['ai_mode'] == 'mock'
    assert health['billable_requests_enabled'] is False
    assert client.post('/v1/assistant', json={'question': 'hello'}, headers=AUTH).status_code == 404


@pytest.mark.parametrize('name,value', [('META_BILLABLE_REQUESTS_ENABLED','true'), ('HYDRA_AI_MODE','live')])
def test_startup_rejects_billable_configuration(tmp_path, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises((ValueError, RuntimeError)):
        create_app(db_path=str(tmp_path / 'disabled.sqlite3'), api_token=TOKEN)


def test_startup_requires_strong_local_credential(tmp_path, monkeypatch):
    monkeypatch.delenv('HYDRA_API_TOKEN', raising=False)
    for token in (None, '', 'short'):
        with pytest.raises((ValueError, RuntimeError)):
            create_app(db_path=str(tmp_path / 'token.sqlite3'), api_token=token)
