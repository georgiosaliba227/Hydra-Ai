"""Number ownership, grounded prose, exact payload and immutable score replay."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from uuid import uuid4

import pytest

from backend.hydration_score import build_facts
from backend import wonder_score as wonder
from backend.meta_provider import ProviderReply
from backend.recognition import RecognitionUnavailable
from backend.wonder_hydration import MODEL


def facts():
    return build_facts([], 2000, "UTC", 0, now=datetime(2026, 11, 3, 17, tzinfo=timezone.utc))


def selection(f):
    options = wonder.allowed_texts(f)
    return {"insights": [{"id": name, "text": options[name][0]} for name in wonder.REQUIRED_IDS]}


def reply(value):
    return ProviderReply(200, {"model": MODEL, "status": "completed", "output": [{"type": "message",
        "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": json.dumps(value)}]}]})


def result():
    f = facts()
    return wonder.score_result(f, wonder.parse_explanation(reply(selection(f)), f), account="aminealichaouche",
        attempt_id=str(uuid4()), observations={"latency_ms": 2, "input_tokens": 100, "output_tokens": 100,
        "usage_derived_cost_micro_usd": 20, "billed_cost_usd": None}, generated_at="2026-11-03T17:00:00+00:00")


def test_score_payload_is_exact_and_contains_only_aggregate_allowlist():
    f = facts()
    payload = wonder.score_payload(f)
    assert wonder.facts_from_payload(payload) == f
    assert "consumed_at" not in json.dumps(payload)
    assert "calibration_history" not in json.dumps(payload)
    for mutate in (lambda p: p.update(store=True), lambda p: p.update(stream=0),
                   lambda p: p.update(max_output_tokens=True), lambda p: p.update(extra="prompt")):
        bad = deepcopy(payload)
        mutate(bad)
        with pytest.raises(ValueError):
            wonder.facts_from_payload(bad)
    preview = wonder.preview(f)
    assert preview["worst_case_micro_usd"] <= preview["per_request_cap_micro_usd"]
    assert preview["live_available"] is False


@pytest.mark.parametrize("text", ["Drink more water.", "You reached your goal.", "No records imply no consumption.",
    "Your score is 100.", "Your kidneys are healthy.", "The measurement proves accuracy."])
def test_free_number_free_and_numeric_inventions_are_rejected(text):
    f = facts()
    value = selection(f)
    value["insights"][0]["text"] = text
    with pytest.raises(RecognitionUnavailable):
        wonder.parse_explanation(reply(value), f)


def test_required_components_duplicates_unknown_ids_and_fact_inapplicable_prose_rejected():
    f = facts()
    good = selection(f)
    assert len(wonder.parse_explanation(reply(good), f)["insights"]) == 3
    variants = [deepcopy(good) for _ in range(4)]
    variants[0]["insights"].pop()
    variants[1]["insights"][1] = variants[1]["insights"][0]
    variants[2]["insights"][0]["id"] = "diagnosis"
    positive = build_facts([], 2000, "UTC", 1, now=datetime(2026, 11, 3, tzinfo=timezone.utc))
    variants[3]["insights"][2]["text"] = wonder.allowed_texts(positive)["measurement_support"][0]
    for value in variants:
        with pytest.raises(RecognitionUnavailable):
            wonder.parse_explanation(reply(value), f)


def test_saved_score_revalidates_facts_prose_provenance_and_is_write_once(tmp_path):
    from backend.wonder_results import save_result, load_score, saved_scores, delete_scores
    tmp_path.chmod(0o700)
    r = result()
    target = save_result(tmp_path, r)
    assert target.name == "score-" + r["payload_sha256"] + ".json"
    assert load_score(tmp_path, r["payload_sha256"]) == r
    assert saved_scores(tmp_path) == [r]
    with pytest.raises(FileExistsError):
        save_result(tmp_path, r)
    altered = deepcopy(r)
    altered["insights"][0]["text"] = "You are healthy."
    target.write_text(json.dumps(altered))
    with pytest.raises(ValueError):
        load_score(tmp_path, r["payload_sha256"])
    assert saved_scores(tmp_path) == []
    assert delete_scores(tmp_path) == 1
    assert load_score(tmp_path, r["payload_sha256"]) is None


def test_saved_score_rejects_ambiguous_json_oversize_symlinks_and_nonregular_files(tmp_path):
    from backend.wonder_results import save_result, load_score, MAX_RESULT_BYTES
    tmp_path.chmod(0o700)
    r = result()
    target = save_result(tmp_path, r)
    raw = json.dumps(r)
    target.write_text('{"version":"invented",' + raw[1:])
    with pytest.raises(ValueError):
        load_score(tmp_path, r["payload_sha256"])
    target.write_text(" " * (MAX_RESULT_BYTES + 1))
    with pytest.raises(ValueError):
        load_score(tmp_path, r["payload_sha256"])
    target.unlink()
    other = tmp_path / "other.json"
    other.write_text(raw)
    target.symlink_to(other)
    with pytest.raises((OSError, ValueError)):
        load_score(tmp_path, r["payload_sha256"])
    target.unlink()
    os.mkfifo(target, 0o600)
    with pytest.raises(ValueError):
        load_score(tmp_path, r["payload_sha256"])


def test_shared_native_fixtures_are_reproducible_from_their_exact_inputs():
    from pathlib import Path
    from backend.wonder_results import validate_recorded_score
    root = Path(__file__).parents[1] / "fixtures"
    source = json.loads((root / "hydration-score-inputs-fake.json").read_text())
    preview = json.loads((root / "hydration-score-preview-fake.json").read_text())
    response = json.loads((root / "hydration-score-response-fake.json").read_text())
    # Foundation normalizes the UTC alias to GMT; the shared snapshot uses a
    # stable named zone so native exact timezone binding remains exercised.
    assert source["request"]["timezone"] == "America/New_York"
    native = root.parents[1] / "ios" / "HydraAITests" / "Fixtures"
    for name in ("inputs", "preview", "response"):
        filename = f"hydration-score-{name}-fake.json"
        assert (native / filename).read_bytes() == (root / filename).read_bytes()
    f = build_facts(source["records"], source["goal_ml"], source["request"]["timezone"],
        source["request"]["measurement_count"], now=datetime.fromisoformat(source["now"]))
    assert wonder.preview(f) == preview
    assert response["result"]["facts"] == f and f["score"] == 39
    assert validate_recorded_score(response["result"]) == response["result"]
