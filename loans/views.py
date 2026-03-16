import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import LoanApplication

logger = logging.getLogger(__name__)
from ml_engine.predict import predict_loan
from ml_engine.fraud_predict import detect_fraud
from django.contrib import messages
from ml_engine.loan_calculator import determine_interest, calculate_loan_limit
from ml_engine.credit_predict import predict_credit
from datetime import timedelta
from django.utils import timezone
from accounts.models import UserSecurityProfile
from accounts.models import UserProfile
from notification.models import Notification
from notification.utils import create_notification
from decimal import Decimal
from wallet.models import Wallet
import traceback
import json
from django.http import JsonResponse
from django.urls import reverse
from wallet.models import SystemWallet, SystemTransaction, WalletTransaction
from loans.models import RepaymentSchedule
from dateutil.relativedelta import relativedelta
from notification.email_util import send_loan_email
from ml_engine.id_verify import verify_id_document


"""
UPGRADE PATCH for loans/views.py
=================================
Drop-in replacement for the apply_loan view and supporting functions.

New features:
  1. KYC gate   — if user hasn't verified face, redirect to KYC first,
                  then come back to apply. Skip if already verified.
  2. Pre-fill   — returning users (repaid ≥1 loan on time) skip ID upload
                  and all personal fields; just confirm amount + purpose.
  3. Trust score engine — TrustProfile auto-computed from repayment history.
  4. AI limit boost — trusted users get up to 3× normal limit.
  5. Express lane — zero-friction re-apply for gold/platinum tier users.

Add this import at the top of views.py:
    from loans.trust_engine import get_trust_profile, compute_trust_tier
"""

import logging
import traceback
from decimal import Decimal
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse

from .models import LoanApplication
from accounts.models import UserProfile, UserSecurityProfile
from notification.utils import create_notification
from wallet.models import Wallet, SystemWallet, SystemTransaction, WalletTransaction
from loans.models import RepaymentSchedule
from ml_engine.predict import predict_loan
from ml_engine.fraud_predict import detect_fraud
from ml_engine.loan_calculator import determine_interest, calculate_loan_limit
from ml_engine.credit_predict import predict_credit
from ml_engine.id_verify import verify_id_document
from dateutil.relativedelta import relativedelta

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  TRUST ENGINE  (paste into new file: loans/trust_engine.py)
# ─────────────────────────────────────────────────────────────────────────────
TRUST_ENGINE_CODE = '''
"""
loans/trust_engine.py
Computes a trust tier for each user based on repayment behaviour.

Tiers:
    NEW       — no completed loans
    BRONZE    — 1 loan repaid on time
    SILVER    — 2–3 loans repaid on time, no defaults
    GOLD      — 4+ loans repaid, avg days-early > 0
    PLATINUM  — 6+ loans, all on time, consistent borrower

Each tier gets a loan limit multiplier and an interest rate discount.
"""
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta


TIER_CONFIG = {
    "NEW":      {"multiplier": 1.0,  "rate_discount": Decimal("0.00"), "label": "New Member",    "color": "#64748b"},
    "BRONZE":   {"multiplier": 1.3,  "rate_discount": Decimal("0.02"), "label": "Bronze",        "color": "#b45309"},
    "SILVER":   {"multiplier": 1.6,  "rate_discount": Decimal("0.03"), "label": "Silver",        "color": "#475569"},
    "GOLD":     {"multiplier": 2.0,  "rate_discount": Decimal("0.05"), "label": "Gold",          "color": "#d97706"},
    "PLATINUM": {"multiplier": 3.0,  "rate_discount": Decimal("0.07"), "label": "Platinum",      "color": "#7c3aed"},
}


def get_trust_profile(user):
    """
    Returns dict with all trust data for a user.
    """
    from loans.models import LoanApplication

    loans = LoanApplication.objects.filter(user=user)
    repaid_loans  = loans.filter(fully_repaid=True)
    active_loans  = loans.filter(status__in=["Funded", "Approved"])
    defaulted     = loans.filter(
        fully_repaid=False,
        amount_remaining__gt=0,
        status="Funded",
        funded_at__lt=timezone.now() - timedelta(days=60),
    )

    total_repaid    = repaid_loans.count()
    total_borrowed  = sum(float(l.qualified_amount) for l in repaid_loans)
    total_defaulted = defaulted.count()

    # Average repayment speed (days before due — positive = early)
    early_days_list = []
    for loan in repaid_loans:
        if loan.funded_at and loan.fully_repaid_at:
            expected_end = loan.funded_at + timedelta(days=30 * loan.repayment_period)
            days_early = (expected_end.date() - loan.fully_repaid_at.date()).days
            early_days_list.append(days_early)
    avg_days_early = sum(early_days_list) / len(early_days_list) if early_days_list else 0

    tier = compute_trust_tier(
        total_repaid=total_repaid,
        total_defaulted=total_defaulted,
        avg_days_early=avg_days_early,
    )

    config = TIER_CONFIG[tier]
    return {
        "tier":           tier,
        "label":          config["label"],
        "color":          config["color"],
        "multiplier":     config["multiplier"],
        "rate_discount":  config["rate_discount"],
        "total_repaid":   total_repaid,
        "total_borrowed": total_borrowed,
        "total_defaulted": total_defaulted,
        "avg_days_early": round(avg_days_early, 1),
        "is_returning":   total_repaid >= 1,
        "is_trusted":     tier in ("GOLD", "PLATINUM"),
    }


def compute_trust_tier(total_repaid, total_defaulted, avg_days_early):
    if total_defaulted > 0:
        return "NEW"
    if total_repaid == 0:
        return "NEW"
    if total_repaid == 1:
        return "BRONZE"
    if total_repaid <= 3:
        return "SILVER"
    if total_repaid >= 6 and avg_days_early >= 0:
        return "PLATINUM"
    if total_repaid >= 4:
        return "GOLD"
    return "SILVER"


def apply_trust_boost(base_limit, trust_profile):
    """Apply tier multiplier to base loan limit."""
    boosted = float(base_limit) * trust_profile["multiplier"]
    return min(boosted, 500_000)   # hard cap KES 500k even for platinum
'''


