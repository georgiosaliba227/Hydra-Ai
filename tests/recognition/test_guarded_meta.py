"""No Meta/GitHub connections: synthetic accounts, replies and fault injection."""
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.meta_accounts import AccountLedger, Evidence, Price, FirstPermit, ACCOUNTS
from backend.meta_budget import BudgetDenied, MetaBudget
from backend.meta_gateway import GuardedMetaGateway, GitHubNotifier
from backend.meta_provider import OfficialMetaTransport, ProviderReply, request_payload, parse_recognition
from backend.recognition import AnalysisRequest, RecognitionUnavailable

TOKEN = 'test-only-local-development-token-00000000'
AUTH = {'Authorization': 'Bearer ' + TOKEN}
JPEG = b'\xff\xd8\xff\xc0\x00\x0b\x08\x00\x10\x00\x10\x01\x01\x11\x00\xff\xd9'
IMAGE = base64.b64encode(JPEG).decode()
HASH = hashlib.sha256(JPEG).hexdigest()


def future(): return datetime.now(timezone.utc) + timedelta(hours=1)


def evidence(account=ACCOUNTS[0], baseline=0, credits=150_000_000):
    return Evidence(account_id=account, provider_account_reference="synthetic-meta-team-"+account, key_sha256=hashlib.sha256(("synthetic-key" if account==ACCOUNTS[0] else "synthetic-amine-key").encode()).hexdigest(), gross_micro_usd=baseline, credits_remaining_micro_usd=credits,
        valid_until=future(), credits_expire=future(), reference='synthetic-dashboard-only',
        billing_verified=True, hackathon_terms_verified=True, exclusive_gateway_key_verified=True,
        provider_limits_verified=True, retention_reviewed=True, all_charge_categories_verified=True,
        extra_charge_bound_micro_usd=0)


def price(version='fixture-v1'):
    return Price(version=version, valid_until=future(), reviewed_by=ACCOUNTS, reference='synthetic-price-review')


def image():
    return AnalysisRequest(image_base64=IMAGE, photo_consent=True, mode='meta_live', meta_photo_consent=True)


def reply(**changes):
    result={'id':'resp_testonly', 'model':'muse-spark-1.3','status':'completed','error':None,'incomplete_details':None,
        'usage':{'input_tokens':100,'output_tokens':50,'total_tokens':150,'input_tokens_details':{'cached_tokens':0}},
        'output':[{'type':'message','role':'assistant','status':'completed','content':[{'type':'output_text','text':json.dumps({'candidates':[{'category':'tea','brand':None,'product':None,'container_ml':300,'confidence':'low','uncertainty_reasons':['Capacity uncertain; verify']}]})}]}]}
    return ProviderReply(200,result | changes)


class FakeTransport:
    credential_fingerprint=hashlib.sha256(b"synthetic-key").hexdigest()
    def __init__(self, response=None, fault=None, account=ACCOUNTS[0]):
        self.response=response or reply(); self.calls=0; self.fault=fault
        self.credential_fingerprint=evidence(account).key_sha256
    def input_bound(self, payload): return 1000  # Synthetic bound only; no real sender.
    def generate(self, payload, ticket):
        ticket.claim(payload, input_bound=1000, credential_fingerprint=self.credential_fingerprint)
        self.calls+=1
        assert payload['model']=='muse-spark-1.3' and payload['max_output_tokens']==512
        assert not any(k in payload for k in ('tools','previous_response_id','conversation','files'))
        assert payload['store'] is False and payload['background'] is False
        if self.fault: raise self.fault
        return self.response


class FakeNotifier:
    def __init__(self, fail=False): self.delivered=[]; self.fail=fail
    def deliver(self, notice):
        if self.fail: raise BudgetDenied('synthetic notification fault')
        self.delivered.append(notice['recipient']); return 'synthetic-delivery-receipt'


def setup(tmp_path, account=ACCOUNTS[0], baseline=0, credits=150_000_000, further=None):
    ledger=AccountLedger(tmp_path/'authority.sqlite3'); ledger.initialize_accounts()
    ledger.attest_account(evidence(account,baseline,credits)); ledger.record_price(price())
    ledger.approve_first_test(FirstPermit(account_id=account,image_sha256=HASH,price_version='fixture-v1',
        developer_approvals=ACCOUNTS, spending_authority_reference='synthetic-one-request-approval',
        account_owner_authorization_reference='synthetic-account-owner-approval',image_owner_consent_reference='synthetic-image-owner-approval',valid_until=future(),
        further_spend_approval_reference=further))
    return ledger


