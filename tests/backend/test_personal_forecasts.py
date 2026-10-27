"""Authenticated local forecast integration; no provider or wearable disclosure."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import socket

import pytest
from fastapi.testclient import TestClient
from backend.app import create_app

AUTH={'Authorization':'Bearer test-only-local-development-token-00000000'}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path/'test.sqlite3'),api_token=AUTH['Authorization'][7:])) as client:
        yield client


def payload():
    return {'date':datetime.now(timezone.utc).date().isoformat(),'timezone':'UTC'}


def test_auth_and_default_fallback(client):
    assert client.post('/v1/forecasts',json=payload()).status_code == 401
    response=client.post('/v1/forecasts',json=payload(),headers=AUTH)
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    value=response.json()
    assert value['daily_requirement']['status'] == value['exercise_loss']['status'] == 'insufficient_data'
    assert value['historical_logged_intake']['logged_days'] == 0
    assert value['historical_logged_intake']['beverage_lower_ml'] is None


def test_owned_snapshot_recomputed_without_client_totals_or_network(client,monkeypatch):
    def forbidden(*args,**kwargs): raise AssertionError('No external connection')
    monkeypatch.setattr(socket,'create_connection',forbidden)
    data={'category':'tea','consumed_ml':250,'consumed_at':(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),
          'timezone':'UTC','source':'manual'}
    assert client.post('/v1/beverages',json=data,headers=AUTH|{'Idempotency-Key':str(uuid4())}).status_code == 201
    value=client.post('/v1/forecasts',json=payload(),headers=AUTH).json()
    assert value['intake']['beverage_total_ml'] == 250
    assert value['intake']['estimated_water_ml'] is None
    assert len(value['intake']['log_revisions']) == 1
    assert client.get('/health').json()['ai_mode'] == 'mock'


@pytest.mark.parametrize('changes',[{'heart_rate':70},{'history_days':True},{'timezone':'Invalid/Zone'},
    {'beverage_total_ml':999},{'date':'0001-01-01'},{'samples':[{}]*33}, {'healthkit_records':[]}])
def test_invalid_private_and_forged_data_refused(client,changes):
    response=client.post('/v1/forecasts',json=payload()|changes,headers=AUTH)
    assert response.status_code == 422, response.text
    assert response.json()['code'] == 'invalid_request'
    assert response.json()['retryable'] is False


def test_exercise_request_numeric_fixture(client):
    now=datetime.now(timezone.utc)
    conditions={'activity':'running','intensity':'moderate','temperature_c':20.0,'humidity_percent':60.0}
    start=now+timedelta(minutes=30)
    data=payload()|{'date':start.date().isoformat(),'calibration_processing_consent':True,'exercise':{'event_id':str(uuid4()),'starts_at':start.isoformat(),
        'duration_minutes':30.0,'conditions':conditions,'comparable_conditions_confirmed':True},
        'samples':[{'event_id':str(uuid4()),'observed_at':(now-timedelta(days=1)).isoformat(),'conditions':conditions,
        'measurement':{'pre_mass_kg':70.0,'post_mass_kg':69.0,'consumed_ml':400.0,'urine_ml':0.0,'duration_minutes':60.0,
            'protocol_confirmed':True,'provenance':['synthetic']},
        'errors':{'pre_mass_kg':.05,'post_mass_kg':.05,'consumed_ml':10.0,'urine_ml':0.0,'duration_minutes':0.0,'provenance':['synthetic-bounds']}}]}
    response=client.post('/v1/forecasts',json=data,headers=AUTH)
    assert response.status_code == 200, response.text
    value=response.json()['exercise_loss']
    assert (value['lower_ml'],value['upper_ml']) == (645,755)
    data['calibration_processing_consent']=False
    assert client.post('/v1/forecasts',json=data,headers=AUTH).status_code == 422
    data['calibration_processing_consent']=True
    data['samples'][0]['observed_at']='2026-10-26T12:00:00'
    assert client.post('/v1/forecasts',json=data,headers=AUTH).status_code == 422


def test_wearable_export_is_not_opened_by_new_endpoint(client):
    now=datetime.now(timezone.utc)
    data=payload()|{'exercise':{'event_id':str(uuid4()),'starts_at':now.isoformat(),'duration_minutes':30.0,
        'conditions':{'activity':'walking'},'duration_source':'wearable_aggregate'}}
    response=client.post('/v1/forecasts',json=data,headers=AUTH)
    assert response.status_code == 422
    assert 'wearable' not in response.text and 'duration_minutes' not in response.text
