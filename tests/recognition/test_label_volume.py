"""Deterministic capacity from unverified model-transcribed label text."""
import pytest

from backend.label_volume import label_capacity_ml
from test_camera_corrections import camera, analyze


@pytest.mark.parametrize('text,expected',[
    ('NET 500 mL',500), ('0.75 L',750), ('NET CONTENTS: 1 litre',1000),
    ('16.9 FL OZ (500 mL)',500), ('330 millilitres',330),
    ('Serving size 100 mL. NET 500 mL',500),
    ('NET 500 mL. Serving size 100 mL',500),
    ('500 mL / 0.5 L',500),
    ('Serving size 237 mL; two servings per bottle',None),
    ('Nutrition facts per 250 mL',None),
    ('Per 200 mL: energy 96 kcal',None),
    ('Nutrition facts: per cup (250 mL)',None),
    ('Portion size 250 mL',None),
    ('NET CONTENTS 1 L. Nutrition per 250 mL',1000),
    ('500 mL and 750 mL',None), ('20 fl oz',None),
    ('-500 mL',None), ('1e3 mL',None), ('0 mL',None),
    ('6 L',None), ('0.0001 L',None), ('25 CALORIES 2g SUGAR',None),
    (None,None),
])
def test_metric_capacity_requires_one_unambiguous_container_size(text,expected):
    assert label_capacity_ml(text)==expected


def test_api_exposes_label_size_separately_from_raw_model_capacity(camera):
    app,client,_=camera
    original=app.state.recognizer.analyze
    def response(payload):
        value=original(payload)
        value['candidates'][0]|={'container_ml':600,'visible_label_text':'NET 500 mL; serving size 100 mL'}
        return value
    app.state.recognizer.analyze=response
    candidate=analyze(client)['candidates'][0]
    assert candidate['container_ml']==600, 'Do not rewrite the original visual prediction'
    assert candidate['label_capacity_ml']==500


def test_one_liter_label_is_container_capacity_not_a_visual_fill_guess(camera):
    app,client,_=camera
    original=app.state.recognizer.analyze
    def response(payload):
        value=original(payload)
        value['candidates'][0]|={
            'container_ml':1000,
            'visible_label_text':'DASANI PURIFIED WATER Enhanced with minerals for a pure, fresh taste 1 LITER',
            'estimated_liquid_ml_min':900,'estimated_liquid_ml_max':1000,'volume_basis':'visual_estimate'}
        return value
    app.state.recognizer.analyze=response
    candidate=analyze(client)['candidates'][0]
    assert candidate['label_capacity_ml']==1000
    assert (candidate['estimated_liquid_ml_min'],candidate['estimated_liquid_ml_max'])==(900,1000)
    assert label_capacity_ml('1LITER')==1000
