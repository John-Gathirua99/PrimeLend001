from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserProfile,UserSecurityProfile

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)





@receiver(post_save, sender=User)
def create_security_profile(sender, instance, created, **kwargs):
    if created:
        UserSecurityProfile.objects.create(user=instance)