def test_actual_transport_bound_blocks_before_any_network(tmp_path, monkeypatch):
    ledger=setup(tmp_path)
    def forbidden(*args,**kwargs): raise AssertionError('No external request allowed')
    monkeypatch.setattr('http.client.HTTPSConnection.request', forbidden)
    gateway=GuardedMetaGateway(ledger,ACCOUNTS[0],OfficialMetaTransport('synthetic-key'),FakeNotifier())
    with pytest.raises(RecognitionUnavailable): gateway.analyze(image())
    assert price().cost(1_048_576 - 512,512)==1_312_256
    assert ledger.project_view()['project_reserved_micro_usd']==0


def test_full_mocked_live_round_trip_and_receipt(tmp_path):
    ledger=setup(tmp_path); provider=FakeTransport()
    result=GuardedMetaGateway(ledger,ACCOUNTS[0],provider,FakeNotifier()).analyze(image())
    assert result.mode=='meta_live' and result.candidates[0].category=='tea'
    assert result.candidates[0].product_id is None
    assert ledger.receipt(result.recognition_id)['account_id']==ACCOUNTS[0]
    view=ledger.project_view(); assert view['known_accounts_gross_micro_usd']==338 and view['project_reserved_micro_usd']==0
    with pytest.raises(RecognitionUnavailable): GuardedMetaGateway(ledger,ACCOUNTS[0],provider,FakeNotifier()).analyze(image())
    assert provider.calls==1


def test_multiple_process_connections_one_project_request(tmp_path):
    ledger=setup(tmp_path); provider=FakeTransport()
    def run(_):
        try: GuardedMetaGateway(AccountLedger(ledger.path),ACCOUNTS[0],provider,FakeNotifier()).analyze(image()); return True
        except RecognitionUnavailable: return False
    with ThreadPoolExecutor(max_workers=12) as pool: assert sum(pool.map(run,range(24)))==1
    assert provider.calls==1


def test_accounts_never_pool_or_fallback(tmp_path):
    ledger=setup(tmp_path, credits=1)
    ledger.attest_account(evidence(ACCOUNTS[1]))
    a,b=FakeTransport(),FakeTransport()
    for account,provider in zip(ACCOUNTS,(a,b)):
        with pytest.raises(RecognitionUnavailable): GuardedMetaGateway(ledger,account,provider,FakeNotifier()).analyze(image())
    assert a.calls==b.calls==0
    assert len(ledger.project_view()['accounts'])==2
    assert ledger.project_view()['credits_transferable'] is False


@pytest.mark.parametrize('baseline,further,allowed',[(99_999_000,None,False),(99_999_000,'synthetic-further-approval',True),(119_999_000,'synthetic-further-approval',False),(150_000_000,'synthetic-further-approval',False)])
def test_account_thresholds(tmp_path,baseline,further,allowed):
    ledger=setup(tmp_path,baseline=baseline,further=further); provider=FakeTransport()
    gateway=GuardedMetaGateway(ledger,ACCOUNTS[0],provider,FakeNotifier())
    if allowed: gateway.analyze(image())
    else:
        with pytest.raises(RecognitionUnavailable): gateway.analyze(image())
    assert provider.calls==int(allowed)


def test_notices_delivered_to_both_and_delivery_failure_blocks(tmp_path):
    ledger=setup(tmp_path,baseline=74_999_000); provider=FakeTransport(); notifier=FakeNotifier()
    GuardedMetaGateway(ledger,ACCOUNTS[0],provider,notifier).analyze(image())
    assert set(notifier.delivered)==set(ACCOUNTS)
    assert all(n['delivered_at'] for n in ledger.notices())
    other=tmp_path/'other';other.mkdir();ledger=setup(other,baseline=74_999_000);provider=FakeTransport()
    with pytest.raises(RecognitionUnavailable): GuardedMetaGateway(ledger,ACCOUNTS[0],provider,FakeNotifier(fail=True)).analyze(image())
    assert provider.calls==0 and ledger.project_view()['project_reserved_micro_usd']>0


