"""Authenticated synthetic hydration API; shares the existing financial gateway."""
import os
from typing import Literal
from uuid import UUID

from fastapi import Request
from pydantic import BaseModel, ConfigDict

from .hydration_intelligence import (
    HydrationIntelligence, HydrationMetaTransport, MockHydrationIntelligence,
    Signal, SyntheticContext, explanation_result,
)
from .meta_accounts import ACCOUNTS
from .meta_gateway import GitHubNotifier
from .recognition import MODEL, RecognitionUnavailable


class HydrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mode: Literal["mock", "meta_live"]
    context: SyntheticContext


def install_hydration_routes(app, *, enabled: bool, error_response) -> None:
    app.state.hydration_mode = "meta_live" if enabled else "mock"
    if enabled:
        # Independent feature/account selection, but never an independent ledger.
        transport = HydrationMetaTransport(os.getenv("HYDRA_META_AMINE_API_KEY", ""))
        notifier = GitHubNotifier(os.getenv("HYDRA_GITHUB_NOTIFICATION_TOKEN", ""))
        app.state.meta_ledger.project_view()
        app.state.hydration_service = HydrationIntelligence(
            app.state.meta_ledger, ACCOUNTS[1], transport, notifier)
    else:
        app.state.hydration_service = MockHydrationIntelligence()

    @app.get("/v1/hydration-capabilities")
    def capabilities():
        return {"version": "hydration-explanation-v1", "mode": app.state.hydration_mode,
                "provider": "Meta" if enabled else None, "model": MODEL if enabled else None,
                "synthetic_only": True, "dispatch_requires_account_permit_and_verified_bound": True,
                "model_selects_signals": True, "explanation_text_source": "reviewed_templates"}

    @app.post("/v1/hydration-explanations")
    def explain(payload: HydrationRequest, request: Request):
        try:
            if payload.mode != app.state.hydration_mode:
                raise RecognitionUnavailable()
            result = app.state.hydration_service.explain(payload.context)
            attempt = result["attempt_id"]
            if payload.mode == "meta_live":
                if not isinstance(attempt, str) or str(UUID(attempt)) != attempt:
                    raise RecognitionUnavailable()
            elif attempt is not None:
                raise RecognitionUnavailable()
            # Validate even an injected adapter result. No unreviewed prose, extra
            # health claims or mutated input values cross the HTTP boundary.
            signals = [Signal(value) for value in result["signals"]]
            expected = explanation_result(payload.context, signals, attempt_id=attempt)
            discarded = result["discarded_signal_count"]
            if type(discarded) is not int or not 0 <= discarded <= len(Signal) - len(signals):
                raise RecognitionUnavailable()
            if payload.mode == "mock" and discarded != 0:
                raise RecognitionUnavailable()
            expected["discarded_signal_count"] = discarded
            if result != expected:
                raise RecognitionUnavailable()
            return result
        except Exception:
            return error_response("hydration_unavailable", 503, request.state.request_id, retryable=False)
