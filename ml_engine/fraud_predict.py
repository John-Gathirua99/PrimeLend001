"""
ml_engine/fraud_predict.py — Strict fraud detection

Key improvements:
  - OCR ID match failure = major fraud signal
  - Income implausibility scoring
  - Age vs income mismatch detection
  - Loan-to-income ratio check
  - Phone/account linking
  - Velocity checks
  - KYC face match result
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

FRAUD_FLAG_THRESHOLD  = 0.50   # lowered from 0.55 — stricter
FRAUD_ALERT_THRESHOLD = 0.30   # lowered from 0.40


@dataclass
class FraudResult:
    score: float
    flag: bool
    alert: bool
    reasons: List[str]
    risk_level: str
    breakdown: Dict[str, float] = field(default_factory=dict)


def detect_fraud(features: dict) -> Tuple[float, bool, List[str]]:
    result = detect_fraud_detailed(features)
    return result.score, result.flag, result.reasons


def detect_fraud_detailed(features: dict) -> FraudResult:
    score    = 0.0
    reasons  = []
    breakdown = {}

    age            = features.get("age", 30)
    income         = features.get("monthly_income", 0)
    loan_amount    = features.get("loan_amount", 0)
    credit_history = features.get("credit_history", 0)
    kyc_verified   = features.get("kyc_face_verified", None)
    ocr_verified   = features.get("ocr_id_verified", False)
    ocr_name_match = features.get("ocr_name_match", False)
    id_reuse       = features.get("id_reuse_flag", False)

    # ── 1. ID Reuse — highest weight ─────────────────────────────
    if id_reuse:
        score += 0.45
        breakdown["id_reuse"] = 0.45
        reasons.append("🚨 ID number already registered on another account")

    # ── 2. OCR ID verification failure ───────────────────────────
    if not ocr_verified:
        score += 0.20
        breakdown["ocr_not_verified"] = 0.20
        reasons.append("⚠ ID document could not be verified by OCR")
    elif not ocr_name_match:
        score += 0.12
        breakdown["name_mismatch"] = 0.12
        reasons.append("⚠ Name on ID document does not match account name")

    # ── 3. KYC face result ────────────────────────────────────────
    if kyc_verified is False:
        score += 0.25
        breakdown["kyc_failed"] = 0.25
        reasons.append("🚨 Face does not match ID document photo")
    elif kyc_verified is None:
        score += 0.10
        breakdown["kyc_missing"] = 0.10
        reasons.append("⚠ Identity not verified via face KYC")

    # ── 4. Multiple accounts per phone ───────────────────────────
    accounts_per_phone = features.get("accounts_per_phone", 1)
    if accounts_per_phone >= 3:
        score += 0.20
        breakdown["multi_account_phone"] = 0.20
        reasons.append(f"🚨 Phone linked to {accounts_per_phone} accounts")
    elif accounts_per_phone == 2:
        score += 0.10
        breakdown["multi_account_phone"] = 0.10
        reasons.append(f"⚠ Phone linked to 2 accounts")

    # ── 5. Income plausibility ────────────────────────────────────
    # Age vs income mismatch
    if age < 22 and income > 100000:
        score += 0.18
        breakdown["age_income_mismatch"] = 0.18
        reasons.append(f"⚠ Unusually high income (KES {income:,.0f}) for age {age}")
    elif age < 25 and income > 200000:
        score += 0.12
        breakdown["age_income_mismatch"] = 0.12
        reasons.append(f"⚠ High income (KES {income:,.0f}) for age {age} — verify")

    # Extreme income values
    if income > 800000:
        score += 0.15
        breakdown["extreme_income"] = 0.15
        reasons.append(f"⚠ Extremely high stated income (KES {income:,.0f}) — verify employment")
    elif income < 3000 and loan_amount > 5000:
        score += 0.20
        breakdown["income_too_low"] = 0.20
        reasons.append(f"🚨 Income (KES {income:,.0f}) too low for requested loan (KES {loan_amount:,.0f})")

    # ── 6. Loan-to-income ratio ───────────────────────────────────
    if income > 0 and loan_amount > 0:
        lti = loan_amount / income
        if lti > 5.0:
            score += 0.20
            breakdown["loan_income_ratio"] = 0.20
            reasons.append(f"🚨 Loan amount is {lti:.1f}× monthly income — unsustainable")
        elif lti > 3.0:
            score += 0.10
            breakdown["loan_income_ratio"] = 0.10
            reasons.append(f"⚠ Loan amount is {lti:.1f}× monthly income — high risk")

    # ── 7. Application velocity ───────────────────────────────────
    recent_apps = features.get("recent_application_count", 0)
    if recent_apps >= 5:
        score += 0.20
        breakdown["velocity"] = 0.20
        reasons.append(f"🚨 {recent_apps} applications in short period — loan stacking risk")
    elif recent_apps >= 3:
        score += 0.10
        breakdown["velocity"] = 0.10
        reasons.append(f"⚠ {recent_apps} recent applications")

    # ── 8. Device/IP changes ──────────────────────────────────────
    device_changes = features.get("device_change_count", 0)
    if device_changes >= 5:
        score += 0.12
        breakdown["device_changes"] = 0.12
        reasons.append(f"⚠ {device_changes} device changes detected")

    # ── 9. Credit history vs income mismatch ─────────────────────
    if credit_history == 1 and income < 8000:
        # Claims good credit but very low income — suspicious
        score += 0.08
        breakdown["credit_income_mismatch"] = 0.08
        reasons.append("⚠ Good credit claimed but income very low")

    # ── 10. KYC bonus ────────────────────────────────────────────
    if kyc_verified is True and ocr_verified:
        score -= 0.10
        breakdown["verified_bonus"] = -0.10

    # ── Clamp and classify ────────────────────────────────────────
    score = round(min(1.0, max(0.0, score)), 4)

    if score >= 0.70:
        risk_level = "CRITICAL"
    elif score >= FRAUD_FLAG_THRESHOLD:
        risk_level = "HIGH"
    elif score >= FRAUD_ALERT_THRESHOLD:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    return FraudResult(
        score=score,
        flag=score >= FRAUD_FLAG_THRESHOLD,
        alert=score >= FRAUD_ALERT_THRESHOLD,
        reasons=reasons,
        risk_level=risk_level,
        breakdown=breakdown,
    )