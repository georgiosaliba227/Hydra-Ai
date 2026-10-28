"""Participant-disjoint offline experiments. Never fits on synthetic + real together."""
from __future__ import annotations
import argparse
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import random
from statistics import mean, median

from .predict import predict_artifact

FEATURES = ("duration_minutes", "pre_mass_kg", "age_years")
SEED = 20261028


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def validate_records(records: list[dict]) -> None:
    if not records or len({(r["study_id"], r["target_name"], r["synthetic"]) for r in records}) != 1:
        raise ValueError("one_study_target_and_origin_per_experiment")
    seen = set()
    measured = set()
    for row in records:
        if type(row["synthetic"]) is not bool:
            raise ValueError("invalid_origin")
        if not all(isinstance(row[k], str) and row[k].strip() for k in ("record_id", "participant_id", "study_id", "target_name")):
            raise ValueError("missing_identity_or_target")
        key = (row["study_id"], row["record_id"])
        if key in seen:
            raise ValueError("duplicate_record")
        seen.add(key)
        signature = canonical({k:row.get(k) for k in ("study_id", "target_name", "target_method", *FEATURES, "target_value_ml")})
        if signature in measured:
            raise ValueError("duplicate_measurement_requires_review")
        measured.add(signature)
        for key in (*FEATURES, "target_value_ml"):
            value = row.get(key)
            if value is None and key not in ("duration_minutes", "target_value_ml"):
                continue
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError("invalid_measurement")
        if row["duration_minutes"] <= 0:
            raise ValueError("nonpositive_duration")


