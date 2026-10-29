"""Wonder live-path accounting with disposable ledgers and fake transports. Never network."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import socket
import sqlite3
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend import meta_experiments
from backend.hydration_context_v2 import build_scenario, supported_selection
from backend.meta_accounts import ACCOUNTS, AccountLedger, CAP
from backend.meta_budget import BudgetDenied
from backend.meta_experiments import ExperimentBudget
from backend.meta_provider import ProviderReply
from backend.recognition import RecognitionUnavailable
from backend.wonder_experiment import (LIVE_SCHEMA, ApprovedCase, WonderExperimentLedger, WonderHydrationGateway,
                                       WonderMetaTransport)
from backend.wonder_hydration import input_bound, payload_sha256, wonder_payload
from test_guarded_meta import FakeNotifier, evidence, future
from test_meta_experiments import approval, finalize_fixture, quote, request

WONDER = "muse-wonder-1.0"


@pytest.fixture(autouse=True)
def disabled_network(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("network forbidden"))


def setup(tmp_path, *, credits=150_000_000, baseline=0):
    authority = AccountLedger(tmp_path / "authority.sqlite3")
    authority.initialize_accounts()
    authority.attest_account(evidence(ACCOUNTS[0], baseline, credits))
    authority.attest_account(evidence(ACCOUNTS[1]))
    with authority.transaction() as db:
        for sql in LIVE_SCHEMA:
            db.execute(sql)
    ledger = WonderExperimentLedger(authority)
    ledger.record_approval(approval())
    return authority, ledger


def approve(ledger, scenario="complete", **changes):
    values = dict(case_id=str(uuid4()), model=WONDER, payload_sha256=payload_sha256(wonder_payload(scenario)),
                  valid_until=future(), input_approval_reference="synthetic-exact-input-consent",
                  live_dispatch_reference="synthetic-live-dispatch-approval",
                  spending_approval_reference="synthetic-spend-approval")
    case = ApprovedCase.model_validate(values | changes)
    ledger.record_case(case)
    return case


def selection_reply(scenario="complete", *, inputs=900, outputs=120, cached=0, model=WONDER, text=None, identifier=None):
    text = json.dumps(supported_selection(*build_scenario(scenario))) if text is None else text
    return ProviderReply(200, {
        "id": identifier or "resp_wonder_" + uuid4().hex, "model": model, "status": "completed", "error": None,
        "incomplete_details": None,
        "usage": {"input_tokens": inputs, "output_tokens": outputs, "total_tokens": inputs + outputs,
                  "input_tokens_details": {"cached_tokens": cached}, "output_tokens_details": {"reasoning_tokens": 40}},
        "output": [{"type": "reasoning", "summary": []},
                   {"type": "message", "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "text": text}]}]})


class FakeWonderTransport:
    """Mirrors WonderMetaTransport's claim-then-send order without any socket."""
    def __init__(self, response=None, fault=None):
        self.response, self.fault, self.calls = response, fault, 0
        self.credential_fingerprint = evidence().key_sha256

    def input_bound(self, payload):
        return input_bound(payload)

    def generate(self, payload, ticket):
        ticket.claim(payload, input_bound=self.input_bound(payload), credential_fingerprint=self.credential_fingerprint)
        self.calls += 1
        assert payload["model"] == WONDER and payload["max_output_tokens"] == 512
        assert payload["store"] is False and "tools" not in payload
        if self.fault:
            raise self.fault
        return self.response or selection_reply()


def gateway(ledger, transport=None):
    return WonderHydrationGateway(ledger, transport or FakeWonderTransport(), FakeNotifier())


def attempt_rows(authority):
    with authority.transaction() as db:
        return db.execute("SELECT id,state,reserved,actual,provider_id FROM live_attempts").fetchall()


def frozen(authority):
    with authority.transaction() as db:
        return bool(db.execute("SELECT frozen FROM live_accounts WHERE account_id=?", (ACCOUNTS[0],)).fetchone()[0])


