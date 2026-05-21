
from django.db import models

class ChatMessage(models.Model):
    user_id = models.CharField(max_length=100)
    message = models.TextField()
    response = models.TextField(null=True, blank=True)
    escalated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)