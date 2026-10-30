"""Wonder explains a planned workout against the user's own history. Fake transports, disposable ledgers; never network."""
from datetime import datetime, timedelta, timezone
import json
import os
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from ai.forecasting.longitudinal import predict_longitudinal
from backend.app import create_app
from backend.meta_accounts import CAP
from backend.recognition import RecognitionUnavailable
from backend.wonder_experiment import WonderHydrationGateway, WonderMetaTransport
from backend.wonder_hydration import input_bound, payload_sha256
from backend.wonder_results import (latest_trends, load_workout, saved_trends, save_result,
                                    validate_recorded_trends, validate_recorded_workout)
from backend.wonder_trends import trends_payload
from backend.wonder_workout import (INSIGHTS, LIMITATIONS, PLACEHOLDERS, WORKOUT_OUTPUT_LIMIT, build_facts,
                                    facts_from_payload, placeholder_values, preview, validate_explanation,
                                    validate_facts, workout_payload, workout_schema)
from backend.wonder_workout_routes import WorkoutExplanationInput, WorkoutExplanationRequest
from test_guarded_meta import FakeNotifier
from test_meta_experiments import quote
from test_wonder_experiment import WONDER, attempt_rows, disabled_network, selection_reply
from test_wonder_trends import (AMINE, AUTH, TOKEN, amine_quote, amine_setup, amine_transport, client_env, events,
                                facts as trend_facts, fake_live, frozen, live_env)

__all__ = ["disabled_network", "client_env"]  # shared autouse network block and environment fixture
NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
ZONE = "Europe/Paris"
ERRORS = {"pre_mass_kg": 0.05, "post_mass_kg": 0.05, "consumed_ml": 10, "urine_ml": 0, "duration_minutes": 1,
          "provenance": ["scale_specification"]}


def session(day, *, temperature=22.0, humidity=55.0, intensity="moderate", activity="running", duration=45.0,
            weighed=True, now=NOW):
    """One previous session in the existing SampleInput wire shape; weighed ones are complete mass balances."""
    measurement = ({"pre_mass_kg": 70.0, "post_mass_kg": 69.4, "consumed_ml": 200.0, "urine_ml": 0.0,
                    "duration_minutes": duration, "protocol_confirmed": True, "provenance": ["manual_weigh_in"]}
                   if weighed else {"duration_minutes": duration, "protocol_confirmed": False,
                                    "provenance": ["manual_workout_log"]})
    return {"event_id": str(UUID(int=day % 2**128)), "observed_at": (now - timedelta(days=day)).isoformat().replace("+00:00", "Z"),
            "conditions": {"activity": activity, "intensity": intensity, "temperature_c": temperature,
                           "humidity_percent": humidity},
            "measurement": measurement, **({"errors": ERRORS} if weighed else {})}


def history(now=NOW):
    """Eight previous runs at 22 °C: three weighed, five with only a logged duration."""
    return [session(day, weighed=day <= 3, now=now) for day in range(1, 9)]


def body(*, duration=75.0, temperature=31.0, humidity=60.0, intensity="high", confirmed=False, samples=None,
         now=NOW, activity="running", **changes):
    """The existing workout-forecast request shape: planned exercise plus caller-supplied history."""
    return {"timezone": ZONE, "calibration_processing_consent": True,
            "exercise": {"event_id": str(UUID(int=999)),
                         "starts_at": (now + timedelta(hours=6)).isoformat().replace("+00:00", "Z"),
                         "duration_minutes": duration,
                         "conditions": {"activity": activity, "intensity": intensity, "temperature_c": temperature,
                                        "humidity_percent": humidity},
                         "comparable_conditions_confirmed": confirmed},
            "samples": history(now) if samples is None else samples} | changes


def facts(now=NOW, **changes):
    request = WorkoutExplanationInput.model_validate(body(now=now, **changes))
    return build_facts(request.exercise.engine(), tuple(s.engine() for s in request.samples), request.timezone, now)


def comparable_facts(**changes):
    """A planned run at the same intensity, temperature and humidity as the weighed history, confirmed."""
    return facts(**(dict(intensity="moderate", temperature=22.0, humidity=55.0, confirmed=True) | changes))