def test_approved_case_runs_once_and_settles_at_wonder_prices(tmp_path):
    authority, ledger = setup(tmp_path)
    case = approve(ledger)
    transport = FakeWonderTransport()
    result = gateway(ledger, transport).explain("complete", case.case_id, quote(WONDER), case.input_approval_reference)
    assert transport.calls == 1
    provenance = result["provenance"]
    assert (provenance["mode"], provenance["model"], provenance["account_id"]) == ("meta_live", WONDER, ACCOUNTS[0])
    assert result["systems"]["A"]["prediction"] == result["systems"]["C"]["prediction"]
    assert result["systems"]["B"]["prediction"] is None
    # 900 input x $4 + 120 output x $20 per million = 6,000 micro-USD.
    assert result["provider_observations"]["usage_derived_cost_micro_usd"] == 6000
    assert result["provider_observations"]["billed_cost_usd"] is None
    [(attempt, state, reserved, actual, provider)] = attempt_rows(authority)
    assert (attempt, state, actual) == (provenance["attempt_id"], "settled", 6000) and provider.startswith("resp_")
    assert reserved == quote(WONDER).bound(input_bound(wonder_payload("complete")), 512) <= CAP
    assert not frozen(authority)
    assert ledger.snapshot()["model_exposure_micro_usd"][WONDER] == reserved  # max(reserved, actual)


def test_next_case_waits_for_invoice_finality(tmp_path):
    authority, ledger = setup(tmp_path)
    first, second = approve(ledger), approve(ledger, "missing_measurements")
    transport = FakeWonderTransport()
    gateway(ledger, transport).explain("complete", first.case_id, quote(WONDER), first.input_approval_reference)
    transport.response = selection_reply("missing_measurements")
    with pytest.raises(RecognitionUnavailable):
        gateway(ledger, transport).explain("missing_measurements", second.case_id, quote(WONDER), second.input_approval_reference)
    assert transport.calls == 1 and len(attempt_rows(authority)) == 1
    finalize_fixture(authority, attempt_rows(authority)[0][0], actual=6000)
    gateway(ledger, transport).explain("missing_measurements", second.case_id, quote(WONDER), second.input_approval_reference)
    assert transport.calls == 2


@pytest.mark.parametrize("problem", ["unapproved", "other_payload", "other_input_reference"])
def test_only_exact_approved_cases_are_admitted(tmp_path, problem):
    authority, ledger = setup(tmp_path)
    case = approve(ledger)
    case_id, scenario, reference = case.case_id, "complete", case.input_approval_reference
    if problem == "unapproved":
        case_id = str(uuid4())
    elif problem == "other_payload":
        scenario = "missing_measurements"
    else:
        reference = "different-consent"
    transport = FakeWonderTransport()
    with pytest.raises(RecognitionUnavailable):
        gateway(ledger, transport).explain(scenario, case_id, quote(WONDER), reference)
    assert transport.calls == 0 and attempt_rows(authority) == []


def test_case_manifest_is_immutable_and_one_case_per_payload(tmp_path):
    authority, ledger = setup(tmp_path)
    case = approve(ledger)
    ledger.record_case(case)  # identical re-import is idempotent
    with pytest.raises(BudgetDenied):
        ledger.record_case(case.model_copy(update={"live_dispatch_reference": "replacement"}))
    with pytest.raises(BudgetDenied):
        approve(ledger)  # same payload under a new case ID
    with authority.transaction() as db:
        with pytest.raises(sqlite3.DatabaseError):
            db.execute("DELETE FROM experiment_cases")
        with pytest.raises(sqlite3.DatabaseError):
            db.execute("UPDATE experiment_cases SET model='muse-spark-1.3'")
    with pytest.raises(ValidationError):
        approve(ledger, "missing_measurements", live_dispatch_reference=" ")
    with pytest.raises(ValidationError):
        approve(ledger, "missing_measurements", case_id="not-a-uuid")


