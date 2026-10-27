"""No provider calls. Race, replay, retry, restart and threshold coverage."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from backend.meta_budget import BudgetDenied, MetaBudget, USD

PRICE = "mock-reviewed-price-v1"
VALID_UNTIL = datetime.now(timezone.utc) + timedelta(hours=1)


def ledger(tmp_path, baseline=0, further=False):
    budget = MetaBudget(tmp_path / "authoritative.sqlite3")
    budget.initialize(historical_micro_usd=baseline, reconciliation_reference="synthetic-dashboard")
    budget.record_approval(reference="synthetic-test-approval", price_version=PRICE, valid_until=VALID_UNTIL, further_spend=further)
    return budget


def reserve(budget, amount=250_000, attempt=None, parent=None):
    attempt = attempt or str(uuid4())
    budget.reserve(attempt, parent or str(uuid4()), amount, price_version=PRICE)
    return attempt


def test_concurrent_requests_cannot_cross_cutoff(tmp_path):
    budget = ledger(tmp_path, 119 * USD, further=True)
    def attempt(_):
        try: reserve(budget); return True
        except BudgetDenied: return False
    with ThreadPoolExecutor(max_workers=12) as pool:
        assert sum(pool.map(attempt, range(24))) == 3
    assert budget.snapshot()["exposure_micro_usd"] == 119_750_000


def test_duplicate_dispatch_denied_concurrently(tmp_path):
    budget = ledger(tmp_path); key = str(uuid4()); parent = str(uuid4())
    def attempt(_):
        try: reserve(budget, attempt=key, parent=parent); return True
        except BudgetDenied: return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt, range(16))) == 1


def test_crash_timeout_and_restart_keep_reservation(tmp_path):
    budget = ledger(tmp_path); key = reserve(budget)
    restored = MetaBudget(budget.path)
    assert restored.snapshot()["exposure_micro_usd"] == 250_000
    with pytest.raises(BudgetDenied): reserve(restored, attempt=key)
    restored.settle(key, 100_000, provider_id="synthetic-provider-id")
    restored.settle(key, 100_000, provider_id="synthetic-provider-id")
    assert restored.snapshot()["exposure_micro_usd"] == 100_000
    with pytest.raises(BudgetDenied): restored.settle(key, 0, provider_id="different")
    with pytest.raises(BudgetDenied): reserve(restored)
    with pytest.raises(BudgetDenied): restored.initialize(historical_micro_usd=0,reconciliation_reference="reset")


@pytest.mark.parametrize("baseline,further,allowed", [(74_750_000,False,True),(99_750_000,False,False),
    (99_750_000,True,True),(119_750_000,True,False),(120_000_000,True,False)])
def test_thresholds(tmp_path, baseline, further, allowed):
    budget = ledger(tmp_path, baseline, further)
    if allowed: reserve(budget)
    else:
        with pytest.raises(BudgetDenied): reserve(budget)


def test_75_notice_is_durable_once(tmp_path):
    budget = ledger(tmp_path, 74_750_000)
    reserve(budget); reserve(budget)
    events = MetaBudget(budget.path).snapshot()["events"]
    assert sum(kind == "notify_both_75_pending" for kind, _ in events) == 1


def test_retry_requires_separate_reservation_and_parent_cap(tmp_path):
    budget = ledger(tmp_path); parent = str(uuid4())
    reserve(budget,parent=parent); reserve(budget,parent=parent)
    with pytest.raises(BudgetDenied): reserve(budget,parent=parent)
    assert budget.snapshot()["exposure_micro_usd"] == 500_000


def test_unapproved_missing_unknown_and_stale_fail_closed(tmp_path):
    budget = MetaBudget(tmp_path / "unknown.sqlite3")
    with pytest.raises(BudgetDenied): reserve(budget)
    budget.initialize(historical_micro_usd=0, reconciliation_reference="synthetic")
    with pytest.raises(BudgetDenied): reserve(budget)
    budget.record_approval(reference="synthetic",price_version="other",valid_until=VALID_UNTIL)
    with pytest.raises(BudgetDenied): reserve(budget)
    for amount in [None, True, -1, 0, 250_001, 0.1]:
        with pytest.raises(BudgetDenied): reserve(budget,amount=amount)


def test_corruption_lock_and_overrun_freeze(tmp_path):
    budget = ledger(tmp_path)
    db = sqlite3.connect(budget.path); db.execute("BEGIN IMMEDIATE")
    with pytest.raises(BudgetDenied): reserve(budget)
    db.rollback(); db.close()
    key = reserve(budget)
    with pytest.raises(BudgetDenied): budget.settle(key,300_000,provider_id="overrun")
    assert budget.snapshot()["exposure_micro_usd"] == 300_000
    with pytest.raises(BudgetDenied): reserve(budget)
    corrupt = tmp_path / "corrupt.sqlite3"; corrupt.write_bytes(b"broken sqlite")
    with pytest.raises(BudgetDenied): reserve(MetaBudget(corrupt))


def test_reconciliation_discrepancy_kill_switch(tmp_path):
    budget = ledger(tmp_path)
    budget.freeze("synthetic-reconciliation-discrepancy")
    with pytest.raises(BudgetDenied): reserve(budget)


def test_expired_prices_block_existing_approval(tmp_path):
    budget = ledger(tmp_path)
    with sqlite3.connect(budget.path) as db:
        db.execute("UPDATE meta_policy SET price_expires=0")
    with pytest.raises(BudgetDenied): reserve(budget)


def test_committed_reservation_survives_process_exit(tmp_path):
    import subprocess
    import sys
    budget = ledger(tmp_path)
    key, parent = str(uuid4()), str(uuid4())
    code = "from backend.meta_budget import MetaBudget; import os,sys; MetaBudget(sys.argv[1]).reserve(sys.argv[2],sys.argv[3],250000,price_version=sys.argv[4]); os._exit(0)"
    subprocess.run([sys.executable,"-c",code,budget.path,key,parent,PRICE],check=True)
    assert MetaBudget(budget.path).snapshot()["exposure_micro_usd"] == 250_000
    with pytest.raises(BudgetDenied): reserve(budget,attempt=key,parent=parent)