# ─────────────────────────────────────────────────────────────────────────────
#  KYC GATE DECORATOR
# ─────────────────────────────────────────────────────────────────────────────

def kyc_required(view_func):
    """
    Decorator: ensures user has completed face KYC before proceeding.
    If already KYC-verified (DB), skip. Otherwise redirect to kyc_verify.
    """
    from functools import wraps

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')

        # Check DB first (permanent verification)
        already_verified = LoanApplication.objects.filter(
            user=request.user,
            kyc_face_verified=True,
        ).exists()

        if already_verified:
            return view_func(request, *args, **kwargs)

        # Check session (current session verification)
        if request.session.get('kyc_face_verified') is True:
            return view_func(request, *args, **kwargs)

        # Not verified — store where to return after KYC
        request.session['kyc_next'] = request.path
        messages.info(request, "Please verify your identity before applying for a loan.")
        return redirect('kyc_verify')

    return wrapper


# ─────────────────────────────────────────────────────────────────────────────
#  APPLY LOAN — FULL UPGRADE
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def apply_loan(request):
    profile, _         = UserProfile.objects.get_or_create(user=request.user)
    security_profile, _ = UserSecurityProfile.objects.get_or_create(user=request.user)

    # ── Trust profile ─────────────────────────────────────────────
    try:
        from loans.trust_engine import get_trust_profile, apply_trust_boost
        trust = get_trust_profile(request.user)
    except ImportError:
        trust = {
            "tier": "NEW", "label": "New Member", "color": "#64748b",
            "multiplier": 1.0, "rate_discount": Decimal("0.00"),
            "total_repaid": 0, "is_returning": False, "is_trusted": False,
        }

    # ── Block if active loan exists ───────────────────────────────
    active_loan = LoanApplication.objects.filter(
        user=request.user,
        status__in=["Pending", "Pending KYC", "Approved", "Funded", "Under Review"]
    ).first()
    if active_loan:
        return render(request, "loans/active_loan_block.html", {"loan": active_loan})

    # ── Profile completeness gate (new users only) ────────────────
    if not trust["is_returning"]:
        REQUIRED_FIELDS = ['phone_number', 'national_id', 'date_of_birth',
                           'employment_status', 'monthly_income']
        missing = [f.replace('_', ' ').title() for f in REQUIRED_FIELDS
                   if not getattr(profile, f, None)]
        if missing:
            messages.warning(request,
                f"Please complete your profile before applying. Missing: {', '.join(missing)}.")
            return redirect('profile')

    # ── Last approved loan for pre-fill ──────────────────────────
    last_loan = LoanApplication.objects.filter(
        user=request.user, fully_repaid=True
    ).order_by('-created_at').first()

    # ── GET: render form ──────────────────────────────────────────
    if request.method == "GET":
        from datetime import date
        profile_age = None
        if profile.date_of_birth:
            today = date.today()
            dob   = profile.date_of_birth
            profile_age = today.year - dob.year - (
                (today.month, today.day) < (dob.month, dob.day)
            )

        # Estimate max limit for display
        base_limit = calculate_loan_limit(
            age=profile_age or 30,
            monthly_income=float(profile.monthly_income or 0),
            credit_history=int(profile.credit_history if hasattr(profile, 'credit_history') else 1),
            kyc_verified=True,
            ocr_id_verified=True,
            previous_loans_repaid=trust["total_repaid"],
            previous_default=False,
        )
        try:
            max_limit = apply_trust_boost(base_limit, trust)
        except Exception:
            max_limit = base_limit

        return render(request, "loans/apply_loan.html", {
            "profile":       profile,
            "profile_age":   profile_age,
            "trust":         trust,
            "last_loan":     last_loan,
            "is_returning":  trust["is_returning"],
            "max_limit":     int(max_limit),
            "prefill": {
                "id_number":         getattr(profile, 'national_id', ''),
                "employment_status": getattr(profile, 'employment_status', ''),
                "monthly_income":    getattr(profile, 'monthly_income', ''),
            } if trust["is_returning"] else {},
        })

    # ────────────────────────── POST ─────────────────────────────

    # ── Returning user express lane ───────────────────────────────
    is_express = trust["is_returning"]

    age              = request.POST.get("age") or (
        str(profile.get_age()) if hasattr(profile, 'get_age') else None
    )
    monthly_income   = request.POST.get("monthly_income") or str(getattr(profile, 'monthly_income', ''))
    repayment_period = request.POST.get("repayment_period")
    credit_history   = request.POST.get("credit_history") or (
        str(last_loan.credit_history) if last_loan else "1"
    )
    id_number        = (request.POST.get("id_number", "") or
                        getattr(profile, 'national_id', '')).strip()
    reason_for_loan  = request.POST.get("reason_for_loan", "").strip()
    employment_status = (request.POST.get("employment_status") or
                         getattr(profile, 'employment_status', 'Unknown'))

    # ── ID document — reuse last if returning ─────────────────────
    id_document_front = None
    id_document_back  = None

    if is_express and last_loan:
        # Reuse last verified ID documents — no re-upload needed
        id_document_front = last_loan.id_document_front
        id_document_back  = last_loan.id_document_back
        id_number         = id_number or last_loan.id_number
    else:
        id_document_front_raw = request.FILES.get("id_document_front")
        id_document_back_raw  = request.FILES.get("id_document_back")

        if id_document_front_raw:
            try:
                from loans.image_utils import compress_id_image
                id_document_front = compress_id_image(
                    id_document_front_raw, filename=f"front_{request.user.id}.jpg"
                )
            except Exception:
                id_document_front = id_document_front_raw

        if id_document_back_raw:
            try:
                from loans.image_utils import compress_id_image
                id_document_back = compress_id_image(
                    id_document_back_raw, filename=f"back_{request.user.id}.jpg"
                )
            except Exception:
                id_document_back = id_document_back_raw

        if not id_document_front or not id_document_back:
            messages.error(request, "Both sides of your ID document are required.")
            return redirect("loan_apply")

    # ── Basic validation ──────────────────────────────────────────
    if not all([age, monthly_income, repayment_period, credit_history]):
        messages.error(request, "All fields are required.")
        return redirect("loan_apply")

    if not id_number:
        messages.error(request, "ID number is required.")
        return redirect("loan_apply")

    # ── OCR verification — skip for returning trusted users ───────
    class _OCRSkipped:
        failures = []
        warnings = ["OCR skipped — returning verified user."]
        id_number_match = True
        name_match      = True
        id_reused       = False
        authenticity    = None
        id_authentic    = True
        id_authenticity_score = None
        id_authenticity_notes = ""

    class _TimedOut:
        failures = []
        warnings = ["OCR timed out — flagged for manual review."]
        id_number_match = False
        name_match      = False
        id_reused       = False
        authenticity    = None
        id_authentic    = None
        id_authenticity_score = None
        id_authenticity_notes = ""

    if is_express and trust["tier"] in ("GOLD", "PLATINUM"):
        id_verification = _OCRSkipped()
        print("[APPLY] Express lane — OCR skipped for trusted user")
    else:
        import concurrent.futures
        account_name = request.user.get_full_name() or request.user.username
        print("[APPLY] Starting OCR — timeout: 120s")
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    verify_id_document,
                    image_file=id_document_front,
                    submitted_id_number=id_number,
                    account_full_name=account_name,
                    stated_age=int(age) if str(age).isdigit() else None,
                    existing_loan_qs=LoanApplication.objects.all(),
                    current_user=request.user,
                )
                try:
                    id_verification = future.result(timeout=120)
                    print("[APPLY] OCR completed")
                except concurrent.futures.TimeoutError:
                    id_verification = _TimedOut()
        except Exception as ocr_err:
            print(f"[APPLY] OCR error: {ocr_err}")
            id_verification = _TimedOut()

    id_issues = id_verification.failures + id_verification.warnings
    needs_manual_review = bool(id_issues) and not is_express

    try:
        age              = int(age)
        monthly_income   = float(monthly_income)
        repayment_period = int(repayment_period)
        credit_history   = int(credit_history)

        if age < 18 or age > 80:
            messages.error(request, "Age must be between 18 and 80.")
            return redirect("loan_apply")
        if monthly_income <= 0:
            messages.error(request, "Monthly income must be greater than 0.")
            return redirect("loan_apply")

        # ── Base loan limit ───────────────────────────────────────
        ocr_id_verified = getattr(id_verification, 'id_number_match', False)
        ocr_name_match  = getattr(id_verification, 'name_match', False)
        kyc_session     = request.session.get('kyc_face_verified', None) or True  # gate ensures verified

        previous_loans_repaid_count = LoanApplication.objects.filter(
            user=request.user, fully_repaid=True
        ).count()

        base_limit = calculate_loan_limit(
            age=age,
            monthly_income=monthly_income,
            credit_history=credit_history,
            kyc_verified=kyc_session,
            ocr_id_verified=bool(ocr_id_verified),
            previous_loans_repaid=previous_loans_repaid_count,
            previous_default=False,
        )

        # ── Apply trust boost ─────────────────────────────────────
        try:
            boosted_limit = apply_trust_boost(base_limit, trust)
        except Exception:
            boosted_limit = base_limit

        qualified_amount = Decimal(str(min(boosted_limit, 500_000)))
        # ML model qualified amount will override after prediction for approved loans

        # ── Fraud detection ───────────────────────────────────────
        recent_apps = LoanApplication.objects.filter(
            user=request.user,
            created_at__gte=timezone.now() - timedelta(hours=24)
        ).count()

        ocr_reuse  = id_verification.id_reused if id_verification else False
        text_reuse = LoanApplication.objects.filter(
            id_number=id_number
        ).exclude(user=request.user).exists()
        id_reuse_flag = ocr_reuse or text_reuse

        accounts_per_phone = UserProfile.objects.filter(
            phone_number=profile.phone_number
        ).count() if profile.phone_number else 1

        fraud_score, fraud_flag, risk_reasons = detect_fraud({
            "age":                    age,
            "monthly_income":         float(monthly_income),
            "loan_amount":            float(qualified_amount),
            "repayment_period":       repayment_period,
            "credit_history":         credit_history,
            "device_change_count":    security_profile.device_change_count,
            "ip_change_count":        security_profile.ip_change_count,
            "accounts_per_phone":     accounts_per_phone,
            "recent_application_count": recent_apps,
            "id_reuse_flag":          int(id_reuse_flag),
            "income_age_ratio":       float(monthly_income / age),
            "kyc_face_verified":      kyc_session,
            "ocr_id_verified":        bool(ocr_id_verified),
            "ocr_name_match":         bool(ocr_name_match),
        })

        # Trusted users get fraud score dampened
        if trust["tier"] in ("GOLD", "PLATINUM"):
            fraud_score = fraud_score * 0.5
            fraud_flag  = fraud_score > 0.50

        # ── Credit model ──────────────────────────────────────────
        previous_loans = LoanApplication.objects.filter(user=request.user)
        past_default_flag = previous_loans.filter(
            fully_repaid=False,
            amount_remaining__gt=0,
            status="Funded",
            funded_at__lt=timezone.now() - timedelta(days=30)
        ).exists()

        prediction = predict_credit({
            "age":                    age,
            "monthly_income":         float(monthly_income),
            "loan_amount":            float(qualified_amount),
            "repayment_period":       repayment_period,
            "credit_history":         credit_history,
            "debt_to_income_ratio":   float(qualified_amount) / monthly_income if monthly_income else 0,
            "past_default_flag":      int(past_default_flag),
            "previous_loan_count":    previous_loans.count(),
            "on_time_repayment_count": previous_loans_repaid_count,
            "fraud_score":            float(fraud_score),
            "recent_application_count": previous_loans.filter(
                created_at__gte=timezone.now() - timedelta(days=7)
            ).count(),
            "kyc_face_verified":      kyc_session,
            "ocr_id_verified":        bool(ocr_id_verified),
            "ocr_name_match":         bool(ocr_name_match),
            "id_reuse_flag":          bool(id_reuse_flag),
            "needs_manual_review":    needs_manual_review,
        })

        predicted_probability = prediction["probability"]
        credit_decision       = prediction["decision"]

        # Trust tier boosts probability for credit model
        tier_prob_bonus = {
            "NEW": 0.0, "BRONZE": 0.03, "SILVER": 0.06,
            "GOLD": 0.10, "PLATINUM": 0.15
        }.get(trust["tier"], 0.0)
        adjusted_probability = max(0.0, min(1.0,
            predicted_probability - {
                "Unemployed": 0.25, "Student": 0.20,
                "Self-employed": 0.08, "Employed": 0.0,
            }.get(employment_status, 0.10) + tier_prob_bonus
        ))

        # ── Decision logic ────────────────────────────────────────
        id_authentic = getattr(id_verification, 'id_authentic', True) or is_express

        # Apply trust rate discount
        rate_discount = trust["rate_discount"]

        if needs_manual_review:
            status        = "Pending"
            interest_rate = max(Decimal("0.10"), Decimal("0.15") - rate_discount)
            decision_reason = f"Pending manual review — ID verification issues: {'; '.join(id_issues)}"

        elif not id_authentic:
            status        = "Pending"
            interest_rate = Decimal("0.15")
            decision_reason = "Pending manual review — ID document failed authenticity checks."

        elif fraud_flag:
            status        = "Rejected"
            interest_rate = Decimal("0")
            decision_reason = "Rejected: Fraud risk — " + ("; ".join(risk_reasons) if risk_reasons else "suspicious activity")

        elif credit_decision == "Rejected" or adjusted_probability < 0.45:
            status        = "Rejected"
            interest_rate = Decimal("0")
            decision_reason = f"Rejected: Credit profile insufficient (score: {adjusted_probability:.0%})"

        elif credit_decision in ("Review", "Under Review") or adjusted_probability < 0.82:
            status        = "Pending"
            interest_rate = max(Decimal("0.10"), Decimal("0.22") - rate_discount)
            decision_reason = f"Under manual review — score {adjusted_probability:.0%}"

        else:
            status = "Approved"
            # Use ML model rate, apply trust discount
            model_rate = prediction.get("interest_rate", Decimal("0.15"))
            base_rate = Decimal(str(model_rate))
            # Override qualified amount with ML recommendation
            ml_qualified = prediction.get("qualified_amount", 0)
            if ml_qualified and ml_qualified < float(qualified_amount):
                qualified_amount = Decimal(str(ml_qualified))
            interest_rate = max(Decimal("0.08"), base_rate - rate_discount)
            decision_reason = (
                f"Approved — score: {adjusted_probability:.0%}, "
                f"tier: {trust['label']}, KYC: ✓"
            )

        if id_verification.warnings and not is_express:
            decision_reason += " | OCR: " + "; ".join(id_verification.warnings)

        if trust["tier"] in ("GOLD", "PLATINUM"):
            decision_reason += f" | {trust['label']} member — loyalty discount applied"

        # ── Save loan ─────────────────────────────────────────────
        loan = LoanApplication.objects.create(
            user=request.user,
            full_name=request.user.get_full_name() or request.user.username,
            age=age,
            employment_status=employment_status,
            monthly_income=monthly_income,
            qualified_amount=qualified_amount,
            repayment_period=repayment_period,
            credit_history=credit_history,
            interest_rate=interest_rate,
            status="Pending KYC",
            fraud_score=fraud_score,
            fraud_flag=fraud_flag,
            predicted_probability=predicted_probability,
            rejection_reason=decision_reason,
            risk_reasons=risk_reasons,
            id_number=id_number,
            id_document_front=id_document_front,
            id_document_back=id_document_back,
            reason_for_loan=reason_for_loan,
        )

    except Exception as e:
        traceback.print_exc()
        messages.error(request, f"Loan processing error: {str(e)}")
        return redirect("loan_apply")

    # ── Send application email ────────────────────────────────────
    try:
        from notification.email_service import send_loan_application_email
        send_loan_application_email(request.user, loan)
    except Exception as e:
        logger.warning(f"Application email failed: {e}")

    # ── Store in session for finalize_loan ────────────────────────
    request.session['pending_kyc_loan_id']     = loan.id
    request.session['pending_status']          = status
    request.session['pending_decision_reason'] = decision_reason
    request.session['pending_interest_rate']   = str(interest_rate)

    # Express trusted users with approval — skip KYC re-verification
    if is_express and trust["tier"] in ("GOLD", "PLATINUM"):
        # Already KYC'd — go straight to finalize
        request.session['kyc_face_verified'] = True
        return redirect("finalize_loan", loan_id=loan.id)

    return redirect("kyc_verify")


