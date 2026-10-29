"""Georgio's recovery after PR #14's camera request, end to end on synthetic data. No network.

camera request (billing_pending, frozen) -> reconcile-risk-invoice -> resume template/preview/resume
-> Wonder schema -> $30 allocation with the standing synthetic approval -> one synthetic case.
"""
from datetime import datetime, timedelta, timezone
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.meta_accounts import ACCOUNTS, InvoiceFinality
from backend.meta_budget import BudgetDenied
from backend.meta_resume import ResumeApproval, approval_template, preview_resume, resume_account
from backend.recognition import RecognitionUnavailable
from backend.wonder_experiment import WonderExperimentLedger
from test_controlled_tests import permit as controlled_permit
from test_first_camera_risk import gateway, image, no_network, risk_permit, setup_risk  # noqa: F401 (fixtures)
from test_guarded_meta import HASH, evidence
from test_meta_experiments import approval, quote
from test_wonder_live import LIVE, OWNER, OWNER_AUTH, env, fake_live  # noqa: F401 (fixture)
from test_wonder_experiment import WONDER, FakeWonderTransport, selection_reply

GEORGIO = ACCOUNTS[0]
FINAL = 1_500  # micro-USD on the synthetic final invoice


def rows(ledger, sql, *args):
    with ledger.transaction() as db:
        return db.execute(sql, args).fetchall()


def camera_request(setup_risk):
    ledger, risk = setup_risk()
    attempt = gateway(ledger).analyze(image()).recognition_id
    return ledger, risk, attempt


def finality_from(template, final=FINAL):
    [skeleton] = template["_ledger_notes"]["reconcile_first"]["finality_files"]
    return InvoiceFinality.model_validate(skeleton | {
        "final_gross_micro_usd": final, "finalized_at": datetime.now(timezone.utc),
        "provider_evidence_reference": "synthetic-final-invoice", "georgio_review_reference": "synthetic-g",
        "amine_review_reference": "synthetic-a"})


def filled(template):
    values = {k: ("synthetic-" + k if isinstance(v, str) and v.startswith("REQUIRED") else v)
              for k, v in template.items() if k != "_ledger_notes"}
    return ResumeApproval.model_validate(values | {"valid_until": datetime.now(timezone.utc) + timedelta(hours=1)})


def fresh(risk, gross):
    return evidence(GEORGIO, gross).model_copy(update={"provider_account_reference": risk.provider_account_reference,
                                                       "key_sha256": risk.key_sha256})


def test_billing_pending_camera_attempt_must_be_reconciled_before_resume(setup_risk):
    ledger, risk, attempt = camera_request(setup_risk)
    template = approval_template(ledger, GEORGIO)
    assert template["reconciled_attempts"][0]["final_gross_micro_usd"] is None
    notes = template["_ledger_notes"]
    assert notes["attempt_states"] == {attempt: "billing_pending"}
    assert "reconcile-risk-invoice" in notes["reconcile_first"]["command"]
    assert notes["reconcile_first"]["finality_files"][0]["provider_id"] == "resp_testonly"
    approval_now = filled(template | {"reconciled_attempts": [
        {"attempt_id": attempt, "provider_id": "resp_testonly", "final_gross_micro_usd": FINAL}]})
    assert f"attempt_not_finalized:{attempt}" in preview_resume(ledger, approval_now, fresh(risk, FINAL))["blockers"]
    with pytest.raises(BudgetDenied):  # the ordinary finality path refuses a frozen project
        ledger.record_invoice_finality(finality_from(template))


