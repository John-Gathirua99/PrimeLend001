"""
notifications/email_service.py — All transactional emails for PrimeLend AI

Emails sent:
  1. KYC verified — identity confirmed
  2. Loan application received
  3. Loan approved
  4. Loan rejected
  5. Loan disbursed (funds sent to M-Pesa)
  6. Repayment received
  7. Repayment reminder (due soon)
  8. Loan fully repaid
  9. Account registered (welcome)
 10. Password changed
"""
import logging
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

BRAND   = "PrimeLend AI"
COLOR_NAVY  = "#0f172a"
COLOR_GOLD  = "#d97706"
COLOR_GREEN = "#16a34a"
COLOR_RED   = "#dc2626"
FROM_EMAIL  = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@primelend.ai')


def _base_template(title, body_html, footer_note=""):
    """Wrap content in branded email shell."""
    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:32px 16px;">
    <tr><td align="center">
      <table width="100%" style="max-width:560px;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">

        <!-- Header -->
        <tr>
          <td style="background:{COLOR_NAVY};padding:28px 32px;">
            <div style="font-size:1.3rem;font-weight:800;color:#ffffff;letter-spacing:-0.02em;">
              🏦 {BRAND}
            </div>
            <div style="color:#94a3b8;font-size:0.8rem;margin-top:4px;">Smart Lending, Powered by AI</div>
          </td>
        </tr>

        <!-- Gold accent bar -->
        <tr><td style="height:4px;background:linear-gradient(90deg,{COLOR_GOLD},{COLOR_NAVY});"></td></tr>

        <!-- Body -->
        <tr>
          <td style="padding:32px;">
            <h2 style="margin:0 0 16px;color:{COLOR_NAVY};font-size:1.25rem;">{title}</h2>
            {body_html}
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f8fafc;padding:20px 32px;border-top:1px solid #e2e8f0;">
            <p style="margin:0;font-size:0.72rem;color:#94a3b8;line-height:1.6;">
              {footer_note or "This is an automated message from PrimeLend AI. Please do not reply to this email."}
              <br>© {timezone.now().year} PrimeLend AI. All rights reserved.
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>
"""


def _info_row(label, value, bold=False):
    val_style = f"font-weight:700;color:{COLOR_NAVY};" if bold else f"color:{COLOR_NAVY};"
    return f"""
    <tr>
      <td style="padding:8px 0;color:#64748b;font-size:0.85rem;border-bottom:1px solid #f1f5f9;width:45%;">{label}</td>
      <td style="padding:8px 0;font-size:0.85rem;{val_style}border-bottom:1px solid #f1f5f9;">{value}</td>
    </tr>"""


def _button(text, url, color=None):
    bg = color or COLOR_NAVY
    return f"""
    <div style="text-align:center;margin:24px 0 8px;">
      <a href="{url}" style="display:inline-block;background:{bg};color:#ffffff;
         text-decoration:none;padding:12px 32px;border-radius:10px;
         font-weight:700;font-size:0.9rem;letter-spacing:0.02em;">{text}</a>
    </div>"""


def _send(to_email, subject, html):
    """Send HTML email. Returns True on success."""
    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=subject,   # plain text fallback
            from_email=FROM_EMAIL,
            to=[to_email],
        )
        msg.attach_alternative(html, "text/html")
        msg.send()
        logger.info(f"[EMAIL] Sent '{subject}' to {to_email}")
        return True
    except Exception as e:
        logger.error(f"[EMAIL] Failed to send '{subject}' to {to_email}: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 1. WELCOME EMAIL
# ─────────────────────────────────────────────────────────────────────────────

def send_welcome_email(user):
    name = user.get_full_name() or user.username
    body = f"""
    <p style="color:#475569;line-height:1.7;">Hi <strong>{name}</strong>,</p>
    <p style="color:#475569;line-height:1.7;">
      Welcome to <strong>PrimeLend AI</strong>! Your account has been created successfully.
      We use AI-powered credit scoring to give you fast, fair loan decisions.
    </p>
    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:16px;margin:16px 0;">
      <p style="margin:0;color:#166534;font-size:0.85rem;font-weight:600;">✅ Account created</p>
      <p style="margin:4px 0 0;color:#166534;font-size:0.8rem;">Complete your profile and KYC to unlock loan applications.</p>
    </div>
    <p style="color:#475569;line-height:1.7;font-size:0.85rem;">Next steps:</p>
    <ol style="color:#475569;font-size:0.85rem;line-height:2;">
      <li>Complete your profile</li>
      <li>Verify your identity (KYC)</li>
      <li>Apply for a loan</li>
    </ol>
    {_button("Get Started", getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000') + '/accounts/profile/')}
    """
    html = _base_template("Welcome to PrimeLend AI! 🎉", body)
    _send(user.email, f"Welcome to {BRAND}!", html)


# ─────────────────────────────────────────────────────────────────────────────
# 2. KYC VERIFIED
# ─────────────────────────────────────────────────────────────────────────────

def send_kyc_verified_email(user, confidence=None):
    name = user.get_full_name() or user.username
    conf_text = f" (Match confidence: {confidence:.0f}%)" if confidence else ""
    body = f"""
    <p style="color:#475569;line-height:1.7;">Hi <strong>{name}</strong>,</p>
    <p style="color:#475569;line-height:1.7;">
      Your identity has been successfully verified{conf_text}. Your face matched your ID document
      and your account is now fully verified.
    </p>
    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:20px;margin:16px 0;text-align:center;">
      <div style="font-size:2rem;">✅</div>
      <div style="font-weight:700;color:#166534;font-size:1rem;margin-top:8px;">Identity Verified</div>
      <div style="color:#166534;font-size:0.8rem;margin-top:4px;">Your account is now KYC-verified</div>
    </div>
    <p style="color:#475569;line-height:1.7;">
      You can now apply for loans with higher approval chances. Your verified status is permanent
      and you won't need to repeat this process.
    </p>
    {_button("Apply for a Loan", getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000') + '/loans/apply/', COLOR_GREEN)}
    """
    html = _base_template("Identity Verified ✅", body)
    _send(user.email, f"{BRAND} — Identity Verified Successfully", html)


# ─────────────────────────────────────────────────────────────────────────────
# 3. LOAN APPLICATION RECEIVED
# ─────────────────────────────────────────────────────────────────────────────

def send_loan_application_email(user, loan):
    name = user.get_full_name() or user.username
    rows = (
        _info_row("Application #", f"#{loan.id}") +
        _info_row("Amount Requested", f"KES {loan.qualified_amount:,.0f}", bold=True) +
        _info_row("Repayment Period", f"{loan.repayment_period} months") +
        _info_row("Interest Rate", f"{loan.interest_rate:.1f}%") +
        _info_row("Status", "Under Review") +
        _info_row("Submitted", loan.created_at.strftime("%d %b %Y, %I:%M %p"))
    )
    body = f"""
    <p style="color:#475569;line-height:1.7;">Hi <strong>{name}</strong>,</p>
    <p style="color:#475569;line-height:1.7;">
      We've received your loan application and our AI system is reviewing it now.
      You'll receive an email once a decision has been made — usually within minutes.
    </p>
    <table width="100%" cellpadding="0" cellspacing="0" style="margin:16px 0;">
      {rows}
    </table>
    <div style="background:#fef3c7;border:1px solid #fde68a;border-radius:10px;padding:14px;margin:16px 0;">
      <p style="margin:0;color:#92400e;font-size:0.82rem;">
        ⏱ Our AI reviews applications instantly. Complex cases may take up to 24 hours for manual review.
      </p>
    </div>
    {_button("View Application", getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000') + '/loans/status/')}
    """
    html = _base_template("Loan Application Received 📋", body)
    _send(user.email, f"{BRAND} — Loan Application #{loan.id} Received", html)


# ─────────────────────────────────────────────────────────────────────────────
# 4. LOAN APPROVED
# ─────────────────────────────────────────────────────────────────────────────

def send_loan_approved_email(user, loan):
    name = user.get_full_name() or user.username
    rows = (
        _info_row("Application #", f"#{loan.id}") +
        _info_row("Approved Amount", f"KES {loan.qualified_amount:,.0f}", bold=True) +
        _info_row("Interest Rate", f"{loan.interest_rate:.1f}% per month") +
        _info_row("Repayment Period", f"{loan.repayment_period} months") +
        _info_row("Monthly Payment", f"KES {(loan.qualified_amount * (1 + loan.interest_rate/100)):,.0f} approx")
    )
    body = f"""
    <p style="color:#475569;line-height:1.7;">Hi <strong>{name}</strong>,</p>
    <p style="color:#475569;line-height:1.7;">
      🎉 Congratulations! Your loan application has been <strong style="color:{COLOR_GREEN};">approved</strong>.
      Please review and accept the loan terms to proceed to disbursement.
    </p>
    <table width="100%" cellpadding="0" cellspacing="0" style="margin:16px 0;">
      {rows}
    </table>
    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:14px;margin:16px 0;">
      <p style="margin:0;color:#166534;font-size:0.82rem;font-weight:600;">
        ✅ Next step: Accept loan terms to receive your funds via M-Pesa.
      </p>
    </div>
    {_button("Accept Terms & Get Funds", getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000') + '/loans/status/', COLOR_GREEN)}
    """
    html = _base_template("Loan Approved! 🎉", body)
    _send(user.email, f"{BRAND} — Your Loan of KES {loan.qualified_amount:,.0f} is Approved!", html)


# ─────────────────────────────────────────────────────────────────────────────
# 5. LOAN REJECTED
# ─────────────────────────────────────────────────────────────────────────────

def send_loan_rejected_email(user, loan, reason=None):
    name = user.get_full_name() or user.username
    reason_block = ""
    if reason:
        reason_block = f"""
        <div style="background:#fff1f2;border:1px solid #fecdd3;border-radius:10px;padding:14px;margin:16px 0;">
          <p style="margin:0;color:#991b1b;font-size:0.82rem;"><strong>Reason:</strong> {reason}</p>
        </div>"""
    body = f"""
    <p style="color:#475569;line-height:1.7;">Hi <strong>{name}</strong>,</p>
    <p style="color:#475569;line-height:1.7;">
      After reviewing your application, we're unable to approve your loan request at this time.
    </p>
    {reason_block}
    <p style="color:#475569;line-height:1.7;font-size:0.85rem;">
      Common reasons for rejection include credit history, income level, or outstanding loans.
      You may reapply after 30 days or once your financial situation improves.
    </p>
    {_button("View Details", getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000') + '/loans/status/')}
    """
    html = _base_template("Loan Application Update", body)
    _send(user.email, f"{BRAND} — Loan Application #{loan.id} Decision", html)


# ─────────────────────────────────────────────────────────────────────────────
# 6. LOAN DISBURSED
# ─────────────────────────────────────────────────────────────────────────────

def send_loan_disbursed_email(user, loan, phone=None):
    name  = user.get_full_name() or user.username
    phone = phone or "your registered M-Pesa number"
    rows  = (
        _info_row("Loan #", f"#{loan.id}") +
        _info_row("Amount Disbursed", f"KES {loan.qualified_amount:,.0f}", bold=True) +
        _info_row("Sent To", phone) +
        _info_row("Date", timezone.now().strftime("%d %b %Y, %I:%M %p")) +
        _info_row("First Repayment", "Check your repayment schedule")
    )
    body = f"""
    <p style="color:#475569;line-height:1.7;">Hi <strong>{name}</strong>,</p>
    <p style="color:#475569;line-height:1.7;">
      💸 Your loan funds have been disbursed to your M-Pesa account. Check your phone for the
      M-Pesa confirmation message.
    </p>
    <table width="100%" cellpadding="0" cellspacing="0" style="margin:16px 0;">
      {rows}
    </table>
    <div style="background:#fef3c7;border:1px solid #fde68a;border-radius:10px;padding:14px;margin:16px 0;">
      <p style="margin:0;color:#92400e;font-size:0.82rem;font-weight:600;">
        ⚠ Remember: Timely repayment improves your credit score and increases future loan limits.
      </p>
    </div>
    {_button("View Repayment Schedule", getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000') + '/loans/schedule/', COLOR_GOLD)}
    """
    html = _base_template("Funds Disbursed to M-Pesa 💸", body)
    _send(user.email, f"{BRAND} — KES {loan.qualified_amount:,.0f} Sent to Your M-Pesa", html)


# ─────────────────────────────────────────────────────────────────────────────
# 7. REPAYMENT RECEIVED
# ─────────────────────────────────────────────────────────────────────────────

def send_repayment_received_email(user, loan, amount_paid, balance_remaining):
    name = user.get_full_name() or user.username
    rows = (
        _info_row("Amount Paid", f"KES {amount_paid:,.0f}", bold=True) +
        _info_row("Loan #", f"#{loan.id}") +
        _info_row("Remaining Balance", f"KES {balance_remaining:,.0f}") +
        _info_row("Date", timezone.now().strftime("%d %b %Y, %I:%M %p"))
    )
    fully_paid = balance_remaining <= 0
    status_block = ""
    if fully_paid:
        status_block = f"""
        <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:16px;margin:16px 0;text-align:center;">
          <div style="font-size:1.5rem;">🎊</div>
          <div style="font-weight:700;color:#166534;margin-top:8px;">Loan Fully Repaid!</div>
          <div style="color:#166534;font-size:0.8rem;margin-top:4px;">Congratulations — your loan is cleared.</div>
        </div>"""
    body = f"""
    <p style="color:#475569;line-height:1.7;">Hi <strong>{name}</strong>,</p>
    <p style="color:#475569;line-height:1.7;">We've received your repayment. Thank you!</p>
    <table width="100%" cellpadding="0" cellspacing="0" style="margin:16px 0;">
      {rows}
    </table>
    {status_block}
    {_button("View Loan Details", getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000') + '/wallet/')}
    """
    subject = f"{BRAND} — {'Loan Fully Repaid! 🎊' if fully_paid else 'Repayment Received ✅'}"
    html = _base_template("Repayment Confirmed ✅", body)
    _send(user.email, subject, html)


# ─────────────────────────────────────────────────────────────────────────────
# 8. REPAYMENT REMINDER
# ─────────────────────────────────────────────────────────────────────────────

def send_repayment_reminder_email(user, loan, amount_due, due_date):
    name = user.get_full_name() or user.username
    rows = (
        _info_row("Amount Due", f"KES {amount_due:,.0f}", bold=True) +
        _info_row("Due Date", due_date.strftime("%d %b %Y")) +
        _info_row("Loan #", f"#{loan.id}")
    )
    body = f"""
    <p style="color:#475569;line-height:1.7;">Hi <strong>{name}</strong>,</p>
    <p style="color:#475569;line-height:1.7;">
      This is a friendly reminder that your loan repayment is due soon.
    </p>
    <table width="100%" cellpadding="0" cellspacing="0" style="margin:16px 0;">
      {rows}
    </table>
    <div style="background:#fff1f2;border:1px solid #fecdd3;border-radius:10px;padding:14px;margin:16px 0;">
      <p style="margin:0;color:#991b1b;font-size:0.82rem;">
        ⚠ Late payments affect your credit score. Please repay on time to maintain good standing.
      </p>
    </div>
    {_button("Make Repayment Now", getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000') + '/wallet/', COLOR_RED)}
    """
    html = _base_template("Repayment Reminder ⏰", body)
    _send(user.email, f"{BRAND} — Repayment of KES {amount_due:,.0f} Due {due_date.strftime('%d %b')}", html)


# ─────────────────────────────────────────────────────────────────────────────
# 9. PASSWORD CHANGED
# ─────────────────────────────────────────────────────────────────────────────

def send_password_changed_email(user):
    name = user.get_full_name() or user.username
    body = f"""
    <p style="color:#475569;line-height:1.7;">Hi <strong>{name}</strong>,</p>
    <p style="color:#475569;line-height:1.7;">
      Your PrimeLend AI account password was changed on {timezone.now().strftime("%d %b %Y at %I:%M %p")}.
    </p>
    <div style="background:#fff1f2;border:1px solid #fecdd3;border-radius:10px;padding:14px;margin:16px 0;">
      <p style="margin:0;color:#991b1b;font-size:0.82rem;">
        🔒 If you did not make this change, contact support immediately and secure your account.
      </p>
    </div>
    {_button("Contact Support", getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000') + '/support/')}
    """
    html = _base_template("Password Changed 🔒", body)
    _send(user.email, f"{BRAND} — Your Password Was Changed", html)


# ─────────────────────────────────────────────────────────────────────────────
# 10. MANUAL REVIEW REQUESTED
# ─────────────────────────────────────────────────────────────────────────────

def send_manual_review_email(user, loan):
    name = user.get_full_name() or user.username
    body = f"""
    <p style="color:#475569;line-height:1.7;">Hi <strong>{name}</strong>,</p>
    <p style="color:#475569;line-height:1.7;">
      Your loan application <strong>#{loan.id}</strong> has been flagged for manual review
      by our team. This is routine for some applications and does not mean it will be rejected.
    </p>
    <div style="background:#fef3c7;border:1px solid #fde68a;border-radius:10px;padding:14px;margin:16px 0;">
      <p style="margin:0;color:#92400e;font-size:0.82rem;">
        ⏱ Manual reviews typically complete within 24 hours. You'll receive an email with the decision.
      </p>
    </div>
    {_button("View Application", getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000') + '/loans/status/')}
    """
    html = _base_template("Application Under Review 🔍", body)
    _send(user.email, f"{BRAND} — Loan #{loan.id} Under Manual Review", html)