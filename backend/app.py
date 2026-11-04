"""Local single-user FastAPI adapter for durable, confirmed beverage accounting."""
import base64
from dataclasses import asdict
from datetime import date, datetime, timezone as dt_timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
from typing import Annotated
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from ai.hydration import BeverageLog, calculate_contribution, summarize_day
from ai.hydration.models import Composition, METHOD_VERSION
from database.repository import (BeverageNotFound, BeverageRepository, IdempotencyConflict, RevisionConflict,
                                 StorageUnavailable)
from .recognition import AnalysisRequest, AnalysisResult, Candidate, MockMetaRecognizer, RecognitionUnavailable, LOCAL_MODEL
from .recognition_feedback import candidate_key, product_signature
from .label_volume import label_capacity_ml
from .meta_images import sanitized_jpeg
from .nutrition import lookup
from .meta_accounts import AccountLedger, ACCOUNTS
from .meta_gateway import GuardedMetaGateway, GitHubNotifier
from .meta_provider import OfficialMetaTransport
from .meta_budget import BudgetDenied
from .schemas import CreateBeverageRequest, SettingsUpdate, UpdateBeverageRequest, utc_string

MAX_BODY_BYTES = 16 * 1024


def error_response(code: str, status: int, request_id: str, *, retryable: bool = False) -> JSONResponse:
    messages = {
        "unauthorized": "A valid development session is required.",
        "invalid_request": "The request is invalid.",
        "idempotency_conflict": "This request key was already used for different data.",
        "revision_conflict": "This beverage changed since it was loaded. Reload it and try again.",
        "storage_unavailable": "Storage is temporarily unavailable.",
        "internal_error": "The request could not be completed.",
        "not_found": "The requested resource does not exist.",
        "method_not_allowed": "This method is not supported.",
        "request_too_large": "The request exceeds the size limit.",
        "recognition_unavailable": "Photo analysis is unavailable. Log manually or ask a developer to review the attempt.",
        "hydration_unavailable": "Hydration explanation is unavailable. Ask a developer to review the attempt.",
        "wonder_unavailable": "Live Muse Wonder is not configured on this backend.",
        "wonder_busy": "Another Muse Wonder request is in progress.",
        "wonder_blocked": "Muse Wonder is paused by a spending safeguard. Nothing was sent or charged.",
        "wonder_attempt_unresolved": "The Muse Wonder request failed after it was reserved. Do not retry; a developer must reconcile the attempt.",
        "trends_preview_stale": "Your log changed since the preview. Review the new preview first.",
        "trends_insufficient_data": "Log drinks in the last 14 days before asking for trends.",
        "workout_preview_stale": "Your planned workout or history changed since the preview. Review the new preview first.",
        "workout_insufficient_history": "Add at least one previous session of this activity before asking for an explanation.",
        "analysis_preview_stale": "The included workout, history or beverage totals changed. Review the new preview first.",
        "analysis_insufficient_data": "The analysis is unavailable for this record. Review its missing information and cost bound.",
    }
    return JSONResponse(
        {"code": code, "message": messages.get(code, "The request could not be completed."),
         "request_id": request_id, "retryable": retryable},
        status_code=status, headers={"X-Request-ID": request_id, "Cache-Control": "no-store"},
    )


