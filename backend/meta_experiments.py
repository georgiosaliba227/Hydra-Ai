"""Inert V2 experiment accounting in the SAME AccountLedger authority.

No migration executor, initialization, HTTP route, provider, dispatch, settlement
or activation API. Proposed DDL is installed only by disposable tests this phase.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import json
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from .meta_accounts import AccountLedger, Evidence, CAP, USD, now, stamp, FINANCIAL_DDL, _canonical_schema
from .meta_budget import BudgetDenied

ALLOCATION_ID = "hydration-v2-georgio-30usd"
ACCOUNT = "georgiosaliba227"
HARD_LIMIT = 30 * USD
SOFT_TARGETS = {"muse-spark-1.3": 20 * USD, "muse-wonder-1.0": 10 * USD}
REFERENCE_PRICES = {"muse-spark-1.3": (1_250_000, 4_250_000), "muse-wonder-1.0": (4_000_000, 20_000_000)}
Model = Literal["muse-spark-1.3", "muse-wonder-1.0"]
AccountId = Literal["georgiosaliba227", "aminealichaouche"]


@dataclass(frozen=True)
class Allocation:
    allocation_id: str
    hard_limit: int
    soft_targets: dict[str, int]
    cutoff: int  # A reservation taking the account's gross exposure to this amount is refused.


# Reviewed per-account limits. Georgio: $30 experiment within the $120 cutoff.
# Amine (2026-10-29): $100 of his reported $150, so his account stops at $100.
ALLOCATIONS = {
    ACCOUNT: Allocation(ALLOCATION_ID, HARD_LIMIT, dict(SOFT_TARGETS), 120 * USD),
    "aminealichaouche": Allocation("wonder-amine-100usd", 100 * USD,
                                   {"muse-spark-1.3": 0, "muse-wonder-1.0": 100 * USD}, 100 * USD),
}
Reference = Annotated[str, Field(strict=True, min_length=1, max_length=500)]
Fingerprint = Annotated[str, Field(strict=True, pattern=r"^[a-f0-9]{64}$")]

# Proposal only: no production method executes these statements.
PROPOSED_SCHEMA = (
    "CREATE TABLE experiment_allocation(id INTEGER PRIMARY KEY CHECK(id=1), approval TEXT NOT NULL)",
    "CREATE TABLE experiment_attempts(attempt_id TEXT PRIMARY KEY, allocation_id INTEGER NOT NULL CHECK(allocation_id=1), case_id TEXT NOT NULL, model TEXT NOT NULL CHECK(model IN ('muse-spark-1.3','muse-wonder-1.0')), payload_sha256 TEXT NOT NULL, retry_of TEXT, request TEXT NOT NULL)",
    "CREATE TRIGGER experiment_allocation_no_update BEFORE UPDATE ON experiment_allocation BEGIN SELECT RAISE(ABORT,'immutable allocation'); END",
    "CREATE TRIGGER experiment_allocation_no_delete BEFORE DELETE ON experiment_allocation BEGIN SELECT RAISE(ABORT,'immutable allocation'); END",
    "CREATE TRIGGER experiment_attempts_no_update BEFORE UPDATE ON experiment_attempts BEGIN SELECT RAISE(ABORT,'immutable experiment history'); END",
    "CREATE TRIGGER experiment_attempts_no_delete BEFORE DELETE ON experiment_attempts BEGIN SELECT RAISE(ABORT,'immutable experiment history'); END",
)


class StrictDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("valid_until", check_fields=False)
    @classmethod
    def current(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value <= now():
            raise ValueError("Current timezone-aware reviewed evidence required")
        return value

    @field_validator("*", mode="after")
    @classmethod
    def no_blank_references(cls, value, info):
        if info.field_name.endswith("reference") and value is not None and not value.strip():
            raise ValueError("Meaningful evidence reference required")
        return value


class ExperimentApproval(StrictDescriptor):
    allocation_id: Reference = ALLOCATION_ID
    account_id: AccountId = ACCOUNT
    hard_limit_micro_usd: StrictInt = HARD_LIMIT
    spark_soft_target_micro_usd: StrictInt = 20 * USD
    wonder_soft_target_micro_usd: StrictInt = 10 * USD
    key_sha256: Fingerprint
    valid_until: datetime
    owner_authorization_reference: Reference
    spending_authority_reference: Reference
    policy_transition_reference: Reference
    georgio_review_reference: Reference
    amine_review_reference: Reference
    further_spend_approval_reference: Reference | None = None
    # Standing approval for Wonder trend explanations of the owner's own data;
    # each request is then bound to the exact payload the user saw and consented to.
    trend_dispatch_reference: Reference | None = None
    # Standing approval for the fixed, server-built synthetic Wonder payloads (scenarios and
    # suggested questions); each is sent at most once, so total spend is bounded and counted.
    synthetic_dispatch_reference: Reference | None = None

    @model_validator(mode="after")
    def reviewed_allocation(self):
        allocation = ALLOCATIONS[self.account_id]
        if (self.allocation_id, self.hard_limit_micro_usd, self.spark_soft_target_micro_usd,
                self.wonder_soft_target_micro_usd) != (allocation.allocation_id, allocation.hard_limit,
                                                       allocation.soft_targets["muse-spark-1.3"],
                                                       allocation.soft_targets["muse-wonder-1.0"]):
            raise ValueError("Allocation does not match the reviewed account limits")
        return self


class ExperimentQuote(StrictDescriptor):
    account_id: AccountId = ACCOUNT
    model: Model
    tier: Literal["Standard"] = "Standard"
    version: Annotated[str, Field(strict=True, min_length=1, max_length=100)]
    source: Literal["https://dev.meta.ai/docs/pricing-rate-limits"] = "https://dev.meta.ai/docs/pricing-rate-limits"
    valid_until: datetime
    input_micro_per_million: StrictInt = Field(gt=0)
    output_micro_per_million: StrictInt = Field(gt=0)
    extra_charge_bound_micro_usd: StrictInt = Field(ge=0, le=CAP)
    all_charge_categories_verified: Literal[True]
    model_access_verified: Literal[True]
    reference: Reference
    model_access_reference: Reference
    all_charge_bound_reference: Reference

    @field_validator("all_charge_categories_verified", "model_access_verified", mode="before")
    @classmethod
    def explicit_true(cls, value):
        if value is not True:
            raise ValueError("Independent verified evidence required")
        return True

    @model_validator(mode="after")
    def reviewed_reference_prices(self):
        if (self.input_micro_per_million, self.output_micro_per_million) != REFERENCE_PRICES[self.model]:
            raise ValueError("Unknown price snapshot; separate review required")
        if not self.version.strip():
            raise ValueError("Meaningful price version required")
        return self

    def bound(self, inputs: int, outputs: int) -> int:
        # No cache discount, credit offset or assumed-zero extra category.
        total = inputs * self.input_micro_per_million + outputs * self.output_micro_per_million
        return (total + 999_999) // 1_000_000 + self.extra_charge_bound_micro_usd


class ExperimentRequest(StrictDescriptor):
    attempt_id: str
    case_id: str
    payload_sha256: Fingerprint
    input_bound: StrictInt = Field(ge=1, le=1_000_000)
    output_bound: StrictInt = Field(ge=1, le=512)
    maximum_micro_usd: StrictInt = Field(ge=1, le=CAP)
    input_approval_reference: Reference
    quote: ExperimentQuote
    retry_of: str | None = None
    retry_approval_reference: Reference | None = None

    @field_validator("attempt_id", "case_id", "retry_of")
    @classmethod
    def canonical_uuid(cls, value):
        if value is not None and str(UUID(value)) != value:
            raise ValueError("Canonical UUID required")
        return value

    @model_validator(mode="after")
    def retry_authorized(self):
        if (self.retry_of is None) != (self.retry_approval_reference is None):
            raise ValueError("Retry requires explicit ancestry and approval")
        return self


class ExperimentBudget:
    """Review-only reservations; never returns a network-capable ticket."""
    SCHEMA = PROPOSED_SCHEMA  # Subclasses may require additional reviewed DDL.

    def __init__(self, authority: AccountLedger) -> None:
        if type(authority) is not AccountLedger:
            raise BudgetDenied("Existing AccountLedger authority required")
        self.authority = authority

    @contextmanager
    def _transaction(self, *, write: bool = True):
        # Existing-only handle with identity/private-file checks and atomic
        # BEGIN IMMEDIATE; unlike sqlite's default open, cannot create a DB.
        with self.authority._existing_migration_database(write=write) as db:
            if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise BudgetDenied("Ledger integrity verification failed")
            expected = dict(FINANCIAL_DDL)
            expected.update({sql.split()[2].split("(")[0]:sql for sql in self.SCHEMA})
            objects = {row[0]:(row[1],row[2],row[3]) for row in db.execute("SELECT name,type,tbl_name,sql FROM sqlite_master")}
            for name,sql in expected.items():
                row = objects.get(name)
                if not row or row[2] is None or _canonical_schema(row[2]) != _canonical_schema(sql):
                    raise BudgetDenied("Reviewed financial and immutable experiment schema required")
            for name,(kind,table,sql) in objects.items():
                if kind == "trigger" and table in expected and name not in expected:
                    raise BudgetDenied("Unknown financial side effect rejected")
            yield db

    def _evidence(self, db, approval: ExperimentApproval) -> Evidence:
        self.authority.verify_project_unfrozen(db)
        account = approval.account_id
        row = db.execute("SELECT evidence,anchor_gross FROM live_accounts WHERE account_id=?", (account,)).fetchone()
        if not row:
            raise BudgetDenied("Verified account evidence required")
        try:
            evidence = Evidence.model_validate_json(row[0])
            if evidence.account_id != account or evidence.key_sha256 != approval.key_sha256 or row[1] != evidence.gross_micro_usd:
                raise ValueError
        except (ValueError, TypeError):
            raise BudgetDenied("Account identity, credential or current evidence unavailable") from None
        return evidence

    def record_approval(self, approval: ExperimentApproval) -> None:
        approval = ExperimentApproval.model_validate(approval.model_dump())
        with self._transaction() as db:
            approval = ExperimentApproval.model_validate(approval.model_dump())
            self._evidence(db, approval)
            self.authority.verify_prior_finalities(db)
            # Unused standing approvals are left out, keeping the byte layout of allocations recorded before them.
            raw = approval.model_dump_json(exclude={name for name in ("trend_dispatch_reference", "synthetic_dispatch_reference")
                                                    if getattr(approval, name) is None})
            existing = db.execute("SELECT approval FROM experiment_allocation WHERE id=1").fetchone()
            if existing:
                if existing[0] == raw:
                    return
                raise BudgetDenied("One immutable project allocation; no replacement or reset")
            db.execute("INSERT INTO experiment_allocation(id,approval) VALUES(1,?)", (raw,))
            self.authority.event(db, approval.account_id, "experiment_review_only_allocation", approval.allocation_id)

    @staticmethod
    def _allocation(db) -> ExperimentApproval:
        """The one immutable allocation in this ledger; it names the only account it may charge."""
        row = db.execute("SELECT approval FROM experiment_allocation WHERE id=1").fetchone()
        if not row:
            raise BudgetDenied("Immutable reviewed allocation missing")
        try:
            return ExperimentApproval.model_validate_json(row[0])
        except ValueError:
            raise BudgetDenied("Allocation expired or invalid") from None

    @staticmethod
    def _exposure(db, account: str) -> tuple[int, dict[str, int]]:
        totals = {model: 0 for model in SOFT_TARGETS}
        rows = db.execute("SELECT e.attempt_id,e.model,a.account_id,a.reserved,a.actual,e.request,e.case_id,e.payload_sha256,e.retry_of,a.price,a.input_bound,a.payload_sha256 FROM experiment_attempts e LEFT JOIN live_attempts a ON a.id=e.attempt_id")
        for attempt, model, attempt_account, reserved, actual, raw, case_id, payload, retry_of, price, input_bound, attempt_payload in rows:
            if (attempt_account != account or model not in totals or type(reserved) is not int or reserved <= 0
                    or (actual is not None and (type(actual) is not int or actual < 0))):
                raise BudgetDenied("Experiment financial linkage unavailable or corrupt")
            try:
                original = json.loads(raw)
                if (original["attempt_id"] != attempt or original["case_id"] != case_id
                        or original["payload_sha256"] != payload or payload != attempt_payload
                        or original["retry_of"] != retry_of or original["input_bound"] != input_bound
                        or original["quote"]["model"] != model or original["quote"] != json.loads(price)
                        or type(original["maximum_micro_usd"]) is not int
                        or original["maximum_micro_usd"] != reserved or not 1 <= reserved <= CAP):
                    raise ValueError
            except (KeyError,ValueError,TypeError):
                raise BudgetDenied("Immutable reservation evidence mismatch") from None
            totals[model] += max(reserved, actual or 0)
        if db.execute("SELECT 1 FROM live_attempts a LEFT JOIN experiment_attempts e ON e.attempt_id=a.id WHERE a.state='experiment_review_only' AND e.attempt_id IS NULL").fetchone():
            raise BudgetDenied("Unattributed experiment reservation")
        return sum(totals.values()), totals

    @staticmethod
    def _acknowledged_overruns(db, account: str) -> dict[str, int]:
        """Attempts whose final charge a reviewed resume acknowledged as above their reservation."""
        acknowledged = {}
        for (raw,) in db.execute("SELECT reference FROM live_events WHERE kind='account_resumed' AND account_id=?", (account,)):
            try:
                approval = json.loads(raw)["approval"]
                if approval["overrun_acknowledged"] is True and approval["account_id"] == account:
                    acknowledged |= {item["attempt_id"]: item["final_gross_micro_usd"] for item in approval["reconciled_attempts"]}
            except (ValueError, KeyError, TypeError):
                raise BudgetDenied("Unreadable resume record") from None
        return acknowledged

    def reserve_review_only(self, request: ExperimentRequest) -> dict:
        return self._reserve(request, "experiment_review_only")

    def _check_case(self, db, request: ExperimentRequest) -> None:
        """Hook for subclasses that admit only approved manifest cases."""

    def _reserve(self, request: ExperimentRequest, state: str) -> dict:
        request = ExperimentRequest.model_validate(request.model_dump())
        with self._transaction() as db:
            # Evidence can expire while waiting for the authoritative write lock.
            request = ExperimentRequest.model_validate(request.model_dump())
            approval = self._allocation(db)
            account, allocation = approval.account_id, ALLOCATIONS[approval.account_id]
            if request.quote.account_id != account:
                raise BudgetDenied("Quote is for another account; no account switching")
            evidence = self._evidence(db, approval)
            self.authority.verify_prior_finalities(db)
            self._check_case(db, request)
            if db.execute("SELECT 1 FROM live_notices WHERE delivered_at IS NULL").fetchone():
                raise BudgetDenied("Both developers must receive pending notices")
            if db.execute("SELECT 1 FROM live_attempts WHERE actual IS NULL").fetchone():
                raise BudgetDenied("Prior billing unresolved; no new attempt")
            if request.quote.bound(request.input_bound, request.output_bound) > request.maximum_micro_usd:
                raise BudgetDenied("All-inclusive verified quote exceeds request ceiling")
            if db.execute("SELECT 1 FROM live_attempts WHERE id=?", (request.attempt_id,)).fetchone():
                raise BudgetDenied("Attempt cannot be replayed")
            case_rows = db.execute("SELECT attempt_id,model,payload_sha256 FROM experiment_attempts WHERE case_id=?", (request.case_id,)).fetchall()
            if case_rows:
                if (len(case_rows) >= 2 or request.retry_of is None or not request.retry_approval_reference
                        or case_rows[0] != (request.retry_of, request.quote.model, request.payload_sha256)):
                    raise BudgetDenied("Case replay or unapproved retry")
            elif request.retry_of is not None:
                raise BudgetDenied("Retry ancestor must belong to the same case")
            aggregate, totals = self._exposure(db, account)
            if aggregate + request.maximum_micro_usd > allocation.hard_limit:
                raise BudgetDenied("Aggregate experimental allocation exhausted")
            account_spend = 0
            acknowledged = self._acknowledged_overruns(db, account)
            for attempt_id,reserved,actual in db.execute("SELECT id,reserved,actual FROM live_attempts WHERE account_id=?", (account,)):
                if (type(reserved) is not int or reserved <= 0 or type(actual) is not int or actual < 0
                        or (actual > reserved and acknowledged.get(attempt_id) != actual)):
                    raise BudgetDenied("Corrupt or over-bound account history requires reconciliation")
                account_spend += actual
            proposed = evidence.gross_micro_usd + account_spend + request.maximum_micro_usd
            if proposed >= 150 * USD or proposed >= allocation.cutoff:
                raise BudgetDenied("Account operational cutoff reached")
            if proposed >= 100 * USD and not approval.further_spend_approval_reference:
                raise BudgetDenied("Account-specific further-spend approval required")
            if account_spend + request.maximum_micro_usd > evidence.credits_remaining_micro_usd:
                raise BudgetDenied("Verified available account credits insufficient")
            db.execute("INSERT INTO live_attempts(id,account_id,price,reserved,state,input_bound,created_at,payload_sha256) VALUES(?,?,?,?,?,?,?,?)",
                       (request.attempt_id,account,request.quote.model_dump_json(),request.maximum_micro_usd,
                        state,request.input_bound,stamp(),request.payload_sha256))
            db.execute("INSERT INTO experiment_attempts(attempt_id,allocation_id,case_id,model,payload_sha256,retry_of,request) VALUES(?,1,?,?,?,?,?)",
                       (request.attempt_id,request.case_id,request.quote.model,request.payload_sha256,request.retry_of,request.model_dump_json()))
            self.authority.event(db, account, "experiment_review_only_reserved", request.attempt_id)
            self.authority.queue_threshold_notices(db, account, proposed)
            totals[request.quote.model] += request.maximum_micro_usd
            return self._view(aggregate + request.maximum_micro_usd, totals, account)

    @staticmethod
    def _view(aggregate: int, totals: dict[str, int], account: str) -> dict:
        allocation = ALLOCATIONS[account]
        return {"allocation_id": allocation.allocation_id, "account_id": account, "dispatch_enabled": False,
                "state": "review_only_no_live_adapter", "hard_limit_micro_usd": allocation.hard_limit,
                "account_cutoff_micro_usd": allocation.cutoff,
                "aggregate_exposure_micro_usd": aggregate, "remaining_micro_usd": max(0, allocation.hard_limit - aggregate),
                "model_exposure_micro_usd": totals, "soft_model_targets_micro_usd": dict(allocation.soft_targets),
                "soft_target_exceeded": [model for model in totals if totals[model] > allocation.soft_targets[model]],
                "credits_offset_gross": False, "reservation_replenishment": False}

    def snapshot(self) -> dict:
        with self._transaction(write=False) as db:
            if not db.execute("SELECT 1 FROM experiment_allocation WHERE id=1").fetchone():
                raise BudgetDenied("Reviewed allocation missing")
            # Reporting still works after the approval expires; only admission needs it current.
            account = json.loads(db.execute("SELECT approval FROM experiment_allocation WHERE id=1").fetchone()[0])["account_id"]
            if account not in ALLOCATIONS:
                raise BudgetDenied("Allocation names an unknown account")
            return self._view(*self._exposure(db, account), account)
