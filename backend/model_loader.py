import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from threading import Lock
import zipfile
from core.settings import get_settings
from catboost import CatBoostClassifier
import shap

from model.calibration import Calibrator, load_for_model
from model.linear_model import LinearChurnModel

from storage.factory import build_object_storage

_BASE_DIR = Path(__file__).parent.parent
MODEL_PATH = Path(get_settings().model_path)


class _CatBoostAdapter:
    """Uniform interface: predict_proba(frame) -> 1-D P(churn); explain(frame) -> per-feature values."""

    kind = "catboost"

    def __init__(self, model: CatBoostClassifier) -> None:
        self._model = model
        self._explainer = None

    def prepare_explainer(self) -> None:
        if self._explainer is None:
            self._explainer = shap.TreeExplainer(self._model)

    def predict_proba(self, features):
        return self._model.predict_proba(features)[:, 1]

    def explain(self, df):
        # SHAP values are in the raw model's log-odds space.
        self.prepare_explainer()
        return self._explainer.shap_values(df)[0]


class _LinearAdapter:
    kind = "logistic_regression"

    def __init__(self, model: LinearChurnModel) -> None:
        self._model = model

    def prepare_explainer(self) -> None:
        pass

    def predict_proba(self, features):
        return self._model.predict_proba(features)

    def explain(self, df):
        # Exact log-odds contributions vs the average training customer.
        return self._model.explain(df)


