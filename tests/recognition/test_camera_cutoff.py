"""Real ledger/gateway behavior, disposable synthetic accounts, no network."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import socket
import sqlite3
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.meta_accounts import AccountLedger, ACCOUNTS, FINANCIAL_DDL
from backend.meta_budget import BudgetDenied
from backend.meta_camera_cutoff import CutoffCameraLedger, CutoffCameraPolicy, CUTOFF_INPUT_LIMIT
from test_guarded_meta import setup, image, HASH, reply


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *args: pytest.fail('No billable test connections'))


def seed(tmp_path, *, baseline=0):
    old = setup(tmp_path, baseline=baseline)
    with old.transaction() as db:
        db.execute('UPDATE live_permit SET spent=1')
        db.execute('UPDATE live_accounts SET frozen=1')
        for state, reserved in [('billing_pending', 1312256), ('unresolved', 1312256), ('billing_pending', 1313792)]:
            db.execute('INSERT INTO live_attempts(id,account_id,price,reserved,state,created_at,input_bound) VALUES(?,?,?,?,?,?,?)',
                       (str(uuid4()), ACCOUNTS[0], '{}', reserved, state, '2026-11-01T00:00:00+00:00', 1048064))
    return CutoffCameraLedger(old.path)


def policy(**changes):
    return CutoffCameraPolicy(key_sha256=hashlib.sha256(b'synthetic-key').hexdigest(),
        owner_authorization_reference='synthetic-owner-replaces-financial-policy',
        price_reference='synthetic-reviewed-official-pricing', residual_provider_charge_risk_accepted=True,
        account_gross_floor_micro_usd=120000, **changes)


def snapshot(ledger):
    with ledger.transaction() as db:
        return {n: db.execute('SELECT * FROM '+n).fetchall() for n in FINANCIAL_DDL if n != 'live_events'}


def reserve(ledger):
    return ledger.reserve_first(ACCOUNTS[0], HASH, CUTOFF_INPUT_LIMIT)


def send(ledger):
    attempt = reserve(ledger)
    ticket = ledger.mark_dispatched(attempt, 'a'*64)
    ledger.claim_send(attempt, ticket.nonce, 'a'*64, CUTOFF_INPUT_LIMIT, policy().key_sha256)
    return attempt, ticket


def test_activation_preserves_every_existing_financial_row(tmp_path):
    ledger = seed(tmp_path); before = snapshot(ledger)
    ledger.activate(policy())
    assert snapshot(ledger) == before
    assert ledger.cutoff_status()['exposure_micro_usd'] == 89058304
    assert ledger.cutoff_status()['invoice_finality_required'] is False
    with pytest.raises(BudgetDenied):
        ledger.activate(policy(account_id=ACCOUNTS[0], cutoff_micro_usd=120000000).model_copy(update={'key_sha256':'b'*64}))


def test_repeated_requests_keep_full_reservations_and_old_holds(tmp_path):
    ledger = seed(tmp_path); ledger.activate(policy())
    first,_ = send(ledger); ledger.settle_provider_reply(first, reply())
    ledger.mark_recognized(first)
    assert ledger.receipt(first)['account_id'] == ACCOUNTS[0]
    second,_ = send(ledger)
    ledger.settle_provider_reply(second, reply(id='resp_second'))
    with ledger.transaction() as db:
        assert db.execute('SELECT count(*) FROM live_attempts').fetchone()[0] == 5
        assert db.execute('SELECT count(*) FROM live_finalities').fetchone()[0] == 0
        assert db.execute('SELECT frozen FROM live_accounts').fetchone()[0] == 1
        assert db.execute('SELECT reserved,actual,state FROM live_attempts WHERE id=?',(first,)).fetchone() == (1313792,None,'billing_pending')
    assert ledger.cutoff_status()['exposure_micro_usd'] == 91685888


@pytest.mark.parametrize('baseline,allowed',[(29747903,True),(29747904,False),(35000000,False)])
def test_exact_cutoff_includes_external_allocation_and_all_holds(tmp_path, baseline, allowed):
    ledger = seed(tmp_path,baseline=baseline); ledger.activate(policy())
    if allowed:
        reserve(ledger)
        assert ledger.cutoff_status()['exposure_micro_usd'] == 119999999
    else:
        with pytest.raises(BudgetDenied): reserve(ledger)


def test_parallel_admission_reserves_one_inflight_request(tmp_path):
    ledger = seed(tmp_path); ledger.activate(policy())
    def attempt(_):
        try: reserve(CutoffCameraLedger(ledger.path)); return True
        except BudgetDenied: return False
    with ThreadPoolExecutor(max_workers=8) as pool: assert sum(pool.map(attempt,range(16))) == 1


def test_one_use_send_cannot_replay_or_change_payload_or_credential(tmp_path):
    ledger = seed(tmp_path); ledger.activate(policy())
    attempt=reserve(ledger); ticket=ledger.mark_dispatched(attempt,'a'*64)
    for digest,key,bound in [('b'*64,policy().key_sha256,CUTOFF_INPUT_LIMIT),('a'*64,'b'*64,CUTOFF_INPUT_LIMIT),('a'*64,policy().key_sha256,20)]:
        with pytest.raises(BudgetDenied): ledger.claim_send(attempt,ticket.nonce,digest,bound,key)
    ledger.claim_send(attempt,ticket.nonce,'a'*64,CUTOFF_INPUT_LIMIT,policy().key_sha256)
    with pytest.raises(BudgetDenied): ledger.claim_send(attempt,ticket.nonce,'a'*64,CUTOFF_INPUT_LIMIT,policy().key_sha256)


def test_reserved_crash_stays_held_and_prevents_overlapping_send(tmp_path):
    ledger = seed(tmp_path);ledger.activate(policy());reserve(ledger)
    with pytest.raises(BudgetDenied): reserve(CutoffCameraLedger(ledger.path))
    assert CutoffCameraLedger(ledger.path).cutoff_status()['exposure_micro_usd'] == 90372096


@pytest.mark.parametrize('usage',[None,{}, {'input_tokens': True}])
def test_bad_usage_keeps_hold_and_known_provider_id(tmp_path,usage):
    ledger=seed(tmp_path);ledger.activate(policy());attempt,_=send(ledger)
    with pytest.raises(BudgetDenied):ledger.settle_provider_reply(attempt,reply(usage=usage))
    ledger.quarantine(attempt)
    with ledger.transaction() as db:
        assert db.execute('SELECT reserved,actual,state,provider_id FROM live_attempts WHERE id=?',(attempt,)).fetchone() == (1313792,None,'unresolved','resp_testonly')
    reserve(ledger)  # Owner waived invoice-finality gating; the failed attempt remains held.


def test_overbound_usage_increases_hold_and_cannot_be_shown_as_success(tmp_path):
    ledger=seed(tmp_path);ledger.activate(policy());attempt,_=send(ledger)
    usage={'input_tokens':1047552,'output_tokens':1025,'total_tokens':1048577,'input_tokens_details':{'cached_tokens':0}}
    with pytest.raises(BudgetDenied):ledger.settle_provider_reply(attempt,reply(usage=usage))
    with ledger.transaction() as db:
        assert db.execute('SELECT reserved,actual,state FROM live_attempts WHERE id=?',(attempt,)).fetchone() == (1313797,None,'unresolved')


def test_account_identity_and_storage_still_required(tmp_path):
    ledger=seed(tmp_path);ledger.activate(policy())
    with pytest.raises(BudgetDenied):ledger.verify_credential(ACCOUNTS[0],'b'*64)
    with pytest.raises(BudgetDenied):ledger.verify_credential(ACCOUNTS[1],policy().key_sha256)
    with pytest.raises(BudgetDenied):ledger.verify_purpose(ACCOUNTS[0],'hydration')
    with pytest.raises(BudgetDenied):ledger.quote(ACCOUNTS[0],20)
    with pytest.raises(BudgetDenied):ledger.reserve_first(ACCOUNTS[0],'invalid',CUTOFF_INPUT_LIMIT)


@pytest.mark.parametrize('change',[{'account_id':ACCOUNTS[1]},{'cutoff_micro_usd':150000000}, {'external_allocation_hold_micro_usd':0}, {'residual_provider_charge_risk_accepted':False}, {'residual_provider_charge_risk_accepted':1}, {'account_gross_floor_micro_usd':True}])
def test_policy_cannot_silently_drop_cutoff_or_external_exposure(change):
    raw=policy().model_dump()|change
    with pytest.raises(ValidationError):CutoffCameraPolicy.model_validate(raw)


def test_authenticated_app_two_official_http_requests_and_confirmed_log(tmp_path, monkeypatch):
    import base64
    from fastapi.testclient import TestClient
    from backend.app import create_app
    from backend.meta_observations import read_observation
    from test_guarded_meta import AUTH,TOKEN,IMAGE
    ledger=seed(tmp_path);ledger.activate(policy())
    monkeypatch.setenv('HYDRA_AI_MODE','guarded_meta')
    monkeypatch.setenv('META_BILLABLE_REQUESTS_ENABLED','true')
    monkeypatch.setenv('HYDRA_META_ACCOUNT',ACCOUNTS[0])
    monkeypatch.setenv('HYDRA_META_LEDGER_PATH',ledger.path)
    monkeypatch.setenv('HYDRA_META_CAMERA_POLICY','georgio-camera-cutoff-v1')
    monkeypatch.setenv('HYDRA_META_GEORGIO_API_KEY','synthetic-key')
    calls=[]
    class Response:
        status=200
        def read(self,maximum):
            return json.dumps(reply(id='resp_cutoff_'+str(len(calls))).body).encode()
    class Connection:
        def __init__(self,host,timeout): assert host=='api.meta.ai'
        def request(self,method,path,body,headers):
            payload=json.loads(body)
            assert (method,path)==('POST','/v1/responses')
            assert payload['max_output_tokens']==1024
            assert not any(k in payload for k in ('tools','previous_response_id','conversation','files'))
            assert payload['store'] is False and payload['stream'] is False
            calls.append(payload)
        def getresponse(self):return Response()
        def close(self):pass
    monkeypatch.setattr('backend.meta_provider.http.client.HTTPSConnection',Connection)
    app=create_app(tmp_path/'beverages.sqlite3',TOKEN)
    with TestClient(app) as client:
        assert client.post('/v1/recognitions',json=image().model_dump()).status_code==401
        bad=image().model_dump()|{'meta_photo_consent':False}
        assert client.post('/v1/recognitions',json=bad,headers=AUTH).status_code in (422,503)
        assert not calls
        results=[]
        for _ in range(2):
            result=client.post('/v1/recognitions',json=image().model_dump(),headers=AUTH)
            assert result.status_code==200,result.text
            results.append(result.json())
        assert len(calls)==2
        for value in results:
            observed=read_observation(ledger.path,value['recognition_id'])
            assert observed['transport_kind']=='official_meta_https'
            assert observed['input_sha256']==HASH
            assert observed['usage_cost_micro_usd']==338
            assert observed['final_gross_micro_usd'] is None
        assert client.get('/v1/beverages',headers=AUTH).json()['items']==[]
        from datetime import datetime,timezone
        payload={'source':'confirmed_recognition','consumed_ml':200,'container_ml':300,
                 'consumed_at':datetime.now(timezone.utc).isoformat(),'timezone':'UTC','category':'Tea',
                 'recognition_id':results[0]['recognition_id'],'consumption_assumption':'entire_liquid','beverage_type':'Tea'}
        response=client.post('/v1/beverages',json=payload,headers=AUTH|{'Idempotency-Key':str(uuid4())})
        assert response.status_code==201,response.text
        assert response.json()['consumed_ml']==200
        assert response.json()['consumption_assumption']=='entire_liquid'
        assert len(calls)==2  # Confirming never invokes inference.


def test_unknown_policy_cannot_silently_fall_back_to_legacy_live(tmp_path,monkeypatch):
    from backend.app import create_app
    from test_guarded_meta import TOKEN
    monkeypatch.setenv('HYDRA_AI_MODE','guarded_meta');monkeypatch.setenv('META_BILLABLE_REQUESTS_ENABLED','true')
    ledger=seed(tmp_path);ledger.activate(policy())
    monkeypatch.setenv('HYDRA_META_ACCOUNT',ACCOUNTS[0])
    monkeypatch.setenv('HYDRA_META_LEDGER_PATH',ledger.path)
    monkeypatch.setenv('HYDRA_META_GEORGIO_API_KEY','synthetic-key')
    monkeypatch.setenv('HYDRA_GITHUB_NOTIFICATION_TOKEN','synthetic-token')
    monkeypatch.setenv('HYDRA_META_CAMERA_POLICY','unknown')
    with pytest.raises(ValueError):create_app(tmp_path/'beverages.sqlite3',TOKEN)


def test_cutoff_rechecked_before_dispatch_after_intervening_charge(tmp_path):
    ledger=seed(tmp_path);ledger.activate(policy());attempt=reserve(ledger)
    with ledger.transaction() as db:
        db.execute('UPDATE live_attempts SET reserved=40000000 WHERE id=(SELECT id FROM live_attempts WHERE state=\'unresolved\' LIMIT 1)')
    with pytest.raises(BudgetDenied):ledger.mark_dispatched(attempt,'a'*64)
    with ledger.transaction() as db:
        assert db.execute('SELECT state FROM live_attempts WHERE id=?',(attempt,)).fetchone()[0]=='reserved'


def test_new_policy_never_reactivates_legacy_permit(tmp_path):
    ledger=seed(tmp_path);ledger.activate(policy())
    with pytest.raises(BudgetDenied):AccountLedger(ledger.path).reserve_first(ACCOUNTS[0],HASH,1000)


def test_private_operator_result_excludes_key_and_keeps_full_hold(tmp_path,monkeypatch):
    from scripts.meta_camera_cutoff import analyze_once
    from test_guarded_meta import JPEG,TOKEN
    ledger=seed(tmp_path);ledger.activate(policy())
    tmp_path.chmod(0o700)
    env=tmp_path/'backend.env'
    env.write_text(f'HYDRA_AI_MODE=mock\nMETA_BILLABLE_REQUESTS_ENABLED=false\nHYDRA_META_ACCOUNT={ACCOUNTS[0]}\nHYDRA_META_GEORGIO_API_KEY=synthetic-key\nHYDRA_API_TOKEN={TOKEN}\n')
    env.chmod(0o600)
    photo=tmp_path/'synthetic.jpg';photo.write_bytes(JPEG);photo.chmod(0o600)
    requests=[]
    class Response:
        status=200
        def read(self,maximum):return json.dumps(reply().body).encode()
    class Connection:
        def __init__(self,*args,**kwargs):pass
        def request(self,method,path,body,headers):requests.append(path)
        def getresponse(self):return Response()
        def close(self):pass
    monkeypatch.setattr('backend.meta_provider.http.client.HTTPSConnection',Connection)
    result=analyze_once(env,ledger.path,photo,tmp_path/'result.json')
    assert result['error'] is None
    assert result['recognition']['candidates'][0]['category']=='tea'
    assert result['observation']['usage_cost_micro_usd']==338
    assert result['observation']['reserved_micro_usd']==1313792
    assert result['observation']['final_gross_micro_usd'] is None
    assert (tmp_path/'result.json').stat().st_mode & 0o777 == 0o600
    assert 'synthetic-key' not in (tmp_path/'result.json').read_text()
    with pytest.raises(ValueError):analyze_once(env,ledger.path,photo,tmp_path/'result.json')
    assert requests==['/v1/responses']


def test_timeout_never_retries_or_releases_reservation(tmp_path,monkeypatch):
    from backend.meta_camera_cutoff import CutoffCameraGateway,CutoffCameraTransport
    from backend.recognition import RecognitionUnavailable
    ledger=seed(tmp_path);ledger.activate(policy());requests=[]
    class Connection:
        def __init__(self,*args,**kwargs):pass
        def request(self,*args,**kwargs):requests.append(1);raise TimeoutError
        def close(self):pass
    monkeypatch.setattr('backend.meta_provider.http.client.HTTPSConnection',Connection)
    with pytest.raises(RecognitionUnavailable):CutoffCameraGateway(ledger,CutoffCameraTransport('synthetic-key')).analyze(image())
    assert requests==[1]
    assert ledger.cutoff_status()['exposure_micro_usd']==90372096


@pytest.mark.parametrize('state',['experiment_reserved','experiment_dispatched','experiment_sending'])
def test_inflight_other_feature_in_same_authority_blocks_camera(tmp_path,state):
    ledger=seed(tmp_path);ledger.activate(policy())
    with ledger.transaction() as db:
        db.execute('INSERT INTO live_attempts(id,account_id,price,reserved,state,created_at,input_bound) VALUES(?,?,?,?,?,?,?)',
                   (str(uuid4()),ACCOUNTS[0],'{}',250000,state,'2026-11-01T00:00:00+00:00',1000))
    with pytest.raises(BudgetDenied):reserve(ledger)
