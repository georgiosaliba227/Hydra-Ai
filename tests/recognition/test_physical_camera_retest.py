"""Synthetic-only verification of the separately authorized 1,024-token call."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import socket

import pytest
from pydantic import ValidationError

import backend.meta_physical_retest as retest
from backend.meta_accounts import AccountLedger
from backend.meta_budget import BudgetDenied
from backend.meta_gateway import GuardedMetaGateway
from backend.meta_observations import read_observation
from backend.meta_policy import OUTPUT_LIMIT, MAX_INPUT_TOKENS
from backend.meta_physical_service import arm_physical_once
from backend.meta_provider import OfficialMetaTransport, request_payload
from backend.recognition import RecognitionUnavailable
from test_guarded_meta import HASH, image, reply, FakeNotifier, TOKEN, AUTH
from test_first_camera_risk import FullBoundTransport
from test_physical_camera_once import prepared


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*a, **k): raise AssertionError("Retest tests cannot spend")
    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.fixture
def ready(prepared, monkeypatch):
    first, approval = prepared
    first.approve_physical_once(approval)
    usage = {"input_tokens":100,"output_tokens":512,"total_tokens":612,"input_tokens_details":{"cached_tokens":0}}
    provider = FullBoundTransport(response=reply(id="resp_truncated_synthetic",status="incomplete",incomplete_details={"reason":"max_output_tokens"},usage=usage))
    with pytest.raises(RecognitionUnavailable):
        GuardedMetaGateway(first,retest.ACCOUNT,provider,FakeNotifier()).analyze(image())
    ledger = retest.RetestLedger(first.path)
    with ledger.transaction() as db:
        second = db.execute("SELECT id,provider_id FROM live_attempts WHERE id!=?",(approval.prior_attempt_id,)).fetchone()
        row_hash = ledger.prior_digest(db,second[0])
        permit_hash = ledger.previous_permit_digest(db)
        prior_rows = db.execute("SELECT * FROM live_attempts ORDER BY created_at").fetchall()
    payload = retest.retest_payload(image())
    raw = approval.model_dump() | {
        "policy_version":retest.RETEST_POLICY,
        "payload_sha256":hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest(),
        "previous_physical_attempt_id":second[0],"previous_physical_provider_id":second[1],
        "previous_physical_row_sha256":row_hash,"previous_physical_permit_sha256":permit_hash,
        "both_prior_holds_accepted":True}
    auth = retest.RetestApproval.model_validate(raw)
    monkeypatch.setattr(retest,"IMAGE",HASH)
    return ledger,auth,prior_rows


def mocked_provider(monkeypatch,outputs=700,status="completed"):
    usage={"input_tokens":100,"output_tokens":outputs,"total_tokens":100+outputs,"input_tokens_details":{"cached_tokens":0}}
    response=reply(id="resp_retest_synthetic",usage=usage,status=status,incomplete_details=None if status=="completed" else {"reason":"max_output_tokens"})
    calls=[]
    class Response:
        status=200
        def read(self,size):return json.dumps(response.body).encode()
    class Connection:
        def __init__(self,host,timeout):assert (host,timeout)==("api.meta.ai",20)
        def request(self,method,path,body,headers):
            assert (method,path)==("POST","/v1/responses")
            payload=json.loads(body);calls.append(payload)
            assert payload["max_output_tokens"]==1024
            assert not any(k in payload for k in ("tools","previous_response_id","conversation"))
        def getresponse(self):return Response()
        def close(self):pass
    monkeypatch.setattr("http.client.HTTPSConnection",Connection)
    return calls,retest.RetestTransport("synthetic-key")


def test_complete_retest_over_512_preserves_both_holds_and_uses_once(ready,monkeypatch,tmp_path):
    from backend.app import create_app
    from fastapi.testclient import TestClient
    ledger,approval,prior_rows=ready
    ledger.approve_physical_once(approval)
    calls,provider=mocked_provider(monkeypatch)
    app=create_app(tmp_path/'beverages.sqlite3',TOKEN)
    arm_physical_once(app,ledger,provider,FakeNotifier(),tmp_path/'result.json')
    client=TestClient(app)
    response=client.post('/v1/recognitions',json=image().model_dump(mode='json'),headers=AUTH)
    assert response.status_code==200
    attempt=response.json()['recognition_id']
    assert client.get('/health').json()['billable_requests_enabled'] is False
    with ledger.transaction() as db:
        assert db.execute('SELECT * FROM live_attempts WHERE id!=? ORDER BY created_at',(attempt,)).fetchall()==prior_rows
        assert db.execute('SELECT reserved,actual,state FROM live_attempts WHERE id=?',(attempt,)).fetchone()==(1313792,None,'billing_pending')
        assert db.execute('SELECT SUM(reserved) FROM live_attempts WHERE actual IS NULL').fetchone()==(3938304,)
        assert db.execute('SELECT frozen FROM live_accounts').fetchall()==[(1,)]
        assert db.execute('SELECT spent FROM controlled_permits').fetchall()==[(1,)]
    observation=read_observation(ledger.path,attempt)
    assert observation['input_sha256']==HASH and observation['usage']['output_tokens']==700
    assert observation['transport_kind']=='official_meta_https'
    assert observation['final_gross_micro_usd'] is None
    with pytest.raises(BudgetDenied):ledger.approve_physical_once(approval)
    with pytest.raises(BudgetDenied):ledger.reserve_first(retest.ACCOUNT,HASH,retest.RETEST_INPUT)
    assert len(calls)==1


def test_default_transport_and_ledger_limits_stay_512(ready):
    ledger,approval,_=ready
    assert OUTPUT_LIMIT==512 and request_payload(image())["max_output_tokens"]==512
    assert OfficialMetaTransport('synthetic-key').input_bound(request_payload(image()))==MAX_INPUT_TOKENS
    with ledger.transaction() as db:assert AccountLedger(ledger.path).output_bound_for_attempt(db,'anything')==512
    ledger.approve_physical_once(approval)
    assert ledger.quote(retest.ACCOUNT,retest.RETEST_INPUT)[1]==1313792
    with pytest.raises(BudgetDenied):ledger.quote(retest.ACCOUNT,MAX_INPUT_TOKENS)


@pytest.mark.parametrize('change',[
    {'both_prior_holds_accepted':False},{'both_prior_holds_accepted':1},
    {'combined_output_limit':2048},{'policy_version':'georgio-physical-camera-once-risk-v1'},
    {'intended_maximum_micro_usd':3000000},{'image_sha256':'0'*64},
])
def test_retest_authorization_is_explicit_and_fixed(ready,change):
    _,approval,_=ready
    with pytest.raises(ValidationError):retest.RetestApproval.model_validate(approval.model_dump()|change)


@pytest.mark.parametrize('change',[
    {'previous_physical_row_sha256':'0'*64},{'previous_physical_permit_sha256':'0'*64},
    {'credits_lower_micro_usd':100000000},{'dashboard_gross_upper_micro_usd':20000000},
])
def test_history_credit_reserve_and_checkpoint_rechecked(ready,change):
    ledger,approval,_=ready
    with pytest.raises(BudgetDenied):ledger.approve_physical_once(retest.RetestApproval.model_validate(approval.model_dump()|change))


def test_atomic_retest_and_ticket_payload_substitution(ready):
    ledger,approval,_=ready
    ledger.approve_physical_once(approval)
    def reserve(_):
        try:return ledger.reserve_first(retest.ACCOUNT,HASH,retest.RETEST_INPUT)
        except BudgetDenied:return None
    with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(reserve,range(8)))
    assert sum(v is not None for v in results)==1
    attempt=next(v for v in results if v is not None)
    with pytest.raises(BudgetDenied):ledger.mark_dispatched(attempt,'0'*64)
    ticket=ledger.mark_dispatched(attempt,approval.payload_sha256)
    with pytest.raises(BudgetDenied):ticket.claim(request_payload(image()),input_bound=retest.RETEST_INPUT,credential_fingerprint=approval.key_sha256)
    ticket.claim(retest.retest_payload(image()),input_bound=retest.RETEST_INPUT,credential_fingerprint=approval.key_sha256)
    with pytest.raises(BudgetDenied):ticket.claim(retest.retest_payload(image()),input_bound=retest.RETEST_INPUT,credential_fingerprint=approval.key_sha256)


@pytest.mark.parametrize('outputs,status',[(1024,'incomplete'),(1025,'completed')])
def test_incomplete_or_over_limit_output_keeps_every_hold(ready,monkeypatch,outputs,status):
    ledger,approval,_=ready
    ledger.approve_physical_once(approval)
    calls,provider=mocked_provider(monkeypatch,outputs,status)
    with pytest.raises(RecognitionUnavailable):GuardedMetaGateway(ledger,retest.ACCOUNT,provider,FakeNotifier()).analyze(image())
    with ledger.transaction() as db:
        assert db.execute('SELECT COUNT(*) FROM live_attempts WHERE actual IS NULL').fetchone()==(3,)
        assert db.execute('SELECT SUM(reserved) FROM live_attempts').fetchone()==(3938304,)
    assert len(calls)==1
