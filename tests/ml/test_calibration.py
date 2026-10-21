"""Calibration: JSON round trip, parity with scikit-learn, and that serving applies it."""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml
from sklearn.isotonic import IsotonicRegression

from ml.calibration import Calibrator, calibration_path_for, cross_fit

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL = REPO_ROOT / "models" / "catboost_churn.cbm"


def _scores_and_labels(n=2000, seed=0):
    rng = np.random.default_rng(seed)
    s = rng.uniform(0.01, 0.99, n)
    y = (rng.uniform(size=n) < s**1.5).astype(int)  # miscalibrated on purpose
    return s, y


@pytest.mark.parametrize("method", ["identity", "platt", "isotonic"])
def test_json_round_trip_preserves_transform(method, tmp_path):
    s, y = _scores_and_labels()
    cal = Calibrator.fit(method, s, y)
    path = cal.save(tmp_path / "c.json")
    again = Calibrator.load(path)
    np.testing.assert_allclose(again.transform(s), cal.transform(s))


def test_isotonic_matches_sklearn_predict():
    s, y = _scores_and_labels()
    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(s, y)
    grid = np.linspace(-0.2, 1.2, 501)  # includes out-of-range values
    np.testing.assert_allclose(Calibrator.fit("isotonic", s, y).transform(grid), iso.predict(grid), atol=1e-12)


def test_platt_improves_log_loss_on_miscalibrated_scores():
    from sklearn.metrics import log_loss

    s, y = _scores_and_labels()
    cal = cross_fit("platt", s, y, folds=5, seed=0)
    assert log_loss(y, cal) < log_loss(y, s)


def test_calibration_is_monotone():
    s, y = _scores_and_labels()
    grid = np.linspace(0.001, 0.999, 200)
    for method in ("platt", "isotonic"):
        out = Calibrator.fit(method, s, y).transform(grid)
        assert np.all(np.diff(out) >= -1e-12), method


def test_shipped_model_has_a_calibration_file():
    assert calibration_path_for(MODEL).exists()
    params = yaml.safe_load((REPO_ROOT / "params.yaml").read_text(encoding="utf-8"))
    assert Path(params["output"]["calibration_path"]).name == calibration_path_for(MODEL).name


def test_params_threshold_matches_api_default():
    from core.settings import Settings

    params = yaml.safe_load((REPO_ROOT / "params.yaml").read_text(encoding="utf-8"))
    assert params["evaluation"]["decision_threshold"] == Settings.model_fields["decision_threshold"].default


def _row():
    from ml.preprocessing.preprocessing import load_artifacts, prepare_for_model, preprocess

    raw = pd.DataFrame([{
        "SeniorCitizen": 0, "Partner": "Yes", "Dependents": "No", "tenure": 5, "PhoneService": "Yes",
        "MultipleLines": "No", "InternetService": "Fiber optic", "OnlineSecurity": "No", "OnlineBackup": "No",
        "DeviceProtection": "No", "TechSupport": "No", "StreamingTV": "Yes", "StreamingMovies": "No",
        "Contract": "Month-to-month", "PaperlessBilling": "Yes", "PaymentMethod": "Electronic check",
        "MonthlyCharges": 85.0, "TotalCharges": 425.0,
    }])
    features, cats = load_artifacts()
    x = prepare_for_model(preprocess(raw), features)
    for c in cats:
        x[c] = x[c].astype(str)
    return x


def test_runtime_serves_calibrated_score_for_loose_cbm(tmp_path):
    from catboost import CatBoostClassifier
    from model_loader import ModelRuntimeManager

    model_copy = tmp_path / "m.cbm"
    shutil.copy(MODEL, model_copy)
    Calibrator("platt", {"a": 0.5, "b": -1.0}).save(calibration_path_for(model_copy))

    raw_model = CatBoostClassifier()
    raw_model.load_model(str(MODEL))
    x = _row()
    raw = raw_model.predict_proba(x)[0][1]
    expected = float(Calibrator("platt", {"a": 0.5, "b": -1.0}).transform(raw))

    manager = ModelRuntimeManager(model_copy)
    assert manager.predict_active(x) == pytest.approx(expected)
    assert manager.state()["active_calibration"] == "platt"

    manager.set_shadow_model(str(MODEL))  # shipped artifact with its own calibration file
    shipped = Calibrator.load(calibration_path_for(MODEL))
    assert manager.predict_shadow(x) == pytest.approx(float(shipped.transform(raw)))


def test_artifact_without_calibration_file_serves_raw_score(tmp_path):
    from catboost import CatBoostClassifier
    from model_loader import ModelRuntimeManager

    model_copy = tmp_path / "old.cbm"
    shutil.copy(MODEL, model_copy)
    raw_model = CatBoostClassifier()
    raw_model.load_model(str(MODEL))
    x = _row()
    manager = ModelRuntimeManager(model_copy)
    assert manager.predict_active(x) == pytest.approx(raw_model.predict_proba(x)[0][1])
    assert manager.state()["active_calibration"] == "identity"


def test_bundle_carries_calibration_and_runtime_uses_it(tmp_path):
    from ml.preprocessing.pipeline_bundle import build_pipeline_bundle
    from model_loader import ModelRuntimeManager

    model_copy = tmp_path / "m.cbm"
    shutil.copy(MODEL, model_copy)
    Calibrator("platt", {"a": 1.0, "b": 2.0}).save(calibration_path_for(model_copy))
    art = REPO_ROOT / "models"
    bundle = build_pipeline_bundle(model_copy, art / "feature_list.json", art / "cat_columns.json", tmp_path / "b", "vtest")

    with zipfile.ZipFile(bundle) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        assert "model/calibration.json" in zf.namelist()
    assert any(f["path"] == "model/calibration.json" for f in manifest["files"])

    manager = ModelRuntimeManager(MODEL)
    manager.set_active_model(str(bundle))
    assert manager.state()["active_calibration"] == "platt"
    scorer = manager.load_scorer(str(bundle))
    x = _row()
    assert manager.predict_active(x) == pytest.approx(float(scorer(x)[0]))
