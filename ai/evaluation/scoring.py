"""Deterministic scoring only: no model calls, photos, or financial mutations."""
from collections.abc import Callable
import math
import statistics

from backend.recognition import AnalysisResult
from .models import Dataset, EvaluationCase, Observation, ObservationFile, VerifiedEvidence

Verifier = Callable[[EvaluationCase, Observation], VerifiedEvidence]


def ratio(values: list[bool]) -> dict:
    return {"numerator": sum(values), "denominator": len(values),
            "value": sum(values) / len(values) if values else None}


def distribution(values: list[float]) -> dict:
    ordered = sorted(values)
    return {"count": len(values), "mean": statistics.mean(values) if values else None,
            "median": statistics.median(values) if values else None,
            "p95_nearest_rank": ordered[math.ceil(len(values) * .95) - 1] if values else None}


def label(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def camera_gateway_result(raw: dict) -> dict:
    # HTTP API enriches candidates from the reviewed catalogue after the gateway.
    # These are the only fields excluded from the gateway result fingerprint.
    copied = dict(raw)
    if isinstance(copied.get("candidates"), list):
        copied["candidates"] = [{key: value for key, value in item.items() if key != "nutrition"}
                                if isinstance(item, dict) else item for item in copied["candidates"]]
    return copied


def camera_result(raw: dict, mode: str) -> AnalysisResult:
    parsed = AnalysisResult.model_validate(camera_gateway_result(raw), strict=True)
    if parsed.mode != mode:
        raise ValueError("Result mode disagrees with observation")
    return parsed


def hydration_signals(raw: dict, mode: str) -> list[str]:
    from backend.hydration_intelligence import EXPLANATIONS, SyntheticContext
    if set(raw) != {"version", "mode", "provider", "model", "account_id", "attempt_id", "context", "signals",
                    "discarded_signal_count", "explanations", "prediction", "missing_information"}:
        raise ValueError("Hydration result fields do not match the versioned contract")
    if raw.get("version") != "hydration-explanation-v1" or raw.get("mode") != mode or raw.get("prediction") is not None:
        raise ValueError("Invalid hydration result boundary")
    if type(raw["discarded_signal_count"]) is not int or not 0 <= raw["discarded_signal_count"] <= 6:
        raise ValueError("Invalid discarded signal count")
    expected_provider = (None, None, None, None) if mode == "mock" else ("Meta", "muse-spark-1.3", "aminealichaouche", raw["attempt_id"])
    if (raw["provider"], raw["model"], raw["account_id"], raw["attempt_id"]) != expected_provider:
        raise ValueError("Hydration provider provenance disagrees with mode")
    if mode == "meta_live" and not isinstance(raw["attempt_id"], str):
        raise ValueError("Live hydration requires an attempt")
    SyntheticContext.model_validate(raw["context"])
    signals = raw["signals"]
    allowed = {item.value: text for item, text in EXPLANATIONS.items()}
    if (not isinstance(signals, list) or not signals
            or any(not isinstance(item, str) or item not in allowed for item in signals)
            or len(signals) != len(set(signals))):
        raise ValueError("Invalid hydration signals")
    if raw.get("explanations") != [allowed[item] for item in signals]:
        raise ValueError("Hydration explanations differ from reviewed signal text")
    if raw["discarded_signal_count"] + len(signals) > 6:
        raise ValueError("Signal count exceeds the model selection limit")
    return signals


def empty_group() -> dict:
    return {"cases": 0, "successes": 0, "errors": 0, "category_top1": [], "category_topk": [],
            "brand_top1": [], "brand_topk": [], "unknown_category_abstention": [],
            "unknown_brand_abstention": [], "unsupported_capacity_claim": [],
            "capacity_prediction_coverage": [], "capacity_absolute_error_ml": [], "capacity_absolute_percentage_error": [],
            "high_confidence_category_error": [], "signals_precision": [], "required_signal_recall": [],
            "all_required_signals_present": [], "reviewed_explanation_quality": [], "latency_ms": [],
            "raw_signal_supported_fraction": [], "discarded_signal_count": [],
            "hallucinated_identity": [], "invented_nutrition": [], "unsupported_medical_claim": [],
            "unsupported_numerical_recommendation": [], "usage": [], "settled_costs": [], "final_costs": [],
            "accounts": {}, "consistency_groups": {}}


def evaluate(dataset: Dataset, observations: ObservationFile, verifier: Verifier | None = None) -> dict:
    """VerifiedEvidence must come from a trusted reader, never observation JSON."""
    cases = {case.case_id: case for case in dataset.cases}
    groups = {"mock": empty_group(), "meta_live": empty_group()}
    for observation in observations.observations:
        if observation.case_id not in cases:
            raise ValueError("Observation case absent from dataset")
        case = cases[observation.case_id]
        group = groups[observation.mode]
        evidence = None
        if observation.mode == "meta_live":
            if verifier is None or case.input_sha256 is None:
                raise ValueError("Live observations require an exact input and authoritative receipt verifier")
            evidence = VerifiedEvidence.model_validate(verifier(case, observation))
            expected = "georgiosaliba227" if case.purpose == "camera" else "aminealichaouche"
            if evidence.account_id != expected:
                raise ValueError("Workstream account mismatch")
            if case.purpose == "camera" and case.source != "private_owned_input":
                raise ValueError("Real camera evaluation requires a privately owned input record")
        group["cases"] += 1
        group["successes" if observation.outcome == "success" else "errors"] += 1
        latency = evidence.latency_ms if evidence else observation.latency_ms
        if latency is not None:
            group["latency_ms"].append(latency)
        if evidence:
            if evidence.usage is not None:
                group["usage"].append(evidence.usage.model_dump())
            if evidence.settled_cost_micro_usd is not None:
                group["settled_costs"].append(evidence.settled_cost_micro_usd)
            if evidence.final_gross_micro_usd is not None:
                group["final_costs"].append(evidence.final_gross_micro_usd)
            account = group["accounts"].setdefault(evidence.account_id, {"attempts": 0, "usage_settled_cost_micro_usd": 0,
                                                    "settled_cost_count": 0, "invoice_verified_gross_micro_usd": 0, "final_cost_count": 0})
            account["attempts"] += 1
            if evidence.settled_cost_micro_usd is not None:
                account["usage_settled_cost_micro_usd"] += evidence.settled_cost_micro_usd
                account["settled_cost_count"] += 1
            if evidence.final_gross_micro_usd is not None:
                account["invoice_verified_gross_micro_usd"] += evidence.final_gross_micro_usd
                account["final_cost_count"] += 1
        if observation.outcome == "error":
            continue
        if case.purpose == "camera":
            parsed = camera_result(observation.result, observation.mode)
            truth = case.camera
            for field, expected in (("category", truth.categories), ("brand", truth.brands)):
                predicted = [label(getattr(candidate, field)) for candidate in parsed.candidates]
                acceptable = {label(item) for item in expected}
                if acceptable:
                    group[f"{field}_top1"].append(bool(predicted and predicted[0] in acceptable))
                    group[f"{field}_topk"].append(any(item in acceptable for item in predicted))
                else:
                    group[f"unknown_{field}_abstention"].append(not any(predicted))
            first = parsed.candidates[0] if parsed.candidates else None
            capacity = first.container_ml if first else None
            if not truth.capacity_visible:
                group["unsupported_capacity_claim"].append(any(item.container_ml is not None for item in parsed.candidates))
            if truth.container_ml is not None:
                group["capacity_prediction_coverage"].append(capacity is not None)
                if capacity is not None:
                    error = abs(capacity - truth.container_ml)
                    group["capacity_absolute_error_ml"].append(error)
                    group["capacity_absolute_percentage_error"].append(error / truth.container_ml * 100)
            if first and first.confidence == "high" and truth.categories:
                group["high_confidence_category_error"].append(label(first.category) not in {label(item) for item in truth.categories})
        else:
            signals = set(hydration_signals(observation.result, observation.mode))
            truth = case.hydration
            group["signals_precision"].extend(signal in truth.allowed_signals for signal in signals)
            group["required_signal_recall"].extend(signal in signals for signal in truth.required_signals)
            if truth.required_signals:
                group["all_required_signals_present"].append(set(truth.required_signals) <= signals)
            discarded = observation.result["discarded_signal_count"]
            group["discarded_signal_count"].append(discarded)
            group["raw_signal_supported_fraction"].extend([True] * len(signals) + [False] * discarded)
            if truth.consistency_group:
                group["consistency_groups"].setdefault(truth.consistency_group, []).append(signals)
        if observation.human_review:
            review = observation.human_review
            for field in ("hallucinated_identity", "invented_nutrition", "unsupported_medical_claim", "unsupported_numerical_recommendation"):
                value = getattr(review, field)
                if value is not None:
                    group[field].append(value)
            if case.purpose == "hydration" and review.explanation_quality_1_to_5 is not None:
                group["reviewed_explanation_quality"].append(review.explanation_quality_1_to_5)
    report = {"version": "meta-evaluation-report-v1", "dataset_cases": len(cases),
              "observed_cases": len(observations.observations), "not_run_cases": len(cases) - len(observations.observations),
              "modes": {}, "limits": ["Mock scores test the harness, not Meta performance.",
                  "Accuracy denominators use successful identifiable cases; errors and missing runs are reported separately.",
                  "Capacity is container volume, never volume consumed.",
                  "Confidence is uncalibrated; manual hallucination rubrics require explicit review.",
                  "Settled token cost is distinct from independently reviewed final gross billing.",
                  "No population generalization or clinical validation is implied by this small dataset."]}
    rate_fields = ("category_top1", "category_topk", "brand_top1", "brand_topk", "unknown_category_abstention",
                   "unknown_brand_abstention", "unsupported_capacity_claim", "capacity_prediction_coverage",
                   "high_confidence_category_error", "signals_precision", "required_signal_recall", "all_required_signals_present",
                   "raw_signal_supported_fraction",
                   "hallucinated_identity", "invented_nutrition", "unsupported_medical_claim", "unsupported_numerical_recommendation")
    for mode, group in groups.items():
        for account in group["accounts"].values():
            if account["settled_cost_count"] == 0:
                account["usage_settled_cost_micro_usd"] = None
            if account["final_cost_count"] == 0:
                account["invoice_verified_gross_micro_usd"] = None
        consistency = [all(item == sets[0] for item in sets) for sets in group["consistency_groups"].values() if len(sets) > 1]
        result = {"status": "evaluated" if group["cases"] else "not_run", "cases": group["cases"],
                  "successes": group["successes"], "errors": group["errors"],
                  **{name: ratio(group[name]) for name in rate_fields},
                  **{name: distribution(group[name]) for name in ("capacity_absolute_error_ml", "capacity_absolute_percentage_error", "reviewed_explanation_quality", "latency_ms", "discarded_signal_count")},
                  "consistency_groups_exact_match": ratio(consistency),
                  "usage": {"count": len(group["usage"]), "totals": {name: sum(item[name] for item in group["usage"]) for name in ("input_tokens", "output_tokens", "cached_tokens", "total_tokens")} if group["usage"] else None},
                  "usage_settled_cost": {"count": len(group["settled_costs"]), "micro_usd": sum(group["settled_costs"]) if group["settled_costs"] else None},
                  "invoice_verified_gross_cost": {"count": len(group["final_costs"]), "micro_usd": sum(group["final_costs"]) if group["final_costs"] else None},
                  "accounts": group["accounts"]}
        report["modes"][mode] = result
    return report
