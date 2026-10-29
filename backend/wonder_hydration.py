"""Muse Wonder 1.0 hydration-context requests: payload, cost bounds and strict parsing.

Mock-only (docs/architecture/WONDER_HYDRATION_API.md). This module holds no
credential, transport, ledger or dispatch path. A live adapter is a separate,
independently reviewed change charged to Georgio's $30 experiment allocation.
"""
import hashlib
import json

from fastapi.encoders import jsonable_encoder

from .hydration_context_v2 import PROMPT, SCENARIOS, Selection, build_scenario, validate_selection
from .meta_accounts import CAP
from .meta_experiments import ACCOUNT, REFERENCE_PRICES
from .meta_policy import MAX_INPUT_TOKENS, OUTPUT_LIMIT
from .meta_provider import ProviderReply, strict_json
from .recognition import RecognitionUnavailable

MODEL = "muse-wonder-1.0"
VERSION = "wonder-hydration-context-v1"
# Micro-USD per million uncached input / output tokens; no cache discount is assumed.
INPUT_PRICE, OUTPUT_PRICE = REFERENCE_PRICES[MODEL]
# Input bound policy: at most one input token per byte of the canonical payload
# JSON (which already includes schema, keys and quoting), plus a fixed allowance
# for provider-side role/format framing. Settlement freezes the account if the
# provider reports more input tokens than this bound.
INPUT_BOUND_POLICY = "canonical-payload-bytes-v1"
FRAMING_ALLOWANCE_TOKENS = 256


def canonical(value) -> str:
    return json.dumps(jsonable_encoder(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def selection_schema() -> dict:
    """Strict json_schema: titles/defaults removed, every object property required."""
    def compact(value):
        if isinstance(value, dict):
            result = {key: compact(item) for key, item in value.items() if key not in ("title", "default")}
            if result.get("type") == "object":
                result["required"] = list(result.get("properties", {}))
            return result
        if isinstance(value, list):
            return [compact(item) for item in value]
        return value
    return compact(Selection.model_json_schema())


def wonder_payload(scenario: str) -> dict:
    """Server-owned synthetic scenario only; no caller context reaches the payload."""
    context, prediction = build_scenario(scenario)
    return {"model": MODEL, "store": False, "stream": False, "background": False,
            "max_output_tokens": OUTPUT_LIMIT, "reasoning": {"effort": "minimal"},
            "text": {"format": {"type": "json_schema", "name": "hydration_context_selection", "strict": True,
                                "schema": selection_schema()}},
            "input": [{"role": "user", "content": [{"type": "input_text",
                "text": PROMPT + " Context: " + canonical({"context": context, "prediction": prediction})}]}]}


def payload_json(payload: dict) -> str:
    """Byte-identical to the digest a DispatchTicket claim computes before sending."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def payload_sha256(payload: dict) -> str:
    return hashlib.sha256(payload_json(payload).encode()).hexdigest()


def input_bound(payload: dict) -> int:
    return len(payload_json(payload).encode()) + FRAMING_ALLOWANCE_TOKENS


def worst_case_micro_usd(input_tokens: int, output_tokens: int = OUTPUT_LIMIT) -> int:
    """Upper-bound token charge, rounded up. Every generated token is priced as output."""
    for value in (input_tokens, output_tokens):
        if type(value) is not int or value < 0:
            raise ValueError("Token bounds must be nonnegative integers")
    return (input_tokens * INPUT_PRICE + output_tokens * OUTPUT_PRICE + 999_999) // 1_000_000


def preview(scenario: str) -> dict:
    """Read-only approval evidence. Neither bound is a provider billing guarantee."""
    payload = wonder_payload(scenario)
    full_context = worst_case_micro_usd(MAX_INPUT_TOKENS)
    payload_bytes = len(payload_json(payload).encode())
    return {"version": VERSION, "scenario": scenario, "model": MODEL, "account_id": ACCOUNT,
            "payload_sha256": payload_sha256(payload), "payload_bytes": payload_bytes,
            "max_output_tokens": OUTPUT_LIMIT, "per_attempt_cap_micro_usd": CAP,
            "full_context_bound_micro_usd": full_context, "admissible_under_cap": full_context <= CAP,
            "input_bound_policy": INPUT_BOUND_POLICY, "input_bound_tokens": input_bound(payload),
            "byte_bound_micro_usd": worst_case_micro_usd(input_bound(payload)),
            "dispatch_enabled": False, "billing_evidence": False}


def parse_selection(reply: ProviderReply, scenario: str) -> dict:
    """Untrusted Wonder output to a validated selection; no repair, retry or fallback."""
    context, prediction = build_scenario(scenario)
    try:
        body = reply.body
        if (reply.status != 200 or body.get("model") != MODEL or body.get("status") != "completed"
                or body.get("error") is not None or body.get("incomplete_details") is not None):
            raise ValueError
        messages = [item for item in body["output"] if item.get("type") != "reasoning"]
        if len(messages) != 1 or messages[0]["type"] != "message" or messages[0]["role"] != "assistant" or messages[0]["status"] != "completed":
            raise ValueError
        parts = messages[0]["content"]
        if len(parts) != 1 or parts[0]["type"] != "output_text":
            raise ValueError
        if not isinstance(parts[0]["text"], str) or len(parts[0]["text"]) > 4096:
            raise ValueError
        return validate_selection(strict_json(parts[0]["text"]), context, prediction)
    except (ValueError, KeyError, TypeError, AttributeError):
        raise RecognitionUnavailable() from None


if __name__ == "__main__":
    print(json.dumps([preview(name) for name in SCENARIOS], indent=2, sort_keys=True))