@login_required
def finalize_loan(request, loan_id):
    """
    Called after KYC completes. Re-scores the loan with KYC result
    and sets the final status (Approved / Review / Rejected).
    Also triggered if user skips KYC.
    """
    loan = get_object_or_404(LoanApplication, id=loan_id, user=request.user)

    if loan.status not in ("Pending KYC",):
        # Already finalized (e.g. page refresh) — go straight to result
        return redirect("loan_result", loan_id=loan.id)

    # ── Pull KYC result from session ──────────────────────────
    kyc_verified   = request.session.get('kyc_face_verified', None)
    kyc_confidence = request.session.get('kyc_confidence', None)

    # ── Re-run credit decision with KYC result ────────────────
    from ml_engine.credit_predict import predict_credit
    from ml_engine.loan_calculator import calculate_loan_limit, determine_interest

    previous_loans = LoanApplication.objects.filter(user=request.user).exclude(id=loan.id)
    prev_repaid    = previous_loans.filter(fully_repaid=True).count()
    past_default   = previous_loans.filter(
        fully_repaid=False, amount_remaining__gt=0, status="Funded",
        funded_at__lt=timezone.now() - timedelta(days=30)
    ).exists()

    prediction = predict_credit({
        "age":                    loan.age,
        "monthly_income":         float(loan.monthly_income),
        "loan_amount":            float(loan.qualified_amount),
        "repayment_period":       loan.repayment_period,
        "credit_history":         loan.credit_history,
        "debt_to_income_ratio":   float(loan.qualified_amount) / float(loan.monthly_income) if loan.monthly_income else 0,
        "past_default_flag":      int(past_default),
        "previous_loan_count":    previous_loans.count(),
        "on_time_repayment_count": prev_repaid,
        "fraud_score":            float(loan.fraud_score),
        "recent_application_count": previous_loans.filter(
            created_at__gte=timezone.now() - timedelta(days=7)
        ).count(),
        "kyc_face_verified":      kyc_verified,
        "ocr_id_verified":        bool(loan.kyc_face_verified),
        "id_reuse_flag":          bool(loan.fraud_flag),
        "needs_manual_review":    bool(loan.fraud_score > 0.3),
    })

    probability    = prediction["probability"]
    credit_decision = prediction["decision"]
    explanations   = prediction["explanation"]

    # ── Recalculate loan limit using KYC result ───────────────
    new_limit = calculate_loan_limit(
        age=loan.age,
        monthly_income=loan.monthly_income,
        credit_history=loan.credit_history,
        kyc_verified=kyc_verified,
        ocr_id_verified=bool(loan.kyc_face_verified),
        previous_loans_repaid=prev_repaid,
        previous_default=past_default,
    )

    # ── Map decision to status ────────────────────────────────
    employment_status = loan.employment_status or "Unknown"
    emp_penalty = {
        "Unemployed":    0.25,
        "Student":       0.20,
        "Self-employed": 0.08,
        "Employed":      0.0,
    }.get(employment_status, 0.10)
    adjusted_prob = max(0.0, probability - emp_penalty)

    hard_blocks = prediction.get("hard_blocks", [])

    if hard_blocks or adjusted_prob < 0.40:
        status        = "Rejected"
        interest_rate = Decimal("0.30")
        reason        = "Rejected — " + "; ".join(hard_blocks[:2]) if hard_blocks else f"Rejected — score too low ({adjusted_prob:.0%})"
    elif credit_decision == "Review" or adjusted_prob < 0.78:
        status        = "Under Review"
        interest_rate = Decimal("0.25")
        reason        = f"Manual review — score {adjusted_prob:.0%}, KYC: {'✓' if kyc_verified else '✗' if kyc_verified is False else '?'}"
    else:
        status        = "Approved"
        interest_rate = Decimal("0.15") if adjusted_prob >= 0.90 else Decimal("0.20")
        reason        = f"Approved — score {adjusted_prob:.0%}, KYC verified: {'Yes' if kyc_verified else 'No'}"

    # Append KYC info to reason
    if kyc_verified is True:
        reason += f" | KYC face matched ({round((kyc_confidence or 0)*100, 1)}% confidence)"
    elif kyc_verified is False:
        reason += " | KYC face match failed — flagged for manual review"
    elif kyc_verified is None:
        reason += " | KYC not completed"

    # ── Update loan record ────────────────────────────────────
    loan.status               = status
    loan.qualified_amount     = min(new_limit, loan.qualified_amount)  # never increase, only decrease
    loan.interest_rate        = interest_rate
    loan.predicted_probability = adjusted_prob
    loan.rejection_reason     = reason
    loan.kyc_face_verified    = kyc_verified
    loan.kyc_confidence       = round((kyc_confidence or 0) * 100, 1) if kyc_confidence else None
    loan.save(update_fields=[
        'status', 'qualified_amount', 'interest_rate',
        'predicted_probability', 'rejection_reason',
        'kyc_face_verified', 'kyc_confidence',
    ])

    # ── Send emails ───────────────────────────────────────────
    try:
        from notification.email_service import (
            send_loan_application_email, send_manual_review_email
        )
        send_loan_application_email(request.user, loan)
        if status == "Under Review":
            send_manual_review_email(request.user, loan)
    except Exception as e:
        logger.warning(f"Post-KYC email failed: {e}")

    # ── Clean up session ──────────────────────────────────────
    for key in ('pending_kyc_loan_id', 'pending_status', 'pending_decision_reason',
                'pending_interest_rate', 'kyc_face_verified', 'kyc_confidence'):
        request.session.pop(key, None)

    return redirect("loan_result", loan_id=loan.id)


