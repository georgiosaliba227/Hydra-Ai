"""Account-isolated v2 financial ledger. No network, provider keys or image storage."""
from datetime import datetime, timezone
from dataclasses import dataclass
from contextlib import contextmanager
from collections.abc import Iterator
import os
from pathlib import Path
import stat
import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .meta_provider import ProviderReply
import hashlib
import json
import re
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from .meta_budget import MetaBudget, BudgetDenied
from .recognition import MODEL
from .meta_policy import MAX_INPUT_TOKENS, OUTPUT_LIMIT

ACCOUNTS = ("georgiosaliba227", "aminealichaouche")
USD = 1_000_000
CAP = 250_000
PROPOSED_CAP = 2_000_000

FINALITY_SCHEMA_VERSION = "account-ledger-finality-v1"
# These are the shipped pre-finality tables, including every constraint/default.
# Migration accepts this known layout only; it never repairs unfamiliar schemas.
FINANCIAL_DDL: dict[str, str] = {
    "live_accounts": "CREATE TABLE live_accounts(account_id TEXT PRIMARY KEY, evidence TEXT NOT NULL, anchor_gross INTEGER NOT NULL, frozen INTEGER NOT NULL DEFAULT 0)",
    "live_prices": "CREATE TABLE live_prices(version TEXT PRIMARY KEY, snapshot TEXT NOT NULL)",
    "live_permit": "CREATE TABLE live_permit(id INTEGER PRIMARY KEY CHECK(id=1), permit TEXT NOT NULL, spent INTEGER NOT NULL DEFAULT 0)",
    "live_attempts": "CREATE TABLE live_attempts(id TEXT PRIMARY KEY, account_id TEXT NOT NULL, price TEXT NOT NULL, reserved INTEGER NOT NULL, actual INTEGER, provider_id TEXT, state TEXT NOT NULL, input_bound INTEGER NOT NULL, recognized INTEGER NOT NULL DEFAULT 0, usage TEXT, created_at TEXT NOT NULL, dispatched_at TEXT, payload_sha256 TEXT, ticket_nonce TEXT)",
    "live_events": "CREATE TABLE live_events(id INTEGER PRIMARY KEY, at TEXT NOT NULL, account_id TEXT, kind TEXT NOT NULL, reference TEXT NOT NULL)",
    "live_notices": "CREATE TABLE live_notices(id TEXT PRIMARY KEY, account_id TEXT NOT NULL, recipient TEXT NOT NULL, threshold INTEGER NOT NULL, delivered_at TEXT, delivery_reference TEXT, UNIQUE(account_id,recipient,threshold))",
    "controlled_permits": "CREATE TABLE controlled_permits(account_id TEXT PRIMARY KEY, permit TEXT NOT NULL, spent INTEGER NOT NULL DEFAULT 0)",
    "live_finalities": "CREATE TABLE live_finalities(attempt_id TEXT PRIMARY KEY, evidence TEXT NOT NULL, recorded_at TEXT NOT NULL)",
}


def _canonical_schema(sql: str) -> str:
    return re.sub(r"\s+", "", sql).lower().replace("ifnotexists", "").rstrip(";")


def now() -> datetime:
    return datetime.now(timezone.utc)


