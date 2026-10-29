"""Muse Wonder hydration-context payload, cost bound and parser tests. Fake replies only."""
import json
import socket

import pytest

from backend.hydration_context_v2 import SCENARIOS, build_scenario, supported_selection
from backend.meta_accounts import CAP
from backend.meta_policy import MAX_INPUT_TOKENS, OUTPUT_LIMIT
from backend.meta_provider import ProviderReply
from backend.recognition import RecognitionUnavailable
from backend.wonder_hydration import (MODEL, parse_selection, payload_sha256, preview, selection_schema,
                                      wonder_payload, worst_case_micro_usd)


@pytest.fixture(autouse=True)
def disabled_network(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("network forbidden"))


def reply(text, *, http_status=200, model=MODEL, **body_changes):
    body = {"model": model, "status": "completed", "error": None, "incomplete_details": None,
            "output": [{"type": "reasoning", "summary": []},
                       {"type": "message", "role": "assistant", "status": "completed",
                        "content": [{"type": "output_text", "text": text}]}]}
    return ProviderReply(http_status, body | body_changes)


def supported(scenario):
    return supported_selection(*build_scenario(scenario))


def test_payload_is_deterministic_wonder_only_and_bounded():
    for scenario in SCENARIOS:
        payload = wonder_payload(scenario)
        assert payload["model"] == "muse-wonder-1.0"
        assert payload["store"] is payload["stream"] is payload["background"] is False
        assert payload["max_output_tokens"] == OUTPUT_LIMIT == 512
        assert "tools" not in payload
        assert payload_sha256(payload) == payload_sha256(wonder_payload(scenario))
    assert len({payload_sha256(wonder_payload(name)) for name in SCENARIOS}) == len(SCENARIOS)
    with pytest.raises(ValueError):
        wonder_payload("user_supplied")


def test_payload_carries_only_server_owned_synthetic_context():
    text = wonder_payload("complete")["input"][0]["content"][0]["text"]
    sent = json.loads(text.split(" Context: ", 1)[1])
    context, prediction = build_scenario("complete")
    assert sent["context"] == context and sent["context"]["synthetic"] is True
    assert sent["prediction"]["value_ml"] == prediction["value_ml"]
    assert set(sent) == {"context", "prediction"}


def test_strict_schema_requires_every_field_and_forbids_extras():
    schema = selection_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert "title" not in json.dumps(schema) and "default" not in schema


def test_worst_case_cost_uses_wonder_prices_and_rounds_up():
    assert worst_case_micro_usd(1_000_000, 0) == 4_000_000
    assert worst_case_micro_usd(0, 1_000_000) == 20_000_000
    assert worst_case_micro_usd(1, 0) == 4
    assert worst_case_micro_usd(0, 1) == 20
    assert worst_case_micro_usd(1, 1) == 24
    for bad in (-1, 1.5, True, None):
        with pytest.raises(ValueError):
            worst_case_micro_usd(bad)


def test_full_context_bound_is_not_admissible_under_the_per_attempt_cap():
    result = preview("complete")
    assert result["full_context_bound_micro_usd"] == worst_case_micro_usd(MAX_INPUT_TOKENS) > CAP
    assert result["admissible_under_cap"] is False
    assert result["unreviewed_byte_bound_micro_usd"] < CAP
    assert result["dispatch_enabled"] is False and result["billing_evidence"] is False
    assert result["account_id"] == "georgiosaliba227"


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_supported_selection_parses_for_every_scenario(scenario):
    selection = supported(scenario)
    assert parse_selection(reply(json.dumps(selection)), scenario) == selection


@pytest.mark.parametrize("bad", [
    reply("{}", http_status=500), reply("{}", model="muse-spark-1.3"), reply("{}", status="failed"),
    ProviderReply(200, {"model": MODEL, "status": "incomplete", "error": None, "incomplete_details": {"reason": "max_output_tokens"}, "output": []}),
    ProviderReply(200, {"model": MODEL, "status": "completed", "error": {"code": "x"}, "incomplete_details": None, "output": []}),
    ProviderReply(200, {"model": MODEL, "status": "completed", "error": None, "incomplete_details": None, "output": []}),
    ProviderReply(200, {"model": MODEL, "status": "completed", "error": None, "incomplete_details": None, "output": "text"}),
])
def test_malformed_envelopes_fail_closed(bad):
    with pytest.raises(RecognitionUnavailable):
        parse_selection(bad, "complete")


def test_two_messages_or_two_parts_fail_closed():
    good = reply(json.dumps(supported("complete")))
    message = good.body["output"][1]
    with pytest.raises(RecognitionUnavailable):
        parse_selection(ProviderReply(200, good.body | {"output": [message, message]}), "complete")
    doubled = message | {"content": message["content"] * 2}
    with pytest.raises(RecognitionUnavailable):
        parse_selection(ProviderReply(200, good.body | {"output": [doubled]}), "complete")


@pytest.mark.parametrize("change", [
    {"factors": ["heart_rate_context"]},          # unsupported in the complete scenario
    {"contradictions": ["negative_mass_balance"]},  # invented contradiction
    {"numerical_abstention": True},
    {"uncertainty": ["synthetic_evidence_only"]},  # required uncertainty omitted
    {"daily_goal_ml": 2000},                       # extra field
    {"factors": ["workout_duration", "workout_duration"]},
])
def test_ungrounded_or_numeric_selections_are_rejected(change):
    with pytest.raises(RecognitionUnavailable):
        parse_selection(reply(json.dumps(supported("complete") | change)), "complete")


@pytest.mark.parametrize("text", ["not json", "[]", '{"factors": NaN}', "x" * 4097,
                                  '{"factors": [], "factors": []}'])
def test_invalid_text_is_rejected(text):
    with pytest.raises(RecognitionUnavailable):
        parse_selection(reply(text), "complete")


def test_contradiction_scenario_requires_the_contradiction():
    selection = supported("contradictory_mass")
    assert "negative_mass_balance" in selection["contradictions"]
    assert parse_selection(reply(json.dumps(selection)), "contradictory_mass")["numerical_abstention"] is True
    with pytest.raises(RecognitionUnavailable):
        parse_selection(reply(json.dumps(selection | {"contradictions": []})), "contradictory_mass")
