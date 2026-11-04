"""Versioned, development-only grouped selection; frozen v1 artifacts stay intact.

This is offline research on separate study-specific mass-loss proxy targets.
It does not make the real research models eligible for application serving.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
import json
import math
from pathlib import Path
import random
from statistics import mean, stdev

from .predict import predict_artifact
from .reproduce import SOURCES
from .train import SEED, fit_candidates, metrics, split_participants, validate_records

BASELINE = "cohort_rate_baseline"
MODEL_ORDER = (BASELINE, "ridge", "random_forest", "gradient_boosting")


def development_folds(records: list[dict], *, seed: int = SEED, repeats: int = 3,
                      folds: int = 5) -> list[dict]:
    """Each participant is validation once per repeat; preprocessing fits later."""
    validate_records(records)
    groups = sorted({row["participant_id"] for row in records})
    if type(repeats) is not int or not 1 <= repeats <= 10 or type(folds) is not int or not 2 <= folds <= 10:
        raise ValueError("invalid_grouped_validation_design")
    if len(groups) < 3:
        raise ValueError("at_least_three_development_participants_required")
    count = min(folds, len(groups))
    result = []
    for repeat in range(repeats):
        shuffled = groups.copy()
        random.Random(seed + repeat).shuffle(shuffled)
        for fold in range(count):
            heldout = set(shuffled[fold::count])
            result.append({"repeat": repeat, "fold": fold,
                "train": sorted((r for r in records if r["participant_id"] not in heldout), key=lambda r: r["record_id"]),
                "validation": sorted((r for r in records if r["participant_id"] in heldout), key=lambda r: r["record_id"])})
    return result


def _participant_errors(rows: list[dict], predictions: list[float]) -> dict[str, list[float]]:
    grouped = defaultdict(list)
    for row, prediction in zip(rows, predictions, strict=True):
        grouped[row["participant_id"]].append(abs(prediction - row["target_value_ml"]))
    return grouped


def participant_metrics(rows: list[dict], predictions: list[float], radius: float | None = None) -> dict:
    """Report row metrics and equal-participant mean absolute error separately."""
    grouped = _participant_errors(rows, predictions)
    return metrics(rows, predictions, radius) | {
        "participants": len(grouped),
        "participant_mae_ml": mean(mean(errors) for errors in grouped.values()) if grouped else None,
        "participant_simultaneous_coverage": (
            mean(max(errors) <= radius for errors in grouped.values()) if grouped and radius is not None else None),
    }


def select_candidate(participant_errors: dict[str, dict[str, float]]) -> tuple[str, dict]:
    """Require paired gain > one SE across people before preferring complexity.

    Repeated folds are averaged within each person first. This is a conservative
    engineering rule, not a confidence interval, hypothesis test, or proof of
    generalization. Fold fits overlap, and participant errors remain dependent.
    """
    baseline = participant_errors[BASELINE]
    if len(baseline) < 2:
        raise ValueError("at_least_two_validation_participants_required")
    if any(set(errors) != set(baseline) or any(not math.isfinite(value) or value < 0 for value in errors.values())
           for errors in participant_errors.values()):
        raise ValueError("unaligned_or_invalid_participant_errors")
    evidence = {}
    for name in MODEL_ORDER:
        if name not in participant_errors:
            continue
        errors = participant_errors[name]
        gains = [baseline[pid] - errors[pid] for pid in sorted(baseline)]
        gain = mean(gains)
        standard_error = stdev(gains) / math.sqrt(len(gains))
        evidence[name] = {"participant_mae_ml": mean(errors.values()), "paired_gain_ml": gain,
            "gain_standard_error_ml": standard_error, "eligible": name == BASELINE or gain > standard_error}
    selected = min((name for name in evidence if evidence[name]["eligible"]),
                   key=lambda name: evidence[name]["participant_mae_ml"])
    return selected, evidence


def _predictions(artifact: dict, rows: list[dict]) -> list[float]:
    return [predict_artifact(artifact, row) for row in rows]


def grouped_experiment(records: list[dict], *, provenance: list[str], seed: int = SEED,
                       repeats: int = 3, folds: int = 5) -> tuple[dict, dict]:
    """Reuse the historical holdouts; do not choose or refit after test scoring."""
    partitions = split_participants(records, seed)
    development = sorted(partitions["train"] + partitions["validation"], key=lambda r: r["record_id"])
    per_participant = {name: defaultdict(list) for name in MODEL_ORDER}
    fold_reports = []
    for fold in development_folds(development, seed=seed, repeats=repeats, folds=folds):
        models = fit_candidates(fold["train"], provenance=provenance, seed=seed)
        comparison = {}
        for name, artifact in models.items():
            predictions = _predictions(artifact, fold["validation"])
            comparison[name] = participant_metrics(fold["validation"], predictions)
            for pid, errors in _participant_errors(fold["validation"], predictions).items():
                per_participant[name][pid].append(mean(errors))
        fold_reports.append({"repeat": fold["repeat"], "fold": fold["fold"],
            "training_participants": sorted({r["participant_id"] for r in fold["train"]}),
            "validation_participants": sorted({r["participant_id"] for r in fold["validation"]}),
            "fit_partition_sha256": models[BASELINE]["fit_partition_sha256"], "comparison": comparison})
    selected, evidence = select_candidate({name: {pid: mean(errors) for pid, errors in people.items()}
                                          for name, people in per_participant.items()})
    # Only after the development-only decision: refit on development, calibrate,
    # then score the fixed historical test. No test outcome triggers reselection.
    candidates = fit_candidates(development, provenance=provenance, seed=seed, audit_records=records)
    artifact = deepcopy(candidates[selected])
    artifact["model_version"] = records[0]["study_id"] + "-grouped-research-v2"
    artifact["selected_model"] = selected
    artifact["selection_protocol"] = "repeated-grouped-paired-gain-one-se-v2"
    calibration = partitions["calibration"]
    scores = sorted(max(errors) for errors in _participant_errors(calibration, _predictions(artifact, calibration)).values())
    rank = math.ceil((len(scores) + 1) * .9)
    supported = rank <= len(scores)
    radius = scores[rank - 1] if supported else scores[-1]
    artifact["interval"] = {
        "kind": "participant_split_conformal" if supported else "empirical_calibration_envelope",
        "nominal_coverage": .9 if supported else None, "radius_ml": radius,
        "calibration_participants": len(scores),
        "limitation": "Same-source exchangeable participant groups only; no external or clinical coverage guarantee.",
    }
    test = partitions["test"]
    predictions = _predictions(artifact, test)
    selected_test = participant_metrics(test, predictions, radius)
    baseline_test = participant_metrics(test, _predictions(candidates[BASELINE], test))
    missing = [{**row, "pre_mass_kg": None, "age_years": None} for row in test]
    ood = [row for row in test if any(row.get(feature) is not None and not lower <= row[feature] <= upper
           for feature, (lower, upper) in artifact["feature_bounds"].items())]
    curve = []
    for level in (.5, .8, .9):
        level_rank = math.ceil((len(scores) + 1) * level)
        level_radius = scores[level_rank - 1] if level_rank <= len(scores) else None
        curve.append({"nominal_coverage": level, "radius_ml": level_radius,
            "test": participant_metrics(test, predictions, level_radius)})
    report = {
        "protocol_version": "grouped-proxy-evaluation-v2", "seed": seed,
        "study_id": records[0]["study_id"], "target_name": records[0]["target_name"],
        "synthetic": records[0]["synthetic"], "data_sha256": artifact["dataset_sha256"],
        "selected_model": selected,
        "selection": {"rule": "lowest participant MAE among candidates with mean paired gain over baseline greater than one participant-level SE; ties prefer simplicity",
            "repeats": repeats, "folds_per_repeat": min(folds, len(per_participant[BASELINE])),
            "participants": len(per_participant[BASELINE]), "evidence": evidence,
            "limitation": "One-SE heuristic; repeated overlapping fits are not independent evidence or a significance test."},
        "folds": fold_reports,
        "partitions": {name: {"records": len(rows), "participants": sorted({r["participant_id"] for r in rows}),
            "record_ids": [r["record_id"] for r in rows]}
            for name, rows in {"development": development, "calibration": calibration, "test": test}.items()},
        "interval": artifact["interval"], "calibration_curve": curve,
        "selected_test": selected_test, "baseline_test": baseline_test,
        "promotion_status": "offline_only_baseline_retained" if selected == BASELINE or selected_test["participant_mae_ml"] >= baseline_test["participant_mae_ml"] else "offline_only_independent_validation_required",
        "missing_mass_and_age_test": participant_metrics(missing, _predictions(artifact, missing), radius),
        "missing_input_tests": {feature: participant_metrics(test, _predictions(artifact, [{**row, feature: None} for row in test]), radius)
                                for feature in ("pre_mass_kg", "age_years")},
        "out_of_training_feature_range_test": participant_metrics(ood, _predictions(artifact, ood), radius),
        "workload_speed_subgroups": {str(speed): participant_metrics(
            [row for row in test if row.get("running_speed_kmh") == speed],
            _predictions(artifact, [row for row in test if row.get("running_speed_kmh") == speed]), radius)
            for speed in sorted({row["running_speed_kmh"] for row in test if row.get("running_speed_kmh") is not None})},
        "input_perturbation_sensitivity": {
            "description": "Software-only +/-1 kg mass and +/-1 year age probes; not measured sensor error or physiological counterfactual accuracy.",
            "maximum_prediction_shift_ml": max(abs(predict_artifact(artifact, {**row,
                feature: row[feature] + delta}) - prediction)
                for row, prediction in zip(test, predictions, strict=True)
                for feature in ("pre_mass_kg", "age_years") if row.get(feature) is not None for delta in (-1., 1.))
                if any(row.get(feature) is not None for row in test for feature in ("pre_mass_kg", "age_years")) else None},
        "limitations": [
            "Historical test outcomes were already published before this protocol; this is an audit, not a new untouched confirmatory study.",
            "No hyperparameter search or test-based reselection; calibration and test are excluded from fitting and grouped selection.",
            "Measured labels are study-specific body-mass-loss proxies, not pure sweat, total hydration, or intake requirements.",
            "No external-study validation: incompatible protocols and targets are not pooled.",
            "Temperature, humidity and relative intensity lack real measurements; no learned adjustment or stratified claim.",
            "Synthetic rows are absent from the real experiments; neither real model is enabled for application serving.",
        ],
    }
    return artifact, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="versioned output directory; do not overwrite frozen v1 artifacts")
    args = parser.parse_args()
    frozen = Path(__file__).with_name("artifacts").resolve()
    if args.output.resolve() == frozen:
        parser.error("use a versioned output directory; frozen v1 artifacts must be preserved")
    records = json.loads(args.records.read_text())
    reports = {}
    args.output.mkdir(parents=True, exist_ok=True)
    for study, sources in SOURCES.items():
        rows = [row for row in records if row["study_id"] == study]
        provenance = sources + sorted({"source_sha256:" + row["source_sha256"] for row in rows})
        artifact, report = grouped_experiment(rows, provenance=provenance)
        (args.output / (study + ".json")).write_text(json.dumps(artifact, indent=2, sort_keys=True, allow_nan=False) + "\n")
        reports[study] = report
    (args.output / "evaluation.json").write_text(json.dumps(reports, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({study: {"selected_model": report["selected_model"], "test": report["selected_test"],
                             "promotion_status": report["promotion_status"]} for study, report in reports.items()}, sort_keys=True))


if __name__ == "__main__":
    main()
