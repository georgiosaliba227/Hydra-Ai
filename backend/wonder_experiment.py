"""Live Muse Wonder path, charged to the one account a ledger's allocation names.

Georgio's $30 experiment or Amine's $20 allocation, each in its own ledger.
Implemented and tested with fake transports only. A real request additionally
needs the LIVE_SCHEMA installed by a reviewed migration, current account
evidence, an approved case for the exact payload (a recorded case, or a trend
or planned-workout case bound to the user's consent under the allocation's
standing trend approval) and invoice finality for every earlier attempt.
"""
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re
from time import monotonic_ns, sleep
from uuid import uuid4

from pydantic import field_validator

from .hydration_context_v2 import SCENARIOS, build_scenario, comparison_result
from .meta_accounts import FINANCIAL_DDL, _canonical_schema, stamp
from .meta_budget import BudgetDenied
from .meta_experiments import (PROPOSED_SCHEMA, ExperimentApproval, ExperimentBudget, ExperimentQuote,
                               ExperimentRequest, Fingerprint, Model, Reference, StrictDescriptor)
from .meta_gateway import Notifier
from .meta_policy import OUTPUT_LIMIT
from .meta_provider import OfficialMetaTransport, ProviderReply
from .recognition import RecognitionUnavailable
from .wonder_assistant import assistant_payload, live_answer, parse_topics
from .wonder_hydration import (MODEL, input_bound, live_comparison_provenance, parse_selection, payload_sha256,
                               wonder_payload)
from .wonder_trends import facts_from_payload, parse_explanation, trend_result, trends_payload
from . import wonder_workout
from ai.assistant import SUGGESTED

# Reviewed additive DDL; installed only by tests until a separate migration is approved.
LIVE_SCHEMA = PROPOSED_SCHEMA + (
    "CREATE TABLE experiment_cases(case_id TEXT PRIMARY KEY, model TEXT NOT NULL CHECK(model IN ('muse-spark-1.3','muse-wonder-1.0')), payload_sha256 TEXT NOT NULL UNIQUE, approval TEXT NOT NULL)",
    "CREATE TRIGGER experiment_cases_no_update BEFORE UPDATE ON experiment_cases BEGIN SELECT RAISE(ABORT,'immutable case manifest'); END",
    "CREATE TRIGGER experiment_cases_no_delete BEFORE DELETE ON experiment_cases BEGIN SELECT RAISE(ABORT,'immutable case manifest'); END",
)
LIVE_SCHEMA_VERSION = "experiment-live-v1"
RESPONSE_ID = re.compile(r"resp_[A-Za-z0-9_-]{1,180}")
# A busy ledger (another writer) must not lose the provider's reply: retry the
# local write, never the network request.
LEDGER_RETRIES = 20
LEDGER_RETRY_SECONDS = 0.25


def synthetic_payload_hashes() -> set[str]:
    """Every fixed synthetic payload Hydra builds: the scenarios and the suggested questions."""
    return ({payload_sha256(wonder_payload(name)) for name in SCENARIOS}
            | {payload_sha256(assistant_payload(question_id)) for question_id in SUGGESTED})


class UsageRejected(BudgetDenied):
    """Settlement reached a final outcome (recorded or frozen); retrying cannot help."""


def _object_name(sql: str) -> str:
    return sql.split()[2].split("(")[0]


class ApprovedCase(StrictDescriptor):
    """One exact payload a human approved for real dispatch; immutable once recorded."""
    case_id: str
    model: Model
    payload_sha256: Fingerprint
    valid_until: datetime
    input_approval_reference: Reference
    live_dispatch_reference: Reference
    spending_approval_reference: Reference

    _uuid = field_validator("case_id")(ExperimentRequest.canonical_uuid.__func__)


