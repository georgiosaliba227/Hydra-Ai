"""Selection safety and grouped evaluation of measured proxy outcomes."""
from copy import deepcopy

import pytest

pytest.importorskip("sklearn")

from ai.forecasting import train


def records():
    return [{"record_id": f"s:{i}:{j}", "participant_id": f"s:{i}", "study_id": "s",
             "synthetic": False, "target_name": "mass_loss_proxy_ml", "target_method": "fixture",
             "target_value_ml": 100.0 + i * 7 + j * 31, "duration_minutes": 30.0 + j * 20,
             "pre_mass_kg": 50.0 + i, "age_years": 20.0 + i % 20}
            for i in range(20) for j in range(2)]


def test_worse_or_unstable_challenger_cannot_replace_baseline():
    from ai.forecasting.grouped_evaluation import select_candidate

    # A large gain for a single person cannot outweigh unstable paired evidence.
    selected, evidence = select_candidate({
        "cohort_rate_baseline": {"a": 100., "b": 100., "c": 100.},
        "ridge": {"a": 110., "b": 110., "c": 110.},
        "random_forest": {"a": 0., "b": 140., "c": 140.},
    })
    assert selected == "cohort_rate_baseline"
    assert evidence["ridge"]["eligible"] is False
    assert evidence["random_forest"]["eligible"] is False


def test_consistent_paired_improvement_is_eligible_and_exact_tie_stays_simple():
    from ai.forecasting.grouped_evaluation import select_candidate

    selected, evidence = select_candidate({
        "cohort_rate_baseline": {"a": 100., "b": 100., "c": 100.},
        "ridge": {"a": 80., "b": 80., "c": 80.},
        "random_forest": {"a": 80., "b": 80., "c": 80.},
    })
    assert selected == "ridge"
    assert evidence["ridge"]["paired_gain_ml"] == 20.
    assert evidence["ridge"]["gain_standard_error_ml"] == 0.


def test_repeated_folds_keep_every_visit_together_and_once_per_repeat():
    from ai.forecasting.grouped_evaluation import development_folds

    rows = records()
    folds = development_folds(rows, repeats=3, folds=4)
    assert folds == development_folds(list(reversed(rows)), repeats=3, folds=4)
    for repeat in range(3):
        heldout_ids = []
        for fold in [f for f in folds if f["repeat"] == repeat]:
            training_ids = {r["participant_id"] for r in fold["train"]}
            validation_ids = {r["participant_id"] for r in fold["validation"]}
            assert not training_ids & validation_ids
            assert len(fold["validation"]) == 2 * len(validation_ids)
            heldout_ids.extend(r["record_id"] for r in fold["validation"])
        assert sorted(heldout_ids) == sorted(r["record_id"] for r in rows)


def test_participant_weighting_does_not_give_many_correlated_rows_extra_votes():
    from ai.forecasting.grouped_evaluation import participant_metrics

    rows = [{"participant_id": "a", "target_value_ml": 0.}] * 8 + [
        {"participant_id": "b", "target_value_ml": 100.}]
    result = participant_metrics(rows, [0.] * 9, radius=50.)
    assert result["mae_ml"] == pytest.approx(100. / 9)
    assert result["participant_mae_ml"] == 50.
    assert result["participant_simultaneous_coverage"] == .5


def test_holdout_outcomes_do_not_change_selection_fit_or_calibration():
    from ai.forecasting.grouped_evaluation import grouped_experiment

    rows = records()
    artifact, report = grouped_experiment(rows, provenance=["fixture"], repeats=2, folds=3)
    ids = {r["record_id"] for r in train.split_participants(rows)["test"]}
    altered = deepcopy(rows)
    for row in altered:
        if row["record_id"] in ids:
            row["target_value_ml"] += 5000
    second, second_report = grouped_experiment(altered, provenance=["fixture"], repeats=2, folds=3)
    for key in ("model", "selected_model", "imputation", "means", "scales", "feature_bounds", "interval"):
        assert artifact[key] == second[key]
    assert report["selection"] == second_report["selection"]
    assert report["selected_test"] != second_report["selected_test"]
    # Reports preserve the original calibration/test groups, not new convenient splits.
    expected = train.split_participants(rows)
    assert report["partitions"]["test"]["record_ids"] == [r["record_id"] for r in expected["test"]]
    assert report["partitions"]["calibration"]["record_ids"] == [r["record_id"] for r in expected["calibration"]]
    assert report["interval"]["nominal_coverage"] is None


def test_grouped_fit_and_selection_are_reproducible_with_missing_inputs():
    from ai.forecasting.grouped_evaluation import grouped_experiment

    rows = records()
    for row in rows[::3]:
        row["age_years"] = None
    first = grouped_experiment(rows, provenance=["fixture"], repeats=2, folds=3)
    again = grouped_experiment(list(reversed(rows)), provenance=["fixture"], repeats=2, folds=3)
    assert first == again
    assert first[1]["missing_mass_and_age_test"]["n"] == 8
    assert first[0]["runtime_use"] == "offline_research_only"


def test_calibration_outcomes_never_enter_grouped_selection_or_fitting():
    from ai.forecasting.grouped_evaluation import grouped_experiment

    rows = records()
    artifact, report = grouped_experiment(rows, provenance=["fixture"], repeats=1, folds=3)
    calibration_ids = {r["record_id"] for r in train.split_participants(rows)["calibration"]}
    altered = deepcopy(rows)
    for row in altered:
        if row["record_id"] in calibration_ids:
            row["target_value_ml"] += 2000
    other, other_report = grouped_experiment(altered, provenance=["fixture"], repeats=1, folds=3)
    assert report["selection"] == other_report["selection"]
    assert artifact["model"] == other["model"]
    assert artifact["fit_partition_sha256"] == other["fit_partition_sha256"]
    assert artifact["interval"]["radius_ml"] != other["interval"]["radius_ml"]


def test_fit_preprocessing_uses_training_only_and_rejects_misattributed_audit():
    rows = records()
    training = rows[:12]
    audit = deepcopy(rows)
    for row in audit[12:]:
        row["pre_mass_kg"] = 200.
    models = train.fit_candidates(training, provenance=["fixture"], audit_records=audit)
    assert models["ridge"]["imputation"][1] == 52.5
    assert models["ridge"]["feature_bounds"]["pre_mass_kg"] == [50., 55.]
    different_study = [{**row, "study_id": "different"} for row in audit]
    with pytest.raises(ValueError, match="training_audit_mismatch"):
        train.fit_candidates(training, provenance=["fixture"], audit_records=different_study)


def test_required_duration_cannot_be_imputed_in_grouped_experiments():
    from ai.forecasting.grouped_evaluation import grouped_experiment

    rows = records()
    rows[0]["duration_minutes"] = None
    with pytest.raises(ValueError, match="invalid_measurement"):
        grouped_experiment(rows, provenance=["fixture"], repeats=1, folds=3)
