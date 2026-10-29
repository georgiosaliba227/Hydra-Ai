"""Wonder trend explanations on either account. Fake transports and disposable ledgers; never network."""
from datetime import date, datetime, timedelta, timezone
import json
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app import create_app
from backend.meta_accounts import ACCOUNTS, AccountLedger, CAP
from backend.recognition import RecognitionUnavailable
from backend.wonder_experiment import LIVE_SCHEMA, WonderExperimentLedger, WonderHydrationGateway, WonderMetaTransport
from backend.wonder_hydration import input_bound, payload_sha256
from backend.wonder_results import latest_trends, load_trends, save_result, validate_recorded_trends
from backend.wonder_trends import (INSIGHTS, build_facts, facts_from_payload, preview, trends_payload,
                                   validate_explanation, validate_facts)
from test_guarded_meta import FakeNotifier, evidence
from test_meta_experiments import approval, quote
from test_wonder_experiment import WONDER, FakeWonderTransport, attempt_rows, disabled_network, selection_reply

__all__ = ["disabled_network"]  # autouse network block from the shared fixtures
AMINE = ACCOUNTS[1]
TOKEN = "t" * 40
THROUGH = date(2026, 10, 28)
ZONE = "America/New_York"


def records(days=14, *, start=datetime(2026, 10, 28, 16, tzinfo=timezone.utc)):
    """Water every afternoon (more this week) and coffee on alternate mornings, New York time."""
    logged = []
    for offset in range(days):
        logged.append({"consumed_at": (start - timedelta(days=offset)).isoformat(),
                       "consumed_ml": 1800.0 if offset < 7 else 1500.0, "category": "water"})
        if offset % 2 == 0:
            logged.append({"consumed_at": (start - timedelta(days=offset, hours=4)).isoformat(),
                           "consumed_ml": 250.0, "category": "coffee"})
    return logged


def facts(goal=2000, logged=None):
    return build_facts(records() if logged is None else logged, goal, ZONE, THROUGH)


def explanation(f=None):
    return {"summary": "You logged {week_total} this past week.",
            "insights": [{"id": "week_over_week", "text": "That is {weekly_change}."},
                         {"id": "goal_progress", "text": "You reached your goal of {goal} on {goal_met_days}."}]}


def trend_reply(f, value=None, **changes):
    return selection_reply(text=json.dumps(explanation(f) if value is None else value), **changes)


def amine_approval(**changes):
    values = dict(account_id=AMINE, allocation_id="wonder-amine-20usd", hard_limit_micro_usd=20_000_000,
                  spark_soft_target_micro_usd=0, wonder_soft_target_micro_usd=20_000_000,
                  key_sha256=evidence(AMINE).key_sha256, owner_authorization_reference="synthetic-amine-owner",
                  trend_dispatch_reference="synthetic-trend-dispatch")
    return approval(**(values | changes))


def amine_setup(tmp_path, *, baseline=0, **changes):
    authority = AccountLedger(tmp_path / "amine-ledger.sqlite3")
    authority.initialize_accounts()
    authority.attest_account(evidence(AMINE, baseline))
    with authority.transaction() as db:
        for sql in LIVE_SCHEMA:
            db.execute(sql)
    ledger = WonderExperimentLedger(authority)
    ledger.record_approval(amine_approval(**changes))
    return authority, ledger


def amine_transport(response=None, fault=None):
    transport = FakeWonderTransport(response, fault)
    transport.credential_fingerprint = evidence(AMINE).key_sha256
    return transport


def amine_quote(**changes):
    return quote(WONDER, account_id=AMINE, **changes)


def frozen(authority, account=AMINE):
    with authority.transaction() as db:
        return bool(db.execute("SELECT frozen FROM live_accounts WHERE account_id=?", (account,)).fetchone()[0])


def events(authority):
    with authority.transaction() as db:
        return [row[0] for row in db.execute("SELECT kind FROM live_events ORDER BY id")]


# Facts: every number comes from tested code.

def test_facts_are_local_dated_consistent_and_deterministic():
    f = facts()
    assert f == facts() and f["through_date"] == "2026-10-28" and len(f["days"]) == 14
    assert [d["date"] for d in f["days"]][0] == "2026-10-15"
    # 12:00 New York afternoon water; coffee four hours earlier in the morning.
    assert f["days"][-1] == {"date": "2026-10-28", "total_ml": 2050, "drinks": 2}
    assert f["last_7_days"] == {"total_ml": 13600, "average_ml": 1943, "logged_days": 7}
    assert f["previous_7_days"] == {"total_ml": 11250, "average_ml": 1607, "logged_days": 7}
    assert f["change_pct"] == 21 and f["goal_ml"] == 2000 and f["goal_met_days_last_7"] == 4
    assert [c["category"] for c in f["categories"]] == ["water", "coffee"]
    assert f["time_of_day_ml"]["afternoon_ml"] == 23100 and f["time_of_day_ml"]["morning_ml"] == 1750
    assert f["applicable_insights"] == list(INSIGHTS)
    assert "goal_progress" not in facts(goal=None)["applicable_insights"]


