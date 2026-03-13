from django.core.management.base import BaseCommand
from loans.models import LoanApplication
from accounts.utils import send_sms

class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        loans = LoanApplication.objects.filter(status='approved')

        for loan in loans:
            phone = loan.user.userprofile.phone_number
            send_sms(phone, "Reminder: Your loan repayment is due.")
