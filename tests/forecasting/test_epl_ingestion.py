"""Invented workbook fixtures; no public participant values are committed."""
import hashlib
from html import escape
import io
import json
from pathlib import Path
import zipfile

import pytest


def workbook(*, duplicate=False, private_id=False, missing_cache=False, wrong_target=False,
             wrong_rate=False, wrong_context=False, bad_unit=False) -> bytes:
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    strings = []
    def cell(address, value, *, formula=None):
        if isinstance(value, str):
            strings.append(value)
            return f'<c r="{address}" t="s"><v>{len(strings)-1}</v></c>'
        f = '' if formula is None else f'<f>{escape(formula)}</f>'
        v = '' if value is None else f'<v>{value}</v>'
        return f'<c r="{address}">{f}{v}</c>'
    sheets = {}
    for session, count in ((1, 14), (2, 17)):
        intake, target, rate = ('I', 'L', 'Q') if session == 1 else ('K', 'M', 'R')
        headers = {'A': 'Name', 'B': 'Age', 'D': 'Pre-training weight (kg)', 'F': 'Post-training weight (kg)',
                   intake: 'Fluid intake' if session == 1 else 'Fluid Intake',
                   target: 'Sweat Loss (L)' if session == 1 else 'Total Sweat Loss (L)',
                   rate: 'Sweat rate (L/hr)'}
        rows = ['<row r="1">'+''.join(cell(k+'1', v) for k,v in headers.items())+'</row>']
        for index in range(count):
            r = index+2
            participant = index+1 if session == 1 else index+15
            label = f'Participant {participant}'
            if session == 1 and index == 1 and duplicate:
                label = 'Participant 1'
            if session == 1 and index == 0 and private_id:
                label = 'INVENTED PRIVATE NAME'
            # pre70, post69.5, consumed0.25 L => 750 mL corrected proxy.
            values = {'A': label, 'B': 30, 'D': 70+index, 'F': 69.5+index, intake: 250 if bad_unit else .25,
                      target: 1. if wrong_target else .75,
                      rate: 2. if wrong_rate else .75*60/(84 if session == 1 else 75),
                      'ZZ': 'INVENTED PRIVATE FIELD; MODELLED HYDRATION 62%'}
            if session == 1 and index == 0 and missing_cache:
                values[target] = None
            body = ''.join(cell(k+str(r), v, formula='F2-D2+I2' if k==target else None) for k,v in values.items())
            rows.append(f'<row r="{r}">{body}</row>')
        for row, label, value in ((20 if session==1 else 23, 'Training Duration (min)',84 if session==1 else 75),
                                  (21 if session==1 else 24, 'Environmental Temperature (°C)',19 if session==1 else 23),
                                  (22 if session==1 else 25, 'Relative Humidity (%)',45 if session==1 else 67)):
            rows.append(f'<row r="{row}">'+cell('A'+str(row),label)+cell('B'+str(row),99 if wrong_context else value)+'</row>')
        sheets[f'xl/worksheets/sheet{session+1}.xml'] = f'<worksheet xmlns="{ns}"><sheetData>'+''.join(rows)+'</sheetData></worksheet>'
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as z:
        z.writestr('xl/sharedStrings.xml',f'<sst xmlns="{ns}">'+''.join('<si><t>'+escape(s)+'</t></si>' for s in strings)+'</sst>')
        for path, data in sheets.items():z.writestr(path,data)
    return stream.getvalue()


def fixture_file(tmp_path, monkeypatch, **changes):
    from ai.forecasting.epl_ingestion import SOURCE
    payload=workbook(**changes)
    path=tmp_path/'epl.xlsx';path.write_bytes(payload)
    monkeypatch.setitem(SOURCE,'sha256',hashlib.sha256(payload).hexdigest())
    monkeypatch.setitem(SOURCE,'size_bytes',len(payload))
    return path


def test_litres_to_ml_target_allowlist_and_disjoint_anonymous_ids(tmp_path,monkeypatch):
    from ai.forecasting.epl_ingestion import load_epl
    rows=load_epl(fixture_file(tmp_path,monkeypatch))
    assert len(rows)==len({r['participant_id'] for r in rows})==31
    assert {r['target_value_ml'] for r in rows}=={750.}
    assert {r['duration_minutes'] for r in rows}=={75.,84.}
    assert {r['temperature_c'] for r in rows}=={19.,23.}
    assert {r['humidity_percent'] for r in rows}=={45.,67.}
    assert all(r['age_years']==30 and not r['synthetic'] for r in rows)
    assert all(r['target_name']=='intake_corrected_mass_loss_proxy_ml' for r in rows)
    assert len({r['participant_id'] for r in rows if r['session_id']=='epl-v1:session-1'})==14
    assert len({r['participant_id'] for r in rows if r['session_id']=='epl-v1:session-2'})==17
    assert all('post_mass_kg' not in r and 'consumed_ml' not in r and 'urine_ml' not in r for r in rows)
    assert 'INVENTED PRIVATE FIELD' not in json.dumps(rows)
    assert rows==load_epl(fixture_file(tmp_path,monkeypatch))


