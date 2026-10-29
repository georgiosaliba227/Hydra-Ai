"""Live synthetic Wonder for the backend owner (standing approval). Fake transports only; never network."""
import hashlib
import json
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.meta_accounts import ACCOUNTS, AccountLedger
from backend.meta_budget import BudgetDenied
from backend.wonder_experiment import LIVE_SCHEMA, WonderExperimentLedger, WonderHydrationGateway
from backend.wonder_hydration import payload_sha256
from backend.wonder_trends import build_facts, trends_payload
from test_guarded_meta import FakeNotifier, evidence
from test_meta_experiments import approval, quote
from test_wonder_assistant import topics_reply
from test_wonder_experiment import WONDER, FakeWonderTransport, attempt_rows, disabled_network, frozen, selection_reply

__all__ = ["disabled_network"]  # autouse network block from the shared fixtures
OWNER = "o" * 40
OTHER_TOKEN = "former-developer-token-0123456789abcdef"
OWNER_AUTH = {"Authorization": f"Bearer {OWNER}"}
OTHER_AUTH = {"Authorization": f"Bearer {OTHER_TOKEN}"}
LIVE = {"kind": "scenario", "id": "complete", "confirm_billable": True}


@pytest.fixture
def env(monkeypatch, tmp_path):
    for name in ("HYDRA_AI_MODE", "META_BILLABLE_REQUESTS_ENABLED", "HYDRA_META_HYDRATION_ENABLED", "HYDRA_WONDER_LIVE",
                 "HYDRA_WONDER_ACCOUNT", "HYDRA_WONDER_LEDGER", "HYDRA_WONDER_QUOTE", "HYDRA_WONDER_RESULTS_DIR",
                 "HYDRA_META_GEORGIO_API_KEY", "HYDRA_META_AMINE_API_KEY", "HYDRA_GITHUB_NOTIFICATION_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("HYDRA_DEVELOPER_CREDENTIALS", raising=False)
    return monkeypatch, None


def georgio_live(env, tmp_path, *, synthetic=True):
    monkeypatch, _ = env
    authority = AccountLedger(tmp_path / "georgio-ledger.sqlite3")
    authority.initialize_accounts()
    authority.attest_account(evidence(ACCOUNTS[0]))
    with authority.transaction() as db:
        for sql in LIVE_SCHEMA:
            db.execute(sql)
    ledger = WonderExperimentLedger(authority)
    ledger.record_approval(approval(synthetic_dispatch_reference="synthetic-standing-wonder" if synthetic else None))
    quote_file = tmp_path / "quote.json"
    quote_file.write_text(quote(WONDER).model_dump_json())
    results = tmp_path / "results"
    results.mkdir(mode=0o700)
    for name, value in {"META_BILLABLE_REQUESTS_ENABLED": "true", "HYDRA_WONDER_LIVE": "true",
                        "HYDRA_WONDER_ACCOUNT": ACCOUNTS[0], "HYDRA_WONDER_LEDGER": str(authority.path),
                        "HYDRA_WONDER_QUOTE": str(quote_file), "HYDRA_WONDER_RESULTS_DIR": str(results),
                        "HYDRA_META_GEORGIO_API_KEY": "synthetic-key",
                        "HYDRA_GITHUB_NOTIFICATION_TOKEN": "synthetic-notify-token"}.items():
        monkeypatch.setenv(name, value)
    return authority, ledger


def fake_live(app, ledger, transport):
    app.state.wonder_trends_gateway = lambda: WonderHydrationGateway(ledger, transport, FakeNotifier())


def cases(authority):
    with authority.transaction() as db:
        return [json.loads(raw) for (raw,) in db.execute("SELECT approval FROM experiment_cases")]


# Only the owner token works; the withdrawn developer-credential file is ignored.

def test_no_other_token_is_accepted_even_with_a_credentials_file(tmp_path, env):
    monkeypatch, _ = env
    credentials = tmp_path / "developers.json"
    credentials.write_text(json.dumps({"version": "developer-credentials-v1", "developers": [
        {"id": "aminealichaouche", "token_sha256": hashlib.sha256(OTHER_TOKEN.encode()).hexdigest(),
         "scopes": ["wonder"], "revoked": False}]}))
    os.chmod(credentials, 0o600)
    monkeypatch.setenv("HYDRA_DEVELOPER_CREDENTIALS", str(credentials))
    with TestClient(create_app(tmp_path / "data.sqlite3", OWNER)) as client:
        for path in ("/v1/wonder/live", "/v1/assistant/questions"):
            assert client.get(path, headers=OTHER_AUTH).status_code == 401
            assert client.get(path, headers=OWNER_AUTH).status_code == 200


# Standing synthetic approval on Georgio's $30 allocation.

def test_the_owner_runs_a_synthetic_scenario_once_on_the_allocation(tmp_path, env):
    authority, ledger = georgio_live(env, tmp_path)
    app = create_app(tmp_path / "data.sqlite3", OWNER)
    with TestClient(app) as client:
        transport = FakeWonderTransport(selection_reply())
        fake_live(app, ledger, transport)
        first = client.post("/v1/wonder/live", json=LIVE, headers=OWNER_AUTH).json()
        assert (first["replayed"], first["saved"], transport.calls) == (False, True, 1)
        assert first["result"]["provenance"]["account_id"] == ACCOUNTS[0]
        [case] = cases(authority)
        assert case["input_approval_reference"].startswith("owner:")
        assert case["live_dispatch_reference"] == "synthetic-standing-wonder"
        again = client.post("/v1/wonder/live", json=LIVE, headers=OWNER_AUTH).json()
        assert (again["replayed"], again["result"], transport.calls) == (True, first["result"], 1)
        status = client.get("/v1/wonder/live", headers=OWNER_AUTH).json()
        assert status["account_id"] == ACCOUNTS[0] and status["allocation"]["hard_limit_micro_usd"] == 30_000_000
        assert status["allocation"]["remaining_micro_usd"] < 30_000_000
        assert status["allocation"]["aggregate_exposure_micro_usd"] > 0
        assert [i["recorded"] for i in status["items"] if i["id"] == "complete"] == [True]
        # The app's recorded mode now replays it without another request.
        replay = client.post("/v2/hydration-context-comparison", json={"mode": "recorded", "scenario": "complete",
                                                                       "candidate_model": WONDER}, headers=OWNER_AUTH)
        assert replay.status_code == 200 and transport.calls == 1


def test_a_second_request_waits_for_the_first_invoice(tmp_path, env):
    authority, ledger = georgio_live(env, tmp_path)
    app = create_app(tmp_path / "data.sqlite3", OWNER)
    with TestClient(app) as client:
        transport = FakeWonderTransport(selection_reply())
        fake_live(app, ledger, transport)
        client.post("/v1/wonder/live", json=LIVE, headers=OWNER_AUTH)
        second = client.post("/v1/wonder/live", json={"kind": "question", "id": "hot_weather", "confirm_billable": True},
                             headers=OWNER_AUTH)
        assert second.status_code == 409 and second.json()["code"] == "wonder_blocked" and transport.calls == 1


def test_suggested_questions_use_the_same_standing_approval(tmp_path, env):
    authority, ledger = georgio_live(env, tmp_path)
    app = create_app(tmp_path / "data.sqlite3", OWNER)
    with TestClient(app) as client:
        transport = FakeWonderTransport(topics_reply(["weather", "exercise_sweat"]))
        fake_live(app, ledger, transport)
        body = client.post("/v1/wonder/live", json={"kind": "question", "id": "hot_weather", "confirm_billable": True},
                           headers=OWNER_AUTH).json()
        assert body["result"]["topics"] == ["exercise_sweat", "weather"] and transport.calls == 1
        recorded = client.post("/v1/assistant", json={"question_id": "hot_weather", "source": "recorded_wonder"},
                               headers=OWNER_AUTH)
        assert recorded.status_code == 200 and recorded.json() == body["result"]


def test_without_the_standing_approval_nothing_is_sent(tmp_path, env):
    authority, ledger = georgio_live(env, tmp_path, synthetic=False)
    app = create_app(tmp_path / "data.sqlite3", OWNER)
    with TestClient(app) as client:
        transport = FakeWonderTransport(selection_reply())
        fake_live(app, ledger, transport)
        response = client.post("/v1/wonder/live", json=LIVE, headers=OWNER_AUTH)
        assert response.status_code == 409 and transport.calls == 0 and attempt_rows(authority) == []


@pytest.mark.parametrize("body", [{"kind": "scenario", "id": "made_up", "confirm_billable": True},
                                  {"kind": "question", "id": "free text", "confirm_billable": True}])
def test_only_hydras_fixed_payloads_can_run(tmp_path, env, body):
    _, ledger = georgio_live(env, tmp_path)
    app = create_app(tmp_path / "data.sqlite3", OWNER)
    with TestClient(app) as client:
        transport = FakeWonderTransport()
        fake_live(app, ledger, transport)
        assert client.post("/v1/wonder/live", json=body, headers=OWNER_AUTH).status_code == 404
        assert client.post("/v1/wonder/live", json=LIVE | {"confirm_billable": False}, headers=OWNER_AUTH).status_code == 422
        assert transport.calls == 0


def test_the_standing_synthetic_approval_never_covers_personal_payloads(tmp_path, env):
    _, ledger = georgio_live(env, tmp_path)
    from datetime import date
    facts = build_facts([{"consumed_at": "2026-10-28T12:00:00+00:00", "consumed_ml": 500.0, "category": "water"}],
                        None, "UTC", date(2026, 10, 28))
    with pytest.raises(BudgetDenied):
        ledger.register_synthetic_case(payload_sha256(trends_payload(facts)), "owner:x")


def test_rejected_synthetic_output_is_recorded_without_freezing(tmp_path, env):
    authority, ledger = georgio_live(env, tmp_path)
    app = create_app(tmp_path / "data.sqlite3", OWNER)
    with TestClient(app) as client:
        fake_live(app, ledger, FakeWonderTransport(selection_reply(text="not json")))
        response = client.post("/v1/wonder/live", json=LIVE, headers=OWNER_AUTH)
        assert response.status_code == 502 and response.json()["attempt_id"]
        [(_, state, _, actual, _)] = attempt_rows(authority)
        assert state == "settled" and actual > 0 and not frozen(authority)


def test_every_standing_request_is_audited(tmp_path, env):
    authority, ledger = georgio_live(env, tmp_path)
    digest = payload_sha256(__import__("backend.wonder_hydration", fromlist=["x"]).wonder_payload("complete"))
    first = ledger.register_synthetic_case(digest, "owner:req-1")
    assert ledger.register_synthetic_case(digest, "owner:req-2") == first  # unsent case reused
    with authority.transaction() as db:
        asked = [r for (r,) in db.execute("SELECT reference FROM live_events WHERE kind='experiment_case_requested'")]
    assert asked == [first.case_id + ":owner:req-1", first.case_id + ":owner:req-2"]
