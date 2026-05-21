from loans.models import LoanApplication
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from notification.models import Notification
from django.db.models import Sum


@login_required
def user_dashboard(request):
    user = request.user
    all_loans = LoanApplication.objects.filter(user=user).order_by("-created_at")
    active_loan = all_loans.filter(status="Funded", fully_repaid=False).first()
    latest_loan = all_loans.first()

    # Wallet
    wallet_balance = 0
    try:
        from wallet.models import Wallet
        w = Wallet.objects.filter(user=user).first()
        wallet_balance = float(w.balance) if w else 0
    except Exception:
        pass

    # Trust tier
    trust_tier = "NEW"
    trust_progress = 0
    tier_max = {"NEW": 10000, "BRONZE": 30000, "SILVER": 75000, "GOLD": 150000, "PLATINUM": 500000}
    tier_order = ["NEW", "BRONZE", "SILVER", "GOLD", "PLATINUM"]
    try:
        profile = user.profile
        trust_tier = getattr(profile, "trust_tier", "NEW") or "NEW"
        tier_idx = tier_order.index(trust_tier) if trust_tier in tier_order else 0
        tier_progress_pct = ((tier_idx) / (len(tier_order) - 1)) * 100
    except Exception:
        tier_progress_pct = 0

    # Stats
    total_borrowed = all_loans.filter(status="Funded").aggregate(t=Sum("qualified_amount"))["t"] or 0
    total_repaid = all_loans.filter(fully_repaid=True).count()
    pending_count = all_loans.filter(status__in=["Pending", "Under Review", "Pending KYC"]).count()

    # Next payment
    next_payment = None
    if active_loan:
        try:
            from loans.models import RepaymentSchedule
            next_payment = RepaymentSchedule.objects.filter(
                loan=active_loan, paid=False
            ).order_by("due_date").first()
        except Exception:
            pass

    # Notifications
    notifications = Notification.objects.filter(user=user).order_by("-created_at")[:5]
    unread_notifications = Notification.objects.filter(user=user, is_read=False).count()

    # Loan timeline status
    timeline_steps = []
    if latest_loan:
        steps = [
            ("Applied", "bi-send", True),
            ("KYC Verified", "bi-person-check", latest_loan.kyc_face_verified or False),
            ("Under Review", "bi-search", latest_loan.status not in ["Pending", "Pending KYC"]),
            ("Approved", "bi-check-circle", latest_loan.status in ["Approved", "Funded"]),
            ("Fee Paid", "bi-credit-card", getattr(latest_loan, "processing_fee_paid", False)),
            ("Funded", "bi-wallet2", latest_loan.status == "Funded"),
        ]
        if latest_loan.status == "Rejected":
            steps = [("Applied", "bi-send", True), ("Reviewed", "bi-search", True), ("Rejected", "bi-x-circle", True)]
        timeline_steps = steps

    return render(request, "dashboard/dashboard.html", {
        "loans": all_loans[:10],
        "active_loan": active_loan,
        "latest_loan": latest_loan,
        "wallet_balance": wallet_balance,
        "trust_tier": trust_tier,
        "tier_progress_pct": tier_progress_pct,
        "tier_max": tier_max.get(trust_tier, 10000),
        "total_borrowed": total_borrowed,
        "total_repaid": total_repaid,
        "pending_count": pending_count,
        "next_payment": next_payment,
        "notifications": notifications,
        "unread_notifications": unread_notifications,
        "timeline_steps": timeline_steps,
    })


@login_required
def loan_detail(request, loan_id):
    loan = get_object_or_404(LoanApplication, id=loan_id, user=request.user)
    return render(request, "dashboard/loan_detail.html", {"loan": loan})
