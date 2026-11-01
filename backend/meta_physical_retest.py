"""One separately approved 1,024-token retest, preserving both earlier holds."""
import hashlib
import json
from typing import Literal

from pydantic import Field, field_validator

from .meta_budget import BudgetDenied
from .meta_images import sanitized_jpeg
from .meta_physical_once import (PhysicalApproval, PhysicalCameraLedger, ACCOUNT,
                                 IMAGE, APPROVAL_EVENT, RESERVATION_EVENT)
from .meta_policy import MODEL_CONTEXT, OUTPUT_LIMIT
from .meta_provider import OfficialMetaTransport, request_payload
from .recognition import AnalysisRequest

RETEST_POLICY = "georgio-physical-camera-retest-risk-v1"
RETEST_OUTPUT = 1024
RETEST_INPUT = MODEL_CONTEXT - RETEST_OUTPUT


class RetestApproval(PhysicalApproval):
    policy_version: Literal["georgio-physical-camera-retest-risk-v1"] = RETEST_POLICY
    combined_output_limit: Literal[1024] = RETEST_OUTPUT
    previous_physical_attempt_id: str = Field(pattern=r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")
    previous_physical_provider_id: str = Field(pattern=r"^resp_[A-Za-z0-9_-]{1,180}$")
    previous_physical_row_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    previous_physical_permit_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    both_prior_holds_accepted: Literal[True]

    _accepted_both = field_validator("both_prior_holds_accepted", mode="before")(PhysicalApproval.explicit_acceptance.__func__)


def retest_payload(image):
    return request_payload(image) | {"max_output_tokens": RETEST_OUTPUT}


class RetestTransport(OfficialMetaTransport):
    """Same official single-shot sender; fixed approved cap and exact photo."""
    def build_payload(self, image):
        return retest_payload(image)

    def input_bound(self, payload):
        return RETEST_INPUT

    def validate_payload(self, payload):
        url = payload["input"][0]["content"][1]["image_url"]
        prefix = "data:image/jpeg;base64,"
        if not url.startswith(prefix):
            raise ValueError("JPEG data required")
        image = AnalysisRequest(image_base64=url[len(prefix):], photo_consent=True,
                                meta_photo_consent=True, mode="meta_live")
        if (hashlib.sha256(sanitized_jpeg(image)).hexdigest() != IMAGE
                or payload != retest_payload(image)):
            raise ValueError("Only the exact retest payload is authorized")


class RetestLedger(PhysicalCameraLedger):
    approval_type = RetestApproval
    approval_event = "physical_camera_retest_authorized"
    reservation_event = "physical_camera_retest_reserved"
    policy_version = RETEST_POLICY
    input_limit = RETEST_INPUT
    output_limit = RETEST_OUTPUT
    retained_micro_usd = 2624512

    @staticmethod
    def previous_permit_digest(db):
        rows = db.execute("SELECT * FROM live_events WHERE kind IN (?,?) ORDER BY id",
                          (APPROVAL_EVENT, RESERVATION_EVENT)).fetchall()
        return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()

    def _check_additional_history(self, db, approval, own_attempt):
        second = approval.previous_physical_attempt_id
        if second == approval.prior_attempt_id:
            raise BudgetDenied("Two distinct prior holds required")
        row = db.execute("SELECT account_id,state,reserved,actual,provider_id,usage FROM live_attempts WHERE id=?", (second,)).fetchone()
        if (not row or row[:5] != (ACCOUNT, "unresolved", 1312256, None, approval.previous_physical_provider_id)
                or self.prior_digest(db, second) != approval.previous_physical_row_sha256
                or self.previous_permit_digest(db) != approval.previous_physical_permit_sha256
                or db.execute("SELECT reference FROM live_events WHERE kind=?", (RESERVATION_EVENT,)).fetchall() != [(second,)]
                or len(db.execute("SELECT 1 FROM live_events WHERE kind=?", (APPROVAL_EVENT,)).fetchall()) != 1):
            raise BudgetDenied("Prior physical permit or held attempt changed")
        try:
            if json.loads(row[5])["output_tokens"] != 512:
                raise ValueError
        except (ValueError, TypeError, KeyError):
            raise BudgetDenied("Prior truncated-response usage required") from None
        if db.execute("SELECT 1 FROM live_attempts WHERE id NOT IN (?,?,?)",
                      (approval.prior_attempt_id, second, own_attempt or "")).fetchone():
            raise BudgetDenied("No additional attempt is authorized")

    def output_bound_for_attempt(self, db, attempt):
        if db.execute("SELECT reference FROM live_events WHERE kind=?", (self.reservation_event,)).fetchall() == [(attempt,)]:
            return RETEST_OUTPUT
        return OUTPUT_LIMIT
