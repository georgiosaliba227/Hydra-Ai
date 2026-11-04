"""Local adapter camera contract; no hosted calls or financial mutations."""
import base64
from datetime import datetime, timezone
import hashlib
import json
import socket
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.recognition import AnalysisRequest, RecognitionUnavailable
from test_guarded_meta import JPEG, TOKEN, AUTH

ADAPTER = '71a361e862c5e1399b25098601fd7d974253a5f5d285e9ad194f90e38028d48f'
MODEL = 'muse-glimmer-30b-beverage-lora-v1'


def prediction(**overrides):
    return dict(image_id='camera-example', model_id='mlx-community/Muse-Glimmer-30B-4bit',
                base_revision='3e7677d7a40d348a3daba263a2b1c0aa41910710', adapter_sha256=ADAPTER,
                prompt_sha256='0d9b19529813b8effc401618f529df66c1967f13238fde5d675a204b882defa1',
                outcome='success', error=None, brand='DASANI', product='Purified Water',
                capacity_ml=1000, latency_ms=14000) | overrides


def photo():
    return {'image_base64':base64.b64encode(JPEG).decode(), 'photo_consent':True, 'mode':'local_meta'}


def test_local_mode_is_additive_and_requires_photo_consent():
    value = AnalysisRequest.model_validate(photo())
    assert value.mode == 'local_meta' and not value.meta_photo_consent
    with pytest.raises(ValueError):
        AnalysisRequest.model_validate(photo() | {'photo_consent':False})


@pytest.mark.parametrize('ocr,capacity,expected', [
    ('DASANI\nPURIFIED WATER\n1 LITER',1000,1000),
    ('DASANI\nPURIFIED WATER\n1 LITER',500,None),
    ('DASANI\nPURIFIED WATER',1000,None),
    ('Serving size 250 ml',250,None),
    ('6 x 250 ml',1500,None),
    ('6 x 250 ml',250,None),
    ('500 ml\n750 ml',500,None),
    ('Net contents 500 mL\nServing size 250 mL',500,500),
])
def test_only_supported_consistent_label_capacity_is_used(ocr,capacity,expected):
    from backend.local_meta import local_result
    result=local_result(prediction(capacity_ml=capacity),ocr)
    candidate=result.candidates[0]
    assert result.mode=='local_meta' and result.model==MODEL
    assert candidate.identity=='DASANI Purified Water'
    assert candidate.container_ml==expected and candidate.label_capacity_ml==expected
    assert candidate.estimated_liquid_ml_min is None and candidate.estimated_liquid_ml_max is None
    assert result.requires_confirmation


@pytest.mark.parametrize('override', [
    {'adapter_sha256':'a'*64}, {'base_revision':'wrong'}, {'model_id':'muse-spark-1.3'},
    {'outcome':'error'}, {'capacity_ml':True}, {'capacity_ml':1000.5},
    {'brand':[]}, {'product':'a'*201}, {'prompt_sha256':'a'*64},
])
def test_untrusted_or_wrong_checkpoint_predictions_fail_closed(override):
    from backend.local_meta import local_result
    with pytest.raises(RecognitionUnavailable):
        local_result(prediction(**override),'1 LITER')


def test_local_failure_is_not_retried():
    from backend.local_meta import LocalMetaRecognizer
    class Runtime:
        calls=0
        def recognize(self,jpeg):
            self.calls+=1
            raise RuntimeError('private failure detail')
    runtime=Runtime()
    with pytest.raises(RecognitionUnavailable):
        LocalMetaRecognizer(runtime).analyze(AnalysisRequest.model_validate(photo()))
    assert runtime.calls==1


def test_ocr_background_text_is_not_returned_or_kept_with_the_result():
    from backend.local_meta import local_result
    result=local_result(prediction(),'Private background text\nDASANI\nPURIFIED WATER\n1 LITER')
    label=result.candidates[0].visible_label_text
    assert label=='1 LITER'


def test_generic_ocr_context_does_not_retain_private_background_sentences():
    from backend.local_meta import local_result
    result=local_result(prediction(),'Synthetic Jane takes medication twice per day\nNet private chat\n1 LITER')
    assert result.candidates[0].visible_label_text=='1 LITER'


