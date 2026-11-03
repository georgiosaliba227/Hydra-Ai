"""One owner-authorized synthetic Wonder attempt; ordinary financial gates stay intact.

This policy acknowledges unverified extras rather than claiming a hard provider
cap. It appends to the existing authority and never rewrites prior history.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from .hydration_analysis import build_analysis
from .meta_accounts import AccountLedger, FINANCIAL_DDL, _canonical_schema, stamp
from .meta_budget import BudgetDenied
from .meta_provider import ProviderReply, strict_json
from .recognition import RecognitionUnavailable
from .wonder_experiment import LIVE_SCHEMA, WonderMetaTransport
from .wonder_hydration import input_bound, payload_sha256
from .workout_forecasts import WorkoutForecastInput
from . import wonder_analysis

ACCOUNT = "georgiosaliba227"
MODEL = "muse-wonder-1.0"
POLICY = "wonder-owner-once-v1"
ENVELOPE_VERSION = "wonder-owner-once-result-v1"
PAYLOAD_HASH = "12ef839f44757b452034632ef91c50ff44455e6c02c99104230f4c46d02ab34c"
TOKEN_RESERVATION = 250_000
INPUT_BOUND = 4750
OUTPUT_BOUND = 2048
TOKEN_BOUND_COST = 59960
INPUT_PRICE = 4_000_000
OUTPUT_PRICE = 20_000_000
AUTH_EVENT = "wonder_owner_once_authorized"
CONSUME_EVENT = "wonder_owner_once_consumed"
OWN_EVENTS = frozenset((AUTH_EVENT, CONSUME_EVENT, "wonder_owner_once_dispatched",
    "wonder_owner_once_send_claimed", "wonder_owner_once_usage_recorded", "wonder_owner_once_unresolved",
    "wonder_owner_once_output_rejected", "wonder_owner_once_result_saved", "wonder_owner_once_result_save_failed"))
REFERENCE = Annotated[str, Field(strict=True, min_length=1, max_length=500)]
FINGERPRINT = Annotated[str, Field(strict=True, pattern=r"^[a-f0-9]{64}$")]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fixed_facts() -> dict:
    request = WorkoutForecastInput(mode="synthetic_demo", timezone="America/New_York")
    analysis = build_analysis(request, (), generated_at=datetime(2026, 11, 3, 12, tzinfo=timezone.utc))
    return wonder_analysis.build_facts(analysis)


def fixed_payload() -> dict:
    payload = wonder_analysis.analysis_payload(fixed_facts())
    if payload_sha256(payload) != PAYLOAD_HASH or input_bound(payload) != INPUT_BOUND:
        raise BudgetDenied("Pinned synthetic payload changed; a new policy review is required")
    return payload


class OwnerOnceAuthorization(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: Literal["wonder-owner-once-v1"] = POLICY
    account_id: Literal["georgiosaliba227"] = ACCOUNT
    key_sha256: FINGERPRINT
    historical_snapshot_sha256: FINGERPRINT
    payload_sha256: Literal[PAYLOAD_HASH] = PAYLOAD_HASH
    input_bound: Literal[4750] = INPUT_BOUND
    output_bound: Literal[2048] = OUTPUT_BOUND
    token_reservation_micro_usd: Literal[250000] = TOKEN_RESERVATION
    published_token_bound_micro_usd: Literal[59960] = TOKEN_BOUND_COST
    input_micro_per_million: Literal[4000000] = INPUT_PRICE
    output_micro_per_million: Literal[20000000] = OUTPUT_PRICE
    valid_until: datetime
    owner_authorization_reference: REFERENCE
    prior_billing_waiver_reference: REFERENCE
    price_reference: REFERENCE
    credit_observation_reference: REFERENCE
    observed_credits_micro_usd: StrictInt = Field(ge=TOKEN_RESERVATION, le=150_000_000)
    risk_acceptance_reference: REFERENCE
    accept_unverified_extras: Literal[True]

    @field_validator("accept_unverified_extras", mode="before")
    @classmethod
    def explicit_risk_acceptance(cls, value):
        if value is not True:
            raise ValueError("Explicit owner acknowledgement of unverified extras is required")
        return True

    @field_validator("*", mode="after")
    @classmethod
    def meaningful_references(cls, value, info):
        if info.field_name.endswith("reference") and not value.strip():
            raise ValueError("Meaningful reference required")
        return value

    @model_validator(mode="after")
    def current(self):
        if (self.valid_until.tzinfo is None or not utc_now() < self.valid_until <= utc_now() + timedelta(hours=1)):
            raise ValueError("Authorization must expire within one hour")
        return self


def _schema(db) -> None:
    if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise BudgetDenied("Existing financial authority failed integrity validation")
    objects = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master").fetchall()
    found = {name: sql for kind, name, _, sql in objects if kind == "table"}
    for name, expected in FINANCIAL_DDL.items():
        if name not in found or _canonical_schema(found[name] or "") != _canonical_schema(expected):
            raise BudgetDenied("Reviewed existing financial schema required")
    allowed = {_canonical_schema(sql) for sql in LIVE_SCHEMA if sql.startswith("CREATE TRIGGER")}
    for kind, _, table, sql in objects:
        if kind == "trigger" and _canonical_schema(sql or "") not in allowed:
            raise BudgetDenied("Unknown financial side effect rejected")
        if kind == "index" and sql is not None and table in FINANCIAL_DDL:
            raise BudgetDenied("Unknown financial index rejected")


def _historical_snapshot(db, *, excluding_attempt: str | None = None) -> str:
    """Hash existing financial records without exposing their private contents."""
    objects = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
    snapshot = []
    for kind, name, table, sql in objects:
        if table == "beverages":
            continue  # Beverage history is unrelated to financial admission.
        entry = [kind, name, table, sql]
        if kind == "table":
            quoted = '"' + name.replace('"', '""') + '"'
            columns = [item[1] for item in db.execute("PRAGMA table_info(" + quoted + ")")]
            rows = db.execute("SELECT * FROM " + quoted).fetchall()
            if name == "live_events":
                kind_index = columns.index("kind")
                rows = [row for row in rows if row[kind_index] not in OWN_EVENTS]
            if name == "live_attempts" and excluding_attempt:
                id_index = columns.index("id")
                rows = [row for row in rows if row[id_index] != excluding_attempt]
            safe_rows = [[{"bytes_hex": value.hex()} if isinstance(value, bytes) else value for value in row] for row in rows]
            entry.append(sorted(safe_rows, key=canonical))
        snapshot.append(entry)
    return hashlib.sha256(canonical(snapshot).encode()).hexdigest()


class OwnerOnceAuthority:
    def __init__(self, authority: AccountLedger):
        if type(authority) is not AccountLedger:
            raise BudgetDenied("Existing AccountLedger authority required")
        self.authority = authority

    @contextmanager
    def _transaction(self, *, write: bool = False):
        with self.authority._existing_migration_database(write=write) as db:
            _schema(db)
            yield db

    @staticmethod
    def _account(db):
        row = db.execute("SELECT evidence,anchor_gross,frozen FROM live_accounts WHERE account_id=?", (ACCOUNT,)).fetchone()
        try:
            evidence = strict_json(row[0])
            key = evidence["key_sha256"]
            if not re.fullmatch(r"[a-f0-9]{64}", key) or type(row[1]) is not int or row[1] < 0 or row[2] != 1:
                raise ValueError
            return evidence, row[1], key
        except (ValueError, TypeError, KeyError, IndexError):
            raise BudgetDenied("Existing frozen owner account and key binding required") from None

    @staticmethod
    def _exposure(db, *, excluding_attempt=None, credits: int | None = None) -> None:
        _, baseline, _ = OwnerOnceAuthority._account(db)
        total = 0
        for attempt, account, state, reserved, actual in db.execute("SELECT id,account_id,state,reserved,actual FROM live_attempts"):
            if attempt == excluding_attempt:
                continue
            if state not in ("billing_pending", "unresolved", "settled"):
                raise BudgetDenied("Active or unknown historical attempt cannot be waived")
            if (type(reserved) is not int or reserved <= 0 or
                    (actual is not None and (type(actual) is not int or actual < 0)) or (state == "settled" and actual is None)):
                raise BudgetDenied("Historical exposure is unavailable")
            if account == ACCOUNT:
                total += max(reserved, actual or 0)
        if total + TOKEN_RESERVATION > 30_000_000:
            raise BudgetDenied("Preserved reservations exhaust the experiment allocation")
        if baseline + total + TOKEN_RESERVATION >= 75_000_000 or baseline + total + TOKEN_RESERVATION >= 120_000_000:
            raise BudgetDenied("Account exposure reaches a protected threshold")
        if credits is not None and total + TOKEN_RESERVATION > credits:
            raise BudgetDenied("Observed credits do not cover preserved reservations")

    @staticmethod
    def _events(db, kind: str):
        return db.execute("SELECT account_id,reference FROM live_events WHERE kind=? ORDER BY id", (kind,)).fetchall()

    def prepare(self) -> dict:
        fixed_payload()
        with self._transaction() as db:
            _, _, key = self._account(db)
            self._exposure(db)
            snapshot = _historical_snapshot(db)
        return {"version": POLICY, "account_id": ACCOUNT, "key_sha256": key,
            "historical_snapshot_sha256": snapshot, "payload_sha256": PAYLOAD_HASH,
            "input_bound": INPUT_BOUND, "output_bound": OUTPUT_BOUND,
            "token_reservation_micro_usd": TOKEN_RESERVATION, "published_token_bound_micro_usd": TOKEN_BOUND_COST,
            "input_micro_per_million": INPUT_PRICE, "output_micro_per_million": OUTPUT_PRICE,
            "valid_until": (utc_now() + timedelta(minutes=55)).isoformat(),
            "owner_authorization_reference": "", "prior_billing_waiver_reference": "", "price_reference": "",
            "credit_observation_reference": "", "observed_credits_micro_usd": None,
            "risk_acceptance_reference": "", "accept_unverified_extras": False}

    def authorize(self, descriptor: OwnerOnceAuthorization) -> None:
        descriptor = OwnerOnceAuthorization.model_validate(descriptor.model_dump())
        fixed_payload()
        with self._transaction(write=True) as db:
            descriptor = OwnerOnceAuthorization.model_validate(descriptor.model_dump())
            if self._events(db, AUTH_EVENT) or self._events(db, CONSUME_EVENT):
                raise BudgetDenied("The singleton owner authorization already exists")
            _, _, key = self._account(db)
            if key != descriptor.key_sha256 or _historical_snapshot(db) != descriptor.historical_snapshot_sha256:
                raise BudgetDenied("Owner identity or historical snapshot changed")
            self._exposure(db, credits=descriptor.observed_credits_micro_usd)
            self.authority.event(db, ACCOUNT, AUTH_EVENT, descriptor.model_dump_json())

    def _authorization(self, db) -> OwnerOnceAuthorization:
        events = self._events(db, AUTH_EVENT)
        if len(events) != 1 or events[0][0] != ACCOUNT:
            raise BudgetDenied("Exactly one owner authorization is required")
        try:
            return OwnerOnceAuthorization.model_validate_json(events[0][1])
        except ValueError:
            raise BudgetDenied("Owner authorization is invalid or expired") from None

    def _current(self, db, attempt: str):
        descriptor = self._authorization(db)
        consumed = self._events(db, CONSUME_EVENT)
        if len(consumed) != 1 or consumed[0][0] != ACCOUNT or strict_json(consumed[0][1]) != {"attempt_id": attempt}:
            raise BudgetDenied("Attempt does not own the consumed authorization")
        _, _, key = self._account(db)
        if key != descriptor.key_sha256 or _historical_snapshot(db, excluding_attempt=attempt) != descriptor.historical_snapshot_sha256:
            raise BudgetDenied("Historical financial state changed")
        self._exposure(db, excluding_attempt=attempt, credits=descriptor.observed_credits_micro_usd)
        row = db.execute("SELECT state,payload_sha256,input_bound,reserved,actual,price,ticket_nonce FROM live_attempts WHERE id=? AND account_id=?", (attempt, ACCOUNT)).fetchone()
        if (not row or row[1:5] != (PAYLOAD_HASH, INPUT_BOUND, TOKEN_RESERVATION, None)
                or row[5] != descriptor.model_dump_json()):
            raise BudgetDenied("Owner attempt no longer matches its authorization")
        return descriptor, row

    def _reserve(self, credential_fingerprint: str) -> str:
        with self._transaction(write=True) as db:
            descriptor = self._authorization(db)
            if self._events(db, CONSUME_EVENT):
                raise BudgetDenied("The owner authorization is permanently consumed")
            _, _, key = self._account(db)
            if descriptor.key_sha256 != key or credential_fingerprint != key:
                raise BudgetDenied("Current credential does not match the owner authorization")
            if _historical_snapshot(db) != descriptor.historical_snapshot_sha256:
                raise BudgetDenied("Historical financial state changed")
            self._exposure(db, credits=descriptor.observed_credits_micro_usd)
            attempt = str(uuid4())
            db.execute("INSERT INTO live_attempts(id,account_id,price,reserved,state,input_bound,created_at,payload_sha256) VALUES(?,?,?,?,?,?,?,?)",
                (attempt, ACCOUNT, descriptor.model_dump_json(), TOKEN_RESERVATION, "owner_once_reserved", INPUT_BOUND, stamp(), PAYLOAD_HASH))
            self.authority.event(db, ACCOUNT, CONSUME_EVENT, canonical({"attempt_id": attempt}))
            return attempt

    def _dispatch(self, attempt: str) -> "OwnerOnceTicket":
        with self._transaction(write=True) as db:
            _, row = self._current(db, attempt)
            if row[0] != "owner_once_reserved":
                raise BudgetDenied("Attempt cannot dispatch twice")
            nonce = str(uuid4())
            db.execute("UPDATE live_attempts SET state='owner_once_dispatched',dispatched_at=?,ticket_nonce=? WHERE id=?", (stamp(), nonce, attempt))
            self.authority.event(db, ACCOUNT, "wonder_owner_once_dispatched", attempt)
        return OwnerOnceTicket(self, attempt, nonce)

    def claim(self, attempt: str, nonce: str, payload: dict, bound: int, credential: str) -> None:
        if payload != fixed_payload() or type(bound) is not int or bound != INPUT_BOUND:
            raise BudgetDenied("Only the exact bounded synthetic payload is authorized")
        with self._transaction(write=True) as db:
            descriptor, row = self._current(db, attempt)
            if row[0] != "owner_once_dispatched" or row[6] != nonce or credential != descriptor.key_sha256:
                raise BudgetDenied("No matching one-use owner network ticket")
            db.execute("UPDATE live_attempts SET state='owner_once_sending',ticket_nonce=NULL WHERE id=?", (attempt,))
            self.authority.event(db, ACCOUNT, "wonder_owner_once_send_claimed", attempt)

    def _record_reply(self, attempt: str, reply: ProviderReply) -> dict:
        usage = checked_usage(reply)
        with self._transaction(write=True) as db:
            row = db.execute("SELECT state FROM live_attempts WHERE id=? AND account_id=?", (attempt, ACCOUNT)).fetchone()
            if row != ("owner_once_sending",):
                raise BudgetDenied("No sending owner attempt")
            if db.execute("SELECT 1 FROM live_attempts WHERE provider_id=? AND id!=?", (reply.body["id"], attempt)).fetchone():
                raise BudgetDenied("Provider response identity is already recorded")
            db.execute("UPDATE live_attempts SET state='billing_pending',provider_id=?,usage=? WHERE id=?",
                (reply.body["id"], canonical(usage), attempt))
            self.authority.event(db, ACCOUNT, "wonder_owner_once_usage_recorded", attempt)
        return usage

    def _record_failure(self, attempt: str, *, reply: ProviderReply | None, usage_recorded: bool,
                        output_validated: bool) -> None:
        with self._transaction(write=True) as db:
            if usage_recorded:
                event = "wonder_owner_once_result_save_failed" if output_validated else "wonder_owner_once_output_rejected"
                self.authority.event(db, ACCOUNT, event, attempt)
            else:
                # Retain attributable response identity/usage for reconciliation,
                # while making no claim that malformed usage proves a charge.
                body = reply.body if isinstance(reply, ProviderReply) and isinstance(reply.body, dict) else {}
                identifier = body.get("id")
                if (isinstance(identifier, str) and re.fullmatch(r"resp_[A-Za-z0-9_-]{1,180}", identifier)
                        and not db.execute("SELECT 1 FROM live_attempts WHERE provider_id=? AND id!=?", (identifier, attempt)).fetchone()):
                    db.execute("UPDATE live_attempts SET provider_id=? WHERE id=?", (identifier, attempt))
                try:
                    raw_usage = canonical(body.get("usage"))
                    if len(raw_usage.encode()) <= 16384:
                        db.execute("UPDATE live_attempts SET usage=? WHERE id=?", (raw_usage, attempt))
                except (ValueError, TypeError):
                    pass
                db.execute("UPDATE live_attempts SET state='unresolved',ticket_nonce=NULL WHERE id=? AND actual IS NULL AND state!='billing_pending'", (attempt,))
                self.authority.event(db, ACCOUNT, "wonder_owner_once_unresolved", attempt)

    def run(self, transport, result_path: Path) -> dict:
        _private_destination(result_path, must_be_absent=True)
        _private_destination(Path(result_path).with_name(Path(result_path).name + ".sha256"), must_be_absent=True)
        payload = fixed_payload()
        if transport.input_bound(payload) != INPUT_BOUND:
            raise BudgetDenied("Transport input bound changed")
        attempt = self._reserve(transport.credential_fingerprint)
        usage_recorded = False
        output_validated = False
        reply = None
        try:
            ticket = self._dispatch(attempt)
            reply = transport.generate(payload, ticket)
            usage = self._record_reply(attempt, reply)
            usage_recorded = True
            result = wonder_analysis.checked_result(reply, fixed_facts())
            output_validated = True
            envelope = {"version": ENVELOPE_VERSION, "mode": "synthetic_demo", "generated_at": stamp(),
                "result": result, "receipt": {"account_id": ACCOUNT, "attempt_id": attempt, "model": MODEL,
                    "payload_sha256": PAYLOAD_HASH, **usage, "token_reservation_micro_usd": TOKEN_RESERVATION,
                    "published_token_bound_micro_usd": TOKEN_BOUND_COST, "provider_invoice_final": False,
                    "provider_extras_bounded": False, "state": "billing_pending"}}
            validate_envelope(envelope)
            save_result(result_path, envelope)
            with self._transaction(write=True) as db:
                self.authority.event(db, ACCOUNT, "wonder_owner_once_result_saved", canonical({"attempt_id": attempt,
                    "result_sha256": hashlib.sha256(canonical(envelope).encode()).hexdigest()}))
            return envelope
        except Exception:
            try:
                self._record_failure(attempt, reply=reply, usage_recorded=usage_recorded,
                                     output_validated=output_validated)
            except Exception:
                pass  # The consumed authorization and reservation remain durable.
            raise RecognitionUnavailable() from None


@dataclass(frozen=True)
class OwnerOnceTicket:
    ledger: OwnerOnceAuthority
    attempt: str
    nonce: str

    def claim(self, payload: dict, *, input_bound: int, credential_fingerprint: str) -> None:
        self.ledger.claim(self.attempt, self.nonce, payload, input_bound, credential_fingerprint)


class OwnerOnceMetaTransport(WonderMetaTransport):
    ticket_type = OwnerOnceTicket

    def validate_payload(self, payload: dict) -> None:
        if payload != fixed_payload():
            raise ValueError("Only the pinned synthetic owner payload is supported")


def checked_usage(reply: ProviderReply) -> dict:
    try:
        body = reply.body
        identifier, usage = body["id"], body["usage"]
        inputs, outputs, total = (usage[key] for key in ("input_tokens", "output_tokens", "total_tokens"))
        cached = usage["input_tokens_details"]["cached_tokens"]
        if (reply.status != 200 or body["model"] != MODEL or not isinstance(identifier, str)
                or not re.fullmatch(r"resp_[A-Za-z0-9_-]{1,180}", identifier)
                or any(type(value) is not int or value < 0 for value in (inputs, outputs, total, cached))
                or inputs > INPUT_BOUND or outputs > OUTPUT_BOUND or total != inputs + outputs or cached > inputs):
            raise ValueError
        return {"input_tokens": inputs, "output_tokens": outputs, "cached_tokens": cached,
                "usage_derived_cost_micro_usd": (inputs * INPUT_PRICE + outputs * OUTPUT_PRICE + 999_999) // 1_000_000}
    except (TypeError, KeyError, ValueError, AttributeError):
        raise RecognitionUnavailable() from None


def validate_envelope(envelope: dict) -> dict:
    try:
        if set(envelope) != {"version", "mode", "generated_at", "result", "receipt"}:
            raise ValueError
        if envelope["version"] != ENVELOPE_VERSION or envelope["mode"] != "synthetic_demo":
            raise ValueError
        generated = datetime.fromisoformat(envelope["generated_at"].replace("Z", "+00:00"))
        if generated.tzinfo is None or generated.utcoffset() != timedelta(0):
            raise ValueError
        receipt = envelope["receipt"]
        fixed = {"account_id": ACCOUNT, "model": MODEL, "payload_sha256": PAYLOAD_HASH,
            "token_reservation_micro_usd": TOKEN_RESERVATION, "published_token_bound_micro_usd": TOKEN_BOUND_COST,
            "provider_invoice_final": False, "provider_extras_bounded": False, "state": "billing_pending"}
        if set(receipt) != {*fixed, "attempt_id", "input_tokens", "output_tokens", "cached_tokens", "usage_derived_cost_micro_usd"}:
            raise ValueError
        for key, value in fixed.items():
            if type(receipt[key]) is not type(value) or receipt[key] != value:
                raise ValueError
        if str(UUID(receipt["attempt_id"])) != receipt["attempt_id"]:
            raise ValueError
        inputs, outputs, cached, cost = (receipt[key] for key in ("input_tokens", "output_tokens", "cached_tokens", "usage_derived_cost_micro_usd"))
        if (any(type(value) is not int or value < 0 for value in (inputs, outputs, cached, cost)) or inputs > INPUT_BOUND
                or outputs > OUTPUT_BOUND or cached > inputs or cost != (inputs * 4 + outputs * 20)):
            raise ValueError
        result = envelope["result"]
        if result["provenance"]["selection_origin"] != "checked_provider_reply":
            raise ValueError
        wonder_analysis.replay_recorded(result, fixed_facts())
        return envelope
    except (KeyError, ValueError, TypeError, AttributeError, RecognitionUnavailable):
        raise ValueError("Invalid saved synthetic owner result") from None


def _private_destination(path: Path, *, must_be_absent: bool = False) -> Path:
    path = Path(path)
    if not path.is_absolute() or path.is_symlink() or path.parent.is_symlink():
        raise ValueError("Absolute private regular-file destination required")
    parent = path.parent.stat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
        raise ValueError("Owned mode-0700 result directory required")
    if path.exists():
        info = path.stat(follow_symlinks=False)
        if must_be_absent or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1:
            raise ValueError("Owned mode-0600 new or existing result file required")
    return path


def _atomic_new_file(path: Path, content: bytes) -> None:
    temporary = path.with_name("." + path.name + "." + uuid4().hex)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.link(temporary, path, follow_symlinks=False)  # Refuses replacement of any existing result.
    finally:
        temporary.unlink(missing_ok=True)


def save_result(path: Path, envelope: dict) -> None:
    path = _private_destination(path, must_be_absent=True)
    content = (canonical(validate_envelope(envelope)) + "\n").encode()
    sidecar = path.with_name(path.name + ".sha256")
    _private_destination(sidecar, must_be_absent=True)
    _atomic_new_file(path, content)
    _atomic_new_file(sidecar, (hashlib.sha256(content).hexdigest() + "\n").encode())


def load_result(path: Path) -> dict:
    path = _private_destination(path)
    sidecar = _private_destination(path.with_name(path.name + ".sha256"))
    if path.stat().st_size > 262144 or sidecar.stat().st_size > 100:
        raise ValueError("Saved owner result is oversized")
    content = path.read_bytes()
    if sidecar.read_text().strip() != hashlib.sha256(content).hexdigest():
        raise ValueError("Saved owner result integrity check failed")
    return validate_envelope(strict_json(content))
