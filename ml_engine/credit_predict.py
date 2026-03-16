"""
ml_engine/credit_predict.py — AI credit scoring engine
Model: GradientBoostingClassifier (94% accuracy, 0.986 AUC)
Features: 14 features including KYC, OCR, fraud, DTI, repayment history
"""
import os
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────
APPROVE_THRESHOLD = 0.72   # probability >= this = Approved
REVIEW_THRESHOLD  = 0.45   # probability >= this = Under Review
# Below REVIEW_THRESHOLD = Rejected

# ── Interest rate tiers ───────────────────────────────────────
RATE_TIERS = [
    (0.90, 0.10),   # excellent — 10%
    (0.82, 0.13),   # very good — 13%
    (0.72, 0.15),   # good      — 15%
    (0.60, 0.18),   # fair      — 18%
    (0.45, 0.22),   # marginal  — 22%
]

# ── Load model ────────────────────────────────────────────────
_model    = None
_scaler   = None
_features = None
_ML_READY = False

def _load_model():
    global _model, _scaler, _features, _ML_READY
    if _ML_READY:
        return True
    try:
        import joblib
        BASE = os.path.dirname(os.path.abspath(__file__))
        _model    = joblib.load(os.path.join(BASE, "credit_model.pkl"))
        _scaler   = joblib.load(os.path.join(BASE, "credit_scaler.pkl"))
        _features = joblib.load(os.path.join(BASE, "credit_features.pkl"))
        _ML_READY = True
        logger.info("[Credit] Model loaded successfully")
        return True
    except Exception as e:
        logger.warning(f"[Credit] Model load failed: {e}")
        return False


def _get_interest_rate(probability: float) -> Decimal:
    for threshold, rate in RATE_TIERS:
        if probability >= threshold:
            return Decimal(str(rate))
    return Decimal("0.25")


def _qualify_amount(
    requested: float,
    monthly_income: float,
    repayment_period: int,
    probability: float,
    past_default: bool,
) -> float:
    """
    Calculate maximum qualifiable loan amount based on:
    - Income affordability (max 40% of monthly income x period)
    - Credit score tier multiplier
    - Past default penalty
    """
    if monthly_income <= 0:
        return 0.0

    # Max affordable = 40% of total repayment capacity
    max_affordable = monthly_income * repayment_period * 0.40

    # Score-based multiplier
    if probability >= 0.90:
        multiplier = 1.00
    elif probability >= 0.82:
        multiplier = 0.85
    elif probability >= 0.72:
        multiplier = 0.70
    elif probability >= 0.60:
        multiplier = 0.55
    else:
        multiplier = 0.40

    # Past default penalty
    if past_default:
        multiplier *= 0.70

    qualified = min(requested, max_affordable * multiplier)

    # Floor at KES 1,000, cap at KES 500,000
    qualified = max(1000, min(qualified, 500000))
    return round(qualified, -2)  # round to nearest 100


