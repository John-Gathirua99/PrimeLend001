# helpdesk/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import SupportTicket, Message
from .ai import generate_ai_reply, wants_admin


@login_required
def create_ticket(request):
    """Create a new support ticket with first user message and AI auto-reply"""
    if request.method == 'POST':
        subject = request.POST.get('subject')
        message_text = request.POST.get('message')
        image = request.FILES.get('image')

        if not subject or not message_text:
            messages.error(request, "Please enter both subject and message.")
            return redirect('create_ticket')

        # 1️⃣ Create ticket
        ticket = SupportTicket.objects.create(
            user=request.user,
            subject=subject,
            status='AI'  # AI will handle initially
        )

        # 2️⃣ Save user message
        Message.objects.create(
            ticket=ticket,
            sender='USER',
            text=message_text,
            image=image
        )

        # 3️⃣ AI auto-reply
        ai_reply = generate_ai_reply(message_text)
        if ai_reply:  # prevent empty messages
            Message.objects.create(
                ticket=ticket,
                sender='AI',
                text=ai_reply
            )

        # Notify all admins of new ticket
        try:
            from django.contrib.auth.models import User as AuthUser
            from django.core.mail import send_mail
            from django.conf import settings
            from notification.utils import create_notification
            admins = AuthUser.objects.filter(is_staff=True)
            for admin in admins:
                create_notification(
                    admin,
                    title="New Support Ticket #{}".format(ticket.id),
                    message="{} submitted a ticket: {}".format(
                        request.user.get_full_name() or request.user.username,
                        subject
                    ),
                    link="/support/{}/chat/admin".format(ticket.id),
                )
            admin_emails = list(admins.exclude(email="").values_list("email", flat=True))
            if admin_emails:
                send_mail(
                    "New Support Ticket #{} - {}".format(ticket.id, subject),
                    "New ticket from {}\n\nSubject: {}\n\nMessage:\n{}\n\nView: http://127.0.0.1:8000/helpdesk/support/{}/chat/admin".format(
                        request.user.get_full_name() or request.user.username,
                        subject, message_text, ticket.id
                    ),
                    getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@primelend.ai"),
                    admin_emails,
                    fail_silently=True,
                )
        except Exception:
            pass
        messages.success(request, "Your request has been submitted. AI has responded.")
        return redirect('ticket_chat', ticket_id=ticket.id)

    return render(request, 'helpdesk/create_ticket.html')


@login_required
def my_tickets(request):
    """List all tickets for the logged-in user"""
    tickets = SupportTicket.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'helpdesk/my_tickets.html', {'tickets': tickets})

@login_required
def ticket_chat(request, ticket_id):
    ticket = get_object_or_404(SupportTicket, id=ticket_id, user=request.user)

    if request.method == "POST" and ticket.status != "CLOSED":
        user_message = request.POST.get("message")
        image = request.FILES.get("image")

        # Save user message
        Message.objects.create(
            ticket=ticket,
            sender='USER',
            text=user_message,
            image=image
        )

        # AI replies only if ticket is still handled by AI
        if ticket.status in ['OPEN', 'AI']:
            if wants_admin(user_message):
                ticket.status = 'ADMIN'
                ticket.save()
                Message.objects.create(
                    ticket=ticket,
                    sender='AI',
                    text="I’ve connected you to an admin. Please wait while they assist you."
                )
            else:
                ai_reply = generate_ai_reply(user_message)
                Message.objects.create(
                    ticket=ticket,
                    sender='AI',
                    text=ai_reply
                )
                # Keep status as AI
                if ticket.status == 'OPEN':
                    ticket.status = 'AI'
                    ticket.save()

        # If status is ADMIN, AI does nothing. Admin can respond manually.

        return redirect('ticket_chat', ticket_id=ticket.id)

    return render(request, 'helpdesk/chat.html', {
        'ticket': ticket,
        'messages': ticket.messages.order_by('created_at')
    })


@login_required
def ticket_detail(request, ticket_id):
    """Show ticket details and all related messages"""
    ticket = get_object_or_404(SupportTicket, id=ticket_id, user=request.user)
    messages_qs = ticket.messages.order_by('created_at')
    
    return render(request, 'helpdesk/ticket_detail.html', {
        'ticket': ticket,
        'messages': messages_qs
    })


# AdMIN REPLY


@login_required
def admin_ticket_list(request):
    # Only staff can access
    if not request.user.is_staff:
        messages.error(request, "Unauthorized")
        return redirect('dashboard')

    status_filter = request.GET.get('status', '')
    tickets = SupportTicket.objects.all().order_by('-created_at')
    if status_filter:
        tickets = tickets.filter(status=status_filter)
    counts = {'all': SupportTicket.objects.count(), 'ai': SupportTicket.objects.filter(status='AI').count(), 'admin': SupportTicket.objects.filter(status='ADMIN').count(), 'closed': SupportTicket.objects.filter(status='CLOSED').count()}
    return render(request, 'helpdesk/admin_ticket_list.html', {'tickets': tickets, 'counts': counts, 'status_filter': status_filter})

# ---------------- Admin Chat View ---------------- #
@login_required
def admin_ticket_chat(request, ticket_id):
    if not request.user.is_staff:
        return redirect('dashboard')
    ticket = get_object_or_404(SupportTicket, id=ticket_id)
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "close":
            ticket.status = "CLOSED"
            ticket.save()
            try:
                from notification.utils import create_notification
                create_notification(ticket.user, title="Ticket #{} Resolved".format(ticket.id), message="Your support ticket has been resolved and closed.", link="/support/{}/chat/".format(ticket.id))
            except Exception:
                pass
            return redirect("admin_ticket_list")
        reply_text = request.POST.get("message", "").strip()
        image = request.FILES.get("image")
        if reply_text or image:
            Message.objects.create(ticket=ticket, sender="ADMIN", text=reply_text, image=image)
            ticket.status = "ADMIN"
            ticket.save()
            try:
                from notification.utils import create_notification
                create_notification(ticket.user, title="Support replied - Ticket #{}".format(ticket.id), message="PrimeLend support has responded. Log in to view.", link="/support/{}/chat/".format(ticket.id))
            except Exception:
                pass
        return redirect("admin_ticket_chat", ticket_id=ticket.id)
    return render(request, "helpdesk/admin_chat.html", {"ticket": ticket, "messages": ticket.messages.order_by("created_at")})


@login_required
def rate_ticket(request, ticket_id):
    ticket = get_object_or_404(SupportTicket, id=ticket_id, user=request.user)
    if request.method == "POST":
        rating = request.POST.get("rating")
        comment = request.POST.get("comment", "").strip()
        if rating:
            ticket.rating = int(rating)
            ticket.rating_comment = comment
            ticket.save()
    return redirect("ticket_chat", ticket_id=ticket.id)