@pytest.mark.parametrize('change',[{'status':'incomplete'},{'output':[]},{'output':[{'type':'message','role':'assistant','status':'completed','content':[{'type':'refusal','refusal':'sensitive raw text'}]}]}, {'output':[{'type':'function_call'}]}, {'output':[{'type':'message','role':'assistant','status':'completed','content':[{'type':'output_text','text':'invalid JSON secret'}]}]}])
def test_billed_bad_outputs_settle_before_recognition_failure(tmp_path,change):
    ledger=setup(tmp_path); provider=FakeTransport(reply(**change))
    with pytest.raises(RecognitionUnavailable): GuardedMetaGateway(ledger,ACCOUNTS[0],provider,FakeNotifier()).analyze(image())
    assert provider.calls==1 and ledger.project_view()['project_reserved_micro_usd']==0
    assert ledger.project_view()['known_accounts_gross_micro_usd']==338


@pytest.mark.parametrize('bad_usage',[None,{}, {'input_tokens':True}])
def test_missing_or_uncertain_usage_holds_reservation(tmp_path,bad_usage):
    ledger=setup(tmp_path);provider=FakeTransport(reply(usage=bad_usage))
    with pytest.raises(RecognitionUnavailable): GuardedMetaGateway(ledger,ACCOUNTS[0],provider,FakeNotifier()).analyze(image())
    assert ledger.project_view()['project_reserved_micro_usd']>0
    restored=AccountLedger(ledger.path)
    restored.record_reconciliation_reference(ACCOUNTS[0],'unverified-dashboard-reference')
    with pytest.raises(RecognitionUnavailable): GuardedMetaGateway(restored,ACCOUNTS[0],provider,FakeNotifier()).analyze(image())
    assert provider.calls==1


def test_timeout_crash_and_failed_dispatch_keep_exposure(tmp_path):
    ledger=setup(tmp_path);provider=FakeTransport(fault=TimeoutError('secret raw socket error'))
    with pytest.raises(RecognitionUnavailable): GuardedMetaGateway(ledger,ACCOUNTS[0],provider,FakeNotifier()).analyze(image())
    assert provider.calls==1 and AccountLedger(ledger.path).project_view()['project_reserved_micro_usd']>0
    other=tmp_path/'crash';other.mkdir();ledger=setup(other)
    attempt=ledger.reserve_first(ACCOUNTS[0],HASH,1000)
    restored=AccountLedger(ledger.path)
    assert restored.project_view()['project_reserved_micro_usd']>0
    with pytest.raises(BudgetDenied): restored.reserve_first(ACCOUNTS[0],HASH,1000)
    restored.mark_dispatched(attempt, "0"*64)
    with pytest.raises(BudgetDenied): restored.mark_dispatched(attempt, "0"*64)


def test_expired_changed_prices_and_bad_image_refuse_without_send(tmp_path):
    ledger=setup(tmp_path);provider=FakeTransport()
    with sqlite3.connect(ledger.path) as db:
        row=db.execute('SELECT snapshot FROM live_prices').fetchone(); snapshot=json.loads(row[0]);snapshot['input_micro_per_million']=1
        db.execute('UPDATE live_prices SET snapshot=?',(json.dumps(snapshot),))
    with pytest.raises(RecognitionUnavailable): GuardedMetaGateway(ledger,ACCOUNTS[0],provider,FakeNotifier()).analyze(image())
    assert provider.calls==0


def test_corrupt_uninitialized_locked_ledgers_fail_closed(tmp_path):
    bad=tmp_path/'broken';bad.write_bytes(b'corrupt');bad.chmod(0o600)
    for path in (bad,tmp_path/'absent.sqlite3'):
        provider=FakeTransport()
        with pytest.raises(RecognitionUnavailable): GuardedMetaGateway(AccountLedger(path),ACCOUNTS[0],provider,FakeNotifier()).analyze(image())
        assert provider.calls==0
    ledger=setup(tmp_path);provider=FakeTransport()
    with sqlite3.connect(ledger.path) as db:
        db.execute('BEGIN IMMEDIATE')
        with pytest.raises(RecognitionUnavailable): GuardedMetaGateway(ledger,ACCOUNTS[0],provider,FakeNotifier()).analyze(image())
    assert provider.calls==0


def test_no_legacy_spend_or_account_reset(tmp_path):
    ledger=setup(tmp_path)
    with pytest.raises(BudgetDenied): MetaBudget(ledger.path).initialize(historical_micro_usd=0,reconciliation_reference='reset')
    with pytest.raises(BudgetDenied): ledger.attest_account(evidence())
    with pytest.raises(BudgetDenied): ledger.approve_first_test(FirstPermit(account_id=ACCOUNTS[1],image_sha256=HASH,price_version='fixture-v1',developer_approvals=ACCOUNTS,spending_authority_reference='not-new-authority',account_owner_authorization_reference='synthetic-account-owner-approval',image_owner_consent_reference='not-new-authority',valid_until=future()))


