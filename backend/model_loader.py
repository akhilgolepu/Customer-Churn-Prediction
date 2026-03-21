from pathlib import Path
from catboost import CatBoostClassifier
import shap

_BASE_DIR = Path(__file__).parent.parent
MODEL_PATH = _BASE_DIR / "model" / "artifacts" / "catboost_churn.cbm"

try:
    model = CatBoostClassifier()
    model.load_model(str(MODEL_PATH))
    explainer = shap.TreeExplainer(model)
except Exception as e:
    raise RuntimeError(f"Failed to load model from {MODEL_PATH}: {e}")


def predict_proba(features):
    proba = model.predict_proba(features)
    # Returns [[prob_no_churn, prob_churn]]
    return float(proba[0][1])


def explain(df):
    shap_values = explainer.shap_values(df)[0]
    return shap_values

