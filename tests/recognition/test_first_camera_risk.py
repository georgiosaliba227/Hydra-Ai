"""Synthetic-only tests; outbound sockets are disabled."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import socket
import pytest
from pydantic import ValidationError
import backend.meta_accounts as accounts
from backend.meta_accounts import AccountLedger, RiskEvidence, RiskPermit, InvoiceFinality, ACCOUNTS, RISK_POLICY
from backend.meta_budget import BudgetDenied
from backend.meta_gateway import GuardedMetaGateway
from backend.meta_observations import read_observation
from backend.meta_policy import MAX_INPUT_TOKENS
from backend.meta_provider import request_payload
from backend.recognition import RecognitionUnavailable
from test_guarded_meta import evidence, price, HASH, image, FakeTransport, FakeNotifier, reply
from test_controlled_tests import permit as controlled_permit


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Risk-policy tests must remain nonbillable")
    monkeypatch.setattr(socket.socket, 'connect', blocked)


def risk_evidence(**changes):
    instant = datetime.now(timezone.utc)
    raw = evidence().model_dump() | dict(
        policy_version=RISK_POLICY, all_charge_categories_verified=False,
        extra_charge_bound_micro_usd=None, known_pending_micro_usd=0,
        billing_observed_at=instant, valid_until=instant + timedelta(minutes=10),
        account_key_binding_verified=True, pending_usage_verified=True,
        no_outstanding_requests_verified=True, automatic_topups_disabled_verified=True,
        notification_delivery_reference='synthetic-two-developer-delivery',
        credit_terms_reviewed=True, free_credit_disclosure_consent_reference='synthetic-consent')
    raw.pop('hackathon_terms_verified')
    return RiskEvidence.model_validate(raw | changes)


def risk_permit(account_evidence, **changes):
    raw = controlled_permit(ACCOUNTS[0], HASH).model_dump() | dict(
        policy_version=RISK_POLICY, residual_provider_charge_risk_accepted=True,
        risk_authorization_reference='synthetic-owner-acceptance',
        account_evidence_sha256=hashlib.sha256(account_evidence.model_dump_json().encode()).hexdigest())
    return RiskPermit.model_validate(raw | changes)


@pytest.fixture
def setup_risk(tmp_path, monkeypatch):
    # Substitute a tiny owned fixture only within tests; production pins the
    # user's illustration. Exercise the actual gateway hashing/consent path.
    monkeypatch.setattr(accounts, 'APPROVED_CAMERA_SHA256', HASH)
    def setup(**changes):
        directory = tmp_path / str(len(list(tmp_path.iterdir())))
        directory.mkdir()
        ledger = AccountLedger(directory / 'synthetic.sqlite3')
        ledger.initialize_accounts()
        ev = risk_evidence(**changes)
        ledger.attest_account(ev)
        ledger.record_price(price())
        ledger.approve_risk_test(risk_permit(ev))
        return ledger, ev
    return setup


class FullBoundTransport(FakeTransport):
    def input_bound(self, payload):
        return MAX_INPUT_TOKENS

    def generate(self, payload, ticket):
        ticket.claim(payload, input_bound=MAX_INPUT_TOKENS, credential_fingerprint=self.credential_fingerprint)
        self.calls += 1
        assert payload == request_payload(image())
        if self.fault:
            raise self.fault
        return self.response


def gateway(ledger, provider=None, notifier=None):
    return GuardedMetaGateway(ledger, ACCOUNTS[0], provider or FullBoundTransport(), notifier or FakeNotifier())


def test_production_exception_rejects_other_image():
    assert accounts.APPROVED_CAMERA_SHA256 == 'c7bbab98d7ee9a1c41e4f6cb5a2dc62b336a81f717893995ce8cc7cf9a33edd8'
    with pytest.raises(ValidationError):
        risk_permit(risk_evidence())


@pytest.mark.parametrize('change', [
    {'all_charge_categories_verified': True}, {'all_charge_categories_verified': 0},
    {'extra_charge_bound_micro_usd': 0}, {'known_pending_micro_usd': 1},
    {'known_pending_micro_usd': False}, {'known_pending_micro_usd': None},
    {'pending_usage_verified': False}, {'account_key_binding_verified': False},
    {'no_outstanding_requests_verified': False}, {'automatic_topups_disabled_verified': False},
    {'billing_observed_at': datetime.now(timezone.utc) - timedelta(hours=1)},
    {'billing_observed_at': datetime.now(timezone.utc) + timedelta(hours=1)},
    {'notification_delivery_reference': ' '}, {'account_id': ACCOUNTS[1]},
])
def test_unknown_stale_pending_or_wrong_account_evidence_rejected(change):
    with pytest.raises(ValidationError):
        risk_evidence(**change)


def test_token_reservation_and_unknown_total_stay_distinct(setup_risk):
    ledger, _ = setup_risk()
    provider = FullBoundTransport()
    result = gateway(ledger, provider).analyze(image())
    report = read_observation(ledger.path, result.recognition_id)
    assert result.candidates[0].category == 'tea'
    assert report['reserved_micro_usd'] == 1_312_256
    assert report['usage_cost_micro_usd'] == 338
    assert report['final_gross_micro_usd'] is None
    assert report['billing_status'] == 'usage_recorded_invoice_pending'
    assert report['outcome'] == 'success'
    assert ledger.project_view()['accounts'][0]['frozen']
    with pytest.raises(RecognitionUnavailable):
        gateway(ledger, provider).analyze(image())
    assert provider.calls == 1

def test_operator_runner_uses_official_sender_once_and_restores_mock(setup_risk, monkeypatch):
    import json
    import os
    from pathlib import Path
    from scripts.meta_camera_once import run_once
    from backend.meta_camera_preparation import prepare_camera
    from test_guarded_meta import JPEG, TOKEN
    ledger, _ = setup_risk()
    root = Path(ledger.path).parent.resolve()
    root.chmod(0o700)
    env = root / 'backend.env'
    env.write_text(f"HYDRA_AI_MODE=mock\nMETA_BILLABLE_REQUESTS_ENABLED=false\nHYDRA_META_ACCOUNT={ACCOUNTS[0]}\nHYDRA_DATABASE_PATH={root / 'synthetic.sqlite3'}\nHYDRA_META_GEORGIO_API_KEY=synthetic-key\nHYDRA_GITHUB_NOTIFICATION_TOKEN=synthetic-token\nHYDRA_API_TOKEN={TOKEN}\n")
    env.chmod(0o600)
    photo = root / 'synthetic.jpg'
    photo.write_bytes(JPEG)
    photo.chmod(0o600)
    before = Path(ledger.path).read_bytes()
    plan = prepare_camera(env, root / 'synthetic.sqlite3', photo)
    assert plan['policy']['version'] == RISK_POLICY
    assert plan['reservation']['locally_attested_total_bound_micro_usd'] is None
    assert plan['gates']['active_cost_ceiling']['status'] == 'locally_satisfied'
    assert not plan['dispatch_authorized']
    assert Path(ledger.path).read_bytes() == before
    calls = []
    class Response:
        status = 200
        def read(self, maximum):
            return json.dumps(reply().body).encode()
    class Connection:
        def __init__(self, host, timeout):
            assert host == 'api.meta.ai'
        def request(self, method, path, body, headers):
            calls.append((method,path))
            assert json.loads(body) == request_payload(image())
        def getresponse(self):
            return Response()
        def close(self):
            pass
    monkeypatch.setattr('backend.meta_provider.http.client.HTTPSConnection', Connection)
    monkeypatch.setenv('HYDRA_AI_MODE','mock')
    monkeypatch.setenv('META_BILLABLE_REQUESTS_ENABLED','false')
    original_config = env.read_bytes()
    result = run_once(env, root / 'synthetic.sqlite3', photo, root / 'response.json')
    assert ledger.preview_finality_schema()['status'] == 'already_current'
    assert calls == [('POST','/v1/responses')]
    assert result['provider_reply']['body']['id'] == 'resp_testonly'
    assert result['recognition']['candidates'][0]['category'] == 'tea'
    assert result['backend_returned_to_mock']
    assert os.environ['HYDRA_AI_MODE'] == 'mock'
    assert os.environ['META_BILLABLE_REQUESTS_ENABLED'] == 'false'
    assert env.read_bytes() == original_config
    assert (root/'response.json').stat().st_mode & 0o777 == 0o600
    with pytest.raises(BudgetDenied):
        run_once(env, root/'synthetic.sqlite3', photo, root/'retry.json')
    assert len(calls) == 1


def test_backend_startup_preserves_authoritative_journal_and_financial_records(setup_risk, monkeypatch):
    from backend.app import create_app
    from test_guarded_meta import TOKEN
    ledger, _ = setup_risk()
    with ledger.transaction() as db:
        before = {table: db.execute('SELECT * FROM ' + table).fetchall() for table in accounts.FINANCIAL_DDL}
    monkeypatch.setenv('HYDRA_AI_MODE', 'mock')
    monkeypatch.setenv('META_BILLABLE_REQUESTS_ENABLED', 'false')
    create_app(ledger.path, TOKEN)
    assert ledger.preview_finality_schema()['status'] == 'already_current'
    with ledger.transaction() as db:
        assert db.execute('PRAGMA journal_mode').fetchone()[0] == 'delete'
        assert {table: db.execute('SELECT * FROM ' + table).fetchall() for table in accounts.FINANCIAL_DDL} == before


def test_known_provider_id_survives_missing_usage(setup_risk):
    ledger, _ = setup_risk()
    provider = FullBoundTransport(response=reply(usage=None))
    with pytest.raises(RecognitionUnavailable):
        gateway(ledger, provider).analyze(image())
    with ledger.transaction() as db:
        assert db.execute('SELECT provider_id FROM live_attempts').fetchone()[0] == 'resp_testonly'



@pytest.mark.parametrize('baseline,credits', [(118_000_000,150_000_000), (98_000_000,150_000_000), (0,31_999_999)])
def test_cutoff_checkpoint_and_credit_reserve_block(setup_risk, baseline, credits):
    with pytest.raises(BudgetDenied):
        setup_risk(gross_micro_usd=baseline, credits_remaining_micro_usd=credits)


def test_threshold_notice_and_failure_before_send(setup_risk):
    ledger, _ = setup_risk(gross_micro_usd=73_000_000)
    notifier = FakeNotifier()
    gateway(ledger, notifier=notifier).analyze(image())
    assert set(notifier.delivered) == set(ACCOUNTS)
    ledger, _ = setup_risk(gross_micro_usd=73_000_000)
    provider = FullBoundTransport()
    with pytest.raises(RecognitionUnavailable):
        gateway(ledger, provider, FakeNotifier(fail=True)).analyze(image())
    assert provider.calls == 0
    assert ledger.project_view()['project_reserved_micro_usd'] == 1_312_256


def test_concurrent_admissions_only_one_send(setup_risk):
    ledger, _ = setup_risk()
    provider = FullBoundTransport()
    def run(_):
        try:
            gateway(AccountLedger(ledger.path), provider).analyze(image())
            return True
        except RecognitionUnavailable:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(run, range(16))) == 1
    assert provider.calls == 1


def test_no_reduced_bound_wrong_image_or_credential(setup_risk):
    ledger, _ = setup_risk()
    with pytest.raises(BudgetDenied):
        ledger.quote(ACCOUNTS[0], 1000)
    with pytest.raises(BudgetDenied):
        ledger.reserve_first(ACCOUNTS[0], '0' * 64, MAX_INPUT_TOKENS)
    provider = FullBoundTransport()
    provider.credential_fingerprint = '0' * 64
    with pytest.raises(RecognitionUnavailable):
        gateway(ledger, provider).analyze(image())
    assert provider.calls == 0


def test_no_other_account_policy_or_permit_reset(setup_risk):
    ledger, ev = setup_risk()
    for approve in (lambda: ledger.approve_risk_test(risk_permit(ev)),
                    lambda: ledger.approve_controlled_test(controlled_permit(ACCOUNTS[1], HASH))):
        with pytest.raises(BudgetDenied):
            approve()
    with pytest.raises(ValidationError):
        risk_permit(ev, residual_provider_charge_risk_accepted=False)
    with pytest.raises(ValidationError):
        risk_permit(ev, account_id=ACCOUNTS[1])


@pytest.mark.parametrize('response,fault', [(reply(usage=None),None), (None,TimeoutError())])
def test_ambiguous_response_or_timeout_retains_reservation(setup_risk,response,fault):
    ledger, _ = setup_risk()
    provider = FullBoundTransport(response=response, fault=fault)
    for _ in range(2):
        with pytest.raises(RecognitionUnavailable):
            gateway(ledger,provider).analyze(image())
    assert provider.calls == 1
    assert ledger.project_view()['project_reserved_micro_usd'] == 1_312_256


def test_crash_and_expiry_between_reserve_and_send(setup_risk,monkeypatch):
    ledger, ev = setup_risk()
    attempt = ledger.reserve_first(ACCOUNTS[0], HASH, MAX_INPUT_TOKENS)
    monkeypatch.setattr(accounts,'now',lambda: ev.valid_until + timedelta(seconds=1))
    with pytest.raises(BudgetDenied):
        ledger.mark_dispatched(attempt, '0' * 64)
    assert AccountLedger(ledger.path).project_view()['project_reserved_micro_usd'] == 1_312_256


def test_verified_invoice_records_overrun_without_reopening_spending(setup_risk):
    ledger, _ = setup_risk()
    result = gateway(ledger).analyze(image())
    finality = InvoiceFinality(attempt_id=result.recognition_id, account_id=ACCOUNTS[0],
        provider_id='resp_testonly', final_gross_micro_usd=2_500_000,
        finalized_at=datetime.now(timezone.utc), provider_finality_verified=True,
        provider_evidence_reference='synthetic-final-invoice', georgio_review_reference='synthetic-review',
        amine_review_reference='synthetic-review')
    ledger.reconcile_risk_invoice(finality)
    ledger.reconcile_risk_invoice(finality)
    observed = read_observation(ledger.path, result.recognition_id)
    assert observed['final_gross_micro_usd'] == 2_500_000
    assert observed['usage_cost_micro_usd'] == 338
    assert observed['billing_status'] == 'invoice_verified'
    assert ledger.project_view()['accounts'][0]['frozen']
    assert ledger.project_view()['project_reserved_micro_usd'] == 0
    with pytest.raises(RecognitionUnavailable):
        gateway(ledger).analyze(image())