def predict_credit(features: dict) -> dict:
    """
    Main credit prediction function.
    Returns dict with probability, status, interest_rate, qualified_amount, explanations.
    """
    # Extract features
    age            = float(features.get("age", 30))
    income         = float(features.get("monthly_income", 0))
    loan_amount    = float(features.get("loan_amount", 0))
    repayment      = int(features.get("repayment_period", 12))
    credit_history = int(features.get("credit_history", 0))
    dti            = float(features.get("debt_to_income_ratio", 0))
    past_default   = int(features.get("past_default_flag", 0))
    prev_loans     = int(features.get("previous_loan_count", 0))
    on_time        = int(features.get("on_time_repayment_count", 0))
    fraud_score    = float(features.get("fraud_score", 0))
    recent_apps    = int(features.get("recent_application_count", 0))
    kyc_verified   = int(bool(features.get("kyc_face_verified", False)))
    ocr_verified   = int(features.get("ocr_id_verified", False))
    id_reuse       = int(features.get("id_reuse_flag", False))
    needs_review   = features.get("needs_manual_review", False)

    hard_blocks  = []
    explanations = []
    warnings     = []

    # ── Hard blocks ───────────────────────────────────────────
    if id_reuse:
        hard_blocks.append("ID number already used on another account — possible fraud")
    if fraud_score > 0.75:
        hard_blocks.append(f"High fraud risk score ({fraud_score:.2f})")
    if income < 5000:
        hard_blocks.append("Monthly income below minimum threshold (KES 5,000)")
    if dti > 2.0:
        hard_blocks.append(f"Debt-to-income ratio too high ({dti:.1f}x)")
    if kyc_verified == 0:
        hard_blocks.append("KYC face verification not completed")

    if hard_blocks:
        return {
            "probability":      0.0,
            "status":           "Rejected",
            "interest_rate":    Decimal("0.30"),
            "qualified_amount": 0,
            "hard_blocks":      hard_blocks,
            "explanations":     hard_blocks,
            "warnings":         [],
            "risk_level":       "HIGH",
        }

    # ── ML prediction ─────────────────────────────────────────
    probability = 0.5  # fallback
    if _load_model():
        try:
            import numpy as np
            import pandas as pd
            row = pd.DataFrame([{
                "age": age, "monthly_income": income, "loan_amount": loan_amount,
                "repayment_period": repayment, "credit_history": credit_history,
                "debt_to_income_ratio": dti, "past_default_flag": past_default,
                "previous_loan_count": prev_loans, "on_time_repayment_count": on_time,
                "fraud_score": fraud_score, "recent_application_count": recent_apps,
                "kyc_face_verified": kyc_verified, "ocr_id_verified": ocr_verified,
                "id_reuse_flag": id_reuse
            }])
            row_scaled = _scaler.transform(row)
            probability = float(_model.predict_proba(row_scaled)[0][1])
            logger.info(f"[Credit] ML probability: {probability:.4f}")
        except Exception as e:
            logger.error(f"[Credit] Prediction error: {e}")
            # Fall back to rule-based
            probability = _rule_based_score(
                age, income, loan_amount, repayment, credit_history,
                dti, past_default, prev_loans, on_time, fraud_score,
                recent_apps, kyc_verified, ocr_verified
            )
    else:
        probability = _rule_based_score(
            age, income, loan_amount, repayment, credit_history,
            dti, past_default, prev_loans, on_time, fraud_score,
            recent_apps, kyc_verified, ocr_verified
        )

    # ── Manual review override ────────────────────────────────
    if needs_review and probability >= REVIEW_THRESHOLD:
        probability = min(probability, APPROVE_THRESHOLD - 0.01)

    # ── Status determination ──────────────────────────────────
    if probability >= APPROVE_THRESHOLD:
        status = "Approved"
    elif probability >= REVIEW_THRESHOLD:
        status = "Under Review"
    else:
        status = "Rejected"

    # ── Interest rate ─────────────────────────────────────────
    interest_rate = _get_interest_rate(probability)

    # ── Qualified amount ──────────────────────────────────────
    qualified_amount = _qualify_amount(
        loan_amount, income, repayment, probability, bool(past_default)
    ) if status == "Approved" else 0

    # ── Build explanations ────────────────────────────────────
    if probability >= 0.82:
        explanations.append("✓ Strong credit profile")
    if income >= 50000:
        explanations.append("✓ High income increases approval likelihood")
    if credit_history >= 5:
        explanations.append("✓ Good credit history")
    if on_time > 0 and prev_loans > 0:
        rate = on_time / prev_loans
        if rate >= 0.8:
            explanations.append(f"✓ Strong repayment record ({on_time}/{prev_loans} on time)")
    if past_default:
        explanations.append("✗ Previous loan default on record")
    if dti > 0.8:
        explanations.append(f"✗ High debt-to-income ratio ({dti:.1f}x)")
    if fraud_score > 0.3:
        explanations.append(f"⚠ Elevated fraud risk score ({fraud_score:.2f})")
    if not ocr_verified:
        warnings.append("ID document could not be fully verified — manual review recommended")
    if recent_apps >= 3:
        explanations.append("⚠ Multiple recent loan applications detected")

    # ── Default risk ──────────────────────────────────────────
    default_risk = _predict_default_risk(
        probability, past_default, dti, fraud_score, on_time, prev_loans
    )

    return {
        "probability":      round(probability, 4),
        "status":           status,
        "interest_rate":    interest_rate,
        "qualified_amount": qualified_amount,
        "hard_blocks":      hard_blocks,
        "explanations":     explanations,
        "warnings":         warnings,
        "risk_level":       default_risk["level"],
        "default_probability": default_risk["probability"],
    }


def _rule_based_score(
    age, income, loan_amount, repayment, credit_history,
    dti, past_default, prev_loans, on_time, fraud_score,
    recent_apps, kyc_verified, ocr_verified
) -> float:
    """Fallback rule-based scoring when ML model unavailable."""
    score = 0.40  # base
    score += min(income / 500000, 0.20)
    score += max(0, 0.18 - dti * 0.18)
    score += min(credit_history * 0.015, 0.10)
    if prev_loans > 0:
        score += (on_time / prev_loans) * 0.12
    score += 0.08 if kyc_verified else -0.10
    score += 0.05 if ocr_verified else -0.05
    score -= fraud_score * 0.20
    score -= 0.15 if past_default else 0
    score -= 0.08 if recent_apps >= 3 else 0
    score += 0.05 if 25 <= age <= 50 else 0
    return round(max(0.0, min(1.0, score)), 4)


def _predict_default_risk(
    probability, past_default, dti, fraud_score, on_time, prev_loans
) -> dict:
    """Predict likelihood of loan default."""
    risk_score = 1.0 - probability

    if past_default:
        risk_score = min(1.0, risk_score + 0.20)
    if dti > 0.8:
        risk_score = min(1.0, risk_score + 0.10)
    if fraud_score > 0.3:
        risk_score = min(1.0, risk_score + 0.10)
    if prev_loans > 0 and on_time / prev_loans < 0.5:
        risk_score = min(1.0, risk_score + 0.10)

    if risk_score < 0.25:
        level = "LOW"
    elif risk_score < 0.50:
        level = "MEDIUM"
    elif risk_score < 0.75:
        level = "HIGH"
    else:
        level = "VERY HIGH"

    return {"probability": round(risk_score, 4), "level": level}
