from django.db import models
from django.contrib.auth.models import User


class Payment(models.Model):
    PAYMENT_TYPE_CHOICES = (
        ("PROCESSING_FEE", "Processing Fee"),
        ("DISBURSEMENT",   "Loan Disbursement"),
        ("REPAYMENT",      "Loan Repayment"),
    )
    STATUS_CHOICES = (
        ("PENDING",   "Pending"),
        ("PAID",      "Paid"),
        ("FAILED",    "Failed"),
    )

    user         = models.ForeignKey(User, on_delete=models.CASCADE)
    loan         = models.ForeignKey("loans.LoanApplication", on_delete=models.CASCADE)
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES)
    amount       = models.DecimalField(max_digits=10, decimal_places=2)
    phone_number = models.CharField(max_length=15, blank=True)
    status       = models.CharField(max_length=10, choices=STATUS_CHOICES, default="PENDING")

    # M-Pesa fields
    checkout_request_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    mpesa_receipt       = models.CharField(max_length=50,  blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.get_payment_type_display()} — {self.user.username} — {self.status}"