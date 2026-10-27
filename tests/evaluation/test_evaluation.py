from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket
import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from ai.evaluation.models import Dataset, ObservationFile, Usage, VerifiedEvidence
from ai.evaluation.scoring import evaluate
from scripts.evaluate_meta import read_json, require_private

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("Offline evaluation attempted networking")
    monkeypatch.setattr(socket, "create_connection", fail)


def fixture_data():
    return (json.loads((ROOT / "evaluation/synthetic-dataset.json").read_text()),
            json.loads((ROOT / "evaluation/synthetic-observations.json").read_text()))


def scored(dataset=None, observations=None, verifier=None):
    default_dataset, default_observations = fixture_data()
    return evaluate(Dataset.model_validate(dataset or default_dataset),
                    ObservationFile.model_validate(observations or default_observations), verifier)


def live_data():
    dataset, observations = fixture_data()
    dataset["cases"] = [dataset["cases"][0]]
    dataset["cases"][0].update(source="private_owned_input", input_sha256="a" * 64)
    observations["observations"] = [observations["observations"][0]]
    observations["observations"][0].update(mode="meta_live", attempt_id="attempt-1", latency_ms=999.0)
    observations["observations"][0]["result"].update(mode="meta_live", recognition_id="attempt-1")
    return dataset, observations


def test_reproducible_fixture_metrics_and_no_real_claims():
    report = scored()
    assert report["not_run_cases"] == 1
    mock = report["modes"]["mock"]
    assert mock["successes"] == 5 and mock["errors"] == 1
    assert mock["category_top1"] == {"numerator": 2, "denominator": 2, "value": 1.0}
    assert mock["brand_top1"]["value"] == .5
    assert mock["brand_topk"]["value"] == 1.0
    assert mock["capacity_absolute_error_ml"]["mean"] == 25
    assert mock["consistency_groups_exact_match"]["value"] == 1.0
    actual = report["modes"]["meta_live"]
    assert actual["status"] == "not_run"
    assert actual["brand_top1"]["value"] is None
    assert actual["usage"]["totals"] is None
    assert actual["usage_settled_cost"]["micro_usd"] is None
    assert "Fixture Fizz" not in json.dumps(report)
    assert report == json.loads((ROOT / "evaluation/synthetic-report.json").read_text())


def test_empty_observations_are_not_perfect_scores():
    report = scored(observations={"observations": []})
    assert report["not_run_cases"] == 7
    assert report["modes"]["mock"]["category_top1"]["value"] is None


def test_claimed_live_mode_requires_authoritative_evidence():
    dataset, observations = live_data()
    with pytest.raises(ValueError):
        scored(dataset, observations)


def test_receipt_usage_and_finality_are_separate_and_observation_latency_untrusted():
    dataset, observations = live_data()
    report = scored(dataset, observations, lambda *_: VerifiedEvidence(
        account_id="georgiosaliba227", usage=Usage(input_tokens=10, output_tokens=2, cached_tokens=0, total_tokens=12),
        settled_cost_micro_usd=21, latency_ms=12.0))
    actual = report["modes"]["meta_live"]
    assert actual["usage"]["totals"]["total_tokens"] == 12
    assert actual["usage_settled_cost"]["micro_usd"] == 21
    assert actual["invoice_verified_gross_cost"]["micro_usd"] is None
    assert actual["latency_ms"]["mean"] == 12


def test_workstream_account_cannot_be_substituted():
    dataset, observations = live_data()
    with pytest.raises(ValueError):
        scored(dataset, observations, lambda *_: VerifiedEvidence(account_id="aminealichaouche"))


@pytest.mark.parametrize("mutation", ["unknown_case", "duplicate_case", "duplicate_observation", "injected_cost", "nan_latency", "false_mode", "invented_numeric_advice"])
def test_untrusted_inputs_fail_closed(mutation):
    dataset, observations = fixture_data()
    if mutation == "unknown_case":
        observations["observations"][0]["case_id"] = "missing"
    elif mutation == "duplicate_case":
        dataset["cases"].append(deepcopy(dataset["cases"][0]))
    elif mutation == "duplicate_observation":
        observations["observations"].append(deepcopy(observations["observations"][0]))
    elif mutation == "injected_cost":
        observations["observations"][0]["actual_cost"] = 0
    elif mutation == "nan_latency":
        observations["observations"][0]["latency_ms"] = float("nan")
    elif mutation == "false_mode":
        observations["observations"][0]["result"]["mode"] = "meta_live"
    else:
        observations["observations"][3]["result"]["explanations"] = ["You are dehydrated. Drink 2000 ml now."]
    with pytest.raises((ValueError, ValidationError)):
        scored(dataset, observations)


