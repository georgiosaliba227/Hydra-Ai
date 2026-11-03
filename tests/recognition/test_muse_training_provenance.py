"""The Muse-origin branch accepts only the common authority's recorded output.

Every provider response and ledger in this test is invented and disposable.
It exercises provenance plumbing and provides no evidence of actual inference.
"""
from copy import deepcopy
from pathlib import Path

import pytest

from ai.forecasting import muse_synthetic
from backend.meta_budget import BudgetDenied
from test_wonder_personal_owner_policy import (
    setup, complete, finalize, quote, gateway_api, Transport, plan_reply,
)


def test_training_origin_requires_exact_recorded_gateway_result_without_writing_the_ledger(tmp_path):
    ledger, authority, ninth = setup(tmp_path)
    policy = complete(authority, research_authorization_reference="invented-test-research-approval")
    authority.authorize(policy)
    finalize(ledger, ninth)
    transport = Transport(plan_reply())
    gateway = gateway_api().OwnerPersonalWonderGateway(authority, policy, transport)
    envelope = gateway.generate_training_plan(quote(), "invented-test-synthetic-plan-consent")
    before = Path(ledger.path).read_bytes()

    plan, provenance = muse_synthetic._plan_source(envelope, "muse_wonder", authority)
    assert plan == envelope["plan"] and transport.calls == 1
    assert provenance["plan_origin"] == "muse_wonder" and provenance["muse_inference_used"] is True
    assert provenance["verified_plan_record_sha256"] == muse_synthetic.digest(envelope)
    assert not {"attempt_id", "account_id", "provider_observations"}.intersection(provenance)
    assert Path(ledger.path).read_bytes() == before

    forged = deepcopy(envelope)
    forged["plan"]["training_weights"]["base"] = 1
    with pytest.raises((ValueError, BudgetDenied)):
        muse_synthetic._plan_source(forged, "muse_wonder", authority)
    assert Path(ledger.path).read_bytes() == before
