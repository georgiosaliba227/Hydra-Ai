"""The new Home purpose shares financial finality; disposable ledgers only."""
from pathlib import Path
from datetime import datetime, timezone
import json
import socket

import pytest

from backend.meta_budget import BudgetDenied
from test_wonder_personal_owner_policy import KEY_HASH, complete, finalize, quote, setup


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("Network forbidden in score admission tests"))


def score_facts():
    from backend.hydration_score import build_facts
    return build_facts([], 2000, "UTC", 2, now=datetime(2026, 11, 3, 12, tzinfo=timezone.utc))


def score_reply(facts):
    from backend.wonder_score import REQUIRED_IDS, allowed_texts
    from test_wonder_experiment import selection_reply
    choices = allowed_texts(facts)
    return selection_reply(text=json.dumps({"insights": [{"id": key, "text": choices[key][0]} for key in REQUIRED_IDS]}))


def test_home_purpose_requires_finality_and_preserves_old_holds(tmp_path):
    ledger, owner, ninth = setup(tmp_path)
    policy = complete(owner)
    owner.authorize(policy)
    before = Path(ledger.path).read_bytes()
    args = (policy, quote(), "personal_home_score", "a" * 64, 2000, 768, KEY_HASH, "synthetic-score-consent")
    with pytest.raises(BudgetDenied):
        owner.reserve(*args)
    assert Path(ledger.path).read_bytes() == before
    finalize(ledger, ninth)
    attempt = owner.reserve(*args)
    with ledger.transaction() as db:
        assert db.execute("SELECT COUNT(*) FROM live_attempts").fetchone()[0] == 10
        assert db.execute("SELECT reserved,state FROM live_attempts WHERE id=?", (attempt,)).fetchone() == (250000, "personal_owner_reserved")
        assert db.execute("SELECT SUM(reserved) FROM live_attempts WHERE created_at='2026-10-28T00:00:00Z'").fetchone()[0] == 8_000_000
    assert owner.readiness(policy, quote())["status"] == "blocked"


@pytest.mark.parametrize("transport_kind", ["verified", "owner_risk"])
def test_home_transport_accepts_only_exact_fixed_payload(transport_kind):
    from backend.wonder_score import score_payload
    from backend.wonder_experiment import WonderMetaTransport
    from backend.wonder_personal_owner_gateway import OwnerPersonalMetaTransport, validate_purpose_payload
    payload = score_payload(score_facts())
    transport = (WonderMetaTransport if transport_kind == "verified" else OwnerPersonalMetaTransport)("invented-score-key")
    transport.validate_payload(payload)
    assert validate_purpose_payload(payload) == "personal_home_score"
    for change in ({"store": 0}, {"stream": 0}, {"background": 0}, {"max_output_tokens": 1024.0}, {"tools": []}):
        with pytest.raises(ValueError):
            transport.validate_payload(payload | change)


def test_owner_score_uses_exact_claim_and_holds_full_unverified_charge(tmp_path):
    from backend.wonder_personal_owner_gateway import OwnerPersonalWonderGateway
    from backend.recognition import RecognitionUnavailable
    from test_wonder_personal_owner_policy import Transport
    ledger, owner, ninth = setup(tmp_path)
    policy = complete(owner)
    owner.authorize(policy)
    facts = score_facts()
    transport = Transport(score_reply(facts))
    gateway = OwnerPersonalWonderGateway(owner, policy, transport)
    before = Path(ledger.path).read_bytes()
    with pytest.raises(RecognitionUnavailable):
        gateway.explain_score(facts, quote(), "synthetic-exact-score-preview-consent")
    assert transport.calls == 0 and gateway.last_attempt is None
    assert Path(ledger.path).read_bytes() == before
    finalize(ledger, ninth)
    result = gateway.explain_score(facts, quote(), "synthetic-exact-score-preview-consent")
    assert result["facts"] == facts and transport.calls == 1
    assert result["provider_observations"]["billed_cost_usd"] is None
    with ledger.transaction() as db:
        assert db.execute("SELECT reserved,actual,state FROM live_attempts WHERE id=?", (gateway.last_attempt,)).fetchone() == (250000, None, "billing_pending")
    with pytest.raises(RecognitionUnavailable):
        gateway.explain_score(facts, quote(), "synthetic-exact-score-preview-consent")
    assert transport.calls == 1


def test_verified_score_uses_existing_own_data_case_and_finality_gate(tmp_path):
    from backend.wonder_experiment import WonderHydrationGateway, WonderMetaTransport
    from backend.wonder_hydration import input_bound
    from backend.recognition import RecognitionUnavailable
    from test_guarded_meta import FakeNotifier, evidence
    from test_wonder_trends import AMINE, amine_quote, amine_setup
    _, ledger = amine_setup(tmp_path)
    facts = score_facts()

    class Transport:
        credential_fingerprint = evidence(AMINE).key_sha256
        calls = 0

        def input_bound(self, payload):
            WonderMetaTransport("invented-score-key").validate_payload(payload)
            return input_bound(payload)

        def generate(self, payload, ticket):
            ticket.claim(payload, input_bound=self.input_bound(payload), credential_fingerprint=self.credential_fingerprint)
            self.calls += 1
            return score_reply(facts)

    transport = Transport()
    result = WonderHydrationGateway(ledger, transport, FakeNotifier()).explain_score(facts, amine_quote(), "synthetic-exact-score-consent")
    assert result["facts"] == facts and result["provenance"]["account_id"] == AMINE
    with pytest.raises(RecognitionUnavailable):
        WonderHydrationGateway(ledger, transport, FakeNotifier()).explain_score(facts, amine_quote(), "synthetic-exact-score-consent")
    assert transport.calls == 1
