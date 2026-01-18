from catboost import CatBoostClassifier
import shap

MODEL_PATH = "G:/23881A66E2/Projects/Customer_Churn_Predictor/model/artifacts/catboost_churn.cbm"

model = CatBoostClassifier()
model.load_model(MODEL_PATH)

explainer = shap.TreeExplainer(model)

def predict_proba(features):
    proba = model.predict_proba(features)
    # Returns [[prob_no_churn, prob_churn]]
    return float(proba[0][1])

def explain(df):
    shap_values = explainer.shap_values(df)[0]
    return shap_values