class WonderExperimentLedger(ExperimentBudget):
    """Dispatchable experiment reservations in the same authoritative AccountLedger.

    States: experiment_reserved -> experiment_dispatched -> experiment_sending ->
    settled (or unresolved + frozen). Legacy camera dispatch, send and settlement
    methods accept none of the experiment states.
    """
    SCHEMA = LIVE_SCHEMA

    @staticmethod
    def _inspect_live_schema(db) -> dict:
        """Accept the finality-current financial schema plus any exact subset of LIVE_SCHEMA."""
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise BudgetDenied("Ledger integrity check failed")
        objects = {row[1]: row for row in db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master")}
        for name, sql in FINANCIAL_DDL.items():
            row = objects.get(name)
            if row is None or row[0] != "table" or not isinstance(row[3], str) or _canonical_schema(row[3]) != _canonical_schema(sql):
                raise BudgetDenied("Finality-current financial schema required first")
        live = {_object_name(sql): sql for sql in LIVE_SCHEMA}
        missing = [name for name in live if name not in objects]
        for name, sql in live.items():
            row = objects.get(name)
            if row is not None and (not isinstance(row[3], str) or _canonical_schema(row[3]) != _canonical_schema(sql)):
                raise BudgetDenied("Unrecognized experiment schema object; migration refused")
        for kind, name, table, sql in objects.values():
            if ((kind == "trigger" and name not in live)
                    or (kind == "index" and sql is not None and (table in FINANCIAL_DDL or table in live))
                    or (name.startswith("experiment_") and name not in live)):
                raise BudgetDenied("Unexpected schema object; migration refused")
        target = "\n".join(_canonical_schema(sql) for sql in LIVE_SCHEMA)
        return {"version": LIVE_SCHEMA_VERSION, "compatible": True,
                "status": "migration_required" if missing else "already_current", "missing_objects": missing,
                "target_schema_sha256": hashlib.sha256(target.encode()).hexdigest(),
                "existing_records_changed": False, "audit_event_added": False, "activation_authorized": False}

    def preview_live_schema(self) -> dict:
        """Read-only compatibility inspection of an existing private ledger."""
        with self.authority._existing_migration_database(write=False) as db:
            return self._inspect_live_schema(db)

    def migrate_live_schema(self, *, review_reference: str) -> dict:
        """Atomically add only missing LIVE_SCHEMA objects and one audit event.

        Never creates a ledger, records approvals or cases, changes balances or
        clears freezes. Run the finality migration first.
        """
        if (not isinstance(review_reference, str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/# -]{0,199}", review_reference)
                or review_reference != review_reference.strip()):
            raise BudgetDenied("A bounded nonsecret schema review reference is required")
        with self.authority._existing_migration_database(write=True) as db:
            before = self._inspect_live_schema(db)
            if before["status"] == "already_current":
                return before
            for sql in LIVE_SCHEMA:
                if _object_name(sql) in before["missing_objects"]:
                    db.execute(sql)
            self.authority.event(db, None, "experiment_live_schema_migrated", LIVE_SCHEMA_VERSION + ":" + review_reference)
            after = self._inspect_live_schema(db)
            return {**after, "status": "migrated", "migrated_objects": before["missing_objects"], "audit_event_added": True}

    def record_case(self, case: ApprovedCase) -> None:
        case = ApprovedCase.model_validate(case.model_dump())
        with self._transaction() as db:
            case = ApprovedCase.model_validate(case.model_dump())
            if not db.execute("SELECT 1 FROM experiment_allocation WHERE id=1").fetchone():
                raise BudgetDenied("Immutable reviewed allocation missing")
            account = json.loads(db.execute("SELECT approval FROM experiment_allocation WHERE id=1").fetchone()[0])["account_id"]
            self._insert_case(db, case, account)

    def register_trend_case(self, payload: str, consent_reference: str) -> ApprovedCase:
        """A case for one exact trend payload the user consented to, under the standing trend approval."""
        return self._register_standing_case(payload, consent_reference, "trend_dispatch_reference")

    def register_workout_case(self, payload: str, consent_reference: str) -> ApprovedCase:
        """A case for one exact planned-workout payload the user consented to.

        The standing trend approval covers Wonder explanations of the owner's own data, each bound
        to the exact payload hash the user previewed and consented to (WONDER_WORKOUT_API.md).
        """
        return self._register_standing_case(payload, consent_reference, "trend_dispatch_reference")

    def register_synthetic_case(self, payload: str, request_reference: str) -> ApprovedCase:
        """A case for one fixed server-built synthetic payload, under the standing synthetic approval."""
        if payload not in synthetic_payload_hashes():
            raise BudgetDenied("Only Hydra's fixed synthetic payloads use the standing approval")
        return self._register_standing_case(payload, request_reference, "synthetic_dispatch_reference")

    def _register_standing_case(self, payload: str, reference: str, standing: str) -> ApprovedCase:
        """Reuses an unsent case for the same payload; a payload already sent is never approved again."""
        with self._transaction() as db:
            allocation = self._allocation(db)
            dispatch_reference = getattr(allocation, standing)
            if dispatch_reference is None:
                raise BudgetDenied("No standing approval for this kind of request")
            case = self._standing_case_in(db, allocation, payload, reference, dispatch_reference)
            # Every request is audited with who asked, including when an unsent case is reused.
            self.authority.event(db, allocation.account_id, "experiment_case_requested", case.case_id + ":" + reference)
            return case

    def _standing_case_in(self, db, allocation, payload: str, reference: str, dispatch_reference: str) -> ApprovedCase:
        existing = db.execute("SELECT case_id FROM experiment_cases WHERE payload_sha256=?", (payload,)).fetchone()
        if existing:
            case = self._case(db, existing[0])
            if (case.live_dispatch_reference != dispatch_reference
                    or db.execute("SELECT 1 FROM experiment_attempts WHERE case_id=?", (case.case_id,)).fetchone()):
                raise BudgetDenied("This exact payload was already approved or sent")
            return case
        case = ApprovedCase(case_id=str(uuid4()), model=MODEL, payload_sha256=payload,
                            valid_until=allocation.valid_until, input_approval_reference=reference,
                            live_dispatch_reference=dispatch_reference,
                            spending_approval_reference=allocation.spending_authority_reference)
        self._insert_case(db, case, allocation.account_id)
        return case

    def _insert_case(self, db, case: ApprovedCase, account: str) -> None:
        raw = case.model_dump_json()
        existing = db.execute("SELECT approval FROM experiment_cases WHERE case_id=?", (case.case_id,)).fetchone()
        if existing:
            if existing[0] == raw:
                return
            raise BudgetDenied("Approved cases are immutable")
        if db.execute("SELECT 1 FROM experiment_cases WHERE payload_sha256=?", (case.payload_sha256,)).fetchone():
            raise BudgetDenied("One approved case per exact payload")
        db.execute("INSERT INTO experiment_cases(case_id,model,payload_sha256,approval) VALUES(?,?,?,?)",
                   (case.case_id, case.model, case.payload_sha256, raw))
        self.authority.event(db, account, "experiment_case_approved", case.case_id)

    @staticmethod
    def _case(db, case_id: str) -> ApprovedCase:
        row = db.execute("SELECT model,payload_sha256,approval FROM experiment_cases WHERE case_id=?", (case_id,)).fetchone()
        if not row:
            raise BudgetDenied("Case is not in the approved manifest")
        try:
            case = ApprovedCase.model_validate_json(row[2])
            if (case.case_id, case.model, case.payload_sha256) != (case_id, row[0], row[1]):
                raise ValueError
        except ValueError:
            raise BudgetDenied("Case approval expired or invalid") from None
        return case

    def _check_case(self, db, request: ExperimentRequest) -> None:
        case = self._case(db, request.case_id)
        if (case.model, case.payload_sha256, case.input_approval_reference) != (
                request.quote.model, request.payload_sha256, request.input_approval_reference):
            raise BudgetDenied("Request does not match its approved case")

    def reserve_for_dispatch(self, request: ExperimentRequest) -> dict:
        return self._reserve(request, "experiment_reserved") | {"dispatch_enabled": True, "state": "reserved_for_dispatch"}

    def _current(self, db, attempt: str) -> tuple:
        """Re-validate freeze, finality, allocation, evidence, quote and case inside the lock."""
        self.authority.verify_project_unfrozen(db)
        self.authority.verify_prior_finalities(db, excluding_attempt=attempt)
        approval = self._allocation(db)
        row = db.execute("SELECT a.state,a.payload_sha256,a.ticket_nonce,a.input_bound,a.price,e.case_id "
                         "FROM live_attempts a JOIN experiment_attempts e ON e.attempt_id=a.id "
                         "WHERE a.id=? AND a.account_id=?", (attempt, approval.account_id)).fetchone()
        if not row:
            raise BudgetDenied("Unknown experiment attempt")
        try:
            ExperimentQuote.model_validate_json(row[4])
        except (TypeError, ValueError):
            raise BudgetDenied("Allocation or price evidence expired") from None
        evidence = self._evidence(db, approval)
        if self._case(db, row[5]).payload_sha256 != row[1]:
            raise BudgetDenied("Attempt no longer matches its approved case")
        return row, evidence, approval.account_id

    def mark_dispatched(self, attempt: str, payload: str) -> "ExperimentTicket":
        if not re.fullmatch(r"[a-f0-9]{64}", payload):
            raise BudgetDenied("Exact payload fingerprint required")
        nonce = str(uuid4())
        with self._transaction() as db:
            row, _, account = self._current(db, attempt)
            if row[0] != "experiment_reserved" or row[1] != payload:
                raise BudgetDenied("Attempt cannot dispatch twice or with another payload")
            if db.execute("SELECT 1 FROM live_notices WHERE delivered_at IS NULL").fetchone():
                raise BudgetDenied("Both developers must receive pending notices")
            db.execute("UPDATE live_attempts SET state='experiment_dispatched',dispatched_at=?,ticket_nonce=? WHERE id=?",
                       (stamp(), nonce, attempt))
            self.authority.event(db, account, "experiment_dispatched", attempt)
        return ExperimentTicket(self, attempt, nonce)

    def claim_send(self, attempt: str, nonce: str, payload: str, bound: int, credential_fingerprint: str) -> None:
        self.authority.verify_storage()
        with self._transaction() as db:
            row, evidence, account = self._current(db, attempt)
            if row[:3] != ("experiment_dispatched", payload, nonce):
                raise BudgetDenied("No matching one-use network dispatch ticket")
            if evidence.key_sha256 != credential_fingerprint or type(bound) is not int or bound != row[3]:
                raise BudgetDenied("Credential or input bound does not match the reservation")
            db.execute("UPDATE live_attempts SET state='experiment_sending',ticket_nonce=NULL WHERE id=?", (attempt,))
            self.authority.event(db, account, "experiment_network_send_claimed", attempt)

    def settle(self, attempt: str, reply: ProviderReply) -> int:
        """Usage-derived gross at the reserved quote's prices. Not invoice finality."""
        blocked, amount = False, 0
        with self._transaction() as db:
            row = db.execute("SELECT a.price,a.reserved,a.state,a.input_bound,e.request,a.account_id FROM live_attempts a "
                             "JOIN experiment_attempts e ON e.attempt_id=a.id WHERE a.id=? AND a.actual IS NULL",
                             (attempt,)).fetchone()
            if not row or row[2] != "experiment_sending":
                raise UsageRejected("No unsettled sending experiment attempt")
            account = row[5]
            try:
                quote, request = json.loads(row[0]), json.loads(row[4])
                body = reply.body
                usage = body["usage"]
                inputs, outputs, total = usage["input_tokens"], usage["output_tokens"], usage["total_tokens"]
                cached = usage["input_tokens_details"]["cached_tokens"]
                identifier = body["id"]
                if body.get("model") != quote["model"] or not isinstance(identifier, str) or not RESPONSE_ID.fullmatch(identifier):
                    raise ValueError
                if any(type(x) is not int or x < 0 for x in (inputs, outputs, cached, total)) or cached > inputs or total != inputs + outputs:
                    raise ValueError
                if db.execute("SELECT 1 FROM live_attempts WHERE account_id=? AND provider_id=?", (account, identifier)).fetchone():
                    raise ValueError
                recorded = json.dumps({"input_tokens": inputs, "output_tokens": outputs, "cached_tokens": cached, "total_tokens": total}, sort_keys=True)
                evidence = json.loads(db.execute("SELECT evidence FROM live_accounts WHERE account_id=?", (account,)).fetchone()[0])
                # Extra categories cannot be priced from usage alone. Cached input is billed below the input
                # price, so charging every input token at the full price is an upper bound, never an undercount.
                if quote["extra_charge_bound_micro_usd"] or evidence["extra_charge_bound_micro_usd"]:
                    db.execute("UPDATE live_attempts SET provider_id=?,usage=? WHERE id=?", (identifier, recorded, attempt))
                    raise ValueError
                amount = (inputs * quote["input_micro_per_million"] + outputs * quote["output_micro_per_million"] + 999_999) // 1_000_000
                db.execute("UPDATE live_attempts SET actual=?,provider_id=?,usage=?,state='settled' WHERE id=?",
                           (amount, identifier, recorded, attempt))
                exposure = evidence["gross_micro_usd"] + db.execute(
                    "SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM live_attempts WHERE account_id=?", (account,)).fetchone()[0]
                self.authority.queue_threshold_notices(db, account, exposure)
                blocked = amount > row[1] or inputs > row[3] or outputs > request["output_bound"]
                if blocked:
                    db.execute("UPDATE live_accounts SET frozen=1 WHERE account_id=?", (account,))
                self.authority.event(db, account, "experiment_settled_over_bound" if blocked else "experiment_settled", attempt)
            except (ValueError, KeyError, TypeError, AttributeError):
                db.execute("UPDATE live_attempts SET state='unresolved' WHERE id=?", (attempt,))
                db.execute("UPDATE live_accounts SET frozen=1 WHERE account_id=?", (account,))
                self.authority.event(db, account, "experiment_usage_unverified", attempt)
                blocked = True
        if blocked:
            raise UsageRejected("Provider usage unresolved or exceeded reservation")
        return amount


    def verify_identity(self, account: str, credential_fingerprint: str) -> None:
        """Read-only: the key and account must be this ledger's, checked before anything is reserved."""
        with self._transaction(write=False) as db:
            row = db.execute("SELECT approval FROM experiment_allocation WHERE id=1").fetchone()
            if not row:
                raise BudgetDenied("Immutable reviewed allocation missing")
            allocated = json.loads(row[0])["account_id"]
            evidence = db.execute("SELECT evidence FROM live_accounts WHERE account_id=?", (allocated,)).fetchone()
            if (allocated != account or not evidence
                    or json.loads(evidence[0])["key_sha256"] != credential_fingerprint):
                raise BudgetDenied("Key or account does not belong to this ledger")

    def record_rejected_output(self, attempt: str) -> None:
        """Audit a settled attempt whose output failed validation; changes no amounts or freezes."""
        with self._transaction() as db:
            row = db.execute("SELECT account_id FROM live_attempts WHERE id=? AND state='settled'", (attempt,)).fetchone()
            if not row:
                raise BudgetDenied("Only a settled attempt can record rejected output")
            self.authority.event(db, row[0], "experiment_output_rejected", attempt)


@dataclass(frozen=True)
class ExperimentTicket:
    ledger: WonderExperimentLedger
    attempt: str
    nonce: str

    def claim(self, payload: dict, *, input_bound: int, credential_fingerprint: str) -> None:
        self.ledger.claim_send(self.attempt, self.nonce, payload_sha256(payload), input_bound, credential_fingerprint)


class WonderMetaTransport(OfficialMetaTransport):
    """Same fixed-origin, no-retry sender; accepts only exact payloads Hydra builds.

    Those are the synthetic scenarios and suggested questions, trend payloads and planned-workout payloads.
    """
    ticket_type = ExperimentTicket

    def validate_payload(self, payload: dict) -> None:
        if (any(payload == wonder_payload(name) for name in SCENARIOS)
                or any(payload == assistant_payload(question_id) for question_id in SUGGESTED)):
            return
        try:
            facts_from_payload(payload)  # Exactly a Hydra trend payload,
        except ValueError:
            wonder_workout.facts_from_payload(payload)  # or a planned-workout payload; raises otherwise.

    def input_bound(self, payload: dict) -> int:
        self.validate_payload(payload)
        return input_bound(payload)


class WonderHydrationGateway:
    """One approved Wonder case per call: reserve, notify, dispatch, settle, validate."""
    def __init__(self, ledger: WonderExperimentLedger, transport, notifier: Notifier) -> None:
        if type(ledger) is not WonderExperimentLedger:
            raise ValueError("Wonder experiment ledger required")
        self.ledger, self.transport, self.notifier = ledger, transport, notifier
        self.last_attempt: str | None = None  # Lets operators find a reserved attempt after a failure.
        self.account: str | None = None  # The account the last reservation charged.
        self.rejected_reply: dict | None = None  # Body of a settled reply that failed validation, for diagnosis.

    @staticmethod
    def _with_ledger_retries(operation):
        """Repeat a local ledger write while storage is busy; final outcomes are not retried."""
        for remaining in range(LEDGER_RETRIES, 0, -1):
            try:
                return operation()
            except UsageRejected:
                raise
            except BudgetDenied:
                if remaining == 1:
                    raise
                sleep(LEDGER_RETRY_SECONDS)

    def deliver_pending_notices(self) -> None:
        for notice in self.ledger.authority.notices():
            if notice["delivered_at"] is None:
                receipt = self.notifier.deliver(notice)
                if not receipt:
                    raise BudgetDenied("Notification lacks delivery receipt")
                self.ledger.authority.notice_delivered(notice["id"], receipt)

    def _run(self, payload: dict, case_id: str, quote: ExperimentQuote, input_approval_reference: str, parse, *,
             freeze_on_rejected_output: bool = True):
        """Reserve, notify, dispatch once, settle, then parse; any failure after reservation quarantines.

        With freeze_on_rejected_output=False, output rejected after a successful settlement is
        recorded without freezing: its charge is already accounted from provider usage.
        """
        attempt, replied, latency_ms, settled = None, False, None, False
        try:
            # A wrong key or account is refused here; after reservation it would freeze the ledger.
            self.ledger.verify_identity(quote.account_id, self.transport.credential_fingerprint)
            bound = self.transport.input_bound(payload)
            request = ExperimentRequest(attempt_id=str(uuid4()), case_id=case_id, payload_sha256=payload_sha256(payload),
                                        input_bound=bound, output_bound=payload["max_output_tokens"],
                                        maximum_micro_usd=quote.bound(bound, payload["max_output_tokens"]),
                                        input_approval_reference=input_approval_reference, quote=quote)
            self.account = self.ledger.reserve_for_dispatch(request)["account_id"]
            attempt = self.last_attempt = request.attempt_id
            self.deliver_pending_notices()
            # Durable dispatch marker precedes the only network operation.
            ticket = self.ledger.mark_dispatched(attempt, request.payload_sha256)
            started = monotonic_ns()
            try:
                reply = self.transport.generate(payload, ticket)
            finally:
                latency_ms = max(0, (monotonic_ns() - started) // 1_000_000)
            replied = True
            cost = self._with_ledger_retries(lambda: self.ledger.settle(attempt, reply))
            settled = True
            parsed = parse(reply)
        except Exception:
            if settled:
                self.rejected_reply = reply.body
            if settled and not freeze_on_rejected_output:
                try:
                    self._with_ledger_retries(lambda: self.ledger.record_rejected_output(attempt))
                except Exception:
                    pass  # The settled charge is recorded; the event is informational.
            elif attempt is not None:
                try:
                    self._with_ledger_retries(lambda: self.ledger.authority.quarantine(attempt))
                except Exception:
                    pass  # Durable reservation remains; unavailable storage fails closed.
                if replied:
                    try:
                        self.deliver_pending_notices()
                    except Exception:
                        pass
            raise RecognitionUnavailable() from None
        usage = reply.body["usage"]
        observations = {"latency_ms": latency_ms, "input_tokens": usage["input_tokens"],
                        "output_tokens": usage["output_tokens"], "usage_derived_cost_micro_usd": cost,
                        "billed_cost_usd": None}
        return parsed, attempt, observations

    def explain(self, scenario: str, case_id: str, quote: ExperimentQuote, input_approval_reference: str) -> dict:
        selection, attempt, observations = self._run(wonder_payload(scenario), case_id, quote, input_approval_reference,
                                                     lambda reply: parse_selection(reply, scenario))
        _, prediction = build_scenario(scenario)
        return comparison_result(scenario, prediction, selection, live_comparison_provenance(attempt, self.account),
                                 observations)

    def answer(self, question_id: str, case_id: str, quote: ExperimentQuote, input_approval_reference: str) -> dict:
        """Wonder selects allowed reviewed topics for one approved suggested question."""
        if question_id not in SUGGESTED:
            raise RecognitionUnavailable()
        topics, attempt, observations = self._run(assistant_payload(question_id), case_id, quote, input_approval_reference,
                                                  lambda reply: parse_topics(reply, question_id))
        return live_answer(question_id, topics, attempt_id=attempt, observations=observations, account=self.account)

    def explain_synthetic(self, scenario: str, quote: ExperimentQuote, request_reference: str) -> dict:
        """One synthetic scenario under the standing approval; sent at most once, never retried."""
        payload = wonder_payload(scenario)
        case = self._standing_case(payload, request_reference)
        selection, attempt, observations = self._run(payload, case.case_id, quote, case.input_approval_reference,
                                                     lambda reply: parse_selection(reply, scenario),
                                                     freeze_on_rejected_output=False)
        _, prediction = build_scenario(scenario)
        return comparison_result(scenario, prediction, selection, live_comparison_provenance(attempt, self.account),
                                 observations)

    def answer_synthetic(self, question_id: str, quote: ExperimentQuote, request_reference: str) -> dict:
        """One suggested question under the standing approval; sent at most once, never retried."""
        if question_id not in SUGGESTED:
            raise RecognitionUnavailable()
        payload = assistant_payload(question_id)
        case = self._standing_case(payload, request_reference)
        topics, attempt, observations = self._run(payload, case.case_id, quote, case.input_approval_reference,
                                                  lambda reply: parse_topics(reply, question_id),
                                                  freeze_on_rejected_output=False)
        return live_answer(question_id, topics, attempt_id=attempt, observations=observations, account=self.account)

    def _standing_case(self, payload: dict, reference: str) -> ApprovedCase:
        try:
            return self.ledger.register_synthetic_case(payload_sha256(payload), reference)
        except Exception:
            raise RecognitionUnavailable() from None

    def explain_trends(self, facts: dict, quote: ExperimentQuote, consent_reference: str) -> dict:
        """Wonder explains the user's own trends; the case is bound to the exact payload they consented to."""
        try:
            payload = trends_payload(facts)
            case = self.ledger.register_trend_case(payload_sha256(payload), consent_reference)
        except Exception:
            raise RecognitionUnavailable() from None
        # A reused unsent case keeps the consent reference it was first approved with.
        explanation, attempt, observations = self._run(payload, case.case_id, quote, case.input_approval_reference,
                                                       lambda reply: parse_explanation(reply, facts),
                                                       freeze_on_rejected_output=False)
        return trend_result(facts, explanation, account=self.account, attempt_id=attempt, observations=observations,
                            generated_at=stamp())

    def explain_workout(self, facts: dict, quote: ExperimentQuote, consent_reference: str) -> dict:
        """Wonder explains a planned workout against the user's own history; bound to the consented payload."""
        try:
            payload = wonder_workout.workout_payload(facts)
            case = self.ledger.register_workout_case(payload_sha256(payload), consent_reference)
        except Exception:
            raise RecognitionUnavailable() from None
        # A reused unsent case keeps the consent reference it was first approved with.
        explanation, attempt, observations = self._run(payload, case.case_id, quote, case.input_approval_reference,
                                                       lambda reply: wonder_workout.parse_explanation(reply, facts),
                                                       freeze_on_rejected_output=False)
        return wonder_workout.workout_result(facts, explanation, account=self.account, attempt_id=attempt,
                                             observations=observations, generated_at=stamp())