class RequestGuard:
    """Bound payloads before parsing; avoid logging or retaining rejected bodies."""

    def __init__(self, app, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        if scope["path"].startswith(("/v1", "/v2", "/v3")):
            provided = headers.get(b"authorization", b"")
            expected = ("Bearer " + self.token).encode()
            if not hmac.compare_digest(provided, expected):
                await error_response("unauthorized", 401, request_id)(scope, receive, send)
                return
        if scope["path"] == "/v1/recognitions":
            body_limit = 1_400_000
        elif scope["path"] == "/v1/beverages":
            # A confirmed photo may carry its image only for separately opted-in
            # training collection. The typed schema rejects all other images.
            body_limit = 1_450_000
        elif scope["path"] in ("/v1/workout-forecasts", "/v2/workout-forecasts", "/v1/hydration-analysis", "/v1/wonder/workout/preview",
                               "/v1/wonder/workout", "/v1/wonder/analysis/preview", "/v1/wonder/analysis",
                               "/v3/workout-forecasts", "/v3/hydration-analysis", "/v3/wonder/analysis/preview",
                               "/v3/wonder/analysis"):
            body_limit = 128 * 1024  # Up to 32 bounded calibration samples.
        else:
            body_limit = MAX_BODY_BYTES
        length = headers.get(b"content-length")
        if length is not None:
            try:
                size = int(length)
            except ValueError:
                size = -1
            if size < 0:
                await error_response("invalid_request", 422, request_id)(scope, receive, send)
                return
            if size > body_limit:
                await error_response("request_too_large", 413, request_id)(scope, receive, send)
                return
        chunks = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            data = message.get("body", b"")
            size += len(data)
            if size > body_limit:
                await error_response("request_too_large", 413, request_id)(scope, receive, send)
                return
            chunks.append(data)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        if scope["path"] == "/v1/beverages" and size > MAX_BODY_BYTES:
            try:
                envelope=json.loads(body)
                feedback=envelope.get("recognition_feedback")
                if (not isinstance(feedback,dict) or feedback.get("share_for_training") is not True
                        or feedback.get("training_consent_version")!="hydra-training-photo-correction-v1"
                        or not isinstance(feedback.get("training_photo_base64"),str)):
                    raise ValueError
            except (ValueError,TypeError,AttributeError,RecursionError):
                await error_response("request_too_large",413,request_id)(scope,receive,send)
                return
        delivered = False

        async def buffered_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        started = False

        async def response_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                message["headers"] = [
                    (k, v) for k, v in message.get("headers", [])
                    if k.lower() not in (b"cache-control", b"x-request-id")
                ] + [(b"cache-control", b"no-store"), (b"x-request-id", request_id.encode())]
            await send(message)

        try:
            await self.app(scope, buffered_receive, response_send)
        except Exception:
            # Keep sensitive exceptions out of the ASGI server log. Non-streaming
            # endpoints finish calculation before response headers are sent.
            if not started:
                await error_response("internal_error", 500, request_id)(scope, receive, send)
            else:
                raise


def to_engine(record: dict) -> BeverageLog:
    return BeverageLog(
        id=UUID(record["id"]), revision=record["revision"], category=record["category"],
        consumed_ml=record["consumed_ml"], consumed_at=datetime.fromisoformat(record["consumed_at"]),
        timezone=record["timezone"], source=record["source"], provenance=tuple(record["provenance"]),
        nutrition=Composition(**{**record["nutrition"], "provenance": tuple(record["nutrition"]["provenance"])}) if record.get("nutrition") else None,
    )


def cursor_encode(record: dict) -> str:
    data = json.dumps([record["consumed_at"], record["id"]], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def cursor_decode(cursor: str) -> tuple[str, str]:
    try:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,512}", cursor):
            raise ValueError
        values = json.loads(base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True))
        if not isinstance(values, list) or len(values) != 2 or not all(isinstance(v, str) for v in values):
            raise ValueError
        instant = datetime.fromisoformat(values[0])
        if instant.tzinfo is None or utc_string(instant) != values[0] or str(UUID(values[1])) != values[1]:
            raise ValueError
        return values[0], values[1]
    except (ValueError, TypeError, OverflowError):
        raise HTTPException(422, "invalid_request") from None


