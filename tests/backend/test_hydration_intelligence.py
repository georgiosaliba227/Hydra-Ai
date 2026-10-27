"""Synthetic hydration API checks; no real Meta calls, keys or account evidence."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.hydration_intelligence import (
    SyntheticContext, HydrationIntelligence, context_fingerprint, hydration_payload,
    EXPLANATIONS, Signal,
)
from backend.meta_accounts import AccountLedger, Evidence, Price, ControlledPermit, FirstPermit, ACCOUNTS
from backend.meta_provider import ProviderReply
from backend.meta_observations import read_observation, result_fingerprint

TOKEN = "synthetic-local-api-session-token-000000000"
AUTH = {"Authorization": "Bearer " + TOKEN}
KEY = "synthetic-amine-key"


def context(**changes):
    return SyntheticContext(synthetic=True, disclosure_consent=True, beverage_total_ml=750.0, **changes)


def request(mode="mock", **changes):
    return {"mode": mode, "context": context(**changes).model_dump()}


@pytest.fixture(autouse=True)
def disabled_network(monkeypatch):
    for name in ("HYDRA_AI_MODE", "META_BILLABLE_REQUESTS_ENABLED", "HYDRA_META_HYDRATION_ENABLED",
                 "HYDRA_META_ACCOUNT", "HYDRA_META_GEORGIO_API_KEY", "HYDRA_META_AMINE_API_KEY",
                 "HYDRA_GITHUB_NOTIFICATION_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    def forbidden(*args, **kwargs):
        pytest.fail("This suite must not contact any external provider")
    monkeypatch.setattr("http.client.HTTPSConnection.request", forbidden)


def test_mock_response_and_context_grounding(tmp_path):
    app = create_app(tmp_path / "data.sqlite3", TOKEN)
    with TestClient(app) as client:
        caps = client.get("/v1/hydration-capabilities", headers=AUTH)
        assert caps.json()["mode"] == "mock" and caps.json()["model"] is None
        response = client.post("/v1/hydration-explanations", headers=AUTH, json=request())
        result = response.json()
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        assert result["mode"] == "mock"
        assert all(result[field] is None for field in ("provider", "model", "account_id", "attempt_id", "prediction"))
        assert result["signals"] == ["review_intake", "composition_missing"]
        assert result["explanations"] == [EXPLANATIONS[Signal(value)] for value in result["signals"]]
        assert "estimated_water_ml" in result["missing_information"]
        richer = client.post("/v1/hydration-explanations", headers=AUTH,
                             json=request(workout_minutes=30, temperature_c=28.0,
                                          creatine_reported=True, intake_pattern="lower_than_recent"))
        assert len(richer.json()["signals"]) == 6
        assert client.get("/health").json()["billable_requests_enabled"] is False
    with sqlite3.connect(app.state.meta_ledger.path) as db:
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='live_attempts'").fetchone()


@pytest.mark.parametrize("path,method", [("/v1/hydration-capabilities", "get"), ("/v1/hydration-explanations", "post")])
def test_hydration_authentication(tmp_path, path, method):
    with TestClient(create_app(tmp_path / "data.sqlite3", TOKEN)) as client:
        response = getattr(client, method)(path)
        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("changes", [
    {"synthetic": False}, {"synthetic": 1}, {"disclosure_consent": False},
    {"disclosure_consent": 1}, {"beverage_total_ml": "750"},
    {"estimated_water_ml": 800.0}, {"temperature_c": 61.0},
    {"humidity_percent": 101.0}, {"heart_rate": 123},
    {"healthkit_records": [{"private": "sensitive-marker"}]},
    {"intake_pattern": "drink_more"}, {"free_text": "sensitive-marker"},
])
def test_invalid_private_context_is_redacted(tmp_path, changes):
    payload = request()
    payload["context"].update(changes)
    with TestClient(create_app(tmp_path / "data.sqlite3", TOKEN)) as client:
        response = client.post("/v1/hydration-explanations", headers=AUTH, json=payload)
        assert response.status_code == 422
        assert "sensitive-marker" not in response.text


def test_mode_and_body_limit_fail_closed(tmp_path):
    with TestClient(create_app(tmp_path / "data.sqlite3", TOKEN)) as client:
        response = client.post("/v1/hydration-explanations", headers=AUTH, json=request("meta_live"))
        assert response.status_code == 503 and response.json()["retryable"] is False
        assert response.json()["code"] == "hydration_unavailable"
        response = client.post("/v1/hydration-explanations", headers=AUTH, content=b"x" * 16385)
        assert response.status_code == 413


@pytest.mark.parametrize("enable,billable", [("true", "false"), ("false", "true"), ("yes", "false")])
def test_inconsistent_configuration_refused(tmp_path, monkeypatch, enable, billable):
    monkeypatch.setenv("HYDRA_META_HYDRATION_ENABLED", enable)
    monkeypatch.setenv("META_BILLABLE_REQUESTS_ENABLED", billable)
    with pytest.raises(ValueError):
        create_app(tmp_path / "data.sqlite3", TOKEN)


def configured_ledger(tmp_path, *, legacy=False):
    path = tmp_path / "authority.sqlite3"
    ledger = AccountLedger(path)
    ledger.initialize_accounts()
    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    ledger.attest_account(Evidence(
        account_id=ACCOUNTS[1], provider_account_reference="synthetic-team-amine",
        key_sha256=hashlib.sha256(KEY.encode()).hexdigest(), gross_micro_usd=0,
        credits_remaining_micro_usd=150_000_000, credits_expire=expires,
        valid_until=expires, reference="synthetic-dashboard",
        billing_verified=True, hackathon_terms_verified=True, exclusive_gateway_key_verified=True,
        provider_limits_verified=True, retention_reviewed=True, all_charge_categories_verified=True,
        extra_charge_bound_micro_usd=0))
    ledger.record_price(Price(version="synthetic-price", valid_until=expires,
                              reviewed_by=ACCOUNTS, reference="synthetic-price-review"))
    permit = dict(account_id=ACCOUNTS[1], image_sha256=context_fingerprint(context()),
                  price_version="synthetic-price", developer_approvals=ACCOUNTS,
                  spending_authority_reference="synthetic-only", account_owner_authorization_reference="synthetic-owner",
                  image_owner_consent_reference="synthetic-context", valid_until=expires)
    if legacy:
        ledger.approve_first_test(FirstPermit(**permit))
    else:
        ledger.approve_controlled_test(ControlledPermit(**permit, purpose="hydration",
                                      policy_version="dual-test-v1", maximum_micro_usd=2_000_000))
    return ledger


class FakeTransport:
    """A synthetic transport cannot establish real inference in this test suite."""
    def __init__(self, key, signals=None, extra=None):
        self.credential_fingerprint = hashlib.sha256(key.encode()).hexdigest()
        self.calls = 0
        self.signals = signals if signals is not None else ["review_intake", "weather_context"]
        self.extra = extra or {}

    def input_bound(self, payload):
        return 1000

    def generate(self, payload, ticket):
        ticket.claim(payload, input_bound=1000, credential_fingerprint=self.credential_fingerprint)
        self.calls += 1
        assert payload == hydration_payload(context())
        return ProviderReply(200, {"id": "resp_synthetic_hydration", "model": "muse-spark-1.3",
            "status": "completed", "error": None, "incomplete_details": None,
            "usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150,
                      "input_tokens_details": {"cached_tokens": 0}},
            "output": [{"type": "message", "role": "assistant", "status": "completed",
                        "content": [{"type": "output_text", "text": json.dumps({"signals": self.signals} | self.extra)}]}]})


def live_app(tmp_path, monkeypatch, *, legacy=False, provider=None, key=KEY):
    ledger = configured_ledger(tmp_path, legacy=legacy)
    monkeypatch.setenv("HYDRA_META_HYDRATION_ENABLED", "true")
    monkeypatch.setenv("META_BILLABLE_REQUESTS_ENABLED", "true")
    monkeypatch.setenv("HYDRA_META_AMINE_API_KEY", key)
    monkeypatch.setenv("HYDRA_GITHUB_NOTIFICATION_TOKEN", "synthetic-github")
    provider = provider or FakeTransport(key)
    monkeypatch.setattr("backend.hydration_routes.HydrationMetaTransport", lambda key: provider)
    app = create_app(ledger.path, TOKEN)
    assert app.state.hydration_service.ledger is app.state.meta_ledger
    assert app.state.hydration_service.account == ACCOUNTS[1]
    assert isinstance(app.state.hydration_service, HydrationIntelligence)
    return app, provider


def test_independent_hydration_mode_settles_one_fake_attempt(tmp_path, monkeypatch):
    app, provider = live_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        assert client.get("/health").json()["ai_mode"] == "mock"
        assert client.get("/health").json()["billable_requests_enabled"] is True
        assert client.get("/v1/recognition-capabilities", headers=AUTH).json()["mode"] == "mock"
        response = client.post("/v1/hydration-explanations", headers=AUTH, json=request("meta_live"))
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "meta_live" and data["provider"] == "Meta"
        assert data["model"] == "muse-spark-1.3" and data["account_id"] == ACCOUNTS[1]
        assert data["signals"] == ["review_intake"]  # Missing weather cannot become a model claim.
        assert data["discarded_signal_count"] == 1  # Preserve quality evidence of repair.
        assert data["context"] == context().model_dump()
        assert data["prediction"] is None
        observation = read_observation(app.state.meta_ledger.path, data["attempt_id"])
        assert observation["result_sha256"] == result_fingerprint(data)
        assert observation["transport_kind"] == "injected_test_transport"
        assert observation["purpose"] == "hydration" and observation["api_latency_ms"] >= 0
        assert observation["usage_cost_micro_usd"] == 338
        assert observation["provider_http_status"] == 200
        again = client.post("/v1/hydration-explanations", headers=AUTH, json=request("meta_live"))
        assert again.status_code == 503 and again.json()["retryable"] is False
        assert provider.calls == 1


@pytest.mark.parametrize("legacy,key", [(True, KEY), (False, "wrong-synthetic-key")])
def test_legacy_camera_policy_or_wrong_key_never_sends(tmp_path, monkeypatch, legacy, key):
    app, provider = live_app(tmp_path, monkeypatch, legacy=legacy, key=key)
    with TestClient(app) as client:
        response = client.post("/v1/hydration-explanations", headers=AUTH, json=request("meta_live"))
        assert response.status_code == 503 and provider.calls == 0


@pytest.mark.parametrize("signals,extra", [(["diagnosis"], {}), (["review_intake"], {"target_ml": 2500}), (["weather_context"], {})])
def test_invalid_or_ungrounded_output_freezes_after_usage(tmp_path, monkeypatch, signals, extra):
    provider = FakeTransport(KEY, signals, extra)
    app, provider = live_app(tmp_path, monkeypatch, provider=provider)
    with TestClient(app) as client:
        response = client.post("/v1/hydration-explanations", headers=AUTH, json=request("meta_live"))
        assert response.status_code == 503 and response.json()["retryable"] is False
        assert "target_ml" not in response.text and "diagnosis" not in response.text
    with sqlite3.connect(app.state.meta_ledger.path) as db:
        assert db.execute("SELECT frozen FROM live_accounts").fetchone()[0] == 1
        assert db.execute("SELECT actual FROM live_attempts").fetchone()[0] == 338
    assert provider.calls == 1
    with sqlite3.connect(app.state.meta_ledger.path) as db:
        attempt = db.execute("SELECT id FROM live_attempts").fetchone()[0]
    observation = read_observation(app.state.meta_ledger.path, attempt)
    assert observation["outcome"] == "output_rejected" and observation["result_sha256"] is None


def test_injected_output_cannot_mutate_context_or_prose(tmp_path):
    app = create_app(tmp_path / "data.sqlite3", TOKEN)
    delegate = app.state.hydration_service
    class InvalidService:
        def explain(self, value):
            result = delegate.explain(value)
            result["explanations"] = ["Drink 2000 mL now"]
            return result
    app.state.hydration_service = InvalidService()
    with TestClient(app) as client:
        response = client.post("/v1/hydration-explanations", headers=AUTH, json=request())
        assert response.status_code == 503 and "2000" not in response.text
