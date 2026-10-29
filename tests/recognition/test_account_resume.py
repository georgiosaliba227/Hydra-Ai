"""Reviewed resume of a frozen account. Disposable synthetic ledgers only; never network or the private ledger."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.meta_accounts import ACCOUNTS, USD, AccountLedger
from backend.meta_budget import BudgetDenied
from backend.meta_resume import ResumeApproval, preview_resume, resume_account
from backend.wonder_experiment import LIVE_SCHEMA, WonderExperimentLedger
from test_guarded_meta import evidence
from test_meta_experiments import approval as experiment_approval, finalize_fixture, quote
from test_wonder_experiment import WONDER, FakeWonderTransport, approve, disabled_network, gateway

__all__ = ["disabled_network"]  # autouse network block from the shared fixtures
GEORGIO = ACCOUNTS[0]
CAMERA_COST = 1_312_256  # a full-context camera reservation's size, for realism


def rows(authority, sql, *args):
    with authority.transaction() as db:
        return db.execute(sql, args).fetchall()


def frozen_ledger(tmp_path, *, actual=CAMERA_COST, finalize=True, risk_evidence=False, baseline=0):
    """Georgio after the first camera request: one settled attempt, finalized, permit spent, account frozen."""
    authority = AccountLedger(tmp_path / "ledger.sqlite3")
    authority.initialize_accounts()
    if risk_evidence:  # PR #14 stores RiskEvidence, which main cannot parse; resume keeps it verbatim.
        raw = json.loads(evidence(GEORGIO, baseline).model_dump_json()) | {"policy_version": "georgio-first-camera-risk-v1",
                                                                         "all_charge_categories_verified": False}
        with authority.transaction() as db:
            db.execute("INSERT INTO live_accounts(account_id,evidence,anchor_gross) VALUES(?,?,?)",
                       (GEORGIO, json.dumps(raw), baseline))
    else:
        authority.attest_account(evidence(GEORGIO, baseline))
    attempt = str(uuid4())
    with authority.transaction() as db:
        db.execute("INSERT INTO live_permit(id,permit,spent) VALUES(1,?,1)", (json.dumps({"synthetic": "spent camera permit"}),))
        db.execute("INSERT INTO live_attempts(id,account_id,price,reserved,state,input_bound,created_at) VALUES(?,?,?,?,?,?,?)",
                   (attempt, GEORGIO, "{}", 2_000_000, "billing_pending", 1, datetime.now(timezone.utc).isoformat()))
        db.execute("UPDATE live_accounts SET frozen=1 WHERE account_id=?", (GEORGIO,))
    if finalize:
        finalize_fixture(authority, attempt, actual)
    return authority, attempt


def resume_approval(attempt, *, actual=CAMERA_COST, provider=None, **changes):
    values = {"version": "account-resume-v1", "account_id": GEORGIO,
              "reconciled_attempts": [{"attempt_id": attempt, "final_gross_micro_usd": actual,
                                       "provider_id": provider or "resp_fixture_" + attempt.replace("-", "")}],
              "provider_reconciliation_reference": "synthetic-final-invoice-review",
              "spending_approval_reference": "synthetic-new-wonder-spend-approval",
              "georgio_review_reference": "synthetic-review-a", "amine_review_reference": "synthetic-review-b",
              "reason": "camera invoice reconciled; resume for approved Wonder experiments",
              "valid_until": datetime.now(timezone.utc) + timedelta(hours=1)}
    return ResumeApproval.model_validate(values | changes)


def fresh(gross=CAMERA_COST, **changes):
    return evidence(GEORGIO, gross).model_copy(update=changes)


def snapshot(authority):
    return {table: rows(authority, f"SELECT * FROM {table}") for table in
            ("live_attempts", "live_finalities", "live_permit", "controlled_permits", "live_notices")}


def test_reconciled_account_resumes_once_with_history_preserved(tmp_path):
    authority, attempt = frozen_ledger(tmp_path)
    before, events = snapshot(authority), rows(authority, "SELECT * FROM live_events")
    previous = rows(authority, "SELECT evidence FROM live_accounts")[0][0]
    result = resume_account(authority, resume_approval(attempt), fresh())
    assert result["resumed"] and result["permits_changed"] is False and result["history_changed"] is False
    assert snapshot(authority) == before  # attempts, finalities, permits and notices untouched
    after = rows(authority, "SELECT * FROM live_events")
    assert after[:len(events)] == events and len(after) == len(events) + 1
    record = json.loads(after[-1][4])
    assert after[-1][2:4] == (GEORGIO, "account_resumed") and record["previous_evidence"] == previous
    assert record["approval"]["georgio_review_reference"] == "synthetic-review-a" and record["resumed_at"]
    [(raw, anchor, is_frozen)] = rows(authority, "SELECT evidence,anchor_gross,frozen FROM live_accounts")
    assert (anchor, is_frozen) == (CAMERA_COST, 0) and json.loads(raw)["gross_micro_usd"] == CAMERA_COST
    assert rows(authority, "SELECT spent FROM live_permit") == [(1,)]  # the spent camera permit stays spent
    with pytest.raises(BudgetDenied):  # and the camera path still refuses to reserve with it
        authority.reserve_first(GEORGIO, "a" * 64, 1)


def test_duplicate_resume_is_refused_and_records_nothing(tmp_path):
    authority, attempt = frozen_ledger(tmp_path)
    resume_account(authority, resume_approval(attempt), fresh())
    count = len(rows(authority, "SELECT * FROM live_events"))
    with pytest.raises(BudgetDenied, match="account_not_frozen"):
        resume_account(authority, resume_approval(attempt), fresh())
    assert len(rows(authority, "SELECT * FROM live_events")) == count


def test_concurrent_resumes_succeed_exactly_once(tmp_path):
    authority, attempt = frozen_ledger(tmp_path)

    def attempt_resume(_):
        try:
            return resume_account(authority, resume_approval(attempt), fresh())["resumed"]
        except BudgetDenied:
            return False
    with ThreadPoolExecutor(4) as pool:
        outcomes = list(pool.map(attempt_resume, range(4)))
    assert outcomes.count(True) == 1
    assert len(rows(authority, "SELECT 1 FROM live_events WHERE kind='account_resumed'")) == 1


def test_missing_finality_blocks_and_preview_changes_nothing(tmp_path):
    authority, attempt = frozen_ledger(tmp_path, finalize=False)
    with authority.transaction() as db:  # usage recorded, invoice not yet final
        db.execute("UPDATE live_attempts SET actual=?,provider_id=?,state='settled',dispatched_at=? WHERE id=?",
                   (CAMERA_COST, "resp_fixture_" + attempt.replace("-", ""), datetime.now(timezone.utc).isoformat(), attempt))
    before = (snapshot(authority), rows(authority, "SELECT * FROM live_events"), rows(authority, "SELECT * FROM live_accounts"))
    view = preview_resume(authority, resume_approval(attempt), fresh())
    assert view["would_resume"] is False and view["ledger_changed"] is False
    assert f"attempt_not_finalized:{attempt}" in view["blockers"]
    with pytest.raises(BudgetDenied, match="attempt_not_finalized"):
        resume_account(authority, resume_approval(attempt), fresh())
    assert (snapshot(authority), rows(authority, "SELECT * FROM live_events"), rows(authority, "SELECT * FROM live_accounts")) == before


def test_unresolved_billing_anywhere_blocks(tmp_path):
    authority, attempt = frozen_ledger(tmp_path)
    authority.attest_account(evidence(ACCOUNTS[1]))
    with authority.transaction() as db:  # e.g. a timeout on the other account: no usage, no finality
        db.execute("INSERT INTO live_attempts(id,account_id,price,reserved,state,input_bound,created_at) VALUES(?,?,?,?,?,?,?)",
                   (str(uuid4()), ACCOUNTS[1], "{}", 100, "unresolved", 1, datetime.now(timezone.utc).isoformat()))
    assert any(b.startswith("attempt_not_finalized") for b in preview_resume(authority, resume_approval(attempt), fresh())["blockers"])


@pytest.mark.parametrize("changes,blocker", [
    ({"provider": "resp_someone_elses_response"}, "reconciled_attempts_do_not_match_ledger"),
    ({"actual": CAMERA_COST - 1}, "reconciled_attempts_do_not_match_ledger"),
])
def test_reviewers_must_name_the_exact_provider_id_and_final_charge(tmp_path, changes, blocker):
    authority, attempt = frozen_ledger(tmp_path)
    assert blocker in preview_resume(authority, resume_approval(attempt, **changes), fresh())["blockers"]


def test_every_attempt_on_the_account_must_be_named(tmp_path):
    authority, attempt = frozen_ledger(tmp_path)
    approval = resume_approval(attempt).model_copy(update={"reconciled_attempts": []})
    assert "reconciled_attempts_do_not_match_ledger" in preview_resume(authority, approval, fresh())["blockers"]


@pytest.mark.parametrize("gross,blocker", [
    (CAMERA_COST - 1, "evidence_gross_below_recorded_spending"),
    (120 * USD - CAMERA_COST, "account_at_operational_cutoff"),
])
def test_fresh_evidence_must_account_for_recorded_spending_and_respect_the_cutoff(tmp_path, gross, blocker):
    authority, attempt = frozen_ledger(tmp_path)
    assert blocker in preview_resume(authority, resume_approval(attempt), fresh(gross))["blockers"]


@pytest.mark.parametrize("changes,blocker", [
    ({"provider_account_reference": "a-different-meta-account"}, "evidence_names_another_provider_account"),
    ({"key_sha256": evidence(ACCOUNTS[1]).key_sha256}, "key_belongs_to_another_account"),
])
def test_fresh_evidence_must_be_for_the_same_provider_account(tmp_path, changes, blocker):
    authority, attempt = frozen_ledger(tmp_path)
    authority.attest_account(evidence(ACCOUNTS[1]))
    assert blocker in preview_resume(authority, resume_approval(attempt), fresh(**changes))["blockers"]


def test_undelivered_notices_and_unacknowledged_overruns_block(tmp_path):
    authority, attempt = frozen_ledger(tmp_path, actual=2_500_000)  # actual above the 2,000,000 reservation
    assert "overrun_not_acknowledged" in preview_resume(authority, resume_approval(attempt, actual=2_500_000),
                                                         fresh(2_500_000))["blockers"]
    with authority.transaction() as db:
        db.execute("INSERT INTO live_notices(id,account_id,recipient,threshold) VALUES(?,?,?,75)", (str(uuid4()), GEORGIO, GEORGIO))
    view = preview_resume(authority, resume_approval(attempt, actual=2_500_000, overrun_acknowledged=True), fresh(2_500_000))
    assert view["blockers"] == ["undelivered_notices"]


def test_account_that_is_not_frozen_cannot_be_resumed(tmp_path):
    authority, attempt = frozen_ledger(tmp_path)
    with authority.transaction() as db:
        db.execute("UPDATE live_accounts SET frozen=0")
    assert preview_resume(authority, resume_approval(attempt), fresh())["blockers"] == ["account_not_frozen"]


@pytest.mark.parametrize("changes", [
    {"valid_until": datetime.now(timezone.utc) - timedelta(minutes=1)},
    {"valid_until": datetime.now(timezone.utc) + timedelta(days=3)},
    {"amine_review_reference": " "}, {"georgio_review_reference": ""}, {"spending_approval_reference": "  "},
    {"version": "account-resume-v0"}, {"account_id": "someone-else"},
])
def test_incomplete_or_expired_approvals_are_rejected(tmp_path, changes):
    with pytest.raises(ValidationError):
        resume_approval(str(uuid4()), **changes)


def test_pr14_risk_evidence_is_replaced_and_kept_in_the_audit_record(tmp_path):
    authority, attempt = frozen_ledger(tmp_path, risk_evidence=True)
    previous = rows(authority, "SELECT evidence FROM live_accounts")[0][0]
    resume_account(authority, resume_approval(attempt), fresh())
    record = json.loads(rows(authority, "SELECT reference FROM live_events WHERE kind='account_resumed'")[0][0])
    assert record["previous_evidence"] == previous and "policy_version" in json.loads(previous)


def test_resumed_account_can_run_an_approved_wonder_case_within_its_limits(tmp_path):
    authority, attempt = frozen_ledger(tmp_path)
    with authority.transaction() as db:
        for sql in LIVE_SCHEMA:
            db.execute(sql)
    ledger = WonderExperimentLedger(authority)
    with pytest.raises(BudgetDenied):  # frozen: nothing admitted before the resume
        ledger.record_approval(experiment_approval())
    resume_account(authority, resume_approval(attempt), fresh())
    ledger.record_approval(experiment_approval())
    case = approve(ledger)
    transport = FakeWonderTransport()
    result = gateway(ledger, transport).explain("complete", case.case_id, quote(WONDER), case.input_approval_reference)
    assert transport.calls == 1 and result["provenance"]["account_id"] == GEORGIO
    assert ledger.snapshot()["hard_limit_micro_usd"] == 30 * USD  # the $30 experiment limit is unchanged


def test_operator_script_requires_private_files_and_previews_read_only(tmp_path, capsys):
    import scripts.meta_account_resume as tool
    authority, attempt = frozen_ledger(tmp_path)
    files = {}
    for name, value in (("approval", resume_approval(attempt)), ("evidence", fresh())):
        path = tmp_path / f"{name}.json"
        path.write_text(value.model_dump_json())
        files[name] = path
    args = ["preview", "--database", str(authority.path), "--approval", str(files["approval"]), "--evidence", str(files["evidence"])]
    with pytest.raises(SystemExit):  # world-readable evidence is refused
        tool.main(args)
    for path in files.values():
        os.chmod(path, 0o600)
    tool.main(args)
    assert json.loads(capsys.readouterr().out)["would_resume"] is True
    assert rows(authority, "SELECT frozen FROM live_accounts")[0][0] == 1
    tool.main(["resume"] + args[1:])
    assert json.loads(capsys.readouterr().out)["resumed"] is True


# Review findings (2026-10-29): each reproduced before its fix.

def pr14_shaped(tmp_path, **kwargs):
    """PR #14 stores the spent risk permit in controlled_permits and leaves live_permit empty."""
    authority, attempt = frozen_ledger(tmp_path, **kwargs)
    with authority.transaction() as db:
        db.execute("DELETE FROM live_permit")
        db.execute("INSERT INTO controlled_permits(account_id,permit,spent) VALUES(?,?,1)",
                   (GEORGIO, json.dumps({"policy_version": "georgio-first-camera-risk-v1"})))
    return authority, attempt


