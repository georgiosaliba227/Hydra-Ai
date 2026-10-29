"""Hydration assistant: reviewed answers, safety-first matching, consented context. No network."""
import logging
import socket
import sqlite3
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from ai.assistant import ANSWERS, MAX_ANSWERS, PRIORITY, SUGGESTED, answers_for, match_topics
from backend.app import create_app

TOKEN = 'test-only-local-development-token-00000000'
AUTH = {'Authorization': f'Bearer {TOKEN}'}


@pytest.fixture(autouse=True)
def disabled_network(monkeypatch):
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: pytest.fail('network forbidden'))


@pytest.fixture
def database(tmp_path):
    return str(tmp_path / 'test.sqlite3')


@pytest.fixture
def client(database):
    with TestClient(create_app(db_path=database, api_token=TOKEN)) as c:
        yield c


def ask(client, **body):
    return client.post('/v1/assistant', json=body, headers=AUTH)


@pytest.mark.parametrize('question, expected', [
    ('Does coffee count toward my fluids?', ('coffee_caffeine',)),
    ('Is green tea dehydrating?', ('coffee_caffeine',)),
    ('Do I need more water on creatine?', ('creatine',)),
    ('How much do I sweat when running?', ('exercise_sweat', 'daily_needs')),
    ('Is milk better than water after the gym?', ('exercise_sweat', 'beverage_types')),
    ('Can my HRV show dehydration?', ('heart_rate',)),
    ('Should I drink more in hot weather?', ('weather',)),
    ('What does my total today mean?', ('logged_intake',)),
    ('What should I eat for brunch?', ('scope',)),
    ('   hello   ', ('scope',)),
])
def test_free_text_matching(question, expected):
    assert match_topics(question) == expected


@pytest.mark.parametrize('question', [
    'I fainted after my run', 'I feel confused and dizzy in the heat', 'I have chest pain while training',
    'I think I have heat stroke', "I can't keep fluids down", 'No urine since this morning',
])
def test_urgent_symptoms_always_escalate_first(question):
    topics = match_topics(question)
    assert topics[0] == 'urgent' and len(topics) <= MAX_ANSWERS


@pytest.mark.parametrize('question', ['I am pregnant, how much should I drink daily?', 'I take a diuretic medication',
                                      'I have kidney disease'])
def test_medical_wording_adds_the_clinician_answer(question):
    assert 'medical_scope' in match_topics(question)
    assert match_topics(question)[0] in ('urgent', 'medical_scope')


def test_reviewed_answers_avoid_prescriptions_and_cite_evidence():
    for topic, answer in ANSWERS.items():
        assert answer.evidence, topic
        lowered = answer.text.lower()
        for banned in ('you are dehydrated', 'drink at least', ' ml per', 'litres per day', 'liters per day'):
            assert banned not in lowered, (topic, banned)
    assert set(PRIORITY) | {'scope'} == set(ANSWERS)
    for question_id, (text, topics) in SUGGESTED.items():
        assert text.endswith('?') and answers_for(topics)


def test_answers_for_rejects_unknown_duplicate_or_excess_topics():
    for bad in ((), ('made_up',), ('creatine', 'creatine'), tuple(PRIORITY[:MAX_ANSWERS + 1])):
        with pytest.raises(ValueError):
            answers_for(bad)


def test_suggested_question_returns_reviewed_answer_with_evidence(client):
    questions = client.get('/v1/assistant/questions', headers=AUTH).json()['questions']
    assert [q['id'] for q in questions] == list(SUGGESTED)
    result = ask(client, question_id='creatine_water').json()
    assert result['topics'] == ['creatine'] and result['escalation'] is False
    [answer] = result['answers']
    assert answer['text'] == ANSWERS['creatine'].text
    assert answer['evidence'][0]['url'].startswith('https://pmc.ncbi.nlm.nih.gov/')
    assert result['provenance'] == {'mode': 'local_rules', 'provider': None, 'model': None, 'answer_origin': 'reviewed_text'}
    assert result['intake_context'] is None


def test_consented_context_uses_engine_total_for_that_day(client):
    for ml, at in ((250, '2026-10-28T08:00:00Z'), (400, '2026-10-28T20:00:00Z'), (300, '2026-10-27T20:00:00Z')):
        body = dict(category='water', consumed_ml=ml, consumed_at=at, timezone='Europe/Paris', source='manual')
        assert client.post('/v1/beverages', json=body, headers=AUTH | {'Idempotency-Key': str(uuid4())}).status_code == 201
    result = ask(client, question_id='logged_meaning', context_scope='today_logged_total',
                 date='2026-10-28', timezone='Europe/Paris').json()
    assert result['intake_context']['beverage_total_ml'] == 650
    assert 'not a hydration measurement' in result['intake_context']['note']


@pytest.mark.parametrize('body', [
    {}, {'question': '   '}, {'question': 'x' * 301}, {'question': 'coffee?', 'question_id': 'coffee_counts'},
    {'question_id': 'made_up'}, {'question': 'coffee?', 'context_scope': 'today_logged_total'},
    {'question': 'coffee?', 'date': '2026-10-28', 'timezone': 'UTC'},
    {'question': 'coffee?', 'context_scope': 'today_logged_total', 'date': '2026-10-28', 'timezone': 'Mars/Base'},
    {'question': 'coffee?', 'context_scope': 'all_health_records'}, {'question': 'coffee?', 'heart_rate': 80},
])
def test_invalid_requests_are_rejected_without_echo(client, body):
    response = ask(client, **body)
    assert response.status_code == 422
    assert 'coffee' not in response.text


def test_questions_are_never_stored_or_logged(client, database, caplog):
    secret = 'my-private-question-marker coffee'
    with caplog.at_level(logging.DEBUG):
        assert ask(client, question=secret).status_code == 200
    assert 'my-private-question-marker' not in caplog.text
    with sqlite3.connect(database) as connection:
        dump = '\n'.join(connection.iterdump())
    assert 'my-private-question-marker' not in dump


def test_assistant_requires_auth(client):
    assert client.post('/v1/assistant', json={'question': 'coffee?'}).status_code == 401
    assert client.get('/v1/assistant/questions').status_code == 401
