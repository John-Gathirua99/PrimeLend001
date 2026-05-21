from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal  
from django.utils import timezone
from django.core.exceptions import ValidationError


STATUS_CHOICES = (
    ('Pending', 'Pending'),
    ('Pending KYC', 'Pending KYC'),
    ('Under Review', 'Under Review'),
    ('Approved', 'Approved'),
    ('Rejected', 'Rejected'),
    ('Info Required', 'Info Required'),
    ('Funded', 'Funded'),
)


class LoanAmount(models.Model):
    amount = models.FloatField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"KES {self.amount}"
    
class LoanApplication(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    full_name = models.CharField(max_length=100)
    age = models.IntegerField()
    employment_status = models.CharField(max_length=50)
    monthly_income = models.FloatField()

    
    repayment_period = models.IntegerField(help_text="Months")
    credit_history = models.IntegerField(help_text="0 = Bad, 1 = Good")

    # for ai predict amount qualified
    qualified_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)


    id_number = models.CharField(max_length=20)
    

    id_document_front = models.FileField(
    upload_to='ids/front/',
    null=True,
    blank=True
)

    id_document_back = models.FileField(
        upload_to='ids/back/',
        null=True,
        blank=True
)


    reason_for_loan = models.TextField()

    documents_verified = models.BooleanField(default=False)

    kyc_face_verified = models.BooleanField(null=True, blank=True)
    kyc_confidence    = models.FloatField(null=True, blank=True)
    ai_explanation    = models.JSONField(null=True, blank=True)
    risk_level        = models.CharField(max_length=10, blank=True, default="")

   
    kyc_selfie        = models.ImageField(upload_to='kyc/selfies/', null=True, blank=True)
    

    id_authentic          = models.BooleanField(null=True, blank=True)
    id_authenticity_score = models.FloatField(null=True, blank=True)
    id_authenticity_notes = models.TextField(blank=True, default="")
    mrz_valid             = models.BooleanField(null=True, blank=True)
    ela_score             = models.FloatField(null=True, blank=True)

    # ✅ Keep ONE status field
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='Pending'
    )

    # 📅 Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
   
    admin_approved = models.BooleanField(default=False)
    approved_by    = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="approved_loans")
    funded = models.BooleanField(default=False)


    funded_at = models.DateTimeField(null=True, blank=True)
    terms_accepted = models.BooleanField(default=False)


    # 🤖 AI / fraud detection
    fraud_score = models.FloatField(default=0.0)
    fraud_flag = models.BooleanField(default=False)
    predicted_probability = models.FloatField(default=0.0)
    # admin states reason for loan rejection
    rejection_reason = models.TextField(blank=True, null=True)
    risk_reasons = models.JSONField(null=True, blank=True)

    previous_loan_count = models.IntegerField(default=0)
    on_time_repayment_count = models.IntegerField(default=0)
    last_default_flag = models.BooleanField(default=False)




    # loan fees
    processing_fee = models.PositiveIntegerField(default=10)
    processing_fee_paid = models.BooleanField(default=False)
    disbursed = models.BooleanField(default=False)

    interest_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=10.00   # 10% default
    )

    amount_remaining = models.DecimalField(max_digits=10, decimal_places=2,default=0)


    fully_repaid = models.BooleanField(default=False)

    
    # prevents multiple loan applications
    def clean(self):
        if not self.pk:  # only when creating new loan
            if LoanApplication.objects.filter(
                user=self.user,
                status__in=["Pending", "Approved"]
            ).exists():
                raise ValidationError("User already has an active loan.")



    def calculate_total_payable(self):
        principal = Decimal(self.qualified_amount)
        interest = principal * (self.interest_rate / Decimal(100))
        return principal + interest

    def initialize_loan_balance(self):
        total = self.calculate_total_payable()
        self.amount_remaining = total
        self.save()


    
    def save(self, *args, **kwargs):

        # If loan is being approved and amount_remaining is 0
        if self.status == "Approved" and self.amount_remaining == 0:

            principal = Decimal(str(self.qualified_amount))
            interest_rate = Decimal("0.10")  # 10%

            interest = principal * interest_rate
            total_payable = principal + interest

            self.amount_remaining = total_payable
            self.fully_repaid = False
            self.approved_at = timezone.now()

        super().save(*args, **kwargs)


    def __str__(self):
        return f"{self.full_name} - {self.qualified_amount} - {self.status}"








class RepaymentSchedule(models.Model):
    loan = models.ForeignKey(
        "LoanApplication",
        on_delete=models.CASCADE,
        related_name="repayments"
    )

    installment_number = models.IntegerField()
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    paid = models.BooleanField(default=False)
    paid_at = models.DateTimeField(null=True, blank=True)

    reminder_sent = models.BooleanField(default=False)

    def is_overdue(self):
        return not self.paid and self.due_date < timezone.now().date()

    def __str__(self):
        return f"Loan {self.loan.id} - Installment {self.installment_number}"





class LoanReviewMessage(models.Model):
    """
    Threaded messages between admin and applicant during loan review.
    """
    SENDER_CHOICES = [("admin", "Admin"), ("applicant", "Applicant")]

    loan       = models.ForeignKey(
        LoanApplication, on_delete=models.CASCADE, related_name="review_messages"
    )
    sender     = models.ForeignKey(User, on_delete=models.CASCADE)
    sender_type = models.CharField(max_length=10, choices=SENDER_CHOICES)
    message    = models.TextField()
    attachment = models.FileField(upload_to="review_docs/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read       = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"[{self.sender_type}] Loan #{self.loan_id} — {self.created_at:%d %b %Y}"


class AuditLog(models.Model):
    loan_id   = models.IntegerField()
    action    = models.CharField(max_length=100)
    note      = models.TextField(blank=True, default="")
    actor     = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.created_at:%d %b %H:%M}] Loan #{self.loan_id} — {self.action} by {self.actor}"


class SystemSettings(models.Model):
    """Global system configuration — singleton (id=1)"""
    loans_enabled            = models.BooleanField(default=True)
    min_loan_amount          = models.IntegerField(default=1000)
    max_loan_amount_new      = models.IntegerField(default=10000)
    max_loan_amount_bronze   = models.IntegerField(default=30000)
    max_loan_amount_silver   = models.IntegerField(default=75000)
    max_loan_amount_gold     = models.IntegerField(default=150000)
    max_loan_amount_platinum = models.IntegerField(default=500000)
    min_interest_rate        = models.FloatField(default=10.0)
    max_interest_rate        = models.FloatField(default=25.0)
    maintenance_message      = models.TextField(blank=True)
    updated_at               = models.DateTimeField(auto_now=True)
    updated_by               = models.ForeignKey(
        "auth.User", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="system_settings"
    )

    class Meta:
        verbose_name = "System Settings"

    def __str__(self):
        return f"System Settings (loans={'ON' if self.loans_enabled else 'OFF'})"
