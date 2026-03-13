import uuid
from django.db import models
from django.contrib.auth.models import User
from loans.models import LoanApplication


class Wallet(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=10)
    description = models.TextField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - KES {self.balance}"

class WalletTransaction(models.Model):
    TRANSACTION_TYPES = (
        ("DISBURSEMENT", "Loan Disbursed"),
        ("REPAYMENT", "Loan Repayment"),
        ("WITHDRAWAL", "User Withdrawal"),
        ("DEPOSIT", "User Deposit"),
    )
    STATUS_CHOICES = (
        ("Pending", "Pending"),
        ("Completed", "Completed"),
        ("Failed", "Failed"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE,null=True,blank=True)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE,related_name='transactions',null=True)
    loan = models.ForeignKey(
        "loans.LoanApplication",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)

    description = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    balance_before = models.DecimalField(max_digits=10, decimal_places=2,null=True,blank=True)
    balance_after = models.DecimalField(max_digits=10, decimal_places=2,null=True,blank=True)
    status = models.CharField(max_length=20,
        choices=STATUS_CHOICES,
        default="Completed"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def generate_description(self):
        if self.transaction_type == "DISBURSEMENT":
            return f"Loan disbursed (Loan #{self.loan.id})" if self.loan else "Loan disbursed"

        if self.transaction_type == "REPAYMENT":
            return f"Loan repayment (Loan #{self.loan.id})" if self.loan else "Loan repayment"

        if self.transaction_type == "WITHDRAWAL":
            return "Withdrawal to M-Pesa"

        if self.transaction_type == "DEPOSIT":
            return "Wallet deposit"

        if self.transaction_type == "TOPUP":
            return "System wallet top-up"

        return "Wallet transaction"

    def save(self, *args, **kwargs):
        if not self.description:
            self.description = self.generate_description()
        super().save(*args, **kwargs)


    def __str__(self):
        return f"{self.user} - {self.transaction_type} - {self.amount}"



# system wallet

class SystemWallet(models.Model):
    name = models.CharField(max_length=50, default="Main Liquidity Pool")
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    minimum_reserve = models.DecimalField(max_digits=14, decimal_places=2, default=50000)

    updated_at = models.DateTimeField(auto_now=True)

    def can_fund(self, amount):
        return self.balance - amount >= self.minimum_reserve

    def __str__(self):
        return f"{self.name} - {self.balance}"


class SystemTransaction(models.Model):
    TRANSACTION_TYPES = (
        ("DISBURSEMENT", "Loan Disbursement"),
        ("REPAYMENT", "Loan Repayment"),
        ("TOPUP", "Admin Topup"),
        ("WITHDRAWAL", "Admin Withdrawal"),
    )

    system_wallet = models.ForeignKey(SystemWallet, on_delete=models.CASCADE)
    loan = models.ForeignKey("loans.LoanApplication", null=True, blank=True, on_delete=models.SET_NULL)
    user = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL)

    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    balance_before = models.DecimalField(max_digits=14, decimal_places=2)
    balance_after = models.DecimalField(max_digits=14, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transaction_type} - {self.amount}"



