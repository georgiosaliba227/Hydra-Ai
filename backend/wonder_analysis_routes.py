"""Consent to an exact eight-section aggregate payload; disabled by default."""
from datetime import datetime, timezone
import json
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import Field, field_validator

from ai.hydration.models import CalculationError
from .hydration_analysis import build_analysis
from .meta_experiments import ExperimentQuote
from .recognition import RecognitionUnavailable
from .wonder_results import load_analysis, save_result
from . import wonder_analysis
from .workout_forecasts import WorkoutForecastInput
from .wonder_trends import build_facts as build_trend_facts


class AnalysisExplanationRequest(WorkoutForecastInput):
    mode: Literal["personal"] = "personal"
    payload_sha256: Annotated[str, Field(strict=True, pattern=r"^[a-f0-9]{64}$")]
    consent_to_send: Literal[True]

    @field_validator("consent_to_send", mode="before")
    @classmethod
    def explicit_true(cls, value):
        if value is not True:
            raise ValueError("Explicit consent required")
        return value


def install_wonder_analysis_routes(app, to_engine, *, enabled: bool, error_response) -> None:
    def facts_for(payload: WorkoutForecastInput) -> dict:
        # Consent to server processing is already required by WorkoutForecastInput.
        # Preview never discloses data externally, and synthetic reads no real logs.
        now = datetime.now(timezone.utc)
        records = [] if payload.mode == "synthetic_demo" else app.state.repository.list_all("local-demo")
        logs = tuple(to_engine(record) for record in records)
        try:
            local = build_analysis(payload, logs, generated_at=now)
            context = None
            if payload.mode == "personal":
                # Reuse the existing descriptive calculation, then allowlist only
                # numeric aggregates. Future timestamps and free category text
                # never enter the rich payload.
                observed = [record for record, log in zip(records, logs, strict=True) if log.consumed_at <= now]
                try:
                    trends = build_trend_facts(observed, None, payload.timezone, now.astimezone(ZoneInfo(payload.timezone)).date())
                    context = {"last_7_days": {key: trends["last_7_days"][key] for key in ("total_ml", "logged_days")},
                               "previous_7_days": {key: trends["previous_7_days"][key] for key in ("total_ml", "logged_days")},
                               "change_pct": trends["change_pct"], "time_of_day_ml": trends["time_of_day_ml"]}
                except ValueError:
                    pass  # Unsupported aggregation never invents a pattern.
            return wonder_analysis.build_facts(local, trend_context=context)
        except (ValueError, CalculationError):
            raise HTTPException(422, "invalid_request") from None

    def view_for(payload: WorkoutForecastInput) -> dict:
        view = wonder_analysis.preview(facts_for(payload))
        facts = view["facts"]
        # Local missing-data explanations remain available, without paying for
        # an entirely empty personal record or sending a synthetic case here.
        has_evidence = (facts["calibration"]["total_samples"] > 0 or facts["intake"]["beverage_count"]
                        or facts["trends"]["logged_days"] or facts["forecast"]["status"] == "estimated")
        if payload.mode == "synthetic_demo" or not has_evidence:
            view.update(explainable=False, reason="personal_observation_or_log_required" if payload.mode == "personal"
                        else "synthetic_live_dispatch_not_supported")
        config = app.state.wonder_live_config
        view.update(dispatch_supported=enabled,
                    live_available=bool(enabled and view["explainable"] and config and app.state.wonder_trends_gateway),
                    account_id=config.account if config else None, saved=None)
        directory = app.state.wonder_results_dir
        if directory and payload.mode == "personal":
            try:
                view["saved"] = load_analysis(directory, view["payload_sha256"])
            except (OSError, ValueError):
                pass
        return view

    @app.post("/v1/wonder/analysis/preview")
    def analysis_preview(payload: WorkoutForecastInput):
        return view_for(payload)

    @app.post("/v1/wonder/analysis")
    def explain_analysis(payload: AnalysisExplanationRequest, request: Request):
        request_id = request.state.request_id
        if not app.state.wonder_lock.acquire(blocking=False):
            return error_response("wonder_busy", 409, request_id, retryable=True)
        try:
            view = view_for(payload)
            if view["payload_sha256"] != payload.payload_sha256:
                return error_response("analysis_preview_stale", 409, request_id, retryable=True)
            if view["saved"] is not None:
                return {"replayed": True, "saved": True, "result": view["saved"]}
            if not view["explainable"]:
                return error_response("analysis_insufficient_data", 422, request_id)
            factory, config = app.state.wonder_trends_gateway, app.state.wonder_live_config
            if not enabled or factory is None or config is None:
                return error_response("wonder_unavailable", 503, request_id)
            gateway = factory()
            try:
                quote = ExperimentQuote.model_validate_json(config.quote_path.read_text())
                result = gateway.explain_analysis(view["facts"], quote,
                    f"in-app-analysis-consent:{request_id}:{payload.payload_sha256}")
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
            return {"replayed": False, "saved": saved, "result": result}
        finally:
            app.state.wonder_lock.release()