def create_app(db_path: str | Path | None = None, api_token: str | None = None) -> FastAPI:
    """Default to mock; explicit guarded configuration still requires ledger gates."""
    mode = os.getenv("HYDRA_AI_MODE", "mock")
    billable = os.getenv("META_BILLABLE_REQUESTS_ENABLED", "false").lower()
    hydration_enabled = os.getenv("HYDRA_META_HYDRATION_ENABLED", "false").lower()
    wonder_live = os.getenv("HYDRA_WONDER_LIVE", "false").lower()
    analysis_enabled = os.getenv("HYDRA_WONDER_ANALYSIS_ENABLED", "false").lower()
    local_wonder = os.getenv("HYDRA_LOCAL_META_ALLOW_WONDER", "false").lower()
    camera_policy = os.getenv("HYDRA_META_CAMERA_POLICY", "legacy")
    if camera_policy not in ("legacy", "georgio-camera-cutoff-v1"):
        raise ValueError("Unsupported camera policy")
    if (mode not in ("mock", "guarded_meta", "local_meta") or billable not in ("false", "true")
            or hydration_enabled not in ("false", "true") or wonder_live not in ("false", "true")
            or analysis_enabled not in ("false", "true") or local_wonder not in ("false", "true")):
        raise ValueError("Unsupported AI configuration")
    live_feature = mode == "guarded_meta" or hydration_enabled == "true" or wonder_live == "true"
    if local_wonder == "true" and (mode != "local_meta" or wonder_live != "true" or hydration_enabled != "false"):
        raise ValueError("Local camera/Wonder coexistence requires explicit compatible features")
    if mode == "local_meta" and local_wonder != "true" and (billable != "false" or hydration_enabled != "false" or wonder_live != "false"):
        raise ValueError("Local Meta camera cannot enable hosted providers without explicit coexistence")
    if (billable == "true") != live_feature:
        raise ValueError("Mode and billable gate conflict")
    token = api_token if api_token is not None else os.getenv("HYDRA_API_TOKEN", "")
    if not isinstance(token, str) or len(token) < 32 or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError("HYDRA_API_TOKEN must be at least 32 non-whitespace ASCII characters")
    app = FastAPI(title="Hydra AI Local Prototype", version="1.0.0")
    app.state.repository = BeverageRepository(db_path or os.getenv("HYDRA_DATABASE_PATH", "database/hydra.sqlite3"))
    app.state.recognition_mode = "meta_live" if mode == "guarded_meta" else mode
    app.state.data_generation = 0
    app.state.meta_ledger = AccountLedger(os.getenv("HYDRA_META_LEDGER_PATH") or db_path or os.getenv("HYDRA_DATABASE_PATH", "database/hydra.sqlite3"))
    if mode == "guarded_meta":
        account = os.getenv("HYDRA_META_ACCOUNT", "")
        if account not in ACCOUNTS:
            raise ValueError("Select one explicitly authorized Meta account")
        key_name = "HYDRA_META_GEORGIO_API_KEY" if account == "georgiosaliba227" else "HYDRA_META_AMINE_API_KEY"
        if camera_policy == "georgio-camera-cutoff-v1":
            from .meta_camera_cutoff import CutoffCameraLedger, CutoffCameraTransport, CutoffCameraGateway, ACCOUNT
            if account != ACCOUNT or hydration_enabled == "true" or wonder_live == "true":
                raise ValueError("Cutoff camera policy is Georgio camera-only")
            app.state.meta_ledger = CutoffCameraLedger(app.state.meta_ledger.path)
            # Explicit operator activation required; startup never migrates.
            app.state.meta_ledger.cutoff_status()
            app.state.recognizer = CutoffCameraGateway(app.state.meta_ledger, CutoffCameraTransport(os.getenv(key_name, "")))
        else:
            transport = OfficialMetaTransport(os.getenv(key_name, ""))
            notifier = GitHubNotifier(os.getenv("HYDRA_GITHUB_NOTIFICATION_TOKEN", ""))
            # Existing evidence is mandatory; do not create a zero baseline at startup.
            app.state.meta_ledger.project_view()
            app.state.recognizer = GuardedMetaGateway(app.state.meta_ledger, account, transport, notifier)
    elif mode == "local_meta":
        from .local_meta import LocalMetaRecognizer
        if not app.state.repository.feedback_enabled:
            raise ValueError("Local camera requires the separate beverage database")
        app.state.recognizer = LocalMetaRecognizer.from_environment()
    else:
        app.state.recognizer = MockMetaRecognizer()
    app.add_middleware(RequestGuard, token=token)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc):
        return error_response("invalid_request", 422, request.state.request_id)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc):
        code = {404: "not_found", 405: "method_not_allowed", 401: "unauthorized"}.get(exc.status_code, "invalid_request")
        return error_response(code, exc.status_code, request.state.request_id)

    @app.exception_handler(IdempotencyConflict)
    async def conflict(request: Request, exc):
        return error_response("idempotency_conflict", 409, request.state.request_id)

    @app.exception_handler(RevisionConflict)
    async def revision_conflict(request: Request, exc):
        return error_response("revision_conflict", 409, request.state.request_id)

    @app.exception_handler(BeverageNotFound)
    async def beverage_not_found(request: Request, exc):
        return error_response("not_found", 404, request.state.request_id)

    @app.exception_handler(StorageUnavailable)
    async def storage_error(request: Request, exc):
        return error_response("storage_unavailable", 503, request.state.request_id, retryable=True)

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc):
        return error_response("internal_error", 500, getattr(request.state, "request_id", str(uuid4())))

    @app.exception_handler(RecognitionUnavailable)
    async def recognition_error(request: Request, exc):
        return error_response("recognition_unavailable", 503, request.state.request_id, retryable=request.app.state.recognition_mode == "mock")

    @app.get("/v1/recognition-capabilities")
    def recognition_capabilities():
        return {"version": "recognition-v1", "mode": app.state.recognition_mode,
                "correction_memory_available": app.state.repository.feedback_enabled,
                "training_examples_available": app.state.repository.feedback_enabled,
                "provider": "Meta (local trained adapter)" if mode == "local_meta" else "Meta" if mode == "guarded_meta" else None,
                "model": LOCAL_MODEL if mode == "local_meta" else "muse-spark-1.3",
                "dispatch_requires_account_permit_and_verified_bound": mode != "local_meta",
                "privacy": "Photo is processed locally on your configured Mac; no hosted model request." if mode == "local_meta" else "Meta may retain content under its service, safety and legal terms; no zero-retention claim."}

    @app.get("/v1/meta/spending")
    def meta_spending():
        try:
            return app.state.meta_ledger.project_view()
        except BudgetDenied:
            return {"status": "unconfigured", "accounts": [{"account_id": a, "status": "unverified"} for a in ACCOUNTS],
                    "project_gross_micro_usd": None, "project_reserved_micro_usd": None, "credits_transferable": False}

    @app.get("/v1/meta/notices")
    def meta_notices():
        try:
            return {"items": app.state.meta_ledger.notices()}
        except BudgetDenied:
            return {"items": [], "status": "unconfigured"}

    @app.post("/v1/recognitions")
    def analyze_beverage(payload: AnalysisRequest, request: Request):
        if payload.mode != request.app.state.recognition_mode:
            raise RecognitionUnavailable()
        with request.app.state.wonder_lock:
            data_generation = request.app.state.data_generation
        # Validate even injected adapter output, then enrich only from the catalogue.
        try:
            result = AnalysisResult.model_validate(request.app.state.recognizer.analyze(payload)).model_dump()
            result["image_sha256"]=hashlib.sha256(sanitized_jpeg(payload)).hexdigest()
            if not result["candidates"]:
                unknown=Candidate(identity="Unknown beverage",confidence="low",
                                  uncertainty_reasons=["No confident model match; prior user correction is shown separately"]).model_dump()
                memory=request.app.state.repository.correction_for("local-demo",result["mode"],result["image_sha256"],candidate_key(unknown),None)
                if memory is not None:
                    result["candidates"].append(unknown)
            for candidate in result["candidates"]:
                if result["mode"] != "local_meta":
                    candidate["label_capacity_ml"]=label_capacity_ml(candidate.get("visible_label_text"))
                candidate["nutrition"] = lookup(candidate["product_id"], candidate["identity"])
                candidate["personal_correction"]=request.app.state.repository.correction_for(
                    "local-demo",result["mode"],result["image_sha256"],candidate_key(candidate),product_signature(candidate))
            if result["mode"] == "local_meta":
                from .local_meta import ADAPTER_SHA256
                original=[{k:v for k,v in item.items() if k not in ("nutrition","personal_correction")} for item in result["candidates"]]
                with request.app.state.wonder_lock:
                    if data_generation != request.app.state.data_generation:
                        raise RecognitionUnavailable()
                    request.app.state.repository.record_local_recognition("local-demo",{
                        "recognition_id":result["recognition_id"],"image_sha256":result["image_sha256"],
                        "mode":"local_meta","model":LOCAL_MODEL,"adapter_sha256":ADAPTER_SHA256,
                        "created_at":utc_string(datetime.now(dt_timezone.utc)),"candidates":original})
            return result
        except (ValidationError, ValueError):
            raise RecognitionUnavailable() from None

    @app.get("/health")
    def health():
        return {"status": "ok", "ai_mode": app.state.recognition_mode, "billable_requests_enabled": billable == "true", "dispatch_requires_account_permit_and_verified_bound": True}

    @app.post("/v1/beverages", status_code=201)
    def create_beverage(payload: CreateBeverageRequest, request: Request,
                        idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")]):
        canonical = payload.model_dump(mode="json", exclude_none=True)
        canonical["consumed_at"] = utc_string(payload.consumed_at)
        fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        replay=request.app.state.repository.replay("local-demo",str(idempotency_key),fingerprint)
        if replay is not None:
            return JSONResponse(replay,status_code=200)
        provenance = ["user_confirmed_manual"] if payload.source == "manual" else ["user_confirmed_photo", "recognition-v1:mock"]
        local_receipt = (request.app.state.repository.local_recognition("local-demo",str(payload.recognition_id))
                         if payload.recognition_id is not None else None)
        if local_receipt is not None:
            from .local_meta import ADAPTER_SHA256
            if (local_receipt.get("mode"),local_receipt.get("model"),local_receipt.get("adapter_sha256")) != ("local_meta",LOCAL_MODEL,ADAPTER_SHA256):
                raise HTTPException(422,"invalid_request")
            if payload.recognition_feedback is not None:
                feedback=payload.recognition_feedback
                reference=feedback.original_candidate.model_dump(exclude={"personal_correction"})
                if (feedback.source_mode != "local_meta" or feedback.image_sha256 != local_receipt["image_sha256"]
                        or reference not in local_receipt["candidates"]):
                    raise HTTPException(422,"invalid_request")
            provenance=["user_confirmed_photo","recognition-v1:local_meta",LOCAL_MODEL,ADAPTER_SHA256]
        elif payload.recognition_id is not None:
            try:
                if payload.recognition_feedback is not None and payload.recognition_feedback.source_mode != "meta_live":
                    raise BudgetDenied("Correction source differs from hosted receipt")
                receipt = request.app.state.meta_ledger.receipt(str(payload.recognition_id))
                if payload.recognition_feedback is not None:
                    from .meta_observations import read_observation
                    observation=read_observation(request.app.state.meta_ledger.path,str(payload.recognition_id))
                    if (observation["outcome"]!="success" or observation["purpose"]!="camera"
                            or observation["input_sha256"]!=payload.recognition_feedback.image_sha256):
                        raise BudgetDenied("Correction photo differs from the verified receipt")
            except BudgetDenied:
                raise HTTPException(422, "invalid_request") from None
            provenance = ["user_confirmed_photo", "recognition-v1:meta_live", receipt["model"], receipt["account_id"], receipt["provider_id"]]
        if payload.consumption_assumption is not None:
            provenance.append("user_assumed_"+payload.consumption_assumption)
        record = {**{k:v for k,v in canonical.items() if k!="recognition_feedback"}, "id": str(uuid4()), "revision": 1,
                  "provenance": provenance,
                  "nutrition": lookup(payload.product_id, payload.category)}
        record["contribution"] = jsonable_encoder(asdict(calculate_contribution(to_engine(record))))
        feedback=(payload.recognition_feedback.storage_value(payload.category,payload.container_ml,utc_string(datetime.now(dt_timezone.utc)),beverage_type=payload.beverage_type)
                  if payload.recognition_feedback is not None else None)
        if feedback is not None:
            feedback["photo_receipt_verified"]=payload.recognition_id is not None
        stored, created = request.app.state.repository.create("local-demo", str(idempotency_key), fingerprint, record,feedback=feedback)
        return JSONResponse(stored, status_code=201 if created else 200)

    @app.patch("/v1/beverages/{beverage_id}")
    def update_beverage(beverage_id: UUID, payload: UpdateBeverageRequest, request: Request):
        changes = {name: getattr(payload, name) for name in payload.model_fields_set - {"revision"}}
        if "consumed_at" in changes:
            changes["consumed_at"] = utc_string(changes["consumed_at"])

        def corrected(current: dict) -> dict:
            # A photo-confirmed category is tied to its product nutrition; only manual logs rename.
            if "category" in changes and current["source"] != "manual":
                raise ValueError("category of a confirmed recognition is fixed")
            record = {**current, **changes, "revision": current["revision"] + 1}
            if "consumed_ml" in changes and changes["consumed_ml"]!=current["consumed_ml"]:
                record.pop("consumption_assumption",None)
                record["provenance"]=[p for p in record["provenance"] if p not in ("user_assumed_entire_liquid","user_assumed_full_container")]
            if record.get("container_ml") is not None and record["consumed_ml"] > record["container_ml"]:
                raise ValueError("consumed amount exceeds the confirmed container")
            if "user_corrected" not in record["provenance"]:
                record["provenance"] = [*record["provenance"], "user_corrected"]
            record["contribution"] = jsonable_encoder(asdict(calculate_contribution(to_engine(record))))
            return record

        try:
            return request.app.state.repository.update("local-demo", str(beverage_id), payload.revision, corrected)
        except RevisionConflict as conflict:
            current = conflict.current
            # Retrying an applied correction (e.g. after a lost response) replays the result.
            if current["revision"] == payload.revision + 1 and all(current.get(k) == v for k, v in changes.items()):
                return current
            raise
        except ValueError:
            raise HTTPException(422, "invalid_request") from None

    @app.delete("/v1/beverages/{beverage_id}", status_code=204)
    def delete_beverage(beverage_id: UUID, request: Request,
                        revision: Annotated[int | None, Query(ge=1, le=1_000_000)] = None):
        request.app.state.repository.delete("local-demo", str(beverage_id), revision)
        return Response(status_code=204)

    @app.get("/v1/beverages")
    def list_beverages(request: Request, limit: Annotated[int, Query(ge=1, le=200)] = 100,
                       cursor: Annotated[str | None, Query(max_length=512)] = None):
        boundary = cursor_decode(cursor) if cursor is not None else None
        records = request.app.state.repository.list_all("local-demo")
        if boundary is not None:
            records = [r for r in records if (r["consumed_at"], r["id"]) < boundary]
        page = records[:limit]
        return {"items": page, "next_cursor": cursor_encode(page[-1]) if len(records) > limit else None}

    @app.get("/v1/summary")
    def daily_summary(request: Request, date_value: Annotated[str, Query(alias="date", pattern=r"^\d{4}-\d{2}-\d{2}$")],
                      timezone: Annotated[str, Query(min_length=1, max_length=128)]):
        try:
            local_date = date.fromisoformat(date_value)
            ZoneInfo(timezone)
        except (ValueError, ZoneInfoNotFoundError):
            raise HTTPException(422, "invalid_request") from None
        records = request.app.state.repository.list_all("local-demo")
        summary = summarize_day([to_engine(r) for r in records], local_date, timezone)
        goal_ml = (request.app.state.repository.get_settings("local-demo") or {}).get("daily_beverage_goal_ml")
        goal = None if goal_ml is None else {
            "daily_beverage_goal_ml": goal_ml, "basis": "user_confirmed",
            "remaining_ml": max(goal_ml - summary.beverage_total_ml, 0.0),
            "progress_ratio": round(summary.beverage_total_ml / goal_ml, 3)}
        return {**jsonable_encoder(asdict(summary)), "method_version": METHOD_VERSION,
                "forecast_status": "insufficient_data", "goal": goal}

    def settings_view(stored: dict | None) -> dict:
        stored = stored or {}
        return {"version": "settings-v1", "daily_beverage_goal_ml": stored.get("daily_beverage_goal_ml"),
                "goal_basis": "user_confirmed", "updated_at": stored.get("updated_at")}

    @app.get("/v1/export")
    def export_data(request: Request):
        """Everything stored for this owner, for the user to keep. No ledger or provider data."""
        repository = request.app.state.repository
        results_dir = getattr(request.app.state, "wonder_results_dir", None)
        from .wonder_results import saved_trends, saved_workouts, saved_analyses, saved_scores
        corrections, training = repository.export_corrections("local-demo")
        return {"version": "export-v1", "exported_at": utc_string(datetime.now(dt_timezone.utc)),
                "recognition_corrections":corrections,"training_examples":training,
                "local_recognition_receipts":repository.export_local_recognitions("local-demo"),
                "beverages": repository.list_all("local-demo"),
                "settings": settings_view(repository.get_settings("local-demo")),
                "wonder_trends": saved_trends(results_dir) if results_dir else [],
                "wonder_workout_explanations": saved_workouts(results_dir) if results_dir else [],
                "wonder_analysis_explanations": saved_analyses(results_dir) if results_dir else [],
                "wonder_score_explanations": saved_scores(results_dir) if results_dir else []}

    @app.delete("/v1/data")
    def delete_all_data(request: Request, confirm: Annotated[str, Query(max_length=64)] = ""):
        # An explicit phrase guards against an accidental or replayed bulk deletion.
        if confirm != "delete-all-my-data":
            raise HTTPException(422, "invalid_request")
        lock = request.app.state.wonder_lock
        if not lock.acquire(blocking=False):
            return error_response("wonder_busy", 409, request.state.request_id, retryable=True)
        try:
            request.app.state.data_generation += 1
            results_dir = getattr(request.app.state, "wonder_results_dir", None)
            from .wonder_results import delete_trends, delete_workouts, delete_analyses, delete_pending_results, delete_scores
            deleted = request.app.state.repository.delete_all("local-demo")
            if results_dir:
                delete_pending_results(results_dir)
            return {"deleted_beverages": deleted, "settings_cleared": True,
                    "deleted_trend_explanations": delete_trends(results_dir) if results_dir else 0,
                    "deleted_workout_explanations": delete_workouts(results_dir) if results_dir else 0,
                    "deleted_analysis_explanations": delete_analyses(results_dir) if results_dir else 0,
                    "deleted_score_explanations": delete_scores(results_dir) if results_dir else 0}
        finally:
            lock.release()

    @app.get("/v1/settings")
    def get_settings(request: Request):
        return settings_view(request.app.state.repository.get_settings("local-demo"))

    @app.put("/v1/settings")
    def put_settings(payload: SettingsUpdate, request: Request):
        stored = {"daily_beverage_goal_ml": payload.daily_beverage_goal_ml,
                  "updated_at": utc_string(datetime.now(dt_timezone.utc))}
        return settings_view(request.app.state.repository.put_settings("local-demo", stored))

    from .hydration_routes import install_hydration_routes
    install_hydration_routes(app, enabled=hydration_enabled == "true", error_response=error_response)
    from .personal_forecasts import install_forecast_routes
    install_forecast_routes(app, to_engine)
    from .assistant_routes import install_assistant_routes
    install_assistant_routes(app, to_engine)
    from .workout_forecasts import install_workout_forecast_routes
    install_workout_forecast_routes(app)
    from .hydration_context_v2 import install_context_v2_routes
    install_context_v2_routes(app)
    from .wonder_trend_routes import install_wonder_trend_routes
    install_wonder_trend_routes(app, live=wonder_live == "true", error_response=error_response)
    from .wonder_workout_routes import install_wonder_workout_routes
    install_wonder_workout_routes(app, error_response=error_response)  # shares the trend config and lock
    from .hydration_analysis import install_hydration_analysis_routes
    install_hydration_analysis_routes(app, to_engine, error_response=error_response)
    from .wonder_analysis_routes import install_wonder_analysis_routes
    install_wonder_analysis_routes(app, to_engine, enabled=analysis_enabled == "true", error_response=error_response)
    from .personal_runtime_routes import install_personal_runtime_routes
    install_personal_runtime_routes(app, to_engine, enabled=analysis_enabled == "true", error_response=error_response)
    from .wonder_live_routes import install_wonder_live_routes
    install_wonder_live_routes(app, error_response=error_response)
    from .wonder_owner_once_routes import install_owner_once_routes
    install_owner_once_routes(app)  # Recorded synthetic output only; never dispatches.
    from .wonder_readiness_routes import install_wonder_readiness_routes
    install_wonder_readiness_routes(app)  # Owner-authenticated availability; never dispatches.
    from .wonder_score_routes import install_wonder_score_routes
    install_wonder_score_routes(app, enabled=analysis_enabled == "true", error_response=error_response)
    return app