def test_case_manifest_requires_installed_live_schema(tmp_path):
    authority = AccountLedger(tmp_path / "authority.sqlite3")
    authority.initialize_accounts()
    authority.attest_account(evidence(ACCOUNTS[0]))
    with authority.transaction() as db:
        for sql in meta_experiments.PROPOSED_SCHEMA:
            db.execute(sql)
    ExperimentBudget(authority).record_approval(approval())
    with pytest.raises(BudgetDenied):
        WonderExperimentLedger(authority).record_case(ApprovedCase(
            case_id=str(uuid4()), model=WONDER, payload_sha256="a" * 64, valid_until=future(),
            input_approval_reference="x", live_dispatch_reference="y", spending_approval_reference="z"))


def test_legacy_and_review_only_paths_cannot_dispatch_each_other(tmp_path):
    authority, ledger = setup(tmp_path)
    case = approve(ledger)
    payload = wonder_payload("complete")
    live = request(WONDER, case_id=case.case_id, payload_sha256=payload_sha256(payload),
                   input_bound=input_bound(payload), maximum_micro_usd=CAP)
    ledger.reserve_for_dispatch(live)
    with pytest.raises(BudgetDenied):
        authority.mark_dispatched(live.attempt_id, live.payload_sha256)  # legacy camera path
    finalize_fixture(authority, live.attempt_id)
    review = request(WONDER)  # review-only reservation is not in the manifest and never dispatches
    ExperimentBudget(authority).reserve_review_only(review)
    with pytest.raises(BudgetDenied):
        ledger.mark_dispatched(review.attempt_id, review.payload_sha256)


def test_ticket_is_one_use_and_bound_to_credential_and_input_bound(tmp_path):
    authority, ledger = setup(tmp_path)
    case = approve(ledger)
    payload = wonder_payload("complete")
    item = request(WONDER, case_id=case.case_id, payload_sha256=payload_sha256(payload),
                   input_bound=input_bound(payload), maximum_micro_usd=CAP)
    ledger.reserve_for_dispatch(item)
    ticket = ledger.mark_dispatched(item.attempt_id, item.payload_sha256)
    with pytest.raises(BudgetDenied):
        ledger.mark_dispatched(item.attempt_id, item.payload_sha256)
    key = evidence().key_sha256
    with pytest.raises(BudgetDenied):
        ticket.claim(payload, input_bound=item.input_bound, credential_fingerprint="b" * 64)
    with pytest.raises(BudgetDenied):
        ticket.claim(payload, input_bound=item.input_bound + 1, credential_fingerprint=key)
    with pytest.raises(BudgetDenied):
        ledger.claim_send(item.attempt_id, str(uuid4()), item.payload_sha256, item.input_bound, key)
    with pytest.raises(BudgetDenied):
        ticket.claim(wonder_payload("missing_measurements"), input_bound=item.input_bound, credential_fingerprint=key)
    ticket.claim(payload, input_bound=item.input_bound, credential_fingerprint=key)
    with pytest.raises(BudgetDenied):
        ticket.claim(payload, input_bound=item.input_bound, credential_fingerprint=key)


@pytest.mark.parametrize("reply", [
    selection_reply(model="muse-spark-1.3"), selection_reply(cached=10), selection_reply(identifier="not-a-response-id"),
    ProviderReply(200, {"model": WONDER, "id": "resp_x", "usage": {"input_tokens": 1}}),
    ProviderReply(500, {"error": {"code": "server_error"}}),
])
def test_unverifiable_usage_freezes_and_keeps_reservation(tmp_path, reply):
    authority, ledger = setup(tmp_path)
    case = approve(ledger)
    with pytest.raises(RecognitionUnavailable):
        gateway(ledger, FakeWonderTransport(reply)).explain("complete", case.case_id, quote(WONDER), case.input_approval_reference)
    [(_, state, reserved, actual, _)] = attempt_rows(authority)
    assert state == "unresolved" and actual is None and reserved > 0
    assert frozen(authority)


@pytest.mark.parametrize("usage", [{"inputs": 50_000}, {"outputs": 513}])
def test_usage_above_reservation_bounds_settles_and_freezes(tmp_path, usage):
    authority, ledger = setup(tmp_path)
    case = approve(ledger)
    with pytest.raises(RecognitionUnavailable):
        gateway(ledger, FakeWonderTransport(selection_reply(**usage))).explain(
            "complete", case.case_id, quote(WONDER), case.input_approval_reference)
    [(_, state, _, actual, _)] = attempt_rows(authority)
    assert state == "settled" and actual > 0
    assert frozen(authority)


