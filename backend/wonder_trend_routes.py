"""Muse Wonder explanations of the user's own trends (docs/architecture/WONDER_TRENDS_API.md).

GET previews exactly what would be sent and returns any saved explanation.
POST sends it only with the user's consent to that exact payload, through the
account ledger's gates, and never pays twice for the same data.
"""
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import threading
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .meta_accounts import ACCOUNTS, AccountLedger
from .meta_experiments import ExperimentQuote
from .meta_budget import BudgetDenied
from .meta_gateway import GitHubNotifier
from .recognition import RecognitionUnavailable
from .wonder_experiment import WonderExperimentLedger, WonderHydrationGateway, WonderMetaTransport
from .wonder_results import latest_trends, load_trends, save_result, _private_directory
from .wonder_trends import build_facts, preview
from .wonder_personal_owner_policy import (OwnerPersonalAuthority, OwnerPersonalPolicy, OwnerRiskQuote,
                                           readiness_response)
from .wonder_personal_owner_gateway import OwnerPersonalMetaTransport, OwnerPersonalWonderGateway
from .wonder_owner_once import _private_destination

KEY_NAMES = {"georgiosaliba227": "HYDRA_META_GEORGIO_API_KEY", "aminealichaouche": "HYDRA_META_AMINE_API_KEY"}


class TrendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    timezone: str = Field(min_length=1, max_length=128)
    payload_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    consent_to_send: Literal[True]


@dataclass(frozen=True)
class LiveConfig:
    """One explicitly selected account; its key, ledger and quote. No fallback or switching."""
    account: str
    ledger: WonderExperimentLedger | OwnerPersonalAuthority
    quote_path: Path
    key: str
    notification_token: str
    financial_policy: str = "verified"
    owner_policy: OwnerPersonalPolicy | None = None
    results_path: Path | None = None

    @property
    def supports_synthetic(self) -> bool:
        return self.financial_policy == "verified"

    def read_quote(self) -> ExperimentQuote | OwnerRiskQuote:
        if self.financial_policy == "owner_accepted_risk":
            _private_destination(self.quote_path)
            return OwnerRiskQuote.model_validate_json(self.quote_path.read_text())
        return ExperimentQuote.model_validate_json(self.quote_path.read_text())

    def new_gateway(self) -> WonderHydrationGateway | OwnerPersonalWonderGateway:
        if self.financial_policy == "owner_accepted_risk":
            return OwnerPersonalWonderGateway(self.ledger, self.owner_policy, OwnerPersonalMetaTransport(self.key))
        return WonderHydrationGateway(self.ledger, WonderMetaTransport(self.key), GitHubNotifier(self.notification_token))

    def readiness(self) -> dict:
        if self.financial_policy == "owner_accepted_risk":
            try:
                status = self.ledger.readiness(self.owner_policy, self.read_quote())
            except OSError:
                return readiness_response(["storage_unavailable"])
            except ValueError:
                return readiness_response(["owner_policy_invalid"])
            try:
                _private_directory(self.results_path)
            except (AttributeError, TypeError, ValueError, OSError):
                status = readiness_response(status["blocked_reasons"] + ["storage_unavailable"])
            return status
        all_charges = None
        try:
            self.read_quote()
            with self.ledger._transaction(write=False) as db:
                approval = self.ledger._allocation(db)
                self.ledger._evidence(db, approval)
                all_charges = True
                self.ledger.authority.verify_prior_finalities(db)
                if db.execute("SELECT 1 FROM live_notices WHERE delivered_at IS NULL").fetchone():
                    raise BudgetDenied("Pending developer notice")
            reasons = []
        except (BudgetDenied, OSError, ValueError):
            reasons = ["verified_financial_checks_required"]
        return readiness_response(reasons, account=self.account, policy="verified", all_charges=all_charges)

    @classmethod
    def from_env(cls, env) -> "LiveConfig":
        financial_policy = env.get("HYDRA_WONDER_FINANCIAL_POLICY", "verified")
        if financial_policy not in ("verified", "owner_accepted_risk"):
            raise ValueError("Unsupported Wonder financial policy")
        account = env.get("HYDRA_WONDER_ACCOUNT", "")
        if account not in ACCOUNTS:
            raise ValueError("HYDRA_WONDER_ACCOUNT must name one Meta account")
        ledger, quote = Path(env.get("HYDRA_WONDER_LEDGER", "")), Path(env.get("HYDRA_WONDER_QUOTE", ""))
        if not (ledger.is_absolute() and ledger.is_file() and quote.is_absolute() and quote.is_file()):
            raise ValueError("HYDRA_WONDER_LEDGER and HYDRA_WONDER_QUOTE must be absolute paths to existing files")
        key, token = env.get(KEY_NAMES[account], ""), env.get("HYDRA_GITHUB_NOTIFICATION_TOKEN", "")
        transport = (OwnerPersonalMetaTransport(key) if financial_policy == "owner_accepted_risk"
                     else WonderMetaTransport(key))  # Validation only; no provider request.
        GitHubNotifier(token)
        if financial_policy == "owner_accepted_risk":
            if account != "georgiosaliba227":
                raise ValueError("The owner-risk policy is bound to Georgio only")
            policy_path = _private_destination(Path(env.get("HYDRA_WONDER_OWNER_POLICY_FILE", "")))
            policy = OwnerPersonalPolicy.model_validate_json(policy_path.read_text())
            authority = OwnerPersonalAuthority(AccountLedger(ledger))
            authority.verify_identity(policy, transport.credential_fingerprint)
            _private_destination(quote)
            OwnerRiskQuote.model_validate_json(quote.read_text())
            return cls(account, authority, quote, key, token, financial_policy, policy,
                       Path(env.get("HYDRA_WONDER_RESULTS_DIR", "")))
        authority = WonderExperimentLedger(AccountLedger(ledger))
        try:
            authority.verify_identity(account, transport.credential_fingerprint)
        except BudgetDenied:
            raise ValueError("The key and HYDRA_WONDER_ACCOUNT must match the ledger's allocation and evidence") from None
        return cls(account, authority, quote, key, token)