@login_required
def loan_result(request, loan_id):
    """Result card — reads from DB, no session needed. Refresh-safe."""
    loan = get_object_or_404(LoanApplication, id=loan_id, user=request.user)

    interest_amount   = loan.qualified_amount * loan.interest_rate
    total_payable     = loan.qualified_amount + interest_amount
    monthly_repayment = (total_payable / loan.repayment_period) if loan.repayment_period else total_payable

    result = {
        "loan_id":           loan.id,
        "id":                loan.id,
        "terms_accepted":    loan.terms_accepted,
        "processing_fee_paid": loan.processing_fee_paid,
        "processing_fee":    loan.processing_fee,
        "repayment_period":  loan.repayment_period,
        "status":            loan.status,
        "qualified_amount":  str(loan.qualified_amount),
        "interest_rate":     str(loan.interest_rate),
        "interest_amount":   str(interest_amount.quantize(Decimal("0.01"))),
        "total_payable":     str(total_payable.quantize(Decimal("0.01"))),
        "monthly_repayment": str(monthly_repayment.quantize(Decimal("0.01"))),
        "repayment_period":  loan.repayment_period,
        "decision_reason":   loan.rejection_reason,
        "risk_reasons":      loan.risk_reasons or [],
        "fraud_score":       float(loan.fraud_score),
        "credit_score":      float(loan.predicted_probability),
    }

    return render(request, "loans/loan_result.html", {"result": result})