def test_ungrounded_output_after_settlement_freezes_without_a_result(tmp_path):
    authority, ledger = setup(tmp_path)
    case = approve(ledger)
    bad = json.dumps(supported_selection(*build_scenario("complete")) | {"factors": ["heart_rate_context"]})
    with pytest.raises(RecognitionUnavailable):
        gateway(ledger, FakeWonderTransport(selection_reply(text=bad))).explain(
            "complete", case.case_id, quote(WONDER), case.input_approval_reference)
    [(_, state, _, actual, _)] = attempt_rows(authority)
    assert state == "settled" and actual == 6000  # usage is still accounted
    assert frozen(authority)


def test_transport_fault_after_claim_keeps_unresolved_reservation(tmp_path):
    authority, ledger = setup(tmp_path)
    case = approve(ledger)
    transport = FakeWonderTransport(fault=TimeoutError())
    with pytest.raises(RecognitionUnavailable):
        gateway(ledger, transport).explain("complete", case.case_id, quote(WONDER), case.input_approval_reference)
    [(_, state, reserved, actual, _)] = attempt_rows(authority)
    assert (state, actual) == ("unresolved", None) and reserved > 0 and frozen(authority)


def test_expired_case_or_quote_blocks_dispatch_after_reservation(tmp_path, monkeypatch):
    authority, ledger = setup(tmp_path)
    case = approve(ledger)
    payload = wonder_payload("complete")
    item = request(WONDER, case_id=case.case_id, payload_sha256=payload_sha256(payload),
                   input_bound=input_bound(payload), maximum_micro_usd=CAP)
    ledger.reserve_for_dispatch(item)
    later = datetime.now(timezone.utc) + timedelta(hours=2)
    monkeypatch.setattr(meta_experiments, "now", lambda: later)
    with pytest.raises(BudgetDenied):
        ledger.mark_dispatched(item.attempt_id, item.payload_sha256)


def test_quote_above_per_attempt_cap_is_rejected_before_reservation(tmp_path):
    authority, ledger = setup(tmp_path)
    case = approve(ledger)
    transport = FakeWonderTransport()
    with pytest.raises(RecognitionUnavailable):
        gateway(ledger, transport).explain("complete", case.case_id, quote(WONDER, extra_charge_bound_micro_usd=CAP),
                                           case.input_approval_reference)
    assert transport.calls == 0 and attempt_rows(authority) == []


def test_frozen_project_blocks_reservation(tmp_path):
    authority, ledger = setup(tmp_path)
    case = approve(ledger)
    with authority.transaction() as db:
        db.execute("UPDATE live_accounts SET frozen=1 WHERE account_id=?", (ACCOUNTS[1],))
    with pytest.raises(RecognitionUnavailable):
        gateway(ledger).explain("complete", case.case_id, quote(WONDER), case.input_approval_reference)
    assert attempt_rows(authority) == []


def test_official_wonder_transport_accepts_only_exact_payloads_and_experiment_tickets(tmp_path):
    transport = WonderMetaTransport("synthetic-key")
    payload = wonder_payload("complete")
    assert transport.input_bound(payload) == input_bound(payload)
    with pytest.raises(ValueError):
        transport.input_bound(payload | {"model": "muse-spark-1.3"})
    with pytest.raises(ValueError):
        transport.input_bound(payload | {"tools": [{"type": "web_search"}]})
    with pytest.raises(RecognitionUnavailable):
        transport.generate(payload, object())  # wrong ticket type, before any socket


def bare_ledger(tmp_path):
    authority = AccountLedger(tmp_path / "authority.sqlite3")
    authority.initialize_accounts()
    authority.attest_account(evidence(ACCOUNTS[0]))
    return authority


def snapshot_records(authority):
    with authority.transaction() as db:
        return (db.execute("SELECT * FROM live_accounts").fetchall(),
                db.execute("SELECT COUNT(*) FROM live_events").fetchone()[0])


