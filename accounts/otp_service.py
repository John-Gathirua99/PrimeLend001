"""
accounts/otp_service.py — Email OTP (replaces SMS entirely)
Uses Gmail SMTP already configured in settings.py
"""
import random
import logging
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)


def generate_otp() -> str:
    return str(random.randint(100000, 999999))


def send_otp_email(email: str, otp: str, purpose: str = "verification") -> bool:
    """
    Send OTP via email. Returns True on success, False on failure.
    purpose: 'verification' | 'login' | 'password_reset'
    """
    subjects = {
        "verification": "PrimeLend AI — Verify Your Account",
        "login":        "PrimeLend AI — Login Verification Code",
        "password_reset": "PrimeLend AI — Password Reset Code",
    }
    subject = subjects.get(purpose, "PrimeLend AI — Your Verification Code")

    message = f"""
Your PrimeLend AI verification code is:

    {otp}

This code expires in 10 minutes.
Do not share this code with anyone.

If you did not request this, please ignore this email or contact support.

— PrimeLend AI Security Team
"""
    html_message = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:'Inter',Arial,sans-serif;background:#f8fafc;margin:0;padding:2rem;">
  <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.07);">
    
    <!-- Header -->
    <div style="background:#0f172a;padding:1.5rem 2rem;text-align:center;">
      <div style="font-family:'Georgia',serif;font-size:1.4rem;font-weight:700;color:#fff;">
        PrimeLend<span style="color:#d97706;">AI</span>
      </div>
    </div>

    <!-- Body -->
    <div style="padding:2rem;">
      <h2 style="font-family:'Georgia',serif;color:#0f172a;margin:0 0 0.5rem;">Verification Code</h2>
      <p style="color:#64748b;font-size:0.9rem;margin:0 0 1.5rem;">
        Use the code below to complete your {purpose}. It expires in <strong>10 minutes</strong>.
      </p>

      <!-- OTP Box -->
      <div style="background:#f1f5f9;border:2px dashed #d97706;border-radius:12px;padding:1.5rem;text-align:center;margin-bottom:1.5rem;">
        <div style="font-size:2.2rem;font-weight:700;letter-spacing:0.4em;color:#0f172a;font-family:'Courier New',monospace;">
          {otp}
        </div>
      </div>

      <p style="color:#94a3b8;font-size:0.78rem;margin:0;">
        If you did not request this code, please ignore this email.<br>
        Never share this code with anyone, including PrimeLend staff.
      </p>
    </div>

    <!-- Footer -->
    <div style="background:#f8fafc;padding:1rem 2rem;text-align:center;border-top:1px solid #e2e8f0;">
      <p style="color:#94a3b8;font-size:0.72rem;margin:0;">
        &copy; 2026 PrimeLend AI &nbsp;|&nbsp; support@primelend.ai
      </p>
    </div>
  </div>
</body>
</html>
"""
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@primelend.ai'),
            recipient_list=[email],
            html_message=html_message,
            fail_silently=False,
        )
        logger.info(f"OTP email sent to {email} for {purpose}")
        return True
    except Exception as e:
        logger.error(f"Failed to send OTP email to {email}: {e}")
        return False