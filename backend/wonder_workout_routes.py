"""Muse Wonder explains a planned workout (docs/architecture/WONDER_WORKOUT_API.md).

POST .../preview computes the facts and shows exactly what would be sent, plus
any saved explanation. POST /v1/wonder/workout sends it only with the user's
consent to that exact payload, through the same account ledger, live
configuration and one-in-flight lock as trend explanations, and never pays
twice for the same data. Installed after install_wonder_trend_routes.
"""
from datetime import datetime, timezone
import json
from typing import Annotated, Literal

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import Field, field_validator, model_validator

from ai.hydration.models import CalculationError
from .meta_experiments import ExperimentQuote
from .personal_forecasts import ExerciseInput
from .recognition import RecognitionUnavailable
from .wonder_results import load_workout, save_result
from .wonder_workout import build_facts, preview
from .workout_forecasts import WorkoutForecastInput


class WorkoutExplanationInput(WorkoutForecastInput):
    """The existing personal workout-forecast request: a planned workout plus caller-supplied history."""
    mode: Literal["personal"] = "personal"
    exercise: ExerciseInput

    @model_validator(mode="after")
    def planned_not_completed(self):
        if self.exercise.actual is not None:
            raise ValueError("A planned workout carries no completed measurement")
        return self


class WorkoutExplanationRequest(WorkoutExplanationInput):
    payload_sha256: Annotated[str, Field(strict=True, pattern=r"^[a-f0-9]{64}$")]
    consent_to_send: Literal[True]

    @field_validator("consent_to_send", mode="before")
    @classmethod
    def explicit_true(cls, value):
        if value is not True:  # 1, 1.0 and "true" are not consent
            raise ValueError("Explicit consent required")
        return value


def install_wonder_workout_routes(app, *, error_response) -> None:
    def facts_for(payload: WorkoutExplanationInput) -> dict:
        try:
            return build_facts(payload.exercise.engine(), tuple(sample.engine() for sample in payload.samples),
                               payload.timezone, datetime.now(timezone.utc))
        except (CalculationError, ValueError):
            raise HTTPException(422, "invalid_request") from None

    def saved(payload_sha256: str | None) -> dict | None:
        results_dir = app.state.wonder_results_dir
        try:
            return load_workout(results_dir, payload_sha256) if results_dir and payload_sha256 else None
        except (OSError, ValueError):
            return None

    @app.post("/v1/wonder/workout/preview")
    def workout_preview(payload: WorkoutExplanationInput, request: Request):
        view = preview(facts_for(payload))
        config = app.state.wonder_live_config
        return {**view, "live_available": app.state.wonder_trends_gateway is not None,
                "account_id": config.account if config else None, "saved": saved(view["payload_sha256"])}

    @app.post("/v1/wonder/workout")
    def explain_workout(payload: WorkoutExplanationRequest, request: Request):
        request_id = request.scope["state"]["request_id"]
        view = preview(facts_for(payload))
        if not view["explainable"]:
            return error_response("workout_insufficient_history", 422, request_id)
        if view["payload_sha256"] != payload.payload_sha256:
            return error_response("workout_preview_stale", 409, request_id, retryable=True)
        if (recorded := saved(payload.payload_sha256)) is not None:
            return {"replayed": True, "saved": True, "result": recorded}
        factory, config = app.state.wonder_trends_gateway, app.state.wonder_live_config
        if factory is None or config is None:
            return error_response("wonder_unavailable", 503, request_id)
        # One Wonder request in flight per backend, shared with trends and synthetic runs.
        if not app.state.wonder_lock.acquire(blocking=False):
            return error_response("wonder_busy", 409, request_id, retryable=True)
        try:
            gateway = factory()
            try:
                quote = ExperimentQuote.model_validate_json(config.quote_path.read_text())
                result = gateway.explain_workout(view["facts"], quote,
                                                 f"in-app-workout-consent:{request_id}:{payload.payload_sha256}")
            except (RecognitionUnavailable, OSError, ValueError):
                if gateway.last_attempt is None:
                    return error_response("wonder_blocked", 409, request_id)
                response = error_response("wonder_attempt_unresolved", 502, request_id)
                # A billable request may have been sent: name the attempt so a developer can reconcile it.
                return JSONResponse({**json.loads(response.body), "attempt_id": gateway.last_attempt},
                                    status_code=502, headers={k: v for k, v in response.headers.items() if k != "content-length"})
        finally:
            app.state.wonder_lock.release()
        try:
            save_result(app.state.wonder_results_dir, result)
            stored = True
        except (OSError, ValueError):
            stored = False  # The settled attempt stays in the ledger; still show what was paid for.
        return {"replayed": False, "saved": stored, "result": result}