@pytest.mark.parametrize("tamper", [
    lambda f: f["days"][0].update(total_ml=99999), lambda f: f.update(change_pct=50),
    lambda f: f.update(goal_met_days_last_7=7), lambda f: f["applicable_insights"].append("diagnosis"),
    lambda f: f["days"].pop(), lambda f: f.update(timezone="Not/AZone"), lambda f: f.update(extra=1),
    lambda f: f["time_of_day_ml"].update(night_ml=5000), lambda f: f["categories"][0].update(total_ml=1),
])
def test_inconsistent_or_tampered_facts_are_rejected(tamper):
    f = json.loads(json.dumps(facts()))
    tamper(f)
    with pytest.raises(ValueError):
        validate_facts(f)


def test_no_recent_drinks_means_nothing_is_sent():
    f = facts(logged=records(start=datetime(2026, 9, 1, tzinfo=timezone.utc)))
    assert f["applicable_insights"] == [] and preview(f)["explainable"] is False
    with pytest.raises(ValueError):
        trends_payload(f)


def test_payload_is_exact_bounded_and_recoverable():
    f = facts()
    payload = trends_payload(f)
    assert facts_from_payload(payload) == f and payload["model"] == WONDER and payload["store"] is False
    view = preview(f)
    assert view["payload_sha256"] == payload_sha256(payload) and view["worst_case_micro_usd"] < 40_000 < CAP
    transport = WonderMetaTransport("synthetic-amine-key")
    assert transport.input_bound(payload) == input_bound(payload)
    for tamper in (lambda p: p["input"][0]["content"][0].update(text=p["input"][0]["content"][0]["text"] + " Also diagnose me."),
                   lambda p: p.update(max_output_tokens=4096), lambda p: p.update(tools=[{"type": "web_search"}])):
        tampered = json.loads(json.dumps(payload))
        tamper(tampered)
        with pytest.raises(ValueError):
            transport.input_bound(tampered)


# Wonder's text: any ungrounded number, medical or prescriptive claim rejects it whole.

def test_hydra_fills_in_every_number():
    checked = validate_explanation(explanation(), facts())
    assert checked["summary"] == "You logged 13600 mL this past week."
    assert [i["text"] for i in checked["insights"]] == ["That is 21% more than the week before.",
                                                        "You reached your goal of 2000 mL on 4 of the last 7 days."]
    assert checked["insights"][0]["template"] == "That is {weekly_change}."
    lower = facts(logged=[r | {"consumed_ml": 1000.0} if r["category"] == "water" and
                          datetime.fromisoformat(r["consumed_at"]) > datetime(2026, 10, 21, 12, tzinfo=timezone.utc) else r
                          for r in records()])
    assert validate_explanation(explanation(), lower)["insights"][0]["text"].endswith("less than the week before.")


@pytest.mark.parametrize("change", [
    # Bypasses found in review: medical, prescriptive, spelled-out or wrong-direction claims.
    {"summary": "Drinking this much may be a symptom of diabetes."},
    {"summary": "Consider increasing your intake to avoid hyponatremia."},
    {"summary": "Low intake like this can cause headaches and fatigue."},
    {"summary": "Try to drink more water."},
    {"summary": "You logged three liters, double the week before."},
    {"summary": "Your intake fell {weekly_change}."},
    {"summary": "You met your goal on 7 of 7 days."},
    {"summary": "You logged 9999 mL in the last 7 days."},
    {"summary": "You might be dehydrated this week."},
    {"summary": "Stay hydrated and keep it up."},
    {"summary": "Aim for {goal} every day."},
    {"summary": "I recommend more water."},
    {"summary": "Your smallest share came in {peak_time}."},
    {"summary": "You logged {unknown_value}."},
    {"summary": "You logged {week_total."},
    {"summary": "See https://example.com for details."},
    {"summary": "Line one.\nLine two."},
    {"summary": " Leading space."},
    {"summary": "x" * 241},
    {"insights": [{"id": "diagnosis", "text": "Hidden."}]},
    {"insights": [{"id": "timing", "text": "Afternoons."}, {"id": "timing", "text": "Again."}]},
    {"insights": [{"id": "timing", "text": "Afternoons.", "advice": "drink more"}]},
    {"insights": []},
    {"extra": "field"},
])
def test_ungrounded_unsafe_or_malformed_explanations_are_rejected(change):
    f = facts()
    with pytest.raises(ValueError):
        validate_explanation(explanation(f) | change, f)


def test_goal_insight_and_placeholders_are_rejected_when_no_goal_is_set():
    f = facts(goal=None)
    with pytest.raises(ValueError):
        validate_explanation({"summary": "Steady week.", "insights": [{"id": "goal_progress", "text": "Goal met."}]}, f)
    with pytest.raises(ValueError):
        validate_explanation({"summary": "Your goal is {goal}.", "insights": [{"id": "timing", "text": "Steady."}]}, f)


# Accounts: Amine's $20 allocation, Georgio's unchanged $30, no switching.

