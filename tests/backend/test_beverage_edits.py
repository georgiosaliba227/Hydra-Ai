"""Correcting and deleting confirmed beverage logs; real repository and engine, no network."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.nutrition import IDENTITY, PRODUCT_ID

TOKEN = 'test-only-local-development-token-00000000'
AUTH = {'Authorization': f'Bearer {TOKEN}'}


def manual(**changes):
    return dict(category='coffee', consumed_ml=250, consumed_at='2025-10-26T15:00:00Z',
                timezone='America/New_York', source='manual') | changes


def photo(**changes):
    return dict(category=IDENTITY, consumed_ml=150, container_ml=355, product_id=PRODUCT_ID,
                consumed_at='2026-10-26T15:00:00Z', timezone='America/New_York',
                source='confirmed_recognition') | changes


@pytest.fixture
def database(tmp_path):
    return str(tmp_path / 'test.sqlite3')


@pytest.fixture
def client(database):
    with TestClient(create_app(db_path=database, api_token=TOKEN)) as c:
        yield c


def create(client, data=None, key=None):
    response = client.post('/v1/beverages', json=data or manual(),
                           headers=AUTH | {'Idempotency-Key': key or str(uuid4())})
    assert response.status_code == 201, response.text
    return response.json()


def patch(client, log, **changes):
    return client.patch(f"/v1/beverages/{log['id']}", json={'revision': log['revision']} | changes, headers=AUTH)


def total(client, date='2025-10-26'):
    return client.get('/v1/summary', params={'date': date, 'timezone': 'America/New_York'},
                      headers=AUTH).json()['beverage_total_ml']


def test_correction_advances_revision_recalculates_and_updates_summary(client):
    log = create(client)
    response = patch(client, log, consumed_ml=400, category='Iced coffee')
    assert response.status_code == 200, response.text
    updated = response.json()
    assert (updated['id'], updated['revision'], updated['consumed_ml'], updated['category']) == (log['id'], 2, 400, 'Iced coffee')
    assert updated['contribution']['beverage_total_ml'] == 400
    assert updated['provenance'] == ['user_confirmed_manual', 'user_corrected']
    assert client.get('/v1/beverages', headers=AUTH).json()['items'] == [updated]
    assert total(client) == 400


def test_moving_a_log_to_another_day_moves_it_between_summaries(client):
    log = create(client)
    moved = patch(client, log, consumed_at='2025-10-25T15:00:00-04:00').json()
    assert moved['consumed_at'] == '2025-10-25T19:00:00.000000Z'
    assert total(client) == 0 and total(client, '2025-10-25') == 250


def test_stale_revision_is_rejected_but_an_applied_retry_replays(client):
    log = create(client)
    first = patch(client, log, consumed_ml=300)
    assert first.status_code == 200
    assert patch(client, log, consumed_ml=300).json() == first.json()  # lost-response retry
    conflict = patch(client, log, consumed_ml=350)
    assert conflict.status_code == 409 and conflict.json()['code'] == 'revision_conflict'
    assert client.get('/v1/beverages', headers=AUTH).json()['items'][0]['consumed_ml'] == 300


def test_concurrent_corrections_of_one_revision_admit_exactly_one(client):
    log = create(client)
    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = sorted(pool.map(lambda ml: patch(client, log, consumed_ml=ml).status_code, range(300, 308)))
    assert statuses == [200] + [409] * 7
    assert client.get('/v1/beverages', headers=AUTH).json()['items'][0]['revision'] == 2


@pytest.mark.parametrize('body', [
    {}, {'consumed_ml': None}, {'category': '   '}, {'consumed_ml': 0}, {'consumed_ml': 5001},
    {'consumed_ml': 1.5}, {'consumed_at': '2025-10-26 15:00'}, {'consumed_at': '2999-01-01T00:00:00Z'},
    {'timezone': 'Mars/Base'}, {'source': 'confirmed_recognition'}, {'nutrition': {'sodium_mg': 1}},
    {'id': str(uuid4())}, {'revision': 2, 'consumed_ml': 300},
])
def test_invalid_corrections_change_nothing(client, body):
    log = create(client)
    response = client.patch(f"/v1/beverages/{log['id']}", json={'revision': 1} | body, headers=AUTH)
    assert response.status_code in (409, 422)
    assert client.get('/v1/beverages', headers=AUTH).json()['items'] == [log]


def test_photo_confirmed_log_keeps_product_identity_and_container_bound(client):
    log = create(client, photo())
    assert patch(client, log, category='Water').status_code == 422
    assert patch(client, log, consumed_ml=400).status_code == 422  # exceeds the 355 mL container
    updated = patch(client, log, consumed_ml=355).json()
    assert updated['category'] == IDENTITY and updated['nutrition'] == log['nutrition']
    assert updated['contribution']['beverage_total_ml'] == 355
    assert updated['provenance'][-1] == 'user_corrected'


def test_delete_removes_log_from_history_and_summary(client):
    keep, gone = create(client), create(client, manual(consumed_ml=100))
    assert total(client) == 350
    response = client.delete(f"/v1/beverages/{gone['id']}", headers=AUTH)
    assert response.status_code == 204 and response.content == b''
    assert client.get('/v1/beverages', headers=AUTH).json()['items'] == [keep]
    assert total(client) == 250
    again = client.delete(f"/v1/beverages/{gone['id']}", headers=AUTH)
    assert again.status_code == 404 and again.json()['code'] == 'not_found'
    assert patch(client, gone, consumed_ml=10).status_code == 404


def test_deleted_log_cannot_be_resurrected_by_a_late_create_retry(client):
    key = str(uuid4())
    log = create(client, key=key)
    client.delete(f"/v1/beverages/{log['id']}", headers=AUTH)
    retry = client.post('/v1/beverages', json=manual(), headers=AUTH | {'Idempotency-Key': key})
    assert retry.status_code == 409 and retry.json()['code'] == 'idempotency_conflict'
    assert client.get('/v1/beverages', headers=AUTH).json()['items'] == []


def test_deletion_erases_stored_content(client, database):
    log = create(client, manual(category='private-brand-xyz', consumed_ml=777))
    client.delete(f"/v1/beverages/{log['id']}", headers=AUTH)
    with sqlite3.connect(database) as connection:
        rows = connection.execute('SELECT consumed_at, record_json FROM beverages').fetchall()
    assert rows == [('', '{"deleted":true,"id":"%s"}' % log['id'])]


def test_edit_and_delete_require_auth_and_known_ids(client):
    log = create(client)
    assert client.patch(f"/v1/beverages/{log['id']}", json={'revision': 1, 'consumed_ml': 300}).status_code == 401
    assert client.delete(f"/v1/beverages/{log['id']}").status_code == 401
    assert client.patch(f"/v1/beverages/{uuid4()}", json={'revision': 1, 'consumed_ml': 300}, headers=AUTH).status_code == 404
    assert client.delete(f"/v1/beverages/{uuid4()}", headers=AUTH).status_code == 404
    assert client.delete('/v1/beverages/not-a-uuid', headers=AUTH).status_code == 422


def test_corrections_persist_across_restart(database):
    with TestClient(create_app(db_path=database, api_token=TOKEN)) as first:
        log = create(first)
        patch(first, log, consumed_ml=320)
    with TestClient(create_app(db_path=database, api_token=TOKEN)) as second:
        [stored] = second.get('/v1/beverages', headers=AUTH).json()['items']
        assert (stored['consumed_ml'], stored['revision']) == (320, 2)