def test_confirmed_receipt_survives_unconfirmed_eviction_and_replays_after_restart(local_camera):
    client,path,_=local_camera
    result=client.post('/v1/recognitions',headers=AUTH,json=photo()).json()
    key=str(uuid4());body=confirmation(result)
    first=client.post('/v1/beverages',headers=AUTH|{'Idempotency-Key':key},json=body)
    assert first.status_code==201,first.text
    for _ in range(105):
        response=client.post('/v1/recognitions',headers=AUTH,json=photo())
        assert response.status_code==200
    restarted=TestClient(create_app(path,TOKEN))
    replay=restarted.post('/v1/beverages',headers=AUTH|{'Idempotency-Key':key},json=body)
    assert replay.status_code==200,replay.text
    assert replay.json()==first.json()
    assert len(restarted.get('/v1/export',headers=AUTH).json()['local_recognition_receipts'])==101


def test_durable_confirmation_replay_does_not_depend_on_an_auxiliary_receipt(local_camera):
    import sqlite3
    client,path,_=local_camera
    result=client.post('/v1/recognitions',headers=AUTH,json=photo()).json()
    key=str(uuid4());body=confirmation(result)
    first=client.post('/v1/beverages',headers=AUTH|{'Idempotency-Key':key},json=body)
    assert first.status_code==201
    with sqlite3.connect(path) as db: db.execute('DELETE FROM local_recognition_receipts')
    replay=client.post('/v1/beverages',headers=AUTH|{'Idempotency-Key':key},json=body)
    assert replay.status_code==200,replay.text
    assert replay.json()==first.json()
    conflict=client.post('/v1/beverages',headers=AUTH|{'Idempotency-Key':key},json=body|{'category':'Different water'})
    assert conflict.status_code==409


def test_deleting_confirmed_drink_removes_its_local_receipt_without_resurrection(local_camera):
    client,_,_=local_camera
    result=client.post('/v1/recognitions',headers=AUTH,json=photo()).json()
    key=str(uuid4());body=confirmation(result)
    first=client.post('/v1/beverages',headers=AUTH|{'Idempotency-Key':key},json=body)
    assert first.status_code==201
    deleted=client.delete('/v1/beverages/'+first.json()['id'],headers=AUTH)
    assert deleted.status_code==204,deleted.text
    assert client.get('/v1/export',headers=AUTH).json()['local_recognition_receipts']==[]
    assert client.post('/v1/beverages',headers=AUTH|{'Idempotency-Key':key},json=body).status_code==409


def test_local_receipts_and_photos_follow_data_deletion(local_camera):
    client,path,_=local_camera
    assert client.post('/v1/recognitions',headers=AUTH,json=photo()).status_code==200
    assert JPEG not in path.read_bytes() and base64.b64encode(JPEG) not in path.read_bytes()
    response=client.delete('/v1/data?confirm=delete-all-my-data',headers=AUTH)
    assert response.status_code==200,response.text
    assert client.get('/v1/export',headers=AUTH).json()['local_recognition_receipts']==[]


@pytest.fixture
def local_camera(tmp_path,monkeypatch):
    def blocked(*args,**kwargs): raise AssertionError('No network from local camera')
    monkeypatch.setattr(socket.socket,'connect',blocked)
    monkeypatch.setenv('HYDRA_AI_MODE','local_meta')
    monkeypatch.setenv('META_BILLABLE_REQUESTS_ENABLED','false')
    from backend.local_meta import LocalMetaRecognizer
    class Runtime:
        def recognize(self,jpeg): return prediction(),'DASANI\nPURIFIED WATER\n1 LITER'
    monkeypatch.setattr(LocalMetaRecognizer,'from_environment',classmethod(lambda cls:cls(Runtime())))
    path=tmp_path/'beverages.sqlite3'
    ledger=tmp_path/'financial-history.bin'
    ledger.write_bytes(b'preserve the original financial history unchanged')
    monkeypatch.setenv('HYDRA_META_LEDGER_PATH',str(ledger))
    app=create_app(path,TOKEN)
    return TestClient(app),path,ledger


