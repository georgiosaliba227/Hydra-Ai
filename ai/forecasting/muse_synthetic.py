"""Muse-guided recipe mixtures, never measured personal history or physiology.

The base experiment is frozen independently of the plan. Only its TRAIN rows
can supply augmentation anchors. Numerical relationships remain the explicitly
assumed simulator, rather than measurements manufactured by a language model.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import math
import random
from typing import Literal

from .ingestion import SOURCES
from .predict import predict_artifact
from .synthetic import generate_scenarios
from .train import FEATURES, canonical, metrics, split_participants, train_experiment, validate_records

PLAN_VERSION = "muse-synthetic-plan-v1"
VERSION = "muse-guided-synthetic-training-v1"
STUDY = "muse-guided-synthetic-v1"
TARGET = "simulated_exercise_loss_proxy_ml"
BASE_SEED = 20261103
SPLIT_SEED = 20261103
AUGMENT_SEED = 20261104
RECIPES = ("base", "missing_covariates", "wide_noise", "outlier")
DURATIONS = (30.0, 45.0, 60.0, 90.0, 120.0)
LIMITATIONS = [
    "Muse selects a simulation mixture; Hydra generates every numerical label under declared assumptions.",
    "Study mass-loss proxy rates are reinterpreted as duration-linear simulated loss, not validated physiological truth.",
    "Noise, missingness and contamination are software stress settings, not measured instrument accuracy or population distributions.",
    "Exact duplicate training vectors are deterministically resampled and counted; simulated clones are not independent observations.",
    "Anchor-group holdouts are simulated clones of real TRAIN anchors, not independent people or real measured validation.",
    "Synthetic interval coverage and model gains cannot establish accuracy for a real person.",
    "Weather, humidity, intensity, HR, HRV, caffeine and creatine have no numerical effect.",
    "This artifact is offline research only, never a personal calibration history or drinking prescription.",
]


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def validate_plan(plan: dict) -> dict:
    if (not isinstance(plan, dict) or set(plan) != {"version", "training_weights"}
            or plan["version"] != PLAN_VERSION or not isinstance(plan["training_weights"], dict)
            or set(plan["training_weights"]) != set(RECIPES)
            or any(type(value) is not int or value not in (1, 2) for value in plan["training_weights"].values())):
        raise ValueError("Invalid bounded Muse simulation plan")
    return {"version": PLAN_VERSION, "training_weights": {key: plan["training_weights"][key] for key in RECIPES}}


def _public_source(records: list[dict]) -> list[dict]:
    if not isinstance(records, list) or not records or any(row.get("synthetic") is not False for row in records):
        raise ValueError("Public real-study inventory required")
    selected = sorted((deepcopy(row) for row in records if row.get("study_id") == "spectrophon-v1"),
                      key=lambda row: row["record_id"])
    validate_records(selected)
    for row in selected:
        if (row["target_name"] != "corrected_mass_loss_proxy_ml"
                or row.get("source_sha256") != SOURCES["spectrophon"]["sha256"]
                or row.get("source_license") != SOURCES["spectrophon"]["license"]
                or any(type(row.get(key)) not in (int, float) or not math.isfinite(row[key])
                       or row[key] <= 0 for key in ("pre_mass_kg", "age_years"))):
            raise ValueError("Attributed SpectroPhon source schema required")
    return selected


def _partition_manifest(rows: list[dict]) -> dict:
    return {name: {"record_count": len(part), "anchor_group_count": len({r["participant_id"] for r in part}),
                   "record_ids": [r["record_id"] for r in part],
                   "participant_ids": sorted({r["participant_id"] for r in part}),
                   "records_sha256": digest(part)}
            for name, part in split_participants(rows, seed=SPLIT_SEED).items()}


def prepare_base(real_records: list[dict]) -> dict:
    """No plan argument exists here: base records and all holdouts freeze first."""
    selected = _public_source(real_records)
    source_train = split_participants(selected)["train"]
    rows = generate_scenarios(selected, seed=BASE_SEED, participants=240)
    for row in rows:
        row["record_id"] = "muse-base:" + row["record_id"]
        row.update(study_id=STUDY, target_name=TARGET, target_method="fixed_synthetic_mass_balance_v1",
                   simulation_recipe="frozen_base", evidence_origin="fixed_base_simulation")
        measurement = row["simulated_measurement"]
        source_group = row["participant_id"].removeprefix("synthetic:")
        rate = measurement["latent_loss_ml"] / row["duration_minutes"]
        matching = [r for r in source_train if r["participant_id"] == source_group
                    and r["pre_mass_kg"] == measurement["pre_mass_kg"]
                    and math.isclose(r["target_value_ml"] / r["duration_minutes"], rate, rel_tol=1e-12, abs_tol=1e-12)]
        if not matching:
            raise ValueError("Synthetic source-anchor linkage unavailable")
        measurement["anchor_rate_ml_per_minute"] = matching[0]["target_value_ml"] / matching[0]["duration_minutes"]
        measurement["anchor_age_years"] = matching[0]["age_years"]
    validate_records(rows)
    manifest = {"version": VERSION, "study_id": STUDY, "target_name": TARGET, "synthetic": True,
        "base_seed": BASE_SEED, "split_seed": SPLIT_SEED, "simulated_profiles": 240,
        "source_study_id": "spectrophon-v1", "source_records_sha256": digest(selected),
        "source_train_sha256": digest(source_train), "base_records_sha256": digest(rows),
        "base_record_count": len(rows), "partitions": _partition_manifest(rows),
        "preparation": "base_and_holdout_hashes_frozen_before_plan_is_read"}
    # Corruption detection only; a self-hash is not authentication of a source.
    manifest["manifest_sha256"] = digest(manifest)
    return {"records": rows, "split_manifest": manifest}


def _validate_base_measurement(row: dict, source_train_sha256: str) -> None:
    measurement = row["simulated_measurement"]
    if set(measurement) != {"pre_mass_kg", "post_mass_kg", "consumed_ml", "urine_ml",
            "latent_loss_ml", "noise_bound_ml", "anchor_rate_ml_per_minute", "anchor_age_years"}:
        raise ValueError
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in measurement.values()):
        raise ValueError
    reconstructed = ((measurement["pre_mass_kg"] - measurement["post_mass_kg"]) * 1000
                     + measurement["consumed_ml"] - measurement["urine_ml"])
    if (measurement["pre_mass_kg"] <= 0 or measurement["post_mass_kg"] <= 0
            or measurement["anchor_age_years"] <= 0 or measurement["anchor_rate_ml_per_minute"] < 0
            or measurement["consumed_ml"] not in (0.0, 150.0, 300.0) or measurement["urine_ml"] != 0.0
            or row["duration_minutes"] not in DURATIONS or measurement["noise_bound_ml"] != 40.0
            or abs(row["target_value_ml"] - measurement["latent_loss_ml"]) > 40.0 + 1e-8
            or not math.isclose(reconstructed, row["target_value_ml"], rel_tol=1e-12, abs_tol=1e-8)
            or not math.isclose(measurement["latent_loss_ml"],
                measurement["anchor_rate_ml_per_minute"] * row["duration_minutes"], rel_tol=1e-12, abs_tol=1e-8)
            or row["pre_mass_kg"] not in (None, measurement["pre_mass_kg"])
            or row["age_years"] not in (None, measurement["anchor_age_years"])
            or row["source_train_sha256"] != source_train_sha256
            or not row["participant_id"].startswith("synthetic:spectrophon-v1:")
            or row["target_method"] != "fixed_synthetic_mass_balance_v1"
            or row["evidence_origin"] != "fixed_base_simulation"):
        raise ValueError


def validate_prepared(prepared: dict) -> None:
    try:
        if set(prepared) != {"records", "split_manifest"}:
            raise ValueError
        rows, manifest = prepared["records"], prepared["split_manifest"]
        validate_records(rows)
        if (set(manifest) != {"version", "study_id", "target_name", "synthetic", "base_seed", "split_seed",
                "simulated_profiles", "source_study_id", "source_records_sha256", "source_train_sha256",
                "base_records_sha256", "base_record_count", "partitions", "preparation", "manifest_sha256"}
                or manifest["manifest_sha256"] != digest({k:v for k,v in manifest.items() if k != "manifest_sha256"})
                or any(not isinstance(manifest[key], str) or len(manifest[key]) != 64
                    or any(c not in "0123456789abcdef" for c in manifest[key])
                    for key in ("source_records_sha256", "source_train_sha256"))
                or manifest["source_study_id"] != "spectrophon-v1"
                or manifest["preparation"] != "base_and_holdout_hashes_frozen_before_plan_is_read"
                or manifest["version"] != VERSION or manifest["study_id"] != STUDY
                or manifest["target_name"] != TARGET or manifest["synthetic"] is not True
                or manifest["base_seed"] != BASE_SEED or manifest["split_seed"] != SPLIT_SEED
                or manifest["simulated_profiles"] != 240 or manifest["base_record_count"] != 960
                or len(rows) != 960 or manifest["base_records_sha256"] != digest(rows)
                or manifest["partitions"] != _partition_manifest(rows)
                or any(row["study_id"] != STUDY or row["target_name"] != TARGET
                       or row["synthetic"] is not True or row["simulation_recipe"] != "frozen_base" for row in rows)):
            raise ValueError
        for row in rows:
            _validate_base_measurement(row, manifest["source_train_sha256"])
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError("Prepared base or frozen holdout hashes changed") from None


def _simulated_row(anchor: dict, *, record_id: str, duration: float, noise: float,
                   bound: float, consumed: float, missing_mass: bool, missing_age: bool) -> dict:
    measurement = anchor["simulated_measurement"]
    rate = measurement["anchor_rate_ml_per_minute"]
    latent = rate * duration
    observed = max(0.0, latent + noise)
    pre = measurement["pre_mass_kg"]
    post = pre + (consumed-observed)/1000.0
    if not all(math.isfinite(value) for value in (rate, latent, observed, pre, post, noise, bound)) or post <= 0:
        raise ValueError("Invalid simulated mass-balance measurement")
    row = deepcopy(anchor)
    row.update(record_id=record_id, scenario_user_id=record_id, duration_minutes=duration,
               target_value_ml=observed, pre_mass_kg=None if missing_mass else pre,
               age_years=None if missing_age else measurement["anchor_age_years"])
    row["simulated_measurement"] = {"pre_mass_kg": pre, "post_mass_kg": post,
        "consumed_ml": consumed, "urine_ml": 0.0, "latent_loss_ml": latent, "noise_bound_ml": bound,
        "realized_observation_deviation_ml": observed-latent, "lower_clip_applied": latent+noise < 0,
        "anchor_rate_ml_per_minute": rate, "anchor_age_years": measurement["anchor_age_years"]}
    return row


def augment_training(prepared: dict, plan: dict, *, plan_origin: str = "unverified_plan") -> list[dict]:
    validate_prepared(prepared)
    plan = validate_plan(plan)
    if plan_origin not in ("unverified_plan", "offline_stub", "muse_wonder"):
        raise ValueError("Invalid simulation-plan origin")
    base = deepcopy(prepared["records"])
    parts = split_participants(base, seed=SPLIT_SEED)
    training = parts["train"]
    added = []
    def learning_key(row):
        return canonical({key: row.get(key) for key in (*FEATURES, "target_value_ml")})
    # Duplicate screening is training-only too. Consulting a held-out target
    # even just to resample an exact collision would influence the training set.
    seen = {learning_key(row) for row in training}
    for recipe_index, recipe in enumerate(RECIPES):
        for block in range(plan["training_weights"][recipe]):
            rng = random.Random(AUGMENT_SEED + 10007 * recipe_index + block)
            for index in range(len(training)):
                # Clipping plus missing covariates can create identical vectors.
                # Do not hide duplicates under new IDs or invent tiny jitter.
                for rejected in range(128):
                    anchor = rng.choice(training)
                    duration, consumed = rng.choice(DURATIONS), rng.choice((0.0, 150.0, 300.0))
                    amplitude = 150.0 if recipe == "wide_noise" else 40.0
                    contamination = 500.0 if recipe == "outlier" and index % 4 == 3 else 0.0
                    noise = rng.uniform(-amplitude, amplitude) + contamination
                    missing_probability = 0.5 if recipe == "missing_covariates" else 0.1
                    row = _simulated_row(anchor, record_id=f"muse-aug:{recipe}:{block}:{index:04}",
                        duration=duration, noise=noise, bound=amplitude+contamination, consumed=consumed,
                        missing_mass=rng.random() < missing_probability, missing_age=rng.random() < missing_probability)
                    key = learning_key(row)
                    if key not in seen:
                        seen.add(key)
                        break
                else:
                    raise ValueError("Simulation could not produce unique training vectors")
                row.update(simulation_recipe=recipe, evidence_origin="plan_guided_simulation",
                    plan_origin=plan_origin, plan_sha256=digest(plan), source_base_record_id=anchor["record_id"],
                    duplicate_candidates_rejected=rejected,
                    target_method="muse_recipe_synthetic_mass_balance_v1")
                added.append(row)
    combined = base + added
    validate_records(combined)
    after = split_participants(combined, seed=SPLIT_SEED)
    for name in ("validation", "calibration", "test"):
        if canonical(parts[name]) != canonical(after[name]):
            raise ValueError("Augmentation changed a frozen holdout")
    return combined


def _plan_source(record: dict, origin: str, authority) -> tuple[dict, dict]:
    if origin == "offline_stub":
        plan = validate_plan(record)
        return plan, {"plan_origin": origin, "plan_sha256": digest(plan), "muse_inference_used": False}
    if origin != "muse_wonder":
        raise ValueError("Invalid explicit plan origin")
    # Importing the financial verifier is deliberate and limited to a claimed
    # live plan. Offline training has no financial-library or ledger access.
    from backend.wonder_personal_owner_policy import OwnerPersonalAuthority
    if type(authority) is not OwnerPersonalAuthority:
        raise ValueError("Verified financial authority required for a Muse-generated plan")
    copied = deepcopy(record)
    authority.verify_training_plan_record(copied)
    plan = validate_plan(copied["plan"])
    return plan, {"plan_origin": origin, "plan_sha256": digest(plan), "muse_inference_used": True,
        "model": "muse-wonder-1.0", "verified_plan_record_sha256": digest(copied),
        "verification": "existing_authoritative_ledger_read_only_attempt_purpose_payload_and_output_digest"}


def _stress_tests(artifact: dict, rows: list[dict]) -> dict:
    rng = random.Random(20261105)
    suites = {}
    suites["missing_covariates"] = [{**deepcopy(r), "pre_mass_kg": None, "age_years": None} for r in rows]
    for recipe in ("wide_noise", "outlier", "short_duration", "long_duration"):
        generated = []
        for index, r in enumerate(rows):
            amplitude = 150.0 if recipe == "wide_noise" else 40.0
            contamination = 500.0 if recipe == "outlier" and index % 4 == 3 else 0.0
            duration = 15.0 if recipe == "short_duration" else 180.0 if recipe == "long_duration" else r["duration_minutes"]
            generated.append(_simulated_row(r, record_id=f"stress:{recipe}:{index:04}", duration=duration,
                noise=rng.uniform(-amplitude, amplitude)+contamination, bound=amplitude+contamination,
                consumed=r["simulated_measurement"]["consumed_ml"], missing_mass=r["pre_mass_kg"] is None,
                missing_age=r["age_years"] is None))
        suites[recipe] = generated
    suites["context_only_shift"] = [{**deepcopy(r), "temperature_c": 30.0, "humidity_percent": 75.0,
                                      "intensity": "high"} for r in rows]
    radius = artifact["interval"]["radius_ml"]
    output = {name: metrics(group, [predict_artifact(artifact, r) for r in group], radius)
              for name, group in suites.items()}
    output["context_only_shift"]["maximum_prediction_change_ml"] = max(
        abs(predict_artifact(artifact, original)-predict_artifact(artifact, changed))
        for original, changed in zip(rows, suites["context_only_shift"], strict=True))
    return output


def train_prepared(prepared: dict, plan_record: dict, *, plan_origin: Literal["offline_stub", "muse_wonder"],
                   authority=None) -> dict:
    """Fit only after validating the existing frozen manifest and plan provenance."""
    validate_prepared(prepared)
    plan, provenance = _plan_source(plan_record, plan_origin, authority)
    combined = augment_training(prepared, plan, plan_origin=plan_origin)
    attribution = ["Muse-guided synthetic exercise-loss proxies; no personal or physiological validation",
        SOURCES["spectrophon"]["url"], SOURCES["spectrophon"]["license"],
        "source_train_sha256:" + prepared["split_manifest"]["source_train_sha256"],
        "plan_origin:" + plan_origin, "plan_sha256:" + digest(plan)]
    # Identical participant sets preserve the exact pre-plan holdout assignment.
    model, guided = train_experiment(combined, provenance=attribution, seed=SPLIT_SEED)
    control_model, control = train_experiment(prepared["records"], provenance=attribution, seed=SPLIT_SEED)
    model.update(model_version=VERSION, runtime_use="offline_research_only", plan_origin=plan_origin,
        plan_provenance=provenance, simulation_protocol=VERSION,
        frozen_split_manifest_sha256=digest(prepared["split_manifest"]))
    test = split_participants(prepared["records"], seed=SPLIT_SEED)["test"]
    latent = [{**r, "target_value_ml": r["simulated_measurement"]["latent_loss_ml"]} for r in test]
    oracle = [r["simulated_measurement"]["latent_loss_ml"] for r in test]
    report = {"version": VERSION, "study_id": STUDY, "target_name": TARGET, "synthetic": True,
        **provenance, "plan": plan, "frozen_holdouts_unchanged": True,
        "frozen_split_manifest_sha256": digest(prepared["split_manifest"]),
        "holdout_hashes_before_plan": {key: value["records_sha256"]
            for key, value in prepared["split_manifest"]["partitions"].items() if key != "train"},
        "base_record_count": len(prepared["records"]), "augmented_record_count": len(combined)-len(prepared["records"]),
        "total_records": len(combined), "selected_model": model["selected_model"],
        "control_selected_model": control_model["selected_model"],
        "control_test": control["selected_test"], "guided_test": guided["selected_test"],
        "guided_minus_control_mae_ml": guided["selected_test"]["mae_ml"]-control["selected_test"]["mae_ml"],
        "comparison": guided["comparison"], "interval": guided["interval"],
        "stress_tests": _stress_tests(model, test),
        "privileged_oracle": {"available_to_unseen_real_user": False,
            "latent_target": metrics(latent, oracle), "observed_noisy_target": metrics(test, oracle)},
        "existing_personal_application_baseline": {"cold_start_status": "insufficient_data",
            "prediction_coverage_without_measured_history": 0.0, "mae_ml": None},
        "real_world_improvement_established": False, "personal_serving_promotion": False,
        "clipped_augmented_labels": sum(r["simulated_measurement"].get("lower_clip_applied", False)
            for r in combined[len(prepared["records"]):]),
        "duplicate_augmentation_candidates_rejected": sum(r["duplicate_candidates_rejected"]
            for r in combined[len(prepared["records"]):]),
        "limitations": list(LIMITATIONS), "guided_experiment": guided, "control_experiment": control}
    return {"records": combined, "model": model, "evaluation": report,
        "split_manifest": deepcopy(prepared["split_manifest"]), "plan_provenance": provenance}