@pytest.mark.parametrize('change,error',[
    ({'duplicate':True},'anonymous_participant'),({'private_id':True},'anonymous_participant'),
    ({'missing_cache':True},'cached_numeric'),({'wrong_target':True},'target_disagreement'),
    ({'wrong_rate':True},'rate_disagreement'),({'wrong_context':True},'session_context'),
    ({'bad_unit':True},'cached_numeric'),
])
def test_invalid_measurements_ids_and_cache_fail_closed_without_raw_echo(tmp_path,monkeypatch,change,error):
    from ai.forecasting.epl_ingestion import load_epl
    with pytest.raises(ValueError,match=error) as caught:
        load_epl(fixture_file(tmp_path,monkeypatch,**change))
    assert 'INVENTED PRIVATE' not in str(caught.value)


def test_unreviewed_source_bytes_and_archive_rejected(tmp_path,monkeypatch):
    from ai.forecasting.epl_ingestion import load_epl
    path=fixture_file(tmp_path,monkeypatch)
    path.write_bytes(path.read_bytes()+b'x')
    with pytest.raises(ValueError,match='size_or_checksum'):
        load_epl(path)
    path.write_bytes(b'not an xlsx')
    from ai.forecasting.epl_ingestion import SOURCE
    monkeypatch.setitem(SOURCE,'sha256',hashlib.sha256(path.read_bytes()).hexdigest())
    monkeypatch.setitem(SOURCE,'size_bytes',len(path.read_bytes()))
    with pytest.raises(ValueError,match='invalid_workbook'):
        load_epl(path)


def test_raw_cache_inside_repository_rejected_before_network():
    from ai.forecasting.epl_ingestion import download_epl
    with pytest.raises(ValueError,match='outside'):
        download_epl(Path(__file__).resolve().parents[2]/'data'/'raw-epl')



def test_optional_epl_evaluation_preserves_source_and_session_separation(tmp_path,monkeypatch):
    pytest.importorskip("sklearn")
    from ai.forecasting.epl_ingestion import load_epl
    from ai.forecasting.epl_evaluation import evaluate_epl
    rows=load_epl(fixture_file(tmp_path,monkeypatch))
    artifact, report=evaluate_epl(rows)
    assert artifact["runtime_use"]=="offline_research_only"
    assert artifact["features"]==["duration_minutes","pre_mass_kg","age_years"]
    assert len(report["partitions"]["test"]["participants"])==6
    assert len(report["partitions"]["calibration"]["participants"])==6
    assert report["interval"]["nominal_coverage"] is None
    assert report["holdout_origin"]=="new_same_study_participants"
    shifts=report["shifted_session_audit"]
    assert shifts["session-1-to-session-2"]["train_participants"]==14
    assert shifts["session-1-to-session-2"]["test_participants"]==17
    assert shifts["session-2-to-session-1"]["train_participants"]==17
    assert shifts["session-2-to-session-1"]["test_participants"]==14
    assert all(value["interval_kind"] is None for value in shifts.values())
    assert all(value["out_of_training_feature_range_participants"]==value["test_participants"] for value in shifts.values())
    assert set(shifts["session-1-to-session-2"]["comparison"])=={"cohort_rate_baseline","ridge","random_forest","gradient_boosting"}
    assert artifact["selected_model"]=="ridge"
    assert report["selected_test"]["mae_ml"]==pytest.approx(0.,abs=1e-7)


def test_epl_evaluation_rejects_origin_or_target_pooling(tmp_path,monkeypatch):
    pytest.importorskip("sklearn")
    from ai.forecasting.epl_ingestion import load_epl
    from ai.forecasting.epl_evaluation import evaluate_epl
    rows=load_epl(fixture_file(tmp_path,monkeypatch))
    rows[0]["target_name"]="body_mass_loss_proxy_ml"
    with pytest.raises(ValueError,match="epl_study_contract"):
        evaluate_epl(rows)
