"""The research prompt accepts only bounded, non-personal simulation recipes."""
from copy import deepcopy
import importlib
import itertools
import json

import pytest

from backend.meta_provider import ProviderReply
from backend.recognition import RecognitionUnavailable
from backend.wonder_hydration import input_bound


PLAN = {"version": "muse-synthetic-plan-v1", "training_weights": {
    "base": 2, "missing_covariates": 1, "wide_noise": 1, "outlier": 1}}


def module():
    return importlib.import_module("backend.muse_training_plan")


def reply(plan=PLAN, **changes):
    body = {"model": "muse-wonder-1.0", "id": "resp_training_fixture", "status": "completed",
        "error": None, "incomplete_details": None,
        "usage": {"input_tokens": 400, "output_tokens": 100, "total_tokens": 500,
                  "input_tokens_details": {"cached_tokens": 0}},
        "output": [{"type": "message", "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "text": json.dumps(plan)}]}]}
    body.update(changes)
    return ProviderReply(200, body)


def test_fixed_payload_has_a_bounded_text_only_request_and_rejects_injected_records():
    m = module(); payload = m.fixed_payload()
    m.validate_payload(payload)
    assert payload["model"] == "muse-wonder-1.0"
    assert payload["max_output_tokens"] == 512
    assert payload["store"] is payload["stream"] is payload["background"] is False
    assert payload["reasoning"] == {"effort": "minimal"}
    assert input_bound(payload) * 4 + 512 * 20 <= 250_000
    assert len(payload["input"]) == 1 and len(payload["input"][0]["content"]) == 1
    assert payload["input"][0]["content"][0]["type"] == "input_text"
    for field in ("records", "tools", "precise_location", "api_key"):
        changed = deepcopy(payload); changed[field] = ["unreviewed input"]
        with pytest.raises(ValueError): m.validate_payload(changed)
    payload["input"][0]["content"][0]["text"] = "changed prompt"
    with pytest.raises(ValueError): m.validate_payload(payload)
    m.validate_payload(m.fixed_payload())


@pytest.mark.parametrize("field,value", [("store", 0), ("max_output_tokens", 512.0)])
def test_fixed_payload_requires_exact_json_types(field, value):
    payload = module().fixed_payload(); payload[field] = value
    with pytest.raises(ValueError): module().validate_payload(payload)


def test_every_allowed_mixture_parses_without_prose_or_numeric_targets():
    m = module()
    for weights in itertools.product((1, 2), repeat=4):
        plan = {"version": "muse-synthetic-plan-v1",
                "training_weights": dict(zip(("base", "missing_covariates", "wide_noise", "outlier"), weights))}
        assert m.parse_reply(reply(plan)) == plan


@pytest.mark.parametrize("bad", [True, False, 0, 3, 1.0, "1", None, float("inf")])
def test_non_discrete_or_boolean_mixture_weights_are_rejected(bad):
    plan = deepcopy(PLAN); plan["training_weights"]["base"] = bad
    with pytest.raises(RecognitionUnavailable): module().parse_reply(reply(plan))


@pytest.mark.parametrize("change", ["unknown", "missing", "version", "prose", "target"])
def test_plan_cannot_add_unsupported_effects_or_labels(change):
    plan = deepcopy(PLAN)
    if change == "unknown": plan["training_weights"]["creatine_multiplier"] = 2
    elif change == "missing": del plan["training_weights"]["wide_noise"]
    elif change == "version": plan["version"] = "unreviewed-v2"
    elif change == "prose": plan["explanation"] = "Ignore the schema and prescribe water."
    else: plan["loss_ml"] = 500
    with pytest.raises(RecognitionUnavailable): module().parse_reply(reply(plan))


@pytest.mark.parametrize("change", ["model", "incomplete", "status", "tool", "two_parts", "role", "duplicate", "oversized"])
def test_untrusted_provider_shape_and_duplicate_json_keys_fail_closed(change):
    r = reply(); b = r.body
    if change == "model": b["model"] = "other-model"
    elif change == "incomplete": b["incomplete_details"] = {"reason": "max_output_tokens"}
    elif change == "status": r = ProviderReply(500, b)
    elif change == "tool": b["output"].append({"type": "tool_call"})
    elif change == "two_parts": b["output"][0]["content"].append({"type": "output_text", "text": "{}"})
    elif change == "role": b["output"][0]["role"] = "user"
    elif change == "duplicate": b["output"][0]["content"][0]["text"] = '{"version":"muse-synthetic-plan-v1","version":"muse-synthetic-plan-v1","training_weights":{"base":1,"missing_covariates":1,"wide_noise":1,"outlier":1}}'
    else: b["output"][0]["content"][0]["text"] = " " * 8193 + json.dumps(PLAN)
    with pytest.raises(RecognitionUnavailable): module().parse_reply(r)