def test_http_sanitization_consent_and_no_caller_usage(tmp_path):
    ledger=setup(tmp_path); provider=FakeTransport(fault=TimeoutError('secret-provider-detail'))
    app=create_app(tmp_path/'authority.sqlite3',TOKEN)
    app.state.recognizer=GuardedMetaGateway(ledger,ACCOUNTS[0],provider,FakeNotifier());app.state.recognition_mode='meta_live'
    with TestClient(app) as client:
        payload={'image_base64':IMAGE,'photo_consent':True,'mode':'meta_live','meta_photo_consent':False}
        assert client.post('/v1/recognitions',json=payload,headers=AUTH).status_code==503
        assert provider.calls==0
        payload['meta_photo_consent']=True
        assert client.post('/v1/recognitions',json=payload|{'usage':{'input_tokens':0}},headers=AUTH).status_code==422
        r=client.post('/v1/recognitions',json=payload,headers=AUTH)
        assert r.status_code==503 and not r.json()['retryable']
        assert 'secret' not in r.text and IMAGE not in r.text


def test_startup_without_credentials_and_defaults(tmp_path,monkeypatch):
    monkeypatch.setenv('HYDRA_AI_MODE','guarded_meta');monkeypatch.setenv('META_BILLABLE_REQUESTS_ENABLED','true');monkeypatch.setenv('HYDRA_META_ACCOUNT',ACCOUNTS[0]);monkeypatch.delenv('HYDRA_META_GEORGIO_API_KEY',raising=False)
    with pytest.raises(ValueError): create_app(tmp_path/'startup.sqlite3',TOKEN)
    monkeypatch.setenv('HYDRA_AI_MODE','mock');monkeypatch.setenv('META_BILLABLE_REQUESTS_ENABLED','false')
    with TestClient(create_app(tmp_path/'startup.sqlite3',TOKEN)) as c: assert c.get('/health').json()['billable_requests_enabled'] is False


def test_live_receipt_confirmed_log_and_account_view(tmp_path):
    ledger=setup(tmp_path); ledger.attest_account(evidence(ACCOUNTS[1],baseline=42))
    app=create_app(tmp_path/'authority.sqlite3',TOKEN)
    app.state.recognizer=GuardedMetaGateway(ledger,ACCOUNTS[0],FakeTransport(),FakeNotifier());app.state.recognition_mode='meta_live'
    with TestClient(app) as client:
        r=client.post('/v1/recognitions',json=image().model_dump(),headers=AUTH)
        assert r.status_code==200,r.text
        receipt=r.json()['recognition_id']
        payload=dict(category='Corrected tea',consumed_ml=125,container_ml=300,recognition_id=receipt,
            consumed_at='2026-10-26T15:00:00Z',timezone='America/New_York',source='confirmed_recognition')
        key=str(uuid4()); headers=AUTH|{'Idempotency-Key':key}
        saved=client.post('/v1/beverages',json=payload,headers=headers)
        assert saved.status_code==201,saved.text
        assert 'recognition-v1:meta_live' in saved.json()['provenance'] and ACCOUNTS[0] in saved.json()['provenance']
        assert saved.json()['nutrition'] is None
        assert client.post('/v1/beverages',json=payload,headers=headers).status_code==200
        forged=client.post('/v1/beverages',json=payload|{'recognition_id':str(uuid4())},headers=AUTH|{'Idempotency-Key':str(uuid4())})
        assert forged.status_code==422
        view=client.get('/v1/meta/spending',headers=AUTH).json()
        assert view['project_gross_micro_usd']==380 and len(view['accounts'])==2
        assert 'credits_total' not in view and view['credits_transferable'] is False
        assert client.get('/v1/meta/spending').status_code==401


def test_actual_network_send_requires_one_use_exact_payload_ticket(tmp_path,monkeypatch):
    ledger=setup(tmp_path); payload=request_payload(image())
    attempt=ledger.reserve_first(ACCOUNTS[0],HASH,1000)
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    ticket=ledger.mark_dispatched(attempt,digest)
    transport=OfficialMetaTransport('synthetic-key')
    with pytest.raises(RecognitionUnavailable): transport.generate(payload,None)
    with pytest.raises(BudgetDenied): ticket.claim(payload|{'tools':[{}]},input_bound=1000,credential_fingerprint=FakeTransport.credential_fingerprint)
    ticket.claim(payload,input_bound=1000,credential_fingerprint=FakeTransport.credential_fingerprint)
    with pytest.raises(BudgetDenied): transport.generate(payload,ticket)


