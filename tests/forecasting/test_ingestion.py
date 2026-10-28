"""Offline ingestion checks; fixtures contain only invented values/identities."""
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile

import pytest

from ai.forecasting.ingestion import SOURCES, checked_bytes, download_source, load_qde, load_spectrophon


def _qde(tmp_path, monkeypatch, duplicate=False):
    columns = ['id', 'age [years]', 'running speed [km/h]', 'running interval', 'weight measured using Kern DE 150K2D [kg]']
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    for subject in range(1, 11):
        for interval in range(9):
            writer.writerow(dict(zip(columns, [subject, 30 if interval == 0 else '', 8 if interval == 0 else '', 0 if duplicate and interval == 1 else interval, 80 - interval * .2])))
    path = tmp_path / 'qde.csv'
    path.write_text(output.getvalue())
    monkeypatch.setitem(SOURCES['qde'], 'sha256', hashlib.sha256(path.read_bytes()).hexdigest())
    return path


def _spectro(tmp_path, monkeypatch, wrong_target=False):
    strings = ['initial', 'final', 'Gender', 'total weight loss', 'INVENTED PRIVATE NAME', '']
    rows = []
    def row(cells):
        rn = len(rows) + 1
        rows.append('<row r="%d">%s</row>' % (rn, ''.join('<c r="%s%d"%s><v>%s</v></c>' % (col, rn, ' t="s"' if string else '', value) for col, value, string in cells)))
    for i in range(200):
        strings.append(f'Subject no. {i+1}')
        row([('A', len(strings)-1, True)])
        # Repeat names and blank names must stay in one respective group.
        row([('A', 2, True), ('D', 30, False), ('G', 4 if i < 100 else 5, True)])
        row([('A', 0, True), ('E', 80, False), ('J', 500, False)])
        row([('A', 1, True), ('E', 79.8, False), ('J', 300, False)])
        row([('F', 3, True)])
        row([('F', .5 if wrong_target else .4, False)])
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    path = tmp_path / 'study.xlsx'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('xl/sharedStrings.xml', '<sst xmlns="%s">%s</sst>' % (ns, ''.join(f'<si><t>{s}</t></si>' for s in strings)))
        z.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="%s"><sheetData>%s</sheetData></worksheet>' % (ns, ''.join(rows)))
    monkeypatch.setitem(SOURCES['spectrophon'], 'sha256', hashlib.sha256(path.read_bytes()).hexdigest())
    return path


def test_checksum_fails_closed(tmp_path):
    p = tmp_path / 'bad.csv'
    p.write_text('not a study')
    with pytest.raises(ValueError, match='checksum'):
        checked_bytes(p, 'qde')


def test_raw_download_inside_repository_rejected():
    root = Path(__file__).resolve().parents[2]
    with pytest.raises(ValueError, match='outside'):
        download_source('spectrophon', root / 'data' / 'raw')


def test_qde_units_grouping_and_no_post_measurement_leakage(tmp_path, monkeypatch):
    records = load_qde(_qde(tmp_path, monkeypatch))
    assert len(records) == 80
    assert len({r['participant_id'] for r in records}) == 10
    assert records[0]['target_value_ml'] == pytest.approx(200)
    assert records[-1]['duration_minutes'] == 120
    assert records[0]['target_name'] == 'body_mass_loss_proxy_ml'
    assert records[0]['pre_mass_kg'] == 80
    assert 'post_mass_kg' not in records[0]
    assert all(r['temperature_c'] is None and not r['synthetic'] for r in records)


def test_qde_duplicate_interval_rejected(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match='duplicated'):
        load_qde(_qde(tmp_path, monkeypatch, duplicate=True))


def test_spectrophon_mass_balance_allowlist_and_private_repeat_grouping(tmp_path, monkeypatch):
    p = _spectro(tmp_path, monkeypatch)
    records = load_spectrophon(p)
    assert len(records) == 200
    assert len({r['participant_id'] for r in records}) == 2
    assert len({r['record_id'] for r in records}) == 200
    assert all(r['target_value_ml'] == pytest.approx(400) for r in records)
    assert 'INVENTED PRIVATE NAME' not in json.dumps(records)
    assert 'name' not in records[0]
    assert 'intake_ml' not in records[0]
    assert records == load_spectrophon(p)


def test_spectrophon_target_disagreement_rejected(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match='disagreement'):
        load_spectrophon(_spectro(tmp_path, monkeypatch, wrong_target=True))
