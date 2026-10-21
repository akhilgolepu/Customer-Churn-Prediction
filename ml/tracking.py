"""MLflow helpers shared by the training scripts and the API loader.

Default store: sqlite:///<repo>/mlflow.db with artifacts under <repo>/mlartifacts
(both git-ignored), independent of the working directory. Override with
MLFLOW_TRACKING_URI and CHURN_MLFLOW_ARTIFACT_ROOT (used when the experiment is
first created).

Registered models are plain artifact directories holding one model file
(<name>.cbm or <name>.json) and its <name>.calibration.json, i.e. the same
layout the API loads from models/, so `models:/<name>/<version>` can be
used as an artifact path in POST /api/v1/models/register.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = "churn"
CATBOOST_MODEL_NAME = "churn-catboost"
CHALLENGER_MODEL_NAME = "churn-logreg-challenger"


def tracking_uri() -> str:
    return os.environ.get("MLFLOW_TRACKING_URI") or f"sqlite:///{(REPO_ROOT / 'mlflow.db').as_posix()}"


def _client():
    import mlflow
    from mlflow import MlflowClient

    mlflow.set_tracking_uri(tracking_uri())
    return mlflow, MlflowClient()


def start_run(run_name: str):
    mlflow, client = _client()
    exp = client.get_experiment_by_name(EXPERIMENT)
    if exp is None:
        root = Path(os.environ.get("CHURN_MLFLOW_ARTIFACT_ROOT") or REPO_ROOT / "mlartifacts")
        client.create_experiment(EXPERIMENT, artifact_location=root.resolve().as_uri())
    mlflow.set_experiment(EXPERIMENT)
    return mlflow.start_run(run_name=run_name)


def log_and_register(model_file: Path, registered_name: str, artifact_path: str = "model") -> str:
    """Log model_file + its sibling calibration into the active run and register a version."""
    import mlflow

    from ml.calibration import calibration_path_for

    _, client = _client()
    staging = Path(tempfile.mkdtemp(prefix="churn_mlflow_"))
    try:
        shutil.copy(model_file, staging / model_file.name)
        cal = calibration_path_for(model_file)
        if cal.exists():
            shutil.copy(cal, staging / cal.name)
        mlflow.log_artifacts(str(staging), artifact_path=artifact_path)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    run = mlflow.active_run()
    if run is None:
        raise RuntimeError("log_and_register must be called inside tracking.start_run()")
    try:
        client.create_registered_model(registered_name)
    except Exception:  # already exists
        pass
    version = client.create_model_version(
        registered_name, source=f"{run.info.artifact_uri}/{artifact_path}", run_id=run.info.run_id
    )
    return str(version.version)


def is_mlflow_uri(artifact_path: str) -> bool:
    return artifact_path.startswith(("models:/", "runs:/"))


def download_model_dir(artifact_uri: str) -> tuple[Path, Path]:
    """Download a registered model directory; returns (model file, temp dir to clean up)."""
    mlflow, _ = _client()
    target = Path(tempfile.mkdtemp(prefix="churn_mlflow_model_"))
    local = Path(mlflow.artifacts.download_artifacts(artifact_uri=artifact_uri, dst_path=str(target)))
    candidates = [
        p for p in local.rglob("*")
        if p.suffix in (".cbm", ".json") and not p.name.endswith(".calibration.json")
    ]
    if len(candidates) != 1:
        shutil.rmtree(target, ignore_errors=True)
        raise RuntimeError(f"Expected exactly one model file in {artifact_uri}, found {[p.name for p in candidates]}")
    return candidates[0], target
