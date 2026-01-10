from catboost import CatBoostClassifier

MODEL_PATH = "G:/23881A66E2/Projects\Customer_Churn_Predictor/model/artifacts/catboost_churn.cbm"

model = CatBoostClassifier()
model.load_model(MODEL_PATH)

def predict_proba(features):
    proba = model.predict_proba(features)
    return float(proba)

