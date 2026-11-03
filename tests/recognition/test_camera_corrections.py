"""Owned synthetic photos, local memory and explicit training-example consent."""
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import socket
import sqlite3
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.meta_images import sanitized_jpeg
from backend.recognition import AnalysisRequest
from test_guarded_meta import JPEG, TOKEN, AUTH

PHOTO = base64.b64encode(JPEG).decode()
TAGGED = base64.b64encode(JPEG[:2] + b'\xff\xe1\x00\x09PRIVATE' + JPEG[2:]).decode()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs): raise AssertionError('Camera feedback tests cannot call providers')
    monkeypatch.setattr(socket.socket,'connect',blocked)


@pytest.fixture
def camera(tmp_path):
    path=tmp_path/'synthetic-beverages.sqlite3'
    app=create_app(path,TOKEN)
    class Recognizer:
        def analyze(self,payload):
            return {'mode':'mock','candidates':[{'identity':'Wrong tea','brand':'Demo brand','product':'Demo green tea',
                    'visible_label_text':'DEMO GREEN TEA','container_ml':500,'confidence':'low',
                    'uncertainty_reasons':['Synthetic test estimate; verify'],
                    'estimated_liquid_ml_min':100,'estimated_liquid_ml_max':200,'volume_basis':'visual_estimate'}]}
    app.state.recognizer=Recognizer()
    return app,TestClient(app),path


def analyze(client,photo=PHOTO):
    response=client.post('/v1/recognitions',headers=AUTH,json={'image_base64':photo,'photo_consent':True,'mock_scenario':'generic'})
    assert response.status_code==200
    return response.json()


def confirmation(result,*,share=False,photo=None,remember=True):
    feedback={'image_sha256':result['image_sha256'],'source_mode':'mock',
              'original_candidate':result['candidates'][0], 'remember_for_me':remember,
              'share_for_training':share}
    if share:
        feedback|={'training_consent_version':'hydra-training-photo-correction-v1','training_photo_base64':photo or PHOTO}
    return {'category':'Corrected green tea','container_ml':300,'consumed_ml':125,'source':'confirmed_recognition',
            'consumed_at':datetime.now(timezone.utc).isoformat(),'timezone':'America/New_York',
            'recognition_feedback':feedback}


def save(client,body,key=None):
    return client.post('/v1/beverages',headers=AUTH|{'Idempotency-Key':key or str(uuid4())},json=body)


def test_confirmation_learns_only_after_user_save_and_keeps_actual_consumption(camera):
    app,client,path=camera
    original=analyze(client)
    assert original['candidates'][0]['estimated_liquid_ml_min']==100
    assert original['candidates'][0]['estimated_liquid_ml_max']==200
    assert original['candidates'][0].get('personal_correction') is None
    body=confirmation(original)
    response=save(client,body)
    assert response.status_code==201
    assert response.json()['consumed_ml']==125
    assert 'recognition_feedback' not in response.json()
    next_result=analyze(client)
    memory=next_result['candidates'][0]['personal_correction']
    assert memory['identity']=='Corrected green tea' and memory['container_ml']==300
    assert memory['match_basis']=='exact_image'
    assert next_result['candidates'][0]['identity']=='Wrong tea', 'Never misrepresent a correction as Muse output'
    exported=client.get('/v1/export',headers=AUTH).json()
    assert len(exported['recognition_corrections'])==1 and exported['training_examples']==[]
    assert exported['beverages'][0]['consumed_ml']==125


def test_same_label_reuses_identity_but_not_capacity_or_fill(camera):
    _,client,_=camera
    result=analyze(client)
    body=confirmation(result)
    body['recognition_feedback']['corrected_liquid_ml']=240
    assert save(client,body).status_code==201
    exact=analyze(client)['candidates'][0]
    assert exact['personal_correction']['liquid_ml']==240
    assert exact['estimated_liquid_ml_max']==200, 'The original model range remains distinct'
    other=bytearray(JPEG);other[8]=17
    changed=base64.b64encode(other).decode()
    memory=analyze(client,changed)['candidates'][0]['personal_correction']
    assert memory['match_basis']=='product_label' and memory['identity']=='Corrected green tea'
    assert memory['container_ml'] is None, 'Similar front labels do not establish the same bottle capacity'
    assert memory['liquid_ml'] is None, 'A new photo cannot reuse an old fill amount'