def test_allocations_must_match_each_accounts_reviewed_limits(tmp_path):
    with pytest.raises(ValidationError):
        amine_approval(hard_limit_micro_usd=150_000_000).model_validate(amine_approval(hard_limit_micro_usd=150_000_000).model_dump())
    with pytest.raises(ValidationError):  # the earlier $100 allocation is no longer accepted
        amine_approval(allocation_id="wonder-amine-100usd", hard_limit_micro_usd=100_000_000,
                       wonder_soft_target_micro_usd=100_000_000).model_validate(amine_approval(
            allocation_id="wonder-amine-100usd", hard_limit_micro_usd=100_000_000,
            wonder_soft_target_micro_usd=100_000_000).model_dump())
    with pytest.raises(ValidationError):
        approval(account_id=AMINE).model_validate(approval(account_id=AMINE).model_dump())
    with pytest.raises(ValidationError):  # Georgio cannot take Amine's limits.
        amine_approval(account_id=ACCOUNTS[0]).model_validate(amine_approval(account_id=ACCOUNTS[0]).model_dump())
    _, ledger = amine_setup(tmp_path)
    view = ledger.snapshot()
    assert (view["account_id"], view["hard_limit_micro_usd"], view["account_cutoff_micro_usd"]) == (AMINE, 20_000_000, 100_000_000)


def test_amine_account_explains_trends_once_and_settles_at_wonder_prices(tmp_path):
    authority, ledger = amine_setup(tmp_path)
    f = facts()
    transport = amine_transport(trend_reply(f))
    gateway = WonderHydrationGateway(ledger, transport, FakeNotifier())
    result = gateway.explain_trends(f, amine_quote(), "in-app-consent:synthetic")
    assert transport.calls == 1 and result["facts"] == f
    assert [i["id"] for i in result["insights"]] == ["week_over_week", "goal_progress"]
    provenance = result["provenance"]
    assert (provenance["account_id"], provenance["model"], provenance["text_origin"]) == (AMINE, WONDER, "muse_wonder_checked")
    assert result["provider_observations"]["usage_derived_cost_micro_usd"] == 6000
    [(attempt, state, _, actual, _)] = attempt_rows(authority)
    assert (attempt, state, actual) == (provenance["attempt_id"], "settled", 6000) and not frozen(authority)
    with authority.transaction() as db:
        assert db.execute("SELECT account_id FROM live_attempts").fetchone()[0] == AMINE
    assert validate_recorded_trends(result) == result
    # The same data is never approved or paid for again.
    with pytest.raises(RecognitionUnavailable):
        WonderHydrationGateway(ledger, transport, FakeNotifier()).explain_trends(f, amine_quote(), "in-app-consent:again")
    assert transport.calls == 1


@pytest.mark.parametrize("baseline", [99_990_000, 100_000_000])
def test_amine_account_stops_at_100_dollars(tmp_path, baseline):
    authority, ledger = amine_setup(tmp_path, baseline=baseline)
    transport = amine_transport()
    gateway = WonderHydrationGateway(ledger, transport, FakeNotifier())
    with pytest.raises(RecognitionUnavailable):
        gateway.explain_trends(facts(), amine_quote(), "in-app-consent:synthetic")
    assert transport.calls == 0 and attempt_rows(authority) == [] and gateway.last_attempt is None


def test_quote_for_the_other_account_is_refused_before_reservation(tmp_path):
    authority, ledger = amine_setup(tmp_path)
    transport = amine_transport()
    gateway = WonderHydrationGateway(ledger, transport, FakeNotifier())
    with pytest.raises(RecognitionUnavailable):
        gateway.explain_trends(facts(), quote(WONDER), "in-app-consent:synthetic")  # Georgio's quote
    assert transport.calls == 0 and attempt_rows(authority) == []


def test_trends_need_the_standing_trend_approval(tmp_path):
    authority, ledger = amine_setup(tmp_path, trend_dispatch_reference=None)
    transport = amine_transport()
    with pytest.raises(RecognitionUnavailable):
        WonderHydrationGateway(ledger, transport, FakeNotifier()).explain_trends(facts(), amine_quote(), "consent")
    assert transport.calls == 0 and attempt_rows(authority) == []


def test_unsent_trend_case_is_reused_not_duplicated(tmp_path):
    _, ledger = amine_setup(tmp_path)
    digest = payload_sha256(trends_payload(facts()))
    first = ledger.register_trend_case(digest, "consent-a")
    assert ledger.register_trend_case(digest, "consent-b") == first


def test_request_refused_before_reservation_can_later_run_the_same_data(tmp_path):
    authority, ledger = amine_setup(tmp_path)
    f = facts()
    transport = amine_transport(trend_reply(f))
    with pytest.raises(RecognitionUnavailable):  # wrong account's quote: refused, case left unsent
        WonderHydrationGateway(ledger, transport, FakeNotifier()).explain_trends(f, quote(WONDER), "consent-first")
    result = WonderHydrationGateway(ledger, transport, FakeNotifier()).explain_trends(f, amine_quote(), "consent-second")
    assert transport.calls == 1 and result["provenance"]["account_id"] == AMINE