def test_unknown_claims_and_missing_capacity_have_correct_denominators():
    dataset, observations = fixture_data()
    observations["observations"][1]["result"]["candidates"] = deepcopy(observations["observations"][0]["result"]["candidates"])
    observations["observations"][0]["result"]["candidates"][0]["container_ml"] = None
    mock = scored(dataset, observations)["modes"]["mock"]
    assert mock["unknown_category_abstention"]["value"] == 0.0
    assert mock["unsupported_capacity_claim"]["value"] == 1.0
    assert mock["capacity_prediction_coverage"]["value"] == .5
    assert mock["capacity_absolute_error_ml"]["count"] == 1


def test_unreviewed_hallucinations_are_unscored():
    mock = scored()["modes"]["mock"]
    assert mock["hallucinated_identity"]["value"] is None
    assert mock["unsupported_medical_claim"]["denominator"] == 2


def test_empty_required_rubric_does_not_create_perfect_coverage():
    dataset, observations = fixture_data()
    for case in dataset["cases"]:
        if case["purpose"] == "hydration":
            case["hydration"]["required_signals"] = []
    result = scored(dataset, observations)["modes"]["mock"]
    assert result["all_required_signals_present"]["value"] is None
    assert result["required_signal_recall"]["value"] is None


def test_blank_ground_truth_alias_is_not_a_valid_label():
    dataset, observations = fixture_data()
    dataset["cases"][0]["camera"]["categories"] = ["  "]
    with pytest.raises(ValueError):
        scored(dataset, observations)


def test_filtered_model_signals_remain_visible_in_metrics():
    dataset, observations = fixture_data()
    observations["observations"][3]["result"]["discarded_signal_count"] = 1
    result = scored(dataset, observations)["modes"]["mock"]
    assert result["signals_precision"]["value"] == 1.0
    assert result["raw_signal_supported_fraction"] == {"numerator": 4, "denominator": 5, "value": .8}
    assert result["discarded_signal_count"]["mean"] == .5


@pytest.mark.parametrize("raw", ['{"a":1,"a":2}', '{"value":NaN}'])
def test_duplicate_and_nonfinite_json_rejected(tmp_path, raw):
    path = tmp_path / "bad.json"
    path.write_text(raw)
    with pytest.raises(ValueError):
        read_json(path)


def test_private_inputs_and_symlinks_rejected(tmp_path):
    path = tmp_path / "data.json"
    path.write_text("{}")
    path.chmod(0o644)
    with pytest.raises(ValueError):
        require_private(path)
    path.chmod(0o600)
    require_private(path)
    link = tmp_path / "link.json"
    link.symlink_to(path)
    with pytest.raises((ValueError, OSError)):
        read_json(link)


def test_inconsistent_usage_rejected():
    with pytest.raises(ValueError):
        Usage(input_tokens=10, output_tokens=2, cached_tokens=11, total_tokens=12)
    with pytest.raises(ValueError):
        Usage(input_tokens=10, output_tokens=2, cached_tokens=0, total_tokens=10)


def test_actual_result_digest_and_transport_required(monkeypatch):
    from ai.evaluation.evidence import ledger_verifier
    dataset, observations = live_data()
    fingerprint = lambda result: hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    receipt = {"attempt_id": "attempt-1", "account_id": "georgiosaliba227", "purpose": "camera", "input_sha256": "a" * 64,
               "model": "muse-spark-1.3", "outcome": "success", "transport_kind": "official_meta_https",
               "result_sha256": fingerprint(observations["observations"][0]["result"]),
               "billing_status": "usage_settled_invoice_pending", "usage": {"input_tokens": 10, "output_tokens": 2, "cached_tokens": 0, "total_tokens": 12},
               "provider_id": "resp_fixture", "usage_cost_micro_usd": 21, "final_gross_micro_usd": None, "api_latency_ms": 10}
    monkeypatch.setitem(sys.modules, "backend.meta_observations", SimpleNamespace(read_observation=lambda *_: receipt, result_fingerprint=fingerprint))
    verify = ledger_verifier(Path("/explicit/synthetic-test.sqlite3"))
    assert scored(dataset, observations, verify)["modes"]["meta_live"]["cases"] == 1
    receipt["transport_kind"] = "injected_test_transport"
    with pytest.raises(ValueError):
        scored(dataset, observations, verify)
    receipt["transport_kind"] = "official_meta_https"
    receipt["result_sha256"] = "b" * 64
    with pytest.raises(ValueError):
        scored(dataset, observations, verify)
