# Add this model to your accounts/models.py

from django.db import models
from django.contrib.auth.models import User


class UserOTP(models.Model):
    """Stores one-time passwords for 2FA."""
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name="otps")
    code       = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used       = models.BooleanField(default=False)
    attempts   = models.IntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"OTP for {self.user.username} — {'used' if self.used else 'active'}"