def install_wonder_trend_routes(app, *, live: bool, error_response) -> None:
    if os.getenv("HYDRA_WONDER_FINANCIAL_POLICY", "verified") not in ("verified", "owner_accepted_risk"):
        raise ValueError("Unsupported Wonder financial policy")
    configured = os.getenv("HYDRA_WONDER_RESULTS_DIR", "")
    results_dir = Path(configured) if configured else None
    if results_dir is not None and not results_dir.is_absolute():
        raise ValueError("HYDRA_WONDER_RESULTS_DIR must be absolute")
    config = LiveConfig.from_env(os.environ) if live else None
    if config is not None and results_dir is None:
        raise ValueError("Live Wonder trends need HYDRA_WONDER_RESULTS_DIR to keep each paid result")
    app.state.wonder_trends_gateway = config.new_gateway if config else None
    app.state.wonder_results_dir = results_dir  # Data export and delete-all include saved trends.
    app.state.wonder_live_config = config
    # One Wonder request in flight per backend, shared by trends and synthetic runs.
    in_flight = app.state.wonder_lock = threading.Lock()

    def facts_for(request: Request, timezone: str) -> dict:
        try:
            today = datetime.now(ZoneInfo(timezone)).date()
        except (ValueError, ZoneInfoNotFoundError):
            raise HTTPException(422, "invalid_request") from None
        repository = request.app.state.repository
        goal = (repository.get_settings("local-demo") or {}).get("daily_beverage_goal_ml")
        try:
            return build_facts(repository.list_all("local-demo"), goal, timezone, today)
        except ValueError:
            raise HTTPException(422, "invalid_request") from None

    def saved(payload_sha256: str | None) -> dict | None:
        try:
            return load_trends(results_dir, payload_sha256) if results_dir and payload_sha256 else None
        except (OSError, ValueError):
            return None

    @app.get("/v1/wonder/trends")
    def trends_preview(request: Request, timezone: Annotated[str, Query(min_length=1, max_length=128)]):
        view = preview(facts_for(request, timezone))
        try:
            latest = latest_trends(results_dir) if results_dir else None
        except (OSError, ValueError):
            latest = None
        return {**view, "live_available": bool(config and config.readiness()["status"] == "ready"),
                "account_id": config.account if config else None, "saved": saved(view["payload_sha256"]),
                "latest": latest}

    @app.post("/v1/wonder/trends")
    def explain_trends(payload: TrendRequest, request: Request):
        request_id = request.scope["state"]["request_id"]
        if not in_flight.acquire(blocking=False):
            return error_response("wonder_busy", 409, request_id, retryable=True)
        try:
            view = preview(facts_for(request, payload.timezone))
            if not view["explainable"]:
                return error_response("trends_insufficient_data", 422, request_id)
            if view["payload_sha256"] != payload.payload_sha256:
                return error_response("trends_preview_stale", 409, request_id, retryable=True)
            if (recorded := saved(payload.payload_sha256)) is not None:
                return {"replayed": True, "saved": True, "result": recorded}
            factory = request.app.state.wonder_trends_gateway
            if factory is None:
                return error_response("wonder_unavailable", 503, request_id)
            if config.financial_policy == "owner_accepted_risk" and config.readiness()["status"] != "ready":
                return error_response("wonder_blocked", 409, request_id)
            gateway = factory()
            try:
                quote = config.read_quote()
                result = gateway.explain_trends(view["facts"], quote,
                                                f"in-app-consent:{request_id}:{payload.payload_sha256}")
            except (RecognitionUnavailable, OSError, ValueError):
                if gateway.last_attempt is None:
                    return error_response("wonder_blocked", 409, request_id)
                response = error_response("wonder_attempt_unresolved", 502, request_id)
                # A billable request may have been sent: name the attempt so a developer can reconcile it.
                return JSONResponse({**json.loads(response.body), "attempt_id": gateway.last_attempt},
                                    status_code=502, headers={k: v for k, v in response.headers.items() if k != "content-length"})
            try:
                save_result(results_dir, result)
                stored = True
            except (OSError, ValueError):
                stored = False  # The settled attempt stays in the ledger; still show what was paid for.
                if hasattr(gateway, "record_save_failure"):
                    try: gateway.record_save_failure()
                    except Exception: pass
            if stored and hasattr(gateway, "record_result_saved"):
                try: gateway.record_result_saved(result)
                except Exception: pass  # Saved replay survives; the missing marker blocks another send.
            return {"replayed": False, "saved": stored, "result": result}
        finally:
            in_flight.release()