def test_live_schema_migration_is_explicit_atomic_and_idempotent(tmp_path):
    authority = bare_ledger(tmp_path)
    ledger = WonderExperimentLedger(authority)
    raw_before = Path(authority.path).read_bytes()
    preview = ledger.preview_live_schema()
    assert preview["status"] == "migration_required" and len(preview["missing_objects"]) == len(LIVE_SCHEMA)
    assert Path(authority.path).read_bytes() == raw_before  # preview is read-only
    accounts, events = snapshot_records(authority)
    with pytest.raises(BudgetDenied):
        ledger.migrate_live_schema(review_reference=" padded ")
    result = ledger.migrate_live_schema(review_reference="PR-20 schema review")
    assert result["status"] == "migrated" and result["audit_event_added"] is True
    assert snapshot_records(authority) == (accounts, events + 1)
    assert ledger.migrate_live_schema(review_reference="PR-20 schema review")["status"] == "already_current"
    ledger.record_approval(approval())
    approve(ledger)


def test_partial_review_only_schema_gets_only_missing_objects(tmp_path):
    authority = bare_ledger(tmp_path)
    with authority.transaction() as db:
        for sql in meta_experiments.PROPOSED_SCHEMA:
            db.execute(sql)
    result = WonderExperimentLedger(authority).migrate_live_schema(review_reference="partial-review")
    assert result["migrated_objects"] == ["experiment_cases", "experiment_cases_no_update", "experiment_cases_no_delete"]


@pytest.mark.parametrize("tamper", [
    "CREATE TRIGGER rogue AFTER INSERT ON live_attempts BEGIN SELECT 1; END",
    "CREATE TABLE experiment_cases(case_id TEXT PRIMARY KEY, model TEXT, payload_sha256 TEXT, approval TEXT)",
    "CREATE TABLE experiment_extra(id INTEGER)",
    "CREATE INDEX live_attempts_extra ON live_attempts(state)",
    "DROP TABLE live_finalities",
])
def test_live_schema_migration_refuses_unknown_or_old_schemas(tmp_path, tamper):
    authority = bare_ledger(tmp_path)
    with authority.transaction() as db:
        db.execute(tamper)
    ledger = WonderExperimentLedger(authority)
    with pytest.raises(BudgetDenied):
        ledger.preview_live_schema()
    with pytest.raises(BudgetDenied):
        ledger.migrate_live_schema(review_reference="tamper-review")


def test_live_schema_migration_never_creates_a_ledger(tmp_path):
    ledger = WonderExperimentLedger(AccountLedger(tmp_path / "missing.sqlite3"))
    with pytest.raises(BudgetDenied):
        ledger.migrate_live_schema(review_reference="missing-review")
    assert not (tmp_path / "missing.sqlite3").exists()


def test_admin_prepare_and_import_without_network(tmp_path, capsys):
    from scripts.wonder_admin import main
    main(["prepare", "--scenario", "contradictory_mass"])
    package = json.loads(capsys.readouterr().out)
    assert package["preview"]["dispatch_enabled"] is False
    assert package["approved_case_template"]["payload_sha256"] == payload_sha256(wonder_payload("contradictory_mass"))
    authority = bare_ledger(tmp_path)
    database = str(authority.path)
    main(["migrate-schema", "--database", database, "--reference", "admin-test-review"])
    capsys.readouterr()
    descriptor = tmp_path / "approval.json"
    descriptor.write_text(approval().model_dump_json())
    main(["record-allocation", "--database", database, "--descriptor", str(descriptor)])
    case = package["approved_case_template"] | {"valid_until": future().isoformat(), "input_approval_reference": "a",
                                                "live_dispatch_reference": "b", "spending_approval_reference": "c"}
    descriptor.write_text(json.dumps(case))
    main(["record-case", "--database", database, "--descriptor", str(descriptor)])
    with pytest.raises(SystemExit):
        main(["record-case", "--database", database, "--descriptor", str(descriptor.with_name("absent.json"))])
    with pytest.raises(SystemExit):
        main(["preview-schema", "--database", "relative.sqlite3"])
