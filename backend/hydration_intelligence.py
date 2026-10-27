"""Synthetic-only controlled Meta test; engine values never come from model output."""
from datetime import date
from enum import Enum
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator
from ai.hydration import summarize_day
from ai.hydration.models import BeverageLog, METHOD_VERSION
from .meta_accounts import ACCOUNTS
from .meta_gateway import GuardedMetaGateway
from .meta_provider import OfficialMetaTransport, ProviderReply, strict_json
from .meta_policy import OUTPUT_LIMIT
from .recognition import MODEL, RecognitionUnavailable


class Signal(str, Enum):
    review_intake = "review_intake"
    activity_context = "activity_context"
    composition_missing = "composition_missing"
    supplement_uncertain = "supplement_uncertain"


EXPLANATIONS = {
    Signal.review_intake: "Review confirmed beverage intake alongside your activity and feedback.",
    Signal.activity_context: "Activity and weather provide context; they do not establish dehydration or a fluid prescription.",
    Signal.composition_missing: "Missing verified beverage composition limits water and electrolyte estimates.",
    Signal.supplement_uncertain: "Supplement use alone does not justify an extra fluid adjustment.",
}


class SyntheticContext(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: Literal["hydration-context-v1"] = "hydration-context-v1"
    synthetic: Literal[True]
    disclosure_consent: Literal[True]
    beverage_total_ml: float = Field(ge=0, le=50000, allow_inf_nan=False)
    estimated_water_ml: float | None = Field(default=None, ge=0, le=50000, allow_inf_nan=False)
    workout_minutes: StrictInt | None = Field(default=None, ge=0, le=1440)
    workout_intensity: Literal["low", "moderate", "high", "missing"] = "missing"
    temperature_c: float | None = Field(default=None, ge=-60, le=60, allow_inf_nan=False)
    humidity_percent: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    estimated_sweat_loss_ml: float | None = Field(default=None, ge=0, le=20000, allow_inf_nan=False)
    creatine_reported: bool | None = None
    feedback: Literal["comfortable", "thirst_reported", "missing"] = "missing"
    method: Literal["hydration-accounting-v1"] = METHOD_VERSION

    @model_validator(mode="after")
    def consistent_water_content(self):
        if self.estimated_water_ml is not None and self.estimated_water_ml > self.beverage_total_ml:
            raise ValueError("Estimated water cannot exceed beverage volume")
        return self

    @field_validator("synthetic", "disclosure_consent", mode="before")
    @classmethod
    def explicit_true(cls, value):
        if value is not True:
            raise ValueError("Explicit synthetic-data and disclosure attestation required")
        return True


def context_from_engine(logs: tuple[BeverageLog, ...], day: date, timezone: str, **context) -> SyntheticContext:
    """Caller supplies ONLY synthetic logs; raw HealthKit export is unsupported."""
    summary = summarize_day(logs, day, timezone)
    return SyntheticContext(
                            beverage_total_ml=summary.beverage_total_ml,
                            estimated_water_ml=summary.estimated_water_ml, **context)


class Interpretation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    signals: list[Signal] = Field(min_length=1, max_length=4)


def hydration_payload(context: SyntheticContext) -> dict:
    return {"model": MODEL, "store": False, "stream": False, "background": False,
            "max_output_tokens": OUTPUT_LIMIT, "reasoning": {"effort": "minimal"},
            "text": {"format": {"type": "json_schema", "name": "hydration_context", "strict": True,
                                "schema": Interpretation.model_json_schema()}},
            "input": [{"role": "user", "content": [{"type": "input_text", "text":
                "Select relevant explanation signals for this synthetic context. Intake is engine-accounted; water and sweat are estimates; null is missing. No validated prediction is available. Never diagnose, calculate fluid targets, infer dehydration from activity, or adjust for creatine. No tools. Context: " + context.model_dump_json()}]}]}


def context_fingerprint(context: SyntheticContext) -> str:
    return hashlib.sha256(json.dumps(hydration_payload(context), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class HydrationMetaTransport(OfficialMetaTransport):
    def validate_payload(self, payload: dict) -> None:
        text = payload["input"][0]["content"][0]["text"]
        context = SyntheticContext.model_validate_json(text.split("Context: ", 1)[1])
        if payload != hydration_payload(context):
            raise ValueError


def parse_interpretation(reply: ProviderReply) -> list[str]:
    try:
        body = reply.body
        if reply.status != 200 or body.get("model") != MODEL or body.get("status") != "completed" or body.get("error") is not None or body.get("incomplete_details") is not None:
            raise ValueError
        messages = [item for item in body["output"] if item.get("type") != "reasoning"]
        if len(messages) != 1 or messages[0]["type"] != "message" or messages[0]["role"] != "assistant" or messages[0]["status"] != "completed":
            raise ValueError
        parts = messages[0]["content"]
        if len(parts) != 1 or parts[0]["type"] != "output_text":
            raise ValueError
        parsed = Interpretation.model_validate_json(json.dumps(strict_json(parts[0]["text"])))
        return [EXPLANATIONS[signal] for signal in dict.fromkeys(parsed.signals)]
    except (ValueError, KeyError, TypeError, AttributeError):
        raise RecognitionUnavailable() from None


class HydrationIntelligence(GuardedMetaGateway):
    def explain(self, context: SyntheticContext) -> dict:
        attempt = None
        try:
            if self.account != ACCOUNTS[1]:
                raise ValueError
            context = SyntheticContext.model_validate(context.model_dump())
            self.ledger.verify_credential(self.account, self.transport.credential_fingerprint)
            self.ledger.verify_purpose(self.account, "hydration")
            payload = hydration_payload(context)
            bound = self.transport.input_bound(payload)
            self.ledger.quote(self.account, bound)
            attempt = self.ledger.reserve_first(self.account, context_fingerprint(context), bound)
            self.deliver_pending_notices()
            ticket = self.ledger.mark_dispatched(attempt, context_fingerprint(context))
            reply = self.transport.generate(payload, ticket)
            self.ledger.settle_provider_reply(attempt, reply)
            explanations = parse_interpretation(reply)
            return {"version": "hydration-explanation-v1", "attempt_id": attempt,
                    "context": context.model_dump(), "explanations": explanations,
                    "prediction": None, "missing_information": [name for name, value in context.model_dump().items() if value is None or value == "missing"]}
        except Exception:
            if attempt is not None:
                try:
                    self.ledger.quarantine(attempt)
                    self.deliver_pending_notices()
                except Exception:
                    pass  # Durable reservation remains; unavailable storage fails closed.
            raise RecognitionUnavailable() from None
