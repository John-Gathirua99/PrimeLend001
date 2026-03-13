from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

class Command(BaseCommand):
    help = "Send email/notification reminders to overdue borrowers"

    def handle(self, *args, **kwargs):
        from loans.models import LoanApplication
        from notification.utils import create_notification

        now = timezone.now()
        overdue = LoanApplication.objects.filter(
            status="Funded", fully_repaid=False,
            funded_at__lt=now - timedelta(days=30)
        )

        count = 0
        for loan in overdue:
            days = (now.date() - loan.funded_at.date()).days - 30
            if days <= 0:
                continue
            try:
                create_notification(
                    loan.user,
                    title="⚠️ Loan Repayment Overdue",
                    message=(
                        f"Your loan of KES {loan.qualified_amount:,} is {days} day(s) overdue. "
                        f"Outstanding balance: KES {loan.amount_remaining:,}. "
                        f"Please repay immediately to avoid penalties."
                    )
                )
                count += 1
            except Exception as e:
                self.stderr.write(f"Failed for loan {loan.id}: {e}")

        self.stdout.write(self.style.SUCCESS(f"Sent {count} overdue reminders."))
