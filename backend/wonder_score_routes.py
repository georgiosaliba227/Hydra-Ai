"""Exact Home aggregate preview and separately consented single-send explanation."""
from datetime import datetime, timezone
import json
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .hydration_score import GoalRequired, build_facts
from .recognition import RecognitionUnavailable
from .wonder_results import load_score, save_result
from . import wonder_score


class ScorePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    timezone: Annotated[str, Field(min_length=1, max_length=128)]
    measurement_count: Annotated[int, Field(strict=True, ge=0, le=32)]
    processing_consent: Literal[True]

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        try:
            ZoneInfo(value)
        except (ValueError, KeyError):
            raise ValueError("Valid timezone required") from None
        return value

    @field_validator("processing_consent", mode="before")
    @classmethod
    def explicit_processing(cls, value):
        if value is not True:
            raise ValueError("Explicit processing consent required")
        return value


class ScoreExplanationRequest(ScorePreviewRequest):
    payload_sha256: Annotated[str, Field(strict=True, pattern=r"^[a-f0-9]{64}$")]
    consent_to_send: Literal[True]

    @field_validator("consent_to_send", mode="before")
    @classmethod
    def explicit_meta(cls, value):
        if value is not True:
            raise ValueError("Explicit Meta consent required")
        return value


def install_wonder_score_routes(app, *, enabled: bool, error_response) -> None:
    def view_for(payload: ScorePreviewRequest) -> dict:
        repository = app.state.repository
        goal = (repository.get_settings("local-demo") or {}).get("daily_beverage_goal_ml")
        facts = build_facts(repository.list_all("local-demo"), goal, payload.timezone,
                            payload.measurement_count, now=datetime.now(timezone.utc))
        view = wonder_score.preview(facts)
        config = app.state.wonder_live_config
        view.update(live_available=bool(enabled and config and app.state.wonder_trends_gateway
                                        and config.readiness()["status"] == "ready"),
                    account_id=config.account if config else None)
        directory = app.state.wonder_results_dir
        if directory is not None:
            try:
                view["saved"] = load_score(directory, view["payload_sha256"])
            except (OSError, ValueError):
                pass  # Invalid saved data is neither displayed nor reclassified as fresh.
        return view

    @app.post("/v1/wonder/score/preview")
    def score_preview(payload: ScorePreviewRequest, request: Request):
        try:
            return view_for(payload)
        except GoalRequired:
            return error_response("goal_required", 422, request.state.request_id)
        except (ValueError, KeyError, OSError):
            return error_response("invalid_request", 422, request.state.request_id)

    @app.post("/v1/wonder/score")
    def explain_score(payload: ScoreExplanationRequest, request: Request):
        request_id = request.state.request_id
        if not app.state.wonder_lock.acquire(blocking=False):
            return error_response("wonder_busy", 409, request_id, retryable=True)
        try:
            try:
                view = view_for(payload)
            except GoalRequired:
                return error_response("goal_required", 422, request_id)
            except (ValueError, KeyError, OSError):
                return error_response("invalid_request", 422, request_id)
            if view["payload_sha256"] != payload.payload_sha256:
                return error_response("score_preview_stale", 409, request_id, retryable=True)
            if view["saved"] is not None:
                return {"replayed": True, "saved": True, "result": view["saved"]}
            factory, config = app.state.wonder_trends_gateway, app.state.wonder_live_config
            if not enabled or factory is None or config is None:
                return error_response("wonder_unavailable", 503, request_id)
            if config.financial_policy == "owner_accepted_risk" and config.readiness()["status"] != "ready":
                return error_response("wonder_blocked", 409, request_id)
            gateway = factory()
            try:
                quote = config.read_quote()
                result = gateway.explain_score(view["facts"], quote,
                    f"in-app-score-consent:{request_id}:{payload.payload_sha256}")
            except (RecognitionUnavailable, OSError, ValueError):
                if gateway.last_attempt is None:
                    return error_response("wonder_blocked", 409, request_id)
                response = error_response("wonder_attempt_unresolved", 502, request_id)
                return JSONResponse({**json.loads(response.body), "attempt_id": gateway.last_attempt}, status_code=502,
                    headers={key: value for key, value in response.headers.items() if key != "content-length"})
            try:
                save_result(app.state.wonder_results_dir, result)
                saved = True
            except (OSError, ValueError):
                saved = False
                if hasattr(gateway, "record_save_failure"):
                    try:
                        gateway.record_save_failure()
                    except Exception:
                        pass
            if saved and hasattr(gateway, "record_result_saved"):
                try:
                    gateway.record_result_saved(result)
                except Exception:
                    pass  # Saved replay remains available; audit failure blocks later paid admission.
            return {"replayed": False, "saved": saved, "result": result}
        finally:
            app.state.wonder_lock.release()
