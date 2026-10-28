from datetime import datetime, timedelta, timezone
import json
from uuid import UUID

import pytest

from ai.forecasting import predict
from ai.hydration.models import CalculationError, WorkoutMeasurement
from ai.hydration.personal_forecast import Conditions, Exercise, MeasurementErrors, SweatSample

NOW=datetime(2026,10,28,12,tzinfo=timezone.utc)
CONDITIONS=Conditions("running","moderate",24.0,50.0)


def exercise():
    return Exercise(UUID(int=100),NOW+timedelta(hours=1),60,CONDITIONS,True)


def sample(index=1,loss_kg=.4):
    return SweatSample(UUID(int=index),NOW-timedelta(days=index),CONDITIONS,
                       WorkoutMeasurement(70,70-loss_kg,200,0,60,True,("manual_measured",)),
                       MeasurementErrors(.02,.02,10,0,1,("scale_bounds_supplied",)))


def test_cold_start_returns_null_and_does_not_load_population_model():
    result=predict.predict_workout(exercise(),generated_at=NOW)
    assert result["status"]=="insufficient_data"
    assert result["value_ml"] is None and result["lower_ml"] is None
    assert result["synthetic"] is False


def test_personal_measurements_update_center_without_claiming_ml():
    one=predict.predict_workout(exercise(),(sample(),),generated_at=NOW)
    two=predict.predict_workout(exercise(),(sample(),sample(2,.8)),generated_at=NOW)
    assert one["value_ml"]==pytest.approx(600)
    assert two["value_ml"]==pytest.approx(800)
    assert two["lower_ml"]<=two["value_ml"]<=two["upper_ml"]
    assert two["sample_count"]==2
    assert two["personalization_status"]=="personal_measured_calibration"
    assert two["interval_kind"]=="conditional_measurement_envelope"
    assert two["model_version"]=="personal-exercise-loss-v1"


def test_future_duplicate_and_mismatched_samples_are_not_learned():
    with pytest.raises(CalculationError):
        predict.predict_workout(exercise(),(sample(),sample()),generated_at=NOW)
    future=SweatSample(UUID(int=1),NOW+timedelta(minutes=1),CONDITIONS,sample().measurement,sample().errors)
    with pytest.raises(CalculationError):predict.predict_workout(exercise(),(future,),generated_at=NOW)
    other=SweatSample(UUID(int=1),NOW-timedelta(days=1),Conditions("cycling","moderate",24,50),sample().measurement,sample().errors)
    assert predict.predict_workout(exercise(),(other,),generated_at=NOW)["status"]=="insufficient_data"


def test_demo_fixture_cannot_relabel_real_inputs():
    with pytest.raises(CalculationError):
        predict.predict_workout(exercise(),generated_at=NOW,mode="synthetic_demo")
    with pytest.raises(CalculationError):
        predict.predict_workout(None,(sample(),),generated_at=NOW,mode="synthetic_demo")
    result=predict.predict_workout(None,generated_at=NOW,mode="synthetic_demo")
    assert result["status"]=="estimated" and result["synthetic"] is True
    assert result["data_sufficiency"]=="synthetic_demo_only"
    assert result["sample_count"]==0
    assert result["value_ml"]>=0


@pytest.mark.parametrize("change",["missing","wrong_origin","zero_scale","empty_trees","nonfinite_radius","overflow_upper"])
def test_corrupt_demo_artifact_fails_closed(tmp_path,monkeypatch,change):
    artifact=json.loads((predict.ARTIFACT_DIR/"synthetic_demo.json").read_text())
    monkeypatch.setattr(predict,"ARTIFACT_DIR",tmp_path)
    if change=="wrong_origin":artifact["synthetic"]=False
    if change=="zero_scale":artifact["scales"][0]=0
    if change=="empty_trees":artifact["model"]={"kind":"random_forest","trees":[]}
    if change=="nonfinite_radius":artifact["interval"]["radius_ml"]=float("nan")
    if change=="overflow_upper":
        artifact["model"]={"kind":"constant_rate","rate_ml_per_minute":1e306}
        artifact["interval"]["radius_ml"]=1.79e308
    if change!="missing":(tmp_path/"synthetic_demo.json").write_text(json.dumps(artifact))
    result=predict.predict_workout(None,generated_at=NOW,mode="synthetic_demo")
    assert result["status"]=="insufficient_data" and result["value_ml"] is None


@pytest.mark.parametrize("field,value",[("provenance",None),("provenance",[]),("provenance",[3]),
                                        ("model_version",None),("model_version",[]),("model_version",""),
                                        ("kind",None),("kind",[]),("kind","unvalidated")])
def test_corrupt_metadata_fails_closed(tmp_path,monkeypatch,field,value):
    artifact=json.loads((predict.ARTIFACT_DIR/"synthetic_demo.json").read_text())
    target=artifact["interval"] if field=="kind" else artifact
    if value is None:target.pop(field)
    else:target[field]=value
    (tmp_path/"synthetic_demo.json").write_text(json.dumps(artifact))
    monkeypatch.setattr(predict,"ARTIFACT_DIR",tmp_path)
    result=predict.predict_workout(None,generated_at=NOW,mode="synthetic_demo")
    assert result["status"]=="insufficient_data" and result["value_ml"] is None