def test_prior_unfinalized_attempt_blocks_the_next_request(tmp_path):
    authority, ledger = amine_setup(tmp_path)
    transport = amine_transport(trend_reply(facts()))
    WonderHydrationGateway(ledger, transport, FakeNotifier()).explain_trends(facts(), amine_quote(), "consent")
    newer = facts(logged=records() + [{"consumed_at": "2026-10-28T20:00:00+00:00", "consumed_ml": 300.0, "category": "tea"}])
    with pytest.raises(RecognitionUnavailable):
        WonderHydrationGateway(ledger, transport, FakeNotifier()).explain_trends(newer, amine_quote(), "consent")
    assert transport.calls == 1  # invoice finality for the first attempt is still required


def test_rejected_text_after_settlement_is_recorded_without_freezing(tmp_path):
    authority, ledger = amine_setup(tmp_path)
    f = facts()
    bad = explanation(f) | {"summary": "You may be dehydrated."}
    gateway = WonderHydrationGateway(ledger, amine_transport(trend_reply(f, bad)), FakeNotifier())
    with pytest.raises(RecognitionUnavailable):
        gateway.explain_trends(f, amine_quote(), "consent")
    [(_, state, _, actual, _)] = attempt_rows(authority)
    assert (state, actual) == ("settled", 6000) and not frozen(authority)
    assert "experiment_output_rejected" in events(authority)


def test_usage_over_the_reservation_still_freezes(tmp_path):
    authority, ledger = amine_setup(tmp_path)
    f = facts()
    gateway = WonderHydrationGateway(ledger, amine_transport(trend_reply(f, inputs=1_000_000)), FakeNotifier())
    with pytest.raises(RecognitionUnavailable):
        gateway.explain_trends(f, amine_quote(), "consent")
    assert frozen(authority)


# Replay: saved once per payload, re-validated on every read.

def recorded(tmp_path):
    _, ledger = amine_setup(tmp_path)
    f = facts()
    return WonderHydrationGateway(ledger, amine_transport(trend_reply(f)), FakeNotifier()).explain_trends(
        f, amine_quote(), "consent")


@pytest.mark.parametrize("tamper", [
    lambda r: r.update(summary="You logged 9999 mL in the last 7 days."),
    lambda r: r.update(summary_template="You might be dehydrated."),
    lambda r: r["insights"][0].update(text="Something Hydra did not render."),
    lambda r: r["insights"][0].update(title="Diagnosis"),
    lambda r: r["facts"]["days"][0].update(total_ml=1),
    lambda r: r["provenance"].update(account_id="someone-else"),
    lambda r: r["provenance"].update(text_origin="reviewed_text"),
    lambda r: r.update(generated_at="2026-10-28T12:00:00"),
    lambda r: r.update(payload_sha256="0" * 64),
    lambda r: r["provider_observations"].update(billed_cost_usd=0.01),
])
def test_tampered_trend_records_are_rejected(tmp_path, tamper):
    result = json.loads(json.dumps(recorded(tmp_path)))
    tamper(result)
    with pytest.raises(ValueError):
        validate_recorded_trends(result)


def test_trend_records_are_write_once_and_latest_skips_tampered_files(tmp_path):
    results = tmp_path / "results"
    results.mkdir(mode=0o700)
    result = recorded(tmp_path)
    path = save_result(results, result)
    assert path.name == f"trends-{result['payload_sha256']}.json" and os.stat(path).st_mode & 0o777 == 0o600
    assert load_trends(results, result["payload_sha256"]) == result and latest_trends(results) == result
    with pytest.raises(FileExistsError):
        save_result(results, result)
    (results / ("trends-" + "f" * 64 + ".json")).write_text(json.dumps(result | {"summary": "Tampered 9999."}))
    assert latest_trends(results) == result


# HTTP: preview what is sent, consent to that exact payload, never pay twice.