def stamp() -> str:
    return now().isoformat()


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    account_id: Literal["georgiosaliba227", "aminealichaouche"]
    provider_account_reference: str = Field(min_length=1, max_length=200)
    key_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    gross_micro_usd: StrictInt = Field(ge=0, le=9_000_000_000_000_000)
    credits_remaining_micro_usd: StrictInt = Field(ge=0, le=150_000_000)
    valid_until: datetime
    credits_expire: datetime
    reference: str = Field(min_length=1, max_length=500)
    billing_verified: Literal[True]
    hackathon_terms_verified: Literal[True]
    exclusive_gateway_key_verified: Literal[True]
    provider_limits_verified: Literal[True]
    retention_reviewed: Literal[True]
    all_charge_categories_verified: Literal[True]
    extra_charge_bound_micro_usd: StrictInt = Field(ge=0, le=PROPOSED_CAP)

    @field_validator("billing_verified", "hackathon_terms_verified", "exclusive_gateway_key_verified", "provider_limits_verified", "retention_reviewed", "all_charge_categories_verified", mode="before")
    @classmethod
    def explicit_true(cls, value: object) -> bool:
        if value is not True:
            raise ValueError("Explicit independent human verification required")
        return True

    @field_validator("valid_until", "credits_expire")
    @classmethod
    def future(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value <= now():
            raise ValueError("Current dated evidence required")
        return value


class Price(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: str = Field(min_length=1, max_length=100)
    model: Literal["muse-spark-1.3"] = MODEL
    source: Literal["https://dev.meta.ai/docs/pricing-rate-limits"] = "https://dev.meta.ai/docs/pricing-rate-limits"
    input_micro_per_million: Literal[1250000] = 1_250_000
    cached_micro_per_million: Literal[150000] = 150_000
    output_micro_per_million: Literal[4250000] = 4_250_000
    valid_until: datetime
    reviewed_by: tuple[Literal["georgiosaliba227"], Literal["aminealichaouche"]]
    reference: str = Field(min_length=1, max_length=500)

    _future = field_validator("valid_until")(Evidence.future.__func__)

    def cost(self, inputs: int, outputs: int, cached: int = 0) -> int:
        # Integer ceiling, no floating-point under-reservation or credit offsets.
        numerator = ((inputs - cached) * self.input_micro_per_million + cached * self.cached_micro_per_million
                     + outputs * self.output_micro_per_million)
        return (numerator + 999_999) // 1_000_000


class FirstPermit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    account_id: Literal["georgiosaliba227", "aminealichaouche"]
    image_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    price_version: str
    developer_approvals: tuple[Literal["georgiosaliba227"], Literal["aminealichaouche"]]
    spending_authority_reference: str = Field(min_length=1, max_length=500)
    account_owner_authorization_reference: str = Field(min_length=1, max_length=500)
    image_owner_consent_reference: str = Field(min_length=1, max_length=500)
    valid_until: datetime
    maximum_micro_usd: Literal[250000] = CAP
    request_count: Literal[1] = 1
    further_spend_approval_reference: str | None = Field(default=None, min_length=1, max_length=500)

    _future = field_validator("valid_until")(Evidence.future.__func__)


class ControlledPermit(FirstPermit):
    """Proposed policy: inert until genuine account-specific approval is recorded."""
    policy_version: Literal["dual-test-v1"]
    purpose: Literal["camera", "hydration"]
    maximum_micro_usd: StrictInt = Field(ge=1, le=PROPOSED_CAP)


class InvoiceFinality(BaseModel):
    """Private reviewed attestation; never an authenticated billing fetch."""
    model_config = ConfigDict(extra="forbid", strict=True)
    attempt_id: str = Field(pattern=r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")
    account_id: Literal["georgiosaliba227", "aminealichaouche"]
    provider_id: str = Field(pattern=r"^resp_[A-Za-z0-9_-]{1,180}$")
    final_gross_micro_usd: StrictInt = Field(ge=0, le=9_000_000_000_000_000)
    finalized_at: datetime
    provider_evidence_reference: str = Field(min_length=1, max_length=500)
    georgio_review_reference: str = Field(min_length=1, max_length=500)
    amine_review_reference: str = Field(min_length=1, max_length=500)
    provider_finality_verified: Literal[True]

    _explicit_true = field_validator("provider_finality_verified", mode="before")(Evidence.explicit_true.__func__)

    @field_validator("finalized_at")
    @classmethod
    def past_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value > now():
            raise ValueError("Past timezone-aware provider finalization time required")
        return value.astimezone(timezone.utc)

    @field_validator("provider_evidence_reference", "georgio_review_reference", "amine_review_reference")
    @classmethod
    def meaningful_reference(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Explicit provider evidence and both developer reviews required")
        return value


def parse_permit(raw: str) -> FirstPermit:
    kind = json.loads(raw).get("policy_version")
    return ControlledPermit.model_validate_json(raw) if kind else FirstPermit.model_validate_json(raw)


class AccountLedger(MetaBudget):
    """Logical per-account ledgers within ONE authoritative local SQLite file.

    Operator evidence is an attestation, not independently verified dashboard data.
    No default baseline, automatic mapping of legacy usage, reset or HTTP admin API.
    """
    def initialize(self, **kwargs) -> None:
        raise BudgetDenied("Use explicit account-specific initialization")

    def reserve(self, *args, **kwargs) -> None:
        raise BudgetDenied("Legacy reservation cannot bypass the first-test gate")

    def settle(self, *args, **kwargs) -> None:
        raise BudgetDenied("Caller-supplied costs are not provider billing evidence")

    def record_approval(self, **kwargs) -> None:
        raise BudgetDenied("Use account- and image-bound first-test approval")

    def initialize_accounts(self) -> None:
        with self.transaction() as db:
            db.execute("CREATE TABLE IF NOT EXISTS live_accounts(account_id TEXT PRIMARY KEY, evidence TEXT NOT NULL, anchor_gross INTEGER NOT NULL, frozen INTEGER NOT NULL DEFAULT 0)")
            db.execute("CREATE TABLE IF NOT EXISTS live_prices(version TEXT PRIMARY KEY, snapshot TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS live_permit(id INTEGER PRIMARY KEY CHECK(id=1), permit TEXT NOT NULL, spent INTEGER NOT NULL DEFAULT 0)")
            db.execute("CREATE TABLE IF NOT EXISTS live_attempts(id TEXT PRIMARY KEY, account_id TEXT NOT NULL, price TEXT NOT NULL, reserved INTEGER NOT NULL, actual INTEGER, provider_id TEXT, state TEXT NOT NULL, input_bound INTEGER NOT NULL, recognized INTEGER NOT NULL DEFAULT 0, usage TEXT, created_at TEXT NOT NULL, dispatched_at TEXT, payload_sha256 TEXT, ticket_nonce TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS live_events(id INTEGER PRIMARY KEY, at TEXT NOT NULL, account_id TEXT, kind TEXT NOT NULL, reference TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS live_notices(id TEXT PRIMARY KEY, account_id TEXT NOT NULL, recipient TEXT NOT NULL, threshold INTEGER NOT NULL, delivered_at TEXT, delivery_reference TEXT, UNIQUE(account_id,recipient,threshold))")

        with self.transaction() as db:
            db.execute("CREATE TABLE IF NOT EXISTS controlled_permits(account_id TEXT PRIMARY KEY, permit TEXT NOT NULL, spent INTEGER NOT NULL DEFAULT 0)")
            db.execute("CREATE TABLE IF NOT EXISTS live_finalities(attempt_id TEXT PRIMARY KEY, evidence TEXT NOT NULL, recorded_at TEXT NOT NULL)")
        os.chmod(self.path, 0o600)

    @contextmanager
    def _existing_migration_database(self, *, write: bool) -> Iterator[sqlite3.Connection]:
        """Open an existing offline ledger only; never create or recover one.

        Rollback-journal format is the known deployed layout. Refuse WAL or
        leftover journals instead of modifying sidecars or silently recovering
        potentially interrupted financial work during a schema operation.
        """
        connection = None
        descriptor = None
        try:
            path = Path(self.path)
            if not path.is_absolute() or any(item.is_symlink() for item in (path, *path.parents)):
                raise ValueError
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            original = os.fstat(descriptor)
            if (not stat.S_ISREG(original.st_mode) or original.st_uid != os.getuid()
                    or stat.S_IMODE(original.st_mode) != 0o600 or original.st_nlink != 1):
                raise ValueError
            header = os.read(descriptor, 100)
            if len(header) != 100 or header[:16] != b"SQLite format 3\x00" or header[18:20] != b"\x01\x01":
                raise ValueError
            if any(os.path.lexists(str(path) + suffix) for suffix in ("-journal", "-wal", "-shm")):
                raise ValueError
            connection = sqlite3.connect(path.as_uri() + ("?mode=rw" if write else "?mode=ro"),
                                         uri=True, timeout=0.5)
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("PRAGMA synchronous=FULL" if write else "PRAGMA query_only=ON")
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            current = os.stat(path, follow_symlinks=False)
            if (current.st_dev, current.st_ino, current.st_uid, current.st_mode, current.st_nlink) != (
                    original.st_dev, original.st_ino, original.st_uid, original.st_mode, original.st_nlink):
                raise ValueError
            yield connection
            current = os.stat(path, follow_symlinks=False)
            if (current.st_dev, current.st_ino, current.st_uid, current.st_mode, current.st_nlink) != (
                    original.st_dev, original.st_ino, original.st_uid, original.st_mode, original.st_nlink):
                raise ValueError
            connection.commit() if write else connection.rollback()
        except Exception:
            if connection is not None:
                try:
                    connection.rollback()
                except sqlite3.Error:
                    pass  # Leave any interrupted journal for separate recovery.
            raise BudgetDenied("Schema operation refused; existing private offline ledger requires review") from None
        finally:
            if connection is not None:
                connection.close()
            if descriptor is not None:
                os.close(descriptor)

    @staticmethod
    def _inspect_finality_schema(db: sqlite3.Connection) -> dict:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise BudgetDenied("Ledger integrity check failed")
        objects = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master").fetchall()
        by_name = {row[1]: row for row in objects}
        for name, expected in FINANCIAL_DDL.items():
            row = by_name.get(name)
            if row is None and name == "live_finalities":
                continue
            if row is None or row[0] != "table" or not isinstance(row[3], str) or _canonical_schema(row[3]) != _canonical_schema(expected):
                raise BudgetDenied("Unrecognized financial schema; migration refused")
        for kind, name, table, sql in objects:
            if (kind == "trigger" or (kind == "index" and table in FINANCIAL_DDL and sql is not None)
                    or (name.startswith(("live_", "controlled_", "meta_")) and name not in FINANCIAL_DDL)):
                raise BudgetDenied("Unexpected schema object; migration refused")
        present = "live_finalities" in by_name
        expected_ddl = "\n".join(_canonical_schema(sql) for sql in FINANCIAL_DDL.values())
        return {"version": FINALITY_SCHEMA_VERSION, "compatible": True,
                "status": "already_current" if present else "migration_required",
                "financial_tables_verified": len(FINANCIAL_DDL) if present else len(FINANCIAL_DDL) - 1,
                "target_schema_sha256": hashlib.sha256(expected_ddl.encode()).hexdigest(),
                "existing_records_changed": False, "audit_event_added": False, "activation_authorized": False}

    def preview_finality_schema(self) -> dict:
        """Read-only compatibility/integrity inspection; no evidence/body output."""
        with self._existing_migration_database(write=False) as db:
            return self._inspect_finality_schema(db)

    def migrate_finality_schema(self, *, review_reference: str) -> dict:
        """Atomically add only the finality table and one schema audit event.

        This never attests invoices, changes permits/balances or clears freezes.
        Idempotent repeats still verify the complete known schema before success.
        """
        if (not isinstance(review_reference, str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/# -]{0,199}", review_reference)
                or review_reference != review_reference.strip()):
            raise BudgetDenied("A bounded nonsecret schema review reference is required")
        with self._existing_migration_database(write=True) as db:
            before = self._inspect_finality_schema(db)
            if before["status"] == "already_current":
                return before
            db.execute(FINANCIAL_DDL["live_finalities"])
            self.event(db, None, "finality_schema_migrated", FINALITY_SCHEMA_VERSION + ":" + review_reference)
            after = self._inspect_finality_schema(db)
            return {**after, "status": "migrated", "audit_event_added": True}

    @staticmethod
    def event(db: sqlite3.Connection, account: str | None, kind: str, reference: str) -> None:
        db.execute("INSERT INTO live_events(at,account_id,kind,reference) VALUES(?,?,?,?)", (stamp(), account, kind, reference))

    @staticmethod
    def queue_threshold_notices(db: sqlite3.Connection, account: str, exposure: int) -> None:
        if exposure >= 75 * USD:
            for recipient in ACCOUNTS:
                db.execute("INSERT OR IGNORE INTO live_notices(id,account_id,recipient,threshold) VALUES(?,?,?,75)", (str(uuid4()), account, recipient))

    def attest_account(self, evidence: Evidence) -> None:
        # Private operator interface. A caller cannot submit evidence through iOS.
        evidence = Evidence.model_validate(evidence.model_dump())
        with self.transaction() as db:
            existing = db.execute("SELECT 1 FROM live_accounts WHERE account_id=?", (evidence.account_id,)).fetchone()
            if existing:
                raise BudgetDenied("Existing account requires provider reconciliation, not baseline replacement")
            for (raw,) in db.execute("SELECT evidence FROM live_accounts"):
                prior = json.loads(raw)
                if prior["key_sha256"] == evidence.key_sha256 or prior["provider_account_reference"] == evidence.provider_account_reference:
                    raise BudgetDenied("Accounts must have independent verified provider identities and credentials")
            # Unattributed legacy charges cannot be silently ignored or split.
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='meta_policy'").fetchone():
                old = db.execute("SELECT baseline FROM meta_policy").fetchone()
                count = db.execute("SELECT COUNT(*) FROM meta_attempts").fetchone()[0]
                if (old and old[0] != 0) or count:
                    raise BudgetDenied("Legacy usage must be attributed and reconciled before account migration")
            db.execute("INSERT INTO live_accounts(account_id,evidence,anchor_gross) VALUES(?,?,?)", (evidence.account_id, evidence.model_dump_json(), evidence.gross_micro_usd))
            self.event(db, evidence.account_id, "account_attested", evidence.reference)

    def record_price(self, price: Price) -> None:
        price = Price.model_validate(price.model_dump())
        with self.transaction() as db:
            db.execute("INSERT INTO live_prices(version,snapshot) VALUES(?,?)", (price.version, price.model_dump_json()))
            self.event(db, None, "price_reviewed", price.reference)

    def approve_first_test(self, permit: FirstPermit) -> None:
        permit = FirstPermit.model_validate(permit.model_dump())
        with self.transaction() as db:
            if db.execute("SELECT 1 FROM live_permit").fetchone() or db.execute("SELECT 1 FROM controlled_permits").fetchone():
                raise BudgetDenied("Project first-test permit already exists and cannot be reset")
            self.verify_never_resumed(db)
            db.execute("INSERT INTO live_permit(id,permit) VALUES(1,?)", (permit.model_dump_json(),))
            self.event(db, permit.account_id, "first_test_approved", permit.spending_authority_reference)

    @staticmethod
    def verify_never_resumed(db: sqlite3.Connection) -> None:
        # A resume (backend/meta_resume.py) restores reviewed experiment spending only;
        # it must never reopen the one-request first-test or disabled dual-test policies.
        if db.execute("SELECT 1 FROM live_events WHERE kind='account_resumed'").fetchone():
            raise BudgetDenied("A resumed ledger never authorizes another first or controlled test")

    @staticmethod
    def verify_project_unfrozen(db: sqlite3.Connection) -> None:
        # A second account's existing permit must not bypass a provider breach
        # or reconciliation hold. Check in each transaction up to network claim.
        if db.execute("SELECT 1 FROM live_accounts WHERE frozen=1").fetchone():
            raise BudgetDenied("Frozen account blocks all project dispatch")

    @staticmethod
    def verify_prior_finalities(db: sqlite3.Connection, excluding_attempt: str = "") -> None:
        # Query the table even with no prior attempts: an old schema fails closed.
        rows = db.execute(
            "SELECT a.id,a.account_id,a.provider_id,a.actual,a.state,a.dispatched_at,f.evidence "
            "FROM live_attempts a LEFT JOIN live_finalities f ON f.attempt_id=a.id "
            "WHERE a.id != ?", (excluding_attempt,)
        )
        for attempt, account, provider, actual, state, dispatched, raw in rows:
            try:
                finality = InvoiceFinality.model_validate_json(raw)
                if (attempt != finality.attempt_id or account != finality.account_id
                        or provider != finality.provider_id or actual != finality.final_gross_micro_usd
                        or state != "settled" or dispatched is None
                        or finality.finalized_at < datetime.fromisoformat(dispatched)):
                    raise ValueError
            except (ValueError, TypeError):
                raise BudgetDenied("Prior provider invoice finality is unverified") from None

    def record_invoice_finality(self, finality: InvoiceFinality) -> None:
        finality = InvoiceFinality.model_validate(finality.model_dump())
        with self.transaction() as db:
            self.verify_project_unfrozen(db)
            row = db.execute(
                "SELECT account_id,provider_id,actual,state,dispatched_at FROM live_attempts WHERE id=?",
                (finality.attempt_id,),
            ).fetchone()
            if (not row or row[:4] != (finality.account_id, finality.provider_id,
                                      finality.final_gross_micro_usd, "settled")
                    or row[4] is None or finality.finalized_at < datetime.fromisoformat(row[4])):
                raise BudgetDenied("Finality must match settled provider usage and follow dispatch")
            raw = finality.model_dump_json()
            existing = db.execute("SELECT evidence FROM live_finalities WHERE attempt_id=?",
                                  (finality.attempt_id,)).fetchone()
            if existing:
                if existing[0] == raw:
                    return  # Identical import retry never changes evidence or costs.
                raise BudgetDenied("Provider finality evidence is immutable")
            db.execute("INSERT INTO live_finalities(attempt_id,evidence,recorded_at) VALUES(?,?,?)",
                       (finality.attempt_id, raw, stamp()))
            self.event(db, finality.account_id, "invoice_finality_attested", finality.attempt_id)

    def approve_controlled_test(self, permit: ControlledPermit) -> None:
        permit = ControlledPermit.model_validate(permit.model_dump())
        expected = "camera" if permit.account_id == ACCOUNTS[0] else "hydration"
        if permit.purpose != expected:
            raise BudgetDenied("Account owner and test purpose mismatch")
        with self.transaction() as db:
            if db.execute("SELECT 1 FROM live_permit").fetchone() or db.execute(
                "SELECT 1 FROM live_attempts a LEFT JOIN controlled_permits p "
                "ON p.account_id=a.account_id WHERE p.account_id IS NULL"
            ).fetchone():
                raise BudgetDenied("Legacy approval or prior attempt requires separate policy review")
            # Owners may approve independently, including the second owner later.
            # Never treat a reservation, ambiguous bill or frozen account as settled.
            self.verify_project_unfrozen(db)
            self.verify_never_resumed(db)
            self.verify_prior_finalities(db)
            if db.execute("SELECT 1 FROM live_attempts WHERE actual IS NULL").fetchone():
                raise BudgetDenied("Unresolved billing blocks another approval")
            db.execute("INSERT INTO controlled_permits(account_id,permit) VALUES(?,?)", (permit.account_id, permit.model_dump_json()))
            self.event(db, permit.account_id, "controlled_test_approved", permit.spending_authority_reference)

    @staticmethod
    def grant(db: sqlite3.Connection, account: str):
        controlled = db.execute("SELECT permit,spent FROM controlled_permits WHERE account_id=?", (account,)).fetchone()
        return controlled or db.execute("SELECT permit,spent FROM live_permit WHERE id=1").fetchone()

    def verify_purpose(self, account: str, purpose: str) -> None:
        with self.transaction() as db:
            _, _, permit = self._policy(db, account)
            if isinstance(permit, ControlledPermit) and permit.purpose != purpose:
                raise BudgetDenied("Permit does not authorize this feature")
            if not isinstance(permit, ControlledPermit) and purpose != "camera":
                raise BudgetDenied("Legacy permit only covers camera")

    def _policy(self, db: sqlite3.Connection, account: str) -> tuple[Evidence, Price, FirstPermit]:
        row = db.execute("SELECT evidence,frozen FROM live_accounts WHERE account_id=?", (account,)).fetchone()
        grant = self.grant(db, account)
        if not row or row[1] or not grant or grant[1]:
            raise BudgetDenied("Account approval unavailable, frozen or already spent")
        try:
            evidence = Evidence.model_validate_json(row[0])
            permit = parse_permit(grant[0])
            if permit.account_id != account or evidence.account_id != account:
                raise ValueError
            price_row = db.execute("SELECT snapshot FROM live_prices WHERE version=?", (permit.price_version,)).fetchone()
            if not price_row:
                raise ValueError
            price = Price.model_validate_json(price_row[0])
            if price.version != permit.price_version:
                raise ValueError
            return evidence, price, permit
        except ValueError:
            raise BudgetDenied("Evidence or pricing is invalid or expired") from None

    def verify_storage(self) -> None:
        try:
            info = os.stat(self.path, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
                raise OSError
        except OSError:
            raise BudgetDenied("Authoritative ledger must be an owned private regular file") from None

    def verify_credential(self, account: str, fingerprint: str) -> None:
        self.verify_storage()
        with self.transaction() as db:
            evidence, _, _ = self._policy(db, account)
            if fingerprint != evidence.key_sha256:
                raise BudgetDenied("Credential does not match this account's verified evidence")

    def quote(self, account: str, input_bound: int) -> tuple[Price, int]:
        self.verify_storage()
        if type(input_bound) is not int or not 1 <= input_bound <= MAX_INPUT_TOKENS:
            raise BudgetDenied("Unknown input token bound")
        with self.transaction() as db:
            evidence, price, permit = self._policy(db, account)
            maximum = price.cost(input_bound, OUTPUT_LIMIT) + evidence.extra_charge_bound_micro_usd
            if maximum > permit.maximum_micro_usd:
                raise BudgetDenied("Verified maximum exceeds approved first-test ceiling")
            return price, maximum

    def reserve_first(self, account: str, image_hash: str, input_bound: int) -> str:
        self.verify_storage()
        attempt = str(uuid4())
        with self.transaction() as db:
            self.verify_project_unfrozen(db)
            self.verify_prior_finalities(db)
            evidence, price, permit = self._policy(db, account)
            if image_hash != permit.image_sha256:
                raise BudgetDenied("Image does not match owner-approved permit")
            if type(input_bound) is not int or not 1 <= input_bound <= MAX_INPUT_TOKENS:
                raise BudgetDenied("Unknown input bound")
            maximum = price.cost(input_bound, OUTPUT_LIMIT) + evidence.extra_charge_bound_micro_usd
            if maximum > permit.maximum_micro_usd:
                raise BudgetDenied("Verified maximum exceeds approved ceiling")
            if db.execute("SELECT 1 FROM live_attempts WHERE actual IS NULL").fetchone():
                raise BudgetDenied("Prior billing unresolved; no second request")
            exposure = evidence.gross_micro_usd + db.execute("SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM live_attempts WHERE account_id=?", (account,)).fetchone()[0]
            proposed = exposure + maximum
            if proposed >= 150 * USD or proposed >= 120 * USD:
                raise BudgetDenied("Account operational cutoff reached")
            if proposed >= 100 * USD and not permit.further_spend_approval_reference:
                raise BudgetDenied("Account needs explicit $100 further-spend approval")
            if proposed - evidence.gross_micro_usd > evidence.credits_remaining_micro_usd:
                raise BudgetDenied("Verified account credits exhausted")
            if isinstance(permit, ControlledPermit):
                db.execute("UPDATE controlled_permits SET spent=1 WHERE account_id=?", (account,))
            else:
                db.execute("UPDATE live_permit SET spent=1 WHERE id=1")
            db.execute("INSERT INTO live_attempts(id,account_id,price,reserved,state,created_at,input_bound) VALUES(?,?,?,?,?,?,?)", (attempt, account, price.model_dump_json(), maximum, "reserved", stamp(), input_bound))
            self.event(db, account, "reserved", attempt)
            self.queue_threshold_notices(db, account, proposed)
            return attempt

    def mark_dispatched(self, attempt: str, payload_sha256: str) -> "DispatchTicket":
        if not re.fullmatch(r"[a-f0-9]{64}", payload_sha256):
            raise BudgetDenied("Exact payload fingerprint required")
        nonce = str(uuid4())
        with self.transaction() as db:
            self.verify_project_unfrozen(db)
            self.verify_prior_finalities(db, excluding_attempt=attempt)
            row = db.execute("SELECT account_id,price,state FROM live_attempts WHERE id=?", (attempt,)).fetchone()
            if not row or row[2] != "reserved":
                raise BudgetDenied("Attempt cannot dispatch twice")
            # Evidence can expire while waiting; no dispatch on an expired queue.
            account = db.execute("SELECT evidence,frozen FROM live_accounts WHERE account_id=?", (row[0],)).fetchone()
            permit = self.grant(db, row[0])
            try:
                Evidence.model_validate_json(account[0]); Price.model_validate_json(row[1]); parse_permit(permit[0])
            except (ValueError, TypeError):
                raise BudgetDenied("Approval expired before dispatch") from None
            if account[1] or db.execute("SELECT 1 FROM live_notices WHERE delivered_at IS NULL").fetchone():
                raise BudgetDenied("Frozen account or undelivered developer notices")
            db.execute("UPDATE live_attempts SET state='dispatched',dispatched_at=?,payload_sha256=?,ticket_nonce=? WHERE id=?", (stamp(), payload_sha256, nonce, attempt))
            self.event(db, row[0], "dispatched", attempt)
        return DispatchTicket(self, attempt, nonce)

    def claim_send(self, attempt: str, nonce: str, payload_sha256: str, input_bound: int, credential_fingerprint: str) -> None:
        self.verify_storage()
        with self.transaction() as db:
            self.verify_project_unfrozen(db)
            self.verify_prior_finalities(db, excluding_attempt=attempt)
            row = db.execute("SELECT account_id,state,ticket_nonce,payload_sha256,price,input_bound FROM live_attempts WHERE id=?", (attempt,)).fetchone()
            if not row or row[1:4] != ("dispatched", nonce, payload_sha256):
                raise BudgetDenied("No matching one-use network dispatch ticket")
            account = db.execute("SELECT evidence,frozen FROM live_accounts WHERE account_id=?", (row[0],)).fetchone()
            permit = self.grant(db, row[0])
            try:
                current_account = Evidence.model_validate_json(account[0]); Price.model_validate_json(row[4]); parse_permit(permit[0])
                if current_account.key_sha256 != credential_fingerprint or type(input_bound) is not int or input_bound != row[5]:
                    raise ValueError
            except (ValueError, TypeError):
                raise BudgetDenied("Expired dispatch evidence") from None
            if account[1]:
                raise BudgetDenied("Account frozen before network send")
            db.execute("UPDATE live_attempts SET state='sending',ticket_nonce=NULL WHERE id=?", (attempt,))
            self.event(db, row[0], "network_send_claimed", attempt)

    def quarantine(self, attempt: str) -> None:
        with self.transaction() as db:
            row = db.execute("SELECT account_id FROM live_attempts WHERE id=?", (attempt,)).fetchone()
            if not row:
                raise BudgetDenied("Unknown attempt")
            db.execute("UPDATE live_accounts SET frozen=1 WHERE account_id=?", (row[0],))
            db.execute("UPDATE live_attempts SET state='unresolved' WHERE id=? AND actual IS NULL", (attempt,))
            self.event(db, row[0], "reconciliation_required", attempt)

    def settle_provider_reply(self, attempt: str, reply: "ProviderReply") -> None:
        # Only gateway transport replies reach here. No API accepts usage/costs.
        blocked = False
        with self.transaction() as db:
            row = db.execute("SELECT account_id,price,reserved,state,input_bound FROM live_attempts WHERE id=? AND actual IS NULL", (attempt,)).fetchone()
            if not row or row[3] != "sending":
                raise BudgetDenied("No unsettled dispatched attempt")
            try:
                body = reply.body
                usage = body["usage"]
                inputs, outputs = usage["input_tokens"], usage["output_tokens"]
                cached = usage["input_tokens_details"]["cached_tokens"]
                total = usage["total_tokens"]
                identifier = body["id"]
                if body.get("model") != MODEL or not isinstance(identifier, str) or not re.fullmatch(r"resp_[A-Za-z0-9_-]{1,180}", identifier):
                    raise ValueError
                if any(type(x) is not int or x < 0 for x in (inputs, outputs, cached, total)) or cached > inputs or total != inputs + outputs:
                    raise ValueError
                if db.execute("SELECT 1 FROM live_attempts WHERE account_id=? AND provider_id=?", (row[0], identifier)).fetchone():
                    raise ValueError
                # Expiry blocks new dispatch, not accounting for an existing charge.
                snapshot = json.loads(row[1])
                if snapshot.get("model") != MODEL or snapshot.get("input_micro_per_million") != 1250000 or snapshot.get("cached_micro_per_million") != 150000 or snapshot.get("output_micro_per_million") != 4250000:
                    raise ValueError
                amount = ((inputs - cached) * snapshot["input_micro_per_million"] + cached * snapshot["cached_micro_per_million"] + outputs * snapshot["output_micro_per_million"] + 999999) // 1000000
                evidence = json.loads(db.execute("SELECT evidence FROM live_accounts WHERE account_id=?", (row[0],)).fetchone()[0])
                # Extra categories cannot be guessed from usage. Nonzero overhead
                # requires reconciliation instead of optimistic zero settlement.
                if evidence["extra_charge_bound_micro_usd"] != 0:
                    db.execute("UPDATE live_attempts SET provider_id=?,usage=? WHERE id=?", (identifier, json.dumps({"input_tokens": inputs, "output_tokens": outputs, "cached_tokens": cached, "total_tokens": total}), attempt))
                    raise ValueError
                db.execute("UPDATE live_attempts SET actual=?,provider_id=?,usage=?,state='settled' WHERE id=?", (amount, identifier, json.dumps({"input_tokens": inputs, "output_tokens": outputs, "cached_tokens": cached, "total_tokens": total}, sort_keys=True), attempt))
                exposure = evidence["gross_micro_usd"] + db.execute("SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM live_attempts WHERE account_id=?", (row[0],)).fetchone()[0]
                self.queue_threshold_notices(db, row[0], exposure)
                blocked = amount > row[2] or inputs > row[4] or outputs > OUTPUT_LIMIT
                if blocked:
                    db.execute("UPDATE live_accounts SET frozen=1 WHERE account_id=?", (row[0],))
                self.event(db, row[0], "settled_over_bound" if blocked else "settled", attempt)
            except (ValueError, KeyError, TypeError, AttributeError):
                db.execute("UPDATE live_attempts SET state='unresolved' WHERE id=?", (attempt,))
                db.execute("UPDATE live_accounts SET frozen=1 WHERE account_id=?", (row[0],))
                self.event(db, row[0], "usage_unverified", attempt)
                blocked = True
        if blocked:
            raise BudgetDenied("Provider usage unresolved or exceeded reservation")

    def mark_recognized(self, attempt: str) -> None:
        with self.transaction() as db:
            if db.execute("UPDATE live_attempts SET recognized=1 WHERE id=? AND state='settled'", (attempt,)).rowcount != 1:
                raise BudgetDenied("Recognition lacks settled usage")

    def receipt(self, attempt: str) -> dict:
        with self.transaction() as db:
            row = db.execute("SELECT account_id,provider_id FROM live_attempts WHERE id=? AND state='settled' AND recognized=1", (attempt,)).fetchone()
            if not row:
                raise BudgetDenied("No verified successful recognition receipt")
            return {"account_id": row[0], "provider_id": row[1], "model": MODEL}

    def notices(self) -> list[dict]:
        with self.transaction() as db:
            return [dict(zip(("id", "account_id", "recipient", "threshold", "delivered_at", "delivery_reference"), row)) for row in db.execute("SELECT id,account_id,recipient,threshold,delivered_at,delivery_reference FROM live_notices ORDER BY id")]

    def notice_delivered(self, identifier: str, receipt: str) -> None:
        if not receipt or len(receipt) > 200:
            raise BudgetDenied("Delivery receipt required")
        with self.transaction() as db:
            row = db.execute("SELECT account_id FROM live_notices WHERE id=?", (identifier,)).fetchone()
            if not row:
                raise BudgetDenied("Unknown notice")
            db.execute("UPDATE live_notices SET delivered_at=?,delivery_reference=? WHERE id=? AND delivered_at IS NULL", (stamp(), receipt, identifier))
            self.event(db, row[0], "notice_delivered", identifier + ":" + receipt)

    def record_reconciliation_reference(self, account: str, reference: str) -> None:
        if account not in ACCOUNTS or not reference.strip():
            raise BudgetDenied("Account-specific evidence required")
        with self.transaction() as db:
            self.event(db, account, "unverified_reconciliation_reference", reference)
        # Never release reservations or unfreeze from caller-supplied cost figures.

    def project_view(self) -> dict:
        with self.transaction() as db:
            accounts = []
            for account, evidence, frozen in db.execute("SELECT account_id,evidence,frozen FROM live_accounts ORDER BY account_id"):
                settled, reserved = db.execute("SELECT COALESCE(SUM(actual),0),COALESCE(SUM(CASE WHEN actual IS NULL THEN reserved ELSE 0 END),0) FROM live_attempts WHERE account_id=?", (account,)).fetchone()
                accounts.append({"account_id": account, "gross_micro_usd": json.loads(evidence)["gross_micro_usd"] + settled, "reserved_micro_usd": reserved, "frozen": bool(frozen)})
            return {"accounts": accounts, "status": "complete" if len(accounts) == 2 else "incomplete", "project_gross_micro_usd": sum(a["gross_micro_usd"] for a in accounts) if len(accounts) == 2 else None, "known_accounts_gross_micro_usd": sum(a["gross_micro_usd"] for a in accounts), "project_reserved_micro_usd": sum(a["reserved_micro_usd"] for a in accounts), "credits_transferable": False}


@dataclass(frozen=True)
class DispatchTicket:
    ledger: AccountLedger
    attempt: str
    nonce: str

    def claim(self, payload: dict, *, input_bound: int, credential_fingerprint: str) -> None:
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        self.ledger.claim_send(self.attempt, self.nonce, digest, input_bound, credential_fingerprint)