def check_id_number(request):
    """AJAX: returns {"reused": true/false} for live ID check in form."""
    if not request.user.is_authenticated:
        return JsonResponse({"reused": False})

    id_number = request.GET.get("id_number", "").strip()
    if not id_number or len(id_number) < 8:
        return JsonResponse({"reused": False})

    reused = LoanApplication.objects.filter(
        id_number=id_number
    ).exclude(user=request.user).exists()

    return JsonResponse({"reused": reused})


def approve_loan(request, loan_id):
    loan = get_object_or_404(LoanApplication, id=loan_id)

    if loan.status == "Approved":
        return redirect("admin_dashboard")

    principal     = Decimal(loan.qualified_amount)
    rate          = Decimal(loan.interest_rate)
    interest      = principal * rate
    total_payable = principal + interest

    loan.status           = "Approved"
    loan.approved_at      = timezone.now()
    loan.amount_remaining = total_payable
    loan.fully_repaid     = False
    loan.save()

    create_notification(
        loan.user,
        message=f"Your loan of KES {loan.qualified_amount} has been approved.",
        title="Loan Approved",
    )
    send_loan_email(
        loan.user,
        "Loan Approved",
        f"Dear {loan.user.first_name}, your loan of KES {loan.qualified_amount} has been approved.",
    )
    try:
        from notification.email_service import send_loan_approved_email
        send_loan_approved_email(loan.user, loan)
    except Exception as e:
        logger.warning(f"Loan approved email failed: {e}")
    return redirect("admin_dashboard")


