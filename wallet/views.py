import logging
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import transaction as db_transaction
from django.db import models
from django.http import HttpResponse

from loans.models import LoanApplication
from .models import Wallet, WalletTransaction, SystemWallet, SystemTransaction
from notification.utils import create_notification

from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors

logger = logging.getLogger(__name__)
is_admin = user_passes_test(lambda u: u.is_staff, login_url="login")


# ── Wallet Dashboard ──────────────────────────────────────────
@login_required
def wallet_dashboard(request):
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    recent_txns = WalletTransaction.objects.filter(
        wallet=wallet
    ).order_by("-created_at")[:10]

    # Active loan for quick repay button
    active_loan = LoanApplication.objects.filter(
        user=request.user, status="Funded", fully_repaid=False
    ).first()

    return render(request, "wallet/wallet_dashboard.html", {
        "wallet":      wallet,
        "recent_txns": recent_txns,
        "active_loan": active_loan,
    })


# ── Repay Loan ────────────────────────────────────────────────
@login_required
@db_transaction.atomic
def repay_loan(request, loan_id):
    loan = get_object_or_404(
        LoanApplication, id=loan_id, user=request.user, status="Funded"
    )

    if request.method != "POST":
        return redirect("wallet_dashboard")

    try:
        amount = Decimal(request.POST.get("amount", "0"))
    except Exception:
        messages.error(request, "Invalid amount.")
        return redirect("loan_detail", loan_id=loan.id)

    if amount <= 0:
        messages.error(request, "Amount must be greater than zero.")
        return redirect("loan_detail", loan_id=loan.id)

    user_wallet = Wallet.objects.select_for_update().get(user=request.user)
    system_wallet = SystemWallet.objects.select_for_update().first()

    if user_wallet.balance < amount:
        messages.error(request, "Insufficient wallet balance.")
        return redirect("loan_detail", loan_id=loan.id)

    # Cap at remaining balance
    amount = min(amount, loan.amount_remaining)

    wallet_before = user_wallet.balance
    sys_before    = system_wallet.balance

    # Move money: user wallet → system wallet
    user_wallet.balance -= amount
    user_wallet.save()

    system_wallet.balance += amount
    system_wallet.save()

    # Reduce loan balance
    loan.amount_remaining -= amount
    if loan.amount_remaining <= 0:
        loan.amount_remaining = Decimal("0")
        loan.fully_repaid = True
        loan.status = "Repaid"
    loan.save()

    # Record transactions
    WalletTransaction.objects.create(
        wallet=user_wallet,
        user=request.user,
        loan=loan,
        transaction_type="REPAYMENT",
        amount=amount,
        balance_before=wallet_before,
        balance_after=user_wallet.balance,
        status="Completed",
        description=f"Loan repayment — Loan #{loan.id}",
    )

    SystemTransaction.objects.create(
        system_wallet=system_wallet,
        loan=loan,
        user=request.user,
        transaction_type="REPAYMENT",
        amount=amount,
        balance_before=sys_before,
        balance_after=system_wallet.balance,
    )

    if loan.fully_repaid:
        msg = f"🎉 Loan #{loan.id} fully repaid! Congratulations."
        create_notification(request.user, "Loan Fully Repaid 🎉", msg)
        messages.success(request, msg)
    else:
        remaining = loan.amount_remaining
        create_notification(
            request.user,
            "Repayment Received",
            f"KES {amount:,} repayment received. Remaining: KES {remaining:,}."
        )
        messages.success(request, f"Repayment of KES {amount:,} successful. Remaining: KES {remaining:,}.")

    return redirect("loan_detail", loan_id=loan.id)


# ── Withdraw to M-Pesa ────────────────────────────────────────
@login_required
@db_transaction.atomic
def withdraw_to_mpesa(request):
    messages.info(request, "Withdrawals are currently being processed manually. Contact support to withdraw funds.")
    return redirect("wallet_dashboard")

    # Try both common profile accessors
    phone = None
    try:
        phone = request.user.profile.phone_number
    except Exception:
        pass
    if not phone:
        try:
            phone = request.user.profile.phone_number
        except Exception:
            pass

    if not phone:
        messages.error(request, "Please add a phone number to your profile before withdrawing.")
        return redirect("profile")

    # Normalise phone: strip spaces/dashes, ensure starts with 254
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    elif phone.startswith("+"):
        phone = phone[1:]

    if amount <= 0:
        messages.error(request, "Amount must be greater than zero.")
        return redirect("wallet_dashboard")

    wallet = Wallet.objects.select_for_update().get(user=request.user)

    if wallet.balance < amount:
        messages.error(request, "Insufficient wallet balance.")
        return redirect("wallet_dashboard")

    wallet_before = wallet.balance
    wallet.balance -= amount
    wallet.save()

    txn = WalletTransaction.objects.create(
        wallet=wallet,
        user=request.user,
        transaction_type="WITHDRAWAL",
        amount=amount,
        balance_before=wallet_before,
        balance_after=wallet.balance,
        status="Pending",
        description="Withdrawal to M-Pesa",
    )

    # Trigger M-Pesa B2C
    try:
        from payments.mpesa import b2c_payment
        b2c_payment(phone, amount, reference=f"WDR-{txn.id}")
        txn.status = "Completed"
        txn.save(update_fields=["status"])
        create_notification(
            request.user,
            "Withdrawal Initiated 💸",
            f"KES {amount:,} withdrawal to M-Pesa is being processed."
        )
        messages.success(request, "Withdrawal initiated. M-Pesa will process shortly.")
    except Exception as e:
        logger.error(f"B2C payment failed for user {request.user.id}: {e}")
        # Reverse the deduction
        wallet.balance += amount
        wallet.save()
        txn.status = "Failed"
        txn.save(update_fields=["status"])
        messages.error(request, "Withdrawal failed. Your balance has been restored.")

    return redirect("wallet_dashboard")


