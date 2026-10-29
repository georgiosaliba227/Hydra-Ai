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
from .recognition import AnalysisRequest, AnalysisResult, MockMetaRecognizer, RecognitionUnavailable
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
        if scope["path"].startswith(("/v1", "/v2")):
            provided = headers.get(b"authorization", b"")
            expected = ("Bearer " + self.token).encode()
            if not hmac.compare_digest(provided, expected):
                await error_response("unauthorized", 401, request_id)(scope, receive, send)
                return
        if scope["path"] == "/v1/recognitions":
            body_limit = 1_400_000
        elif scope["path"] in ("/v1/workout-forecasts", "/v2/workout-forecasts"):
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
    if mode not in ("mock", "guarded_meta") or billable not in ("false", "true") or hydration_enabled not in ("false", "true"):
        raise ValueError("Unsupported AI configuration")
    live_feature = mode == "guarded_meta" or hydration_enabled == "true"
    if (billable == "true") != live_feature:
        raise ValueError("Mode and billable gate conflict")
    token = api_token if api_token is not None else os.getenv("HYDRA_API_TOKEN", "")
    if not isinstance(token, str) or len(token) < 32 or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError("HYDRA_API_TOKEN must be at least 32 non-whitespace ASCII characters")
    app = FastAPI(title="Hydra AI Local Prototype", version="1.0.0")
    app.state.repository = BeverageRepository(db_path or os.getenv("HYDRA_DATABASE_PATH", "database/hydra.sqlite3"))
    app.state.recognition_mode = "mock" if mode == "mock" else "meta_live"
    app.state.meta_ledger = AccountLedger(db_path or os.getenv("HYDRA_DATABASE_PATH", "database/hydra.sqlite3"))
    if mode == "guarded_meta":
        account = os.getenv("HYDRA_META_ACCOUNT", "")
        if account not in ACCOUNTS:
            raise ValueError("Select one explicitly authorized Meta account")
        key_name = "HYDRA_META_GEORGIO_API_KEY" if account == "georgiosaliba227" else "HYDRA_META_AMINE_API_KEY"
        transport = OfficialMetaTransport(os.getenv(key_name, ""))
        notifier = GitHubNotifier(os.getenv("HYDRA_GITHUB_NOTIFICATION_TOKEN", ""))
        # Existing evidence is mandatory; do not create a zero baseline at startup.
        app.state.meta_ledger.project_view()
        app.state.recognizer = GuardedMetaGateway(app.state.meta_ledger, account, transport, notifier)
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
                "provider": "Meta" if mode == "guarded_meta" else None,
                "model": "muse-spark-1.3", "dispatch_requires_account_permit_and_verified_bound": True,
                "privacy": "Meta may retain content under its service, safety and legal terms; no zero-retention claim."}

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
        # Validate even injected adapter output, then enrich only from the catalogue.
        try:
            result = AnalysisResult.model_validate(request.app.state.recognizer.analyze(payload)).model_dump()
            for candidate in result["candidates"]:
                candidate["nutrition"] = lookup(candidate["product_id"], candidate["identity"])
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
        provenance = ["user_confirmed_manual"] if payload.source == "manual" else ["user_confirmed_photo", "recognition-v1:mock"]
        if payload.recognition_id is not None:
            try:
                receipt = request.app.state.meta_ledger.receipt(str(payload.recognition_id))
            except BudgetDenied:
                raise HTTPException(422, "invalid_request") from None
            provenance = ["user_confirmed_photo", "recognition-v1:meta_live", receipt["model"], receipt["account_id"], receipt["provider_id"]]
        record = {**canonical, "id": str(uuid4()), "revision": 1,
                  "provenance": provenance,
                  "nutrition": lookup(payload.product_id, payload.category)}
        record["contribution"] = jsonable_encoder(asdict(calculate_contribution(to_engine(record))))
        stored, created = request.app.state.repository.create("local-demo", str(idempotency_key), fingerprint, record)
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
        return {"version": "export-v1", "exported_at": utc_string(datetime.now(dt_timezone.utc)),
                "beverages": repository.list_all("local-demo"),
                "settings": settings_view(repository.get_settings("local-demo"))}

    @app.delete("/v1/data")
    def delete_all_data(request: Request, confirm: Annotated[str, Query(max_length=64)] = ""):
        # An explicit phrase guards against an accidental or replayed bulk deletion.
        if confirm != "delete-all-my-data":
            raise HTTPException(422, "invalid_request")
        return {"deleted_beverages": request.app.state.repository.delete_all("local-demo"), "settings_cleared": True}

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
    return app
