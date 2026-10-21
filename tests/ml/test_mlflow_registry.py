"""Models registered in MLflow (ml/tracking.py) can be loaded by the API by URI."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("mlflow")

from ml import tracking  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
ART = REPO_ROOT / "models"


@pytest.fixture()
def mlflow_store(tmp_path, monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}")
    monkeypatch.setenv("CHURN_MLFLOW_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    yield tmp_path


def test_registered_models_load_by_uri(mlflow_store):
    from model_loader import ModelRuntimeManager

    from tests.ml.test_calibration import _row

    with tracking.start_run("test"):
        cb_version = tracking.log_and_register(ART / "catboost_churn.cbm", "test-catboost", "catboost")
        lr_version = tracking.log_and_register(ART / "logreg_challenger.json", "test-challenger", "challenger")

    manager = ModelRuntimeManager(ART / "catboost_churn.cbm")
    x = _row()
    expected = manager.predict_active(x)

    manager.set_shadow_model(f"models:/test-catboost/{cb_version}")
    assert manager.predict_shadow(x) == pytest.approx(expected)
    assert manager.state()["shadow_calibration"] == "identity"

    manager.set_shadow_model(f"models:/test-challenger/{lr_version}")
    assert manager.state()["shadow_model_kind"] == "logistic_regression"
    assert 0.0 < manager.predict_shadow(x) < 1.0


def test_registered_model_passes_through_the_promotion_gate_scorer(mlflow_store):
    from model_loader import ModelRuntimeManager

    from tests.ml.test_calibration import _row

    with tracking.start_run("test"):
        version = tracking.log_and_register(ART / "catboost_churn.cbm", "test-catboost", "catboost")
    manager = ModelRuntimeManager(ART / "catboost_churn.cbm")
    scorer = manager.load_scorer(f"models:/test-catboost/{version}")
    assert float(scorer(_row())[0]) == pytest.approx(manager.predict_active(_row()))


def test_directory_with_two_model_files_is_rejected(mlflow_store, tmp_path):
    import mlflow

    d = tmp_path / "two"
    d.mkdir()
    (d / "a.cbm").write_bytes((ART / "catboost_churn.cbm").read_bytes())
    (d / "b.json").write_text("{}")
    with tracking.start_run("test") as run:
        mlflow.log_artifacts(str(d), artifact_path="model")
    with pytest.raises(RuntimeError, match="exactly one model file"):
        tracking.download_model_dir(f"runs:/{run.info.run_id}/model")
