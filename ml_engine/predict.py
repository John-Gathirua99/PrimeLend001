try:
    import joblib
except ImportError:
    joblib = None  # not available in production
try:
    import pandas as pd
except ImportError:
    pd = None
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

model = joblib.load(os.path.join(BASE_DIR, "model", "loan_model.pkl"))
encoder = joblib.load(os.path.join(BASE_DIR, "model", "employment_encoder.pkl"))

EXPECTED_FEATURES = [
    "age", "employment_status", "monthly_income",
    "loan_amount", "repayment_period", "credit_history"
]

# Handle unseen employment labels gracefully
KNOWN_LABELS = list(encoder.classes_)


def predict_loan(data: dict) -> dict:
    """
    Predict basic loan eligibility.

    Expected keys:
        age, employment_status, monthly_income,
        loan_amount, repayment_period, credit_history
    """
    emp = data.get("employment_status", "Employed")
    if emp not in KNOWN_LABELS:
        emp = "Employed"  # fallback to most common class

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
    pred_class = int(model.predict(df)[0])

    if prob >= 0.80:
        decision = "Approved"
    elif prob >= 0.55:
        decision = "Pending"
    else:
        decision = "Rejected"

    return {
        "decision": decision,
        "pred_class": pred_class,
        "probability": round(prob, 4),
    }