def confirmation(result):
    return {'category':'DASANI Purified Water','consumed_ml':1000,'container_ml':1000,
            'source':'confirmed_recognition','recognition_id':result['recognition_id'],
            'consumption_assumption':'full_container','beverage_type':'Water',
            'consumed_at':datetime.now(timezone.utc).isoformat(),'timezone':'America/New_York'}


def test_local_analysis_confirms_with_receipt_and_preserves_financial_history(local_camera):
    client,path,ledger=local_camera
    before=ledger.read_bytes()
    capabilities=client.get('/v1/recognition-capabilities',headers=AUTH).json()
    assert (capabilities['mode'],capabilities['model'])==('local_meta',MODEL)
    assert not client.get('/health',headers=AUTH).json()['billable_requests_enabled']
    assert client.post('/v1/recognitions',json=photo()).status_code==401
    response=client.post('/v1/recognitions',headers=AUTH,json=photo())
    assert response.status_code==200,response.text
    result=response.json()
    assert result['image_sha256']==hashlib.sha256(JPEG).hexdigest()
    assert result['candidates'][0]['label_capacity_ml']==1000
    body=confirmation(result)
    saved=client.post('/v1/beverages',headers=AUTH|{'Idempotency-Key':str(uuid4())},json=body)
    assert saved.status_code==201,saved.text
    record=saved.json()
    assert record['consumed_ml']==1000 and record['contribution']['beverage_total_ml']==1000
    assert 'recognition-v1:local_meta' in record['provenance'] and ADAPTER in record['provenance']
    exported=client.get('/v1/export',headers=AUTH).json()
    assert len(exported['local_recognition_receipts'])==1
    assert exported['training_examples']==[]
    assert ledger.read_bytes()==before


def test_local_correction_memory_is_separate_and_receipt_references_cannot_be_forged(local_camera):
    client,_,_=local_camera
    result=client.post('/v1/recognitions',headers=AUTH,json=photo()).json()
    body=confirmation(result)
    feedback={'image_sha256':result['image_sha256'],'source_mode':'local_meta',
              'original_candidate':result['candidates'][0], 'remember_for_me':True,'share_for_training':False}
    body|={'category':'Corrected water','consumed_ml':500,'consumption_assumption':None,
           'recognition_feedback':feedback}
    def save(value): return client.post('/v1/beverages',headers=AUTH|{'Idempotency-Key':str(uuid4())},json=value)
    assert save(body|{'recognition_id':str(uuid4())}).status_code==422
    assert save(body|{'recognition_feedback':feedback|{'image_sha256':'a'*64}}).status_code==422
    assert save(body|{'recognition_feedback':feedback|{'original_candidate':feedback['original_candidate']|{'identity':'Forged'}}}).status_code==422
    response=save(body)
    assert response.status_code==201,response.text
    again=client.post('/v1/recognitions',headers=AUTH,json=photo()).json()['candidates'][0]
    assert again['identity']=='DASANI Purified Water'
    assert again['personal_correction']['identity']=='Corrected water'


def test_local_mode_rejects_hosted_billing_configuration(tmp_path,monkeypatch):
    monkeypatch.setenv('HYDRA_AI_MODE','local_meta')
    monkeypatch.setenv('META_BILLABLE_REQUESTS_ENABLED','true')
    with pytest.raises(ValueError): create_app(tmp_path/'test.sqlite3',TOKEN)

def test_deleted_data_is_not_restored_by_a_late_local_camera_receipt(local_camera, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    client, _, _ = local_camera
    entered, release = threading.Event(), threading.Event()
    original = client.app.state.recognizer.analyze

    def paused(payload):
        entered.set()
        assert release.wait(timeout=10)
        return original(payload)

    monkeypatch.setattr(client.app.state.recognizer, 'analyze', paused)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(client.post, '/v1/recognitions', headers=AUTH, json=photo())
        try:
            assert entered.wait(timeout=10)
            deleted = client.delete('/v1/data', params={'confirm':'delete-all-my-data'}, headers=AUTH)
        finally:
            release.set()
        response = pending.result(timeout=10)
    assert deleted.status_code == 200
    assert response.status_code == 503
    assert client.get('/v1/export', headers=AUTH).json()['local_recognition_receipts'] == []