def test_pricing_expiry_and_credit_expiry_independent_per_account(tmp_path):
    ledger=setup(tmp_path);ledger.attest_account(evidence(ACCOUNTS[1]))
    with sqlite3.connect(ledger.path) as db:
        raw=json.loads(db.execute('SELECT evidence FROM live_accounts WHERE account_id=?',(ACCOUNTS[0],)).fetchone()[0])
        raw['credits_expire']='2000-01-01T00:00:00Z'
        db.execute('UPDATE live_accounts SET evidence=? WHERE account_id=?',(json.dumps(raw),ACCOUNTS[0]))
    provider=FakeTransport()
    with pytest.raises(RecognitionUnavailable): GuardedMetaGateway(ledger,ACCOUNTS[0],provider,FakeNotifier()).analyze(image())
    # A's expired evidence is never replaced with B's balance/credential.
    assert provider.calls==0
    with sqlite3.connect(ledger.path) as db:
        raw=json.loads(db.execute('SELECT snapshot FROM live_prices').fetchone()[0]);raw['valid_until']='2000-01-01T00:00:00Z'
        db.execute('UPDATE live_prices SET snapshot=?',(json.dumps(raw),))
    with pytest.raises(BudgetDenied): ledger.quote(ACCOUNTS[0],1000)


def test_credit_and_billing_evidence_cannot_be_assumed(tmp_path):
    from pydantic import ValidationError
    raw=evidence().model_dump()
    for changes in ({'billing_verified':False},{'billing_verified':1},{'hackathon_terms_verified':False},{'gross_micro_usd':True},{'credits_remaining_micro_usd':150000001}):
        with pytest.raises(ValidationError): Evidence.model_validate(raw|changes)
    ledger=setup(tmp_path); provider=FakeTransport()
    wrong=image().model_copy(update={'image_base64':base64.b64encode(JPEG[:-2]+b'x'+JPEG[-2:]).decode()})
    with pytest.raises(RecognitionUnavailable): GuardedMetaGateway(ledger,ACCOUNTS[0],provider,FakeNotifier()).analyze(wrong)
    assert provider.calls==0


def test_known_over_bound_usage_is_recorded_and_frozen(tmp_path):
    ledger=setup(tmp_path)
    usage={'input_tokens':10000,'output_tokens':513,'total_tokens':10513,'input_tokens_details':{'cached_tokens':0},'sensitive_extra':'must not persist'}
    provider=FakeTransport(reply(usage=usage))
    with pytest.raises(RecognitionUnavailable): GuardedMetaGateway(ledger,ACCOUNTS[0],provider,FakeNotifier()).analyze(image())
    view=ledger.project_view()
    assert view['known_accounts_gross_micro_usd']>0 and view['accounts'][0]['frozen']
    assert b'sensitive_extra' not in (tmp_path/'authority.sqlite3').read_bytes()


@pytest.mark.parametrize("account", ACCOUNTS)
def test_separate_processes_cannot_consume_project_permit_twice(tmp_path, account):
    import subprocess,sys
    ledger=setup(tmp_path, account=account)
    code='''from backend.meta_accounts import AccountLedger
from backend.meta_budget import BudgetDenied
import sys
try:
 AccountLedger(sys.argv[1]).reserve_first(sys.argv[3],sys.argv[2],1000)
 print("reserved")
except BudgetDenied: print("denied")
'''
    def child(_): return subprocess.check_output([sys.executable,'-c',code,ledger.path,HASH,account],text=True).strip()
    with ThreadPoolExecutor(max_workers=6) as pool: results=list(pool.map(child,range(12)))
    assert results.count('reserved')==1
    assert AccountLedger(ledger.path).project_view()['project_reserved_micro_usd']>0


def test_selected_account_without_its_key_never_uses_other_key(tmp_path,monkeypatch):
    monkeypatch.setenv('HYDRA_AI_MODE','guarded_meta');monkeypatch.setenv('META_BILLABLE_REQUESTS_ENABLED','true')
    monkeypatch.setenv('HYDRA_META_ACCOUNT',ACCOUNTS[1]);monkeypatch.setenv('HYDRA_META_GEORGIO_API_KEY','synthetic-other-account-key')
    monkeypatch.delenv('HYDRA_META_AMINE_API_KEY',raising=False)
    with pytest.raises(ValueError): create_app(tmp_path/'startup.sqlite3',TOKEN)