def test_memory_and_training_are_independent_explicit_choices(camera):
    _,client,path=camera
    result=analyze(client,TAGGED)
    body=confirmation(result,share=True,photo=TAGGED,remember=False)
    response=save(client,body);assert response.status_code==201
    exported=client.get('/v1/export',headers=AUTH).json()
    assert exported['recognition_corrections']==[]
    examples=exported['training_examples'];assert len(examples)==1
    example=examples[0]
    sanitized=base64.b64decode(example['photo_base64'])
    assert b'PRIVATE' not in sanitized and sanitized==JPEG
    assert example['consent_version']=='hydra-training-photo-correction-v1'
    assert example['review_status']=='pending_review' and example['synthetic'] is True
    assert example['corrected_identity']=='Corrected green tea'
    assert 'consumed_ml' not in example, 'Consumption is not a vision size label'
    assert analyze(client)['candidates'][0].get('personal_correction') is None


@pytest.mark.parametrize('change',[
    {'share_for_training':True},
    {'share_for_training':1},
    {'training_photo_base64':PHOTO},
    {'share_for_training':True,'training_photo_base64':PHOTO,'training_consent_version':'wrong'},
    {'share_for_training':True,'training_photo_base64':PHOTO,'training_consent_version':'hydra-training-photo-correction-v1','image_sha256':'0'*64},
    {'remember_for_me':'true'},
])
def test_invalid_consent_or_photo_mismatch_writes_nothing(camera,change):
    _,client,_=camera
    body=confirmation(analyze(client));body['recognition_feedback']|=change
    assert save(client,body).status_code==422
    assert client.get('/v1/beverages',headers=AUTH).json()['items']==[]


def test_retry_is_atomic_and_never_duplicates_beverage_memory_or_training(camera):
    _,client,_=camera
    body=confirmation(analyze(client),share=True);key=str(uuid4())
    first=save(client,body,key);second=save(client,body,key)
    assert (first.status_code,second.status_code)==(201,200)
    assert first.json()==second.json()
    exported=client.get('/v1/export',headers=AUTH).json()
    assert len(exported['beverages'])==len(exported['recognition_corrections'])==len(exported['training_examples'])==1
    altered=json.loads(json.dumps(body));altered['recognition_feedback']['share_for_training']=False
    altered['recognition_feedback'].pop('training_consent_version');altered['recognition_feedback'].pop('training_photo_base64')
    assert save(client,altered,key).status_code==409


def test_delete_entry_or_delete_all_removes_corrections_and_training(camera):
    _,client,_=camera
    body=confirmation(analyze(client),share=True)
    created=save(client,body).json()
    assert client.delete('/v1/beverages/'+created['id'],params={'revision':1},headers=AUTH).status_code==204
    exported=client.get('/v1/export',headers=AUTH).json()
    assert exported['recognition_corrections']==exported['training_examples']==[]
    assert analyze(client)['candidates'][0].get('personal_correction') is None
    assert save(client,body).status_code==201
    assert client.delete('/v1/data?confirm=delete-all-my-data',headers=AUTH).status_code==200
    exported=client.get('/v1/export',headers=AUTH).json()
    assert exported['recognition_corrections']==exported['training_examples']==[]


def test_feedback_endpoint_cannot_accept_manual_log_or_fabricated_live_receipt(camera):
    _,client,_=camera
    body=confirmation(analyze(client));body['source']='manual'
    assert save(client,body).status_code==422
    body['source']='confirmed_recognition';body['recognition_feedback']['source_mode']='meta_live'
    assert save(client,body).status_code==422


def test_unknown_and_invalid_liquid_estimates_fail_closed(camera):
    app,client,_=camera
    result=analyze(client)
    assert result['candidates'][0]['estimated_liquid_ml_max']!=result['candidates'][0]['container_ml']
    class Bad:
        def analyze(self,payload):
            return {'candidates':[result['candidates'][0]|{'estimated_liquid_ml_min':400,'estimated_liquid_ml_max':200}]}
    app.state.recognizer=Bad()
    assert client.post('/v1/recognitions',headers=AUTH,json={'image_base64':PHOTO,'photo_consent':True}).status_code==503


def test_staged_training_retains_latest_twenty_and_is_owner_scoped(camera):
    app,client,_=camera
    result=analyze(client)
    ids=[]
    for _ in range(21):
        response=save(client,confirmation(result,share=True));assert response.status_code==201
        ids.append(response.json()['id'])
    exported=client.get('/v1/export',headers=AUTH).json()
    assert len(exported['training_examples'])==20
    assert ids[0] not in {x['example_id'] for x in exported['training_examples']}
    assert ids[-1] in {x['example_id'] for x in exported['training_examples']}
    assert app.state.repository.export_corrections('another-owner')==([],[])
    assert app.state.repository.correction_for('another-owner','mock',result['image_sha256'],'unused',None) is None