# ── Transaction History ───────────────────────────────────────
@login_required
def transaction_history(request):
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    transactions = WalletTransaction.objects.filter(
        wallet=wallet
    ).order_by("-created_at")

    return render(request, "wallet/transaction_history.html", {
        "wallet":       wallet,
        "transactions": transactions,
    })


# ── User Wallet History ───────────────────────────────────────
@login_required
def user_wallet_history(request):
    transactions = WalletTransaction.objects.filter(
        user=request.user
    ).order_by("-created_at")

    return render(request, "wallet/user_wallet_history.html", {
        "transactions": transactions,
    })


# ── Download Statement PDF ────────────────────────────────────
@login_required
def download_user_statement(request):
    transactions = WalletTransaction.objects.filter(
        user=request.user
    ).order_by("-created_at")

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = "attachment; filename=wallet_statement.pdf"

    doc = SimpleDocTemplate(response, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("<b>PrimeLend AI — Wallet Statement</b>", styles["Title"]))
    elements.append(Paragraph(
        f"Account: {request.user.get_full_name() or request.user.username} "
        f"| Email: {request.user.email}",
        styles["Normal"]
    ))
    elements.append(Spacer(1, 12))

    data = [["Date", "Type", "Description", "Amount (KES)", "Balance (KES)"]]
    for t in transactions:
        data.append([
            t.created_at.strftime("%Y-%m-%d %H:%M"),
            t.get_transaction_type_display(),
            t.description or "—",
            f"{t.amount:,.2f}",
            f"{t.balance_after:,.2f}" if t.balance_after is not None else "—",
        ])

    table = Table(data, repeatRows=1, colWidths=[90, 90, 160, 80, 80])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("GRID",       (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("ALIGN",      (3, 0), (-1, -1), "RIGHT"),
    ]))
    elements.append(table)
    doc.build(elements)
    return response


# ── Admin Finance Dashboard ───────────────────────────────────
@login_required
@is_admin
def admin_finance_dashboard(request):
    wallet = SystemWallet.objects.first()

    transactions = SystemTransaction.objects.select_related(
        "loan", "user"
    ).order_by("-created_at")

    total_disbursed = SystemTransaction.objects.filter(
        transaction_type="DISBURSEMENT"
    ).aggregate(t=models.Sum("amount"))["t"] or 0

    total_repaid = SystemTransaction.objects.filter(
        transaction_type="REPAYMENT"
    ).aggregate(t=models.Sum("amount"))["t"] or 0

    return render(request, "wallet/finance_dashboard.html", {
        "wallet":           wallet,
        "transactions":     transactions,
        "total_disbursed":  total_disbursed,
        "total_repaid":     total_repaid,
        "net_outstanding":  total_disbursed - total_repaid,
    })


# ── Admin Top-up System Wallet ────────────────────────────────
@login_required
@is_admin
def admin_topup(request):
    if request.method != "POST":
        return redirect("admin_finance_dashboard")

    try:
        amount = Decimal(request.POST.get("amount", "0"))
        if amount <= 0:
            raise ValueError
    except Exception:
        messages.error(request, "Invalid top-up amount.")
        return redirect("admin_finance_dashboard")

    wallet = SystemWallet.objects.first()
    if not wallet:
        messages.error(request, "System wallet not found.")
        return redirect("admin_finance_dashboard")

    before = wallet.balance
    wallet.balance += amount
    wallet.save()

    SystemTransaction.objects.create(
        system_wallet=wallet,
        transaction_type="TOPUP",
        amount=amount,
        balance_before=before,
        balance_after=wallet.balance,
        user=request.user,
    )

    create_notification(
        request.user,
        "System Wallet Top-up",
        f"KES {amount:,} added to system wallet by {request.user.username}."
    )

    messages.success(request, f"System wallet topped up by KES {amount:,}.")
    return redirect("admin_finance_dashboard")