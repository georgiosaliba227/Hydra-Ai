"""Synthetic ledgers only; no HTTP, credentials or provider claims."""
import json
from pathlib import Path
import sqlite3

import pytest

from backend.meta_accounts import ACCOUNTS
from backend.meta_budget import BudgetDenied
from backend.meta_gateway import GuardedMetaGateway
from backend.meta_observations import EVENT, read_observation, record_observation, result_fingerprint
from backend.meta_provider import OfficialMetaTransport, ProviderReply
from backend.recognition import RecognitionUnavailable
from test_guarded_meta import setup, image, HASH, IMAGE, JPEG, FakeTransport, FakeNotifier, reply
from test_controlled_tests import finality


def analyze(ledger, transport=None):
    return GuardedMetaGateway(ledger, ACCOUNTS[0], transport or FakeTransport(), FakeNotifier()).analyze(image())


def attempt_id(ledger):
    with sqlite3.connect(ledger.path) as db:
        return db.execute("SELECT id FROM live_attempts").fetchone()[0]


def test_observation_binds_result_usage_and_pending_invoice_without_bodies(tmp_path):
    ledger = setup(tmp_path)
    result = analyze(ledger)
    before = Path(ledger.path).read_bytes()
    item = read_observation(ledger.path, result.recognition_id)
    assert Path(ledger.path).read_bytes() == before
    assert item["account_id"] == ACCOUNTS[0] and item["purpose"] == "camera"
    assert item["provider_id"] == "resp_testonly" and item["input_sha256"] == HASH
    assert item["result_sha256"] == result_fingerprint(result.model_dump(mode="json"))
    assert item["outcome"] == "success" and item["transport_kind"] == "injected_test_transport"
    assert item["provider_http_status"] == 200
    assert item["api_latency_ms"] >= 0
    assert item["usage"] == {"input_tokens": 100, "output_tokens": 50, "cached_tokens": 0, "total_tokens": 150}
    assert item["usage_cost_micro_usd"] == 338 and item["final_gross_micro_usd"] is None
    assert item["billing_status"] == "usage_settled_invoice_pending"
    assert JPEG not in before and IMAGE.encode() not in before and b"Capacity uncertain" not in before
    assert "explanations" not in item and "candidates" not in item and "key_sha256" not in item


def test_final_invoice_is_separate_from_usage_settlement(tmp_path):
    ledger = setup(tmp_path)
    result = analyze(ledger)
    ledger.record_invoice_finality(finality(ledger, result.recognition_id))
    item = read_observation(ledger.path, result.recognition_id)
    assert item["billing_status"] == "invoice_verified" and item["final_gross_micro_usd"] == 338
    assert "synthetic-provider-invoice-only" not in json.dumps(item)


@pytest.mark.parametrize("transport,outcome,amount", [
    (FakeTransport(fault=TimeoutError("secret URL/body/key")), "transport_error", None),
    (FakeTransport(ProviderReply(429, {"error": {"message": "secret error"}})), "usage_unresolved", None),
    (FakeTransport(reply(output=[])), "output_rejected", 338),
])
def test_failures_have_safe_classification_and_never_fake_zero_cost(tmp_path, transport, outcome, amount):
    ledger = setup(tmp_path)
    with pytest.raises(RecognitionUnavailable):
        analyze(ledger, transport)
    item = read_observation(ledger.path, attempt_id(ledger))
    assert item["outcome"] == outcome and item["result_sha256"] is None
    assert item["api_latency_ms"] >= 0 and item["usage_cost_micro_usd"] == amount
    assert item["provider_http_status"] == (None if outcome == "transport_error" else 429 if amount is None else 200)
    assert item["final_gross_micro_usd"] is None and transport.calls == 1
    assert b"secret" not in Path(ledger.path).read_bytes()
    with pytest.raises(RecognitionUnavailable):
        analyze(ledger, transport)
    assert transport.calls == 1


