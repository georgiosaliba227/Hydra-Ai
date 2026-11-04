"""Disposable-ledger owner exception tests. All provider replies are invented."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from importlib import import_module
import json
from pathlib import Path
import sys
import socket
import sqlite3
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from backend.app import create_app
from backend.meta_accounts import AccountLedger
from backend.meta_budget import BudgetDenied
from backend.meta_provider import ProviderReply
from backend.recognition import RecognitionUnavailable
from backend import wonder_analysis

KEY = "invented-owner-once-key"
KEY_HASH = hashlib.sha256(KEY.encode()).hexdigest()


def api():
    return import_module("backend.wonder_owner_once")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("network forbidden"))


def setup(tmp_path, *, baseline=0, reserved=1_312_256, state="billing_pending"):
    ledger = AccountLedger(tmp_path / "authority.sqlite3")
    ledger.initialize_accounts()
    with ledger.transaction() as db:
        db.execute("INSERT INTO live_accounts VALUES(?,?,?,1)", ("georgiosaliba227", json.dumps({
            "key_sha256": KEY_HASH, "gross_micro_usd": baseline,
            "credits_remaining_micro_usd": 150_000_000, "all_charge_categories_verified": False,
            "extra_charge_bound_micro_usd": None, "valid_until": "2026-10-28T00:00:00Z"}), baseline))
        for index in range(2):
            db.execute("INSERT INTO live_attempts(id,account_id,price,reserved,state,input_bound,created_at,provider_id,usage) "
                       "VALUES(?,?,?,?,?,?,?,?,?)", (str(uuid4()), "georgiosaliba227", "{}", reserved,
                       state if index == 0 else "unresolved", 100, "2026-10-28T00:00:00Z",
                       "resp_invented_historical_" + str(index), "{}"))
    return ledger, api().OwnerOnceAuthority(ledger)


def approval(owner):
    data = owner.prepare()
    return api().OwnerOnceAuthorization.model_validate_json(json.dumps(data | {
        "owner_authorization_reference": "synthetic-owner-approval",
        "prior_billing_waiver_reference": "synthetic-owner-finality-waiver",
        "price_reference": "https://dev.meta.ai/docs/pricing-rate-limits#synthetic-review",
        "credit_observation_reference": "synthetic-credit-observation",
        "observed_credits_micro_usd": 149_850_000,
        "risk_acceptance_reference": "synthetic-owner-extras-acceptance",
        "accept_unverified_extras": True,
    }))


def reply(*, inputs=1000, outputs=200, cached=0):
    facts = api().fixed_facts()
    selection = {"sections": {name: ids[:3] for name, ids in wonder_analysis.applicable_insights(facts).items()}}
    return ProviderReply(200, {"id": "resp_invented_owner_once", "model": "muse-wonder-1.0",
        "status": "completed", "error": None, "incomplete_details": None,
        "usage": {"input_tokens": inputs, "output_tokens": outputs, "total_tokens": inputs + outputs,
                  "input_tokens_details": {"cached_tokens": cached},
                  "output_tokens_details": {"reasoning_tokens": 0}},
        "output": [{"type": "message", "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "text": json.dumps(selection)}]}]})


class FakeTransport:
    credential_fingerprint = KEY_HASH

    def __init__(self, result=None, failure=None):
        self.result = result
        self.failure = failure
        self.calls = 0

    def input_bound(self, payload):
        return 4750

    def generate(self, payload, ticket):
        ticket.claim(payload, input_bound=4750, credential_fingerprint=self.credential_fingerprint)
        self.calls += 1
        if self.failure:
            raise self.failure
        return self.result or reply()


def original_rows(ledger):
    with ledger.transaction() as db:
        return {table: db.execute("SELECT * FROM " + table + " ORDER BY 1").fetchall()
                for table in ("live_accounts", "live_attempts", "live_finalities", "controlled_permits", "live_prices")}


def test_prepare_is_read_only_and_fixed_payload_is_synthetic(tmp_path):
    ledger, owner = setup(tmp_path)
    before = Path(ledger.path).read_bytes()
    result = owner.prepare()
    assert Path(ledger.path).read_bytes() == before
    assert result["payload_sha256"] == "12ef839f44757b452034632ef91c50ff44455e6c02c99104230f4c46d02ab34c"
    assert api().fixed_facts()["mode"] == "synthetic_demo"
    assert result["published_token_bound_micro_usd"] == 59960
    assert result["accept_unverified_extras"] is False


def test_one_reply_preserves_prior_history_and_retains_pending_reservation(tmp_path):
    ledger, owner = setup(tmp_path)
    before = original_rows(ledger)
    owner.authorize(approval(owner))
    transport = FakeTransport()
    target = tmp_path / "result.json"
    result = owner.run(transport, target)
    assert transport.calls == 1
    assert result["mode"] == "synthetic_demo" and len(result["result"]["sections"]) == 8
    receipt = result["receipt"]
    assert receipt["usage_derived_cost_micro_usd"] == 8000
    assert receipt["provider_invoice_final"] is receipt["provider_extras_bounded"] is False
    assert receipt["token_reservation_micro_usd"] == 250000
    after = original_rows(ledger)
    assert after["live_accounts"] == before["live_accounts"]
    for table in ("live_finalities", "controlled_permits", "live_prices"):
        assert before[table] == after[table]
    assert all(row in after["live_attempts"] for row in before["live_attempts"])
    with ledger.transaction() as db:
        row = db.execute("SELECT state,reserved,actual,provider_id FROM live_attempts WHERE id=?", (receipt["attempt_id"],)).fetchone()
    assert row == ("billing_pending", 250000, None, "resp_invented_owner_once")
    assert target.stat().st_mode & 0o777 == 0o600
    assert api().load_result(target) == result
    with pytest.raises(BudgetDenied):
        owner.run(transport, tmp_path / "second.json")
    with pytest.raises(BudgetDenied):
        owner.authorize(approval(owner))
    assert transport.calls == 1


@pytest.mark.parametrize("field,value", [
    ("payload_sha256", "a" * 64), ("key_sha256", "b" * 64),
    ("accept_unverified_extras", False), ("accept_unverified_extras", 1),
    ("owner_authorization_reference", " "), ("risk_acceptance_reference", ""),
    ("token_reservation_micro_usd", 1), ("input_micro_per_million", 1),
])
def test_changed_or_unacknowledged_authorization_refuses(tmp_path, field, value):
    ledger, owner = setup(tmp_path)
    descriptor = approval(owner).model_copy(update={field: value})
    with pytest.raises((BudgetDenied, ValidationError)):
        owner.authorize(descriptor)
    assert len(original_rows(ledger)["live_attempts"]) == 2


@pytest.mark.parametrize("when", ["authorize", "run"])
def test_changed_historical_snapshot_refuses(tmp_path, when):
    ledger, owner = setup(tmp_path)
    descriptor = approval(owner)
    if when == "run":
        owner.authorize(descriptor)
    with ledger.transaction() as db:
        db.execute("UPDATE live_attempts SET reserved=reserved+1")
    with pytest.raises(BudgetDenied):
        owner.authorize(descriptor) if when == "authorize" else owner.run(FakeTransport(), tmp_path / "result.json")


@pytest.mark.parametrize("state", ["dispatched", "sending", "experiment_reserved", "experiment_sending", "unknown"])
def test_actual_active_send_is_never_waived(tmp_path, state):
    _, owner = setup(tmp_path, state=state)
    with pytest.raises(BudgetDenied):
        owner.prepare()


@pytest.mark.parametrize("baseline,reserved", [(0, 15_000_000), (74_000_000, 500_000), (120_000_000, 1)])
def test_preserved_exposure_blocks_admission(tmp_path, baseline, reserved):
    _, owner = setup(tmp_path, baseline=baseline, reserved=reserved)
    with pytest.raises(BudgetDenied):
        owner.prepare()


def test_expired_or_overlong_permit_refuses(tmp_path):
    _, owner = setup(tmp_path)
    data = approval(owner)
    for expiry in (datetime.now(timezone.utc) - timedelta(seconds=1), datetime.now(timezone.utc) + timedelta(hours=2)):
        with pytest.raises((ValidationError, BudgetDenied)):
            owner.authorize(data.model_copy(update={"valid_until": expiry}))


def test_wrong_current_key_never_consumes_authorization(tmp_path):
    ledger, owner = setup(tmp_path)
    owner.authorize(approval(owner))
    transport = FakeTransport()
    transport.credential_fingerprint = "c" * 64
    with pytest.raises(BudgetDenied):
        owner.run(transport, tmp_path / "result.json")
    assert transport.calls == 0 and len(original_rows(ledger)["live_attempts"]) == 2


def test_two_concurrent_processes_only_reserve_and_send_once(tmp_path):
    ledger, owner = setup(tmp_path)
    owner.authorize(approval(owner))
    transport = FakeTransport()
    def perform(index):
        try:
            return api().OwnerOnceAuthority(AccountLedger(ledger.path)).run(transport, tmp_path / f"result-{index}.json")
        except BudgetDenied:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(perform, range(2)))
    assert sum(item is not None for item in results) == 1
    assert transport.calls == 1 and len(original_rows(ledger)["live_attempts"]) == 3


@pytest.mark.parametrize("problem", ["timeout", "invalid_usage", "over_bound", "invalid_output"])
def test_failure_never_releases_reservation_or_allows_retry(tmp_path, problem):
    ledger, owner = setup(tmp_path)
    owner.authorize(approval(owner))
    result = reply()
    if problem == "invalid_usage": result.body["usage"]["input_tokens"] = True
    if problem == "over_bound": result = reply(inputs=4751)
    if problem == "invalid_output": result.body["output"][0]["content"][0]["text"] = '{"sections":{}}'
    transport = FakeTransport(result, TimeoutError() if problem == "timeout" else None)
    with pytest.raises(RecognitionUnavailable):
        owner.run(transport, tmp_path / "result.json")
    with ledger.transaction() as db:
        state, reserved, actual = db.execute("SELECT state,reserved,actual FROM live_attempts ORDER BY created_at DESC LIMIT 1").fetchone()
    assert state == ("billing_pending" if problem == "invalid_output" else "unresolved")
    assert reserved == 250000 and actual is None
    with pytest.raises(BudgetDenied): owner.run(transport, tmp_path / "again.json")
    assert transport.calls == 1


def test_invalid_usage_retains_provider_identity_for_reconciliation(tmp_path):
    ledger, owner = setup(tmp_path)
    owner.authorize(approval(owner))
    result = reply()
    result.body["usage"]["input_tokens"] = True
    with pytest.raises(RecognitionUnavailable):
        owner.run(FakeTransport(result), tmp_path / "result.json")
    with ledger.transaction() as db:
        row = db.execute("SELECT provider_id,usage FROM live_attempts WHERE state='unresolved' AND provider_id='resp_invented_owner_once'").fetchone()
    assert row is not None
    assert json.loads(row[1])["input_tokens"] is True


def test_existing_integrity_sidecar_refuses_before_consumption(tmp_path):
    ledger, owner = setup(tmp_path)
    owner.authorize(approval(owner))
    path = tmp_path / "result.json"
    path.with_name("result.json.sha256").write_text("old unrelated file")
    transport = FakeTransport()
    with pytest.raises(ValueError):
        owner.run(transport, path)
    assert len(original_rows(ledger)["live_attempts"]) == 2 and transport.calls == 0


def test_process_crash_after_consumption_never_reopens_authorization(tmp_path, monkeypatch):
    ledger, owner = setup(tmp_path)
    owner.authorize(approval(owner))
    monkeypatch.setattr(owner, "_dispatch", lambda _attempt: sys.exit(17))
    with pytest.raises(SystemExit):
        owner.run(FakeTransport(), tmp_path / "result.json")
    fresh = api().OwnerOnceAuthority(AccountLedger(ledger.path))
    with pytest.raises(BudgetDenied):
        fresh.run(FakeTransport(), tmp_path / "again.json")
    with ledger.transaction() as db:
        assert db.execute("SELECT count(*) FROM live_attempts WHERE state='owner_once_reserved' AND actual IS NULL AND reserved=250000").fetchone()[0] == 1


def test_real_transport_claims_exact_ticket_before_fixed_origin_post(tmp_path, monkeypatch):
    ledger, owner = setup(tmp_path)
    owner.authorize(approval(owner))
    calls = []
    class Response:
        status = 200
        def read(self, _limit): return json.dumps(reply().body).encode()
    class Connection:
        def __init__(self, host, timeout):
            assert (host, timeout) == ("api.meta.ai", 20)
        def request(self, method, path, *, body, headers):
            with ledger.transaction() as db:
                assert db.execute("SELECT count(*) FROM live_attempts WHERE state='owner_once_sending' AND ticket_nonce IS NULL").fetchone()[0] == 1
            payload = json.loads(body)
            assert payload["model"] == "muse-wonder-1.0" and "tools" not in payload
            assert payload["store"] is payload["stream"] is payload["background"] is False
            assert (method, path) == ("POST", "/v1/responses")
            calls.append((method, path))
        def getresponse(self): return Response()
        def close(self): pass
    monkeypatch.setattr("backend.meta_provider.http.client.HTTPSConnection", Connection)
    result = owner.run(api().OwnerOnceMetaTransport(KEY), tmp_path / "result.json")
    assert result["receipt"]["state"] == "billing_pending" and len(calls) == 1


def test_cli_preparation_authorization_and_confirmation_refusal(tmp_path, capsys):
    ledger, _ = setup(tmp_path)
    cli = import_module("scripts.wonder_owner_once")
    descriptor = tmp_path / "descriptor.json"
    base = ["--database", str(ledger.path)]
    cli.main([*base, "prepare", "--output", str(descriptor)])
    assert json.loads(capsys.readouterr().out)["request_sent"] is False
    assert descriptor.stat().st_mode & 0o777 == 0o600
    data = json.loads(descriptor.read_text())
    data.update(owner_authorization_reference="invented-owner", prior_billing_waiver_reference="invented-waiver",
                price_reference="invented-current-prices", credit_observation_reference="invented-credits",
                observed_credits_micro_usd=149850000, risk_acceptance_reference="invented-risk", accept_unverified_extras=True)
    descriptor.write_text(json.dumps(data))
    cli.main([*base, "authorize", "--descriptor", str(descriptor)])
    assert json.loads(capsys.readouterr().out)["status"] == "owner_authorization_recorded"
    with pytest.raises(SystemExit):
        cli.main([*base, "run", "--result", str(tmp_path / "result.json")])
    assert len(original_rows(ledger)["live_attempts"]) == 2


def test_missing_replay_configuration_returns_404(tmp_path, monkeypatch):
    monkeypatch.delenv("HYDRA_WONDER_OWNER_ONCE_RESULT", raising=False)
    app = create_app(tmp_path / "beverages.sqlite3", "x" * 32)
    if "/v1/wonder/owner-once/result" not in {route.path for route in app.routes}:
        import_module("backend.wonder_owner_once_routes").install_owner_once_routes(app)
    response = TestClient(app).get("/v1/wonder/owner-once/result", headers={"Authorization": "Bearer " + "x" * 32})
    assert response.status_code == 404


@pytest.mark.parametrize("problem", ["personal", "final", "extras", "cost", "text", "hash", "cached", "unknown_key"])
def test_replay_rejects_changed_or_misleading_envelope(tmp_path, problem):
    _, owner = setup(tmp_path)
    owner.authorize(approval(owner))
    result = owner.run(FakeTransport(), tmp_path / "result.json")
    changed = deepcopy(result)
    if problem == "personal": changed["mode"] = "personal"
    if problem == "final": changed["receipt"]["provider_invoice_final"] = True
    if problem == "extras": changed["receipt"]["provider_extras_bounded"] = True
    if problem == "cost": changed["receipt"]["usage_derived_cost_micro_usd"] = 0
    if problem == "text": changed["result"]["sections"][0]["text"] = "Drink 999 mL"
    if problem == "hash": changed["receipt"]["payload_sha256"] = "f" * 64
    if problem == "cached": changed["receipt"]["cached_tokens"] = 1001
    if problem == "unknown_key": changed["unexpected"] = True
    with pytest.raises(ValueError): api().validate_envelope(changed)


def test_read_only_route_requires_owner_token_and_has_no_dispatch_endpoint(tmp_path, monkeypatch):
    _, owner = setup(tmp_path)
    owner.authorize(approval(owner))
    target = tmp_path / "result.json"
    result = owner.run(FakeTransport(), target)
    monkeypatch.setenv("HYDRA_WONDER_OWNER_ONCE_RESULT", str(target))
    app = create_app(tmp_path / "beverages.sqlite3", "x" * 32)
    routes = import_module("backend.wonder_owner_once_routes")
    if "/v1/wonder/owner-once/result" not in {route.path for route in app.routes}:
        routes.install_owner_once_routes(app)
    client = TestClient(app)
    path = "/v1/wonder/owner-once/result"
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer " + "x" * 32}).json() == result
    assert client.post(path, headers={"Authorization": "Bearer " + "x" * 32}).status_code == 405
    target.write_text("{}")
    assert client.get(path, headers={"Authorization": "Bearer " + "x" * 32}).status_code == 503
