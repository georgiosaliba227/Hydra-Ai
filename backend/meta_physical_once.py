"""Owner-authorized physical-photo exception; existing ledger history stays frozen.

This policy can append one permit event and one attempt to the SAME authority.
It never resets an account, edits the old permit, settles a bill, or grants a
general bypass. Only the dedicated operator process selects this ledger class.
"""
from datetime import datetime, timedelta
import hashlib
import json
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from .meta_accounts import AccountLedger, DispatchTicket, Price, now, stamp, USD
from .meta_budget import BudgetDenied
from .meta_policy import MAX_INPUT_TOKENS, OUTPUT_LIMIT

POLICY = "georgio-physical-camera-once-risk-v1"
IMAGE = "8d89de113d438f875b6503aef054561bb7c136ff0c5dfd6dea654f3d5c224168"
ACCOUNT = "georgiosaliba227"
APPROVAL_EVENT = "physical_camera_once_authorized"
RESERVATION_EVENT = "physical_camera_once_reserved"


class PhysicalApproval(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    policy_version: Literal["georgio-physical-camera-once-risk-v1"] = POLICY
    account_id: Literal["georgiosaliba227"] = ACCOUNT
    image_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    payload_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    prior_attempt_id: str = Field(pattern=r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")
    prior_provider_id: str = Field(pattern=r"^resp_[A-Za-z0-9_-]{1,180}$")
    prior_row_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    key_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    provider_account_reference: str = Field(min_length=1, max_length=200)
    # Conservative bounds from the rounded dashboard, never asserted exact costs.
    dashboard_gross_upper_micro_usd: StrictInt = Field(ge=0, le=150 * USD)
    credits_lower_micro_usd: StrictInt = Field(ge=0, le=150 * USD)
    other_mac_allocation_hold_micro_usd: Literal[85000000] = 85 * USD
    intended_maximum_micro_usd: Literal[2000000] = 2 * USD
    provider_total_bound_micro_usd: None = None
    pending_original_charge_micro_usd: None = None
    accepted_unknown_extra_charges: Literal[True]
    accepted_original_billing_pending: Literal[True]
    other_activity_stopped_and_no_other_pending: Literal[True]
    free_credit_photo_disclosure_accepted: Literal[True]
    automatic_topups_disabled: Literal[True]
    price: Price
    observed_at: datetime
    valid_until: datetime
    authorization_reference: str = Field(min_length=1, max_length=500)
    billing_reference: str = Field(min_length=1, max_length=500)
    notification_reference: str = Field(min_length=1, max_length=500)

    @field_validator("accepted_unknown_extra_charges", "accepted_original_billing_pending",
                     "other_activity_stopped_and_no_other_pending",
                     "free_credit_photo_disclosure_accepted", "automatic_topups_disabled", mode="before")
    @classmethod
    def explicit_acceptance(cls, value):
        if value is not True:
            raise ValueError("Explicit owner acceptance required")
        return True

    @model_validator(mode="after")
    def fresh(self):
        if (self.image_sha256 != IMAGE or self.observed_at.tzinfo is None or self.valid_until.tzinfo is None
                or not now() - timedelta(minutes=15) <= self.observed_at <= now()
                or not now() < self.valid_until <= self.observed_at + timedelta(minutes=15)
                or any(not v.strip() for v in (self.authorization_reference,
                       self.billing_reference, self.notification_reference,
                       self.provider_account_reference))):
            raise ValueError("Fresh account and explicit evidence references required")
        return self


class PhysicalCameraLedger(AccountLedger):
    """A single named exception, still using atomic durable reservations/tickets."""

    @staticmethod
    def prior_digest(db, prior_attempt_id) -> str:
        row = db.execute("SELECT * FROM live_attempts WHERE id=?", (prior_attempt_id,)).fetchone()
        return hashlib.sha256(json.dumps(row, separators=(",", ":")).encode()).hexdigest()

    def approve_physical_once(self, approval: PhysicalApproval) -> None:
        self.verify_storage()
        approval = PhysicalApproval.model_validate_json(approval.model_dump_json())
        with self.transaction() as db:
            self._inspect_finality_schema(db)
            if db.execute("SELECT 1 FROM live_events WHERE kind=?", (APPROVAL_EVENT,)).fetchone():
                raise BudgetDenied("Physical exception is immutable and cannot be renewed")
            self._check(db, approval)
            self.event(db, ACCOUNT, APPROVAL_EVENT, approval.model_dump_json())

    def _check(self, db, approval, own_attempt=None):
        approval = PhysicalApproval.model_validate_json(approval.model_dump_json())
        account = db.execute("SELECT evidence,frozen FROM live_accounts WHERE account_id=?", (ACCOUNT,)).fetchone()
        prior = db.execute("SELECT account_id,state,reserved,actual,provider_id FROM live_attempts WHERE id=?", (approval.prior_attempt_id,)).fetchone()
        grant = db.execute("SELECT spent FROM controlled_permits WHERE account_id=?", (ACCOUNT,)).fetchone()
        if (not account or account[1] != 1 or not grant or grant[0] != 1
                or prior != (ACCOUNT, "billing_pending", 1312256, None, approval.prior_provider_id)
                or self.prior_digest(db, approval.prior_attempt_id) != approval.prior_row_sha256):
            raise BudgetDenied("Only the unchanged original billing hold may be excepted")
        old_evidence = json.loads(account[0])
        if (old_evidence.get("policy_version") != "georgio-first-camera-risk-v1"
                or old_evidence["key_sha256"] != approval.key_sha256
                or old_evidence["provider_account_reference"] != approval.provider_account_reference):
            raise BudgetDenied("Original verified account and key required")
        if db.execute("SELECT 1 FROM live_accounts WHERE account_id!=? AND frozen=1", (ACCOUNT,)).fetchone():
            raise BudgetDenied("Another account is frozen")
        if db.execute("SELECT 1 FROM live_attempts WHERE id!=? AND id!=?", (approval.prior_attempt_id, own_attempt or "")).fetchone():
            raise BudgetDenied("No other project attempt is allowed by this exception")
        if db.execute("SELECT 1 FROM live_finalities").fetchone():
            raise BudgetDenied("Original finality state changed; review new evidence")
        token_cost = approval.price.cost(MAX_INPUT_TOKENS, OUTPUT_LIMIT)
        if token_cost > approval.intended_maximum_micro_usd:
            raise BudgetDenied("Token reservation exceeds intended spend")
        historical = max(approval.dashboard_gross_upper_micro_usd, old_evidence["gross_micro_usd"])
        exposure = historical + prior[2] + approval.other_mac_allocation_hold_micro_usd + approval.intended_maximum_micro_usd
        if exposure >= 100 * USD:  # This approval contains no new $100 authorization.
            raise BudgetDenied("Additional approval checkpoint or operational cutoff reached")
        if (exposure >= 120 * USD or exposure >= 150 * USD
                or approval.credits_lower_micro_usd < prior[2] + approval.other_mac_allocation_hold_micro_usd + approval.intended_maximum_micro_usd + 30 * USD):
            raise BudgetDenied("Credit reserve or account cutoff unavailable")
        return approval, token_cost

    def _approval(self, db, own_attempt=None):
        rows = db.execute("SELECT reference FROM live_events WHERE kind=?", (APPROVAL_EVENT,)).fetchall()
        if len(rows) != 1:
            raise BudgetDenied("Exactly one immutable physical authorization required")
        try:
            approval = PhysicalApproval.model_validate_json(rows[0][0])
        except ValueError:
            raise BudgetDenied("Physical authorization expired or invalid") from None
        return self._check(db, approval, own_attempt)

    def verify_credential(self, account, fingerprint):
        self.verify_storage()
        with self.transaction() as db:
            approval, _ = self._approval(db)
            if account != ACCOUNT or fingerprint != approval.key_sha256:
                raise BudgetDenied("Credential mismatch")

    def verify_purpose(self, account, purpose):
        if (account, purpose) != (ACCOUNT, "camera"):
            raise BudgetDenied("Physical exception covers only Georgio camera")

    def quote(self, account, input_bound):
        with self.transaction() as db:
            approval, amount = self._approval(db)
            if account != ACCOUNT or type(input_bound) is not int or input_bound != MAX_INPUT_TOKENS:
                raise BudgetDenied("Full-context Standard quote required")
            return approval.price, amount

    def reserve_first(self, account, image_hash, input_bound):
        self.verify_storage()
        with self.transaction() as db:
            approval, amount = self._approval(db)
            if ((account, image_hash) != (ACCOUNT, IMAGE)
                    or type(input_bound) is not int or input_bound != MAX_INPUT_TOKENS
                    or db.execute("SELECT 1 FROM live_events WHERE kind=?", (RESERVATION_EVENT,)).fetchone()):
                raise BudgetDenied("Exact one-use physical photo required")
            attempt = str(uuid4())
            db.execute("INSERT INTO live_attempts(id,account_id,price,reserved,state,created_at,input_bound) VALUES(?,?,?,?,?,?,?)",
                       (attempt, ACCOUNT, approval.price.model_dump_json(), amount, "reserved", stamp(), input_bound))
            self.event(db, ACCOUNT, RESERVATION_EVENT, attempt)
            self.event(db, ACCOUNT, "reserved", attempt)
            self.queue_threshold_notices(db, ACCOUNT, approval.dashboard_gross_upper_micro_usd + 1312256 + approval.intended_maximum_micro_usd)
            return attempt

    def mark_dispatched(self, attempt, payload_sha256):
        if len(payload_sha256) != 64 or any(c not in "0123456789abcdef" for c in payload_sha256):
            raise BudgetDenied("Payload fingerprint required")
        with self.transaction() as db:
            approval, _ = self._approval(db, attempt)
            if payload_sha256 != approval.payload_sha256:
                raise BudgetDenied("Payload differs from the exact approved photo request")
            if db.execute("SELECT reference FROM live_events WHERE kind=?", (RESERVATION_EVENT,)).fetchall() != [(attempt,)]:
                raise BudgetDenied("Matching one-use reservation required")
            if db.execute("SELECT state FROM live_attempts WHERE id=?", (attempt,)).fetchone() != ("reserved",):
                raise BudgetDenied("Attempt already dispatched")
            if db.execute("SELECT 1 FROM live_notices WHERE delivered_at IS NULL").fetchone():
                raise BudgetDenied("Notification delivery required")
            nonce = str(uuid4())
            db.execute("UPDATE live_attempts SET state='dispatched',dispatched_at=?,payload_sha256=?,ticket_nonce=? WHERE id=?", (stamp(), payload_sha256, nonce, attempt))
            self.event(db, ACCOUNT, "dispatched", attempt)
        return DispatchTicket(self, attempt, nonce)

    def claim_send(self, attempt, nonce, payload_sha256, input_bound, credential_fingerprint):
        self.verify_storage()
        with self.transaction() as db:
            approval, _ = self._approval(db, attempt)
            row = db.execute("SELECT state,ticket_nonce,payload_sha256,input_bound FROM live_attempts WHERE id=?", (attempt,)).fetchone()
            if (row != ("dispatched", nonce, payload_sha256, MAX_INPUT_TOKENS)
                    or payload_sha256 != approval.payload_sha256
                    or type(input_bound) is not int or input_bound != MAX_INPUT_TOKENS
                    or credential_fingerprint != approval.key_sha256
                    or db.execute("SELECT reference FROM live_events WHERE kind=?", (RESERVATION_EVENT,)).fetchall() != [(attempt,)]
                    or db.execute("SELECT 1 FROM live_notices WHERE delivered_at IS NULL").fetchone()):
                raise BudgetDenied("One-use dispatch evidence mismatch")
            db.execute("UPDATE live_attempts SET state='sending',ticket_nonce=NULL WHERE id=?", (attempt,))
            self.event(db, ACCOUNT, "network_send_claimed", attempt)
