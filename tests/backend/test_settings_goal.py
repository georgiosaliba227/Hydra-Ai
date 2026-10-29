"""User-chosen daily beverage goal and summary progress; local only."""
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


def log(client, ml, at='2026-10-28T12:00:00Z'):
    body = dict(category='water', consumed_ml=ml, consumed_at=at, timezone='UTC', source='manual')
    assert client.post('/v1/beverages', json=body, headers=AUTH | {'Idempotency-Key': str(uuid4())}).status_code == 201


def summary(client):
    return client.get('/v1/summary', params={'date': '2026-10-28', 'timezone': 'UTC'}, headers=AUTH).json()


def test_no_goal_by_default(client):
    assert client.get('/v1/settings', headers=AUTH).json() == {
        'version': 'settings-v1', 'daily_beverage_goal_ml': None, 'goal_basis': 'user_confirmed', 'updated_at': None}
    assert summary(client)['goal'] is None


def test_goal_progress_tracks_logged_volume_and_never_goes_negative(client):
    saved = client.put('/v1/settings', json={'daily_beverage_goal_ml': 2000}, headers=AUTH).json()
    assert saved['daily_beverage_goal_ml'] == 2000 and saved['updated_at'].endswith('Z')
    log(client, 500)
    assert summary(client)['goal'] == {'daily_beverage_goal_ml': 2000, 'basis': 'user_confirmed',
                                       'remaining_ml': 1500.0, 'progress_ratio': 0.25}
    log(client, 1800)
    goal = summary(client)['goal']
    assert goal['remaining_ml'] == 0.0 and goal['progress_ratio'] == 1.15


def test_goal_can_be_cleared_and_persists_across_restart(database):
    with TestClient(create_app(db_path=database, api_token=TOKEN)) as first:
        first.put('/v1/settings', json={'daily_beverage_goal_ml': 1500}, headers=AUTH)
    with TestClient(create_app(db_path=database, api_token=TOKEN)) as second:
        assert second.get('/v1/settings', headers=AUTH).json()['daily_beverage_goal_ml'] == 1500
        assert second.put('/v1/settings', json={'daily_beverage_goal_ml': None}, headers=AUTH).json()['daily_beverage_goal_ml'] is None
        assert summary(second)['goal'] is None


@pytest.mark.parametrize('body', [{}, {'daily_beverage_goal_ml': 99}, {'daily_beverage_goal_ml': 10_001},
                                  {'daily_beverage_goal_ml': 2000.5}, {'daily_beverage_goal_ml': '2000'},
                                  {'daily_beverage_goal_ml': 2000, 'recommended': True}])
def test_invalid_goals_are_rejected(client, body):
    assert client.put('/v1/settings', json=body, headers=AUTH).status_code == 422
    assert client.get('/v1/settings', headers=AUTH).json()['daily_beverage_goal_ml'] is None


def test_settings_require_auth(client):
    assert client.get('/v1/settings').status_code == 401
    assert client.put('/v1/settings', json={'daily_beverage_goal_ml': 2000}).status_code == 401
