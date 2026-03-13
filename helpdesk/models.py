from django.db import models
from django.contrib.auth.models import User

class SupportTicket(models.Model):
    STATUS_CHOICES = (
        ('OPEN', 'Open'),
        ('AI', 'AI Responded'),
        ('ADMIN', 'Admin Responded'),
        ('CLOSED', 'Closed'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    subject = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='OPEN')
    created_at = models.DateTimeField(auto_now_add=True)

    rating = models.IntegerField(null=True, blank=True)  # 1-5 stars
    rating_comment = models.TextField(blank=True, default='')

    def is_closed(self):
        return self.status == 'closed'

    def __str__(self):
        return f"{self.subject} - {self.user.username}"



class Message(models.Model):
    SENDER_CHOICES = (
        ('USER', 'User'),
        ('AI', 'AI'),
        ('ADMIN', 'Admin'),
    )

    ticket = models.ForeignKey(SupportTicket, related_name='messages', on_delete=models.CASCADE)
    sender = models.CharField(max_length=10, choices=SENDER_CHOICES)
    text = models.TextField(blank=True)
    image = models.ImageField(upload_to='support/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sender} - {self.ticket.id}"

