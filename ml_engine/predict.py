import os
import logging
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    import joblib
    import pandas as pd
    from sklearn.preprocessing import LabelEncoder
    model = joblib.load(os.path.join(BASE_DIR, "model", "loan_model.pkl"))
    encoder = joblib.load(os.path.join(BASE_DIR, "model", "employment_encoder.pkl"))
    ML_AVAILABLE = True
except Exception as e:
    logger.warning(f"ML model not available: {e}")
    ML_AVAILABLE = False
    model = None
    encoder = None

def predict_loan(data: dict) -> dict:
    if not ML_AVAILABLE:
        return {"approved": True, "probability": 0.75, "reason": "ML unavailable - manual review"}
    try:
        import pandas as pd
        emp = data.get("employment_status", "Employed")
        known = list(encoder.classes_)
        if emp not in known:
            emp = "Employed"
        employment_encoded = encoder.transform([emp])[0]
        df = pd.DataFrame([{
            "age": data["age"],
            "employment_status": employment_encoded,
            "monthly_income": data["monthly_income"],
            "loan_amount": data["loan_amount"],
            "repayment_period": data["repayment_period"],
            "credit_history": data["credit_history"],
        }])
        prob = float(model.predict_proba(df)[0][1])
        return {"approved": prob >= 0.5, "probability": prob, "reason": "ML prediction"}
    except Exception as e:
        logger.error(f"Prediction error: {e}")
        return {"approved": True, "probability": 0.75, "reason": "Prediction error - manual review"}
