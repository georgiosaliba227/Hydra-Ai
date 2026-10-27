"""Account-isolated v2 financial ledger. No network, provider keys or image storage."""
from datetime import datetime, timezone
from dataclasses import dataclass
import os
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
    extra_charge_bound_micro_usd: StrictInt = Field(ge=0, le=CAP)

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

        os.chmod(self.path, 0o600)

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
            if db.execute("SELECT 1 FROM live_permit").fetchone():
                raise BudgetDenied("Project first-test permit already exists and cannot be reset")
            db.execute("INSERT INTO live_permit(id,permit) VALUES(1,?)", (permit.model_dump_json(),))
            self.event(db, permit.account_id, "first_test_approved", permit.spending_authority_reference)

    def _policy(self, db: sqlite3.Connection, account: str) -> tuple[Evidence, Price, FirstPermit]:
        row = db.execute("SELECT evidence,frozen FROM live_accounts WHERE account_id=?", (account,)).fetchone()
        grant = db.execute("SELECT permit,spent FROM live_permit WHERE id=1").fetchone()
        if not row or row[1] or not grant or grant[1]:
            raise BudgetDenied("Account approval unavailable, frozen or already spent")
        try:
            evidence = Evidence.model_validate_json(row[0])
            permit = FirstPermit.model_validate_json(grant[0])
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
            if maximum > CAP:
                raise BudgetDenied("Verified maximum exceeds the $0.25 first-test ceiling")
            return price, maximum

    def reserve_first(self, account: str, image_hash: str, input_bound: int) -> str:
        self.verify_storage()
        attempt = str(uuid4())
        with self.transaction() as db:
            evidence, price, permit = self._policy(db, account)
            if image_hash != permit.image_sha256:
                raise BudgetDenied("Image does not match owner-approved permit")
            if type(input_bound) is not int or not 1 <= input_bound <= MAX_INPUT_TOKENS:
                raise BudgetDenied("Unknown input bound")
            maximum = price.cost(input_bound, OUTPUT_LIMIT) + evidence.extra_charge_bound_micro_usd
            if maximum > CAP:
                raise BudgetDenied("Verified maximum exceeds $0.25")
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
            row = db.execute("SELECT account_id,price,state FROM live_attempts WHERE id=?", (attempt,)).fetchone()
            if not row or row[2] != "reserved":
                raise BudgetDenied("Attempt cannot dispatch twice")
            # Evidence can expire while waiting; no dispatch on an expired queue.
            account = db.execute("SELECT evidence,frozen FROM live_accounts WHERE account_id=?", (row[0],)).fetchone()
            permit = db.execute("SELECT permit FROM live_permit WHERE id=1").fetchone()
            try:
                Evidence.model_validate_json(account[0]); Price.model_validate_json(row[1]); FirstPermit.model_validate_json(permit[0])
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
            row = db.execute("SELECT account_id,state,ticket_nonce,payload_sha256,price,input_bound FROM live_attempts WHERE id=?", (attempt,)).fetchone()
            if not row or row[1:4] != ("dispatched", nonce, payload_sha256):
                raise BudgetDenied("No matching one-use network dispatch ticket")
            account = db.execute("SELECT evidence,frozen FROM live_accounts WHERE account_id=?", (row[0],)).fetchone()
            permit = db.execute("SELECT permit FROM live_permit WHERE id=1").fetchone()
            try:
                current_account = Evidence.model_validate_json(account[0]); Price.model_validate_json(row[4]); FirstPermit.model_validate_json(permit[0])
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
