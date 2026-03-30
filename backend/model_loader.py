from pathlib import Path
from threading import Lock

from catboost import CatBoostClassifier
import shap

from storage.factory import build_object_storage

_BASE_DIR = Path(__file__).parent.parent
MODEL_PATH = _BASE_DIR / "model" / "artifacts" / "catboost_churn.cbm"


class ModelRuntimeManager:
    def __init__(self, default_model_path: Path) -> None:
        self._lock = Lock()
        self._object_storage = build_object_storage()
        self._default_model_path = default_model_path
        self._active_model = self._load_model(default_model_path)
        self._active_explainer = shap.TreeExplainer(self._active_model)
        self._active_model_path = str(default_model_path)
        self._shadow_model = None
        self._shadow_model_path = None

    def _resolve_artifact(self, artifact_path: str) -> Path:
        if artifact_path.startswith("s3://") or artifact_path.startswith("az://"):
            if self._object_storage is None:
                raise RuntimeError("Object storage provider is not configured")
            return self._object_storage.download_to_path(artifact_path, suffix=".cbm")

        if artifact_path.startswith("file://"):
            return Path(artifact_path.replace("file://", "", 1))

        model_path = Path(artifact_path)
        if model_path.is_absolute():
            return model_path
        return (_BASE_DIR / model_path).resolve()

    def _load_model(self, model_path: Path) -> CatBoostClassifier:
        model = CatBoostClassifier()
        model.load_model(str(model_path))
        return model

    def set_active_model(self, artifact_path: str) -> None:
        model_path = self._resolve_artifact(artifact_path)
        if not model_path.exists():
            raise RuntimeError(f"Model artifact not found: {model_path}")

        with self._lock:
            active = self._load_model(model_path)
            self._active_model = active
            self._active_explainer = shap.TreeExplainer(active)
            self._active_model_path = str(model_path)

    def set_shadow_model(self, artifact_path: str | None) -> None:
        if artifact_path is None:
            with self._lock:
                self._shadow_model = None
                self._shadow_model_path = None
            return

        model_path = self._resolve_artifact(artifact_path)
        if not model_path.exists():
            raise RuntimeError(f"Shadow artifact not found: {model_path}")

        with self._lock:
            self._shadow_model = self._load_model(model_path)
            self._shadow_model_path = str(model_path)

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

