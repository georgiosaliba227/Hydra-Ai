"""Disposable SAME-authority fixtures only. Never real accounts, keys or network."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.meta_accounts import AccountLedger, ACCOUNTS, CAP
from backend.meta_budget import BudgetDenied
from test_guarded_meta import evidence, future


def module():
    assert importlib.util.find_spec("backend.meta_experiments") is not None, "review-only experiment accounting missing"
    from backend import meta_experiments
    return meta_experiments


def approval(**changes):
    return module().ExperimentApproval(
        key_sha256=evidence().key_sha256, valid_until=future(),
        owner_authorization_reference="synthetic-owner-30usd", spending_authority_reference="synthetic-spend30",
        policy_transition_reference="synthetic-review-only-transition", georgio_review_reference="synthetic-review-a",
        amine_review_reference="synthetic-review-b", further_spend_approval_reference=None,
    ).model_copy(update=changes)


def quote(model="muse-spark-1.3", **changes):
    values={"model":model,"version":"synthetic-price-"+model,"valid_until":future(),
            "input_micro_per_million":1250000 if model=="muse-spark-1.3" else 4000000,
            "output_micro_per_million":4250000 if model=="muse-spark-1.3" else 20000000,
            "extra_charge_bound_micro_usd":0,"all_charge_categories_verified":True,
            "model_access_verified":True,"reference":"synthetic-price-provider-review",
            "model_access_reference":"synthetic-account-model-access",
            "all_charge_bound_reference":"synthetic-all-charges-guarantee"}
    return module().ExperimentQuote.model_validate(values|changes)


def request(model="muse-spark-1.3", **changes):
    values={"attempt_id":str(uuid4()),"case_id":str(uuid4()),"payload_sha256":"a"*64,
            "input_bound":1000,"output_bound":512,"maximum_micro_usd":250000,
            "input_approval_reference":"synthetic-exact-input-consent","quote":quote(model)}
    return module().ExperimentRequest.model_validate(values|changes)


def setup(tmp_path, *, baseline=0, credits=150000000, further=None):
    authority=AccountLedger(tmp_path/"authority.sqlite3")
    authority.initialize_accounts()
    authority.attest_account(evidence(ACCOUNTS[0],baseline,credits))
    authority.attest_account(evidence(ACCOUNTS[1]))
    # Proposed migration is deliberately absent from production. Tests install
    # only the reviewed DDL in a disposable authoritative database.
    with authority.transaction() as db:
        for sql in module().PROPOSED_SCHEMA: db.execute(sql)
    budget=module().ExperimentBudget(authority)
    budget.record_approval(approval(further_spend_approval_reference=further))
    return authority,budget


def finalize_fixture(authority, attempt, actual=1000):
    """Synthetic provider-finalized rows; never a production reconciliation API."""
    now=datetime.now(timezone.utc)
    provider="resp_fixture_"+attempt.replace("-","")
    with authority.transaction() as db:
        db.execute("UPDATE live_attempts SET actual=?,provider_id=?,state='settled',dispatched_at=? WHERE id=?",
                   (actual,provider,(now-timedelta(seconds=1)).isoformat(),attempt))
        payload={"attempt_id":attempt,"account_id":ACCOUNTS[0],"provider_id":provider,
                 "final_gross_micro_usd":actual,"finalized_at":now.isoformat(),
                 "provider_evidence_reference":"synthetic-final-invoice","georgio_review_reference":"synthetic-review-a",
                 "amine_review_reference":"synthetic-review-b","provider_finality_verified":True}
        db.execute("INSERT INTO live_finalities(attempt_id,evidence,recorded_at) VALUES(?,?,?)",(attempt,json.dumps(payload),now.isoformat()))


def test_initial_review_reservation_is_atomic_same_authority_and_not_dispatchable(tmp_path):
    authority,budget=setup(tmp_path)
    before=authority.project_view()
    item=request(); outcome=budget.reserve_review_only(item)
    assert outcome["dispatch_enabled"] is False
    assert outcome["aggregate_exposure_micro_usd"]==250000
    assert authority.project_view()["project_reserved_micro_usd"]==250000
    assert authority.project_view()["accounts"][0]==before["accounts"][0] # Amine sorted first
    with pytest.raises(BudgetDenied):authority.mark_dispatched(item.attempt_id,item.payload_sha256)
    with pytest.raises(BudgetDenied):authority.claim_send(item.attempt_id,str(uuid4()),item.payload_sha256,1000,evidence().key_sha256)
    assert module().ExperimentBudget(AccountLedger(authority.path)).snapshot()["aggregate_exposure_micro_usd"]==250000


def test_single_allocation_no_new_identity_or_reset(tmp_path):
    authority,budget=setup(tmp_path)
    with authority.transaction() as db:
        stored=db.execute("SELECT approval FROM experiment_allocation WHERE id=1").fetchone()[0]
    budget.record_approval(module().ExperimentApproval.model_validate_json(stored))
    with pytest.raises((BudgetDenied,ValidationError)):
        budget.record_approval(approval(owner_authorization_reference="different-authorization"))
    with pytest.raises((BudgetDenied,ValidationError)):
        budget.record_approval(approval(allocation_id="another30"))
    with pytest.raises((BudgetDenied,ValidationError)):
        budget.record_approval(approval(account_id=ACCOUNTS[1]))
    with authority.transaction() as db:
        with pytest.raises(sqlite3.DatabaseError):db.execute("DELETE FROM experiment_allocation")


def test_aggregate_cap_across_models_not_replenished_by_cheaper_finality(tmp_path):
    authority,budget=setup(tmp_path)
    for i in range(120):
        item=request("muse-wonder-1.0" if i%2 else "muse-spark-1.3")
        budget.reserve_review_only(item);finalize_fixture(authority,item.attempt_id,actual=1)
    result=budget.snapshot()
    assert result["aggregate_exposure_micro_usd"]==30000000
    assert result["model_exposure_micro_usd"]=={"muse-spark-1.3":15000000,"muse-wonder-1.0":15000000}
    assert result["soft_target_exceeded"]==["muse-wonder-1.0"]
    with pytest.raises(BudgetDenied):budget.reserve_review_only(request())
    assert authority.project_view()["known_accounts_gross_micro_usd"]==120


def test_retry_requires_finality_explicit_approval_and_same_case_model_payload(tmp_path):
    authority,budget=setup(tmp_path)
    first=request();budget.reserve_review_only(first)
    retry=request(case_id=first.case_id,retry_of=first.attempt_id,retry_approval_reference="synthetic-retry-review")
    with pytest.raises(BudgetDenied):budget.reserve_review_only(retry)
    finalize_fixture(authority,first.attempt_id)
    with pytest.raises((BudgetDenied,ValidationError)):
        budget.reserve_review_only(request(case_id=first.case_id,retry_of=first.attempt_id))
    with pytest.raises(BudgetDenied):
        budget.reserve_review_only(request("muse-wonder-1.0",case_id=first.case_id,retry_of=first.attempt_id,retry_approval_reference="synthetic-retry-review"))
    with pytest.raises(BudgetDenied):
        budget.reserve_review_only(request(case_id=first.case_id,payload_sha256="b"*64,retry_of=first.attempt_id,retry_approval_reference="synthetic-retry-review"))
    budget.reserve_review_only(retry);finalize_fixture(authority,retry.attempt_id)
    with pytest.raises(BudgetDenied):
        budget.reserve_review_only(request(case_id=first.case_id,retry_of=retry.attempt_id,retry_approval_reference="synthetic-third-review"))
    assert budget.snapshot()["aggregate_exposure_micro_usd"]==500000


def test_race_one_admission_and_crash_no_release(tmp_path):
    authority,budget=setup(tmp_path)
    def reserve(_):
        try:module().ExperimentBudget(AccountLedger(authority.path)).reserve_review_only(request());return True
        except BudgetDenied:return False
    with ThreadPoolExecutor(max_workers=8) as pool:assert sum(pool.map(reserve,range(16)))==1
    reopened=module().ExperimentBudget(AccountLedger(authority.path))
    assert reopened.snapshot()["aggregate_exposure_micro_usd"]==250000
    with pytest.raises(BudgetDenied):reopened.reserve_review_only(request())


def test_missing_schema_never_initializes_or_creates_a_ledger(tmp_path):
    missing=tmp_path/"missing.sqlite3"
    budget=module().ExperimentBudget(AccountLedger(missing))
    with pytest.raises(BudgetDenied):budget.record_approval(approval())
    assert not missing.exists()
    authority=AccountLedger(tmp_path/"existing.sqlite3");authority.initialize_accounts()
    with pytest.raises(BudgetDenied):module().ExperimentBudget(authority).record_approval(approval())
    with authority.transaction() as db:assert not db.execute("SELECT name FROM sqlite_master WHERE name LIKE 'experiment_%'").fetchall()


@pytest.mark.parametrize("changes",[{"account_id":ACCOUNTS[1]},{"key_sha256":"0"*64},
    {"valid_until":datetime(2000,1,1,tzinfo=timezone.utc)}, {"georgio_review_reference":" "},
    {"amine_review_reference":""}, {"hard_limit_micro_usd":60000000}])
def test_invalid_or_wrong_account_approval_rejected(tmp_path,changes):
    authority,budget=setup(tmp_path)
    with pytest.raises((BudgetDenied,ValidationError)):budget.record_approval(approval(**changes))


@pytest.mark.parametrize("changes",[{"model":"unknown"},{"input_micro_per_million":0},
    {"all_charge_categories_verified":False},{"model_access_verified":False},
    {"extra_charge_bound_micro_usd":-1},{"valid_until":datetime(2000,1,1,tzinfo=timezone.utc)},
    {"reference":" "},{"all_charge_bound_reference":" "},{"model_access_reference":" "}])
def test_unknown_price_cost_or_access_fail_closed(changes):
    with pytest.raises(ValidationError):quote(**changes)


@pytest.mark.parametrize("changes",[{"maximum_micro_usd":250001},{"maximum_micro_usd":True},
    {"input_bound":0},{"input_bound":True},{"output_bound":2049},{"payload_sha256":"bad"},
    {"input_approval_reference":" "}])
def test_request_bound_validation(changes):
    with pytest.raises(ValidationError):request(**changes)


def test_verified_cost_including_extra_charges_must_fit_reservation(tmp_path):
    _,budget=setup(tmp_path)
    with pytest.raises(BudgetDenied):budget.reserve_review_only(request(maximum_micro_usd=100))
    with pytest.raises(BudgetDenied):budget.reserve_review_only(request(quote=quote(extra_charge_bound_micro_usd=249999)))
    assert budget.snapshot()["aggregate_exposure_micro_usd"]==0


def test_thresholds_credits_and_notice_delivery_remain_account_specific(tmp_path):
    authority,budget=setup(tmp_path,baseline=74750000)
    first=request();budget.reserve_review_only(first)
    assert {n["recipient"] for n in authority.notices()}==set(ACCOUNTS)
    finalize_fixture(authority,first.attempt_id)
    with pytest.raises(BudgetDenied):budget.reserve_review_only(request())
    for notice in authority.notices():authority.notice_delivered(notice["id"],"synthetic-delivery")
    budget.reserve_review_only(request())


@pytest.mark.parametrize("baseline,credits,further",[(99750000,150000000,None),(119750000,150000000,"synthetic-further"),(149750000,150000000,"synthetic-further"),(0,249999,None)])
def test_account_cutoffs_and_verified_credit_bounds(tmp_path,baseline,credits,further):
    _,budget=setup(tmp_path,baseline=baseline,credits=credits,further=further)
    with pytest.raises(BudgetDenied):budget.reserve_review_only(request())
    assert budget.snapshot()["aggregate_exposure_micro_usd"]==0


def test_unresolved_amine_or_project_freeze_blocks_without_altering_amine(tmp_path):
    authority,budget=setup(tmp_path)
    with authority.transaction() as db:
        db.execute("INSERT INTO live_attempts(id,account_id,price,reserved,state,input_bound,created_at) VALUES(?,?,?,?,?,?,?)",
                   (str(uuid4()),ACCOUNTS[1],"{}",123,"unresolved",1,datetime.now(timezone.utc).isoformat()))
    with pytest.raises(BudgetDenied):budget.reserve_review_only(request())
    assert budget.snapshot()["aggregate_exposure_micro_usd"]==0
    with authority.transaction() as db:db.execute("UPDATE live_accounts SET frozen=1 WHERE account_id=?",(ACCOUNTS[1],))
    with pytest.raises(BudgetDenied):budget.reserve_review_only(request())


def test_unknown_trigger_rejected_before_attempt_or_link_writes(tmp_path):
    authority,budget=setup(tmp_path)
    with authority.transaction() as db:
        db.execute("CREATE TRIGGER fail_experiment_link BEFORE INSERT ON experiment_attempts BEGIN SELECT RAISE(ABORT,'synthetic_crash'); END")
    with pytest.raises(BudgetDenied):budget.reserve_review_only(request())
    with authority.transaction() as db:
        assert db.execute("SELECT COUNT(*) FROM live_attempts").fetchone()[0]==0
        assert db.execute("SELECT COUNT(*) FROM experiment_attempts").fetchone()[0]==0
    with pytest.raises(BudgetDenied):budget.snapshot()


def test_missing_immutability_guard_fails_closed(tmp_path):
    authority,budget=setup(tmp_path)
    with authority.transaction() as db:db.execute("DROP TRIGGER experiment_allocation_no_delete")
    with pytest.raises(BudgetDenied):budget.reserve_review_only(request())


def test_expired_account_approval_or_quote_blocks_admission(tmp_path):
    authority,budget=setup(tmp_path)
    with authority.transaction() as db:
        raw=json.loads(db.execute("SELECT evidence FROM live_accounts WHERE account_id=?",(ACCOUNTS[0],)).fetchone()[0])
        raw["valid_until"]="2000-01-01T00:00:00Z"
        db.execute("UPDATE live_accounts SET evidence=? WHERE account_id=?",(json.dumps(raw),ACCOUNTS[0]))
    with pytest.raises(BudgetDenied):budget.reserve_review_only(request())
    with pytest.raises(ValidationError):budget.reserve_review_only(request().model_copy(update={"quote":quote().model_copy(update={"valid_until":datetime(2000,1,1,tzinfo=timezone.utc)})}))


def test_changed_or_deleted_attempt_cost_cannot_reduce_allocation(tmp_path):
    authority,budget=setup(tmp_path)
    item=request();budget.reserve_review_only(item);finalize_fixture(authority,item.attempt_id)
    with authority.transaction() as db:db.execute("UPDATE live_attempts SET reserved=1 WHERE id=?",(item.attempt_id,))
    with pytest.raises(BudgetDenied):budget.snapshot()
    with pytest.raises(BudgetDenied):budget.reserve_review_only(request())


def test_over_reservation_actual_remains_visible_but_new_admission_denied(tmp_path):
    authority,budget=setup(tmp_path)
    item=request();budget.reserve_review_only(item);finalize_fixture(authority,item.attempt_id,actual=250001)
    assert budget.snapshot()["aggregate_exposure_micro_usd"]==250001
    with pytest.raises(BudgetDenied):budget.reserve_review_only(request())


def test_crash_after_insert_rolls_back_without_phantom_exposure(tmp_path,monkeypatch):
    authority,budget=setup(tmp_path)
    def crash(*args):raise RuntimeError("synthetic-after-insert-crash")
    monkeypatch.setattr(authority,"event",crash)
    with pytest.raises(BudgetDenied):budget.reserve_review_only(request())
    assert budget.snapshot()["aggregate_exposure_micro_usd"]==0
    with authority.transaction() as db:
        assert db.execute("SELECT COUNT(*) FROM live_attempts").fetchone()[0]==0
        assert db.execute("SELECT COUNT(*) FROM experiment_attempts").fetchone()[0]==0


def test_existing_settlement_and_finality_cannot_activate_review_reservation(tmp_path):
    from test_guarded_meta import reply
    from backend.meta_accounts import InvoiceFinality
    authority,budget=setup(tmp_path)
    item=request();budget.reserve_review_only(item)
    with pytest.raises(BudgetDenied):authority.settle_provider_reply(item.attempt_id,reply())
    with pytest.raises(BudgetDenied):authority.record_invoice_finality(InvoiceFinality(
        attempt_id=item.attempt_id,account_id=ACCOUNTS[0],provider_id="resp_fake",final_gross_micro_usd=1,
        finalized_at=datetime.now(timezone.utc),provider_evidence_reference="synthetic",georgio_review_reference="synthetic",
        amine_review_reference="synthetic",provider_finality_verified=True))
    assert budget.snapshot()["aggregate_exposure_micro_usd"]==250000


@pytest.mark.parametrize("column,value",[("reserved",-1),("reserved",1.5),("actual",-1),("actual",1.5)])
def test_corrupt_existing_account_history_cannot_reduce_cutoff(tmp_path,column,value):
    authority,budget=setup(tmp_path)
    item=request();budget.reserve_review_only(item);finalize_fixture(authority,item.attempt_id)
    with authority.transaction() as db:
        db.execute(f"UPDATE live_attempts SET {column}=? WHERE id=?",(value,item.attempt_id))
    with pytest.raises(BudgetDenied):budget.reserve_review_only(request())


def test_altered_financial_table_layout_fails_closed(tmp_path):
    authority,budget=setup(tmp_path)
    with authority.transaction() as db:db.execute("ALTER TABLE experiment_allocation ADD COLUMN reset_counter INTEGER")
    with pytest.raises(BudgetDenied):budget.reserve_review_only(request())


def test_quote_expiring_while_waiting_for_authority_lock_denies_admission(tmp_path):
    import threading
    import time
    authority,budget=setup(tmp_path)
    expires=datetime.now(timezone.utc)+timedelta(milliseconds=200)
    item=request(quote=quote(valid_until=expires))
    started=threading.Event()
    def run():
        started.set()
        try:budget.reserve_review_only(item);return "admitted"
        except (BudgetDenied,ValidationError):return "denied"
    with ThreadPoolExecutor(max_workers=1) as pool:
        with authority.transaction():
            pending=pool.submit(run)
            assert started.wait(1)
            time.sleep(.25)
        assert pending.result()=="denied"
    assert budget.snapshot()["aggregate_exposure_micro_usd"]==0


def test_finalized_legacy_spend_counts_toward_account_not_experiment_and_permit_preserved(tmp_path):
    from backend.meta_accounts import FirstPermit
    authority,budget=setup(tmp_path,baseline=99600000)
    historical=str(uuid4())
    legacy=FirstPermit(account_id=ACCOUNTS[0],image_sha256="b"*64,price_version="synthetic-legacy",
        developer_approvals=ACCOUNTS,spending_authority_reference="synthetic-legacy-spend",
        account_owner_authorization_reference="synthetic-owner",image_owner_consent_reference="synthetic-image",
        valid_until=future())
    with authority.transaction() as db:
        db.execute("INSERT INTO live_permit(id,permit,spent) VALUES(1,?,1)",(legacy.model_dump_json(),))
        db.execute("INSERT INTO live_attempts(id,account_id,price,reserved,state,input_bound,created_at) VALUES(?,?,?,?,?,?,?)",
                   (historical,ACCOUNTS[0],"{}",250000,"reserved",1,datetime.now(timezone.utc).isoformat()))
    finalize_fixture(authority,historical,actual=200000)
    assert budget.snapshot()["aggregate_exposure_micro_usd"]==0
    # 99.60 historical baseline +0.20 prior actual +0.25 proposed =100.05;
    # existing account-specific further approval is mandatory.
    with pytest.raises(BudgetDenied):budget.reserve_review_only(request())
    with authority.transaction() as db:
        assert db.execute("SELECT permit,spent FROM live_permit WHERE id=1").fetchone()==(legacy.model_dump_json(),1)
        assert db.execute("SELECT actual FROM live_attempts WHERE id=?",(historical,)).fetchone()==(200000,)
