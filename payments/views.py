import json
import logging
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction as db_transaction

from loans.models import LoanApplication
from .models import Payment
from .mpesa import stk_push
from wallet.models import Wallet, WalletTransaction, SystemWallet, SystemTransaction
from notification.utils import create_notification

logger = logging.getLogger(__name__)
is_admin = user_passes_test(lambda u: u.is_staff, login_url="login")


# ── Pay Processing Fee ────────────────────────────────────────
@login_required
def pay_processing_fee(request, loan_id):
    loan = get_object_or_404(LoanApplication, id=loan_id, user=request.user)

    if loan.processing_fee_paid:
        messages.warning(request, "Processing fee already paid.")
        return redirect("loan_result", loan_id=loan.id)

    try:
        profile = request.user.profile
    except Exception:
        messages.error(request, "Profile not found. Please complete your profile.")
        return redirect("profile")

    if not profile.phone_number:
        messages.error(request, "Add a phone number to your profile first.")
        return redirect("profile")

    fee = Decimal(str(loan.processing_fee))

    # Create payment record BEFORE calling M-Pesa
    payment = Payment.objects.create(
        user=request.user,
        loan=loan,
        payment_type="PROCESSING_FEE",
        amount=fee,
        phone_number=profile.phone_number,
        status="PENDING",
    )

    # Trigger M-Pesa STK push
    try:
        response = stk_push(
            phone=profile.phone_number,
            amount=int(fee),
            reference=f"FEE-{loan.id}",
            description="Loan Processing Fee",
        )
        logger.info(f"STK push response for loan {loan.id}: {response}")

        # Store checkout request ID for reliable callback matching
        checkout_id = (
            response.get("CheckoutRequestID") or
            response.get("checkoutRequestID", "")
        )
        if checkout_id:
            payment.checkout_request_id = checkout_id
            payment.save(update_fields=["checkout_request_id"])

        messages.success(request, "M-Pesa prompt sent to your phone. Enter PIN to complete.")
    except Exception as e:
        logger.error(f"STK push failed for loan {loan.id}: {e}")
        payment.status = "FAILED"
        payment.save(update_fields=["status"])
        messages.error(request, "M-Pesa request failed. Please try again.")

    return redirect("loan_result", loan_id=loan.id)


# ── M-Pesa Callback ───────────────────────────────────────────
@csrf_exempt
def mpesa_callback(request):
    """
    Safaricom calls this after STK push is completed or cancelled.
    Match by CheckoutRequestID stored on the Payment record.
    """
    try:
        data = json.loads(request.body)
        callback = data["Body"]["stkCallback"]
        checkout_id = callback.get("CheckoutRequestID", "")
        result_code = callback.get("ResultCode")

        # Find the matching payment by checkout ID
        try:
            payment = Payment.objects.get(
                checkout_request_id=checkout_id,
                status="PENDING",
            )
        except Payment.DoesNotExist:
            logger.warning(f"No pending payment found for checkout ID: {checkout_id}")
            return JsonResponse({"ResultCode": 0, "ResultDesc": "Accepted"})

        if result_code == 0:
            # Success — extract receipt number
            metadata = callback.get("CallbackMetadata", {}).get("Item", [])
            receipt = next(
                (i["Value"] for i in metadata if i["Name"] == "MpesaReceiptNumber"),
                ""
            )
            payment.status = "PAID"
            payment.mpesa_receipt = receipt
            payment.save()

            loan = payment.loan
            loan.processing_fee_paid = True
            loan.save(update_fields=["processing_fee_paid"])

            create_notification(
                payment.user,
                "Processing Fee Confirmed ✓",
                f"M-Pesa payment of KES {payment.amount} received (ref: {receipt}). "
                f"Your loan #{loan.id} is now under review."
            )
            logger.info(f"Processing fee paid for loan {loan.id}, receipt {receipt}")
        else:
            # User cancelled or timed out
            payment.status = "FAILED"
            payment.save(update_fields=["status"])
            create_notification(
                payment.user,
                "Payment Failed",
                f"M-Pesa payment for loan #{payment.loan.id} was not completed. Please try again."
            )

    except Exception as e:
        logger.error(f"M-Pesa callback error: {e}")

    return JsonResponse({"ResultCode": 0, "ResultDesc": "Accepted"})


