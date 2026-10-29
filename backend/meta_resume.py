"""Reviewed recovery of a frozen account after every charge is reconciled.

A freeze is lifted only by `resume_account`, an operator command with no HTTP
route. It requires that every attempt in the ledger is settled with recorded
invoice finality, that the reviewers name each reconciled attempt with its
provider ID and final charge, fresh current account evidence that accounts for
those charges, and both developers' review plus a new spending approval.

It changes exactly one row (the account's evidence, anchor and freeze flag) and
appends one audit event that keeps the previous evidence verbatim. Attempts,
finalities, permits, notices and earlier events are never modified, so spent
permits stay spent and recorded spending is never reset.
"""
from datetime import datetime, timedelta
import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator

from .meta_accounts import FINANCIAL_DDL, USD, AccountLedger, Evidence, InvoiceFinality, _canonical_schema, now, stamp
from .meta_budget import BudgetDenied
from .wonder_experiment import LIVE_SCHEMA

RESUME_VERSION = "account-resume-v1"
CUTOFF = 120 * USD
MAX_APPROVAL_HOURS = 24
Reference = Annotated[str, Field(strict=True, min_length=1, max_length=500)]
AttemptId = Annotated[str, Field(strict=True, pattern=r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")]


class ReconciledAttempt(BaseModel):
    """What the reviewers checked against the provider's final invoice."""
    model_config = ConfigDict(extra="forbid", strict=True)
    attempt_id: AttemptId
    provider_id: str = Field(strict=True, pattern=r"^resp_[A-Za-z0-9_-]{1,180}$")
    final_gross_micro_usd: StrictInt = Field(ge=0, le=9_000_000_000_000_000)


class ResumeApproval(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: Literal["account-resume-v1"]
    account_id: Literal["georgiosaliba227", "aminealichaouche"]
    reconciled_attempts: list[ReconciledAttempt] = Field(max_length=1000)
    overrun_acknowledged: StrictBool = False
    new_key_acknowledged: StrictBool = False
    provider_reconciliation_reference: Reference
    spending_approval_reference: Reference
    georgio_review_reference: Reference
    amine_review_reference: Reference
    reason: Reference
    valid_until: datetime

    @field_validator("*", mode="after")
    @classmethod
    def meaningful(cls, value, info):
        if info.field_name.endswith(("reference", "reason")) and not value.strip():
            raise ValueError("Meaningful reference required")
        return value

    @model_validator(mode="after")
    def current(self):
        if (self.valid_until.tzinfo is None or self.valid_until <= now()
                or self.valid_until > now() + timedelta(hours=MAX_APPROVAL_HOURS)):
            raise ValueError("A current approval valid for at most 24 hours is required")
        if len({item.attempt_id for item in self.reconciled_attempts}) != len(self.reconciled_attempts):
            raise ValueError("Each attempt is named once")
        return self


def _verify_schema(db) -> None:
    if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise BudgetDenied("Ledger integrity check failed")
    objects = {row[0]: row[1] for row in db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'")}
    for name, sql in FINANCIAL_DDL.items():
        if name not in objects or _canonical_schema(objects[name] or "") != _canonical_schema(sql):
            raise BudgetDenied("Finality-current financial schema required")
    # Only the reviewed experiment immutability triggers may exist; any other could rewrite history.
    reviewed = {_canonical_schema(sql) for sql in LIVE_SCHEMA if sql.split()[1] == "TRIGGER"}
    for (sql,) in db.execute("SELECT sql FROM sqlite_master WHERE type='trigger'"):
        if _canonical_schema(sql or "") not in reviewed:
            raise BudgetDenied("Unknown trigger in the financial ledger")


def _blockers(db, approval: ResumeApproval, evidence: Evidence) -> list[str]:
    """Every reason the resume must not happen; empty means it may proceed."""
    account = approval.account_id
    problems = []
    row = db.execute("SELECT evidence,anchor_gross,frozen FROM live_accounts WHERE account_id=?", (account,)).fetchone()
    if not row:
        return ["account_not_attested"]
    if row[2] != 1:
        problems.append("account_not_frozen")
    previous = json.loads(row[0])
    if evidence.account_id != account:
        problems.append("evidence_for_another_account")
    if evidence.provider_account_reference != previous.get("provider_account_reference"):
        problems.append("evidence_names_another_provider_account")
    if evidence.key_sha256 != previous.get("key_sha256") and not approval.new_key_acknowledged:
        problems.append("key_changed_not_acknowledged")
    # A resume must not reactivate an unspent first-test or controlled permit.
    if (db.execute("SELECT 1 FROM live_permit WHERE spent=0").fetchone()
            or db.execute("SELECT 1 FROM controlled_permits WHERE spent=0").fetchone()):
        problems.append("unspent_permit_would_reactivate")
    for (other,) in db.execute("SELECT evidence FROM live_accounts WHERE account_id!=?", (account,)):
        if json.loads(other).get("key_sha256") == evidence.key_sha256:
            problems.append("key_belongs_to_another_account")
    attempts = db.execute("SELECT a.id,a.account_id,a.provider_id,a.actual,a.reserved,a.state,a.dispatched_at,f.evidence "
                          "FROM live_attempts a LEFT JOIN live_finalities f ON f.attempt_id=a.id").fetchall()
    recorded, overrun = {}, False
    for attempt, owner, provider, actual, reserved, state, dispatched, raw in attempts:
        try:
            finality = InvoiceFinality.model_validate_json(raw)
            if (state != "settled" or actual is None or dispatched is None or finality.attempt_id != attempt
                    or finality.account_id != owner or finality.provider_id != provider
                    or finality.final_gross_micro_usd != actual
                    or finality.finalized_at < datetime.fromisoformat(dispatched)):
                raise ValueError
        except (ValueError, TypeError):
            problems.append(f"attempt_not_finalized:{attempt}")
            continue
        if owner == account:
            recorded[attempt] = (provider, actual)
            overrun = overrun or actual > reserved
    named = {item.attempt_id: (item.provider_id, item.final_gross_micro_usd) for item in approval.reconciled_attempts}
    if named != recorded:
        problems.append("reconciled_attempts_do_not_match_ledger")
    if overrun and not approval.overrun_acknowledged:
        problems.append("overrun_not_acknowledged")
    if db.execute("SELECT 1 FROM live_notices WHERE delivered_at IS NULL").fetchone():
        problems.append("undelivered_notices")
    # Fresh provider gross must include everything this ledger already recorded.
    floor = row[1] + sum(actual for _, actual in recorded.values())
    if evidence.gross_micro_usd < floor:
        problems.append("evidence_gross_below_recorded_spending")
    # Recorded attempts are counted again on top of the new anchor: conservative, never under-counted.
    exposure = evidence.gross_micro_usd + sum(actual for _, actual in recorded.values())
    if exposure >= CUTOFF:
        problems.append("account_at_operational_cutoff")
    return problems


def _parse(approval: ResumeApproval, evidence: Evidence) -> tuple[ResumeApproval, Evidence]:
    # Re-validate inside the lock: approvals and evidence can expire while waiting.
    return ResumeApproval.model_validate(approval.model_dump()), Evidence.model_validate(evidence.model_dump())


def preview_resume(ledger: AccountLedger, approval: ResumeApproval, evidence: Evidence) -> dict:
    """Read-only: what would block this exact resume. Changes nothing."""
    with ledger._existing_migration_database(write=False) as db:
        _verify_schema(db)
        approval, evidence = _parse(approval, evidence)
        problems = _blockers(db, approval, evidence)
    return {"version": RESUME_VERSION, "account_id": approval.account_id, "would_resume": not problems,
            "blockers": problems, "ledger_changed": False}


def resume_account(ledger: AccountLedger, approval: ResumeApproval, evidence: Evidence) -> dict:
    """Lift one account's freeze after full reconciliation; atomic, one audit event, no history changes."""
    with ledger._existing_migration_database(write=True) as db:
        _verify_schema(db)
        approval, evidence = _parse(approval, evidence)
        problems = _blockers(db, approval, evidence)
        if problems:
            refused = problems  # Nothing was written; the read transaction rolls back unchanged.
        else:
            refused = None
            _apply(ledger, db, approval, evidence)
    if refused:
        raise BudgetDenied("Resume refused: " + ", ".join(refused))
    return {"version": RESUME_VERSION, "account_id": approval.account_id, "resumed": True,
            "anchor_gross_micro_usd": evidence.gross_micro_usd, "reconciled_attempts": len(approval.reconciled_attempts),
            "permits_changed": False, "history_changed": False}


def _apply(ledger: AccountLedger, db, approval: ResumeApproval, evidence: Evidence) -> None:
    account = approval.account_id
    previous = db.execute("SELECT evidence,anchor_gross FROM live_accounts WHERE account_id=?", (account,)).fetchone()
    raw = evidence.model_dump_json()
    changed = db.execute("UPDATE live_accounts SET evidence=?,anchor_gross=?,frozen=0 WHERE account_id=? AND frozen=1",
                         (raw, evidence.gross_micro_usd, account)).rowcount
    if changed != 1:
        raise BudgetDenied("Resume refused: account_not_frozen")
    record = {"version": RESUME_VERSION, "approval": json.loads(approval.model_dump_json()),
              "previous_evidence": previous[0], "previous_anchor_gross_micro_usd": previous[1],
              "new_evidence_sha256": hashlib.sha256(raw.encode()).hexdigest(), "resumed_at": stamp()}
    ledger.event(db, account, "account_resumed", json.dumps(record, sort_keys=True))
    recorded = sum(item.final_gross_micro_usd for item in approval.reconciled_attempts)
    ledger.queue_threshold_notices(db, account, evidence.gross_micro_usd + recorded)

