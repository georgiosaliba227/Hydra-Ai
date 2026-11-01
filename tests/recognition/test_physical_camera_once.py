"""Nonbillable fixture tests for the exact owner-approved additional request."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import hashlib
import json
import socket

import pytest
from pydantic import ValidationError

import backend.meta_accounts as accounts
import backend.meta_physical_once as physical
from backend.meta_accounts import AccountLedger, now
from backend.meta_budget import BudgetDenied
from backend.meta_gateway import GuardedMetaGateway
from backend.meta_policy import MAX_INPUT_TOKENS
from backend.meta_provider import OfficialMetaTransport, request_payload
from backend.meta_observations import read_observation
from backend.recognition import RecognitionUnavailable
from test_guarded_meta import HASH, image, price, reply, FakeNotifier
from test_first_camera_risk import risk_evidence, risk_permit, FullBoundTransport

PRIOR = "11111111-2222-4333-8444-555555555555"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*a, **k): raise AssertionError("No paid requests in tests")
    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    monkeypatch.setattr(accounts, "APPROVED_CAMERA_SHA256", HASH)
    monkeypatch.setattr(physical, "IMAGE", HASH)
    base = AccountLedger(tmp_path / "synthetic.sqlite3")
    base.initialize_accounts()
    ev = risk_evidence()
    base.attest_account(ev)
    base.record_price(price())
    base.approve_risk_test(risk_permit(ev))
    original = GuardedMetaGateway(base, physical.ACCOUNT, FullBoundTransport(), FakeNotifier()).analyze(image())
    # Synthetic fixture only: give the previous attempt the production policy's
    # expected identifiers. No real provider or financial data is read.
    with base.transaction() as db:
        db.execute("UPDATE live_attempts SET id=?,provider_id=? WHERE id=?", (PRIOR, "resp_prior_synthetic", original.recognition_id))
    ledger = physical.PhysicalCameraLedger(base.path)
    with ledger.transaction() as db:
        prior = ledger.prior_digest(db, PRIOR)
    payload = request_payload(image())
    approval = physical.PhysicalApproval(
        image_sha256=HASH, payload_sha256=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",", ":"),allow_nan=False).encode()).hexdigest(),
        prior_attempt_id=PRIOR,prior_provider_id="resp_prior_synthetic",
        prior_row_sha256=prior,key_sha256=ev.key_sha256,
        provider_account_reference=ev.provider_account_reference,
        dashboard_gross_upper_micro_usd=120000,credits_lower_micro_usd=149880000,
        accepted_unknown_extra_charges=True,accepted_original_billing_pending=True,
        other_activity_stopped_and_no_other_pending=True,free_credit_photo_disclosure_accepted=True,
        automatic_topups_disabled=True,price=price(),observed_at=now(),valid_until=now()+timedelta(minutes=10),
        authorization_reference="synthetic-owner-approval",billing_reference="synthetic-billing",
        notification_reference="synthetic-delivery")
    return ledger, approval


def authorize(prepared):
    ledger, approval = prepared
    ledger.approve_physical_once(approval)
    return ledger, approval


def test_round_trip_preserves_original_and_original_controller_stays_blocked(prepared):
    ledger, approval = authorize(prepared)
    provider = FullBoundTransport(response=reply(id="resp_new_synthetic"))
    result = GuardedMetaGateway(ledger, physical.ACCOUNT, provider, FakeNotifier()).analyze(image())
    assert provider.calls == 1 and result.mode == "meta_live"
    assert read_observation(ledger.path,result.recognition_id)["input_sha256"] == HASH
    with ledger.transaction() as db:
        assert ledger.prior_digest(db, PRIOR) == approval.prior_row_sha256
        assert db.execute("SELECT frozen FROM live_accounts").fetchall() == [(1,)]
        assert db.execute("SELECT spent FROM controlled_permits").fetchall() == [(1,)]
        assert db.execute("SELECT actual,state FROM live_attempts ORDER BY created_at").fetchall() == [(None,"billing_pending"),(None,"billing_pending")]
        assert db.execute("SELECT COUNT(*) FROM live_finalities").fetchone() == (0,)
    with pytest.raises(RecognitionUnavailable):
        GuardedMetaGateway(ledger,physical.ACCOUNT,provider,FakeNotifier()).analyze(image())
    with pytest.raises(BudgetDenied):
        AccountLedger(ledger.path).reserve_first(physical.ACCOUNT,HASH,MAX_INPUT_TOKENS)
    assert provider.calls == 1


def test_approval_and_reservation_atomic_and_never_renewed(prepared):
    ledger, approval = authorize(prepared)
    with pytest.raises(BudgetDenied): ledger.approve_physical_once(approval)
    def reserve(_):
        try:return ledger.reserve_first(physical.ACCOUNT,HASH,MAX_INPUT_TOKENS)
        except BudgetDenied:return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(reserve,range(8)))
    assert sum(value is not None for value in results) == 1
    with pytest.raises(BudgetDenied):
        physical.PhysicalCameraLedger(ledger.path).reserve_first(physical.ACCOUNT,HASH,MAX_INPUT_TOKENS)


@pytest.mark.parametrize("change",[
    {"image_sha256":"0"*64},{"account_id":"aminealichaouche"},
    {"accepted_unknown_extra_charges":False},{"accepted_original_billing_pending":1},
    {"other_activity_stopped_and_no_other_pending":False},{"free_credit_photo_disclosure_accepted":False},
    {"automatic_topups_disabled":False},{"observed_at":now()-timedelta(hours=1)},
    {"valid_until":now()+timedelta(hours=1)},{"intended_maximum_micro_usd":3000000},
    {"provider_total_bound_micro_usd":0},{"notification_reference":" "},
])
def test_invalid_or_unaccepted_policy(prepared,change):
    _,approval=prepared
    with pytest.raises(ValidationError): physical.PhysicalApproval.model_validate(approval.model_dump()|change)


@pytest.mark.parametrize("change",[
    {"dashboard_gross_upper_micro_usd":20000000},
    {"credits_lower_micro_usd":100000000},{"prior_row_sha256":"0"*64},
    {"key_sha256":"0"*64},{"provider_account_reference":"different-account"},
])
def test_credit_checkpoint_and_history_binding(prepared,change):
    ledger,approval=prepared
    with pytest.raises(BudgetDenied):ledger.approve_physical_once(physical.PhysicalApproval.model_validate(approval.model_dump()|change))


def test_exact_payload_and_credential_and_once_only_ticket(prepared):
    ledger, approval=authorize(prepared)
    attempt=ledger.reserve_first(physical.ACCOUNT,HASH,MAX_INPUT_TOKENS)
    with pytest.raises(BudgetDenied):ledger.mark_dispatched(attempt,"0"*64)
    ticket=ledger.mark_dispatched(attempt,approval.payload_sha256)
    with pytest.raises(BudgetDenied):ticket.claim(request_payload(image()),input_bound=MAX_INPUT_TOKENS,credential_fingerprint="0"*64)
    ticket.claim(request_payload(image()),input_bound=MAX_INPUT_TOKENS,credential_fingerprint=approval.key_sha256)
    with pytest.raises(BudgetDenied):ticket.claim(request_payload(image()),input_bound=MAX_INPUT_TOKENS,credential_fingerprint=approval.key_sha256)


def test_expiry_rechecked_before_network_and_crash_hold_remains(prepared,monkeypatch):
    ledger,approval=authorize(prepared)
    attempt=ledger.reserve_first(physical.ACCOUNT,HASH,MAX_INPUT_TOKENS)
    monkeypatch.setattr(physical,"now",lambda:approval.valid_until+timedelta(seconds=1))
    with pytest.raises(BudgetDenied):ledger.mark_dispatched(attempt,approval.payload_sha256)
    with ledger.transaction() as db:
        assert db.execute("SELECT reserved,actual,state FROM live_attempts WHERE id=?",(attempt,)).fetchone()==(1312256,None,"reserved")


def test_official_transport_mocked_http_uses_single_ticket(prepared,monkeypatch):
    ledger,approval=authorize(prepared)
    calls=[]
    class Response:
        status=200
        def read(self,size):return json.dumps(reply(id="resp_official_synthetic").body).encode()
    class Connection:
        def __init__(self,host,timeout):assert (host,timeout)==("api.meta.ai",20)
        def request(self,method,path,body,headers):
            calls.append(json.loads(body));assert method=="POST" and path=="/v1/responses"
        def getresponse(self):return Response()
        def close(self):pass
    monkeypatch.setattr("http.client.HTTPSConnection",Connection)
    transport=OfficialMetaTransport("synthetic-key")
    GuardedMetaGateway(ledger,physical.ACCOUNT,transport,FakeNotifier()).analyze(image())
    assert len(calls)==1
    assert calls[0]["max_output_tokens"]==512 and "tools" not in calls[0]


def test_http_once_service_restores_mock_and_saves_private_evidence(prepared,tmp_path):
    from fastapi.testclient import TestClient
    from backend.app import create_app
    from backend.meta_physical_service import arm_physical_once
    from test_guarded_meta import TOKEN,AUTH
    ledger,_=authorize(prepared)
    app=create_app(tmp_path/'beverages-only.sqlite3',TOKEN)
    provider=FullBoundTransport(response=reply(id='resp_http_synthetic'))
    output=tmp_path/'result.json'
    arm_physical_once(app,ledger,provider,FakeNotifier(),output)
    client=TestClient(app)
    assert client.get('/health').json()['billable_requests_enabled'] is True
    response=client.post('/v1/recognitions',json=image().model_dump(mode='json'),headers=AUTH)
    assert response.status_code==200
    assert response.json()['mode']=='meta_live'
    assert client.get('/health').json()['billable_requests_enabled'] is False
    assert client.get('/v1/recognition-capabilities',headers=AUTH).json()['mode']=='mock'
    assert json.loads(output.read_text())['backend_returned_to_mock'] is True
    assert output.stat().st_mode & 0o777 == 0o600
    assert client.post('/v1/recognitions',json=image().model_dump(mode='json'),headers=AUTH).status_code==503
    assert provider.calls==1


def test_service_timeout_keeps_hold_and_disables_live(prepared,tmp_path):
    from fastapi.testclient import TestClient
    from backend.app import create_app
    from backend.meta_physical_service import arm_physical_once
    from test_guarded_meta import TOKEN,AUTH
    ledger,_=authorize(prepared)
    app=create_app(tmp_path/'beverages-only.sqlite3',TOKEN)
    provider=FullBoundTransport(fault=TimeoutError())
    output=tmp_path/'result.json'
    arm_physical_once(app,ledger,provider,FakeNotifier(),output)
    client=TestClient(app)
    assert client.post('/v1/recognitions',json=image().model_dump(mode='json'),headers=AUTH).status_code==503
    assert client.get('/health').json()['billable_requests_enabled'] is False
    with ledger.transaction() as db:
        assert db.execute('SELECT SUM(reserved) FROM live_attempts WHERE actual IS NULL').fetchone()==(2624512,)
    assert json.loads(output.read_text())['error']=='unavailable_or_unresolved_do_not_retry'
