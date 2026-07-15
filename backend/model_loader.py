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

from storage.factory import build_object_storage

_BASE_DIR = Path(__file__).parent.parent
MODEL_PATH = Path(get_settings().model_path)


class ModelRuntimeManager:
    def __init__(self, default_model_path: Path) -> None:
        self._lock = Lock()
        self._object_storage = build_object_storage()
        self._default_model_path = default_model_path
        self._active_model = self._load_model(default_model_path)
        self._active_explainer = shap.TreeExplainer(self._active_model)
        self._active_model_path = str(default_model_path)
        self._active_bundle_dir: Path | None = None
        self._shadow_model = None
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
            suffix = ".zip" if artifact_path.endswith(".zip") else ".cbm"
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

    def _load_model(self, model_path: Path) -> CatBoostClassifier:
        model = CatBoostClassifier()
        model.load_model(str(model_path))
        return model

    def set_active_model(self, artifact_path: str) -> None:
        model_path, bundle_dir = self._resolve_model_artifact(artifact_path)
        if not model_path.exists():
            raise RuntimeError(f"Model artifact not found: {model_path}")

        with self._lock:
            active = self._load_model(model_path)
            self._active_model = active
            self._active_explainer = shap.TreeExplainer(active)
            old_bundle = self._active_bundle_dir
            self._active_bundle_dir = bundle_dir
            self._active_model_path = artifact_path
            self._cleanup_bundle_dir(old_bundle)

    def set_shadow_model(self, artifact_path: str | None) -> None:
        if artifact_path is None:
            with self._lock:
                old_bundle = self._shadow_bundle_dir
                self._shadow_model = None
                self._shadow_model_path = None
                self._shadow_bundle_dir = None
                self._cleanup_bundle_dir(old_bundle)
            return

        model_path, bundle_dir = self._resolve_model_artifact(artifact_path)
        if not model_path.exists():
            raise RuntimeError(f"Shadow artifact not found: {model_path}")

        with self._lock:
            self._shadow_model = self._load_model(model_path)
            old_bundle = self._shadow_bundle_dir
            self._shadow_bundle_dir = bundle_dir
            self._shadow_model_path = artifact_path
            self._cleanup_bundle_dir(old_bundle)

    def predict_active(self, features) -> float:
        with self._lock:
            proba = self._active_model.predict_proba(features)
        return float(proba[0][1])

    def predict_shadow(self, features) -> float | None:
        with self._lock:
            if self._shadow_model is None:
                return None
            proba = self._shadow_model.predict_proba(features)
        return float(proba[0][1])

    def explain_active(self, df):
        with self._lock:
            shap_values = self._active_explainer.shap_values(df)[0]
        return shap_values

    def state(self) -> dict[str, str | None]:
        with self._lock:
            return {
                "active_model_path": self._active_model_path,
                "shadow_model_path": self._shadow_model_path,
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


def switch_active_model(artifact_path: str) -> None:
    runtime_manager.set_active_model(artifact_path)


def switch_shadow_model(artifact_path: str | None) -> None:
    runtime_manager.set_shadow_model(artifact_path)

