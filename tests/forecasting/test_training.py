"""Training tests are opt-in via the documented offline training dependency set."""
from copy import deepcopy
import json
import math

import pytest
pytest.importorskip("sklearn")

from ai.forecasting.train import metrics, split_participants, train_experiment, validate_records
from ai.forecasting.synthetic import generate_scenarios
from ai.forecasting.predict import predict_artifact


def records():
    return [{"record_id":f"study:{i}:{j}","participant_id":f"study:{i}","study_id":"study",
             "synthetic":False,"target_name":"corrected_mass_loss_proxy_ml","target_method":"corrected",
             "target_value_ml":100.0+i*7+j*31,"duration_minutes":30.0+j*20,
             "pre_mass_kg":50.0+i,"age_years":20.0+i%20,"temperature_c":None,"humidity_percent":None}
            for i in range(30) for j in range(2)]


def test_disjoint_participants_all_visits_and_stable_input_order():
    rows=records()
    parts=split_participants(rows)
    sets=[{r["participant_id"] for r in group} for group in parts.values()]
    assert sum(map(len,sets))==len(set.union(*sets))==30
    assert sum(map(len,parts.values()))==60
    assert parts==split_participants(list(reversed(rows)))


def test_duplicate_measurements_under_new_ids_rejected():
    rows=records()
    rows.append({**rows[0],"record_id":"new","participant_id":"other"})
    with pytest.raises(ValueError,match="duplicate_measurement"):
        validate_records(rows)


@pytest.mark.parametrize("change",[{"synthetic":True},{"target_name":"sweat"},{"study_id":"other"}])
def test_no_real_synthetic_or_target_study_pooling(change):
    rows=records();rows[0].update(change)
    with pytest.raises(ValueError,match="one_study"):
        validate_records(rows)


@pytest.mark.parametrize("value",[True,float("nan"),float("inf"),-1])
def test_invalid_numeric_measurement(value):
    rows=records();rows[0]["target_value_ml"]=value
    with pytest.raises(ValueError):validate_records(rows)


def test_reproducibility_export_parity_and_no_target_leakage():
    rows=records()
    artifact,report=train_experiment(rows,provenance=["fixture"])
    again,report_again=train_experiment(list(reversed(rows)),provenance=["fixture"])
    assert artifact==again and report==report_again
    assert report["json_export_parity"].startswith("passed")
    assert set(artifact["features"])=={"duration_minutes","pre_mass_kg","age_years"}
    assert math.isfinite(predict_artifact(json.loads(json.dumps(artifact)),{"duration_minutes":50}))
    assert set(report["comparison"])=={"cohort_rate_baseline","ridge","random_forest","gradient_boosting"}


def test_test_outcomes_cannot_change_selection_fit_or_calibration():
    rows=records()
    artifact,_=train_experiment(rows,provenance=["fixture"])
    ids={r["record_id"] for r in split_participants(rows)["test"]}
    altered=deepcopy(rows)
    for r in altered:
        if r["record_id"] in ids:r["target_value_ml"]+=5000
    new,_=train_experiment(altered,provenance=["fixture"])
    for key in ("model","selected_model","imputation","means","scales","feature_bounds","interval"):
        assert artifact[key]==new[key]


def test_small_calibration_has_no_claimed_ninety_percent_interval():
    rows=records()[:20]
    artifact,report=train_experiment(rows,provenance=["fixture"])
    assert artifact["interval"]["calibration_participants"]==2
    assert artifact["interval"]["nominal_coverage"] is None
    assert artifact["interval"]["kind"]=="empirical_calibration_envelope"
    assert report["calibration_curve"][-1]["radius_ml"] is None


def test_synthetic_reproducible_bounded_mass_equation_and_no_real_holdouts():
    rows=records()
    generated=generate_scenarios(rows)
    assert generated==generate_scenarios(rows)
    assert all(r["synthetic"] and r["participant_id"].startswith("synthetic:") for r in generated)
    for row in generated:
        m=row["simulated_measurement"]
        calculated=(m["pre_mass_kg"]-m["post_mass_kg"])*1000+m["consumed_ml"]-m["urine_ml"]
        assert calculated==pytest.approx(row["target_value_ml"],abs=1e-8)
        assert abs(row["target_value_ml"]-m["latent_loss_ml"])<=m["noise_bound_ml"]
    heldout={r["record_id"] for k,group in split_participants(rows).items() if k!="train" for r in group}
    altered=deepcopy(rows)
    for row in altered:
        if row["record_id"] in heldout:row["target_value_ml"]+=777
    assert generate_scenarios(altered)==generated


def test_metrics_in_milliliters_and_empty_ood():
    assert metrics([{"target_value_ml":100},{"target_value_ml":200}],[200,100],100)=={
        "n":2,"mae_ml":100,"rmse_ml":100,"bias_ml":0,"interval_coverage":1}
    assert metrics([],[])["mae_ml"] is None