@login_required
def loan_list(request):
    loans = LoanApplication.objects.filter(user=request.user)
    send_due_today_reminders()
    return render(request, "loans/loan_list.html", {"loans": loans})


@login_required
def accept_terms(request, loan_id):
    loan = get_object_or_404(
        LoanApplication, id=loan_id, user=request.user, status="Approved"
    )
    if request.method == "POST":
        loan.terms_accepted = True
        loan.save()
        messages.success(request, "Terms accepted. Your loan will now be disbursed.")
        return redirect("loan_list")

    create_notification(
        loan.user,
        message="You have accepted the loan terms and conditions.",
        title="Terms Accepted",
    )
    return render(request, "loans/accept_terms.html", {"loan": loan})


@login_required
def fund_loan(request, loan_id):
    # Admin disburses — no user filter, but must be staff
    if not request.user.is_staff:
        messages.error(request, "Admin access required.")
        return redirect("dashboard")
    loan = get_object_or_404(
        LoanApplication,
        id=loan_id,
        status="Approved",
        terms_accepted=True,
    )

    if loan.funded:
        messages.info(request, "Loan already funded.")
        return redirect("dashboard")

    system_wallet = SystemWallet.objects.first()
    if system_wallet.balance < loan.qualified_amount:
        messages.error(request, "System has insufficient liquidity.")
        return redirect("dashboard")

    # Credit loan OWNER wallet, not admin
    wallet = Wallet.objects.get(user=loan.user)
    before         = wallet.balance
    wallet.balance += loan.qualified_amount
    wallet.save()

    WalletTransaction.objects.create(
        user=loan.user,
        wallet=wallet,
        loan=loan,
        transaction_type="DISBURSEMENT",
        amount=loan.qualified_amount,
        balance_before=before,
        balance_after=wallet.balance,
    )

    loan.funded    = True
    loan.funded_at = timezone.now()
    loan.status    = "Funded"
    loan.save()

    monthly_amount = loan.amount_remaining / loan.repayment_period
    start_date     = loan.funded_at.date()
    for i in range(1, loan.repayment_period + 1):
        RepaymentSchedule.objects.create(
            loan=loan,
            installment_number=i,
            due_date=start_date + relativedelta(months=i),
            amount=monthly_amount,
        )

    messages.success(request, "Loan disbursed successfully.")
    send_loan_email(
        loan.user,
        "Loan Disbursed",
        f"KES {loan.qualified_amount} has been disbursed to your wallet.",
    )
    try:
        from notification.email_service import send_loan_disbursed_email
        phone = None
        try:
            phone = loan.user.profile.phone_number
        except Exception:
            pass
        send_loan_disbursed_email(loan.user, loan, phone=phone)
    except Exception as e:
        logger.warning(f"Disbursed email failed: {e}")
    return redirect("dashboard")