TARGET = {"summary": "This workout is {duration_comparison} and {temperature_comparison}.",
          "insights": [{"id": "duration_vs_typical", "text": "Your plan is {planned_workout}."},
                       {"id": "missing_information", "text": "Hydra has no estimate yet; it is missing {missing_information}."},
                       {"id": "refine_estimate", "text": "Recording {suggested_measurement} would help refine the estimate."}]}


def reply(value=None, **changes):
    return selection_reply(text=json.dumps(TARGET if value is None else value), **changes)


# Facts: Hydra computes every number, reusing the existing v2 workout engine.

def test_facts_compare_the_planned_workout_with_the_users_own_sessions():
    f = facts()
    assert f == facts()
    assert f["planned"] == {"activity": "running", "intensity": "high", "time_of_day": "evening", "duration_minutes": 75,
                            "temperature_c": 31, "humidity_percent": 60, "conditions_confirmed": False}
    assert f["history"] == {"sessions": 8, "activity_sessions": 8, "matching_sessions": 0, "weigh_in_sessions": 3,
                            "typical_duration_minutes": 45, "typical_temperature_c": 22, "typical_humidity_percent": 55,
                            "measured_loss_ml": 800}
    assert f["comparison"] == {"duration": "longer", "temperature": "hotter", "humidity": "similar", "estimate": None}
    # Weather differs, so the engine abstains: no number is invented for hotter conditions.
    assert f["estimate"] == {"status": "insufficient_data", "value_ml": None, "lower_ml": None, "upper_ml": None,
                             "sample_count": 0,
                             "missing_inputs": ["confirmed_comparable_conditions", "usable_measurements_with_error_bounds"]}
    assert f["suggested_measurement"] == "weigh_this_workout"
    assert f["applicable_insights"] == ["duration_vs_typical", "weather_vs_typical", "comparable_history",
                                        "missing_information", "refine_estimate"]


