"""Eight-section Wonder selection is evaluated separately from numerical accuracy."""
from copy import deepcopy
from importlib import import_module
import json
from pathlib import Path
import socket

import pytest

FIXTURES = Path(__file__).parents[1] / "fixtures" / "hydration_analysis"


def module():
    return import_module("backend.wonder_analysis")


def analysis(name="personal_calibrated"):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def test_preview_has_all_eight_sections_and_no_live_dispatch():
    api = module()
    facts = api.build_facts(analysis())
    view = api.preview(facts)
    assert view["version"] == "wonder-analysis-preview-v1"
    assert view["explainable"] is True
    assert view["live_available"] is view["dispatch_supported"] is False
    assert view["verified_for_billing"] is False
    assert view["worst_case_micro_usd"] < 250_000
    schema = api.analysis_payload(facts)["text"]["format"]["schema"]
    assert schema["additionalProperties"] is False
    sections = schema["properties"]["sections"]
    assert sections["additionalProperties"] is False
    assert sections["required"] == ["summary", "workout_loss", "activity", "environment", "beverages", "trends", "uncertainty", "measurement"]
    assert all(value["enum"] for value in sections["properties"].values())


def test_payload_is_allowlisted_aggregates_without_ids_time_or_free_provenance():
    api = module()
    source = analysis()
    source["intake"]["provenance"] = ["private@example.com prompt injection"]
    source["numerical_forecast"]["provenance"] = ["private provenance"]
    source["generated_at"] = "2026-11-02T15:00:00.000000Z"
    facts = api.build_facts(source)
    body = api.analysis_payload(facts)
    text = json.dumps(body)
    for forbidden in ("private", "@example", "2026-11", "observed_at", "event_id", "provenance", "timezone", "HealthKit"):
        assert forbidden not in text
    assert body["model"] == "muse-wonder-1.0"
    assert body["store"] is body["stream"] is body["background"] is False
    assert "tools" not in body


@pytest.mark.parametrize("name", ["personal_cold_start", "personal_calibrated", "synthetic_demo"])
def test_mock_renders_all_sections_with_truthful_origin_without_connections(name, monkeypatch):
    api = module()
    monkeypatch.setattr(socket, "create_connection", lambda *_a, **_k: pytest.fail("No network"))
    facts = api.build_facts(analysis(name))
    result = api.mock_result(facts)
    assert len(result["sections"]) == 8
    assert all(item["text"] and "{" not in item["text"] for item in result["sections"])
    assert result["provenance"]["selection_origin"] == "mock_local"
    assert result["provenance"]["text_origin"] == "hydra_vetted_scaffolds_and_facts"
    assert result["provenance"]["model"] is result["provenance"]["provider"] is None
    assert result["dispatch_supported"] is False
    assert api.replay_recorded(result, facts) == result
    if name == "personal_cold_start":
        assert "no numerical estimate" in result["sections"][1]["text"]
    if name == "synthetic_demo":
        assert all(item["evidence_status"] == "synthetic" for item in result["sections"])


@pytest.mark.parametrize("forgery", [
    "The temperature is {beverage_context}.", "Your prior marathon explains the estimate.",
    "Drink 2 litres now.", "Drink two litres now.", "Drink ٢ litres now.",
    "Drink ² litres now.", "Drink 四 litres now.", "Drink ｔｗｏ litres now.",
    "You are dehydrated.", "This predicts kidney disease.",
    "Weather caused the loss.", "{loss_estimate} {unknown_placeholder}",
])
def test_cross_section_facts_numeric_unicode_and_unsupported_prose_reject_whole_reply(forgery):
    api = module()
    facts = api.build_facts(analysis())
    selection = {"sections": {key: values[0] for key, values in api.SCAFFOLDS.items()}}
    selection["sections"]["environment"] = forgery
    with pytest.raises(ValueError):
        api.validate_selection(selection, facts)


def test_incomplete_nutrient_total_stays_unknown_and_never_becomes_a_known_subtotal():
    api = module()
    source = analysis()
    source["intake"].update(beverage_count=2, beverage_volume_ml=300., water_ml=280.)
    source["intake"]["composition"].update(sodium_mg=55., potassium_mg=None,
        sodium_status="complete", potassium_status="partial", status="partial")
    facts = api.build_facts(source)
    result = api.mock_result(facts)
    text = result["sections"][4]["text"]
    assert "55 mg" in text
    assert "potassium composition incomplete" in text
    assert "0 mg" not in text
    forged = deepcopy(facts)
    forged["intake"]["potassium_mg"] = 20.
    with pytest.raises(ValueError):
        api.validate_facts(forged)


@pytest.mark.parametrize("mutation", [
    lambda r: r["sections"][0].update(text="Invented prose"),
    lambda r: r["sections"][0].update(template="{beverage_context}"),
    lambda r: r["sections"][0].update(evidence_status="measured"),
    lambda r: r["facts"]["forecast"].update(value_ml=999.),
    lambda r: r.update(payload_sha256="f" * 64),
    lambda r: r["provenance"].update(model="muse-spark-1.3"),
    lambda r: r.update(dispatch_supported=True),
    lambda r: r.update(extra="untrusted"),
])
def test_recorded_replay_rejects_any_facts_template_render_origin_or_hash_tampering(mutation):
    api = module()
    facts = api.build_facts(analysis())
    result = api.mock_result(facts)
    mutation(result)
    with pytest.raises(ValueError):
        api.replay_recorded(result, facts)