def test_real_sender_cannot_use_synthetic_low_cost_ticket(tmp_path,monkeypatch):
    ledger=setup(tmp_path);payload=request_payload(image())
    attempt=ledger.reserve_first(ACCOUNTS[0],HASH,1000)
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    ticket=ledger.mark_dispatched(attempt,digest)
    def forbidden(*args,**kwargs): raise AssertionError("Real network must never be reached")
    monkeypatch.setattr('http.client.HTTPSConnection.request',forbidden)
    with pytest.raises(BudgetDenied): OfficialMetaTransport('synthetic-key').generate(payload,ticket)


def test_account_identity_and_credentials_cannot_be_duplicated(tmp_path):
    ledger=setup(tmp_path)
    from pydantic import ValidationError
    raw=evidence(ACCOUNTS[1]).model_dump();raw['key_sha256']=evidence().key_sha256
    with pytest.raises(BudgetDenied): ledger.attest_account(Evidence.model_validate(raw))
    provider=FakeTransport();provider.credential_fingerprint='0'*64
    with pytest.raises(RecognitionUnavailable): GuardedMetaGateway(ledger,ACCOUNTS[0],provider,FakeNotifier()).analyze(image())
    assert provider.calls==0


@pytest.mark.parametrize('status',[400,401,429,500,503])
def test_provider_http_failures_never_retry_or_assume_zero(tmp_path,status):
    ledger=setup(tmp_path);provider=FakeTransport(ProviderReply(status,{'error':{'message':'secret-provider-error'}}))
    with pytest.raises(RecognitionUnavailable): GuardedMetaGateway(ledger,ACCOUNTS[0],provider,FakeNotifier()).analyze(image())
    assert provider.calls==1 and ledger.project_view()['project_reserved_micro_usd']>0


@pytest.mark.parametrize("account", ACCOUNTS)
def test_crash_after_network_claim_is_durable(tmp_path, account):
    import subprocess,sys
    ledger=setup(tmp_path, account=account)
    code='''from backend.meta_accounts import AccountLedger
import sys,os
l=AccountLedger(sys.argv[1]);a=l.reserve_first(sys.argv[4],sys.argv[2],1000)
t=l.mark_dispatched(a,"0"*64)
l.claim_send(a,t.nonce,"0"*64,1000,sys.argv[3])
os._exit(17)
'''
    result=subprocess.run([sys.executable,'-c',code,ledger.path,HASH,evidence(account).key_sha256,account])
    assert result.returncode==17
    restored=AccountLedger(ledger.path)
    assert restored.project_view()['project_reserved_micro_usd']>0
    with pytest.raises(BudgetDenied): restored.reserve_first(account,HASH,1000)


def test_no_financial_image_or_raw_provider_content_persists(tmp_path):
    ledger=setup(tmp_path); provider=FakeTransport()
    GuardedMetaGateway(ledger,ACCOUNTS[0],provider,FakeNotifier()).analyze(image())
    raw=(tmp_path/'authority.sqlite3').read_bytes()
    assert IMAGE.encode() not in raw and JPEG not in raw and b'Capacity uncertain' not in raw
    with sqlite3.connect(ledger.path) as db:
        columns=[r[1] for r in db.execute('PRAGMA table_info(live_attempts)')]
        assert 'price' in columns and 'dispatched_at' in columns and 'input_bound' in columns
        assert db.execute('SELECT COUNT(*) FROM live_events WHERE at IS NOT NULL').fetchone()[0]>0


def test_alert_sender_uses_fixed_destination_and_validates_receipt(monkeypatch):
    calls=[]
    class Reply:
        status=201
        def read(self,limit): return b'{"id":1234}'
    class Connection:
        def __init__(self,host,timeout): assert host=='api.github.com'
        def request(self,method,path,body,headers):
            assert method=='POST' and path=='/repos/georgiosaliba227/Hydra-Ai/issues/6/comments'
            calls.append(json.loads(body)['body'])
        def getresponse(self): return Reply()
        def close(self): pass
    monkeypatch.setattr('http.client.HTTPSConnection',Connection)
    receipt=GitHubNotifier('synthetic-notification-key').deliver({'recipient':ACCOUNTS[1],'account_id':ACCOUNTS[0]})
    assert receipt=='github-comment:1234' and '@aminealichaouche' in calls[0]


