"""The demo seed script against the real app in process; no network."""
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from backend.app import create_app
from scripts.seed_demo import GOAL_ML, PLAN, entries, seed

TOKEN = 'test-only-local-development-token-00000000'


def test_seed_creates_a_week_once_sets_the_goal_and_never_future_dates(tmp_path):
    zone = ZoneInfo('Europe/Paris')
    now = datetime(2026, 10, 20, 8, 0, tzinfo=zone)  # in the past; before that day's 09:15 coffee
    with TestClient(create_app(db_path=str(tmp_path / 'seed.sqlite3'), api_token=TOKEN)) as client:
        def send(method, path, body, headers):
            return client.request(method, path, json=body, headers={'Authorization': f'Bearer {TOKEN}', **headers}).status_code
        first = seed(send, now, zone)
        assert first == {'created': len(PLAN) - 1, 'already_present': 0, 'goal_ml': GOAL_ML, 'synthetic': True}
        again = seed(send, now, zone)
        assert again['created'] == 0 and again['already_present'] == len(PLAN) - 1
        auth = {'Authorization': f'Bearer {TOKEN}'}
        summary = client.get('/v1/summary', params={'date': '2026-10-20', 'timezone': 'Europe/Paris'}, headers=auth).json()
        assert summary['beverage_total_ml'] == 350 and summary['goal']['daily_beverage_goal_ml'] == GOAL_ML
    assert all(datetime.fromisoformat(body['consumed_at']) <= now for _, body in entries(now, zone))
