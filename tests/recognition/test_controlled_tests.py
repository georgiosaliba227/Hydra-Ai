"""Two proposed test paths; all credentials/evidence/transports are synthetic."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import json

import pytest
from pydantic import ValidationError
from backend.meta_accounts import AccountLedger, ControlledPermit, InvoiceFinality, ACCOUNTS
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


def finality(ledger, attempt_id):
    with ledger.transaction() as db:
        account, provider_id, actual = db.execute(
            'SELECT account_id,provider_id,actual FROM live_attempts WHERE id=?',
            (attempt_id,),
        ).fetchone()
    return InvoiceFinality(attempt_id=attempt_id, account_id=account,
        provider_id=provider_id, final_gross_micro_usd=actual,
        finalized_at=datetime.now(timezone.utc), provider_finality_verified=True,
        provider_evidence_reference='synthetic-provider-invoice-only',
        georgio_review_reference='synthetic-georgio-review',
        amine_review_reference='synthetic-amine-review')


def hydration_reply():
    return reply(output=[{'type':'message','role':'assistant','status':'completed','content':[
        {'type':'output_text','text':json.dumps({'signals':['composition_missing','activity_context']})}]}])


def test_two_accounts_one_request_each(tmp_path):
    ledger = setup(tmp_path)
    camera = FakeTransport()
    result = GuardedMetaGateway(ledger, ACCOUNTS[0], camera, FakeNotifier()).analyze(image())
    ledger.record_invoice_finality(finality(ledger, result.recognition_id))
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


def camera_only_ledger(tmp_path):
    ledger = AccountLedger(tmp_path/'authority.sqlite3')
    ledger.initialize_accounts()
    ledger.record_price(price())
    ledger.attest_account(evidence(ACCOUNTS[0]))
    ledger.approve_controlled_test(permit(ACCOUNTS[0], HASH))
    return ledger


def test_camera_first_without_other_account_evidence_or_permit(tmp_path):
    ledger = camera_only_ledger(tmp_path)
    provider = FakeTransport()
    result = GuardedMetaGateway(ledger, ACCOUNTS[0], provider, FakeNotifier()).analyze(image())
    assert provider.calls == 1
    other = FakeTransport(response=hydration_reply(), account=ACCOUNTS[1])
    with pytest.raises(RecognitionUnavailable):
        HydrationIntelligence(ledger, ACCOUNTS[1], other, FakeNotifier()).explain(context())
    assert other.calls == 0
    # Later independent approval needs finality and never resets the camera permit.
    ledger.record_invoice_finality(finality(ledger, result.recognition_id))
    ledger.attest_account(evidence(ACCOUNTS[1]))
    ledger.approve_controlled_test(permit(ACCOUNTS[1], context_fingerprint(context())))
    with pytest.raises(RecognitionUnavailable):
        GuardedMetaGateway(ledger, ACCOUNTS[0], provider, FakeNotifier()).analyze(image())
    assert provider.calls == 1
    HydrationIntelligence(ledger, ACCOUNTS[1], other, FakeNotifier()).explain(context())
    assert other.calls == 1


def test_later_approval_cannot_bypass_unresolved_first_charge(tmp_path):
    ledger = camera_only_ledger(tmp_path)
    with pytest.raises(RecognitionUnavailable):
        GuardedMetaGateway(ledger, ACCOUNTS[0], FakeTransport(fault=TimeoutError()), FakeNotifier()).analyze(image())
    ledger.attest_account(evidence(ACCOUNTS[1]))
    with pytest.raises(BudgetDenied):
        ledger.approve_controlled_test(permit(ACCOUNTS[1], context_fingerprint(context())))
    assert AccountLedger(ledger.path).project_view()['project_reserved_micro_usd'] > 0


def test_later_approval_cannot_bypass_frozen_settled_account(tmp_path):
    ledger = camera_only_ledger(tmp_path)
    GuardedMetaGateway(ledger, ACCOUNTS[0], FakeTransport(), FakeNotifier()).analyze(image())
    with ledger.transaction() as db:
        db.execute('UPDATE live_accounts SET frozen=1 WHERE account_id=?', (ACCOUNTS[0],))
    ledger.attest_account(evidence(ACCOUNTS[1]))
    with pytest.raises(BudgetDenied):
        ledger.approve_controlled_test(permit(ACCOUNTS[1], context_fingerprint(context())))


def test_controlled_approval_preserves_legacy_singleton(tmp_path):
    from backend.meta_accounts import FirstPermit
    ledger = AccountLedger(tmp_path/'authority.sqlite3')
    ledger.initialize_accounts()
    legacy = permit(ACCOUNTS[0], HASH).model_dump(exclude={'policy_version', 'purpose', 'maximum_micro_usd'})
    ledger.approve_first_test(FirstPermit(**legacy))
    with pytest.raises(BudgetDenied):
        ledger.approve_controlled_test(permit(ACCOUNTS[0], HASH))
    with ledger.transaction() as db:
        assert db.execute('SELECT COUNT(*) FROM live_permit').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM controlled_permits').fetchone()[0] == 0


@pytest.mark.parametrize('failure', ['over_bound', 'malformed_output'])
def test_preapproved_other_account_cannot_bypass_settled_frozen_account(tmp_path, failure):
    ledger = setup(tmp_path)
    changes = {'output': []}
    if failure == 'over_bound':
        changes = {'usage': {'input_tokens': 10000, 'output_tokens': 513,
                            'total_tokens': 10513, 'input_tokens_details': {'cached_tokens': 0}}}
    with pytest.raises(RecognitionUnavailable):
        GuardedMetaGateway(ledger, ACCOUNTS[0], FakeTransport(reply(**changes)), FakeNotifier()).analyze(image())
    restored = AccountLedger(ledger.path)
    assert restored.project_view()['project_reserved_micro_usd'] == 0
    other = FakeTransport(response=hydration_reply(), account=ACCOUNTS[1])
    with pytest.raises(RecognitionUnavailable):
        HydrationIntelligence(restored, ACCOUNTS[1], other, FakeNotifier()).explain(context())
    assert other.calls == 0
    with restored.transaction() as db:
        assert db.execute('SELECT spent FROM controlled_permits WHERE account_id=?', (ACCOUNTS[1],)).fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM live_attempts').fetchone()[0] == 1


@pytest.mark.parametrize('stage', ['reserved', 'dispatched'])
def test_other_account_freeze_between_admission_and_send_blocks(tmp_path, stage):
    ledger = setup(tmp_path)
    digest = context_fingerprint(context())
    attempt = ledger.reserve_first(ACCOUNTS[1], digest, 1000)
    ticket = ledger.mark_dispatched(attempt, digest) if stage == 'dispatched' else None
    # Separate connection/thread commits a hold after this request's admission.
    # Dispatch and send must recheck, rather than trust stale preflight state.
    def freeze_other():
        with AccountLedger(ledger.path).transaction() as db:
            db.execute('UPDATE live_accounts SET frozen=1 WHERE account_id=?', (ACCOUNTS[0],))
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(freeze_other).result()
    restored = AccountLedger(ledger.path)
    with pytest.raises(BudgetDenied):
        if ticket:
            restored.claim_send(attempt, ticket.nonce, digest, 1000, evidence(ACCOUNTS[1]).key_sha256)
        else:
            restored.mark_dispatched(attempt, digest)
    with restored.transaction() as db:
        assert db.execute('SELECT state FROM live_attempts WHERE id=?', (attempt,)).fetchone()[0] == stage
    assert restored.project_view()['project_reserved_micro_usd'] > 0


def test_usage_settlement_does_not_admit_second_preapproved_account(tmp_path):
    ledger = setup(tmp_path)
    result = GuardedMetaGateway(ledger, ACCOUNTS[0], FakeTransport(), FakeNotifier()).analyze(image())
    restored = AccountLedger(ledger.path)
    provider = FakeTransport(response=hydration_reply(), account=ACCOUNTS[1])
    service = HydrationIntelligence(restored, ACCOUNTS[1], provider, FakeNotifier())
    with pytest.raises(RecognitionUnavailable): service.explain(context())
    assert provider.calls == 0
    restored.record_reconciliation_reference(ACCOUNTS[0], 'unverified-generic-reference')
    with pytest.raises(RecognitionUnavailable): service.explain(context())
    assert provider.calls == 0
    restored.record_invoice_finality(finality(restored, result.recognition_id))
    # Multiple connections compete only after the independent finality import.
    def run(_):
        try:
            HydrationIntelligence(AccountLedger(ledger.path), ACCOUNTS[1], provider, FakeNotifier()).explain(context())
            return True
        except RecognitionUnavailable:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(run, range(16))) == 1
    assert provider.calls == 1


def test_later_approval_requires_provider_invoice_finality(tmp_path):
    ledger = camera_only_ledger(tmp_path)
    result = GuardedMetaGateway(ledger, ACCOUNTS[0], FakeTransport(), FakeNotifier()).analyze(image())
    ledger.attest_account(evidence(ACCOUNTS[1]))
    with pytest.raises(BudgetDenied):
        ledger.approve_controlled_test(permit(ACCOUNTS[1], context_fingerprint(context())))
    ledger.record_invoice_finality(finality(ledger, result.recognition_id))
    ledger.approve_controlled_test(permit(ACCOUNTS[1], context_fingerprint(context())))


@pytest.mark.parametrize('change', [
    {'attempt_id': 'invalid'}, {'account_id': 'unknown'}, {'provider_id': 'not-provider-response'},
    {'final_gross_micro_usd': True}, {'final_gross_micro_usd': -1},
    {'provider_finality_verified': False}, {'provider_finality_verified': 1},
    {'finalized_at': datetime(2000, 1, 1)},
    {'finalized_at': datetime.now(timezone.utc) + timedelta(days=1)},
    {'georgio_review_reference': ''}, {'amine_review_reference': '  '},
    {'provider_evidence_reference': '\n'}, {'unrecognized': 'forbidden'},
])
def test_finality_rejects_invalid_evidence(tmp_path, change):
    ledger = setup(tmp_path)
    result = GuardedMetaGateway(ledger, ACCOUNTS[0], FakeTransport(), FakeNotifier()).analyze(image())
    raw = finality(ledger, result.recognition_id).model_dump()
    with pytest.raises(ValidationError): InvoiceFinality.model_validate(raw | change)
    with ledger.transaction() as db:
        assert db.execute('SELECT COUNT(*) FROM live_finalities').fetchone()[0] == 0


@pytest.mark.parametrize('change', [
    {'attempt_id': str(uuid4())}, {'account_id': ACCOUNTS[1]},
    {'provider_id': 'resp_other'}, {'final_gross_micro_usd': 0},
    {'finalized_at': datetime(2000, 1, 1, tzinfo=timezone.utc)},
])
def test_finality_cannot_replace_cost_identity_or_precede_send(tmp_path, change):
    ledger = setup(tmp_path)
    result = GuardedMetaGateway(ledger, ACCOUNTS[0], FakeTransport(), FakeNotifier()).analyze(image())
    raw = finality(ledger, result.recognition_id).model_dump()
    before = ledger.project_view()
    with pytest.raises(BudgetDenied): ledger.record_invoice_finality(InvoiceFinality.model_validate(raw | change))
    assert ledger.project_view() == before
    with ledger.transaction() as db:
        assert db.execute('SELECT COUNT(*) FROM live_finalities').fetchone()[0] == 0


def test_finality_is_immutable_and_identical_import_is_idempotent(tmp_path):
    ledger = setup(tmp_path)
    result = GuardedMetaGateway(ledger, ACCOUNTS[0], FakeTransport(), FakeNotifier()).analyze(image())
    record = finality(ledger, result.recognition_id)
    ledger.record_invoice_finality(record)
    AccountLedger(ledger.path).record_invoice_finality(record)
    with pytest.raises(BudgetDenied):
        ledger.record_invoice_finality(record.model_copy(update={'provider_evidence_reference': 'different'}))
    with ledger.transaction() as db:
        assert db.execute('SELECT COUNT(*) FROM live_finalities').fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM live_events WHERE kind='invoice_finality_attested'").fetchone()[0] == 1


@pytest.mark.parametrize('failure', ['timeout', 'over_bound', 'bad_output'])
def test_finality_cannot_release_or_unfreeze_failed_attempts(tmp_path, failure):
    ledger = setup(tmp_path)
    response = reply(output=[]) if failure == 'bad_output' else reply()
    if failure == 'over_bound':
        response = reply(usage={'input_tokens':10000, 'output_tokens':513, 'total_tokens':10513,
                                'input_tokens_details':{'cached_tokens':0}})
    provider = FakeTransport(response, fault=TimeoutError() if failure == 'timeout' else None)
    with pytest.raises(RecognitionUnavailable):
        GuardedMetaGateway(ledger, ACCOUNTS[0], provider, FakeNotifier()).analyze(image())
    with ledger.transaction() as db:
        attempt_id, actual = db.execute('SELECT id,actual FROM live_attempts').fetchone()
    record = InvoiceFinality(attempt_id=attempt_id, account_id=ACCOUNTS[0], provider_id='resp_testonly',
        final_gross_micro_usd=actual or 0, finalized_at=datetime.now(timezone.utc),
        provider_evidence_reference='synthetic-only', georgio_review_reference='synthetic-only',
        amine_review_reference='synthetic-only', provider_finality_verified=True)
    before = ledger.project_view()
    with pytest.raises(BudgetDenied): ledger.record_invoice_finality(record)
    assert ledger.project_view() == before


@pytest.mark.parametrize('stage', ['approval', 'reservation', 'dispatch', 'send'])
def test_missing_finality_schema_blocks_without_automatic_migration(tmp_path, stage):
    ledger = setup(tmp_path)
    attempt = ticket = None
    if stage in ('dispatch', 'send'):
        attempt = ledger.reserve_first(ACCOUNTS[0], HASH, 1000)
    if stage == 'send': ticket = ledger.mark_dispatched(attempt, HASH)
    with ledger.transaction() as db:
        db.execute('DROP TABLE live_finalities')  # Synthetic prior schema only.
    restored = AccountLedger(ledger.path)
    with pytest.raises(BudgetDenied):
        if stage == 'approval': restored.approve_controlled_test(permit(ACCOUNTS[0], HASH))
        elif stage == 'reservation': restored.reserve_first(ACCOUNTS[0], HASH, 1000)
        elif stage == 'dispatch': restored.mark_dispatched(attempt, HASH)
        else: restored.claim_send(attempt, ticket.nonce, HASH, 1000, evidence().key_sha256)
    with restored.transaction() as db:
        assert db.execute("SELECT 1 FROM sqlite_master WHERE name='live_finalities'").fetchone() is None


def test_finality_cli_import_is_private_local_and_preserves_existing_ledger(tmp_path):
    import subprocess
    import sys
    ledger = setup(tmp_path)
    result = GuardedMetaGateway(ledger, ACCOUNTS[0], FakeTransport(), FakeNotifier()).analyze(image())
    record = finality(ledger, result.recognition_id)
    offset_time = record.finalized_at.astimezone(timezone(timedelta(hours=-4)))
    record = InvoiceFinality.model_validate(record.model_dump() | {'finalized_at': offset_time})
    assert record.finalized_at.utcoffset() == timedelta(0)
    file = tmp_path / 'synthetic-finality.json'
    file.write_text(record.model_dump_json())
    file.chmod(0o600)
    command = [sys.executable, '-m', 'scripts.meta_budget_admin', '--database', ledger.path,
               'record-invoice-finality', '--evidence-file', str(file)]
    for _ in range(2):
        response = subprocess.run(command, capture_output=True, text=True)
        assert response.returncode == 0, response.stderr
        assert response.stdout == ''
    # Explicit schema initialization is additive and does not reset permits/costs.
    before = ledger.project_view()
    ledger.initialize_accounts()
    assert ledger.project_view() == before
    with ledger.transaction() as db:
        assert db.execute('SELECT COUNT(*) FROM live_finalities').fetchone()[0] == 1
        assert db.execute('SELECT spent FROM controlled_permits WHERE account_id=?', (ACCOUNTS[0],)).fetchone()[0] == 1


@pytest.mark.parametrize('damage', ['invalid_json', 'wrong_cost'])
def test_corrupted_finality_record_cannot_authorize_another_account(tmp_path, damage):
    ledger = setup(tmp_path)
    result = GuardedMetaGateway(ledger, ACCOUNTS[0], FakeTransport(), FakeNotifier()).analyze(image())
    record = finality(ledger, result.recognition_id)
    ledger.record_invoice_finality(record)
    raw = '{}' if damage == 'invalid_json' else record.model_copy(update={'final_gross_micro_usd': 0}).model_dump_json()
    with ledger.transaction() as db:
        db.execute('UPDATE live_finalities SET evidence=?', (raw,))
    provider = FakeTransport(response=hydration_reply(), account=ACCOUNTS[1])
    with pytest.raises(RecognitionUnavailable):
        HydrationIntelligence(AccountLedger(ledger.path), ACCOUNTS[1], provider, FakeNotifier()).explain(context())
    assert provider.calls == 0