def test_live_normalization_removes_location_metadata_and_comments():
    from backend.meta_images import sanitized_jpeg
    metadata=b'Exif\x00\x00GPS-SYNTHETIC-LOCATION'
    app_segment=b'\xff\xe1'+(len(metadata)+2).to_bytes(2,'big')+metadata
    comment=b'\xff\xfe\x00\x08SECRET'
    source=JPEG[:2]+app_segment+JPEG[2:-2]+comment+JPEG[-2:]
    payload=AnalysisRequest(image_base64=base64.b64encode(source).decode(),photo_consent=True,mode='meta_live',meta_photo_consent=True)
    assert sanitized_jpeg(payload)==JPEG
    sent=request_payload(payload)['input'][0]['content'][1]['image_url']
    assert base64.b64decode(sent.split(',',1)[1])==JPEG


@pytest.mark.parametrize('account', ACCOUNTS)
@pytest.mark.parametrize('baseline,credits,further,allowed,notices', [
    (0,150_000_000,None,True,False),
    (74_999_000,150_000_000,None,True,True),
    (99_999_000,150_000_000,None,False,False),
    (99_999_000,150_000_000,'synthetic-account-specific-approval',True,True),
    (119_996_573,150_000_000,'synthetic-approval',True,True),
    (119_996_574,150_000_000,'synthetic-approval',False,False),
    (150_000_000,150_000_000,'synthetic-approval',False,False),
    (0,3426,None,True,False),
    (0,3425,None,False,False),
])
def test_both_account_boundaries_and_independent_balances(tmp_path,account,baseline,credits,further,allowed,notices):
    ledger=setup(tmp_path,account=account,baseline=baseline,credits=credits,further=further)
    other=next(a for a in ACCOUNTS if a != account)
    ledger.attest_account(evidence(other,baseline=10_000_000))
    provider=FakeTransport(account=account); notifier=FakeNotifier()
    gateway=GuardedMetaGateway(ledger,account,provider,notifier)
    if allowed:
        result=gateway.analyze(image())
        assert ledger.receipt(result.recognition_id)['account_id']==account
    else:
        with pytest.raises(RecognitionUnavailable): gateway.analyze(image())
    rows={row['account_id']:row for row in ledger.project_view()['accounts']}
    assert provider.calls==int(allowed)
    assert rows[other]['gross_micro_usd']==10_000_000
    assert rows[other]['reserved_micro_usd']==0 and not rows[other]['frozen']
    assert rows[account]['gross_micro_usd']==baseline+(338 if allowed else 0)
    assert bool(notifier.delivered)==notices
    if notices:
        assert set(notifier.delivered)==set(ACCOUNTS)
        assert all(n['account_id']==account and n['delivered_at'] for n in ledger.notices())
    # Switching accounts, providers or the API key never creates another permit.
    with pytest.raises(RecognitionUnavailable):
        GuardedMetaGateway(ledger,other,FakeTransport(account=other),notifier).analyze(image())


@pytest.mark.parametrize('account', ACCOUNTS)
@pytest.mark.parametrize('failure', ['timeout','http','missing_usage','malformed','incomplete','refusal'])
def test_both_accounts_failures_reconciliation_and_restart(tmp_path,account,failure):
    ledger=setup(tmp_path,account=account)
    responses={
        'timeout':reply(), 'http':ProviderReply(429,{}),
        'missing_usage':reply(usage=None), 'malformed':reply(output=[]),
        'incomplete':reply(status='incomplete'),
        'refusal':reply(output=[{'type':'message','role':'assistant','status':'completed',
                                'content':[{'type':'refusal','refusal':'synthetic-only'}]}]),
    }
    provider=FakeTransport(responses[failure], fault=TimeoutError() if failure=='timeout' else None,account=account)
    with pytest.raises(RecognitionUnavailable):
        GuardedMetaGateway(ledger,account,provider,FakeNotifier()).analyze(image())
    restored=AccountLedger(ledger.path)
    row=restored.project_view()['accounts'][0]
    assert row['frozen'] and row['account_id']==account
    uncertain=failure in ('timeout','http','missing_usage')
    assert row['reserved_micro_usd']==(3426 if uncertain else 0)
    assert row['gross_micro_usd']==(0 if uncertain else 338)
    restored.record_reconciliation_reference(account,'UNVERIFIED-NO-REFUND')
    with pytest.raises(RecognitionUnavailable):
        GuardedMetaGateway(restored,account,provider,FakeNotifier()).analyze(image())
    assert provider.calls==1  # No retry, including HTTP 429 or after restart.