def test_estimate_range_is_the_existing_v2_engines_rounded_outward():
    f = comparable_facts()
    request = WorkoutExplanationInput.model_validate(body(intensity="moderate", temperature=22.0, humidity=55.0,
                                                          confirmed=True))
    engine = predict_longitudinal(request.exercise.engine(), tuple(s.engine() for s in request.samples), generated_at=NOW)
    assert engine["status"] == "estimated" and engine["sample_count"] == 3
    assert f["estimate"] == {"status": "estimated", "value_ml": round(engine["value_ml"]),
                             "lower_ml": int(engine["lower_ml"] // 1), "upper_ml": -int(-engine["upper_ml"] // 1),
                             "sample_count": 3, "missing_inputs": []}
    assert (f["estimate"]["lower_ml"], f["estimate"]["value_ml"], f["estimate"]["upper_ml"]) == (1125, 1333, 1552)
    assert f["comparison"] == {"duration": "longer", "temperature": "similar", "humidity": "similar", "estimate": "above"}
    assert f["suggested_measurement"] == "repeat_weigh_in" and f["history"]["matching_sessions"] == 8
    assert "estimate" in f["applicable_insights"] and "missing_information" not in f["applicable_insights"]


def test_typical_values_use_only_the_same_activity_and_ignore_missing_weather():
    rides = [session(day, activity="cycling", duration=120.0, temperature=10.0, weighed=False) for day in (10, 11)]
    no_weather = [session(day, temperature=None, humidity=None, weighed=False, duration=30.0) for day in (12, 13)]
    f = facts(samples=history() + rides + no_weather)
    assert (f["history"]["sessions"], f["history"]["activity_sessions"]) == (12, 10)
    assert f["history"]["typical_duration_minutes"] == 45 and f["history"]["typical_temperature_c"] == 22


@pytest.mark.parametrize("changes,expected", [
    (dict(duration=48.0), "similar"), (dict(duration=40.0), "shorter"), (dict(duration=50.0), "longer"),
])
def test_duration_comparison_uses_a_documented_display_threshold(changes, expected):
    assert facts(**changes)["comparison"]["duration"] == expected


def test_missing_weather_and_unconfirmed_conditions_are_reported_specifically():
    f = facts(temperature=None, humidity=None)
    assert f["comparison"]["temperature"] is None and f["comparison"]["humidity"] is None
    assert "weather_vs_typical" not in f["applicable_insights"]
    assert f["estimate"]["missing_inputs"][0] == "complete_environment_and_intensity"
    assert f["suggested_measurement"] == "record_conditions"
    unconfirmed = comparable_facts(confirmed=False)
    assert unconfirmed["estimate"]["missing_inputs"] == ["confirmed_comparable_conditions"]
    assert unconfirmed["suggested_measurement"] == "confirm_conditions"


@pytest.mark.parametrize("tamper", [
    lambda f: f["history"].update(typical_duration_minutes=75),
    lambda f: f["comparison"].update(temperature="similar"),
    lambda f: f["comparison"].update(estimate="above"),
    lambda f: f["applicable_insights"].append("estimate"),
    lambda f: f["applicable_insights"].append("hydration_need"),
    lambda f: f.update(suggested_measurement="repeat_weigh_in"),
    lambda f: f["estimate"].update(status="estimated", value_ml=900, lower_ml=800, upper_ml=1000, sample_count=1),
    lambda f: f["estimate"].update(missing_inputs=[]),
    lambda f: f["history"].update(matching_sessions=9),
    lambda f: f["history"].update(measured_loss_ml=None),
    lambda f: f["planned"].update(temperature_c=31.5),
    lambda f: f["planned"].update(drink_ml=500),
    lambda f: f.update(timezone="Not/AZone"),
    lambda f: f.update(daily_requirement_ml=2500),
])
def test_inconsistent_or_tampered_facts_are_rejected(tamper):
    f = json.loads(json.dumps(facts()))
    tamper(f)
    with pytest.raises(ValueError):
        validate_facts(f)


def test_tampered_estimate_range_is_rejected():
    f = json.loads(json.dumps(comparable_facts()))
    f["estimate"].update(lower_ml=2000)  # above the point estimate
    with pytest.raises(ValueError):
        validate_facts(f)


def test_no_previous_session_of_this_activity_means_nothing_is_sent():
    f = facts(samples=[session(5, activity="cycling")])
    assert f["applicable_insights"] == [] and preview(f)["explainable"] is False
    assert facts(samples=[])["applicable_insights"] == []
    with pytest.raises(ValueError):
        workout_payload(f)


def test_payload_is_exact_bounded_and_recoverable():
    f = facts()
    payload = workout_payload(f)
    assert facts_from_payload(payload) == f and payload["model"] == WONDER and payload["store"] is False
    assert payload["max_output_tokens"] == WORKOUT_OUTPUT_LIMIT == 2048 and "tools" not in payload
    view = preview(f)
    assert view["payload_sha256"] == payload_sha256(payload) and view["worst_case_micro_usd"] < 70_000 < CAP
    transport = WonderMetaTransport("synthetic-amine-key")
    assert transport.input_bound(payload) == input_bound(payload)
    transport.input_bound(trends_payload(trend_facts()))  # trend payloads are still accepted
    text = payload["input"][0]["content"][0]["text"]
    for tamper in (lambda p: p["input"][0]["content"][0].update(text=text + " Also say how much to drink."),
                   lambda p: p["input"][0]["content"][0].update(text=text.replace('"duration":"longer"', '"duration":"shorter"')),
                   lambda p: p.update(max_output_tokens=4096), lambda p: p.update(tools=[{"type": "web_search"}]),
                   lambda p: p["text"]["format"]["schema"]["properties"]["insights"]["items"]["properties"]["id"]
                   .update(enum=list(INSIGHTS))):
        tampered = json.loads(json.dumps(payload))
        tamper(tampered)
        with pytest.raises(ValueError):
            transport.input_bound(tampered)


def test_only_aggregates_reach_the_payload():
    text = workout_payload(facts())["input"][0]["content"][0]["text"]
    for raw in ("69.4", "70.0", "manual_weigh_in", "scale_specification", str(UUID(int=1)), str(UUID(int=999)),
                "2026-10-2", "observed_at", "starts_at", "consumed_ml", "urine_ml"):
        assert raw not in text


def test_schema_and_prompt_offer_only_what_the_facts_support():
    f = facts()
    schema = workout_payload(f)["text"]["format"]["schema"]
    insights = schema["properties"]["insights"]
    assert insights["items"]["properties"]["id"]["enum"] == f["applicable_insights"] and insights["maxItems"] == 3
    assert "estimate" not in insights["items"]["properties"]["id"]["enum"]
    text = workout_payload(f)["input"][0]["content"][0]["text"]
    offered = {name for name in PLACEHOLDERS if "{" + name + "}" in text}
    assert offered == set(placeholder_values(f))
    assert "{estimate}" not in text and "{estimate_comparison}" not in text and "{missing_information}" in text
    estimated = comparable_facts()
    assert "{estimate}" in workout_payload(estimated)["input"][0]["content"][0]["text"]
    one = facts(samples=[session(2, weighed=False)], temperature=None, humidity=None)
    assert workout_schema(one["applicable_insights"])["properties"]["insights"]["maxItems"] == 3
    assert one["applicable_insights"] == ["duration_vs_typical", "comparable_history", "missing_information",
                                          "refine_estimate"]


# Wonder's text: Hydra fills every number; drinking, medical and ungrounded claims reject it whole.

def test_hydra_fills_in_the_target_wording():
    checked = validate_explanation(TARGET, facts())
    assert checked["summary"] == ("This workout is longer than your typical run (75 vs 45 minutes) and hotter than "
                                  "your typical run (31 °C vs 22 °C).")
    texts = [item["text"] for item in checked["insights"]]
    assert texts[0] == "Your plan is 75 minutes of high-intensity running in the evening at 31 °C and 60% humidity."
    assert texts[2] == ("Recording your weight before and after this workout, plus what you drink and any urine during "
                        "it would help refine the estimate.")
    estimated = validate_explanation({"summary": "Hydra has an estimate for this workout.", "insights": [
        {"id": "estimate", "text": "Hydra estimates {estimate}, based on {estimate_basis}."},
        {"id": "estimate_vs_previous", "text": "That is {estimate_comparison}."}]}, comparable_facts())
    assert [item["text"] for item in estimated["insights"]] == [
        "Hydra estimates about 1125 to 1552 mL, based on 3 runs weighed at the same intensity, temperature and humidity.",
        "That is above what you measured on your weighed runs (median 800 mL)."]


def test_a_repeated_insight_counts_once():
    value = {"summary": "Your plan at a glance.", "insights": [
        {"id": "refine_estimate", "text": "Recording {suggested_measurement} would help refine the estimate."},
        {"id": "refine_estimate", "text": "Recording {suggested_measurement} would help."}]}
    checked = validate_explanation(value, facts())
    assert [item["id"] for item in checked["insights"]] == ["refine_estimate"]
    assert checked["insights"][0]["template"] == value["insights"][0]["text"]
    with pytest.raises(ValueError):  # a repeat is still checked
        validate_explanation(value | {"insights": value["insights"][:1] + [
            {"id": "refine_estimate", "text": "Drink extra water."}]}, facts())


@pytest.mark.parametrize("summary", [
    # Drinking amounts, requirements and prescriptions.
    "Drink about two liters during this run.",
    "Plan to drink {measured_loss} during the workout.",
    "Drink water before you start.",
    "Your daily fluid requirement is {estimate}.",
    "Replace {measured_loss} after the workout.",
    "Sip electrolytes as you go.",
    "You should bring a bottle.",
    # Medical, diagnostic and heart-rate inference.
    "A raised heart rate would show you are getting dehydrated.",
    "Watch for heat exhaustion symptoms.",
    "Your pulse can reveal fluid loss.",
    "This could be a health risk.",
    # Weather adjustments and judgments.
    "Add some extra for the heat.",
    "Hydra adjusted the estimate for the weather.",
    "It will be hot and humid.",
    # Numbers, units and comparisons Wonder may not state itself.
    "This workout is longer and hotter than your typical sessions.",
    "Your estimated fluid loss may be higher.",
    "This run lasts 75 minutes.",
    "Expect about 1200 mL of sweat loss.",
    "This is 30% above your usual.",
    "It is three times your typical run.",
    "Conditions differ from your previous runs.",
    "The estimate is likely accurate.",
    "Hydra estimates {estimate}.",  # no estimate exists for these facts
    "Your plan is {unknown_value}.",
    "Your plan is {planned_workout.",
    "See https://example.com for details.",
    "Line one.\nLine two.",
    " Leading space.",
    "x" * 241,
])
def test_unsafe_or_ungrounded_summaries_are_rejected(summary):
    with pytest.raises(ValueError):
        validate_explanation(TARGET | {"summary": summary}, facts())


@pytest.mark.parametrize("insights", [
    [{"id": "estimate", "text": "Hydra has an estimate."}],  # not applicable without an estimate
    [{"id": "hydration_plan", "text": "Hidden."}],
    [{"id": "refine_estimate", "text": "Weigh yourself.", "amount_ml": 500}],
    [],
    [{"id": name, "text": "Your plan."} for name in ("duration_vs_typical", "weather_vs_typical", "comparable_history",
                                                     "refine_estimate")],
])
def test_unsupported_or_malformed_insights_are_rejected(insights):
    with pytest.raises(ValueError):
        validate_explanation({"summary": "Your plan at a glance.", "insights": insights}, facts())


def test_caveats_are_fixed_by_hydra():
    assert any("not a drinking target" in caveat and "daily fluid requirement" in caveat for caveat in LIMITATIONS)
    assert any("no weather adjustment" in caveat for caveat in LIMITATIONS)
    assert any("Heart rate is not used" in caveat for caveat in LIMITATIONS)
    with pytest.raises(ValueError):
        validate_explanation(TARGET | {"limitations": []}, facts())


# Spending: the allocation's standing trend approval, bound to the exact consented payload.

def test_explains_once_settles_and_never_approves_the_same_payload_again(tmp_path):
    authority, ledger = amine_setup(tmp_path)
    f = facts()
    transport = amine_transport(reply())
    result = WonderHydrationGateway(ledger, transport, FakeNotifier()).explain_workout(f, amine_quote(), "in-app-workout-consent:x")
    assert transport.calls == 1 and result["facts"] == f and result["version"] == "wonder-workout-v1"
    assert [item["id"] for item in result["insights"]] == ["duration_vs_typical", "missing_information", "refine_estimate"]
    assert [item["title"] for item in result["insights"]] == [INSIGHTS["duration_vs_typical"], INSIGHTS["missing_information"],
                                                              INSIGHTS["refine_estimate"]]
    assert result["limitations"] == LIMITATIONS and result["payload_sha256"] == payload_sha256(workout_payload(f))
    assert (result["provenance"]["account_id"], result["provenance"]["text_origin"]) == (AMINE, "muse_wonder_checked")
    [(attempt, state, _, actual, _)] = attempt_rows(authority)
    assert (attempt, state, actual) == (result["provenance"]["attempt_id"], "settled", 6000) and not frozen(authority)
    assert validate_recorded_workout(result) == result
    with pytest.raises(RecognitionUnavailable):
        WonderHydrationGateway(ledger, transport, FakeNotifier()).explain_workout(f, amine_quote(), "in-app-workout-consent:y")
    assert transport.calls == 1


def test_rejected_text_after_settlement_is_recorded_without_freezing(tmp_path):
    authority, ledger = amine_setup(tmp_path)
    bad = TARGET | {"summary": "Drink an extra bottle of water for the heat."}
    gateway = WonderHydrationGateway(ledger, amine_transport(reply(bad)), FakeNotifier())
    with pytest.raises(RecognitionUnavailable):
        gateway.explain_workout(facts(), amine_quote(), "consent")
    [(_, state, _, actual, _)] = attempt_rows(authority)
    assert (state, actual) == ("settled", 6000) and not frozen(authority)
    assert "experiment_output_rejected" in events(authority) and gateway.last_attempt is not None


def test_usage_over_the_reservation_still_freezes(tmp_path):
    authority, ledger = amine_setup(tmp_path)
    gateway = WonderHydrationGateway(ledger, amine_transport(reply(inputs=1_000_000)), FakeNotifier())
    with pytest.raises(RecognitionUnavailable):
        gateway.explain_workout(facts(), amine_quote(), "consent")
    assert frozen(authority)


@pytest.mark.parametrize("setup_changes,make_quote,key", [
    ({"trend_dispatch_reference": None}, amine_quote, None),  # no standing approval
    ({}, lambda: quote(WONDER), None),  # the other account's quote
    ({}, amine_quote, "0" * 64),  # a key the ledger does not name
    ({"baseline": 100_000_000}, amine_quote, None),  # the account cutoff is reached
])
def test_refused_before_reservation_sends_and_freezes_nothing(tmp_path, setup_changes, make_quote, key):
    authority, ledger = amine_setup(tmp_path, **setup_changes)
    transport = amine_transport(reply())
    if key:
        transport.credential_fingerprint = key
    gateway = WonderHydrationGateway(ledger, transport, FakeNotifier())
    with pytest.raises(RecognitionUnavailable):
        gateway.explain_workout(facts(), make_quote(), "consent")
    assert transport.calls == 0 and attempt_rows(authority) == [] and gateway.last_attempt is None
    assert not frozen(authority)


def test_unexplainable_facts_are_refused_before_any_case(tmp_path):
    authority, ledger = amine_setup(tmp_path)
    transport = amine_transport(reply())
    with pytest.raises(RecognitionUnavailable):
        WonderHydrationGateway(ledger, transport, FakeNotifier()).explain_workout(
            facts(samples=[]), amine_quote(), "consent")
    assert transport.calls == 0 and "experiment_case_requested" not in events(authority)


def test_prior_unfinalized_attempt_blocks_the_next_workout(tmp_path):
    _, ledger = amine_setup(tmp_path)
    transport = amine_transport(reply())
    WonderHydrationGateway(ledger, transport, FakeNotifier()).explain_workout(facts(), amine_quote(), "consent")
    with pytest.raises(RecognitionUnavailable):
        WonderHydrationGateway(ledger, transport, FakeNotifier()).explain_workout(facts(duration=90.0), amine_quote(), "c")
    assert transport.calls == 1  # invoice finality for the first attempt is still required


# Replay: saved once per payload, re-validated on every read.

def recorded(tmp_path):
    _, ledger = amine_setup(tmp_path)
    return WonderHydrationGateway(ledger, amine_transport(reply()), FakeNotifier()).explain_workout(
        facts(), amine_quote(), "consent")


@pytest.mark.parametrize("tamper", [
    lambda r: r.update(summary="Drink 2 liters."),
    lambda r: r.update(summary_template="You might be dehydrated."),
    lambda r: r["insights"][0].update(text="Something Hydra did not render."),
    lambda r: r["insights"][0].update(title="Hydration plan"),
    lambda r: r["facts"]["history"].update(typical_duration_minutes=60),
    lambda r: r["provenance"].update(account_id="someone-else"),
    lambda r: r.update(generated_at="2026-10-29T12:00:00"),
    lambda r: r.update(payload_sha256="0" * 64),
    lambda r: r.update(limitations=[]),
    lambda r: r["provider_observations"].update(billed_cost_usd=0.01),
])
def test_tampered_workout_records_are_rejected(tmp_path, tamper):
    result = json.loads(json.dumps(recorded(tmp_path)))
    tamper(result)
    with pytest.raises(ValueError):
        validate_recorded_workout(result)


def test_workout_records_are_write_once_and_kept_apart_from_trends(tmp_path):
    results = tmp_path / "results"
    results.mkdir(mode=0o700)
    result = recorded(tmp_path)
    path = save_result(results, result)
    assert path.name == f"workout-{result['payload_sha256']}.json" and os.stat(path).st_mode & 0o777 == 0o600
    assert load_workout(results, result["payload_sha256"]) == result
    with pytest.raises(FileExistsError):
        save_result(results, result)
    assert latest_trends(results) is None and saved_trends(results) == []
    with pytest.raises(ValueError):
        validate_recorded_trends(result)
    (results / ("workout-" + "e" * 64 + ".json")).write_text(json.dumps(result))
    with pytest.raises(ValueError):  # a saved record only replays for its own payload
        load_workout(results, "e" * 64)


# HTTP: preview what is sent, consent to that exact payload, never pay twice.

def live_body(**changes):
    return body(now=datetime.now(timezone.utc).replace(microsecond=0), **changes)


def consent(view, request):
    return request | {"payload_sha256": view["payload_sha256"], "consent_to_send": True}


PREVIEW, EXPLAIN = "/v1/wonder/workout/preview", "/v1/wonder/workout"


def test_preview_without_live_configuration(tmp_path, client_env):
    request = live_body()
    with TestClient(create_app(tmp_path / "data.sqlite3", TOKEN)) as client:
        view = client.post(PREVIEW, json=request, headers=AUTH)
        assert view.status_code == 200 and view.headers["cache-control"] == "no-store"
        view = view.json()
        assert set(view) == {"version", "facts", "explainable", "payload_sha256", "input_bound_tokens",
                             "worst_case_micro_usd", "live_available", "account_id", "saved"}
        assert view["explainable"] and view["live_available"] is False and view["account_id"] is None
        assert view["saved"] is None and view["facts"]["comparison"]["duration"] == "longer"
        assert view == client.post(PREVIEW, json=request, headers=AUTH).json()  # deterministic
        response = client.post(EXPLAIN, json=consent(view, request), headers=AUTH)
        assert response.status_code == 503 and response.json()["code"] == "wonder_unavailable"


@pytest.mark.parametrize("change", [
    lambda r: r | {"consent_to_send": False}, lambda r: r | {"consent_to_send": 1},
    lambda r: r | {"consent_to_send": "true"}, lambda r: {k: v for k, v in r.items() if k != "consent_to_send"},
    lambda r: r | {"payload_sha256": "xyz"}, lambda r: r | {"calibration_processing_consent": False},
    lambda r: r | {"mode": "synthetic_demo"}, lambda r: r | {"account": "aminealichaouche"},
    lambda r: {k: v for k, v in r.items() if k != "exercise"},
    lambda r: r | {"exercise": r["exercise"] | {"actual": session(1)}},
    lambda r: r | {"timezone": "Not/AZone"},
    lambda r: r | {"samples": [session(-1)]},  # a "previous" session in the future
])
def test_invalid_requests_are_rejected(tmp_path, client_env, change):
    request = live_body()
    with TestClient(create_app(tmp_path / "data.sqlite3", TOKEN)) as client:
        view = client.post(PREVIEW, json=request, headers=AUTH).json()
        response = client.post(EXPLAIN, json=change(consent(view, request)), headers=AUTH)
        assert response.status_code == 422 and response.json()["code"] == "invalid_request"


def test_no_history_of_this_activity_is_not_explainable(tmp_path, client_env):
    request = live_body(samples=[])
    with TestClient(create_app(tmp_path / "data.sqlite3", TOKEN)) as client:
        view = client.post(PREVIEW, json=request, headers=AUTH).json()
        assert view["explainable"] is False and view["payload_sha256"] is None
        response = client.post(EXPLAIN, json=request | {"payload_sha256": "0" * 64, "consent_to_send": True}, headers=AUTH)
        assert response.status_code == 422 and response.json()["code"] == "workout_insufficient_history"


def test_live_request_is_bound_to_the_previewed_payload_and_never_paid_twice(tmp_path, client_env):
    authority, ledger = live_env(client_env, tmp_path)
    app = create_app(tmp_path / "data.sqlite3", TOKEN)
    request = live_body()
    with TestClient(app) as client:
        view = client.post(PREVIEW, json=request, headers=AUTH).json()
        assert view["live_available"] and view["account_id"] == AMINE
        transport = amine_transport(reply())
        fake_live(app, ledger, transport)
        stale = client.post(EXPLAIN, json=consent(view, live_body(duration=90.0)), headers=AUTH)
        assert stale.status_code == 409 and stale.json()["code"] == "workout_preview_stale" and transport.calls == 0
        first = client.post(EXPLAIN, json=consent(view, request), headers=AUTH).json()
        assert (first["replayed"], first["saved"], transport.calls) == (False, True, 1)
        assert first["result"]["summary"].startswith("This workout is longer than your typical run (75 vs 45 minutes)")
        again = client.post(EXPLAIN, json=consent(view, request), headers=AUTH).json()
        assert (again["replayed"], again["result"], transport.calls) == (True, first["result"], 1)
        assert client.post(PREVIEW, json=request, headers=AUTH).json()["saved"] == first["result"]
        consented = [row for row in events(authority) if row == "experiment_case_requested"]
        assert len(consented) == 1


def test_one_request_in_flight_shared_with_trends(tmp_path, client_env):
    _, ledger = live_env(client_env, tmp_path)
    app = create_app(tmp_path / "data.sqlite3", TOKEN)
    request = live_body()
    with TestClient(app) as client:
        transport = amine_transport(reply())
        fake_live(app, ledger, transport)
        view = client.post(PREVIEW, json=request, headers=AUTH).json()
        assert app.state.wonder_lock.acquire(blocking=False)  # e.g. a trend explanation in progress
        try:
            response = client.post(EXPLAIN, json=consent(view, request), headers=AUTH)
        finally:
            app.state.wonder_lock.release()
        assert response.status_code == 409 and response.json()["code"] == "wonder_busy" and transport.calls == 0
        assert response.json()["retryable"] is True


def test_spending_gate_refusal_reports_nothing_sent(tmp_path, client_env):
    _, ledger = live_env(client_env, tmp_path, baseline=100_000_000)
    app = create_app(tmp_path / "data.sqlite3", TOKEN)
    request = live_body()
    with TestClient(app) as client:
        transport = amine_transport()
        fake_live(app, ledger, transport)
        view = client.post(PREVIEW, json=request, headers=AUTH).json()
        response = client.post(EXPLAIN, json=consent(view, request), headers=AUTH)
        assert response.status_code == 409 and response.json()["code"] == "wonder_blocked" and transport.calls == 0


def test_failure_after_reservation_names_the_attempt(tmp_path, client_env):
    authority, ledger = live_env(client_env, tmp_path)
    app = create_app(tmp_path / "data.sqlite3", TOKEN)
    request = live_body()
    with TestClient(app) as client:
        fake_live(app, ledger, amine_transport(fault=TimeoutError()))
        view = client.post(PREVIEW, json=request, headers=AUTH).json()
        response = client.post(EXPLAIN, json=consent(view, request), headers=AUTH)
        assert response.status_code == 502 and response.json()["code"] == "wonder_attempt_unresolved"
        assert response.headers["content-length"] == str(len(response.content))
        assert response.json()["attempt_id"] == attempt_rows(authority)[0][0] and frozen(authority)


def test_rejected_reply_over_http_is_unresolved_without_freezing_or_saving(tmp_path, client_env):
    authority, ledger = live_env(client_env, tmp_path)
    app = create_app(tmp_path / "data.sqlite3", TOKEN)
    request = live_body()
    with TestClient(app) as client:
        fake_live(app, ledger, amine_transport(reply(TARGET | {"summary": "You need to drink more in the heat."})))
        view = client.post(PREVIEW, json=request, headers=AUTH).json()
        response = client.post(EXPLAIN, json=consent(view, request), headers=AUTH)
        assert response.status_code == 502 and response.json()["code"] == "wonder_attempt_unresolved"
        assert not frozen(authority) and client.post(PREVIEW, json=request, headers=AUTH).json()["saved"] is None


def test_export_includes_and_delete_all_removes_saved_workout_explanations(tmp_path, client_env):
    _, ledger = live_env(client_env, tmp_path)
    app = create_app(tmp_path / "data.sqlite3", TOKEN)
    request = live_body()
    with TestClient(app) as client:
        fake_live(app, ledger, amine_transport(reply()))
        view = client.post(PREVIEW, json=request, headers=AUTH).json()
        result = client.post(EXPLAIN, json=consent(view, request), headers=AUTH).json()["result"]
        exported = client.get("/v1/export", headers=AUTH).json()
        assert exported["wonder_workout_explanations"] == [result] and exported["wonder_trends"] == []
        deleted = client.delete("/v1/data", params={"confirm": "delete-all-my-data"}, headers=AUTH).json()
        assert (deleted["deleted_workout_explanations"], deleted["deleted_trend_explanations"]) == (1, 0)
        assert client.post(PREVIEW, json=request, headers=AUTH).json()["saved"] is None
        assert client.get("/v1/export", headers=AUTH).json()["wonder_workout_explanations"] == []


def test_a_full_history_fits_the_workout_forecast_body_limit(tmp_path, client_env):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    padded = ["manual_weigh_in_with_a_long_but_bounded_provenance_label_" + str(n) for n in range(4)]
    samples = [session(day, weighed=day % 2 == 0, now=now) for day in range(1, 33)]
    for sample in samples:
        sample["measurement"]["provenance"] = padded
    request = body(now=now, samples=samples)
    assert len(json.dumps(request)) > 16 * 1024
    with TestClient(create_app(tmp_path / "data.sqlite3", TOKEN)) as client:
        view = client.post(PREVIEW, json=request, headers=AUTH)
        assert view.status_code == 200 and view.json()["facts"]["history"]["sessions"] == 32
        too_many = body(now=now, samples=[session(day, now=now) for day in range(1, 34)])
        assert client.post(PREVIEW, json=too_many, headers=AUTH).status_code == 422


def test_request_models_reuse_the_workout_forecast_shape():
    request = WorkoutExplanationRequest.model_validate(body() | {"payload_sha256": "a" * 64, "consent_to_send": True})
    assert request.mode == "personal" and len(request.samples) == 8
    assert request.exercise.conditions.temperature_c == 31.0
