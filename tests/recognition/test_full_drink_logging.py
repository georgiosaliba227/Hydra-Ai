"""The user declares whole-liquid consumption; inference alone never logs it."""
from datetime import datetime, timezone
from uuid import uuid4
import pytest

from test_camera_corrections import camera, save, analyze
from test_guarded_meta import AUTH


def body(**changes):
    return {'category':'Tea','consumed_ml':200,'container_ml':None,
            'consumed_at':datetime.now(timezone.utc).isoformat(),'timezone':'UTC',
            'source':'confirmed_recognition','consumption_assumption':'entire_liquid'}|changes


def test_unknown_capacity_does_not_invent_a_container_and_assumption_replays(camera):
    _,client,_=camera
    request=body();key=str(uuid4())
    response=save(client,request,key)
    assert response.status_code==201
    record=response.json()
    assert record.get('container_ml') is None
    assert record['consumption_assumption']=='entire_liquid'
    assert 'user_assumed_entire_liquid' in record['provenance']
    assert record['contribution']['beverage_total_ml']==200
    assert record['contribution']['estimated_water_ml'] is None
    replay=save(client,request,key)
    assert replay.status_code==200 and replay.json()==record
    assert len(client.get('/v1/beverages',headers=AUTH).json()['items'])==1


@pytest.mark.parametrize('changes',[
    {'consumption_assumption':'full_container'},
    {'consumption_assumption':'full_container','container_ml':300},
    {'container_ml':150}, {'consumption_assumption':True},
    {'consumption_assumption':'automatic_ai_log'},
    {'source':'manual'},
    {'beverage_type':'   '},
])
def test_invalid_assumption_writes_nothing(camera,changes):
    _,client,_=camera
    assert save(client,body(**changes)).status_code==422
    assert client.get('/v1/beverages',headers=AUTH).json()['items']==[]


def test_partial_correction_clears_full_container_assumption(camera):
    _,client,_=camera
    created=save(client,body(container_ml=250,consumed_ml=250,consumption_assumption='full_container'))
    assert created.status_code==201
    record=created.json()
    assert 'user_assumed_full_container' in record['provenance']
    endpoint='/v1/beverages/'+record['id']
    change={'revision':1,'consumed_ml':125}
    response=client.patch(endpoint,headers=AUTH,json=change)
    assert response.status_code==200
    corrected=response.json()
    assert corrected['consumed_ml']==125 and corrected.get('consumption_assumption') is None
    assert 'user_assumed_full_container' not in corrected['provenance']
    assert 'user_corrected' in corrected['provenance']
    assert client.patch(endpoint,headers=AUTH,json=change).json()==corrected


def test_manual_partial_amount_remains_supported_with_unknown_capacity(camera):
    _,client,_=camera
    response=save(client,body(consumption_assumption=None,consumed_ml=75))
    assert response.status_code==201
    assert not any(p.startswith('user_assumed_') for p in response.json()['provenance'])


def test_corrected_type_and_unknown_capacity_are_remembered_without_training_consumption(camera):
    _,client,_=camera
    original=analyze(client)
    feedback={'source_mode':'mock','image_sha256':original['image_sha256'],
              'original_candidate':original['candidates'][0],'remember_for_me':True,
              'share_for_training':False,'corrected_liquid_ml':240}
    response=save(client,body(beverage_type='Tea',recognition_feedback=feedback))
    assert response.status_code==201
    assert response.json()['beverage_type']=='Tea'
    memory=analyze(client)['candidates'][0]['personal_correction']
    assert memory['beverage_type']=='Tea'
    assert memory['container_ml'] is None and memory['liquid_ml']==240
    exported=client.get('/v1/export',headers=AUTH).json()
    assert 'consumption_assumption' not in exported['recognition_corrections'][0]