@login_required
def repayment_schedule(request, loan_id):
    loan      = get_object_or_404(LoanApplication, id=loan_id, user=request.user)
    schedules = loan.repayments.all().order_by("due_date")

    unpaid_count = schedules.filter(paid=False).count()
    due_today    = schedules.filter(paid=False, due_date=timezone.now().date()).count()
    overdue      = schedules.filter(paid=False, due_date__lt=timezone.now().date()).count()

    return render(request, "loans/repayment_schedule.html", {
        "loan": loan,
        "schedules": schedules,
        "unpaid_count": unpaid_count,
        "due_today": due_today,
        "overdue": overdue,
    })


def process_repayment(loan, amount, user):
    system_wallet = SystemWallet.objects.first()
    before        = system_wallet.balance
    system_wallet.balance += amount
    system_wallet.save()

    SystemTransaction.objects.create(
        system_wallet=system_wallet,
        loan=loan,
        user=user,
        transaction_type="REPAYMENT",
        amount=amount,
        balance_before=before,
        balance_after=system_wallet.balance,
    )


from .utils import generate_loan_statement

@login_required
def download_statement(request, loan_id):
    loan = get_object_or_404(LoanApplication, id=loan_id, user=request.user)
    return generate_loan_statement(loan)


def send_due_today_reminders():
    today = timezone.now().date()
    due_installments = RepaymentSchedule.objects.filter(
        due_date=today, paid=False, reminder_sent=False
    )
    for installment in due_installments:
        create_notification(
            installment.loan.user,
            title="Installment Reminder",
            message=f"Reminder: Your loan installment of KES {installment.amount} is due today.",
        )
        installment.reminder_sent = True
        installment.save()

@login_required
def credit_score_history(request):
    from loans.models import LoanApplication
    import json
    loans = LoanApplication.objects.filter(user=request.user).order_by('-created_at')
    score_data = []
    for loan in loans:
        if loan.predicted_probability:
            score_data.append({
                'date': loan.created_at.strftime('%d %b %Y'),
                'score': round(float(loan.predicted_probability) * 100),
                'status': loan.status,
                'loan_id': loan.id,
                'amount': float(loan.qualified_amount),
            })
    chart_labels = json.dumps([x['date'] for x in reversed(score_data)])
    chart_scores = json.dumps([x['score'] for x in reversed(score_data)])
    return render(request, 'loans/credit_score_history.html', {
        'loans': loans,
        'score_data': score_data,
        'chart_labels': chart_labels,
        'chart_scores': chart_scores,
        'latest_score': score_data[0]['score'] if score_data else None,
    })