def test_no_attempt_no_observation_when_real_bound_is_unapproved(tmp_path, monkeypatch):
    ledger = setup(tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail("No network is authorized")
    monkeypatch.setattr("http.client.HTTPSConnection", forbidden)
    with pytest.raises(RecognitionUnavailable):
        analyze(ledger, OfficialMetaTransport("synthetic-key"))
    with sqlite3.connect(ledger.path) as db:
        assert db.execute("SELECT COUNT(*) FROM live_attempts").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM live_events WHERE kind=?", (EVENT,)).fetchone()[0] == 0


def test_observation_cannot_be_replaced(tmp_path):
    ledger = setup(tmp_path)
    result = analyze(ledger)
    with pytest.raises(BudgetDenied):
        record_observation(ledger, result.recognition_id, purpose="camera", result=result.model_dump(mode="json"),
                           latency_ms=0, outcome="success", transport=FakeTransport())
    with pytest.raises(ValueError):
        record_observation(ledger, result.recognition_id, purpose="camera", result=None,
                           latency_ms=0, outcome="success", transport=FakeTransport())


@pytest.mark.parametrize("mutation", [
    "UPDATE live_attempts SET actual=0",
    "UPDATE live_attempts SET usage='{}'",
    "UPDATE live_attempts SET provider_id='not-a-provider-id'",
    "UPDATE live_attempts SET recognized=0",
    "UPDATE live_events SET reference='bad' WHERE kind='model_observation_v1'",
    "DELETE FROM live_events WHERE kind='model_observation_v1'",
    "UPDATE live_permit SET permit='{}'",
])
def test_corrupt_or_missing_provenance_fails_closed(tmp_path, mutation):
    ledger = setup(tmp_path)
    result = analyze(ledger)
    with sqlite3.connect(ledger.path) as db:
        db.execute(mutation)
    with pytest.raises(BudgetDenied):
        read_observation(ledger.path, result.recognition_id)


def test_read_never_creates_a_ledger_and_rejects_symlink_or_public_file(tmp_path):
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(BudgetDenied):
        read_observation(missing, "00000000-0000-0000-0000-000000000000")
    assert not missing.exists()
    ledger = setup(tmp_path)
    result = analyze(ledger)
    link = tmp_path / "link.sqlite3"
    link.symlink_to(ledger.path)
    with pytest.raises(BudgetDenied):
        read_observation(link, result.recognition_id)
    Path(ledger.path).chmod(0o644)
    with pytest.raises(BudgetDenied):
        read_observation(ledger.path, result.recognition_id)


def test_result_digest_changes_if_evaluation_output_was_replaced():
    first = {"candidates": [{"category": "tea", "brand": None}], "mode": "meta_live"}
    second = {"mode": "meta_live", "candidates": [{"brand": None, "category": "tea"}]}
    assert result_fingerprint(first) == result_fingerprint(second)
    second["candidates"][0]["category"] = "water"
    assert result_fingerprint(first) != result_fingerprint(second)
    with pytest.raises(ValueError):
        result_fingerprint({"latency": float("nan")})


def test_official_transport_label_is_implementation_evidence_not_live_test_claim(tmp_path, monkeypatch):
    from test_controlled_tests import setup as controlled_setup
    ledger = controlled_setup(tmp_path)
    requests = []
    class Response:
        status = 200
        def read(self, limit):
            return json.dumps(reply().body).encode()
    class Connection:
        def __init__(self, host, timeout):
            assert host == "api.meta.ai" and timeout == 20
        def request(self, method, path, body, headers):
            requests.append((method, path))
        def getresponse(self):
            return Response()
        def close(self):
            pass
    monkeypatch.setattr("http.client.HTTPSConnection", Connection)
    result = analyze(ledger, OfficialMetaTransport("synthetic-key"))
    item = read_observation(ledger.path, result.recognition_id)
    assert requests == [("POST", "/v1/responses")]
    assert item["transport_kind"] == "official_meta_https"
    assert item["evidence_source"] == "gateway_ledger_record"
    # This is still a mocked HTTP run. Authoritative ledger custody/provider
    # evidence must be independently designated before claiming actual inference.
    assert "verified_meta_inference" not in item
