"""Live Muse Wonder on Hydra's fixed synthetic payloads, for the owner or a restricted developer.

Each synthetic scenario and suggested question is sent at most once under the
allocation's standing synthetic approval, then replayed from its saved result.
The ledger records which credential asked. No personal data is involved.
See docs/architecture/SHARED_BACKEND.md.
"""
from typing import Literal

from fastapi import Request
from fastapi.responses import JSONResponse
import json
from pydantic import BaseModel, ConfigDict, Field

from ai.assistant import SUGGESTED
from .hydration_context_v2 import SCENARIOS
from .meta_budget import BudgetDenied
from .meta_experiments import ExperimentQuote
from .recognition import RecognitionUnavailable
from .wonder_assistant import assistant_payload
from .wonder_hydration import input_bound, payload_sha256, wonder_payload, worst_case_micro_usd
from .wonder_results import load_recorded, load_recorded_answer, save_result

VERSION = "wonder-live-v1"


class LiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["scenario", "question"]
    id: str = Field(min_length=1, max_length=64)
    confirm_billable: Literal[True]


def _payload(kind: str, identifier: str) -> dict:
    if kind == "scenario" and identifier in SCENARIOS:
        return wonder_payload(identifier)
    if kind == "question" and identifier in SUGGESTED:
        return assistant_payload(identifier)
    raise ValueError("Unknown synthetic case")


def install_wonder_live_routes(app, *, error_response) -> None:
    def recorded(kind: str, identifier: str) -> dict | None:
        directory = app.state.wonder_results_dir
        try:
            if directory is None:
                return None
            return load_recorded(directory, identifier) if kind == "scenario" else load_recorded_answer(directory, identifier)
        except (OSError, ValueError):
            return None

    @app.get("/v1/wonder/live")
    def live_status():
        config = app.state.wonder_live_config
        items = []
        for kind, names in (("scenario", SCENARIOS), ("question", tuple(SUGGESTED))):
            for name in names:
                payload = _payload(kind, name)
                items.append({"kind": kind, "id": name, "payload_sha256": payload_sha256(payload),
                              "worst_case_micro_usd": worst_case_micro_usd(input_bound(payload)),
                              "recorded": recorded(kind, name) is not None})
        allocation = None
        if config is not None:
            try:
                allocation = config.ledger.snapshot()
            except BudgetDenied:
                allocation = None
        return {"version": VERSION, "live_available": app.state.wonder_trends_gateway is not None,
                "account_id": config.account if config else None, "allocation": allocation, "items": items}

    @app.post("/v1/wonder/live")
    def run_live(payload: LiveRequest, request: Request):
        request_id = request.scope["state"]["request_id"]
        try:
            _payload(payload.kind, payload.id)
        except ValueError:
            return error_response("not_found", 404, request_id)
        if (saved := recorded(payload.kind, payload.id)) is not None:
            return {"replayed": True, "saved": True, "result": saved}
        factory, config = app.state.wonder_trends_gateway, app.state.wonder_live_config
        if factory is None or config is None:
            return error_response("wonder_unavailable", 503, request_id)
        if not app.state.wonder_lock.acquire(blocking=False):
            return error_response("wonder_busy", 409, request_id, retryable=True)
        try:
            gateway = factory()
            # The ledger's case record names the credential that asked, for per-developer audit.
            reference = f"{request.scope['state']['principal']}:{request_id}"
            try:
                quote = ExperimentQuote.model_validate_json(config.quote_path.read_text())
                result = (gateway.explain_synthetic(payload.id, quote, reference) if payload.kind == "scenario"
                          else gateway.answer_synthetic(payload.id, quote, reference))
            except (RecognitionUnavailable, OSError, ValueError):
                if gateway.last_attempt is None:
                    return error_response("wonder_blocked", 409, request_id)
                response = error_response("wonder_attempt_unresolved", 502, request_id)
                return JSONResponse({**json.loads(response.body), "attempt_id": gateway.last_attempt},
                                    status_code=502, headers=dict(response.headers))
        finally:
            app.state.wonder_lock.release()
        try:
            save_result(app.state.wonder_results_dir, result)
            stored = True
        except (OSError, ValueError):
            stored = False
        return {"replayed": False, "saved": stored, "result": result}
