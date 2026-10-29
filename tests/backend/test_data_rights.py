"""Export everything and delete everything for the local owner."""
import sqlite3
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app

TOKEN = 'test-only-local-development-token-00000000'
AUTH = {'Authorization': f'Bearer {TOKEN}'}


@pytest.fixture
def database(tmp_path):
    return str(tmp_path / 'test.sqlite3')


@pytest.fixture
def client(database):
    with TestClient(create_app(db_path=database, api_token=TOKEN)) as c:
        yield c


def log(client, ml, key=None):
    body = dict(category='water', consumed_ml=ml, consumed_at='2026-10-28T12:00:00Z', timezone='UTC', source='manual')
    response = client.post('/v1/beverages', json=body, headers=AUTH | {'Idempotency-Key': key or str(uuid4())})
    assert response.status_code == 201
    return response.json()


def test_export_contains_live_logs_and_settings_only(client):
    kept, gone = log(client, 250), log(client, 400)
    client.delete(f"/v1/beverages/{gone['id']}", headers=AUTH)
    client.put('/v1/settings', json={'daily_beverage_goal_ml': 1800}, headers=AUTH)
    exported = client.get('/v1/export', headers=AUTH).json()
    assert exported['version'] == 'export-v1' and exported['exported_at'].endswith('Z')
    assert exported['beverages'] == [kept]
    assert exported['settings']['daily_beverage_goal_ml'] == 1800


def test_delete_all_requires_the_phrase_and_erases_content(client, database):
    key = str(uuid4())
    log(client, 250, key); log(client, 777)
    client.put('/v1/settings', json={'daily_beverage_goal_ml': 1800}, headers=AUTH)
    for bad in ({}, {'confirm': 'yes'}, {'confirm': 'DELETE-ALL-MY-DATA'}):
        assert client.delete('/v1/data', params=bad, headers=AUTH).status_code == 422
    assert len(client.get('/v1/export', headers=AUTH).json()['beverages']) == 2
    response = client.delete('/v1/data', params={'confirm': 'delete-all-my-data'}, headers=AUTH)
    assert response.json() == {'deleted_beverages': 2, 'settings_cleared': True}
    exported = client.get('/v1/export', headers=AUTH).json()
    assert exported['beverages'] == [] and exported['settings']['daily_beverage_goal_ml'] is None
    retry = client.post('/v1/beverages', json=dict(category='water', consumed_ml=250, consumed_at='2026-10-28T12:00:00Z',
                                                    timezone='UTC', source='manual'), headers=AUTH | {'Idempotency-Key': key})
    assert retry.status_code == 409  # a late retry cannot resurrect deleted data
    with sqlite3.connect(database) as connection:
        dump = '\n'.join(connection.iterdump())
    assert '777' not in dump and '"water"' not in dump
    again = client.delete('/v1/data', params={'confirm': 'delete-all-my-data'}, headers=AUTH)
    assert again.json()['deleted_beverages'] == 0


def test_data_rights_require_auth(client):
    assert client.get('/v1/export').status_code == 401
    assert client.delete('/v1/data', params={'confirm': 'delete-all-my-data'}).status_code == 401
