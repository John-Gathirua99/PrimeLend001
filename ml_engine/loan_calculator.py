"""
ml_engine/loan_calculator.py — Strict loan limits for Kenyan micro-lending

Loan limit rules:
  - Base: 25% of monthly income (conservative)
  - Multipliers for age, credit history, KYC, OCR verification
  - Hard minimum KES 1,000
  - Hard maximum KES 200,000 (reduced from 500,000)
  - First-time applicants: max 1 month income regardless
  - Unverified users: capped at KES 10,000
"""
from decimal import Decimal


def calculate_loan_limit(age, monthly_income, credit_history,
                         kyc_verified=None, ocr_id_verified=False,
                         previous_loans_repaid=0, previous_default=False):
    income = Decimal(str(monthly_income))

    # ── Base: 25% of one month income ────────────────────────────
    base_limit = income * Decimal("0.25")

    # ── Age multiplier ────────────────────────────────────────────
    if age < 21:
        base_limit *= Decimal("0.30")
    elif age < 25:
        base_limit *= Decimal("0.50")
    elif age < 30:
        base_limit *= Decimal("0.75")
    elif 30 <= age <= 50:
        base_limit *= Decimal("1.00")
    elif age <= 55:
        base_limit *= Decimal("0.85")
    else:
        base_limit *= Decimal("0.60")

    # ── Credit history ────────────────────────────────────────────
    if credit_history == 1:
        base_limit *= Decimal("1.15")
    else:
        base_limit *= Decimal("0.40")

    # ── KYC verification ─────────────────────────────────────────
    if kyc_verified is True:
        base_limit *= Decimal("1.10")
    elif kyc_verified is False:
        base_limit *= Decimal("0.50")
    else:
        base_limit = min(base_limit, Decimal("10000"))

    # ── OCR ID verification ───────────────────────────────────────
    if ocr_id_verified:
        base_limit *= Decimal("1.10")
    else:
        base_limit *= Decimal("0.70")

    # ── Track record ──────────────────────────────────────────────
    if previous_default:
        base_limit *= Decimal("0.20")
    elif previous_loans_repaid >= 3:
        base_limit *= Decimal("1.20")
    elif previous_loans_repaid >= 1:
        base_limit *= Decimal("1.08")

    # ── Hard floor and ceiling ────────────────────────────────────
    base_limit = max(base_limit, Decimal("1000"))
    base_limit = min(base_limit, Decimal("200000"))

    # ── First-time applicants: never more than 1 month income ────
    if previous_loans_repaid == 0 and not previous_default:
        base_limit = min(base_limit, income)

    return base_limit.quantize(Decimal("0.01"))


def determine_interest(probability, kyc_verified=None, ocr_id_verified=False):
    if probability >= 0.85:
        rate = Decimal("0.08")
    elif probability >= 0.75:
        rate = Decimal("0.12")
    elif probability >= 0.65:
        rate = Decimal("0.18")
    elif probability >= 0.55:
        rate = Decimal("0.25")
    else:
        rate = Decimal("0.30")

    if kyc_verified is None:
        rate += Decimal("0.05")
    elif kyc_verified is False:
        rate += Decimal("0.10")

    if not ocr_id_verified:
        rate += Decimal("0.03")

    return min(rate, Decimal("0.40"))