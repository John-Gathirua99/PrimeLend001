from django.contrib import admin
from decimal import Decimal
from django.utils import timezone
from loans.models import LoanApplication


@admin.action(description="Approve selected loans")
def approve_loan(modeladmin, request, queryset):
    for loan in queryset:

        if not loan.processing_fee_paid:
            continue  # skip if not paid

        if loan.status == "Approved":
            continue  # skip already approved

        principal = Decimal(str(loan.loan_amount.amount))
        interest_rate = Decimal("0.10")  # 10%

        interest = principal * interest_rate
        total_payable = principal + interest

        loan.status = "Approved"
        loan.approved_at = timezone.now()
        loan.amount_remaining = total_payable
        loan.fully_repaid = False

        loan.save()



