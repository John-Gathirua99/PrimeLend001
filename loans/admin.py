from django.contrib import admin
from .models import LoanApplication,RepaymentSchedule
from accounts.utils import send_sms
from notification.utils import create_notification



admin.site.register(RepaymentSchedule)


@admin.register(LoanApplication)

class LoanAdmin(admin.ModelAdmin):

    list_display = (
        'user',
        'qualified_amount',
        'interest_rate',
        'amount_remaining',
        'status',
        'created_at'
    )

    readonly_fields = (
        'qualified_amount',
        'interest_rate',
        'amount_remaining',
        'created_at',
        'approved_at',
        'risk_reasons'
    )

    list_filter = ('status',)
    search_fields = ('user__username',)







from decimal import Decimal
from django.utils import timezone

def approve_loan(modeladmin, request, queryset):
    for loan in queryset:

        if loan.status == "Approved":
            continue

        if not loan.processing_fee_paid:
            continue

        principal = loan.qualified_amount
        interest = principal * loan.interest_rate
        total_payable = principal + interest

        loan.status = "Approved"
        loan.amount_remaining = total_payable
        loan.approved_at = timezone.now()
        loan.fully_repaid = False

        loan.save()
        create_notification(
    loan.user,
    f"Your loan of KES {loan.qualified_amount} has been approved."
)



def reject_loans(self, request, queryset):
    for loan in queryset:
        loan.status = 'rejected'
        loan.save()

        phone = loan.user.userprofile.phone_number

        create_notification(
    loan.user,
    f"Loan of KES {loan.qualified_amount} has been rejected."
)

        send_sms(phone, "Your loan application was rejected.")


from .models import LoanAmount

@admin.register(LoanAmount)
class LoanAmountAdmin(admin.ModelAdmin):
    list_display = ('amount', 'is_active')
    list_editable = ('is_active',)


