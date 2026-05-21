# ml_engine/underwriting.py
import logging

logger = logging.getLogger(__name__)

def make_credit_decision(
    id_verification: dict,
    face_verification: dict,
    risk_score: float,
    loan_amount: float,
    user_income: float
) -> dict:
    """
    Automated Decision Engine.
    Returns: {'decision': 'APPROVED'|'REJECTED'|'MANUAL_REVIEW', 'reasons': [], 'confidence': 0.0-1.0}
    """
    
    # 1. Initialize variables
    decision = "MANUAL_REVIEW" # Default to safe
    reasons = []
    confidence = 0.0
    hard_blocks = [] # Unforgivable errors
    warnings = []

    # --- 2. KYC & ID VALIDATION (The Gatekeepers) ---
    
    # Check ID Authenticity
    if not id_verification.get('passed'):
        hard_blocks.append("ID verification failed")
        # Add specific reason if available
        if id_verification.get('failures'):
            hard_blocks.extend(id_verification['failures'])

    # Check Face Match (Crucial for automation)
    # We demand high confidence (> 0.70) for auto-approval
    face_confidence = face_verification.get('confidence', 0)
    face_matched = face_verification.get('match', False)
    
    if not face_matched:
        hard_blocks.append("Face does not match ID document")
    elif face_confidence < 0.60:
        # If match is weak, don't reject, but don't auto-approve
        warnings.append("Face match confidence low")
        decision = "MANUAL_REVIEW"

    # Check if ID is blacklisted or reused
    if id_verification.get('id_reused'):
        hard_blocks.append("ID number associated with another account")

    # --- 3. FINANCIAL LOGIC ---
    
    # Debt-to-Income Ratio (DTI)
    # Standard rule: Loan repayment shouldn't exceed 30-40% of income
    if user_income and user_income > 0:
        # Simplified monthly repayment calculation (assuming 12 months)
        monthly_repayment = loan_amount / 12 
        dti_ratio = monthly_repayment / user_income
        
        if dti_ratio > 0.5: # More than 50% of income
            hard_blocks.append("Debt to Income ratio too high")
        elif dti_ratio > 0.35:
            warnings.append("DTI slightly elevated")
    else:
        hard_blocks.append("Income not verifiable")

    # Risk Score from your ML Model
    if risk_score > 0.75: # High risk
        hard_blocks.append("High risk score from ML model")
    elif risk_score > 0.50:
        warnings.append("Moderate risk score")

    # --- 4. FINAL DECISION LOGIC ---

    if len(hard_blocks) > 0:
        decision = "REJECTED"
        reasons = hard_blocks
        confidence = 1.0 # We are sure we should reject
        logger.info(f"[Underwriting] REJECTED due to: {hard_blocks}")
    
    elif len(warnings) > 0:
        decision = "MANUAL_REVIEW"
        reasons = warnings
        confidence = 0.5
        logger.info(f"[Underwriting] MANUAL_REVIEW due to: {warnings}")
        
    else:
        # All checks passed cleanly
        decision = "APPROVED"
        reasons = ["All checks passed"]
        confidence = 0.9
        logger.info("[Underwriting] APPROVED automatically.")

    return {
        "decision": decision,
        "reasons": reasons,
        "confidence": confidence,
        "hard_blocks": hard_blocks,
        "warnings": warnings
    }