def split_participants(records: list[dict], seed: int = SEED) -> dict[str, list[dict]]:
    validate_records(records)
    groups = sorted({r["participant_id"] for r in records})
    if len(groups) < 10:
        raise ValueError("at_least_ten_participants_required")
    random.Random(seed).shuffle(groups)
    n_holdout = max(2, len(groups) // 5)
    assignments = {"test": groups[:n_holdout], "calibration": groups[n_holdout:2*n_holdout],
                   "validation": groups[2*n_holdout:3*n_holdout], "train": groups[3*n_holdout:]}
    return {key: sorted((r for r in records if r["participant_id"] in ids), key=lambda r: r["record_id"])
            for key, ids in assignments.items()}


def _tree(model) -> dict:
    tree = model.tree_
    return {"left": tree.children_left.tolist(), "right": tree.children_right.tolist(),
            "feature": tree.feature.tolist(), "threshold": tree.threshold.tolist(),
            "value": tree.value[:, 0, 0].tolist()}


def metrics(rows: list[dict], predictions: list[float], radius: float | None = None) -> dict:
    if not rows:
        return {"n": 0, "mae_ml": None, "rmse_ml": None, "bias_ml": None, "interval_coverage": None}
    residuals = [p-r["target_value_ml"] for r, p in zip(rows, predictions, strict=True)]
    return {"n": len(rows), "mae_ml": mean(abs(x) for x in residuals),
            "rmse_ml": math.sqrt(mean(x*x for x in residuals)), "bias_ml": mean(residuals),
            "interval_coverage": None if radius is None else mean(abs(x) <= radius for x in residuals)}


def _group_residuals(rows, predictions):
    errors = defaultdict(list)
    for row, prediction in zip(rows, predictions, strict=True):
        errors[row["participant_id"]].append(abs(row["target_value_ml"]-prediction))
    return sorted(max(values) for values in errors.values())


def train_experiment(records: list[dict], *, provenance: list[str], seed: int = SEED) -> tuple[dict, dict]:
    """Select on validation only; calibrate once, evaluate untouched test once."""
    import numpy as np
    import sklearn
    from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
    from sklearn.linear_model import Ridge
    partitions = split_participants(records, seed)
    training = partitions["train"]
    fills = [median([r[f] for r in training if r.get(f) is not None])
             if any(r.get(f) is not None for r in training) else 0.0 for f in FEATURES]
    x_raw = np.array([[r.get(f) if r.get(f) is not None else fills[i] for i, f in enumerate(FEATURES)] for r in training])
    means = x_raw.mean(axis=0)
    scales = x_raw.std(axis=0)
    scales[scales == 0] = 1.0
    x = (x_raw-means)/scales
    y = np.array([r["target_value_ml"] for r in training])
    skeleton = {"schema_version": "offline-forecast-json-v1", "model_version": "workout-research-v1",
                "study_id": records[0]["study_id"], "target_name": records[0]["target_name"],
                "synthetic": records[0]["synthetic"], "features": list(FEATURES), "imputation": fills,
                "means": means.tolist(), "scales": scales.tolist(),
                "feature_bounds": {f: [min(r[f] for r in training if r.get(f) is not None), max(r[f] for r in training if r.get(f) is not None)]
                                   for f in FEATURES if any(r.get(f) is not None for r in training)},
                "provenance": provenance, "seed": seed,
                "dataset_sha256": hashlib.sha256(canonical(sorted(records, key=lambda r:r["record_id"])).encode()).hexdigest(),
                "fit_partition_sha256": hashlib.sha256(canonical(training).encode()).hexdigest(),
                "runtime_use": "synthetic_demo_only" if records[0]["synthetic"] else "offline_research_only",
                "training_versions": {"numpy": np.__version__, "scikit_learn": sklearn.__version__}}
    models = {"cohort_rate_baseline": {"kind": "constant_rate", "rate_ml_per_minute": median(r["target_value_ml"]/r["duration_minutes"] for r in training)}}
    ridge = Ridge(alpha=1.0).fit(x, y)
    models["ridge"] = {"kind": "ridge", "coefficients": ridge.coef_.tolist(), "intercept": float(ridge.intercept_)}
    forest = RandomForestRegressor(n_estimators=32, max_depth=3, min_samples_leaf=3, random_state=seed, n_jobs=1).fit(x, y)
    models["random_forest"] = {"kind": "random_forest", "trees": [_tree(t) for t in forest.estimators_]}
    boosting = GradientBoostingRegressor(n_estimators=40, max_depth=2, min_samples_leaf=3, random_state=seed, loss="squared_error").fit(x, y)
    models["gradient_boosting"] = {"kind": "gradient_boosting", "trees": [_tree(t[0]) for t in boosting.estimators_],
                                  "intercept": float(boosting.init_.constant_[0, 0]), "learning_rate": boosting.learning_rate}
    # Verify JSON export against the fitted implementation for every row and
    # missing-feature probes before publishing any artifact. No scoring here.
    fitted = {"ridge":ridge, "random_forest":forest, "gradient_boosting":boosting}
    parity_rows = records + [{**r,"pre_mass_kg":None,"age_years":None} for r in records]
    for name, estimator in fitted.items():
        probe_x = np.array([[r.get(f) if r.get(f) is not None else fills[i] for i,f in enumerate(FEATURES)] for r in parity_rows])
        standardized = (probe_x-means)/scales
        # Single-row evaluation also matches the serving request shape.
        reference = np.maximum(0.0, np.array([estimator.predict(row.reshape(1,-1))[0] for row in standardized]))
        exported = [predict_artifact(skeleton | {"model":models[name]},r) for r in parity_rows]
        if not np.allclose(reference,exported,rtol=1e-10,atol=1e-8):
            raise ValueError("json_export_prediction_mismatch")
    comparisons = {}
    candidates = {}
    for name, model in models.items():
        artifact = skeleton | {"model": model}
        candidates[name] = artifact
        comparisons[name] = {"validation": metrics(partitions["validation"], [predict_artifact(artifact,r) for r in partitions["validation"]])}
    # Prefer the simpler candidate for an exact tie; no test or synthetic scores enter selection.
    selected_name = min(models, key=lambda name: comparisons[name]["validation"]["mae_ml"])
    artifact = deepcopy(candidates[selected_name])
    calibration = partitions["calibration"]
    scores = _group_residuals(calibration, [predict_artifact(artifact,r) for r in calibration])
    rank = math.ceil((len(scores)+1)*0.90)
    nominal_supported = rank <= len(scores)
    radius = scores[rank-1] if nominal_supported else scores[-1]
    artifact["interval"] = {"kind": "participant_split_conformal" if nominal_supported else "empirical_calibration_envelope",
                            "nominal_coverage": 0.90 if nominal_supported else None,
                            "radius_ml": radius, "calibration_participants": len(scores),
                            "limitation": "Exchangeable participants within this source only; no external-study coverage guarantee."}
    artifact["selected_model"] = selected_name
    for name, candidate in candidates.items():
        comparisons[name]["test"] = metrics(partitions["test"], [predict_artifact(candidate,r) for r in partitions["test"]])
    test_rows = partitions["test"]
    predictions = [predict_artifact(artifact,r) for r in test_rows]
    group_scores = _group_residuals(test_rows, predictions)
    missing = [{**r,"pre_mass_kg":None,"age_years":None} for r in test_rows]
    ood_rows = [r for r in test_rows if any(r.get(f) is not None and not lo <= r[f] <= hi for f,(lo,hi) in artifact["feature_bounds"].items())]
    calibration_curve = []
    for level in (0.5, 0.8, 0.9):
        level_rank = math.ceil((len(scores)+1)*level)
        level_radius = scores[level_rank-1] if level_rank <= len(scores) else None
        calibration_curve.append({"nominal_coverage":level,"radius_ml":level_radius,
            "participant_test_coverage":None if level_radius is None else mean(s<=level_radius for s in group_scores)})
    report = {"study_id": records[0]["study_id"], "target_name": records[0]["target_name"], "synthetic": records[0]["synthetic"],
              "seed": seed, "data_sha256": skeleton["dataset_sha256"], "selected_model": selected_name,
              "selection_rule": "minimum validation MAE; test and calibration excluded from fitting and selection",
              "partitions": {key:{"records":len(rows), "participants": sorted({r["participant_id"] for r in rows}),
                                  "record_ids":[r["record_id"] for r in rows]} for key,rows in partitions.items()},
              "comparison": comparisons, "selected_test": metrics(test_rows,predictions,radius),
              "participant_simultaneous_coverage": mean(s <= radius for s in group_scores),
              "interval": artifact["interval"], "calibration_curve":calibration_curve,
              "json_export_parity": "passed for all source rows and missing-feature probes",
              "missing_mass_and_age_test": metrics(test_rows,[predict_artifact(artifact,r) for r in missing],radius),
              "out_of_training_feature_range_test": metrics(ood_rows,[predict_artifact(artifact,r) for r in ood_rows],radius),
              "temperature_and_intensity_subgroups": "unavailable: source lacks measured environmental/intensity features" if not records[0]["synthetic"] else "synthetic context is intentionally not a physiological predictor",
              "workload_speed_subgroups": {str(speed):metrics([r for r in test_rows if r.get("running_speed_kmh")==speed], [predict_artifact(artifact,r) for r in test_rows if r.get("running_speed_kmh")==speed],radius) for speed in sorted({r["running_speed_kmh"] for r in test_rows if r.get("running_speed_kmh") is not None})},
              "external_study_validation": "unavailable: studies have incompatible protocols/targets; not pooled",
              "existing_deterministic_engine_baseline": {"status":"insufficient_data", "prediction_coverage":0.0,
                 "reason":"No preexisting comparable personal measurements with independently established error bounds; target reconstruction is not forecasting."},
              "limitations": ["Proxy labels are not direct physiological ground truth.", "Held-out participants come from the same study; no clinical validity claim.",
                              "Cohort-rate baseline is an engineering comparator, not the existing personal calibration engine.",
                              "No intake recommendation is produced."]}
    return artifact, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("records", type=Path, help="sanitized JSON list, one study and target only")
    parser.add_argument("output", type=Path)
    parser.add_argument("--provenance", action="append", required=True)
    args = parser.parse_args()
    artifact, report = train_experiment(json.loads(args.records.read_text()),provenance=args.provenance)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/"model.json").write_text(json.dumps(artifact,indent=2,sort_keys=True,allow_nan=False)+"\n")
    (args.output/"evaluation.json").write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+"\n")

if __name__ == "__main__":
    main()
