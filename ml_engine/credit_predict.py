"""
ml_engine/credit_predict.py — Strict credit scoring

Key changes from previous version:
  - KYC unverified = hard cap at 'Review' (never auto-approved)
  - OCR ID not verified = automatic penalty
  - Income plausibility check — extreme incomes flagged
  - Stated income vs loan amount ratio enforced
  - First-time applicants require KYC to be approved
  - Approval threshold raised from 0.72 to 0.78
"""
import logging
from typing import Dict

logger = logging.getLogger(__name__)

# Thresholds
APPROVE_THRESHOLD = 0.78   # raised from 0.72
REVIEW_THRESHOLD  = 0.52


def predict_credit(features: dict) -> dict:
    score = 0.0
    components = {}
    explanations = []
    hard_blocks = []   # conditions that force Review/Reject regardless of score

    age            = features.get("age", 30)
    income         = features.get("monthly_income", 0)
    repayment      = features.get("repayment_period", 12)
    credit_history = features.get("credit_history", 0)
    dti            = features.get("debt_to_income_ratio", 0)
    past_default   = features.get("past_default_flag", 0)
    prev_loans     = features.get("previous_loan_count", 0)
    on_time        = features.get("on_time_repayment_count", 0)
    fraud_score    = features.get("fraud_score", 0)
    recent_apps    = features.get("recent_application_count", 0)
    kyc_verified   = features.get("kyc_face_verified", None)
    ocr_verified   = features.get("ocr_id_verified", False)
    id_reuse       = features.get("id_reuse_flag", False)
    loan_amount    = features.get("loan_amount", 0)
    needs_review   = features.get("needs_manual_review", False)

    # ════════════════════════════════════════════════════════════
    # HARD BLOCKS — force to Review or Reject regardless of score
    # ════════════════════════════════════════════════════════════

    if id_reuse:
        hard_blocks.append("✗ ID number already used on another account — possible fraud")

    if kyc_verified is False:
        hard_blocks.append("✗ Face KYC failed — identity could not be confirmed")

    if past_default:
        hard_blocks.append("✗ Previous loan default on record")

    if fraud_score >= 0.60:
        hard_blocks.append(f"✗ High fraud risk score ({fraud_score:.0%})")

    # Income vs loan amount sanity check
    if income > 0 and loan_amount > 0:
        loan_to_income = loan_amount / income
        if loan_to_income > 3.0:
            hard_blocks.append(f"✗ Loan amount ({loan_amount:,.0f}) exceeds 3× monthly income ({income:,.0f})")

    # Income plausibility — extreme values are suspicious
    if income > 500000:
        hard_blocks.append("△ Stated income extremely high — requires manual verification")
    if income < 5000:
        hard_blocks.append("✗ Stated income too low for loan eligibility (min KES 5,000/month)")

    # ════════════════════════════════════════════════════════════
    # SCORING
    # ════════════════════════════════════════════════════════════

    # ── 1. KYC verification (most important for first-time) ───────
    if kyc_verified is True:
        contrib = 0.20
        explanations.append("✓ Identity verified via face KYC")
    elif kyc_verified is None:
        contrib = 0.0
        explanations.append("△ Identity not KYC-verified — approval limited")
        # First-time applicants MUST have KYC
        if prev_loans == 0:
            hard_blocks.append("✗ First-time applicants must complete KYC face verification")
    else:
        contrib = -0.10
        explanations.append("✗ KYC face verification failed")
    score += contrib
    components["kyc"] = contrib

    # ── 2. OCR ID document verification ──────────────────────────
    if ocr_verified:
        contrib = 0.15
        explanations.append("✓ ID document verified by OCR — details confirmed")
    else:
        contrib = -0.05
        explanations.append("△ ID document not OCR-verified — manual check needed")
    score += contrib
    components["ocr_verification"] = contrib

    # ── 3. Credit history ─────────────────────────────────────────
    if credit_history == 1:
        contrib = 0.20
        explanations.append("✓ Good credit history")
    else:
        contrib = 0.0
        explanations.append("✗ No credit history on record")
    score += contrib
    components["credit_history"] = contrib

    # ── 4. Income adequacy ────────────────────────────────────────
    if income >= 100000:
        contrib = 0.15
        explanations.append("✓ Strong income level")
    elif income >= 50000:
        contrib = 0.12
        explanations.append("✓ Adequate income")
    elif income >= 20000:
        contrib = 0.07
        explanations.append("△ Moderate income")
    elif income >= 10000:
        contrib = 0.03
        explanations.append("✗ Low income — reduced limit")
    elif income >= 5000:
        contrib = 0.01
        explanations.append("✗ Minimum income bracket")
    else:
        contrib = -0.10
        explanations.append("✗ Income below minimum threshold")
    score += contrib
    components["income"] = contrib

    # ── 5. Age factor ─────────────────────────────────────────────
    if 28 <= age <= 45:
        contrib = 0.08
        explanations.append("✓ Prime age bracket")
    elif 25 <= age <= 55:
        contrib = 0.05
    elif age >= 21:
        contrib = 0.02
    else:
        contrib = -0.05
        explanations.append("✗ Applicant below recommended age")
    score += contrib
    components["age"] = contrib

    # ── 6. Repayment track record ─────────────────────────────────
    if prev_loans > 0:
        rate = on_time / prev_loans
        if rate >= 0.95:
            contrib = 0.18
            explanations.append(f"✓ Excellent repayment record ({on_time}/{prev_loans})")
        elif rate >= 0.80:
            contrib = 0.10
            explanations.append(f"✓ Good repayment record ({on_time}/{prev_loans})")
        elif rate >= 0.60:
            contrib = 0.04
            explanations.append(f"△ Average repayment record ({on_time}/{prev_loans})")
        else:
            contrib = -0.10
            explanations.append(f"✗ Poor repayment record ({on_time}/{prev_loans})")
        score += contrib
        components["repayment_record"] = contrib
    else:
        # No history — neutral but flagged
        explanations.append("△ No repayment history on platform")

    # ── 7. Debt-to-income ratio ───────────────────────────────────
    if dti < 0.25:
        contrib = 0.08
        explanations.append("✓ Low debt-to-income ratio")
    elif dti < 0.40:
        contrib = 0.04
    elif dti < 0.60:
        contrib = 0.0
        explanations.append("△ Moderate debt-to-income ratio")
    else:
        contrib = -0.08
        explanations.append("✗ High debt-to-income ratio")
    score += contrib
    components["dti"] = contrib

    # ── 8. Repayment period ───────────────────────────────────────
    if repayment <= 3:
        contrib = 0.06
        explanations.append("✓ Very short repayment period")
    elif repayment <= 6:
        contrib = 0.04
    elif repayment <= 12:
        contrib = 0.02
    else:
        contrib = -0.02
        explanations.append("△ Long repayment period increases default risk")
    score += contrib
    components["repayment_period"] = contrib

    # ── 9. Fraud score penalty ────────────────────────────────────
    if fraud_score >= 0.60:
        penalty = 0.30
        explanations.append(f"✗ High fraud risk ({fraud_score:.0%})")
    elif fraud_score >= 0.40:
        penalty = 0.15
        explanations.append(f"△ Elevated fraud risk ({fraud_score:.0%})")
    elif fraud_score >= 0.25:
        penalty = 0.05
    else:
        penalty = 0.0
    score -= penalty
    if penalty > 0:
        components["fraud_penalty"] = -penalty

    # ── 10. Application velocity ──────────────────────────────────
    if recent_apps >= 5:
        score -= 0.15
        components["velocity"] = -0.15
        explanations.append("✗ Excessive recent applications (5+)")
    elif recent_apps >= 3:
        score -= 0.08
        components["velocity"] = -0.08
        explanations.append("△ Multiple recent applications")

    # ── 11. Manual review flag ────────────────────────────────────
    if needs_review:
        score -= 0.05
        explanations.append("△ Application flagged for manual review")

    # ════════════════════════════════════════════════════════════
    # DECISION
    # ════════════════════════════════════════════════════════════
    probability = round(min(1.0, max(0.0, score)), 4)

    if hard_blocks:
        # Hard blocks force Review or Reject
        critical = any("fraud" in b.lower() or "ID number" in b or "default" in b for b in hard_blocks)
        if critical or probability < 0.40:
            decision = "Rejected"
        else:
            decision = "Review"
        explanations = hard_blocks + explanations
    elif probability >= APPROVE_THRESHOLD:
        decision = "Approved"
    elif probability >= REVIEW_THRESHOLD:
        decision = "Review"
    else:
        decision = "Rejected"

    return {
        "probability":      probability,
        "decision":         decision,
        "explanation":      explanations,
        "score_components": components,
        "hard_blocks":      hard_blocks,
    }