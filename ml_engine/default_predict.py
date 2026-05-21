"""
ml_engine/default_predict.py — Loan default prediction
Model: GradientBoostingClassifier (0.98 AUC)
Predicts probability that a funded loan will default
"""
import os
import logging
logger = logging.getLogger(__name__)

_model = None
_scaler = None
_features = None
_READY = False

def _load():
    global _model, _scaler, _features, _READY
    if _READY:
        return True
    try:
        import joblib
        BASE = os.path.dirname(os.path.abspath(__file__))
        _model    = joblib.load(os.path.join(BASE, "default_model.pkl"))
        _scaler   = joblib.load(os.path.join(BASE, "default_scaler.pkl"))
        _features = joblib.load(os.path.join(BASE, "default_features.pkl"))
        _READY = True
        return True
    except Exception as e:
        logger.warning(f"[Default] Model load failed: {e}")
        return False


def predict_default_risk(loan, repayment_data=None) -> dict:
    """
    Predict default risk for a funded loan.
    loan: LoanApplication instance
    repayment_data: dict with missed_payments, partial_payments
    Returns dict with probability, risk_level, recommendation
    """
    if not _load():
        return {"probability": 0.5, "risk_level": "UNKNOWN", "recommendation": "Manual review"}

    try:
        import pandas as pd
        from decimal import Decimal

        emp_map = {"Employed": 0, "Self-employed": 1, "Business": 2, "Unemployed": 3, "Student": 3}
        emp_type = emp_map.get(getattr(loan, "employment_status", "Employed"), 0)

        income = float(getattr(loan, "monthly_income", 0) or 0)
        loan_amount = float(getattr(loan, "qualified_amount", 0) or 0)
        repayment_period = int(getattr(loan, "repayment_period", 12) or 12)
        interest_rate = float(getattr(loan, "interest_rate", 0.15) or 0.15)
        credit_history = int(getattr(loan, "credit_history", 0) or 0)
        past_default = int(getattr(loan, "last_default_flag", False) or False)
        prev_loans = int(getattr(loan, "previous_loan_count", 0) or 0)
        on_time = int(getattr(loan, "on_time_repayment_count", 0) or 0)

        dti = loan_amount / max(income * repayment_period, 1)
        monthly_payment = (loan_amount * (1 + interest_rate)) / max(repayment_period, 1)
        payment_to_income = monthly_payment / max(income, 1)

        missed = repayment_data.get("missed_payments", 0) if repayment_data else 0
        partial = repayment_data.get("partial_payments", 0) if repayment_data else 0
        days_first = repayment_data.get("days_to_first_payment", 7) if repayment_data else 7

        row = pd.DataFrame([{
            "age": getattr(loan, "age", 30) or 30,
            "monthly_income": income,
            "loan_amount": loan_amount,
            "repayment_period": repayment_period,
            "interest_rate": interest_rate,
            "employment_type": emp_type,
            "credit_history": credit_history,
            "past_default_flag": past_default,
            "previous_loan_count": prev_loans,
            "on_time_repayment_count": on_time,
            "debt_to_income_ratio": round(dti, 4),
            "payment_to_income_ratio": round(payment_to_income, 4),
            "days_to_first_payment": days_first,
            "partial_payments": partial,
            "missed_payments": missed,
        }])

        row_scaled = _scaler.transform(row)
        prob = float(_model.predict_proba(row_scaled)[0][1])

        if prob < 0.25:
            level = "LOW"
            rec = "Low default risk — proceed normally"
        elif prob < 0.50:
            level = "MEDIUM"
            rec = "Monitor repayments — send early reminders"
        elif prob < 0.75:
            level = "HIGH"
            rec = "High default risk — require check-in call"
        else:
            level = "VERY HIGH"
            rec = "Very high default risk — consider restructuring"

        return {
            "probability": round(prob, 4),
            "risk_level": level,
            "recommendation": rec,
        }

    except Exception as e:
        logger.error(f"[Default] Prediction error: {e}")
        return {"probability": 0.5, "risk_level": "UNKNOWN", "recommendation": "Manual review"}