@pytest.fixture
def client_env(monkeypatch):
    for name in ("HYDRA_AI_MODE", "META_BILLABLE_REQUESTS_ENABLED", "HYDRA_META_HYDRATION_ENABLED", "HYDRA_WONDER_LIVE",
                 "HYDRA_WONDER_ACCOUNT", "HYDRA_WONDER_LEDGER", "HYDRA_WONDER_QUOTE", "HYDRA_WONDER_RESULTS_DIR",
                 "HYDRA_META_GEORGIO_API_KEY", "HYDRA_META_AMINE_API_KEY", "HYDRA_GITHUB_NOTIFICATION_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


AUTH = {"Authorization": f"Bearer {TOKEN}"}


def seed(client, days=10):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    for offset in range(days):
        body = dict(category="water", consumed_ml=1500 + 50 * offset, consumed_at=(now - timedelta(days=offset, hours=1))
                    .isoformat().replace("+00:00", "Z"), timezone="UTC", source="manual")
        assert client.post("/v1/beverages", json=body, headers=AUTH | {"Idempotency-Key": str(uuid4())}).status_code == 201
    assert client.put("/v1/settings", json={"daily_beverage_goal_ml": 2000}, headers=AUTH).status_code == 200


def live_env(env, tmp_path, *, baseline=0):
    authority, ledger = amine_setup(tmp_path, baseline=baseline)
    quote_file = tmp_path / "quote.json"
    quote_file.write_text(amine_quote().model_dump_json())
    results = tmp_path / "results"
    results.mkdir(mode=0o700)
    for name, value in {"META_BILLABLE_REQUESTS_ENABLED": "true", "HYDRA_WONDER_LIVE": "true",
                        "HYDRA_WONDER_ACCOUNT": AMINE, "HYDRA_WONDER_LEDGER": str(authority.path),
                        "HYDRA_WONDER_QUOTE": str(quote_file), "HYDRA_WONDER_RESULTS_DIR": str(results),
                        "HYDRA_META_AMINE_API_KEY": "synthetic-amine-key",
                        "HYDRA_GITHUB_NOTIFICATION_TOKEN": "synthetic-notify-token"}.items():
        env.setenv(name, value)
    return authority, ledger


def fake_live(app, ledger, transport):
    app.state.wonder_trends_gateway = lambda: WonderHydrationGateway(ledger, transport, FakeNotifier())


def consent(view):
    return {"timezone": "UTC", "payload_sha256": view["payload_sha256"], "consent_to_send": True}


def test_preview_shows_what_would_be_sent_without_live_configuration(tmp_path, client_env):
    with TestClient(create_app(tmp_path / "data.sqlite3", TOKEN)) as client:
        seed(client)
        view = client.get("/v1/wonder/trends", params={"timezone": "UTC"}, headers=AUTH).json()
        assert view["explainable"] and view["live_available"] is False and view["account_id"] is None
        assert view["facts"]["goal_ml"] == 2000 and view["facts"]["last_7_days"]["logged_days"] == 7
        assert view["saved"] is None and view["latest"] is None
        response = client.post("/v1/wonder/trends", json=consent(view), headers=AUTH)
        assert response.status_code == 503 and response.json()["code"] == "wonder_unavailable"
        assert client.post("/v1/wonder/trends", json=consent(view) | {"consent_to_send": False}, headers=AUTH).status_code == 422
        assert client.get("/v1/wonder/trends", params={"timezone": "Not/AZone"}, headers=AUTH).status_code == 422


def test_live_request_is_bound_to_the_previewed_payload_and_never_paid_twice(tmp_path, client_env):
    authority, ledger = live_env(client_env, tmp_path)
    app = create_app(tmp_path / "data.sqlite3", TOKEN)
    with TestClient(app) as client:
        seed(client)
        view = client.get("/v1/wonder/trends", params={"timezone": "UTC"}, headers=AUTH).json()
        assert view["live_available"] and view["account_id"] == AMINE
        stale = client.post("/v1/wonder/trends", json=consent(view) | {"payload_sha256": "0" * 64}, headers=AUTH)
        assert stale.status_code == 409 and stale.json()["code"] == "trends_preview_stale"
        transport = amine_transport(trend_reply(view["facts"], {"summary": "A steady fortnight of logging.",
            "insights": [{"id": "timing", "text": "Your peak time was {peak_time}."}]}))
        fake_live(app, ledger, transport)
        first = client.post("/v1/wonder/trends", json=consent(view), headers=AUTH).json()
        assert (first["replayed"], first["saved"], transport.calls) == (False, True, 1)
        assert first["result"]["provenance"]["account_id"] == AMINE
        again = client.post("/v1/wonder/trends", json=consent(view), headers=AUTH).json()
        assert (again["replayed"], again["result"], transport.calls) == (True, first["result"], 1)
        view = client.get("/v1/wonder/trends", params={"timezone": "UTC"}, headers=AUTH).json()
        assert view["saved"] == first["result"] == view["latest"]


def test_spending_gate_refusal_reports_nothing_sent(tmp_path, client_env):
    _, ledger = live_env(client_env, tmp_path, baseline=100_000_000)
    app = create_app(tmp_path / "data.sqlite3", TOKEN)
    with TestClient(app) as client:
        seed(client)
        transport = amine_transport()
        fake_live(app, ledger, transport)
        view = client.get("/v1/wonder/trends", params={"timezone": "UTC"}, headers=AUTH).json()
        response = client.post("/v1/wonder/trends", json=consent(view), headers=AUTH)
        assert response.status_code == 409 and response.json()["code"] == "wonder_blocked" and transport.calls == 0


def test_failure_after_reservation_names_the_attempt(tmp_path, client_env):
    authority, ledger = live_env(client_env, tmp_path)
    app = create_app(tmp_path / "data.sqlite3", TOKEN)
    with TestClient(app) as client:
        seed(client)
        fake_live(app, ledger, amine_transport(fault=TimeoutError()))
        view = client.get("/v1/wonder/trends", params={"timezone": "UTC"}, headers=AUTH).json()
        response = client.post("/v1/wonder/trends", json=consent(view), headers=AUTH)
        body = response.json()
        assert response.status_code == 502 and body["code"] == "wonder_attempt_unresolved"
        assert body["attempt_id"] == attempt_rows(authority)[0][0] and frozen(authority)


@pytest.mark.parametrize("unset,changes", [
    (None, {"META_BILLABLE_REQUESTS_ENABLED": "false"}),
    ("HYDRA_META_AMINE_API_KEY", {}),
    ("HYDRA_GITHUB_NOTIFICATION_TOKEN", {}),
    ("HYDRA_WONDER_RESULTS_DIR", {}),
    (None, {"HYDRA_WONDER_ACCOUNT": "someone-else"}),
    (None, {"HYDRA_WONDER_LEDGER": "relative.sqlite3"}),
    (None, {"HYDRA_WONDER_LIVE": "maybe"}),
])
def test_live_configuration_fails_closed_at_startup(tmp_path, client_env, unset, changes):
    live_env(client_env, tmp_path)
    if unset:
        client_env.delenv(unset)
    for name, value in changes.items():
        client_env.setenv(name, value)
    with pytest.raises(ValueError):
        create_app(tmp_path / "data.sqlite3", TOKEN)


def test_georgio_key_is_never_used_for_amines_account(tmp_path, client_env):
    live_env(client_env, tmp_path)
    client_env.delenv("HYDRA_META_AMINE_API_KEY")
    client_env.setenv("HYDRA_META_GEORGIO_API_KEY", "synthetic-key")
    with pytest.raises(ValueError):
        create_app(tmp_path / "data.sqlite3", TOKEN)


def test_admin_templates_and_key_follow_the_quote_account(tmp_path, monkeypatch):
    import scripts.wonder_admin as admin
    template = admin.templates(AMINE)
    assert (template["allocation"]["hard_limit_micro_usd"], template["account_cutoff_micro_usd"]) == (20_000_000, 100_000_000)
    assert template["quote"]["account_id"] == AMINE and template["allocation"]["trend_dispatch_reference"].startswith("REQUIRED")
    keys = []
    monkeypatch.setattr(admin, "WonderMetaTransport", lambda key: keys.append(key) or amine_transport())
    monkeypatch.setattr(admin, "GitHubNotifier", lambda token: FakeNotifier())
    monkeypatch.setenv("HYDRA_META_AMINE_API_KEY", "synthetic-amine-key")
    monkeypatch.setenv("HYDRA_META_GEORGIO_API_KEY", "synthetic-key")
    args = admin.argparse.Namespace(confirm_billable=True, results_dir=tmp_path, question_id=None, scenario="complete",
                                    case_id=str(uuid4()), input_reference="x")
    _, ledger = amine_setup(tmp_path)
    with pytest.raises(admin.RunCaseFailed):
        admin.run_case(ledger, args, amine_quote())  # no approved case: refused before reservation
    assert keys == ["synthetic-amine-key"]


# Review findings (2026-10-29): each was a reproduced failure before its fix.

def test_wrong_key_is_refused_before_reservation_without_freezing(tmp_path):
    authority, ledger = amine_setup(tmp_path)
    transport = amine_transport(trend_reply(facts()))
    transport.credential_fingerprint = "0" * 64
    gateway = WonderHydrationGateway(ledger, transport, FakeNotifier())
    with pytest.raises(RecognitionUnavailable):
        gateway.explain_trends(facts(), amine_quote(), "consent")
    assert gateway.last_attempt is None and attempt_rows(authority) == [] and not frozen(authority)


@pytest.mark.parametrize("changes", [{"HYDRA_META_AMINE_API_KEY": "a-different-amine-key"},
                                     {"HYDRA_WONDER_ACCOUNT": ACCOUNTS[0], "HYDRA_META_GEORGIO_API_KEY": "synthetic-key"}])
def test_startup_refuses_a_key_or_account_the_ledger_does_not_name(tmp_path, client_env, changes):
    live_env(client_env, tmp_path)
    for name, value in changes.items():
        client_env.setenv(name, value)
    with pytest.raises(ValueError):
        create_app(tmp_path / "data.sqlite3", TOKEN)


def test_delete_all_removes_saved_trends_and_export_includes_them(tmp_path, client_env):
    _, ledger = live_env(client_env, tmp_path)
    app = create_app(tmp_path / "data.sqlite3", TOKEN)
    with TestClient(app) as client:
        seed(client)
        view = client.get("/v1/wonder/trends", params={"timezone": "UTC"}, headers=AUTH).json()
        fake_live(app, ledger, amine_transport(trend_reply(view["facts"], explanation())))
        result = client.post("/v1/wonder/trends", json=consent(view), headers=AUTH).json()["result"]
        assert client.get("/v1/export", headers=AUTH).json()["wonder_trends"] == [result]
        deleted = client.delete("/v1/data", params={"confirm": "delete-all-my-data"}, headers=AUTH).json()
        assert deleted["deleted_trend_explanations"] == 1
        view = client.get("/v1/wonder/trends", params={"timezone": "UTC"}, headers=AUTH).json()
        assert view["latest"] is None and view["saved"] is None and view["explainable"] is False


def test_a_huge_weekly_change_is_explainable_not_a_server_error(tmp_path, client_env):
    with TestClient(create_app(tmp_path / "data.sqlite3", TOKEN)) as client:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        for offset, volume in ((10, 5), (1, 5000), (2, 5000)):
            body = dict(category="water", consumed_ml=volume, consumed_at=(now - timedelta(days=offset)).isoformat()
                        .replace("+00:00", "Z"), timezone="UTC", source="manual")
            client.post("/v1/beverages", json=body, headers=AUTH | {"Idempotency-Key": str(uuid4())})
        view = client.get("/v1/wonder/trends", params={"timezone": "UTC"}, headers=AUTH)
        assert view.status_code == 200 and view.json()["facts"]["change_pct"] == 199900


def test_a_saved_record_only_replays_for_its_own_payload(tmp_path):
    results = tmp_path / "results"
    results.mkdir(mode=0o700)
    result = recorded(tmp_path)
    (results / ("trends-" + "e" * 64 + ".json")).write_text(json.dumps(result))
    with pytest.raises(ValueError):
        load_trends(results, "e" * 64)


def test_allocations_without_trends_keep_their_recorded_bytes(tmp_path):
    authority = AccountLedger(tmp_path / "georgio.sqlite3")
    authority.initialize_accounts()
    authority.attest_account(evidence(ACCOUNTS[0]))
    with authority.transaction() as db:
        for sql in LIVE_SCHEMA:
            db.execute(sql)
    ledger = WonderExperimentLedger(authority)
    original = approval()
    ledger.record_approval(original)
    with authority.transaction() as db:
        stored = db.execute("SELECT approval FROM experiment_allocation").fetchone()[0]
    assert "trend_dispatch_reference" not in stored
    ledger.record_approval(original)  # identical re-record stays a no-op


GEORGIO = ACCOUNTS[0]


def georgio_key_approval(**changes):
    """The owner-override ledger on Amine's Mac: Georgio's key and account, $20 of Wonder."""
    values = dict(account_id=GEORGIO, allocation_id="wonder-georgio-key-amine-mac-20usd", hard_limit_micro_usd=20_000_000,
                  spark_soft_target_micro_usd=0, wonder_soft_target_micro_usd=20_000_000,
                  key_sha256=evidence(GEORGIO).key_sha256, owner_authorization_reference="synthetic-georgio-owner",
                  trend_dispatch_reference="synthetic-trend-dispatch")
    return approval(**(values | changes))


@pytest.mark.parametrize("account,make", [(AMINE, lambda: amine_approval()), (GEORGIO, lambda: georgio_key_approval())])
def test_twenty_dollar_allocations_stop_at_20_dollars(tmp_path, account, make):
    from backend.meta_budget import BudgetDenied
    from backend.meta_experiments import PROPOSED_SCHEMA, ExperimentBudget, ExperimentRequest
    authority = AccountLedger(tmp_path / "cap.sqlite3")
    authority.initialize_accounts()
    authority.attest_account(evidence(account))
    with authority.transaction() as db:
        for sql in PROPOSED_SCHEMA:
            db.execute(sql)
    budget = ExperimentBudget(authority)
    budget.record_approval(make())

    def reserve():
        budget.reserve_review_only(ExperimentRequest.model_validate({
            "attempt_id": str(uuid4()), "case_id": str(uuid4()), "payload_sha256": "a" * 64, "input_bound": 1000,
            "output_bound": 512, "maximum_micro_usd": 250_000, "input_approval_reference": "synthetic-consent",
            "quote": quote(WONDER, account_id=account)}))

    for _ in range(80):  # 80 x $0.25 reservations, each settled for 1 micro-USD with recorded finality
        reserve()
        now = datetime.now(timezone.utc)
        with authority.transaction() as db:
            attempt = db.execute("SELECT id FROM live_attempts WHERE actual IS NULL").fetchone()[0]
            provider = "resp_fixture_" + attempt.replace("-", "")
            db.execute("UPDATE live_attempts SET actual=1,provider_id=?,state='settled',dispatched_at=? WHERE id=?",
                       (provider, (now - timedelta(seconds=1)).isoformat(), attempt))
            db.execute("INSERT INTO live_finalities(attempt_id,evidence,recorded_at) VALUES(?,?,?)", (attempt, json.dumps({
                "attempt_id": attempt, "account_id": account, "provider_id": provider, "final_gross_micro_usd": 1,
                "finalized_at": now.isoformat(), "provider_evidence_reference": "synthetic-invoice",
                "georgio_review_reference": "synthetic-a", "amine_review_reference": "synthetic-b",
                "provider_finality_verified": True}), now.isoformat()))
    view = budget.snapshot()
    assert (view["account_id"], view["aggregate_exposure_micro_usd"], view["remaining_micro_usd"]) == (account, 20_000_000, 0)
    with pytest.raises(BudgetDenied):
        reserve()


def test_georgio_key_allocation_is_georgios_own_and_keeps_his_120_cutoff(tmp_path):
    with pytest.raises(ValidationError):  # never recorded as Amine's account
        georgio_key_approval(account_id=AMINE).model_validate(georgio_key_approval(account_id=AMINE).model_dump())
    with pytest.raises(ValidationError):  # the limit is fixed at $20
        georgio_key_approval(hard_limit_micro_usd=30_000_000).model_validate(
            georgio_key_approval(hard_limit_micro_usd=30_000_000).model_dump())
    authority = AccountLedger(tmp_path / "georgio-key.sqlite3")
    authority.initialize_accounts()
    authority.attest_account(evidence(GEORGIO))
    with authority.transaction() as db:
        for sql in LIVE_SCHEMA:
            db.execute(sql)
    ledger = WonderExperimentLedger(authority)
    ledger.record_approval(georgio_key_approval())
    view = ledger.snapshot()
    assert (view["allocation_id"], view["hard_limit_micro_usd"], view["account_cutoff_micro_usd"]) == (
        "wonder-georgio-key-amine-mac-20usd", 20_000_000, 120_000_000)
    f = facts()
    transport = FakeWonderTransport(trend_reply(f))
    result = WonderHydrationGateway(ledger, transport, FakeNotifier()).explain_trends(
        f, quote(WONDER), "in-app-consent:synthetic")
    assert transport.calls == 1 and result["provenance"]["account_id"] == GEORGIO
    assert ledger.snapshot()["remaining_micro_usd"] < 20_000_000


def test_admin_templates_offer_the_georgio_key_allocation(tmp_path):
    import scripts.wonder_admin as admin
    template = admin.templates(GEORGIO, "wonder-georgio-key-amine-mac-20usd")
    assert (template["allocation"]["hard_limit_micro_usd"], template["account_cutoff_micro_usd"]) == (20_000_000, 120_000_000)
    assert template["quote"]["account_id"] == GEORGIO
    assert admin.templates(GEORGIO)["allocation"]["hard_limit_micro_usd"] == 30_000_000  # default unchanged
    with pytest.raises(ValueError):
        admin.templates(AMINE, "wonder-georgio-key-amine-mac-20usd")


def georgio_key_ledger(tmp_path):
    authority = AccountLedger(tmp_path / "georgio-key-limit.sqlite3")
    authority.initialize_accounts()
    authority.attest_account(evidence(GEORGIO))
    with authority.transaction() as db:
        for sql in LIVE_SCHEMA:
            db.execute(sql)
    ledger = WonderExperimentLedger(authority)
    ledger.record_approval(georgio_key_approval())
    return authority, ledger


def test_owner_can_raise_and_lower_the_adjustable_limit_with_an_audit_trail(tmp_path):
    from backend.meta_budget import BudgetDenied
    authority, ledger = georgio_key_ledger(tmp_path)
    assert ledger.snapshot()["hard_limit_micro_usd"] == 20_000_000
    assert ledger.snapshot()["limit_adjustable_up_to_micro_usd"] == 85_000_000
    raised = ledger.set_limit(35_000_000, "amine-raise-to-35")
    assert (raised["hard_limit_micro_usd"], raised["remaining_micro_usd"]) == (35_000_000, 35_000_000)
    assert ledger.snapshot()["hard_limit_micro_usd"] == 35_000_000
    f = facts()
    transport = FakeWonderTransport(trend_reply(f))
    WonderHydrationGateway(ledger, transport, FakeNotifier()).explain_trends(f, quote(WONDER), "in-app-consent:synthetic")
    spent = ledger.snapshot()["aggregate_exposure_micro_usd"]
    lowered = ledger.set_limit(1, "amine-pause")  # below what is spent: blocks further requests, keeps history
    assert (lowered["aggregate_exposure_micro_usd"], lowered["remaining_micro_usd"]) == (spent, 0)
    for bad in (0, 85_000_001, 20.5):
        with pytest.raises(BudgetDenied):
            ledger.set_limit(bad, "amine-bad")
    with pytest.raises(BudgetDenied):
        ledger.set_limit(30_000_000, " ")
    with authority.transaction() as db:
        changes = [json.loads(r)["limit_micro_usd"] for (r,) in
                   db.execute("SELECT reference FROM live_events WHERE kind='experiment_limit_changed' ORDER BY id")]
    assert changes == [35_000_000, 1]


def test_lowered_limit_refuses_the_next_reservation(tmp_path):
    authority, ledger = georgio_key_ledger(tmp_path)
    ledger.set_limit(1, "amine-pause")
    transport = FakeWonderTransport(trend_reply(facts()))
    with pytest.raises(RecognitionUnavailable):
        WonderHydrationGateway(ledger, transport, FakeNotifier()).explain_trends(facts(), quote(WONDER), "in-app-consent:x")
    assert transport.calls == 0 and attempt_rows(authority) == []


def test_fixed_allocations_cannot_change_their_limit(tmp_path):
    from backend.meta_budget import BudgetDenied
    _, ledger = amine_setup(tmp_path)
    with pytest.raises(BudgetDenied):
        ledger.set_limit(30_000_000, "amine-raise")
    assert ledger.snapshot()["hard_limit_micro_usd"] == 20_000_000


def test_admin_set_limit_command(tmp_path, capsys):
    import scripts.wonder_admin as admin
    authority, _ = georgio_key_ledger(tmp_path)
    admin.main(["set-limit", "--database", str(authority.path), "--limit-usd", "25.50", "--reference", "amine-raise"])
    assert json.loads(capsys.readouterr().out)["hard_limit_micro_usd"] == 25_500_000
    with pytest.raises(SystemExit):
        admin.main(["set-limit", "--database", str(authority.path), "--limit-usd", "86", "--reference", "amine-raise"])
