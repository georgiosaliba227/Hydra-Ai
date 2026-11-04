"""Personal risk admission uses disposable authorities and invented replies only."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from importlib import import_module
import hashlib
import json
import socket
from uuid import uuid4
from pathlib import Path

from fastapi.testclient import TestClient

import pytest

from backend.meta_accounts import AccountLedger, InvoiceFinality, stamp
from backend.meta_budget import BudgetDenied
from backend.meta_provider import ProviderReply
from backend.recognition import RecognitionUnavailable
from backend.wonder_hydration import input_bound
from backend import wonder_analysis
from test_wonder_owner_once import FakeTransport as OnceTransport, approval as once_approval
from test_wonder_owner_once import reply as once_reply
from test_wonder_workout import facts as workout_facts, reply as workout_reply
from test_wonder_trends import facts as trend_facts, trend_reply

KEY = "invented-owner-once-key"
KEY_HASH = hashlib.sha256(KEY.encode()).hexdigest()


def api():
    return import_module("backend.wonder_personal_owner_policy")


def gateway_api():
    return import_module("backend.wonder_personal_owner_gateway")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("network forbidden"))


def setup(tmp_path):
    from backend.wonder_owner_once import OwnerOnceAuthority
    ledger = AccountLedger(tmp_path / "authority.sqlite3")
    ledger.initialize_accounts()
    with ledger.transaction() as db:
        db.execute("INSERT INTO live_accounts VALUES(?,?,?,1)", ("georgiosaliba227", json.dumps({
            "key_sha256": KEY_HASH, "gross_micro_usd": 0, "credits_remaining_micro_usd": 150_000_000,
            "all_charge_categories_verified": False, "extra_charge_bound_micro_usd": None,
            "valid_until": "2026-10-28T00:00:00Z"}), 0))
        for i in range(8):
            db.execute("INSERT INTO live_attempts(id,account_id,price,reserved,state,input_bound,created_at,provider_id,usage) "
                       "VALUES(?,?,?,?,?,?,?,?,?)", (str(uuid4()), "georgiosaliba227", "{}", 1_000_000,
                       "unresolved" if i == 7 else "billing_pending", 100, "2026-10-28T00:00:00Z",
                       f"resp_legacy_{i}", "{}"))
    once = OwnerOnceAuthority(ledger)
    once.authorize(once_approval(once))
    ninth = once.run(OnceTransport(), tmp_path / "once-result.json")["receipt"]["attempt_id"]
    return ledger, api().OwnerPersonalAuthority(ledger), ninth


def complete(owner, **changes):
    now = datetime.now(timezone.utc)
    d = owner.prepare()
    d.update(owner_authorization_reference="synthetic-owner", legacy_billing_waiver_reference="synthetic-old8-waiver",
             risk_acceptance_reference="synthetic-all-requests-extras-ack", accept_unverified_extras=True,
             personal_data_authorization_reference="synthetic-aggregate-standing-authority",
             account_observation_reference="synthetic-authenticated-credit-observation",
             notification_delivery_reference="synthetic-notification-check", cross_ledger_reference="synthetic-Amine-status",
             cross_ledger_clear=True, cross_ledger_checked_at=now.isoformat(), account_observed_at=now.isoformat(),
             observed_credits_micro_usd=149_850_000, valid_until=(now + timedelta(hours=1)).isoformat())
    d.update(changes)
    return api().OwnerPersonalPolicy.model_validate_json(json.dumps(d))


def quote(**changes):
    d = api().quote_template()
    d.update(reference="synthetic-price-reference", model_access_reference="synthetic-current-response",
             valid_until=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())
    return api().OwnerRiskQuote.model_validate_json(json.dumps(d | changes))


def finalize(ledger, attempt):
    with ledger.transaction() as db:
        provider, dispatched = db.execute("SELECT provider_id,dispatched_at FROM live_attempts WHERE id=?", (attempt,)).fetchone()
        when = max(datetime.fromisoformat(dispatched), datetime.now(timezone.utc) - timedelta(seconds=1))
        f = InvoiceFinality(attempt_id=attempt, account_id="georgiosaliba227", provider_id=provider,
            final_gross_micro_usd=8000, finalized_at=when, provider_evidence_reference="synthetic-final-invoice",
            georgio_review_reference="synthetic-owner-review", amine_review_reference="synthetic-Amine-review",
            provider_finality_verified=True)
        db.execute("UPDATE live_attempts SET actual=8000,state='settled' WHERE id=?", (attempt,))
        db.execute("INSERT INTO live_finalities VALUES(?,?,?)", (attempt, f.model_dump_json(), stamp()))


class Transport:
    credential_fingerprint = KEY_HASH
    calls = 0

    def __init__(self, reply=None, fail=False):
        self.reply, self.fail, self.calls = reply, fail, 0

    def input_bound(self, payload):
        gateway_api().validate_purpose_payload(payload)
        return input_bound(payload)

    def generate(self, payload, ticket):
        ticket.claim(payload, input_bound=self.input_bound(payload), credential_fingerprint=self.credential_fingerprint)
        self.calls += 1
        if self.fail:
            raise RecognitionUnavailable()
        return self.reply


def analysis_facts():
    from backend.hydration_analysis import build_analysis
    from backend.workout_forecasts import WorkoutForecastInput
    from test_wonder_workout import live_body
    return wonder_analysis.build_facts(build_analysis(WorkoutForecastInput.model_validate(live_body()), (),
        generated_at=datetime.now(timezone.utc)))


def analysis_reply(facts):
    reply = once_reply()
    body = deepcopy(reply.body)
    body["id"] = "resp_personal_analysis"
    selection = {"sections": {k:v[:3] for k,v in wonder_analysis.applicable_insights(facts).items()}}
    body["output"][0]["content"][0]["text"] = json.dumps(selection)
    return ProviderReply(200, body)


def test_incomplete_prepare_is_read_only_and_does_not_waive_ninth(tmp_path):
    ledger, owner, ninth = setup(tmp_path)
    before = open(ledger.path, "rb").read()
    d = owner.prepare()
    assert len(d["waived_attempts"]) == 8
    assert ninth not in {v["attempt_id"] for v in d["waived_attempts"]}
    assert d["accept_unverified_extras"] is False and d["cross_ledger_clear"] is False
    assert d["waive_billing_wait"] is False and d["billing_wait_waiver_reference"] is None
    p = api().OwnerPersonalPolicy.model_validate_json(json.dumps(d))
    status = owner.readiness(p, quote())
    assert status["status"] == "blocked" and not status["all_charge_categories_verified"]
    assert {"owner_policy_not_recorded", "cross_ledger_status_unverified", "current_invoice_finality_required"} <= set(status["blocked_reasons"])
    assert open(ledger.path, "rb").read() == before
    with pytest.raises(BudgetDenied): owner.authorize(p)


def test_complete_policy_still_blocks_ninth_before_any_reservation(tmp_path):
    ledger, owner, _ = setup(tmp_path)
    p = complete(owner); owner.authorize(p)
    transport = Transport(analysis_reply(analysis_facts()))
    gateway = gateway_api().OwnerPersonalWonderGateway(owner, p, transport)
    before = open(ledger.path, "rb").read()
    assert owner.readiness(p, quote())["blocked_reasons"] == ["current_invoice_finality_required"]
    with pytest.raises(RecognitionUnavailable): gateway.explain_analysis(analysis_facts(), quote(), "synthetic-consent")
    assert transport.calls == 0 and gateway.last_attempt is None
    assert open(ledger.path, "rb").read() == before


@pytest.mark.parametrize("kind", ["trends", "workout", "analysis"])
def test_each_personal_method_uses_existing_contract_and_holds_unknown_charges(tmp_path, kind):
    ledger, owner, ninth = setup(tmp_path)
    p = complete(owner); owner.authorize(p); finalize(ledger, ninth)
    assert owner.readiness(p, quote())["status"] == "ready"
    facts = trend_facts() if kind == "trends" else workout_facts() if kind == "workout" else analysis_facts()
    reply = trend_reply(facts) if kind == "trends" else workout_reply() if kind == "workout" else analysis_reply(facts)
    transport = Transport(reply)
    result = getattr(gateway_api().OwnerPersonalWonderGateway(owner, p, transport), "explain_" + kind)(facts, quote(), "synthetic-exact-app-consent")
    assert transport.calls == 1 and result["provenance"]["model"] == "muse-wonder-1.0"
    with ledger.transaction() as db:
        state, reserved, actual = db.execute("SELECT state,reserved,actual FROM live_attempts WHERE id=?", (result["provenance"]["attempt_id"],)).fetchone()
        assert db.execute("SELECT frozen FROM live_accounts").fetchone()[0] == 1
    assert (state, reserved, actual) == ("billing_pending", 250000, None)
    assert "current_invoice_finality_required" in owner.readiness(p, quote())["blocked_reasons"]


@pytest.mark.parametrize("change", ["key", "waiver", "account", "risk", "cross", "notification", "stale", "account_reference"])
def test_invalid_or_missing_policy_facts_never_become_admissible(tmp_path, change):
    _, owner, _ = setup(tmp_path)
    p = complete(owner)
    updates = {"key":{"key_sha256":"b"*64}, "waiver":{"waived_attempts":p.waived_attempts[1:]},
        "account":{"account_snapshot_sha256":"b"*64}, "risk":{"accept_unverified_extras":False},
        "cross":{"cross_ledger_clear":False}, "notification":{"notification_delivery_reference":None},
        "stale":{"account_observed_at":datetime.now(timezone.utc)-timedelta(days=2)},
        "account_reference":{"account_observation_reference":None}}[change]
    with pytest.raises((BudgetDenied, ValueError)):
        owner.authorize(p.model_copy(update=updates))


def test_quote_never_claims_verified_extra_bounds():
    q = quote()
    assert q.all_charge_categories_verified is False and q.extra_charge_bound_micro_usd is None
    assert q.bound(1000, 200) == 8000
    with pytest.raises(ValueError): quote(all_charge_categories_verified=True)


@pytest.mark.parametrize("kind", ["trends", "workout", "analysis"])
@pytest.mark.parametrize("change", [{"store": 0}, {"stream": 0}, {"background": 0}])
def test_purpose_transport_requires_exact_json_flag_types(kind, change):
    from backend.wonder_trends import trends_payload
    from backend.wonder_workout import workout_payload
    from backend.wonder_analysis import analysis_payload
    payload = (trends_payload(trend_facts()) if kind == "trends" else
               workout_payload(workout_facts()) if kind == "workout" else analysis_payload(analysis_facts()))
    with pytest.raises(ValueError):
        gateway_api().validate_purpose_payload(payload | change)


@pytest.mark.parametrize("change", [{"model": "muse-spark-1.0"}, {"input_micro_per_million": 0}])
def test_mutated_typed_quote_cannot_enter_financial_admission(tmp_path, change):
    ledger, owner, ninth = setup(tmp_path)
    policy = complete(owner)
    owner.authorize(policy)
    finalize(ledger, ninth)
    from backend.wonder_analysis import analysis_payload
    from backend.wonder_hydration import payload_sha256
    payload = analysis_payload(analysis_facts())
    before = Path(ledger.path).read_bytes()
    with pytest.raises((ValueError, BudgetDenied)):
        owner.reserve(policy, quote().model_copy(update=change), "personal_analysis",
                      payload_sha256(payload), input_bound(payload), payload["max_output_tokens"],
                      KEY_HASH, "synthetic-consent")
    assert Path(ledger.path).read_bytes() == before


@pytest.mark.parametrize("recorded", [False, True])
def test_preparation_cannot_rebind_reduced_original_reservations(tmp_path, recorded):
    ledger, owner, _ = setup(tmp_path)
    if recorded: owner.authorize(complete(owner))
    with ledger.transaction() as db:
        db.execute("UPDATE live_attempts SET reserved=1 WHERE created_at='2026-10-28T00:00:00Z'")
    with pytest.raises(BudgetDenied): owner.prepare()


def test_append_only_operator_note_does_not_invalidate_unchanged_legacy_identity(tmp_path):
    ledger,owner,_=setup(tmp_path)
    with ledger.transaction() as db:ledger.event(db,"georgiosaliba227","operator_delivery_check","synthetic-note")
    assert len(owner.prepare()["waived_attempts"])==8


def test_two_competing_requests_consume_one_reservation(tmp_path):
    ledger, owner, ninth = setup(tmp_path)
    p = complete(owner); owner.authorize(p); finalize(ledger,ninth)
    f = analysis_facts(); transport = Transport(analysis_reply(f))
    def run():
        try:
            gateway_api().OwnerPersonalWonderGateway(owner,p,transport).explain_analysis(f,quote(),"synthetic-consent")
            return True
        except RecognitionUnavailable: return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _:run(),range(2)))
    assert sum(results)==1 and transport.calls==1
    with ledger.transaction() as db: assert db.execute("SELECT count(*) FROM live_attempts").fetchone()[0]==10


@pytest.mark.parametrize("fault", ["timeout","malformed_usage","malicious_text","save_failure"])
def test_later_failure_keeps_hold_and_stops_admission(tmp_path, fault):
    ledger,owner,ninth=setup(tmp_path);p=complete(owner);owner.authorize(p);finalize(ledger,ninth)
    f=analysis_facts();r=analysis_reply(f)
    if fault=="malformed_usage": r.body["usage"]["input_tokens"]=True
    if fault=="malicious_text": r.body["output"][0]["content"][0]["text"]="Drink extra water."
    transport=Transport(r,fail=fault=="timeout");g=gateway_api().OwnerPersonalWonderGateway(owner,p,transport)
    if fault=="save_failure":
        g.explain_analysis(f,quote(),"synthetic-consent");g.record_save_failure()
    else:
        with pytest.raises(RecognitionUnavailable):g.explain_analysis(f,quote(),"synthetic-consent")
    assert transport.calls==1
    status=owner.readiness(p,quote())
    assert "financial_failure_requires_review" in status["blocked_reasons"]
    with ledger.transaction() as db:
        row=db.execute("SELECT reserved,actual,provider_id FROM live_attempts WHERE id=?",(g.last_attempt,)).fetchone()
    assert row[:2]==(250000,None)
    if fault!="timeout":assert row[2]=="resp_personal_analysis"
    with pytest.raises(RecognitionUnavailable):
        gateway_api().OwnerPersonalWonderGateway(owner,p,transport).explain_analysis(f,quote(),"new-consent")
    assert transport.calls==1


def test_attempted_hash_stays_consumed_after_genuine_finality(tmp_path):
    ledger,owner,ninth=setup(tmp_path);p=complete(owner);owner.authorize(p);finalize(ledger,ninth)
    f=analysis_facts();transport=Transport(analysis_reply(f));g=gateway_api().OwnerPersonalWonderGateway(owner,p,transport)
    result=g.explain_analysis(f,quote(),"synthetic-consent");finalize(ledger,result["provenance"]["attempt_id"])
    assert owner.readiness(p,quote())["status"]=="ready"
    with pytest.raises(RecognitionUnavailable):g.explain_analysis(f,quote(),"fresh-consent-cannot-retry")
    assert transport.calls==1


@pytest.mark.parametrize("fault", ["purpose", "hash", "credential", "bound", "expired"])
def test_ticket_rechecks_exact_claim_before_send(tmp_path, fault):
    from backend.wonder_analysis import analysis_payload
    from backend.wonder_hydration import payload_sha256
    from backend.wonder_workout import workout_payload
    ledger, owner, ninth = setup(tmp_path)
    policy = complete(owner)
    owner.authorize(policy)
    finalize(ledger, ninth)
    payload = analysis_payload(analysis_facts())
    price = quote()
    bound = input_bound(payload)
    attempt = owner.reserve(policy, price, "personal_analysis", payload_sha256(payload), bound,
                            payload["max_output_tokens"], KEY_HASH, "synthetic-consent")
    ticket = owner.dispatch(policy, price, attempt)
    claimed_payload, claimed_key, claimed_bound = payload, KEY_HASH, bound
    if fault == "purpose":
        claimed_payload = workout_payload(workout_facts())
    elif fault == "hash":
        from backend.hydration_analysis import build_analysis
        from backend.workout_forecasts import WorkoutForecastInput
        from test_wonder_workout import live_body
        facts = wonder_analysis.build_facts(build_analysis(
            WorkoutForecastInput.model_validate(live_body(duration=76.0)), (),
            generated_at=datetime.now(timezone.utc)))
        claimed_payload = analysis_payload(facts)
    elif fault == "credential":
        claimed_key = "b" * 64
    elif fault == "bound":
        claimed_bound += 1
    else:
        ticket.quote.valid_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises((ValueError, BudgetDenied)):
        ticket.claim(claimed_payload, input_bound=claimed_bound, credential_fingerprint=claimed_key)
    with ledger.transaction() as db:
        assert db.execute("SELECT state,reserved,actual FROM live_attempts WHERE id=?", (attempt,)).fetchone() == (
            "personal_owner_dispatched", 250000, None)


def test_consumed_send_claim_survives_a_crash_and_cannot_be_claimed_twice(tmp_path):
    from backend.wonder_analysis import analysis_payload
    from backend.wonder_hydration import payload_sha256
    ledger, owner, ninth = setup(tmp_path)
    policy = complete(owner)
    owner.authorize(policy)
    finalize(ledger, ninth)
    payload = analysis_payload(analysis_facts())
    price = quote()
    bound = input_bound(payload)
    attempt = owner.reserve(policy, price, "personal_analysis", payload_sha256(payload), bound,
                            payload["max_output_tokens"], KEY_HASH, "synthetic-consent")
    ticket = owner.dispatch(policy, price, attempt)
    ticket.claim(payload, input_bound=bound, credential_fingerprint=KEY_HASH)
    restarted = api().OwnerPersonalAuthority(AccountLedger(ledger.path))
    assert "request_in_flight" in restarted.readiness(policy, price)["blocked_reasons"]
    with pytest.raises(BudgetDenied):
        ticket.claim(payload, input_bound=bound, credential_fingerprint=KEY_HASH)
    with ledger.transaction() as db:
        assert db.execute("SELECT state,ticket_nonce,reserved,actual FROM live_attempts WHERE id=?", (attempt,)).fetchone() == (
            "personal_owner_sending", None, 250000, None)


def private_json(path, data):
    path.write_text(json.dumps(data));path.chmod(0o600);return str(path)


def client_for(tmp_path,monkeypatch,*,pending=False,policy_changes=None):
    from backend.app import create_app
    from backend.wonder_readiness_routes import install_wonder_readiness_routes
    ledger,owner,ninth=setup(tmp_path);p=complete(owner,**(policy_changes or {}));owner.authorize(p)
    if not pending:finalize(ledger,ninth)
    env={"HYDRA_AI_MODE":"mock","META_BILLABLE_REQUESTS_ENABLED":"true","HYDRA_META_HYDRATION_ENABLED":"false",
        "HYDRA_WONDER_LIVE":"true","HYDRA_WONDER_ANALYSIS_ENABLED":"true",
        "HYDRA_WONDER_FINANCIAL_POLICY":"owner_accepted_risk","HYDRA_WONDER_ACCOUNT":"georgiosaliba227",
        "HYDRA_WONDER_LEDGER":ledger.path,"HYDRA_WONDER_OWNER_POLICY_FILE":private_json(tmp_path/"policy.json",p.model_dump(mode="json")),
        "HYDRA_WONDER_QUOTE":private_json(tmp_path/"quote.json",quote().model_dump(mode="json")),
        "HYDRA_WONDER_RESULTS_DIR":str(tmp_path/"results"),"HYDRA_META_GEORGIO_API_KEY":KEY,
        "HYDRA_GITHUB_NOTIFICATION_TOKEN":"invented-notification-key"}
    for k,v in env.items():monkeypatch.setenv(k,str(v))
    (tmp_path/"results").mkdir(mode=0o700)
    app=create_app(tmp_path/"beverages.sqlite3","t"*40)
    if not any(r.path=="/v1/wonder/readiness" for r in app.routes):install_wonder_readiness_routes(app)
    transport=AutoTransport()
    app.state.wonder_trends_gateway=lambda:gateway_api().OwnerPersonalWonderGateway(owner,p,transport)
    return TestClient(app),ledger,owner,p,transport


class AutoTransport(Transport):
    def generate(self,payload,ticket):
        purpose=gateway_api().validate_purpose_payload(payload)
        self.reply=once_reply()
        self.reply.body["id"]="resp_personal_"+uuid4().hex
        if purpose=="personal_analysis":
            f=wonder_analysis.facts_from_payload(payload)
            selection={"sections":{k:v[:3] for k,v in wonder_analysis.applicable_insights(f).items()}}
        elif purpose=="personal_workout":
            message=next(item for item in workout_reply().body["output"] if item["type"]=="message")
            selection=json.loads(message["content"][0]["text"])
        else:
            selection={"summary":"Your record shows {week_total}.","insights":[{"id":"logging_consistency","text":"You logged {week_logged_days}."}]}
        self.reply.body["output"][0]["content"][0]["text"]=json.dumps(selection)
        return super().generate(payload,ticket)


@pytest.mark.parametrize("kind",["trends","workout","analysis","runtime_analysis"])
def test_actual_personal_http_flow_and_free_saved_replay(tmp_path,monkeypatch,kind):
    from test_wonder_workout import live_body
    client,ledger,_,_,transport=client_for(tmp_path,monkeypatch)
    auth={"Authorization":"Bearer "+"t"*40}
    path="/v1/wonder/"+kind if kind!="runtime_analysis" else "/v3/wonder/analysis"
    with client:
        assert client.get("/v1/wonder/readiness").status_code==401
        assert client.get("/v1/wonder/readiness",headers=auth).json()["status"]=="ready"
        assert client.get("/v1/wonder/live",headers=auth).json()["live_available"] is False
        before=Path(ledger.path).read_bytes()
        assert client.post("/v1/wonder/live",json={"kind":"scenario","id":"complete","confirm_billable":True},headers=auth).status_code==503
        assert Path(ledger.path).read_bytes()==before
        if kind=="trends":
            assert client.post("/v1/beverages",headers=auth|{"Idempotency-Key":str(uuid4())},json={
                "category":"water","consumed_ml":250,"consumed_at":stamp(),"timezone":"America/New_York",
                "source":"manual"}).status_code==201
            view=client.get(path+"?timezone=America/New_York",headers=auth).json()
            body={"timezone":"America/New_York"}
        else:
            body=live_body()
            view=client.post(path+"/preview",json=body,headers=auth).json()
        assert view["live_available"] is True
        payload=body|{"payload_sha256":view["payload_sha256"],"consent_to_send":True}
        result=client.post(path,json=payload,headers=auth)
        assert result.status_code==200,result.text
        assert result.json()["saved"] is True and result.json()["replayed"] is False
        before=Path(ledger.path).read_bytes()
        replay=client.post(path,json=payload,headers=auth)
        assert replay.status_code==200 and replay.json()["replayed"] is True
        assert transport.calls==1 and Path(ledger.path).read_bytes()==before
        if "analysis" in kind:assert len(result.json()["result"]["sections"])==8
        assert client.get("/v1/wonder/readiness",headers=auth).json()["status"]=="blocked"


def test_configured_but_pending_personal_preview_cannot_advertise_live(tmp_path,monkeypatch):
    from test_wonder_workout import live_body
    client,ledger,_,_,transport=client_for(tmp_path,monkeypatch,pending=True)
    auth={"Authorization":"Bearer "+"t"*40}
    with client:
        before=Path(ledger.path).read_bytes()
        status=client.get("/v1/wonder/readiness",headers=auth).json()
        assert status["configured"] is True and status["status"]=="blocked"
        assert status["blocked_reasons"]==["current_invoice_finality_required"]
        body=live_body();view=client.post("/v1/wonder/analysis/preview",json=body,headers=auth).json()
        assert view["live_available"] is False
        refused=client.post("/v1/wonder/analysis",json=body|{"payload_sha256":view["payload_sha256"],"consent_to_send":True},headers=auth)
        assert refused.status_code==409 and refused.json()["code"]=="wonder_blocked"
        assert transport.calls==0 and Path(ledger.path).read_bytes()==before


def plan_reply():
    r=once_reply();r.body["id"]="resp_personal_training"
    r.body["output"][0]["content"][0]["text"]=json.dumps({"version":"muse-synthetic-plan-v1",
        "training_weights":{"base":2,"missing_covariates":1,"wide_noise":1,"outlier":1}})
    return r


def test_operator_training_purpose_requires_distinct_research_reference(tmp_path):
    ledger,owner,ninth=setup(tmp_path);p=complete(owner);owner.authorize(p);finalize(ledger,ninth)
    transport=Transport(plan_reply());g=gateway_api().OwnerPersonalWonderGateway(owner,p,transport)
    before=Path(ledger.path).read_bytes()
    with pytest.raises(RecognitionUnavailable):g.generate_training_plan(quote(),"synthetic-training-consent")
    assert transport.calls==0 and Path(ledger.path).read_bytes()==before


def test_generated_training_plan_requires_matching_gateway_ledger_digest(tmp_path):
    ledger,owner,ninth=setup(tmp_path)
    p=complete(owner,research_authorization_reference="synthetic-owner-research")
    owner.authorize(p);finalize(ledger,ninth)
    transport=Transport(plan_reply());g=gateway_api().OwnerPersonalWonderGateway(owner,p,transport)
    result=g.generate_training_plan(quote(),"synthetic-public-plan-consent")
    assert result["provenance"]["personal_data_used"] is False and transport.calls==1
    before=Path(ledger.path).read_bytes();owner.verify_training_plan_record(result)
    assert Path(ledger.path).read_bytes()==before
    for field in ("plan","attempt","purpose_hash","observations","origin","date"):
        wrong=deepcopy(result)
        if field=="plan":wrong["plan"]["training_weights"]["base"]=1
        elif field=="attempt":wrong["provenance"]["attempt_id"]=ninth
        elif field=="purpose_hash":wrong["provenance"]["payload_sha256"]="0"*64
        elif field=="observations":wrong["provider_observations"]["input_tokens"]=0
        elif field=="origin":wrong["provenance"]["mode"]="offline_stub"
        else:wrong["generated_at"]="2026-01-01T00:00:00Z"
        with pytest.raises((ValueError,BudgetDenied)):owner.verify_training_plan_record(wrong)
    with ledger.transaction() as db:
        db.execute("DELETE FROM live_events WHERE kind='wonder_personal_owner_training_plan_validated'")
    with pytest.raises((ValueError,BudgetDenied)):owner.verify_training_plan_record(result)


def test_missing_personal_result_storage_refuses_before_reservation(tmp_path,monkeypatch):
    from test_wonder_workout import live_body
    client,ledger,_,_,transport=client_for(tmp_path,monkeypatch)
    (tmp_path/"results").rmdir()
    auth={"Authorization":"Bearer "+"t"*40}
    with client:
        before=Path(ledger.path).read_bytes()
        status=client.get("/v1/wonder/readiness",headers=auth).json()
        assert status["status"]=="blocked" and "storage_unavailable" in status["blocked_reasons"]
        body=live_body();view=client.post("/v1/wonder/analysis/preview",json=body,headers=auth).json()
        response=client.post("/v1/wonder/analysis",json=body|{"payload_sha256":view["payload_sha256"],"consent_to_send":True},headers=auth)
        assert response.status_code==409 and transport.calls==0 and Path(ledger.path).read_bytes()==before


def test_private_operator_prepare_writes_only_incomplete_drafts(tmp_path, capsys):
    from scripts.wonder_personal_owner import main
    ledger, _, _ = setup(tmp_path)
    before = Path(ledger.path).read_bytes()
    descriptor, price = tmp_path / "draft.json", tmp_path / "price.json"
    main(["--database", str(ledger.path), "prepare", "--output", str(descriptor), "--quote-output", str(price)])
    result = json.loads(capsys.readouterr().out)
    assert result == {"status": "unapproved_draft_saved", "request_sent": False, "financial_state_changed": False}
    assert descriptor.stat().st_mode & 0o777 == price.stat().st_mode & 0o777 == 0o600
    draft = json.loads(descriptor.read_text())
    assert draft["risk_acceptance_reference"] is None and draft["cross_ledger_clear"] is False
    assert draft["waive_billing_wait"] is False and draft["billing_wait_waiver_reference"] is None
    assert json.loads(price.read_text())["all_charge_categories_verified"] is False
    with pytest.raises(SystemExit):
        main(["--database", str(ledger.path), "authorize", "--descriptor", str(descriptor)])
    assert Path(ledger.path).read_bytes() == before


def test_incomplete_private_draft_can_boot_for_blocked_preview(tmp_path, monkeypatch):
    from backend.app import create_app
    from test_wonder_workout import live_body
    _, ledger, owner, _, _ = client_for(tmp_path, monkeypatch, pending=True)
    private_json(tmp_path / "policy.json", owner.prepare())
    app = create_app(tmp_path / "draft-beverages.sqlite3", "t" * 40)
    auth = {"Authorization": "Bearer " + "t" * 40}
    with TestClient(app) as client:
        before = Path(ledger.path).read_bytes()
        status = client.get("/v1/wonder/readiness", headers=auth).json()
        assert status["configured"] is True and status["status"] == "blocked"
        assert {"owner_policy_not_recorded", "owner_policy_invalid", "current_invoice_finality_required"} <= set(status["blocked_reasons"])
        body = live_body()
        view = client.post("/v1/wonder/analysis/preview", json=body, headers=auth).json()
        assert view["explainable"] is True and view["live_available"] is False
        response = client.post("/v1/wonder/analysis", json=body | {
            "payload_sha256": view["payload_sha256"], "consent_to_send": True}, headers=auth)
        assert response.status_code == 409 and Path(ledger.path).read_bytes() == before


def test_old_holds_remain_allocation_exposure_after_ninth_finality(tmp_path):
    ledger, owner, ninth = setup(tmp_path)
    policy = complete(owner, observed_credits_micro_usd=1_000_000)
    owner.authorize(policy)
    finalize(ledger, ninth)
    with ledger.transaction() as db:
        held = db.execute("SELECT SUM(reserved) FROM live_attempts").fetchone()[0]
    assert owner.snapshot()["aggregate_exposure_micro_usd"] == held
    assert "budget_exhausted" in owner.readiness(policy, quote())["blocked_reasons"]
    before = Path(ledger.path).read_bytes()
    gateway = gateway_api().OwnerPersonalWonderGateway(owner, policy, Transport())
    with pytest.raises(RecognitionUnavailable):
        gateway.explain_analysis(analysis_facts(), quote(), "synthetic-consent")
    assert gateway.last_attempt is None and Path(ledger.path).read_bytes() == before


def test_official_owner_transport_uses_fixed_origin_and_one_exact_send(tmp_path, monkeypatch):
    import http.client
    ledger, owner, ninth = setup(tmp_path)
    policy = complete(owner)
    owner.authorize(policy)
    finalize(ledger, ninth)
    facts = analysis_facts()
    reply = analysis_reply(facts)
    sent = []

    class Response:
        status = 200

        def read(self, limit):
            raw = json.dumps(reply.body).encode()
            assert len(raw) < limit
            return raw

    class Connection:
        def __init__(self, host, *, timeout):
            assert (host, timeout) == ("api.meta.ai", 20)

        def request(self, method, path, *, body, headers):
            assert (method, path) == ("POST", "/v1/responses")
            assert headers["Authorization"] == "Bearer " + KEY
            sent.append(json.loads(body))

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(http.client, "HTTPSConnection", Connection)
    gateway = gateway_api().OwnerPersonalWonderGateway(
        owner, policy, gateway_api().OwnerPersonalMetaTransport(KEY))
    result = gateway.explain_analysis(facts, quote(), "synthetic-exact-consent")
    assert len(sent) == 1 and sent[0]["model"] == "muse-wonder-1.0"
    assert result["provider_observations"]["billed_cost_usd"] is None
    with pytest.raises(RecognitionUnavailable):
        gateway.explain_analysis(facts, quote(), "synthetic-exact-consent")
    assert len(sent) == 1
