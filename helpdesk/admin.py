from django.contrib import admin
from .models import SupportTicket, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ('sender', 'text', 'image', 'created_at')
    can_delete = False


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'subject', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('subject', 'user__username')
    readonly_fields = ('user', 'subject', 'created_at')
    inlines = [MessageInline]
