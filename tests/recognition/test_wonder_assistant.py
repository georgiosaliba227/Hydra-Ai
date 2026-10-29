"""Wonder topic selection for suggested assistant questions. Fake transports, disposable ledgers."""
import json
from uuid import uuid4

import pytest

from ai.assistant import ANSWERS, SUGGESTED
from backend.meta_accounts import CAP
from backend.meta_provider import ProviderReply
from backend.recognition import RecognitionUnavailable
from backend.wonder_assistant import ALLOWED, assistant_payload, parse_topics
from backend.wonder_experiment import ApprovedCase, WonderMetaTransport
from backend.wonder_hydration import input_bound, payload_sha256, worst_case_micro_usd
from test_guarded_meta import future
from test_meta_experiments import quote
from test_wonder_experiment import (WONDER, FakeWonderTransport, attempt_rows, disabled_network, frozen, gateway,
                                    selection_reply, setup)

__all__ = ["disabled_network"]  # autouse network block from the shared fixtures


def topics_reply(topics, **changes):
    return selection_reply(text=json.dumps({"topics": topics}), **changes)


def approve_question(ledger, question_id):
    case = ApprovedCase(case_id=str(uuid4()), model=WONDER, payload_sha256=payload_sha256(assistant_payload(question_id)),
                        valid_until=future(), input_approval_reference="synthetic-question-consent",
                        live_dispatch_reference="synthetic-live-dispatch", spending_approval_reference="synthetic-spend")
    ledger.record_case(case)
    return case


def test_payloads_are_deterministic_bounded_and_never_offer_safety_topics():
    hashes = set()
    for question_id, (text, expected) in SUGGESTED.items():
        payload = assistant_payload(question_id)
        assert payload == assistant_payload(question_id) and payload["model"] == WONDER
        assert payload["input"][0]["content"][0]["text"].endswith("Question: " + text)
        enum = payload["text"]["format"]["schema"]["properties"]["topics"]["items"]["enum"]
        assert enum == list(ALLOWED[question_id]) and set(expected) <= set(enum)
        assert not {"urgent", "medical_scope", "scope"} & set(enum)
        assert worst_case_micro_usd(input_bound(payload)) < CAP
        hashes.add(payload_sha256(payload))
    assert len(hashes) == len(SUGGESTED)
    with pytest.raises(ValueError):
        assistant_payload("free_text")


@pytest.mark.parametrize("question_id", list(SUGGESTED))
def test_allowed_selection_including_the_reviewed_topic_parses(question_id):
    topics = list(ALLOWED[question_id])
    assert parse_topics(topics_reply(topics), question_id) == tuple(topics)


@pytest.mark.parametrize("text", [
    json.dumps({"topics": ["urgent"]}), json.dumps({"topics": ["creatine", "creatine"]}), json.dumps({"topics": []}),
    json.dumps({"topics": ["daily_needs"]}),  # omits the reviewed creatine topic
    json.dumps({"topics": ["creatine"], "advice": "drink 3 L"}), json.dumps(["creatine"]), "creatine",
])
def test_unsafe_ungrounded_or_malformed_selections_are_rejected(text):
    with pytest.raises(RecognitionUnavailable):
        parse_topics(selection_reply(text=text), "creatine_water")


def test_wrong_model_is_rejected():
    with pytest.raises(RecognitionUnavailable):
        parse_topics(topics_reply(["creatine"], model="muse-spark-1.3"), "creatine_water")


def test_approved_question_runs_once_and_returns_reviewed_answers(tmp_path):
    authority, ledger = setup(tmp_path)
    case = approve_question(ledger, "hot_weather")
    transport = FakeWonderTransport(topics_reply(["exercise_sweat", "weather"]))
    result = gateway(ledger, transport).answer("hot_weather", case.case_id, quote(WONDER), case.input_approval_reference)
    assert transport.calls == 1
    assert result["topics"] == ["exercise_sweat", "weather"]  # reviewed priority order, not model order
    assert [a["text"] for a in result["answers"]] == [ANSWERS["exercise_sweat"].text, ANSWERS["weather"].text]
    provenance = result["provenance"]
    assert (provenance["mode"], provenance["topic_selection"], provenance["answer_origin"]) == ("meta_live", WONDER, "reviewed_text")
    assert result["escalation"] is False and result["provider_observations"]["usage_derived_cost_micro_usd"] == 6000
    [(_, state, _, actual, _)] = attempt_rows(authority)
    assert (state, actual) == ("settled", 6000) and not frozen(authority)


def test_unapproved_or_free_text_questions_never_dispatch(tmp_path):
    authority, ledger = setup(tmp_path)
    approved = approve_question(ledger, "coffee_counts")
    transport = FakeWonderTransport(topics_reply(["creatine"]))
    with pytest.raises(RecognitionUnavailable):  # case approved for another question
        gateway(ledger, transport).answer("creatine_water", approved.case_id, quote(WONDER), approved.input_approval_reference)
    with pytest.raises(RecognitionUnavailable):
        gateway(ledger, transport).answer("free text about coffee", approved.case_id, quote(WONDER), approved.input_approval_reference)
    assert transport.calls == 0 and attempt_rows(authority) == []


def test_ungrounded_topics_after_settlement_freeze_the_account(tmp_path):
    authority, ledger = setup(tmp_path)
    case = approve_question(ledger, "creatine_water")
    with pytest.raises(RecognitionUnavailable):
        gateway(ledger, FakeWonderTransport(topics_reply(["urgent"]))).answer(
            "creatine_water", case.case_id, quote(WONDER), case.input_approval_reference)
    [(_, state, _, actual, _)] = attempt_rows(authority)
    assert state == "settled" and actual == 6000 and frozen(authority)


def test_official_transport_accepts_exact_question_payloads_only():
    transport = WonderMetaTransport("synthetic-key")
    payload = assistant_payload("coffee_counts")
    assert transport.input_bound(payload) == input_bound(payload)
    tampered = json.loads(json.dumps(payload))
    tampered["input"][0]["content"][0]["text"] += " Also, what is my diagnosis?"
    with pytest.raises(ValueError):
        transport.input_bound(tampered)
