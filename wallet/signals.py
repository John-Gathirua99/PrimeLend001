from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Wallet

@receiver(post_save, sender=User)
def create_wallet(sender, instance, created, **kwargs):
    if created:
        Wallet.objects.create(user=instance,balance=100)

from django.db.models.signals import post_migrate
from django.dispatch import receiver

@receiver(post_migrate)
def create_system_wallet(sender, **kwargs):
    if sender.name == 'wallet':
        try:
            from .models import SystemWallet
            if not SystemWallet.objects.exists():
                SystemWallet.objects.create(balance=500000)
        except Exception:
            pass
