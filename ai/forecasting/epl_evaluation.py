"""Optional independent EPL experiment; original two-study reproduction is frozen.

Selection uses the existing fixed grouped protocol. Shared session weather is
context only. Reported session duration is a retrospective supplied-condition
assumption, not verified prospectively available planned duration.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from .epl_ingestion import SOURCE
from .grouped_evaluation import grouped_experiment, participant_metrics
from .predict import predict_artifact
from .train import SEED, fit_candidates, validate_records


def _score(artifact: dict, rows: list[dict], radius: float | None = None) -> dict:
    return participant_metrics(rows, [predict_artifact(artifact, row) for row in rows], radius)


def _outside_bounds(artifact: dict, rows: list[dict]) -> list[dict]:
    return [row for row in rows if any(row.get(feature) is not None and not lower <= row[feature] <= upper
            for feature, (lower, upper) in artifact["feature_bounds"].items())]


def evaluate_epl(records: list[dict]) -> tuple[dict, dict]:
    """One predeclared grouped evaluation, then fixed shifted-session diagnostics.

    Diagnostics cannot select a model, calibrate intervals, or change the main
    development/calibration/test assignment. Sessions are not independent studies.
    """
    if (len(records) != 31 or len({row.get("participant_id") for row in records}) != 31
            or any(row.get("study_id") != "epl-v1" or row.get("synthetic") is not False
                   or row.get("target_name") != "intake_corrected_mass_loss_proxy_ml"
                   or row.get("source_sha256") != SOURCE["sha256"] for row in records)
            or Counter(row.get("session_id") for row in records) != {"epl-v1:session-1": 14, "epl-v1:session-2": 17}):
        raise ValueError("epl_study_contract_required")
    validate_records(records)
    provenance = [SOURCE["landing_url"], SOURCE["paper_url"], SOURCE["attribution"],
                  "CC BY 4.0; source_sha256:"+SOURCE["sha256"]]
    artifact, report = grouped_experiment(records, provenance=provenance, seed=SEED, repeats=3, folds=5)
    artifact["model_version"] = "epl-v1-grouped-research-v1"
    report["holdout_origin"] = "new_same_study_participants"
    report["source"] = {key: SOURCE[key] for key in ("landing_url", "paper_url", "license", "attribution", "size_bytes", "sha256")}
    report["source_summary"] = {
        "records": 31, "participants": 31, "sessions": 2, "repeated_participants": 0,
        "target_origin": "derived_from_measured_mass_and_fluid_intake",
        "urine_correction": "protocol_observed_no_urination",
        "individual_measurement_error_bounds": "not_available",
        "prospective_planned_duration_availability": "not_verified; conditional supplied-duration evaluation",
        "environment": "shared_session_context_only; duration/weather/intensity/session confounded",
    }
    report["limitations"] = [
        "First model scores for these prespecified held-out participants; not an external study or clinical validation.",
        "Reported shared session duration is retrospectively supplied; availability as a prospective plan was not established.",
        "Only 31 elite male professional football players in two shared sessions; no repeated-workout or longitudinal personal validation.",
        "Intake-corrected minimal-clothing mass-loss proxy, known no urination; respiratory, metabolic and clothing mass changes unresolved.",
        "Only duration, initial body mass and age enter the fixed models; post mass, intake, GPS, modeled body water and sodium guidance are excluded.",
        "Weather and session intensity are shared and confounded; no learned weather adjustment or causal environmental interpretation.",
        "Six calibration people cannot support a finite nominal 90% conformal interval; empirical envelope only.",
        "Development-only grouped selection and fixed hyperparameters; test and shifted-session outcomes never trigger retuning or reselection.",
        "No pooling with SpectroPhon, QDE or synthetic records; no intake prescription or application serving enabled.",
    ]
    by_id = {row["record_id"]: row for row in records}
    test = [by_id[identifier] for identifier in report["partitions"]["test"]["record_ids"]]
    report["test_session_subgroups"] = {session: _score(artifact, [row for row in test if row["session_id"] == session], artifact["interval"]["radius_ml"])
        for session in ("epl-v1:session-1", "epl-v1:session-2")}
    shifted = {}
    for source, destination in ((1, 2), (2, 1)):
        training = sorted((row for row in records if row["session_id"] == f"epl-v1:session-{source}"), key=lambda row: row["record_id"])
        testing = sorted((row for row in records if row["session_id"] == f"epl-v1:session-{destination}"), key=lambda row: row["record_id"])
        models = fit_candidates(training, provenance=provenance, seed=SEED)
        shifted[f"session-{source}-to-session-{destination}"] = {
            "train_participants": len(training), "test_participants": len(testing),
            "fit_partition_sha256": models["cohort_rate_baseline"]["fit_partition_sha256"],
            "out_of_training_feature_range_participants": len(_outside_bounds(models["cohort_rate_baseline"], testing)),
            "comparison": {name: _score(model, testing) for name, model in models.items()},
            "interval_kind": None, "model_selection": "none; all four fixed candidates reported",
            "interpretation": "Shifted-session sensitivity only; duration, conditions, intensity and participant cohort change together. No causal weather effect, external-study validation, or coverage guarantee.",
        }
    report["shifted_session_audit"] = shifted
    return artifact, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    artifacts = Path(__file__).with_name("artifacts").resolve()
    if output == artifacts or (artifacts in output.parents and output != artifacts/"epl-v1"):
        parser.error("only the separate epl-v1 artifact directory may be written inside existing artifacts")
    artifact, report = evaluate_epl(json.loads(args.records.read_text()))
    output.mkdir(parents=True, exist_ok=True)
    for name, value in (("model.json", artifact), ("evaluation.json", report)):
        (output/name).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+"\n")
    print(json.dumps({"selected_model": report["selected_model"], "test": report["selected_test"],
                      "baseline_test": report["baseline_test"], "promotion_status": report["promotion_status"]}, sort_keys=True))


if __name__ == "__main__":
    main()