def test_a_resume_never_reopens_the_first_test_or_dual_test_policies(tmp_path):
    from test_controlled_tests import permit as controlled_permit
    from test_guarded_meta import HASH
    authority, attempt = pr14_shaped(tmp_path)
    authority.attest_account(evidence(ACCOUNTS[1]))
    resume_account(authority, resume_approval(attempt), fresh())
    with pytest.raises(BudgetDenied):  # PR #14 adds its own guard with another message
        authority.approve_controlled_test(controlled_permit(ACCOUNTS[1], HASH))
    assert rows(authority, "SELECT account_id,spent FROM controlled_permits") == [(GEORGIO, 1)]


def test_an_unspent_permit_blocks_the_resume(tmp_path):
    authority, attempt = pr14_shaped(tmp_path)
    with authority.transaction() as db:
        db.execute("INSERT INTO controlled_permits(account_id,permit,spent) VALUES(?,?,0)", (ACCOUNTS[1], "{}"))
    assert "unspent_permit_would_reactivate" in preview_resume(authority, resume_approval(attempt), fresh())["blockers"]


def test_acknowledged_overrun_still_lets_wonder_run_and_unacknowledged_history_does_not(tmp_path):
    authority, attempt = frozen_ledger(tmp_path, actual=2_500_000)  # above the 2,000,000 reservation
    with authority.transaction() as db:
        for sql in LIVE_SCHEMA:
            db.execute(sql)
    resume_account(authority, resume_approval(attempt, actual=2_500_000, overrun_acknowledged=True), fresh(2_500_000))
    ledger = WonderExperimentLedger(authority)
    ledger.record_approval(experiment_approval())
    case = approve(ledger)
    transport = FakeWonderTransport()
    result = gateway(ledger, transport).explain("complete", case.case_id, quote(WONDER), case.input_approval_reference)
    assert transport.calls == 1
    # A later overrun that no resume acknowledged still blocks admission, even once finalized.
    [(reserved,)] = rows(authority, "SELECT reserved FROM live_attempts WHERE id=?", result["provenance"]["attempt_id"])
    finalize_fixture(authority, result["provenance"]["attempt_id"], actual=reserved + 1)
    second = approve(ledger, "missing_measurements")
    later = FakeWonderTransport()
    with pytest.raises(Exception):
        gateway(ledger, later).explain("missing_measurements", second.case_id, quote(WONDER), second.input_approval_reference)
    assert later.calls == 0


def test_unknown_triggers_block_the_resume(tmp_path):
    authority, attempt = frozen_ledger(tmp_path)
    with authority.transaction() as db:
        db.execute("CREATE TRIGGER sneaky AFTER UPDATE ON live_accounts BEGIN UPDATE live_permit SET spent=0; END")
    with pytest.raises(BudgetDenied):
        preview_resume(authority, resume_approval(attempt), fresh())
    with pytest.raises(BudgetDenied):
        resume_account(authority, resume_approval(attempt), fresh())
    assert rows(authority, "SELECT spent FROM live_permit") == [(1,)]
    assert rows(authority, "SELECT frozen FROM live_accounts")[0][0] == 1


def test_a_changed_key_must_be_acknowledged(tmp_path):
    authority, attempt = frozen_ledger(tmp_path)
    rotated = fresh(key_sha256="1" * 64)
    assert preview_resume(authority, resume_approval(attempt), rotated)["blockers"] == ["key_changed_not_acknowledged"]
    assert preview_resume(authority, resume_approval(attempt, new_key_acknowledged=True), rotated)["would_resume"]
