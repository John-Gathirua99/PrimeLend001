from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from accounts.models import UserProfile
from accounts.otp_service import generate_otp, send_otp_email
import random
from notification.utils import create_notification
from django.contrib.auth.decorators import login_required
from .forms import UserUpdateForm, ProfileUpdateForm
from django.utils import timezone
from datetime import timedelta


def register(request):
    if request.method == 'POST':
        username  = request.POST['username']
        email     = request.POST['email']
        phone     = request.POST.get('phone', '').strip()
        password1 = request.POST['password1']
        password2 = request.POST['password2']

        if password1 != password2:
            messages.error(request, "Passwords do not match.")
            return redirect('register')
        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already taken.")
            return redirect('register')
        if User.objects.filter(email=email).exists():
            messages.error(request, "An account with this email already exists.")
            return redirect('register')
        if not email:
            messages.error(request, "Email address is required.")
            return redirect('register')

        # Normalise phone if provided
        if phone:
            if phone.startswith('0'):
                phone = '254' + phone[1:]
            elif phone.startswith('+'):
                phone = phone[1:]
            if UserProfile.objects.filter(phone_number=phone).exists():
                messages.error(request, "This phone number is already registered.")
                return redirect('register')

        user = User.objects.create_user(username=username, email=email, password=password1)
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if phone:
            profile.phone_number = phone

        otp = generate_otp()
        profile.otp_code = otp
        profile.is_phone_verified = False
        profile.save()

        sent = send_otp_email(email, otp, purpose="verification")
        if not sent:
            messages.warning(request, "Account created but we couldn't send the verification email. Contact support.")

        request.session['otp_user_id'] = user.id
        login(request, user)
        messages.success(request, f"Account created! Check {email} for your verification code.")
        return redirect('verify_otp')

    return render(request, 'accounts/register.html')


def verify_otp(request):
    user_id = request.session.get('otp_user_id')
    if not user_id:
        messages.error(request, "Session expired. Please register or log in again.")
        return redirect('register')

    try:
        profile = UserProfile.objects.get(user_id=user_id)
        user    = profile.user
    except UserProfile.DoesNotExist:
        messages.error(request, "User not found.")
        return redirect('register')

    if request.method == 'POST':
        action = request.POST.get('action')

        # Resend OTP
        if action == 'resend':
            otp = generate_otp()
            profile.otp_code = otp
            profile.save()
            sent = send_otp_email(user.email, otp, purpose="verification")
            if sent:
                messages.success(request, f"New code sent to {user.email}.")
            else:
                messages.error(request, "Could not send email. Try again later.")
            return redirect('verify_otp')

        entered_otp = request.POST.get('otp', '').strip()
        if profile.otp_code and profile.otp_code == entered_otp:
            profile.is_phone_verified = True
            profile.otp_code = None
            profile.save()
            request.session.pop('otp_user_id', None)
            create_notification(user, "Account Verified ✅", "Your account has been verified successfully.")
            messages.success(request, "Account verified! Welcome to PrimeLend AI.")
            return redirect('dashboard')

        messages.error(request, "Invalid code. Please try again.")
        return redirect('verify_otp')

    return render(request, 'accounts/verify_otp.html', {'email': user.email})


def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)

        if user:
            login(request, user)
            profile, _ = UserProfile.objects.get_or_create(user=user)

            if not profile.is_phone_verified:
                otp = generate_otp()
                profile.otp_code = otp
                profile.save()
                sent = send_otp_email(user.email, otp, purpose="login")
                request.session['otp_user_id'] = user.id
                if sent:
                    messages.info(request, f"Verification code sent to {user.email}.")
                else:
                    messages.warning(request, "Could not send verification email. Contact support.")
                return redirect('verify_otp')

            create_notification(user, "Login Alert 🔐", "You logged in to your PrimeLend account.")
            return redirect('dashboard')
        else:
            messages.error(request, "Invalid username or password.")
            return redirect('login')

    return render(request, 'accounts/login.html')


def logout_view(request):
    user = request.user
    if user.is_authenticated:
        create_notification(user, "Logout", "You have logged out successfully.")
    logout(request)
    return redirect('login')


# ── Profile completion ────────────────────────────────────────
COMPLETION_FIELDS = [
    {"key": "first_name",        "label": "First Name",    "source": "user"},
    {"key": "last_name",         "label": "Last Name",     "source": "user"},
    {"key": "email",             "label": "Email",         "source": "user"},
    {"key": "phone_number",      "label": "Phone",         "source": "profile"},
    {"key": "national_id",       "label": "National ID",   "source": "profile"},
    {"key": "date_of_birth",     "label": "Date of Birth", "source": "profile"},
    {"key": "employment_status", "label": "Employment",    "source": "profile"},
    {"key": "monthly_income",    "label": "Income",        "source": "profile"},
]

def get_completion(user, profile):
    items = []
    for f in COMPLETION_FIELDS:
        obj  = user if f["source"] == "user" else profile
        val  = getattr(obj, f["key"], None) if obj else None
        items.append({"label": f["label"], "done": bool(val)})
    filled = sum(1 for i in items if i["done"])
    pct    = round(filled / len(items) * 100)
    return items, pct


@login_required
def profile(request):
    prof, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        user_form    = UserUpdateForm(request.POST, instance=request.user)
        profile_form = ProfileUpdateForm(request.POST, instance=prof)
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, "Profile updated successfully.")
            return redirect("profile")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        user_form    = UserUpdateForm(instance=request.user)
        profile_form = ProfileUpdateForm(instance=prof)

    completion_items, completion_pct = get_completion(request.user, prof)
    return render(request, "accounts/profile.html", {
        "user_form":        user_form,
        "profile_form":     profile_form,
        "completion_items": completion_items,
        "completion_pct":   completion_pct,
    })


@login_required
def edit_profile(request):
    prof, _ = UserProfile.objects.get_or_create(user=request.user)
    next_url = request.GET.get('next') or "profile"
    if request.method == "POST":
        u_form = UserUpdateForm(request.POST, instance=request.user)
        p_form = ProfileUpdateForm(request.POST, instance=prof)
        if u_form.is_valid() and p_form.is_valid():
            u_form.save()
            p_form.save()
            messages.success(request, "Profile updated successfully!")
            return redirect(next_url)
    else:
        u_form = UserUpdateForm(instance=request.user)
        p_form = ProfileUpdateForm(instance=prof)
    return render(request, "accounts/edit_profile.html", {"u_form": u_form, "p_form": p_form})