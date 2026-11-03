"""Invented source-shaped fixtures test software, never real or Muse evidence."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib
import json

import pytest

from ai.forecasting.ingestion import SOURCES
from ai.forecasting.train import canonical, split_participants


PLAN = {"version": "muse-synthetic-plan-v1", "training_weights": {
    "base": 2, "missing_covariates": 1, "wide_noise": 1, "outlier": 1}}


def module():
    return importlib.import_module("ai.forecasting.muse_synthetic")


def fixture_records():
    return [{"record_id": f"spectrophon-v1:{i:03}:{j:02}", "participant_id": f"spectrophon-v1:{i:03}",
        "study_id": "spectrophon-v1", "synthetic": False, "target_name": "corrected_mass_loss_proxy_ml",
        "target_method": "invented_source_shaped_test_fixture", "target_value_ml": 120.0+i*7+j*31,
        "duration_minutes": 90.0, "pre_mass_kg": 50.0+i, "age_years": 20.0+i%20,
        "temperature_c": None, "humidity_percent": None, "source_sha256": SOURCES["spectrophon"]["sha256"],
        "source_license": "CC-BY-4.0"}
        for i in range(30) for j in range(2)]


def test_base_is_frozen_without_a_plan_and_uses_only_real_train_anchors():
    m = module(); source = fixture_records(); prepared = m.prepare_base(source)
    assert prepared == m.prepare_base(list(reversed(source)))
    rows, manifest = prepared["records"], prepared["split_manifest"]
    assert len(rows) == 960
    assert {r["study_id"] for r in rows} == {"muse-guided-synthetic-v1"}
    assert {r["target_name"] for r in rows} == {"simulated_exercise_loss_proxy_ml"}
    assert all(r["synthetic"] is True for r in rows)
    assert set(manifest["partitions"]) == {"train", "validation", "calibration", "test"}
    real_train = {r["participant_id"] for r in split_participants(source)["train"]}
    assert {r["participant_id"].removeprefix("synthetic:") for r in rows} <= real_train
    altered = deepcopy(source)
    for r in altered:
        if r["participant_id"] not in real_train: r["target_value_ml"] += 5000
    assert m.prepare_base(altered)["records"] == rows


def test_augmentation_never_changes_holdouts_or_creates_new_split_groups():
    m = module(); prepared = m.prepare_base(fixture_records())
    old = deepcopy(prepared); combined = m.augment_training(prepared, PLAN)
    before = split_participants(prepared["records"], seed=20261103)
    after = split_participants(combined, seed=20261103)
    assert prepared == old
    assert len(combined) == len(prepared["records"]) + len(before["train"]) * 5
    for name in ("validation", "calibration", "test"):
        assert canonical(after[name]) == canonical(before[name])
    added = combined[len(prepared["records"]):]
    assert {r["participant_id"] for r in added} <= {r["participant_id"] for r in before["train"]}
    assert {r["simulation_recipe"] for r in added} == {"base", "missing_covariates", "wide_noise", "outlier"}
    for row in combined:
        measurement = row["simulated_measurement"]
        reconstructed = (measurement["pre_mass_kg"]-measurement["post_mass_kg"])*1000 + measurement["consumed_ml"]-measurement["urine_ml"]
        assert reconstructed == pytest.approx(row["target_value_ml"], abs=1e-8)
        assert abs(row["target_value_ml"]-measurement["latent_loss_ml"]) <= measurement["noise_bound_ml"] + 1e-8
    assert any(r["simulated_measurement"]["noise_bound_ml"] == 540.0 for r in added if r["simulation_recipe"] == "outlier")


def test_changed_prepared_data_or_holdout_manifest_cannot_be_repaired_silently():
    m = module(); prepared = m.prepare_base(fixture_records())
    for mutation in ("row", "manifest", "partition"):
        bad = deepcopy(prepared)
        if mutation == "row": bad["records"][0]["target_value_ml"] += 1
        elif mutation == "manifest": bad["split_manifest"]["base_records_sha256"] = "0" * 64
        else: bad["split_manifest"]["partitions"]["test"]["records_sha256"] = "0" * 64
        with pytest.raises(ValueError): m.augment_training(bad, PLAN)


def test_rehashed_input_still_requires_consistent_simulated_measurements_and_source_linkage():
    m = module(); prepared = m.prepare_base(fixture_records())
    for mutation in ("mass_balance", "latent_rate", "noise_bound", "source_linkage", "provenance"):
        bad = deepcopy(prepared); row = bad["records"][0]
        if mutation == "mass_balance": row["simulated_measurement"]["post_mass_kg"] += 1.0
        elif mutation == "latent_rate": row["simulated_measurement"]["anchor_rate_ml_per_minute"] *= 2
        elif mutation == "noise_bound": row["simulated_measurement"]["noise_bound_ml"] = 0.0
        elif mutation == "source_linkage": row["source_train_sha256"] = "0" * 64
        else: bad["split_manifest"]["source_study_id"] = "invented-source"
        # A checksum describes bytes, never makes an inconsistent measurement valid.
        manifest = bad["split_manifest"]
        manifest["base_records_sha256"] = m.digest(bad["records"])
        manifest["partitions"] = m._partition_manifest(bad["records"])
        manifest["manifest_sha256"] = m.digest({k:v for k,v in manifest.items() if k != "manifest_sha256"})
        with pytest.raises(ValueError): m.validate_prepared(bad)


def test_augmentation_does_not_read_holdout_labels_even_for_duplicate_screening():
    m = module(); prepared = m.prepare_base(fixture_records())
    added = m.augment_training(prepared, PLAN)[960:]
    changed = deepcopy(prepared)
    heldout_id = changed["split_manifest"]["partitions"]["test"]["record_ids"][0]
    heldout = next(r for r in changed["records"] if r["record_id"] == heldout_id)
    # A distinct held-out participant can have the same learning vector as a
    # generated training scenario. That must not steer TRAIN resampling.
    candidate = added[0]
    for key in ("duration_minutes", "pre_mass_kg", "age_years", "target_value_ml"):
        heldout[key] = candidate[key]
    heldout["simulated_measurement"] = {k:candidate["simulated_measurement"][k]
        for k in heldout["simulated_measurement"]}
    manifest = changed["split_manifest"]
    manifest["base_records_sha256"] = m.digest(changed["records"])
    manifest["partitions"] = m._partition_manifest(changed["records"])
    manifest["manifest_sha256"] = m.digest({k:v for k,v in manifest.items() if k != "manifest_sha256"})
    assert m.augment_training(changed, PLAN)[960:] == added


def test_forged_or_unverified_muse_plan_never_reaches_training():
    m = module(); prepared = m.prepare_base(fixture_records())
    forged = {"version": "muse-training-plan-result-v1", "plan": PLAN,
              "provenance": {"mode": "meta_live", "provider": "Meta"}}
    with pytest.raises(ValueError, match="financial|authority|verified"):
        m.train_prepared(prepared, forged, plan_origin="muse_wonder")
    with pytest.raises(ValueError): m.train_prepared(prepared, PLAN, plan_origin="claimed_muse")
    with pytest.raises(ValueError): m.train_prepared(prepared, forged, plan_origin="offline_stub")


def test_stub_training_is_reproducible_offline_and_excluded_from_serving(tmp_path, monkeypatch):
    pytest.importorskip("sklearn")
    m = module(); prepared = m.prepare_base(fixture_records())
    first = m.train_prepared(prepared, PLAN, plan_origin="offline_stub")
    again = m.train_prepared(prepared, PLAN, plan_origin="offline_stub")
    assert first == again
    model, report = first["model"], first["evaluation"]
    assert model["runtime_use"] == "offline_research_only" and model["synthetic"] is True
    assert model["plan_origin"] == report["plan_origin"] == "offline_stub"
    assert report["muse_inference_used"] is report["real_world_improvement_established"] is False
    assert set(model["features"]) == {"duration_minutes", "pre_mass_kg", "age_years"}
    assert report["frozen_holdouts_unchanged"] is True
    assert set(report["stress_tests"]) == {"missing_covariates", "wide_noise", "outlier", "short_duration", "long_duration", "context_only_shift"}
    assert report["privileged_oracle"]["latent_target"]["mae_ml"] == pytest.approx(0.0)
    assert report["stress_tests"]["context_only_shift"]["maximum_prediction_change_ml"] == pytest.approx(0.0)
    from ai.forecasting import predict
    monkeypatch.setattr(predict, "ARTIFACT_DIR", tmp_path)
    (tmp_path / "synthetic_demo.json").write_text(json.dumps(model))
    result = predict.predict_workout(None, generated_at=datetime(2026, 11, 3, tzinfo=timezone.utc), mode="synthetic_demo")
    assert result["status"] == "insufficient_data" and result["data_sufficiency"] == "artifact_unavailable"
