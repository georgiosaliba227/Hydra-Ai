"""Private, bounded attempt observations; no images, prompts or response bodies.

The operator must identify the authoritative ledger. Reading a database does not
authenticate that database's origin or turn synthetic HTTP tests into Meta runs.
Usage-derived charges and independently reviewed invoice finality stay distinct.
"""
import hashlib
import json
from datetime import datetime
from pathlib import Path
import re
import sqlite3
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from .meta_accounts import ACCOUNTS, AccountLedger, InvoiceFinality
from .meta_budget import BudgetDenied
from .recognition import MODEL

EVENT = "model_observation_v1"


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    purpose: Literal["camera", "hydration"]
    result_sha256: str | None = Field(pattern=r"^[a-f0-9]{64}$")
    api_latency_ms: StrictInt | None = Field(ge=0, le=86_400_000)
    provider_http_status: StrictInt | None = Field(default=None, ge=100, le=599)
    outcome: Literal["success", "admission_denied", "transport_error", "usage_unresolved", "output_rejected"]
    transport_kind: Literal["official_meta_https", "injected_test_transport"]


def result_fingerprint(result: dict) -> str:
    """Hash the parsed gateway result, before camera catalogue enrichment."""
    return hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _attempt_id(value: str) -> None:
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("Canonical attempt ID required")


def _transport_kind(transport: object) -> str:
    # Do not trust an injected adapter's claimed provider/mode/property. Exact
    # shipped class identity is evidence of the implementation path only; tests
    # can still replace HTTP, so trusted ledger custody remains a separate gate.
    from .meta_provider import OfficialMetaTransport
    from .hydration_intelligence import HydrationMetaTransport
    return ("official_meta_https" if type(transport) in (OfficialMetaTransport, HydrationMetaTransport)
            else "injected_test_transport")


def record_observation(ledger: AccountLedger, attempt_id: str, *, purpose: str,
                       result: dict | None, latency_ms: int | None, outcome: str,
                       transport: object, provider_http_status: int | None = None) -> None:
    """Append one immutable compact event using the existing authoritative DB."""
    _attempt_id(attempt_id)
    if (outcome == "success") != (result is not None):
        raise ValueError("Only a successful parse has a result fingerprint")
    observation = Observation(purpose=purpose, result_sha256=result_fingerprint(result) if result is not None else None,
                              api_latency_ms=latency_ms, outcome=outcome,
                              provider_http_status=provider_http_status,
                              transport_kind=_transport_kind(transport))
    reference = attempt_id + ":" + observation.model_dump_json()
    ledger.verify_storage()
    with ledger.transaction() as db:
        row = db.execute("SELECT account_id,state,recognized FROM live_attempts WHERE id=?", (attempt_id,)).fetchone()
        if not row or (outcome == "success" and (row[1] != "settled" or (purpose == "camera" and row[2] != 1))):
            raise BudgetDenied("Successful observation requires settled parsed output")
        if db.execute("SELECT 1 FROM live_events WHERE kind=? AND substr(reference,1,36)=?", (EVENT, attempt_id)).fetchone():
            raise BudgetDenied("Attempt observation is immutable")
        ledger.event(db, row[0], EVENT, reference)


