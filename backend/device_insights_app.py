"""Owner-only, nonbillable device features without database, ledger or provider state.

The token is supplied explicitly by the owner launcher. Ambient live, storage,
credential and recorded-result configuration is never read by this factory.
There is deliberately no module-level app or fallback to the full backend.
"""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .app import RequestGuard, error_response
from .assistant_routes import install_assistant_routes
from .device_insights import install_device_insights_routes
from .hydration_context_v2 import install_context_v2_routes


def create_device_insights_app(api_token: str) -> FastAPI:
    # Match the authoritative backend's development-token validation exactly,
    # without calling create_app or reading its environment-selected storage.
    if (not isinstance(api_token, str) or len(api_token) < 32 or not api_token.isascii()
            or any(c.isspace() for c in api_token)):
        raise ValueError("HYDRA_API_TOKEN must be at least 32 non-whitespace ASCII characters")
    app = FastAPI(title="Hydra AI Device Features", version="1.0.0")
    app.add_middleware(RequestGuard, token=api_token)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc):
        return error_response("invalid_request", 422, request.state.request_id)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc):
        code = {404: "not_found", 405: "method_not_allowed", 401: "unauthorized"}.get(exc.status_code, "invalid_request")
        return error_response(code, exc.status_code, request.state.request_id)

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc):
        return error_response("internal_error", 500, request.state.request_id)

    @app.get("/health")
    def health():
        return {"status": "ok", "ai_mode": "features_only", "features_only": True,
                "billable_requests_enabled": False, "provider_dispatch": False, "storage": "none"}

    install_device_insights_routes(app)
    install_assistant_routes(app, None, allow_intake_context=False, allow_recorded=False)
    install_context_v2_routes(app, allow_recorded=False)
    return app