# ── Disburse Loan (Admin) ─────────────────────────────────────
@login_required
@is_admin
@db_transaction.atomic
def disburse_loan(request, loan_id):
    loan = get_object_or_404(LoanApplication, id=loan_id)

    if loan.status == "Funded":
        messages.warning(request, "Loan already disbursed.")
        return redirect("admin_loan_dashboard")

    if loan.status != "Approved":
        messages.error(request, "Only approved loans can be disbursed.")
        return redirect("admin_loan_dashboard")

    amount = loan.qualified_amount

    # Check system wallet has enough funds
    system_wallet = SystemWallet.objects.select_for_update().first()
    if not system_wallet:
        messages.error(request, "System wallet not configured.")
        return redirect("admin_loan_dashboard")

    if not system_wallet.can_fund(amount):
        messages.error(
            request,
            f"Insufficient system wallet funds. "
            f"Available: KES {system_wallet.balance - system_wallet.minimum_reserve:,.2f}"
        )
        return redirect("admin_loan_dashboard")

    # Credit user wallet
    user_wallet, _ = Wallet.objects.select_for_update().get_or_create(user=loan.user)
    wallet_balance_before = user_wallet.balance
    user_wallet.balance += amount
    user_wallet.save()

    # Deduct from system wallet
    sys_balance_before = system_wallet.balance
    system_wallet.balance -= amount
    system_wallet.save()

    # Record wallet transaction
    WalletTransaction.objects.create(
        wallet=user_wallet,
        user=loan.user,
        loan=loan,
        transaction_type="DISBURSEMENT",
        amount=amount,
        balance_before=wallet_balance_before,
        balance_after=user_wallet.balance,
        status="Completed",
        description=f"Loan disbursement — Loan #{loan.id}",
    )

    # Record system transaction
    SystemTransaction.objects.create(
        system_wallet=system_wallet,
        loan=loan,
        user=loan.user,
        transaction_type="DISBURSEMENT",
        amount=amount,
        balance_before=sys_balance_before,
        balance_after=system_wallet.balance,
    )

    # Record payment entry
    Payment.objects.create(
        user=loan.user,
        loan=loan,
        payment_type="DISBURSEMENT",
        amount=amount,
        phone_number=getattr(getattr(loan.user, "userprofile", None), "phone_number", ""),
        status="PAID",
    )

    # Update loan status
    loan.status = "Funded"
    loan.funded = True
    loan.funded_at = __import__("django.utils.timezone", fromlist=["timezone"]).timezone.now()
    loan.amount_remaining = amount + (amount * loan.interest_rate)
    loan.save()

    create_notification(
        loan.user,
        "Loan Disbursed 💰",
        f"KES {amount:,} has been credited to your wallet. "
        f"Repayment starts immediately — KES {loan.amount_remaining / loan.repayment_period:,.2f}/month."
    )

    messages.success(
        request,
        f"Loan #{loan.id} disbursed — KES {amount:,} credited to {loan.user.username}'s wallet."
    )
    return redirect("admin_loan_dashboard")

# ── M-Pesa STK Repayment ──────────────────────────────────────
@login_required
def mpesa_repay_loan(request, loan_id):
    """Trigger M-Pesa STK push for loan repayment."""
    from decimal import Decimal
    loan = get_object_or_404(LoanApplication, id=loan_id, user=request.user)

    if loan.status not in ["Funded", "Overdue"]:
        messages.error(request, "This loan is not active.")
        return redirect("wallet_dashboard")

    try:
        profile = request.user.profile
    except Exception:
        messages.error(request, "Profile not found.")
        return redirect("profile")

    if not profile.phone_number:
        messages.error(request, "Add a phone number to your profile first.")
        return redirect("profile")

    if request.method == "POST":
        try:
            amount = Decimal(request.POST.get("amount", "0"))
        except Exception:
            messages.error(request, "Invalid amount.")
            return redirect("wallet_dashboard")

        if amount <= 0:
            messages.error(request, "Enter a valid amount.")
            return redirect("wallet_dashboard")

        # Cap at remaining balance
        amount = min(amount, loan.amount_remaining)

        payment = Payment.objects.create(
            user=request.user,
            loan=loan,
            payment_type="REPAYMENT",
            amount=amount,
            phone_number=profile.phone_number,
            status="PENDING",
        )

        try:
            response = stk_push(
                phone=profile.phone_number,
                amount=int(amount),
                reference="RPY-{}".format(loan.id),
                description="Loan Repayment",
            )
            checkout_id = response.get("CheckoutRequestID", "")
            if checkout_id:
                payment.checkout_request_id = checkout_id
                payment.save(update_fields=["checkout_request_id"])
            messages.success(
                request,
                "M-Pesa prompt sent to {}. Enter your PIN to complete repayment.".format(
                    profile.phone_number
                )
            )
        except Exception as e:
            logger.error("STK repayment push failed for loan {}: {}".format(loan.id, e))
            payment.status = "FAILED"
            payment.save(update_fields=["status"])
            messages.error(request, "M-Pesa request failed. Please try again.")

    return redirect("wallet_dashboard")


