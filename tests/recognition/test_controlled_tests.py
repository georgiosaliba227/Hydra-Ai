"""Two proposed test paths; all credentials/evidence/transports are synthetic."""
from concurrent.futures import ThreadPoolExecutor
import json

import pytest
from pydantic import ValidationError
from backend.meta_accounts import AccountLedger, ControlledPermit, ACCOUNTS
from backend.meta_budget import BudgetDenied
from backend.meta_gateway import GuardedMetaGateway
from backend.meta_provider import OfficialMetaTransport
from backend.hydration_intelligence import (SyntheticContext, HydrationIntelligence, HydrationMetaTransport,
    hydration_payload, context_fingerprint, parse_interpretation)
from backend.recognition import RecognitionUnavailable
from test_guarded_meta import evidence, price, future, HASH, image, FakeTransport, FakeNotifier, reply


def context(**changes):
    return SyntheticContext(synthetic=True, disclosure_consent=True, beverage_total_ml=750.0, **changes)


def permit(account, digest):
    return ControlledPermit(account_id=account, image_sha256=digest, price_version='fixture-v1',
        developer_approvals=ACCOUNTS, spending_authority_reference='synthetic-only',
        account_owner_authorization_reference='synthetic-owner', image_owner_consent_reference='synthetic-input-consent',
        valid_until=future(), maximum_micro_usd=2_000_000, policy_version='dual-test-v1',
        purpose='camera' if account == ACCOUNTS[0] else 'hydration')


def setup(tmp_path):
    ledger = AccountLedger(tmp_path/'authority.sqlite3'); ledger.initialize_accounts(); ledger.record_price(price())
    for account, digest in zip(ACCOUNTS, (HASH, context_fingerprint(context()))):
        ledger.attest_account(evidence(account)); ledger.approve_controlled_test(permit(account, digest))
    return ledger


def hydration_reply():
    return reply(output=[{'type':'message','role':'assistant','status':'completed','content':[
        {'type':'output_text','text':json.dumps({'signals':['composition_missing','activity_context']})}]}])


def test_two_accounts_one_request_each(tmp_path):
    ledger = setup(tmp_path)
    camera = FakeTransport()
    GuardedMetaGateway(ledger, ACCOUNTS[0], camera, FakeNotifier()).analyze(image())
    hydration = FakeTransport(response=hydration_reply(), account=ACCOUNTS[1])
    service = HydrationIntelligence(ledger, ACCOUNTS[1], hydration, FakeNotifier())
    result = service.explain(context())
    assert result['prediction'] is None and result['context']['beverage_total_ml'] == 750.0
    assert 'estimated_water_ml' in result['missing_information']
    with pytest.raises(RecognitionUnavailable): service.explain(context())
    assert camera.calls == hydration.calls == 1


def test_cross_account_unresolved_attempt_blocks(tmp_path):
    ledger = setup(tmp_path)
    with pytest.raises(RecognitionUnavailable):
        GuardedMetaGateway(ledger,ACCOUNTS[0],FakeTransport(fault=TimeoutError()),FakeNotifier()).analyze(image())
    provider = FakeTransport(response=hydration_reply(), account=ACCOUNTS[1])
    with pytest.raises(RecognitionUnavailable): HydrationIntelligence(ledger,ACCOUNTS[1],provider,FakeNotifier()).explain(context())
    assert provider.calls == 0
    assert AccountLedger(ledger.path).project_view()['project_reserved_micro_usd'] > 0


def test_concurrent_hydration_one_send(tmp_path):
    ledger = setup(tmp_path); provider = FakeTransport(response=hydration_reply(),account=ACCOUNTS[1])
    def run(_):
        try:
            HydrationIntelligence(AccountLedger(ledger.path),ACCOUNTS[1],provider,FakeNotifier()).explain(context()); return True
        except RecognitionUnavailable: return False
    with ThreadPoolExecutor(max_workers=8) as pool: assert sum(pool.map(run,range(16))) == 1
    assert provider.calls == 1


def test_changed_context_and_wrong_feature_block(tmp_path):
    ledger = setup(tmp_path); provider = FakeTransport(account=ACCOUNTS[1])
    with pytest.raises(RecognitionUnavailable): HydrationIntelligence(ledger,ACCOUNTS[1],provider,FakeNotifier()).explain(context(workout_minutes=20))
    with pytest.raises(RecognitionUnavailable): GuardedMetaGateway(ledger,ACCOUNTS[1],provider,FakeNotifier()).analyze(image())
    assert provider.calls == 0