class ModelRuntimeManager:
    def __init__(self, default_model_path: Path) -> None:
        self._lock = Lock()
        self._object_storage = build_object_storage()
        self._default_model_path = default_model_path
        self._active_model, self._active_calibrator = self._load_model(default_model_path)
        self._active_model.prepare_explainer()
        self._active_model_path = str(default_model_path)
        self._active_bundle_dir: Path | None = None
        self._shadow_model = None
        self._shadow_calibrator: Calibrator | None = None
        self._shadow_model_path = None
        self._shadow_bundle_dir: Path | None = None

    def _sha256_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(8192), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _resolve_artifact(self, artifact_path: str) -> Path:
        if artifact_path.startswith("s3://") or artifact_path.startswith("az://"):
            if self._object_storage is None:
                raise RuntimeError("Object storage provider is not configured")
            suffix = next((s for s in (".zip", ".json") if artifact_path.endswith(s)), ".cbm")
            return self._object_storage.download_to_path(artifact_path, suffix=suffix)

        if artifact_path.startswith("file://"):
            return Path(artifact_path.replace("file://", "", 1))

        model_path = Path(artifact_path)
        if model_path.is_absolute():
            return model_path
        return (_BASE_DIR / model_path).resolve()

    def _cleanup_bundle_dir(self, bundle_dir: Path | None) -> None:
        if bundle_dir and bundle_dir.exists():
            shutil.rmtree(bundle_dir, ignore_errors=True)

    def _resolve_model_from_bundle(self, bundle_path: Path) -> tuple[Path, Path]:
        if not bundle_path.exists():
            raise RuntimeError(f"Pipeline bundle not found: {bundle_path}")

        bundle_dir = Path(tempfile.mkdtemp(prefix="churn_pipeline_bundle_"))
        try:
            with zipfile.ZipFile(bundle_path, mode="r") as zf:
                zf.extractall(bundle_dir)
        except Exception:
            self._cleanup_bundle_dir(bundle_dir)
            raise

        manifest_path = bundle_dir / "manifest.json"
        if not manifest_path.exists():
            self._cleanup_bundle_dir(bundle_dir)
            raise RuntimeError("Pipeline bundle missing manifest.json")

        with manifest_path.open("r", encoding="utf-8") as fh:
            manifest = json.load(fh)

        if manifest.get("artifact_format") != "churn_pipeline_bundle/v1":
            self._cleanup_bundle_dir(bundle_dir)
            raise RuntimeError("Unsupported pipeline bundle artifact_format")

        for item in manifest.get("files", []):
            rel_path = item.get("path")
            expected_sha = item.get("sha256")
            if not rel_path or not expected_sha:
                continue
            file_path = bundle_dir / rel_path
            if not file_path.exists():
                self._cleanup_bundle_dir(bundle_dir)
                raise RuntimeError(f"Pipeline bundle missing required file: {rel_path}")
            actual_sha = self._sha256_file(file_path)
            if actual_sha != expected_sha:
                self._cleanup_bundle_dir(bundle_dir)
                raise RuntimeError(f"Checksum mismatch for bundled artifact: {rel_path}")

        model_path = bundle_dir / "model" / "model.cbm"
        if not model_path.exists():
            self._cleanup_bundle_dir(bundle_dir)
            raise RuntimeError("Pipeline bundle missing model/model.cbm")

        return model_path, bundle_dir

    def _resolve_model_artifact(self, artifact_path: str) -> tuple[Path, Path | None]:
        resolved_path = self._resolve_artifact(artifact_path)
        if resolved_path.suffix.lower() == ".zip":
            model_path, bundle_dir = self._resolve_model_from_bundle(resolved_path)
            return model_path, bundle_dir
        return resolved_path, None

    def _load_model(self, model_path: Path):
        """Load a model artifact and its calibration.

        .cbm -> CatBoost; .json -> logistic regression (model/linear_model.py).
        A bundle keeps the calibration at model/calibration.json, a loose artifact
        next to it as <name>.calibration.json. Without one the raw score is served
        (identity), which is how pre-calibration artifacts behave."""
        if LinearChurnModel.is_linear_artifact(model_path):
            model = _LinearAdapter(LinearChurnModel.load(model_path))
        else:
            cb = CatBoostClassifier()
            cb.load_model(str(model_path))
            model = _CatBoostAdapter(cb)
        bundled = model_path.parent / "calibration.json"
        if model_path.name == "model.cbm" and bundled.exists():
            calibrator = Calibrator.load(bundled)
        else:
            calibrator = load_for_model(model_path)
        return model, calibrator

    def set_active_model(self, artifact_path: str) -> None:
        model_path, bundle_dir = self._resolve_model_artifact(artifact_path)
        if not model_path.exists():
            raise RuntimeError(f"Model artifact not found: {model_path}")

        with self._lock:
            active, calibrator = self._load_model(model_path)
            active.prepare_explainer()
            self._active_model = active
            self._active_calibrator = calibrator
            old_bundle = self._active_bundle_dir
            self._active_bundle_dir = bundle_dir
            self._active_model_path = artifact_path
            self._cleanup_bundle_dir(old_bundle)

    def set_shadow_model(self, artifact_path: str | None) -> None:
        if artifact_path is None:
            with self._lock:
                old_bundle = self._shadow_bundle_dir
                self._shadow_model = None
                self._shadow_calibrator = None
                self._shadow_model_path = None
                self._shadow_bundle_dir = None
                self._cleanup_bundle_dir(old_bundle)
            return

        model_path, bundle_dir = self._resolve_model_artifact(artifact_path)
        if not model_path.exists():
            raise RuntimeError(f"Shadow artifact not found: {model_path}")

        with self._lock:
            self._shadow_model, self._shadow_calibrator = self._load_model(model_path)
            old_bundle = self._shadow_bundle_dir
            self._shadow_bundle_dir = bundle_dir
            self._shadow_model_path = artifact_path
            self._cleanup_bundle_dir(old_bundle)

    def predict_active(self, features) -> float:
        with self._lock:
            proba = self._active_model.predict_proba(features)
            calibrator = self._active_calibrator
        return float(calibrator.transform(proba[0]))

    def predict_shadow(self, features) -> float | None:
        with self._lock:
            if self._shadow_model is None:
                return None
            proba = self._shadow_model.predict_proba(features)
            calibrator = self._shadow_calibrator
        return float(calibrator.transform(proba[0]))

    def explain_active(self, df):
        # Explanations are in the raw model's log-odds space. Calibration is a
        # monotone map applied afterwards, so the ranking of drivers is unchanged.
        with self._lock:
            return self._active_model.explain(df)

    def load_scorer(self, artifact_path: str):
        """Load an artifact outside the runtime (does not touch active/shadow) and
        return predict_fn(frame) -> calibrated P(churn) per row. Used by the
        promotion gate."""
        model_path, bundle_dir = self._resolve_model_artifact(artifact_path)
        try:
            if not model_path.exists():
                raise RuntimeError(f"Model artifact not found: {model_path}")
            model, calibrator = self._load_model(model_path)
        finally:
            self._cleanup_bundle_dir(bundle_dir)

        def predict_fn(features):
            return calibrator.transform(model.predict_proba(features))

        return predict_fn

    def state(self) -> dict[str, str | None]:
        with self._lock:
            return {
                "active_model_path": self._active_model_path,
                "active_model_kind": self._active_model.kind,
                "active_calibration": self._active_calibrator.method,
                "shadow_model_path": self._shadow_model_path,
                "shadow_model_kind": self._shadow_model.kind if self._shadow_model else None,
                "shadow_calibration": self._shadow_calibrator.method if self._shadow_calibrator else None,
            }


try:
    runtime_manager = ModelRuntimeManager(MODEL_PATH)
except Exception as e:
    raise RuntimeError(f"Failed to load model from {MODEL_PATH}: {e}")


def predict_proba(features):
    return runtime_manager.predict_active(features)


def predict_shadow_proba(features):
    return runtime_manager.predict_shadow(features)


def explain(df):
    return runtime_manager.explain_active(df)


def load_scorer(artifact_path: str):
    return runtime_manager.load_scorer(artifact_path)


def switch_active_model(artifact_path: str) -> None:
    runtime_manager.set_active_model(artifact_path)


def switch_shadow_model(artifact_path: str | None) -> None:
    runtime_manager.set_shadow_model(artifact_path)

