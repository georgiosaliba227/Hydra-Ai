"""Truthful owner-accepted uncertainty, beside unchanged verified admission.

An incomplete draft is useful for readiness but grants no permission. Financial
rows contain bounded metadata only; unknown provider extras never become zero.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from sqlite3 import Connection
from typing import Annotated, Any, Iterator, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator

from .meta_accounts import AccountLedger, InvoiceFinality, stamp
from .meta_budget import BudgetDenied
from .meta_provider import ProviderReply, strict_json
from .recognition import RecognitionUnavailable
from .wonder_owner_once import _schema

ACCOUNT = "georgiosaliba227"
MODEL = "muse-wonder-1.0"
POLICY = "owner-personal-wonder-v1"
RESERVATION = 250_000
AUTH_EVENT = "wonder_personal_owner_authorized"
BIND_EVENT = "wonder_personal_owner_reserved"
FAIL_EVENT = "wonder_personal_owner_failure"
TRAINING_EVENT = "wonder_personal_owner_training_plan_validated"
OUTPUT_EVENT = "wonder_personal_owner_output_validated"
PUBLISHED_EVENT = "wonder_personal_owner_result_published"
PURPOSES = frozenset(("personal_trends", "personal_workout", "personal_analysis", "personal_home_score", "synthetic_training_plan"))
REASONS = ("owner_policy_not_recorded", "owner_policy_invalid", "quote_expired", "account_observation_stale",
    "cross_ledger_status_unverified", "notification_delivery_unverified", "current_invoice_finality_required",
    "request_in_flight", "financial_failure_requires_review", "budget_exhausted", "storage_unavailable")
Fingerprint = Annotated[str, Field(strict=True, pattern=r"^[a-f0-9]{64}$")]
Reference = Annotated[str, Field(strict=True, min_length=1, max_length=500)]


def now() -> datetime:
    return datetime.now(timezone.utc)


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def meaningful(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 500


def fresh(value: datetime | None, *, minutes: int = 60) -> bool:
    return value is not None and value.tzinfo is not None and now() - timedelta(minutes=minutes) <= value <= now()


class Descriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class LegacyAttemptBinding(Descriptor):
    attempt_id: str
    identity_sha256: Fingerprint

    @field_validator("attempt_id")
    @classmethod
    def uuid(cls, value: str) -> str:
        if str(UUID(value)) != value:
            raise ValueError("Canonical attempt identifier required")
        return value


class OwnerPersonalPolicy(Descriptor):
    version: Literal["owner-personal-wonder-v1"] = POLICY
    policy_id: str
    account_id: Literal["georgiosaliba227"] = ACCOUNT
    allocation_id: Literal["hydration-v2-georgio-30usd"] = "hydration-v2-georgio-30usd"
    key_sha256: Fingerprint
    account_snapshot_sha256: Fingerprint
    waiver_source_sha256: Fingerprint
    legacy_cutoff_attempt_id: str
    waived_attempts: list[LegacyAttemptBinding] = Field(min_length=8, max_length=8)
    owner_authorization_reference: Reference | None = None
    legacy_billing_waiver_reference: Reference | None = None
    risk_acceptance_reference: Reference | None = None
    personal_data_authorization_reference: Reference | None = None
    notification_delivery_reference: Reference | None = None
    cross_ledger_reference: Reference | None = None
    research_authorization_reference: Reference | None = None
    accept_unverified_extras: StrictBool = False
    waive_billing_wait: StrictBool = False
    billing_wait_waiver_reference: Reference | None = None
    cross_ledger_clear: StrictBool = False
    cross_ledger_checked_at: datetime | None = None
    account_observation_reference: Reference | None = None
    account_observed_at: datetime | None = None
    observed_credits_micro_usd: StrictInt | None = Field(default=None, ge=0, le=150_000_000)
    valid_until: datetime | None = None

    _uuid = field_validator("policy_id", "legacy_cutoff_attempt_id")(LegacyAttemptBinding.uuid.__func__)


class OwnerRiskQuote(Descriptor):
    version: Literal["owner-risk-quote-v1"] = "owner-risk-quote-v1"
    account_id: Literal["georgiosaliba227"] = ACCOUNT
    model: Literal["muse-wonder-1.0"] = MODEL
    tier: Literal["Standard"] = "Standard"
    source: Literal["https://dev.meta.ai/docs/pricing-rate-limits"] = "https://dev.meta.ai/docs/pricing-rate-limits"
    input_micro_per_million: Literal[4000000] = 4_000_000
    output_micro_per_million: Literal[20000000] = 20_000_000
    all_charge_categories_verified: Literal[False] = False
    extra_charge_bound_micro_usd: None = None
    valid_until: datetime | None = None
    reference: Reference | None = None
    model_access_reference: Reference | None = None

    @field_validator("all_charge_categories_verified", mode="before")
    @classmethod
    def explicitly_unverified(cls, value: Any) -> bool:
        if value is not False:
            raise ValueError("Unverified provider extras cannot be certified")
        return False

    def current(self) -> bool:
        return (self.valid_until is not None and self.valid_until.tzinfo is not None
                and now() < self.valid_until <= now() + timedelta(days=1)
                and meaningful(self.reference) and meaningful(self.model_access_reference))

    def bound(self, inputs: int, outputs: int) -> int:
        if type(inputs) is not int or type(outputs) is not int or not 1 <= inputs <= 1_000_000 or not 1 <= outputs <= 2048:
            raise BudgetDenied("Bounded token counts required")
        return (inputs * self.input_micro_per_million + outputs * self.output_micro_per_million + 999999) // 1000000


def quote_template() -> dict[str, Any]:
    return OwnerRiskQuote().model_dump(mode="json")


def readiness_response(reasons: list[str], *, configured: bool = True, account: str | None = ACCOUNT,
                       policy: str | None = "owner_accepted_risk", all_charges: bool | None = False) -> dict[str, Any]:
    return {"version": "wonder-readiness-v1", "configured": configured,
        "status": "disabled" if not configured else "blocked" if reasons else "ready", "account_id": account,
        "policy": policy, "blocked_reasons": list(dict.fromkeys(reasons)),
        "all_charge_categories_verified": all_charges, "per_request_token_cap_micro_usd": RESERVATION}


class OwnerPersonalAuthority:
    def __init__(self, authority: AccountLedger) -> None:
        if type(authority) is not AccountLedger:
            raise BudgetDenied("Existing AccountLedger required")
        self.authority = authority

    @contextmanager
    def _transaction(self, *, write: bool = False) -> Iterator[Connection]:
        with self.authority._existing_migration_database(write=write) as db:
            _schema(db)
            yield db

    @staticmethod
    def _account(db: Connection) -> tuple[tuple[Any, ...], str]:
        row = db.execute("SELECT account_id,evidence,anchor_gross,frozen FROM live_accounts WHERE account_id=?", (ACCOUNT,)).fetchone()
        if not row or row[3] != 1 or type(row[2]) is not int or row[2] < 0:
            raise BudgetDenied("Expected preserved frozen owner account unavailable")
        try:
            evidence = strict_json(row[1]); key = evidence["key_sha256"]
            if not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{64}", key):
                raise ValueError
            return row, key
        except (KeyError, TypeError, ValueError):
            raise BudgetDenied("Existing owner key binding unavailable") from None

    @staticmethod
    def _legacy_identity(row: tuple[Any, ...]) -> str:
        return digest(list(row))

    @staticmethod
    def _legacy_rows(db: Connection, cutoff: str) -> list[tuple[Any, ...]]:
        at = db.execute("SELECT created_at FROM live_attempts WHERE id=? AND account_id=?", (cutoff, ACCOUNT)).fetchone()
        if not at:
            raise BudgetDenied("Original one-shot attempt is missing")
        return db.execute("SELECT id,account_id,price,reserved,input_bound,created_at,dispatched_at,payload_sha256,provider_id "
            "FROM live_attempts WHERE account_id=? AND id!=? AND created_at<=? ORDER BY id", (ACCOUNT, cutoff, at[0])).fetchall()

    @staticmethod
    def _waiver_source(db: Connection) -> tuple[str, str]:
        auth = db.execute("SELECT account_id,reference FROM live_events WHERE kind='wonder_owner_once_authorized'").fetchall()
        consumed = db.execute("SELECT account_id,reference FROM live_events WHERE kind='wonder_owner_once_consumed'").fetchall()
        if len(auth) != 1 or len(consumed) != 1 or auth[0][0] != ACCOUNT or consumed[0][0] != ACCOUNT:
            raise BudgetDenied("Existing exact legacy waiver provenance required")
        try:
            original = strict_json(auth[0][1]); cutoff = strict_json(consumed[0][1])["attempt_id"]
            if original["account_id"] != ACCOUNT or str(UUID(cutoff)) != cutoff:
                raise ValueError
            return digest(original), cutoff
        except (KeyError, ValueError, TypeError):
            raise BudgetDenied("Legacy waiver provenance is malformed") from None

    @staticmethod
    def _original_waiver_anchor(db: Connection, cutoff: str) -> None:
        """Reproduce the original pre-test snapshot, excluding only that new test.

        This pins original reservations before the first personal policy exists.
        Later policies are anchored to the first immutable personal descriptor.
        Legitimate finality for the ninth test is excluded with its linked row.
        """
        authorization_id, reference = db.execute(
            "SELECT id,reference FROM live_events WHERE kind='wonder_owner_once_authorized'"
        ).fetchone()
        original = strict_json(reference)
        snapshot = []
        for kind,name,table,sql in db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name"):
            if table == "beverages": continue
            entry = [kind,name,table,sql]
            if kind == "table":
                quoted = '"'+name.replace('"','""')+'"'
                columns = [x[1] for x in db.execute("PRAGMA table_info("+quoted+")")]
                rows = db.execute("SELECT * FROM "+quoted).fetchall()
                if name == "live_events":
                    event_id = columns.index("id")
                    rows = [row for row in rows if row[event_id] < authorization_id]
                if name in ("live_attempts","live_finalities"):
                    i = columns.index("id" if name=="live_attempts" else "attempt_id")
                    rows = [row for row in rows if row[i] != cutoff]
                data = [[{"bytes_hex":v.hex()} if isinstance(v,bytes) else v for v in row] for row in rows]
                entry.append(sorted(data,key=canonical))
            snapshot.append(entry)
        if digest(snapshot) != original.get("historical_snapshot_sha256"):
            raise BudgetDenied("Original legacy financial metadata changed before personal authorization")

    def prepare(self) -> dict[str, Any]:
        with self._transaction() as db:
            row, key = self._account(db)
            source, cutoff = self._waiver_source(db)
            existing = db.execute("SELECT reference FROM live_events WHERE kind=? ORDER BY id LIMIT 1",(AUTH_EVENT,)).fetchone()
            if existing:
                if not self._identity_matches(db,OwnerPersonalPolicy.model_validate_json(existing[0])):
                    raise BudgetDenied("Original personal waiver binding changed")
            else:
                self._original_waiver_anchor(db,cutoff)
            rows = self._legacy_rows(db, cutoff)
            if len(rows) != 8:
                raise BudgetDenied("Exactly the original eight legacy attempts are required")
            p = OwnerPersonalPolicy(policy_id=str(uuid4()), key_sha256=key, account_snapshot_sha256=digest(list(row)),
                waiver_source_sha256=source, legacy_cutoff_attempt_id=cutoff,
                waived_attempts=[LegacyAttemptBinding(attempt_id=r[0], identity_sha256=self._legacy_identity(r)) for r in rows])
            return p.model_dump(mode="json")

    def verify_identity(self, policy: OwnerPersonalPolicy, credential: str) -> None:
        with self._transaction() as db:
            _, key = self._account(db)
            if key != policy.key_sha256 or key != credential:
                raise BudgetDenied("Selected credential is not this owner's recorded key")

    @staticmethod
    def _billing_wait_waived(p: OwnerPersonalPolicy) -> bool:
        return p.waive_billing_wait is True and meaningful(p.billing_wait_waiver_reference)

    @staticmethod
    def _descriptor_reasons(p: OwnerPersonalPolicy) -> list[str]:
        reasons = []
        refs = (p.owner_authorization_reference, p.legacy_billing_waiver_reference, p.risk_acceptance_reference,
                p.personal_data_authorization_reference)
        if (not p.accept_unverified_extras or not all(map(meaningful, refs)) or p.valid_until is None
                or p.valid_until.tzinfo is None or not now() < p.valid_until <= now() + timedelta(days=1)
                or p.waive_billing_wait and not meaningful(p.billing_wait_waiver_reference)):
            reasons.append("owner_policy_invalid")
        if (not meaningful(p.account_observation_reference) or not fresh(p.account_observed_at)
                or p.observed_credits_micro_usd is None):
            reasons.append("account_observation_stale")
        if (not OwnerPersonalAuthority._billing_wait_waived(p)
                and (not p.cross_ledger_clear or not meaningful(p.cross_ledger_reference)
                     or not fresh(p.cross_ledger_checked_at))):
            reasons.append("cross_ledger_status_unverified")
        if not meaningful(p.notification_delivery_reference):
            reasons.append("notification_delivery_unverified")
        return reasons

    def _identity_matches(self, db: Connection, p: OwnerPersonalPolicy) -> bool:
        row, key = self._account(db)
        source, cutoff = self._waiver_source(db)
        expected = {r[0]: self._legacy_identity(r) for r in self._legacy_rows(db, cutoff)}
        given = {r.attempt_id:r.identity_sha256 for r in p.waived_attempts}
        first = db.execute("SELECT reference FROM live_events WHERE kind=? ORDER BY id LIMIT 1",(AUTH_EVENT,)).fetchone()
        if first:
            original = OwnerPersonalPolicy.model_validate_json(first[0])
            if original.waived_attempts != p.waived_attempts:
                return False
        else:
            self._original_waiver_anchor(db,cutoff)
        return (key == p.key_sha256 and digest(list(row)) == p.account_snapshot_sha256
                and source == p.waiver_source_sha256 and cutoff == p.legacy_cutoff_attempt_id
                and len(given) == 8 and given == expected)

    @staticmethod
    def _recorded(db: Connection, p: OwnerPersonalPolicy) -> bool:
        rows = db.execute("SELECT reference FROM live_events WHERE kind=? AND account_id=?", (AUTH_EVENT, ACCOUNT)).fetchall()
        # Omitted additive fields retain their strict false/null defaults. Never
        # rewrite the original event merely to serialize the new defaults.
        return sum(OwnerPersonalPolicy.model_validate_json(raw).model_dump_json() == p.model_dump_json()
                   for (raw,) in rows) == 1

    def authorize(self, policy: OwnerPersonalPolicy) -> None:
        p = OwnerPersonalPolicy.model_validate_json(policy.model_dump_json())
        if self._descriptor_reasons(p):
            raise BudgetDenied("Complete genuine owner policy references are required")
        with self._transaction(write=True) as db:
            if self._descriptor_reasons(p) or not self._identity_matches(db, p):
                raise BudgetDenied("Owner policy identity or waiver changed")
            rows = db.execute("SELECT reference FROM live_events WHERE kind=? AND account_id=?", (AUTH_EVENT, ACCOUNT)).fetchall()
            for (raw,) in rows:
                old = OwnerPersonalPolicy.model_validate_json(raw)
                if old.policy_id == p.policy_id:
                    if old.model_dump_json() == p.model_dump_json():
                        return
                    raise BudgetDenied("Recorded policy is immutable")
            self.authority.event(db, ACCOUNT, AUTH_EVENT, p.model_dump_json())

    @staticmethod
    def _pending_receipt(db: Connection, attempt: str) -> tuple[dict, bool]:
        """Validate recorded usage without representing it as invoice finality."""
        row = db.execute("SELECT account_id,state,reserved,actual,provider_id,input_bound,usage,"
            "payload_sha256,price,dispatched_at FROM live_attempts WHERE id=?", (attempt,)).fetchone()
        if (not row or row[0:4] != (ACCOUNT, "billing_pending", RESERVATION, None)
                or not isinstance(row[4], str) or not re.fullmatch(r"resp_[A-Za-z0-9_-]{1,180}", row[4])
                or type(row[5]) is not int or not 1 <= row[5] <= 1_000_000
                or not isinstance(row[7], str) or not re.fullmatch(r"[a-f0-9]{64}", row[7])
                or db.execute("SELECT COUNT(*) FROM live_attempts WHERE provider_id=?", (row[4],)).fetchone()[0] != 1):
            raise ValueError("No complete pending receipt")
        dispatched = datetime.fromisoformat(row[9])
        if dispatched.tzinfo is None or dispatched > now():
            raise ValueError("No recorded send time")
        usage = strict_json(row[6])
        inputs, outputs, cached, cost = (usage[key] for key in (
            "input_tokens", "output_tokens", "cached_tokens", "usage_derived_cost_micro_usd"))
        if (any(type(value) is not int or value < 0 for value in (inputs, outputs, cached, cost))
                or cached > inputs or inputs > row[5] or cost != inputs * 4 + outputs * 20):
            raise ValueError("Pending usage is unverified")
        consumed = db.execute("SELECT reference FROM live_events WHERE kind='wonder_owner_once_consumed'").fetchall()
        original = len(consumed) == 1 and strict_json(consumed[0][0]) == {"attempt_id": attempt}
        if original:
            from .wonder_owner_once import PAYLOAD_HASH, INPUT_BOUND, OUTPUT_BOUND
            authorization = db.execute("SELECT reference FROM live_events WHERE kind='wonder_owner_once_authorized'").fetchall()
            if (len(authorization) != 1 or row[8] != authorization[0][0]
                    or row[5] != INPUT_BOUND or row[7] != PAYLOAD_HASH or outputs > OUTPUT_BOUND
                    or set(usage) != {"input_tokens", "output_tokens", "cached_tokens", "usage_derived_cost_micro_usd"}
                    or db.execute("SELECT 1 FROM live_events WHERE reference=? AND kind IN "
                        "('wonder_owner_once_unresolved','wonder_owner_once_output_rejected',"
                        "'wonder_owner_once_result_save_failed')", (attempt,)).fetchone()):
                raise ValueError("Original completed test is not successful")
            usage_kind = "wonder_owner_once_usage_recorded"
        else:
            bindings = [strict_json(raw) for (raw,) in db.execute(
                "SELECT reference FROM live_events WHERE kind=? AND account_id=?", (BIND_EVENT, ACCOUNT))]
            bindings = [binding for binding in bindings if binding["attempt_id"] == attempt]
            fields = {"attempt_id", "policy_id", "policy_sha256", "purpose", "payload_sha256",
                      "input_bound", "output_bound", "consent_reference", "quote"}
            if (len(bindings) != 1 or set(bindings[0]) != fields
                    or bindings[0]["purpose"] not in PURPOSES or not meaningful(bindings[0]["consent_reference"])
                    or type(bindings[0]["input_bound"]) is not int
                    or bindings[0]["payload_sha256"] != row[7] or bindings[0]["input_bound"] != row[5]
                    or type(bindings[0]["output_bound"]) is not int or not 1 <= bindings[0]["output_bound"] <= 2048
                    or outputs > bindings[0]["output_bound"] or strict_json(row[8]) != bindings[0]["quote"]
                    or set(usage) != {"input_tokens", "output_tokens", "cached_tokens", "total_tokens", "usage_derived_cost_micro_usd"}
                    or type(usage["total_tokens"]) is not int or usage["total_tokens"] != inputs + outputs):
                raise ValueError("No exact pending request binding")
            OwnerRiskQuote.model_validate_json(row[8])
            approvals = []
            for (raw,) in db.execute("SELECT reference FROM live_events WHERE kind=? AND account_id=?", (AUTH_EVENT, ACCOUNT)):
                approval = OwnerPersonalPolicy.model_validate_json(raw)
                if approval.policy_id == bindings[0]["policy_id"]:
                    approvals.append((approval, strict_json(raw)))
            if (len(approvals) != 1 or bindings[0]["policy_sha256"] not in {
                    digest(approvals[0][1]), digest(approvals[0][0].model_dump(mode="json"))}
                    or bindings[0]["purpose"] == "synthetic_training_plan"
                    and not meaningful(approvals[0][0].research_authorization_reference)):
                raise ValueError("Pending receipt lost its exact immutable authorization")
            usage_kind = "wonder_personal_owner_usage_recorded"
        if db.execute("SELECT COUNT(*) FROM live_events WHERE kind=? AND account_id=? AND reference=?",
                      (usage_kind, ACCOUNT, attempt)).fetchone()[0] != 1:
            raise ValueError("No recorded verified usage event")
        receipt = {"attempt_id": attempt, "payload_sha256": row[7], "usage_sha256": digest(usage)}
        if not original:
            receipt["binding_sha256"] = digest(bindings[0])
        return receipt, original

    @classmethod
    def _successful_pending(cls, db: Connection, attempt: str) -> bool:
        try:
            receipt, original = cls._pending_receipt(db, attempt)
            if original:
                saved = [strict_json(raw) for (raw,) in db.execute(
                    "SELECT reference FROM live_events WHERE kind='wonder_owner_once_result_saved' AND account_id=?", (ACCOUNT,))]
                return (len(saved) == 1 and set(saved[0]) == {"attempt_id", "result_sha256"}
                    and saved[0]["attempt_id"] == attempt and isinstance(saved[0]["result_sha256"], str)
                    and re.fullmatch(r"[a-f0-9]{64}", saved[0]["result_sha256"]) is not None)
            records = {}
            for kind in (OUTPUT_EVENT, PUBLISHED_EVENT):
                records[kind] = [strict_json(raw) for (raw,) in db.execute(
                    "SELECT reference FROM live_events WHERE kind=? AND account_id=?", (kind, ACCOUNT))]
                records[kind] = [record for record in records[kind] if record["attempt_id"] == attempt]
            output, published = records[OUTPUT_EVENT], records[PUBLISHED_EVENT]
            return (len(output) == 1 and published == output and set(output[0]) == set(receipt) | {"result_sha256"}
                and all(output[0][key] == value for key, value in receipt.items())
                and isinstance(output[0]["result_sha256"], str)
                and re.fullmatch(r"[a-f0-9]{64}", output[0]["result_sha256"]) is not None)
        except (KeyError, TypeError, ValueError, AttributeError):
            return False

    def record_output(self, attempt: str, result_sha256: str) -> None:
        self._record_result_event(attempt, result_sha256, published=False)

    def record_result_saved(self, attempt: str, result_sha256: str) -> None:
        self._record_result_event(attempt, result_sha256, published=True)

    def _record_result_event(self, attempt: str, result_sha256: str, *, published: bool) -> None:
        if not isinstance(result_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", result_sha256):
            raise ValueError("Opaque validated result digest required")
        with self._transaction(write=True) as db:
            receipt, original = self._pending_receipt(db, attempt)
            if original:
                raise BudgetDenied("The original test keeps its original publication record")
            record = receipt | {"result_sha256": result_sha256}
            kind = PUBLISHED_EVENT if published else OUTPUT_EVENT
            if published:
                validated = [strict_json(raw) for (raw,) in db.execute(
                    "SELECT reference FROM live_events WHERE kind=? AND account_id=?", (OUTPUT_EVENT, ACCOUNT))]
                if [value for value in validated if value["attempt_id"] == attempt] != [record]:
                    raise BudgetDenied("Saved result does not match validated output")
            old = [strict_json(raw) for (raw,) in db.execute(
                "SELECT reference FROM live_events WHERE kind=? AND account_id=?", (kind, ACCOUNT))]
            old = [value for value in old if value["attempt_id"] == attempt]
            if old:
                if old == [record]:
                    return
                raise BudgetDenied("Validated result linkage is immutable")
            self.authority.event(db, ACCOUNT, kind, canonical(record))

    def _checks(self, db: Connection, p: OwnerPersonalPolicy, q: OwnerRiskQuote,
                *, excluding_attempt: str | None = None) -> list[str]:
        reasons = self._descriptor_reasons(p)
        if not self._recorded(db, p): reasons.append("owner_policy_not_recorded")
        if not q.current(): reasons.append("quote_expired")
        if not self._identity_matches(db, p): reasons.append("owner_policy_invalid")
        waived = {x.attempt_id for x in p.waived_attempts}
        total = 0
        baseline = self._account(db)[0][2]
        for a, account, state, reserved, actual, provider, dispatched in db.execute(
                "SELECT id,account_id,state,reserved,actual,provider_id,dispatched_at FROM live_attempts"):
            if a == excluding_attempt: continue
            if type(reserved) is not int or reserved <= 0 or (actual is not None and (type(actual) is not int or actual < 0)):
                reasons.append("financial_failure_requires_review"); continue
            if account == ACCOUNT: total += max(reserved, actual or 0)
            if state not in ("settled", "billing_pending", "unresolved"):
                reasons.append("request_in_flight"); continue
            if a in waived:
                if account != ACCOUNT: reasons.append("owner_policy_invalid")
                continue
            if self._billing_wait_waived(p) and state == "billing_pending":
                if not self._successful_pending(db, a):
                    reasons.append("financial_failure_requires_review")
                continue
            if self._billing_wait_waived(p) and state == "unresolved":
                reasons.append("financial_failure_requires_review")
                continue
            f = db.execute("SELECT evidence FROM live_finalities WHERE attempt_id=?", (a,)).fetchone()
            try:
                finality = InvoiceFinality.model_validate_json(f[0])
                if (state != "settled" or finality.attempt_id != a or finality.account_id != account
                        or finality.provider_id != provider or finality.final_gross_micro_usd != actual or dispatched is None
                        or finality.finalized_at < datetime.fromisoformat(dispatched)):
                    raise ValueError
            except (TypeError, ValueError): reasons.append("current_invoice_finality_required")
        if db.execute("SELECT 1 FROM live_events WHERE kind=?", (FAIL_EVENT,)).fetchone():
            reasons.append("financial_failure_requires_review")
        if db.execute("SELECT 1 FROM live_notices WHERE delivered_at IS NULL").fetchone():
            reasons.append("notification_delivery_unverified")
        if (total + RESERVATION > 30_000_000 or baseline + total + RESERVATION >= 75_000_000
                or baseline + total + RESERVATION >= 120_000_000
                or p.observed_credits_micro_usd is not None and total + RESERVATION > p.observed_credits_micro_usd):
            reasons.append("budget_exhausted")
        return [reason for reason in REASONS if reason in reasons]

    def readiness(self, policy: OwnerPersonalPolicy, quote: OwnerRiskQuote) -> dict:
        try:
            p = OwnerPersonalPolicy.model_validate_json(policy.model_dump_json())
            q = OwnerRiskQuote.model_validate_json(quote.model_dump_json())
            with self._transaction() as db: reasons = self._checks(db, p, q)
        except (BudgetDenied, OSError): reasons = ["storage_unavailable"]
        except (ValueError, TypeError): reasons = ["owner_policy_invalid"]
        return readiness_response(reasons)

    def snapshot(self) -> dict:
        with self._transaction() as db:
            total = db.execute("SELECT COALESCE(SUM(MAX(reserved,COALESCE(actual,0))),0) FROM live_attempts WHERE account_id=?", (ACCOUNT,)).fetchone()[0]
        return {"account_id": ACCOUNT, "allocation_id": "hydration-v2-georgio-30usd", "hard_limit_micro_usd": 30_000_000,
                "aggregate_exposure_micro_usd": total, "remaining_micro_usd": max(0, 30_000_000-total),
                "all_charge_categories_verified": False, "provider_extras_bounded": False}

    def reserve(self, p: OwnerPersonalPolicy, q: OwnerRiskQuote, purpose: str, payload_hash: str,
                bound: int, output: int, credential: str, consent: str) -> str:
        p = OwnerPersonalPolicy.model_validate_json(p.model_dump_json())
        q = OwnerRiskQuote.model_validate_json(q.model_dump_json())
        if (purpose not in PURPOSES or not meaningful(consent) or not re.fullmatch(r"[a-f0-9]{64}", payload_hash)
                or q.bound(bound, output) > RESERVATION
                or purpose == "synthetic_training_plan" and not meaningful(p.research_authorization_reference)):
            raise BudgetDenied("Exact authorized purpose, consent and bounded tokens required")
        with self._transaction(write=True) as db:
            if credential != p.key_sha256 or self._checks(db, p, q):
                raise BudgetDenied("Personal Wonder readiness gates block admission")
            for (raw,) in db.execute("SELECT reference FROM live_events WHERE kind=?", (BIND_EVENT,)):
                if strict_json(raw)["payload_sha256"] == payload_hash:
                    raise BudgetDenied("An attempted payload is never sent again")
            attempt = str(uuid4())
            binding = {"attempt_id":attempt, "policy_id":p.policy_id, "policy_sha256":digest(p.model_dump(mode="json")),
                "purpose":purpose, "payload_sha256":payload_hash, "input_bound":bound, "output_bound":output,
                "consent_reference":consent, "quote":q.model_dump(mode="json")}
            db.execute("INSERT INTO live_attempts(id,account_id,price,reserved,state,input_bound,created_at,payload_sha256) VALUES(?,?,?,?,?,?,?,?)",
                (attempt, ACCOUNT, q.model_dump_json(), RESERVATION, "personal_owner_reserved", bound, stamp(), payload_hash))
            self.authority.event(db, ACCOUNT, BIND_EVENT, canonical(binding))
        return attempt

    def _current(self, db: Connection, p: OwnerPersonalPolicy, q: OwnerRiskQuote,
                 attempt: str) -> tuple[tuple[Any, ...], dict[str, Any]]:
        bindings = [strict_json(r[0]) for r in db.execute("SELECT reference FROM live_events WHERE kind=?", (BIND_EVENT,))]
        found = [r for r in bindings if r["attempt_id"] == attempt]
        row = db.execute("SELECT state,price,reserved,actual,payload_sha256,input_bound,ticket_nonce FROM live_attempts WHERE id=? AND account_id=?", (attempt,ACCOUNT)).fetchone()
        if (len(found) != 1 or not row or found[0]["policy_id"] != p.policy_id
                or found[0]["policy_sha256"] != digest(p.model_dump(mode="json"))
                or found[0]["quote"] != q.model_dump(mode="json") or row[1:4] != (q.model_dump_json(), RESERVATION, None)
                or row[4:6] != (found[0]["payload_sha256"], found[0]["input_bound"])
                or self._checks(db,p,q,excluding_attempt=attempt)):
            raise BudgetDenied("Attempt no longer matches admissible owner policy")
        return row, found[0]

    def dispatch(self, p: OwnerPersonalPolicy, q: OwnerRiskQuote, attempt: str) -> "OwnerPersonalTicket":
        with self._transaction(write=True) as db:
            row, binding = self._current(db,p,q,attempt)
            if row[0] != "personal_owner_reserved": raise BudgetDenied("Attempt cannot dispatch twice")
            nonce = str(uuid4())
            db.execute("UPDATE live_attempts SET state='personal_owner_dispatched',dispatched_at=?,ticket_nonce=? WHERE id=?", (stamp(),nonce,attempt))
            self.authority.event(db,ACCOUNT,"wonder_personal_owner_dispatched",attempt)
        return OwnerPersonalTicket(self,p,q,attempt,nonce,binding["purpose"])

    def claim(self, ticket: "OwnerPersonalTicket", payload: dict, bound: int, credential: str) -> None:
        from .wonder_personal_owner_gateway import validate_purpose_payload
        from .wonder_hydration import payload_sha256
        purpose = validate_purpose_payload(payload)
        with self._transaction(write=True) as db:
            row, binding = self._current(db,ticket.policy,ticket.quote,ticket.attempt)
            if (row[0] != "personal_owner_dispatched" or row[6] != ticket.nonce or purpose != ticket.purpose
                    or purpose != binding["purpose"] or payload_sha256(payload) != binding["payload_sha256"]
                    or type(bound) is not int or bound != binding["input_bound"] or credential != ticket.policy.key_sha256):
                raise BudgetDenied("No exact one-use purpose ticket")
            db.execute("UPDATE live_attempts SET state='personal_owner_sending',ticket_nonce=NULL WHERE id=?", (ticket.attempt,))
            self.authority.event(db,ACCOUNT,"wonder_personal_owner_send_claimed",ticket.attempt)

    def record_reply(self, attempt: str, reply: ProviderReply) -> int:
        with self._transaction(write=True) as db:
            row = db.execute("SELECT state,input_bound FROM live_attempts WHERE id=? AND account_id=?", (attempt,ACCOUNT)).fetchone()
            if not row or row[0] != "personal_owner_sending": raise BudgetDenied("No sending personal attempt")
            body = reply.body
            identifier = body.get("id") if isinstance(body,dict) else None
            if isinstance(identifier,str) and re.fullmatch(r"resp_[A-Za-z0-9_-]{1,180}",identifier):
                if db.execute("SELECT 1 FROM live_attempts WHERE provider_id=? AND id!=?",(identifier,attempt)).fetchone():
                    raise BudgetDenied("Provider response is already recorded")
                db.execute("UPDATE live_attempts SET provider_id=? WHERE id=?",(identifier,attempt))
            else: identifier = None
            try:
                b = next(strict_json(r[0]) for r in db.execute("SELECT reference FROM live_events WHERE kind=?",(BIND_EVENT,)) if strict_json(r[0])["attempt_id"]==attempt)
                u = body["usage"]; inputs,outputs,total=u["input_tokens"],u["output_tokens"],u["total_tokens"];cached=u["input_tokens_details"]["cached_tokens"]
                if (identifier is None or reply.status != 200 or body["model"] != MODEL
                        or any(type(v) is not int or v < 0 for v in (inputs,outputs,total,cached))
                        or inputs > row[1] or outputs > b["output_bound"] or cached > inputs or total != inputs+outputs): raise ValueError
                estimate=inputs*4+outputs*20
                db.execute("UPDATE live_attempts SET state='billing_pending',usage=? WHERE id=?",(canonical({"input_tokens":inputs,"output_tokens":outputs,"cached_tokens":cached,"total_tokens":total,"usage_derived_cost_micro_usd":estimate}),attempt))
                self.authority.event(db,ACCOUNT,"wonder_personal_owner_usage_recorded",attempt)
            except (KeyError,TypeError,ValueError,StopIteration):
                db.execute("UPDATE live_attempts SET state='unresolved',ticket_nonce=NULL WHERE id=?",(attempt,))
                self.authority.event(db,ACCOUNT,FAIL_EVENT,canonical({"attempt_id":attempt,"reason":"usage_unverified"}))
                estimate=None
        if estimate is None: raise RecognitionUnavailable()
        return estimate

    def failure(self, attempt: str, reason: str) -> None:
        with self._transaction(write=True) as db:
            db.execute("UPDATE live_attempts SET state='unresolved',ticket_nonce=NULL WHERE id=? AND state!='billing_pending' AND actual IS NULL",(attempt,))
            self.authority.event(db,ACCOUNT,FAIL_EVENT,canonical({"attempt_id":attempt,"reason":reason}))

    @staticmethod
    def _training_link(db: Connection, envelope: dict) -> str:
        from .muse_training_plan import fixed_payload, validate_plan
        from .wonder_hydration import payload_sha256
        try:
            if set(envelope)!={"version","plan","generated_at","provenance","provider_observations"}:
                raise ValueError
            validate_plan(envelope["plan"])
            p=envelope["provenance"];attempt=p["attempt_id"]
            expected={"mode":"meta_live","provider":"Meta","model":MODEL,"account_id":ACCOUNT,
                "attempt_id":attempt,"payload_sha256":payload_sha256(fixed_payload()),"personal_data_used":False}
            if (envelope["version"]!="muse-training-plan-result-v1" or p!=expected
                    or p["personal_data_used"] is not False or str(UUID(attempt))!=attempt):raise ValueError
            bindings=[strict_json(r[0]) for r in db.execute("SELECT reference FROM live_events WHERE kind=?",(BIND_EVENT,))
                if strict_json(r[0])["attempt_id"]==attempt]
            row=db.execute("SELECT state,provider_id,usage,payload_sha256,dispatched_at,price FROM live_attempts WHERE id=? AND account_id=?",(attempt,ACCOUNT)).fetchone()
            if (len(bindings)!=1 or bindings[0]["purpose"]!="synthetic_training_plan"
                    or bindings[0]["payload_sha256"]!=p["payload_sha256"] or not row
                    or row[0] not in ("billing_pending","settled") or not isinstance(row[1],str)
                    or not re.fullmatch(r"resp_[A-Za-z0-9_-]{1,180}",row[1])
                    or row[3]!=p["payload_sha256"] or row[2] is None or row[4] is None
                    or strict_json(row[5])!=bindings[0]["quote"]):raise ValueError
            o=envelope["provider_observations"];u=strict_json(row[2])
            if (set(o)!={"latency_ms","input_tokens","output_tokens","usage_derived_cost_micro_usd","billed_cost_usd"}
                    or o["billed_cost_usd"] is not None
                    or any(type(o[k]) is not int or o[k]<0 for k in ("latency_ms","input_tokens","output_tokens","usage_derived_cost_micro_usd"))
                    or any(o[k]!=u[k] for k in ("input_tokens","output_tokens","usage_derived_cost_micro_usd"))
                    or u["input_tokens"]>bindings[0]["input_bound"] or u["output_tokens"]>bindings[0]["output_bound"]):raise ValueError
            generated=datetime.fromisoformat(envelope["generated_at"].replace("Z","+00:00"))
            if generated.tzinfo is None or generated.utcoffset()!=timedelta(0) or not datetime.fromisoformat(row[4])<=generated<=now():
                raise ValueError
            return attempt
        except (KeyError,ValueError,TypeError,AttributeError):
            raise ValueError("No matching synthetic training dispatch provenance") from None

    def record_training_plan(self, envelope: dict) -> None:
        """Append opaque output linkage after the gateway validates a real reply."""
        with self._transaction(write=True) as db:
            attempt=self._training_link(db,envelope)
            record={"attempt_id":attempt,"plan_sha256":digest(envelope["plan"]),"envelope_sha256":digest(envelope)}
            old=[strict_json(r[0]) for r in db.execute("SELECT reference FROM live_events WHERE kind=?",(TRAINING_EVENT,))
                if strict_json(r[0])["attempt_id"]==attempt]
            if old:
                if old==[record]:return
                raise BudgetDenied("A gateway-validated training output is immutable")
            self.authority.event(db,ACCOUNT,TRAINING_EVENT,canonical(record))

    def verify_training_plan_record(self, envelope: dict) -> None:
        """Read-only: a standalone JSON file is never proof of a Muse run."""
        with self._transaction() as db:
            attempt=self._training_link(db,envelope)
            expected={"attempt_id":attempt,"plan_sha256":digest(envelope["plan"]),"envelope_sha256":digest(envelope)}
            records=[strict_json(r[0]) for r in db.execute("SELECT reference FROM live_events WHERE kind=?",(TRAINING_EVENT,))
                if strict_json(r[0])["attempt_id"]==attempt]
            if records!=[expected]:raise ValueError("No gateway-validated training plan digest")



@dataclass(frozen=True)
class OwnerPersonalTicket:
    authority: OwnerPersonalAuthority
    policy: OwnerPersonalPolicy
    quote: OwnerRiskQuote
    attempt: str
    nonce: str
    purpose: str

    def claim(self, payload: dict, *, input_bound: int, credential_fingerprint: str) -> None:
        self.authority.claim(self,payload,input_bound,credential_fingerprint)