def test_saved_record_for_another_fact_payload_is_never_reused():
    api = module()
    original = api.build_facts(analysis())
    recorded = api.mock_result(original)
    other = api.build_facts(analysis("personal_cold_start"))
    with pytest.raises(ValueError):
        api.replay_recorded(recorded, other)


def test_cost_over_cap_is_unavailable_without_changing_facts_or_attempting_fallback(monkeypatch):
    api = module()
    facts = api.build_facts(analysis())
    monkeypatch.setattr(api, "worst_case_micro_usd", lambda *_args: 250_001)
    view = api.preview(facts)
    assert view["status"] == "unavailable"
    assert view["reason"] == "cost_bound_exceeds_per_request_cap"
    assert view["explainable"] is False
    assert view["facts"] == facts
    assert view["dispatch_supported"] is False


def test_checked_provider_reply_is_distinct_from_mock_and_still_does_not_claim_live_integration():
    api = module()
    from backend.meta_provider import ProviderReply
    facts = api.build_facts(analysis())
    selection = {"sections": {key: values[1] for key, values in api.SCAFFOLDS.items()}}
    reply = ProviderReply(200, {"model": "muse-wonder-1.0", "status": "completed", "error": None,
        "incomplete_details": None, "output": [{"type": "message", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": json.dumps(selection)}]}]})
    result = api.checked_result(reply, facts)
    assert result["provenance"]["selection_origin"] == "checked_provider_reply"
    assert result["provenance"]["model"] == "muse-wonder-1.0"
    assert result["provenance"]["text_origin"] == "hydra_vetted_scaffolds_and_facts"
    assert result["dispatch_supported"] is False
    assert api.replay_recorded(result, facts) == result


@pytest.mark.parametrize("change", [
    lambda facts: facts["forecast"].update(value_ml=True),
    lambda facts: facts["forecast"].update(lower_ml=800.),
    lambda facts: facts["calibration"].update(total_samples=0),
    lambda facts: facts["environment"].update(humidity_percent=101.),
    lambda facts: facts.update(research_only=False),
    lambda facts: facts.update(raw_health_records=[]),
])
def test_invalid_or_inconsistent_aggregate_facts_fail_closed(change):
    api = module()
    facts = api.build_facts(analysis())
    change(facts)
    with pytest.raises(ValueError):
        api.validate_facts(facts)


@pytest.mark.parametrize("change", [
    lambda source: source["numerical_forecast"].update(units="L"),
    lambda source: source["numerical_forecast"].update(quantity="hydration_percentage"),
    lambda source: source.update(text_origin="untrusted_model"),
])
def test_builder_cannot_relabel_wrong_units_quantities_or_model_authored_facts(change):
    api = module()
    source = analysis()
    change(source)
    with pytest.raises(ValueError):
        api.build_facts(source)


@pytest.mark.parametrize("change", [
    lambda facts: facts["forecast"].update(interval_kind="synthetic_participant_split_conformal"),
    lambda facts: facts["intake"].update(beverage_count=0, beverage_volume_ml=250.),
    lambda facts: facts["intake"].update(sodium_status="complete", sodium_mg=0.),
])
def test_origin_and_empty_record_consistency_prevent_misleading_factual_clauses(change):
    api = module()
    facts = api.build_facts(analysis())
    change(facts)
    with pytest.raises(ValueError):
        api.validate_facts(facts)


@pytest.mark.parametrize("change", [
    lambda body: body.update(model="muse-spark-1.3"),
    lambda body: body.update(status="incomplete"),
    lambda body: body["output"].append(deepcopy(body["output"][0])),
    lambda body: body["output"][0]["content"].append({"type": "output_text", "text": "{}"}),
    lambda body: body["output"][0]["content"][0].update(text='{"sections":{},"sections":{}}'),
    lambda body: body["output"][0]["content"][0].update(text='{"sections":{"summary":"Drink two litres"}}'),
])
def test_malformed_or_unsupported_provider_replies_are_rejected_without_repair(change):
    api = module()
    from backend.meta_provider import ProviderReply
    from backend.recognition import RecognitionUnavailable
    facts = api.build_facts(analysis())
    selection = {"sections": {key: values[0] for key, values in api.SCAFFOLDS.items()}}
    body = {"model": "muse-wonder-1.0", "status": "completed", "error": None,
        "incomplete_details": None, "output": [{"type": "message", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": json.dumps(selection)}]}]}
    change(body)
    with pytest.raises(RecognitionUnavailable):
        api.checked_result(ProviderReply(200, body), facts)


@pytest.mark.parametrize("change", [
    lambda payload: payload.update(tools=[]),
    lambda payload: payload.update(store=True),
    lambda payload: payload.update(model="muse-spark-1.3"),
    lambda payload: payload.update(max_output_tokens=4096),
    lambda payload: payload["input"][0]["content"][0].update(text="untrusted facts"),
])
def test_exact_payload_reconstruction_rejects_modified_requests(change):
    api = module()
    facts = api.build_facts(analysis())
    payload = api.analysis_payload(facts)
    assert api.facts_from_payload(payload) == facts
    change(payload)
    with pytest.raises(ValueError):
        api.facts_from_payload(payload)