def test_full_recovery_then_one_synthetic_case_runs(setup_risk, env, tmp_path):
    ledger, risk, attempt = camera_request(setup_risk)
    ledger.reconcile_risk_invoice(finality_from(approval_template(ledger, GEORGIO)))
    template = approval_template(ledger, GEORGIO)
    assert "reconcile_first" not in template["_ledger_notes"]
    assert template["reconciled_attempts"] == [{"attempt_id": attempt, "provider_id": "resp_testonly",
                                                "final_gross_micro_usd": FINAL}]
    assert template["overrun_acknowledged"] is False
    current = fresh(risk, risk.gross_micro_usd + FINAL)
    assert preview_resume(ledger, filled(template), current)["would_resume"]
    resume_account(ledger, filled(template), current)

    # The one-time camera permit stays spent; no first, dual or risk test can be approved again.
    assert rows(ledger, "SELECT spent FROM controlled_permits") == [(1,)]
    with pytest.raises(BudgetDenied):
        ledger.approve_risk_test(risk_permit(risk))
    with pytest.raises(BudgetDenied):
        ledger.approve_controlled_test(controlled_permit(GEORGIO, HASH))
    with pytest.raises(RecognitionUnavailable):
        gateway(ledger).analyze(image())

    wonder = WonderExperimentLedger(ledger)
    assert wonder.migrate_live_schema(review_reference="synthetic-schema-review")["status"] == "migrated"
    wonder.record_approval(approval(key_sha256=risk.key_sha256, synthetic_dispatch_reference="synthetic-standing"))
    monkeypatch, _ = env
    quote_file = tmp_path / "quote.json"
    quote_file.write_text(quote(WONDER).model_dump_json())
    results = tmp_path / "results"
    results.mkdir(mode=0o700)
    for name, value in {"META_BILLABLE_REQUESTS_ENABLED": "true", "HYDRA_WONDER_LIVE": "true",
                        "HYDRA_WONDER_ACCOUNT": GEORGIO, "HYDRA_WONDER_LEDGER": str(ledger.path),
                        "HYDRA_WONDER_QUOTE": str(quote_file), "HYDRA_WONDER_RESULTS_DIR": str(results),
                        "HYDRA_META_GEORGIO_API_KEY": "synthetic-key",
                        "HYDRA_GITHUB_NOTIFICATION_TOKEN": "synthetic-notify-token"}.items():
        monkeypatch.setenv(name, value)
    app = create_app(tmp_path / "data.sqlite3", OWNER)
    with TestClient(app) as client:
        transport = FakeWonderTransport(selection_reply())
        fake_live(app, wonder, transport)
        response = client.post("/v1/wonder/live", json=LIVE, headers=OWNER_AUTH).json()
        assert (response["replayed"], transport.calls) == (False, 1)
        assert response["result"]["provenance"]["account_id"] == GEORGIO
        assert wonder.snapshot()["hard_limit_micro_usd"] == 30_000_000


def test_an_invoice_above_the_reservation_must_be_acknowledged(setup_risk):
    ledger, risk, attempt = camera_request(setup_risk)
    reserved = rows(ledger, "SELECT reserved FROM live_attempts")[0][0]
    ledger.reconcile_risk_invoice(finality_from(approval_template(ledger, GEORGIO), reserved + 1))
    template = approval_template(ledger, GEORGIO)
    assert template["overrun_acknowledged"] is True  # prefilled from the ledger; reviewers confirm it
    current = fresh(risk, risk.gross_micro_usd + reserved + 1)
    unacknowledged = filled(template | {"overrun_acknowledged": False})
    assert preview_resume(ledger, unacknowledged, current)["blockers"] == ["overrun_not_acknowledged"]
    assert preview_resume(ledger, filled(template), current)["would_resume"]


def test_operator_commands_reconcile_from_a_private_file(setup_risk, tmp_path, monkeypatch, capsys):
    import scripts.meta_account_resume as resume_tool
    import scripts.meta_budget_admin as admin
    ledger, risk, attempt = camera_request(setup_risk)
    resume_tool.main(["template", "--database", str(ledger.path)])
    template = json.loads(capsys.readouterr().out)
    finality = tmp_path / "finality.json"
    finality.write_text(finality_from(template).model_dump_json())
    os.chmod(finality, 0o600)
    monkeypatch.setattr(sys, "argv", ["meta_budget_admin", "--database", str(ledger.path),
                                      "--evidence-file", str(finality), "reconcile-risk-invoice"])
    admin.main()
    admin.main()  # an identical retry changes nothing
    assert rows(ledger, "SELECT state,actual FROM live_attempts") == [("settled", FINAL)]
    assert len(rows(ledger, "SELECT 1 FROM live_finalities")) == 1
    finality.write_text(finality_from(template, FINAL + 1).model_dump_json())
    with pytest.raises(BudgetDenied):  # recorded finality is immutable
        admin.main()
    assert rows(ledger, "SELECT actual FROM live_attempts") == [(FINAL,)]
