"""Model labels must remain usable at the Swift confirmation boundary."""
import json
import sqlite3

import pytest

from backend.meta_accounts import ACCOUNTS
from backend.meta_gateway import GuardedMetaGateway
from backend.meta_observations import read_observation
from backend.meta_provider import parse_recognition
from backend.recognition import RecognitionUnavailable
from test_guarded_meta import FakeNotifier, FakeTransport, image, reply, setup


def response_with(**fields):
    response = reply()
    part = response.body["output"][0]["content"][0]
    body = json.loads(part["text"])
    body["candidates"][0].update(fields)
    part["text"] = json.dumps(body)
    return response


@pytest.mark.parametrize("field", ["category", "brand", "product"])
@pytest.mark.parametrize("blank", [" ", "\t\n", "\u2003"])
def test_blank_provider_labels_are_rejected_before_success_receipt(field, blank):
    with pytest.raises(RecognitionUnavailable):
        parse_recognition(response_with(**{field: blank}), "00000000-0000-0000-0000-000000000001")


def test_surrounding_whitespace_is_normalized_and_label_transcription_is_verbatim():
    result = parse_recognition(response_with(category="  tea\n", brand=" Example ", product=" Iced tea ",
        uncertainty_reasons=["  Verify capacity\n"], visible_label_text="  300 mL  "),
        "00000000-0000-0000-0000-000000000001")
    candidate = result.candidates[0]
    assert (candidate.identity, candidate.category, candidate.brand, candidate.product) == ("Iced tea", "tea", "Example", "Iced tea")
    assert candidate.uncertainty_reasons == ["Verify capacity"]
    assert candidate.visible_label_text == "  300 mL  "
    assert candidate.product_id is None and "nutrition" not in candidate.model_dump()


def test_blank_uncertainty_is_not_presented_as_model_explanation():
    with pytest.raises(RecognitionUnavailable):
        parse_recognition(response_with(uncertainty_reasons=[" \n"]), "00000000-0000-0000-0000-000000000001")


def test_unusable_model_label_keeps_usage_and_quarantines_without_retry(tmp_path):
    ledger = setup(tmp_path)
    transport = FakeTransport(response=response_with(product=" \n"))
    gateway = GuardedMetaGateway(ledger, ACCOUNTS[0], transport, FakeNotifier())
    with pytest.raises(RecognitionUnavailable):
        gateway.analyze(image())
    with sqlite3.connect(ledger.path) as db:
        attempt, recognized, actual = db.execute("SELECT id, recognized, actual FROM live_attempts").fetchone()
        assert db.execute("SELECT frozen FROM live_accounts").fetchone()[0] == 1
    assert recognized == 0 and actual is not None
    observation = read_observation(ledger.path, attempt)
    assert observation["outcome"] == "output_rejected"
    assert observation["usage"]["output_tokens"] == 50
    assert observation["result_sha256"] is None
    with pytest.raises(RecognitionUnavailable):
        gateway.analyze(image())
    assert transport.calls == 1
