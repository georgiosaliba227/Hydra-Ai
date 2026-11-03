"""Explicit ongoing billing-wait waiver; all finances and replies are invented."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

import pytest

from backend.meta_budget import BudgetDenied
from backend.recognition import RecognitionUnavailable
from test_wonder_personal_owner_policy import (
    api, gateway_api, setup, complete, quote, Transport, AutoTransport,
    analysis_facts, analysis_reply, trend_facts, trend_reply, workout_facts,
    workout_reply, plan_reply,
)


def waived(owner, **changes):
    return complete(owner, waive_billing_wait=True,
        billing_wait_waiver_reference="synthetic-explicit-ongoing-Wonder-waiver",
        cross_ledger_clear=False, cross_ledger_reference=None, cross_ledger_checked_at=None,
        **changes)


def test_default_policy_still_requires_ninth_finality_and_cross_ledger_status(tmp_path):
    ledger, owner, _ = setup(tmp_path)
    policy = complete(owner)
    owner.authorize(policy)
    assert policy.waive_billing_wait is False and policy.billing_wait_waiver_reference is None
    assert owner.readiness(policy, quote())["blocked_reasons"] == ["current_invoice_finality_required"]
    with pytest.raises(BudgetDenied):
        owner.authorize(complete(owner, cross_ledger_clear=False))


@pytest.mark.parametrize("flag,reference", [(True, None), (True, " "), (False, "synthetic-reference"),
                                           ("true", "synthetic-reference"), (1, "synthetic-reference")])
def test_ongoing_waiver_requires_explicit_boolean_and_reference(tmp_path, flag, reference):
    _, owner, _ = setup(tmp_path)
    with pytest.raises((BudgetDenied, ValueError)):
        owner.authorize(complete(owner, waive_billing_wait=flag,
            billing_wait_waiver_reference=reference, cross_ledger_clear=False))


def test_waiver_allows_actual_ninth_pending_without_faking_cross_ledger_clear_or_finality(tmp_path):
    ledger, owner, ninth = setup(tmp_path)
    policy = waived(owner)
    owner.authorize(policy)
    assert owner.readiness(policy, quote())["status"] == "ready"
    assert policy.cross_ledger_clear is False and policy.cross_ledger_checked_at is None
    assert owner.readiness(policy, quote())["all_charge_categories_verified"] is False
    with ledger.transaction() as db:
        assert db.execute("SELECT state,reserved,actual FROM live_attempts WHERE id=?", (ninth,)).fetchone() == (
            "billing_pending", 250000, None)
        assert db.execute("SELECT COUNT(*) FROM live_finalities").fetchone()[0] == 0
        assert db.execute("SELECT frozen FROM live_accounts").fetchone()[0] == 1


@pytest.mark.parametrize("fault", ["missing_usage", "bool_usage", "wrong_cost", "missing_provider", "unresolved", "active", "missing_output"])
def test_waiver_never_covers_failed_or_unverified_ninth(tmp_path, fault):
    ledger, owner, ninth = setup(tmp_path)
    policy = waived(owner)
    owner.authorize(policy)
    with ledger.transaction() as db:
        usage = json.loads(db.execute("SELECT usage FROM live_attempts WHERE id=?", (ninth,)).fetchone()[0])
        if fault == "missing_usage":
            db.execute("UPDATE live_attempts SET usage=NULL WHERE id=?", (ninth,))
        elif fault in ("bool_usage", "wrong_cost"):
            usage["input_tokens" if fault == "bool_usage" else "usage_derived_cost_micro_usd"] = True if fault == "bool_usage" else 1
            db.execute("UPDATE live_attempts SET usage=? WHERE id=?", (json.dumps(usage), ninth))
        elif fault == "missing_provider":
            db.execute("UPDATE live_attempts SET provider_id=NULL WHERE id=?", (ninth,))
        elif fault == "missing_output":
            db.execute("DELETE FROM live_events WHERE kind='wonder_owner_once_result_saved'")
        else:
            db.execute("UPDATE live_attempts SET state=? WHERE id=?", ("unresolved" if fault == "unresolved" else "owner_once_sending", ninth))
    before = Path(ledger.path).read_bytes()
    transport = Transport(analysis_reply(analysis_facts()))
    gateway = gateway_api().OwnerPersonalWonderGateway(owner, policy, transport)
    assert owner.readiness(policy, quote())["status"] == "blocked"
    with pytest.raises(RecognitionUnavailable):
        gateway.explain_analysis(analysis_facts(), quote(), "synthetic-consent")
    assert transport.calls == 0 and Path(ledger.path).read_bytes() == before


def test_repeated_successful_pending_requests_keep_all_holds_and_require_publication(tmp_path):
    ledger, owner, _ = setup(tmp_path)
    policy = waived(owner, research_authorization_reference="synthetic-research-authorization")
    owner.authorize(policy)
    with ledger.transaction() as db:
        initial = db.execute("SELECT SUM(reserved) FROM live_attempts").fetchone()[0]
    cases = [("trends", trend_facts(), trend_reply(trend_facts())),
             ("workout", workout_facts(), workout_reply()),
             ("analysis", analysis_facts(), None)]
    for index, (kind, facts, reply) in enumerate(cases, 1):
        transport = Transport(reply or analysis_reply(facts))
        gateway = gateway_api().OwnerPersonalWonderGateway(owner, policy, transport)
        result = getattr(gateway, "explain_" + kind)(facts, quote(), "synthetic-exact-consent")
        assert transport.calls == 1 and owner.readiness(policy, quote())["status"] == "blocked"
        gateway.record_result_saved(result)
        assert owner.readiness(policy, quote())["status"] == "ready"
        assert owner.snapshot()["aggregate_exposure_micro_usd"] == initial + index * 250000
    with ledger.transaction() as db:
        assert db.execute("SELECT COUNT(*) FROM live_finalities").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM live_attempts WHERE actual IS NOT NULL").fetchone()[0] == 0
    with pytest.raises(RecognitionUnavailable):
        gateway.explain_analysis(cases[-1][1], quote(), "synthetic-new-consent-cannot-retry")
    assert transport.calls == 1


@pytest.mark.parametrize("fault", ["timeout", "usage", "output", "publication"])
def test_new_waiver_still_blocks_later_failures(tmp_path, fault):
    ledger, owner, _ = setup(tmp_path)
    policy = waived(owner)
    owner.authorize(policy)
    facts = analysis_facts()
    reply = analysis_reply(facts)
    if fault == "usage": reply.body["usage"]["input_tokens"] = True
    if fault == "output": reply.body["output"][0]["content"][0]["text"] = "Drink more water."
    transport = Transport(reply, fail=fault == "timeout")
    gateway = gateway_api().OwnerPersonalWonderGateway(owner, policy, transport)
    if fault == "publication":
        gateway.explain_analysis(facts, quote(), "synthetic-consent")
        gateway.record_save_failure()
    else:
        with pytest.raises(RecognitionUnavailable): gateway.explain_analysis(facts, quote(), "synthetic-consent")
    assert transport.calls == 1
    assert "financial_failure_requires_review" in owner.readiness(policy, quote())["blocked_reasons"]
    with ledger.transaction() as db:
        assert db.execute("SELECT reserved,actual FROM live_attempts WHERE id=?", (gateway.last_attempt,)).fetchone() == (250000, None)


def test_waiver_cannot_admit_two_concurrent_inflight_requests(tmp_path):
    ledger, owner, _ = setup(tmp_path)
    policy = waived(owner)
    owner.authorize(policy)
    transport = AutoTransport()
    def run(kind):
        gateway = gateway_api().OwnerPersonalWonderGateway(owner, policy, transport)
        try:
            facts = trend_facts() if kind == "trends" else analysis_facts()
            getattr(gateway, "explain_" + kind)(facts, quote(), "synthetic-consent")
            return True
        except RecognitionUnavailable:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ("trends", "analysis")))
    assert sum(results) == 1 and transport.calls == 1
    with ledger.transaction() as db:
        assert db.execute("SELECT COUNT(*) FROM live_attempts").fetchone()[0] == 10


def test_fixed_training_plan_remains_once_only_under_ongoing_waiver(tmp_path):
    _, owner, _ = setup(tmp_path)
    policy = waived(owner, research_authorization_reference="synthetic-research-authorization")
    owner.authorize(policy)
    transport = Transport(plan_reply())
    gateway = gateway_api().OwnerPersonalWonderGateway(owner, policy, transport)
    result = gateway.generate_training_plan(quote(), "synthetic-research-consent")
    gateway.record_result_saved(result)
    assert owner.readiness(policy, quote())["status"] == "ready"
    owner.verify_training_plan_record(result)
    with pytest.raises(RecognitionUnavailable):
        gateway.generate_training_plan(quote(), "synthetic-new-consent-cannot-retry")
    assert transport.calls == 1


def test_published_success_quarantined_as_unresolved_stays_blocked(tmp_path):
    ledger, owner, _ = setup(tmp_path)
    policy = waived(owner)
    owner.authorize(policy)
    gateway = gateway_api().OwnerPersonalWonderGateway(owner, policy, Transport(analysis_reply(analysis_facts())))
    result = gateway.explain_analysis(analysis_facts(), quote(), "synthetic-consent")
    gateway.record_result_saved(result)
    assert owner.readiness(policy, quote())["status"] == "ready"
    with ledger.transaction() as db:
        db.execute("UPDATE live_attempts SET state='unresolved' WHERE id=?", (gateway.last_attempt,))
    assert "financial_failure_requires_review" in owner.readiness(policy, quote())["blocked_reasons"]


def test_valid_but_changed_usage_cannot_reuse_an_old_publication_marker(tmp_path):
    ledger, owner, _ = setup(tmp_path)
    policy = waived(owner)
    owner.authorize(policy)
    gateway = gateway_api().OwnerPersonalWonderGateway(owner, policy, Transport(analysis_reply(analysis_facts())))
    result = gateway.explain_analysis(analysis_facts(), quote(), "synthetic-consent")
    gateway.record_result_saved(result)
    with ledger.transaction() as db:
        usage = json.loads(db.execute("SELECT usage FROM live_attempts WHERE id=?", (gateway.last_attempt,)).fetchone()[0])
        usage["input_tokens"] -= 1
        usage["total_tokens"] -= 1
        usage["usage_derived_cost_micro_usd"] -= 4
        db.execute("UPDATE live_attempts SET usage=? WHERE id=?", (json.dumps(usage), gateway.last_attempt))
    assert "financial_failure_requires_review" in owner.readiness(policy, quote())["blocked_reasons"]


def test_ongoing_waiver_keeps_the_existing_allocation_cutoff_and_all_old_holds(tmp_path):
    ledger, owner, _ = setup(tmp_path)
    policy = waived(owner)
    owner.authorize(policy)
    with ledger.transaction() as db:
        original = db.execute("SELECT id FROM live_attempts WHERE created_at='2026-10-28T00:00:00Z' LIMIT 1").fetchone()[0]
        db.execute("UPDATE live_attempts SET actual=30000000 WHERE id=?", (original,))
    assert "budget_exhausted" in owner.readiness(policy, quote())["blocked_reasons"]
    transport = Transport(analysis_reply(analysis_facts()))
    with pytest.raises(RecognitionUnavailable):
        gateway_api().OwnerPersonalWonderGateway(owner, policy, transport).explain_analysis(analysis_facts(), quote(), "synthetic-consent")
    assert transport.calls == 0 and owner.snapshot()["hard_limit_micro_usd"] == 30_000_000
    with ledger.transaction() as db:
        assert db.execute("SELECT SUM(reserved) FROM live_attempts WHERE created_at='2026-10-28T00:00:00Z'").fetchone()[0] == 8_000_000


@pytest.mark.parametrize("kind", ["trends", "workout", "analysis", "runtime_analysis", "score"])
def test_http_success_records_publication_only_after_actual_storage(tmp_path, monkeypatch, kind):
    from uuid import uuid4
    from backend.meta_accounts import stamp
    from backend import wonder_score
    from test_wonder_home_score_admission import score_reply
    from test_wonder_personal_owner_policy import client_for
    from test_wonder_workout import live_body
    client, ledger, owner, policy, transport = client_for(tmp_path, monkeypatch, pending=True, policy_changes={
        "waive_billing_wait": True, "billing_wait_waiver_reference": "synthetic-ongoing-authorization",
        "cross_ledger_clear": False, "cross_ledger_reference": None, "cross_ledger_checked_at": None})
    if kind == "score":
        class ScoreTransport(Transport):
            def generate(self, payload, ticket):
                self.reply = score_reply(wonder_score.facts_from_payload(payload))
                return super().generate(payload, ticket)
        transport = ScoreTransport()
        client.app.state.wonder_trends_gateway = lambda: gateway_api().OwnerPersonalWonderGateway(owner, policy, transport)
    auth = {"Authorization": "Bearer " + "t" * 40}
    path = "/v3/wonder/analysis" if kind == "runtime_analysis" else "/v1/wonder/" + kind
    with client:
        if kind == "trends":
            assert client.post("/v1/beverages", headers=auth | {"Idempotency-Key": str(uuid4())}, json={
                "category": "water", "consumed_ml": 250, "consumed_at": stamp(), "timezone": "UTC", "source": "manual"}).status_code == 201
            body = {"timezone": "UTC"}
            view = client.get(path, params=body, headers=auth).json()
        elif kind == "score":
            assert client.put("/v1/settings", headers=auth, json={"daily_beverage_goal_ml": 2000}).status_code == 200
            body = {"timezone": "UTC", "measurement_count": 2, "processing_consent": True}
            view = client.post(path + "/preview", json=body, headers=auth).json()
        else:
            body = live_body()
            view = client.post(path + "/preview", json=body, headers=auth).json()
        assert view["live_available"] is True
        payload = body | {"payload_sha256": view["payload_sha256"], "consent_to_send": True}
        response = client.post(path, json=payload, headers=auth)
        assert response.status_code == 200, response.text
        assert response.json()["saved"] is True and transport.calls == 1
        assert owner.readiness(policy, quote())["status"] == "ready"
        assert len(list((tmp_path / "results").glob("*.json"))) == 1
        with ledger.transaction() as db:
            assert db.execute("SELECT COUNT(*) FROM live_events WHERE kind='wonder_personal_owner_result_published'").fetchone()[0] == 1
        before = Path(ledger.path).read_bytes()
        assert client.post(path, json=payload, headers=auth).json()["replayed"] is True
        assert Path(ledger.path).read_bytes() == before and transport.calls == 1


def test_publication_audit_failure_preserves_saved_file_and_free_replay(tmp_path, monkeypatch):
    from test_wonder_personal_owner_policy import client_for
    from test_wonder_workout import live_body
    client, ledger, owner, policy, transport = client_for(tmp_path, monkeypatch, pending=True, policy_changes={
        "waive_billing_wait": True, "billing_wait_waiver_reference": "synthetic-ongoing-authorization",
        "cross_ledger_clear": False, "cross_ledger_reference": None, "cross_ledger_checked_at": None})
    def reject(*args):
        raise BudgetDenied("Invented audit write failure")
    monkeypatch.setattr(owner, "record_result_saved", reject)
    auth = {"Authorization": "Bearer " + "t" * 40}
    with client:
        body = live_body()
        view = client.post("/v1/wonder/analysis/preview", json=body, headers=auth).json()
        payload = body | {"payload_sha256": view["payload_sha256"], "consent_to_send": True}
        response = client.post("/v1/wonder/analysis", json=payload, headers=auth)
        assert response.status_code == 200 and response.json()["saved"] is True
        assert "financial_failure_requires_review" in owner.readiness(policy, quote())["blocked_reasons"]
        before = Path(ledger.path).read_bytes()
        replay = client.post("/v1/wonder/analysis", json=payload, headers=auth)
        assert replay.status_code == 200 and replay.json()["replayed"] is True
        assert transport.calls == 1 and Path(ledger.path).read_bytes() == before


def test_operator_training_cli_marks_publication_after_the_result_file_exists(tmp_path, monkeypatch, capsys):
    from scripts import muse_simulated_training as cli
    from ai.forecasting import muse_synthetic
    from ai.forecasting.ingestion import SOURCES
    from test_wonder_personal_owner_policy import KEY, private_json
    ledger, owner, _ = setup(tmp_path)
    policy = waived(owner, research_authorization_reference="synthetic-research-authorization")
    owner.authorize(policy)
    # Invented source-shaped software fixture, never actual study evidence.
    records = [{"record_id": f"spectrophon-v1:{i:03}:00", "participant_id": f"spectrophon-v1:{i:03}",
        "study_id": "spectrophon-v1", "synthetic": False, "target_name": "corrected_mass_loss_proxy_ml",
        "target_method": "invented_cli_test_fixture", "target_value_ml": 250.0 + i * 20,
        "duration_minutes": 90.0, "pre_mass_kg": 60.0 + i, "age_years": 20.0 + i,
        "source_sha256": SOURCES["spectrophon"]["sha256"], "source_license": SOURCES["spectrophon"]["license"]}
        for i in range(30)]
    prepared = muse_synthetic.prepare_base(records)
    directory = tmp_path / "prepared"
    directory.mkdir(mode=0o700)
    private_json(directory / "base-records.json", prepared["records"])
    private_json(directory / "split-manifest.json", prepared["split_manifest"])
    policy_path = private_json(tmp_path / "policy.json", policy.model_dump(mode="json"))
    quote_path = private_json(tmp_path / "quote.json", quote().model_dump(mode="json"))
    destination = tmp_path / "training-plan.json"
    transport = Transport(plan_reply())
    monkeypatch.setattr(gateway_api(), "OwnerPersonalMetaTransport", lambda key: transport)
    monkeypatch.setenv("HYDRA_META_GEORGIO_API_KEY", KEY)
    original = api().OwnerPersonalAuthority.record_result_saved
    def verify_file_before_marker(self, attempt, result_hash):
        assert destination.is_file()
        return original(self, attempt, result_hash)
    monkeypatch.setattr(api().OwnerPersonalAuthority, "record_result_saved", verify_file_before_marker)
    cli.main(["generate-plan", "--prepared", str(directory), "--database", str(ledger.path),
        "--policy", policy_path, "--quote", quote_path, "--consent-reference", "synthetic-fixed-plan-consent",
        "--output", str(destination), "--confirm-billable"])
    assert json.loads(capsys.readouterr().out)["status"] == "validated_plan_saved"
    assert transport.calls == 1 and owner.readiness(policy, quote())["status"] == "ready"
    with ledger.transaction() as db:
        assert db.execute("SELECT COUNT(*) FROM live_events WHERE kind='wonder_personal_owner_result_published'").fetchone()[0] == 1


def test_old_recorded_v1_descriptor_omitting_new_fields_keeps_default_checks_and_bytes(tmp_path):
    ledger, owner, ninth = setup(tmp_path)
    policy = complete(owner)
    old = policy.model_dump(mode="json")
    del old["waive_billing_wait"]
    del old["billing_wait_waiver_reference"]
    with ledger.transaction() as db:
        ledger.event(db, "georgiosaliba227", api().AUTH_EVENT, json.dumps(old, separators=(",", ":")))
    before = Path(ledger.path).read_bytes()
    assert owner.readiness(policy, quote())["blocked_reasons"] == ["current_invoice_finality_required"]
    owner.authorize(policy)
    assert Path(ledger.path).read_bytes() == before
    from test_wonder_personal_owner_policy import finalize
    finalize(ledger, ninth)
    assert owner.readiness(policy, quote())["status"] == "ready"


@pytest.mark.parametrize("change", ["missing_policy_id", "missing_policy_hash", "missing_consent", "wrong_policy_id",
    "wrong_policy_hash", "blank_consent", "changed_consent", "unauthorized_purpose", "changed_allowed_purpose", "extra_field"])
def test_pending_success_requires_its_exact_original_policy_and_consent_binding(tmp_path, change):
    from uuid import uuid4
    ledger, owner, _ = setup(tmp_path)
    policy = waived(owner)
    owner.authorize(policy)
    gateway = gateway_api().OwnerPersonalWonderGateway(owner, policy, Transport(analysis_reply(analysis_facts())))
    result = gateway.explain_analysis(analysis_facts(), quote(), "synthetic-original-exact-consent")
    gateway.record_result_saved(result)
    assert owner.readiness(policy, quote())["status"] == "ready"
    with ledger.transaction() as db:
        event, raw = db.execute("SELECT id,reference FROM live_events WHERE kind=?", (api().BIND_EVENT,)).fetchone()
        binding = json.loads(raw)
        if change.startswith("missing_"):
            binding.pop({"missing_policy_id": "policy_id", "missing_policy_hash": "policy_sha256", "missing_consent": "consent_reference"}[change])
        elif change == "wrong_policy_id": binding["policy_id"] = str(uuid4())
        elif change == "wrong_policy_hash": binding["policy_sha256"] = "b" * 64
        elif change == "blank_consent": binding["consent_reference"] = " "
        elif change == "changed_consent": binding["consent_reference"] = "synthetic-different-consent"
        elif change == "unauthorized_purpose": binding["purpose"] = "arbitrary_prompt"
        elif change == "changed_allowed_purpose": binding["purpose"] = "personal_trends"
        else: binding["unexpected"] = True
        db.execute("UPDATE live_events SET reference=? WHERE id=?", (api().canonical(binding), event))
        assert owner._successful_pending(db, gateway.last_attempt) is False
    assert owner.readiness(policy, quote())["status"] == "blocked"


def test_pending_success_requires_the_original_authorization_even_after_policy_renewal(tmp_path):
    ledger, owner, _ = setup(tmp_path)
    policy = waived(owner)
    owner.authorize(policy)
    gateway = gateway_api().OwnerPersonalWonderGateway(owner, policy, Transport(analysis_reply(analysis_facts())))
    result = gateway.explain_analysis(analysis_facts(), quote(), "synthetic-original-exact-consent")
    gateway.record_result_saved(result)
    renewed = waived(owner)
    owner.authorize(renewed)
    assert owner.readiness(renewed, quote())["status"] == "ready"
    with ledger.transaction() as db:
        db.execute("DELETE FROM live_events WHERE kind=? AND reference=?", (api().AUTH_EVENT, policy.model_dump_json()))
        assert owner._successful_pending(db, gateway.last_attempt) is False
    assert owner.readiness(renewed, quote())["status"] == "blocked"


def test_published_historical_receipt_keeps_its_authorization_after_expiry(tmp_path, monkeypatch):
    from datetime import timedelta
    ledger, owner, _ = setup(tmp_path)
    policy = waived(owner)
    owner.authorize(policy)
    gateway = gateway_api().OwnerPersonalWonderGateway(owner, policy, Transport(analysis_reply(analysis_facts())))
    result = gateway.explain_analysis(analysis_facts(), quote(), "synthetic-original-exact-consent")
    gateway.record_result_saved(result)
    advanced = api().now() + timedelta(hours=2)
    assert policy.valid_until < advanced
    monkeypatch.setattr(api(), "now", lambda: advanced)
    renewed = waived(owner, account_observed_at=advanced.isoformat(),
                     valid_until=(advanced + timedelta(minutes=30)).isoformat())
    owner.authorize(renewed)
    current_quote = quote(valid_until=(advanced + timedelta(minutes=30)).isoformat())
    assert owner.readiness(renewed, current_quote)["status"] == "ready"