def test_full_bound_reserved_at_sender_and_gateway(tmp_path):
    ledger=setup(tmp_path)
    transport=HydrationMetaTransport('synthetic-amine-key')
    payload=hydration_payload(context()); transport.validate_payload(payload)
    bound=transport.input_bound(payload)
    assert ledger.quote(ACCOUNTS[1],bound)[1] == 1_312_256
    attempt=ledger.reserve_first(ACCOUNTS[1],context_fingerprint(context()),1000)
    ticket=ledger.mark_dispatched(attempt,context_fingerprint(context()))
    with pytest.raises(BudgetDenied): ticket.claim(payload,input_bound=bound,credential_fingerprint=transport.credential_fingerprint)
    payload['tools'] = []
    with pytest.raises(ValueError): transport.validate_payload(payload)


@pytest.mark.parametrize('changes',[{'synthetic':False},{'disclosure_consent':False},{'beverage_total_ml':float('nan')},{'heart_rate':90},{'creatine_adjustment_ml':500}])
def test_invalid_or_private_context_rejected(changes):
    with pytest.raises(ValidationError): SyntheticContext.model_validate(dict(synthetic=True,disclosure_consent=True,beverage_total_ml=750.0)|changes)


def test_untrusted_numbers_or_diagnosis_rejected():
    for value in ({'signals':['dehydrated']},{'signals':['review_intake'],'target_ml':2000}):
        response=hydration_reply(); response.body['output'][0]['content'][0]['text']=json.dumps(value)
        with pytest.raises(RecognitionUnavailable): parse_interpretation(response)


def test_camera_label_text_is_unverified_and_not_nutrition():
    from backend.meta_provider import parse_recognition
    response = reply()
    candidate = json.loads(response.body['output'][0]['content'][0]['text'])
    candidate['candidates'][0]['visible_label_text'] = 'Volume 300 mL; sodium 10 mg'
    response.body['output'][0]['content'][0]['text'] = json.dumps(candidate)
    result = parse_recognition(response, 'synthetic-attempt')
    assert result.candidates[0].visible_label_text == 'Volume 300 mL; sodium 10 mg'
    assert result.candidates[0].product_id is None
    assert 'nutrition' not in result.candidates[0].model_dump()


def test_engine_values_come_from_synthetic_logs():
    from datetime import date
    from backend.hydration_intelligence import context_from_engine
    value = context_from_engine((), date(2026,10,27), 'America/New_York', synthetic=True, disclosure_consent=True)
    assert value.beverage_total_ml == 0 and value.estimated_water_ml == 0
    with pytest.raises(ValidationError):
        context_from_engine((), date(2026,10,27), 'America/New_York')


def test_over_two_dollars_and_wrong_owner_rejected(tmp_path):
    with pytest.raises(ValidationError):
        ControlledPermit.model_validate(
            permit(ACCOUNTS[0], HASH).model_dump() | {'maximum_micro_usd':2_000_001})
    ledger=AccountLedger(tmp_path/'authority.sqlite3'); ledger.initialize_accounts()
    wrong = permit(ACCOUNTS[0], HASH).model_copy(update={'purpose':'hydration'})
    with pytest.raises(BudgetDenied): ledger.approve_controlled_test(wrong)


@pytest.mark.parametrize('account', ACCOUNTS)
def test_official_transport_mocked_http_once(tmp_path, monkeypatch, account):
    ledger = setup(tmp_path)
    response = reply() if account == ACCOUNTS[0] else hydration_reply()
    calls = []
    class Connection:
        def __init__(self, host, timeout): assert host == 'api.meta.ai' and timeout == 20
        def request(self, method, path, body, headers):
            assert method == 'POST' and path == '/v1/responses'
            calls.append(json.loads(body))
        def getresponse(self): return self
        status = 200
        def read(self, limit): return json.dumps(response.body).encode()
        def close(self): pass
    monkeypatch.setattr('http.client.HTTPSConnection', Connection)
    if account == ACCOUNTS[0]:
        gateway = GuardedMetaGateway(ledger,account,OfficialMetaTransport('synthetic-key'),FakeNotifier())
        gateway.analyze(image())
        with pytest.raises(RecognitionUnavailable): gateway.analyze(image())
    else:
        gateway = HydrationIntelligence(ledger,account,HydrationMetaTransport('synthetic-amine-key'),FakeNotifier())
        gateway.explain(context())
        with pytest.raises(RecognitionUnavailable): gateway.explain(context())
    assert len(calls) == 1
    assert ledger.project_view()['project_reserved_micro_usd'] == 0


@pytest.mark.parametrize('water', [750.01, 50000.0])
def test_context_water_cannot_exceed_beverage_volume(water):
    with pytest.raises(ValidationError): context(estimated_water_ml=water)


def test_context_water_boundary_and_unknown():
    assert context(estimated_water_ml=750.0).estimated_water_ml == 750.0
    assert context().estimated_water_ml is None
