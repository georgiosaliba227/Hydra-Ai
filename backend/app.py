"""Local single-user FastAPI adapter for durable, confirmed beverage accounting."""
import base64
from dataclasses import asdict
from datetime import date, datetime
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
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from ai.hydration import BeverageLog, calculate_contribution, summarize_day
from ai.hydration.models import Composition, METHOD_VERSION
from database.repository import BeverageRepository, IdempotencyConflict, StorageUnavailable
from .recognition import AnalysisRequest, AnalysisResult, MockMetaRecognizer, RecognitionUnavailable
from .nutrition import lookup
from .schemas import CreateBeverageRequest, utc_string

MAX_BODY_BYTES = 16 * 1024


def error_response(code: str, status: int, request_id: str, *, retryable: bool = False) -> JSONResponse:
    messages = {
        "unauthorized": "A valid development session is required.",
        "invalid_request": "The request is invalid.",
        "idempotency_conflict": "This request key was already used for different data.",
        "storage_unavailable": "Storage is temporarily unavailable.",
        "internal_error": "The request could not be completed.",
        "not_found": "The requested resource does not exist.",
        "method_not_allowed": "This method is not supported.",
        "request_too_large": "The request exceeds the size limit.",
        "recognition_unavailable": "Photo analysis is unavailable. Retry or log manually.",
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
        if scope["path"].startswith("/v1"):
            provided = headers.get(b"authorization", b"")
            expected = ("Bearer " + self.token).encode()
            if not hmac.compare_digest(provided, expected):
                await error_response("unauthorized", 401, request_id)(scope, receive, send)
                return
        body_limit = 1_400_000 if scope["path"] == "/v1/recognitions" else MAX_BODY_BYTES
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
    """Create a mock-only app. Configuration errors stop startup, never enable AI."""
    if os.getenv("HYDRA_AI_MODE", "mock") != "mock":
        raise ValueError("Only mock AI mode is permitted in this milestone")
    if os.getenv("META_BILLABLE_REQUESTS_ENABLED", "false").lower() != "false":
        raise ValueError("Billable requests must remain disabled")
    token = api_token if api_token is not None else os.getenv("HYDRA_API_TOKEN", "")
    if not isinstance(token, str) or len(token) < 32 or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError("HYDRA_API_TOKEN must be at least 32 non-whitespace ASCII characters")
    app = FastAPI(title="Hydra AI Local Prototype", version="1.0.0")
    app.state.repository = BeverageRepository(db_path or os.getenv("HYDRA_DATABASE_PATH", "database/hydra.sqlite3"))
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

    @app.exception_handler(StorageUnavailable)
    async def storage_error(request: Request, exc):
        return error_response("storage_unavailable", 503, request.state.request_id, retryable=True)

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc):
        return error_response("internal_error", 500, getattr(request.state, "request_id", str(uuid4())))

    @app.exception_handler(RecognitionUnavailable)
    async def recognition_error(request: Request, exc):
        return error_response("recognition_unavailable", 503, request.state.request_id, retryable=True)

    @app.post("/v1/recognitions")
    def analyze_beverage(payload: AnalysisRequest, request: Request):
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
        return {"status": "ok", "ai_mode": "mock", "billable_requests_enabled": False}

    @app.post("/v1/beverages", status_code=201)
    def create_beverage(payload: CreateBeverageRequest, request: Request,
                        idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")]):
        canonical = payload.model_dump(mode="json", exclude_none=True)
        canonical["consumed_at"] = utc_string(payload.consumed_at)
        fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        record = {**canonical, "id": str(uuid4()), "revision": 1,
                  "provenance": ["user_confirmed_photo", "recognition-v1:mock"] if payload.source == "confirmed_recognition" else ["user_confirmed_manual"],
                  "nutrition": lookup(payload.product_id, payload.category)}
        record["contribution"] = jsonable_encoder(asdict(calculate_contribution(to_engine(record))))
        stored, created = request.app.state.repository.create("local-demo", str(idempotency_key), fingerprint, record)
        return JSONResponse(stored, status_code=201 if created else 200)

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
        return {**jsonable_encoder(asdict(summary)), "method_version": METHOD_VERSION,
                "forecast_status": "insufficient_data"}

    return app
