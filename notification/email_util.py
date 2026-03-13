from django.core.mail import send_mail
from django.conf import settings


def send_loan_email(user, subject, message):
    if not user.email:
        return

    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=True,
    )