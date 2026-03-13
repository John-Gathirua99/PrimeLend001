from django.db import models
from django.contrib.auth.models import User

class UserProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    EMPLOYMENT_CHOICES = [
        ("Employed",      "Employed"),
        ("Self-employed", "Self-employed"),
        ("Unemployed",    "Unemployed"),
        ("Student",       "Student"),
    ]

    # Immutable fields
    phone_number = models.CharField(max_length=15, unique=True, null=True, blank=True)
    id_document = models.FileField(upload_to='ids/', null=True, blank=True)
    is_id_verified = models.BooleanField(default=False)
    is_phone_verified = models.BooleanField(default=False)
    otp_code = models.CharField(max_length=6, blank=True, null=True)

    face_embedding    = models.TextField(null=True, blank=True)
    face_kyc_verified = models.BooleanField(default=False)

    # Editable fields for profile
    full_name = models.CharField(max_length=150, blank=True, null=True)
    age = models.PositiveIntegerField(blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    county = models.CharField(max_length=50, blank=True, null=True)

    
    national_id       = models.CharField(max_length=20, blank=True, default="")
    date_of_birth     = models.DateField(null=True, blank=True)
    employment_status = models.CharField(max_length=30, blank=True, default="", choices=EMPLOYMENT_CHOICES)
    monthly_income    = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Financial info
    credit_score = models.IntegerField(default=0)
    monthly_income = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return self.user.username




class UserSecurityProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    first_device = models.CharField(max_length=255, null=True, blank=True)
    last_device = models.CharField(max_length=255, null=True, blank=True)
    device_change_count = models.IntegerField(default=0)

    last_ip = models.GenericIPAddressField(null=True, blank=True)
    ip_change_count = models.IntegerField(default=0)

    def __str__(self):
        return f"Security Profile - {self.user.username}"