# ── Repayment Callback ────────────────────────────────────────
@csrf_exempt
def repayment_callback(request):
    """Safaricom calls this after repayment STK push completes."""
    try:
        data = json.loads(request.body)
        callback = data["Body"]["stkCallback"]
        checkout_id = callback.get("CheckoutRequestID", "")
        result_code = callback.get("ResultCode")

        try:
            payment = Payment.objects.get(
                checkout_request_id=checkout_id,
                status="PENDING",
                payment_type="REPAYMENT",
            )
        except Payment.DoesNotExist:
            logger.warning("No pending repayment for checkout ID: {}".format(checkout_id))
            return JsonResponse({"ResultCode": 0, "ResultDesc": "Accepted"})

        if result_code == 0:
            metadata = callback.get("CallbackMetadata", {}).get("Item", [])
            receipt = next(
                (i["Value"] for i in metadata if i["Name"] == "MpesaReceiptNumber"), ""
            )
            amount_paid = next(
                (i["Value"] for i in metadata if i["Name"] == "Amount"),
                float(payment.amount)
            )

            payment.status = "PAID"
            payment.mpesa_receipt = receipt
            payment.save()

            from decimal import Decimal
            loan = payment.loan
            amount_dec = Decimal(str(amount_paid))

            # Reduce loan balance
            loan.amount_remaining = max(Decimal("0"), loan.amount_remaining - amount_dec)
            if loan.amount_remaining <= 0:
                loan.amount_remaining = Decimal("0")
                loan.fully_repaid = True
                loan.status = "Repaid"
                try:
                    from django.utils import timezone
                    loan.fully_repaid_at = timezone.now().date()
                except Exception:
                    pass
                try:
                    from loans.trust_engine import boost_trust_tier
                    boost_trust_tier(loan.user)
                except Exception:
                    pass
            loan.save()

            # Record wallet transactions
            try:
                from wallet.models import Wallet, WalletTransaction, SystemWallet, SystemTransaction
                user_wallet, _ = Wallet.objects.get_or_create(user=payment.user)
                sys_wallet = SystemWallet.objects.first()

                bal_before = user_wallet.balance
                user_wallet.balance = max(Decimal("0"), user_wallet.balance - amount_dec)
                user_wallet.save()

                WalletTransaction.objects.create(
                    wallet=user_wallet,
                    user=payment.user,
                    loan=loan,
                    transaction_type="REPAYMENT",
                    amount=amount_dec,
                    balance_before=bal_before,
                    balance_after=user_wallet.balance,
                    status="Completed",
                    description="M-Pesa repayment — ref {}".format(receipt),
                )

                if sys_wallet:
                    sys_before = sys_wallet.balance
                    sys_wallet.balance += amount_dec
                    sys_wallet.save()
                    SystemTransaction.objects.create(
                        system_wallet=sys_wallet,
                        loan=loan,
                        user=payment.user,
                        transaction_type="REPAYMENT",
                        amount=amount_dec,
                        balance_before=sys_before,
                        balance_after=sys_wallet.balance,
                    )
            except Exception as e:
                logger.error("Wallet update error on repayment callback: {}".format(e))

            if loan.fully_repaid:
                create_notification(
                    payment.user,
                    "Loan Fully Repaid! 🎉",
                    "Congratulations! Loan #{} fully repaid. Your trust tier has been upgraded.".format(loan.id),
                    link="/wallet/",
                )
            else:
                create_notification(
                    payment.user,
                    "Repayment Confirmed ✓",
                    "KES {:,} received (ref: {}). Remaining: KES {:,}.".format(
                        int(amount_paid), receipt, int(loan.amount_remaining)
                    ),
                    link="/wallet/",
                )
        else:
            payment.status = "FAILED"
            payment.save(update_fields=["status"])
            create_notification(
                payment.user,
                "Repayment Failed",
                "M-Pesa repayment for loan #{} was not completed. Please try again.".format(
                    payment.loan.id
                ),
                link="/wallet/",
            )

    except Exception as e:
        logger.error("Repayment callback error: {}".format(e))

    return JsonResponse({"ResultCode": 0, "ResultDesc": "Accepted"})