def read_observation(path: str | Path, attempt_id: str) -> dict:
    """Read evidence without creating/migrating/locking for writes or activating.

    This function reports gateway records, not independently verified provider
    truth. Evaluation must reject injected transports and require the operator's
    explicit authoritative-ledger selection. Never use copied test DBs as live
    evidence. Missing legacy observations remain unavailable, never fabricated.
    """
    connection = None
    try:
        _attempt_id(attempt_id)
        location = Path(path)
        if not location.is_absolute():
            raise ValueError
        AccountLedger(location).verify_storage()
        connection = sqlite3.connect(location.as_uri() + "?mode=ro", uri=True, timeout=0.5)
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        row = connection.execute(
            "SELECT account_id,provider_id,state,usage,actual,reserved,price,payload_sha256,recognized FROM live_attempts WHERE id=?",
            (attempt_id,),
        ).fetchone()
        if not row or row[0] not in ACCOUNTS:
            raise ValueError
        account, provider_id, state, raw_usage, actual, reserved, raw_price, payload_hash, recognized = row
        events = connection.execute(
            "SELECT at,reference FROM live_events WHERE kind=? AND account_id=? AND substr(reference,1,36)=?",
            (EVENT, account, attempt_id),
        ).fetchall()
        if len(events) != 1 or len(events[0][1]) > 2048 or events[0][1][36:37] != ":":
            raise ValueError
        observed_at, reference = events[0]
        if datetime.fromisoformat(observed_at).tzinfo is None:
            raise ValueError
        if payload_hash is not None and (not isinstance(payload_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", payload_hash)):
            raise ValueError
        observation = Observation.model_validate_json(reference[37:])
        if observation.outcome == "success" and (state != "settled" or observation.result_sha256 is None
                                                 or (observation.purpose == "camera" and recognized != 1)):
            raise ValueError
        if observation.outcome != "success" and observation.result_sha256 is not None:
            raise ValueError
        permits = connection.execute("SELECT permit FROM controlled_permits WHERE account_id=?", (account,)).fetchall()
        if not permits:
            permits = connection.execute("SELECT permit FROM live_permit WHERE id=1").fetchall()
        if len(permits) != 1:
            raise ValueError
        permit = json.loads(permits[0][0])
        if permit["account_id"] != account or permit.get("purpose", "camera") != observation.purpose:
            raise ValueError
        input_hash = permit["image_sha256"]
        if not isinstance(input_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", input_hash):
            raise ValueError
        if provider_id is not None and (not isinstance(provider_id, str) or not re.fullmatch(r"resp_[A-Za-z0-9_-]{1,180}", provider_id)):
            raise ValueError
        usage = json.loads(raw_usage) if raw_usage is not None else None
        if usage is not None:
            if set(usage) != {"input_tokens", "output_tokens", "cached_tokens", "total_tokens"}:
                raise ValueError
            if any(type(value) is not int or value < 0 for value in usage.values()):
                raise ValueError
            if usage["cached_tokens"] > usage["input_tokens"] or usage["total_tokens"] != usage["input_tokens"] + usage["output_tokens"]:
                raise ValueError
        if actual is not None:
            price = json.loads(raw_price)
            if state != "settled" or usage is None or type(actual) is not int or actual < 0 or provider_id is None:
                raise ValueError
            if (price["model"], price["input_micro_per_million"], price["cached_micro_per_million"], price["output_micro_per_million"]) != (MODEL, 1250000, 150000, 4250000):
                raise ValueError
            expected = ((usage["input_tokens"] - usage["cached_tokens"]) * 1250000 + usage["cached_tokens"] * 150000 + usage["output_tokens"] * 4250000 + 999999) // 1000000
            if actual != expected:
                raise ValueError
        finality_row = connection.execute("SELECT evidence FROM live_finalities WHERE attempt_id=?", (attempt_id,)).fetchone()
        final_amount = None
        if finality_row:
            finality = InvoiceFinality.model_validate_json(finality_row[0])
            if (finality.attempt_id, finality.account_id, finality.provider_id, finality.final_gross_micro_usd) != (attempt_id, account, provider_id, actual):
                raise ValueError
            final_amount = finality.final_gross_micro_usd
        if type(reserved) is not int or reserved < 0:
            raise ValueError
        return {"version": "meta-observation-v1", "attempt_id": attempt_id, "account_id": account,
                "model": MODEL, "provider_id": provider_id, "input_sha256": input_hash,
                "payload_sha256": payload_hash, "observed_at": observed_at,
                **observation.model_dump(), "usage": usage, "usage_cost_micro_usd": actual,
                "reserved_micro_usd": reserved, "final_gross_micro_usd": final_amount,
                "billing_status": ("invoice_verified" if final_amount is not None else
                                   "usage_settled_invoice_pending" if actual is not None else "unresolved"),
                "evidence_source": "gateway_ledger_record"}
    except (ValueError, TypeError, KeyError, AttributeError, OSError, sqlite3.Error):
        raise BudgetDenied("Attempt observation unavailable or inconsistent") from None
    finally:
        if connection is not None:
            connection.close()