def test_feedback_failure_rolls_back_drink_and_every_training_write(camera):
    _,client,path=camera
    result=analyze(client)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TRIGGER fail_feedback BEFORE INSERT ON recognition_corrections BEGIN SELECT RAISE(ABORT,'synthetic storage fault'); END")
    response=save(client,confirmation(result,share=True))
    assert response.status_code==503
    exported=client.get('/v1/export',headers=AUTH).json()
    assert exported['beverages']==exported['recognition_corrections']==exported['training_examples']==[]


def test_financial_authority_never_gains_correction_tables_or_loses_history(tmp_path):
    from backend.meta_accounts import AccountLedger
    path=tmp_path/'synthetic-finance.sqlite3'
    ledger=AccountLedger(path);ledger.initialize_accounts()
    with ledger.transaction() as connection:
        ledger.event(connection,None,'synthetic_financial_marker','keep')
    app=create_app(path,TOKEN)
    client=TestClient(app)
    assert client.get('/v1/recognition-capabilities',headers=AUTH).json()['correction_memory_available'] is False
    assert client.delete('/v1/data?confirm=delete-all-my-data',headers=AUTH).status_code==200
    with ledger.transaction() as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE name LIKE 'recognition_%'").fetchall()==[]
        assert connection.execute("SELECT reference FROM live_events WHERE kind='synthetic_financial_marker'").fetchall()==[('keep',)]


def test_concurrent_duplicate_confirmations_commit_only_one_example(camera):
    _,client,_=camera
    body=confirmation(analyze(client),share=True);key=str(uuid4())
    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses=list(pool.map(lambda _:save(client,body,key).status_code,range(4)))
    assert statuses.count(201)==1 and statuses.count(200)==3
    exported=client.get('/v1/export',headers=AUTH).json()
    assert len(exported['beverages'])==len(exported['training_examples'])==1


def test_live_correction_must_match_the_receipts_exact_image(tmp_path):
    from test_guarded_meta import setup as financial_fixture,FakeTransport,FakeNotifier
    from backend.meta_gateway import GuardedMetaGateway
    folder=tmp_path/'finance';folder.mkdir()
    ledger=financial_fixture(folder)
    result=GuardedMetaGateway(ledger,'georgiosaliba227',FakeTransport(),FakeNotifier()).analyze(
        AnalysisRequest(image_base64=PHOTO,photo_consent=True,meta_photo_consent=True,mode='meta_live')).model_dump()
    result['image_sha256']=hashlib.sha256(JPEG).hexdigest()
    app=create_app(tmp_path/'beverages.sqlite3',TOKEN);app.state.meta_ledger=ledger
    client=TestClient(app)
    body=confirmation(result);body['recognition_id']=result['recognition_id']
    body['recognition_feedback']['source_mode']='meta_live'
    body['recognition_feedback']['image_sha256']='0'*64
    assert save(client,body).status_code==422
    body['recognition_feedback']['image_sha256']=result['image_sha256']
    assert save(client,body).status_code==201


def test_mock_memory_never_changes_live_suggestions(camera):
    app,client,_=camera
    result=analyze(client)
    assert save(client,confirmation(result)).status_code==201
    app.state.recognition_mode='meta_live'
    class InjectedLive:
        def analyze(self,payload):
                return {'mode':'meta_live','recognition_id':str(uuid4()),'candidates':[{k:v for k,v in result['candidates'][0].items() if k!='nutrition'}]}
    app.state.recognizer=InjectedLive()
    response=client.post('/v1/recognitions',headers=AUTH,json={'image_base64':PHOTO,'photo_consent':True,'meta_photo_consent':True,'mode':'meta_live'})
    assert response.status_code==200
    assert response.json()['candidates'][0]['personal_correction'] is None


def test_correction_after_no_match_is_recalled_as_personal_not_model_output(camera):
    app,client,_=camera
    class NoMatch:
        def analyze(self,payload):return {'candidates':[]}
    app.state.recognizer=NoMatch()
    result=analyze(client);assert result['candidates']==[]
    result['candidates']=[{'identity':'Unknown beverage','confidence':'low','uncertainty_reasons':['No confident model match']}]
    assert save(client,confirmation(result)).status_code==201
    recalled=analyze(client)['candidates']
    assert len(recalled)==1
    assert recalled[0]['identity']=='Unknown beverage'
    assert recalled[0]['personal_correction']['identity']=='Corrected green tea'