def test_reviewed_cost_policy_and_canonical_request():
    from backend.meta_policy import MODEL_CONTEXT, OUTPUT_LIMIT, MAX_INPUT_TOKENS
    payload=request_payload(image())
    assert MODEL_CONTEXT==1_048_576 and OUTPUT_LIMIT==512
    assert MAX_INPUT_TOKENS+OUTPUT_LIMIT==MODEL_CONTEXT
    assert OfficialMetaTransport('synthetic-key').input_bound(payload)==MAX_INPUT_TOKENS
    assert price().cost(MAX_INPUT_TOKENS,OUTPUT_LIMIT)==1_312_256
    # No cached discount and no separate unbounded reasoning budget.
    assert payload['reasoning']=={'effort':'minimal'}
    assert payload['max_output_tokens']==OUTPUT_LIMIT
    assert payload['text']['format']['type']=='json_schema'
    assert payload['text']['format']['strict'] is True
    schema=payload['text']['format']['schema']
    assert '"title":' not in json.dumps(schema)
    candidate=schema['$defs']['ProviderCandidate']
    assert candidate['additionalProperties'] is False
    assert set(candidate['required'])=={'category','brand','product','container_ml','confidence','uncertainty_reasons'}
    assert candidate['properties']['container_ml']['anyOf'][0]['maximum']==5000
    assert set(payload)=={'model','store','stream','background','max_output_tokens','reasoning','text','input'}
    # A verified full-input bound would need to be <=198,259 tokens to fit.
    assert price().cost(198_259,OUTPUT_LIMIT)==250_000
    assert price().cost(198_260,OUTPUT_LIMIT)==250_001


@pytest.mark.parametrize('account', ACCOUNTS)
def test_configured_http_route_cannot_bypass_real_transport_bound(tmp_path,monkeypatch,account):
    ledger=setup(tmp_path,account=account)
    monkeypatch.setenv('HYDRA_AI_MODE','guarded_meta')
    monkeypatch.setenv('META_BILLABLE_REQUESTS_ENABLED','true')
    monkeypatch.setenv('HYDRA_META_ACCOUNT',account)
    key='synthetic-key' if account==ACCOUNTS[0] else 'synthetic-amine-key'
    variable='HYDRA_META_GEORGIO_API_KEY' if account==ACCOUNTS[0] else 'HYDRA_META_AMINE_API_KEY'
    monkeypatch.setenv(variable,key)
    monkeypatch.setenv('HYDRA_GITHUB_NOTIFICATION_TOKEN','synthetic-only')
    def forbidden(*args,**kwargs): pytest.fail('No provider or notification network allowed')
    monkeypatch.setattr('http.client.HTTPSConnection.request',forbidden)
    with TestClient(create_app(ledger.path,TOKEN)) as client:
        response=client.post('/v1/recognitions',json=image().model_dump(),headers=AUTH)
        assert response.status_code==503 and response.json()['retryable'] is False
    with sqlite3.connect(ledger.path) as db:
        assert db.execute('SELECT COUNT(*) FROM live_attempts').fetchone()[0]==0
        assert db.execute('SELECT spent FROM live_permit').fetchone()[0]==0


@pytest.mark.parametrize('account', ACCOUNTS)
@pytest.mark.parametrize('delivery_fails', [False,True])
def test_unexpected_billed_threshold_crossing_notifies_and_stays_frozen(tmp_path,account,delivery_fails):
    ledger=setup(tmp_path,account=account)
    # Fault injection: impossible under the contract, but never discard actual
    # reported charges or omit a threshold event because the reservation was small.
    usage={'input_tokens':80_000_000,'output_tokens':0,'total_tokens':80_000_000,
           'input_tokens_details':{'cached_tokens':0}}
    provider=FakeTransport(reply(usage=usage),account=account)
    notifier=FakeNotifier(fail=delivery_fails)
    with pytest.raises(RecognitionUnavailable):
        GuardedMetaGateway(ledger,account,provider,notifier).analyze(image())
    row=ledger.project_view()['accounts'][0]
    assert row['gross_micro_usd']==100_000_000 and row['frozen']
    notices=ledger.notices()
    assert len(notices)==2 and {n['recipient'] for n in notices}==set(ACCOUNTS)
    assert all(bool(n['delivered_at']) is not delivery_fails for n in notices)
    with pytest.raises(RecognitionUnavailable):
        GuardedMetaGateway(AccountLedger(ledger.path),account,provider,notifier).analyze(image())
    assert provider.calls==1
