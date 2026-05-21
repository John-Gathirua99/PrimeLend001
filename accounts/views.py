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
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm


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


@login_required
def change_password(request):
    """
    Allow authenticated users to change their password.
    """
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Keeps the user logged in
            create_notification(request.user, "Security Alert 🔒", "Your password has been changed successfully.")
            messages.success(request, 'Your password was successfully updated!')
            return redirect('profile')
        else:
            messages.error(request, 'Please correct the error below.')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'accounts/change_password.html', {'form': form})


# ── Forgot Password (OTP-based) ───────────────────────────────

def forgot_password(request):
    """
    Step 1 — Ask for email. OTP is saved to UserProfile.otp_code (DB).
    Session only stores the user_id so we can look up the profile later.
    """
    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        account_found = False
        try:
            user       = User.objects.get(email__iexact=email)
            profile, _ = UserProfile.objects.get_or_create(user=user)
            otp        = generate_otp()
            profile.otp_code       = otp
            profile.otp_created_at = timezone.now()
            profile.otp_attempts   = 0
            profile.save(update_fields=["otp_code", "otp_created_at", "otp_attempts"])
            send_otp_email(email, otp, purpose="password_reset")

            # Only need user_id in session; OTP truth is in the DB.
            request.session["pw_reset_user_id"] = user.id
            request.session.modified = True
            request.session.save()           # force flush before redirect
            account_found = True

        except User.DoesNotExist:
            pass  # neutral message shown regardless

        messages.success(
            request,
            f"If an account with {email} exists, a reset code has been sent. Check your inbox.",
        )
        if account_found:
            return redirect("forgot_password_verify_otp")
        return redirect("forgot_password")

    return render(request, "accounts/forgot_password.html")


def forgot_password_verify_otp(request):
    """
    Step 2 — Verify the OTP.
    OTP truth is in UserProfile.otp_code (DB); session only carries user_id.
    """
    user_id = request.session.get("pw_reset_user_id")

    if not user_id:
        messages.error(request, "Session expired or invalid. Please start again.")
        return redirect("forgot_password")

    try:
        user    = User.objects.get(pk=user_id)
        profile = UserProfile.objects.get(user=user)
    except (User.DoesNotExist, UserProfile.DoesNotExist):
        messages.error(request, "Account not found. Please start again.")
        return redirect("forgot_password")

    if request.method == "POST":
        action = request.POST.get("action")

        # ── Resend OTP ────────────────────────────────────────────
        if action == "resend":
            otp = generate_otp()
            profile.otp_code       = otp
            profile.otp_created_at = timezone.now()
            profile.otp_attempts   = 0
            profile.save(update_fields=["otp_code", "otp_created_at", "otp_attempts"])
            send_otp_email(user.email, otp, purpose="password_reset")
            messages.success(request, f"New code sent to {user.email}.")
            return redirect("forgot_password_verify_otp")

        # ── Brute Force & Expiry Check ────────────────────────────
        if profile.otp_attempts >= 5:
            messages.error(request, "Too many failed attempts. Please request a new code.")
            return redirect("forgot_password_verify_otp")

        if not profile.otp_created_at or (timezone.now() - profile.otp_created_at).total_seconds() > 600:
            messages.error(request, "Code has expired (10 min). Please resend.")
            return redirect("forgot_password_verify_otp")

        # ── Verify OTP ────────────────────────────────────────────
        entered_otp = request.POST.get("otp", "").strip()
        if profile.otp_code and entered_otp == profile.otp_code:
            # Consume the OTP immediately
            profile.otp_code       = None
            profile.otp_attempts   = 0
            profile.save(update_fields=["otp_code", "otp_attempts"])
            
            request.session["pw_reset_verified"] = True
            request.session.modified = True
            request.session.save()
            messages.success(request, "Identity verified. Please set your new password.")
            return redirect("forgot_password_reset")

        # Failure: increment attempts
        profile.otp_attempts += 1
        profile.save(update_fields=["otp_attempts"])
        
        attempts_left = 5 - profile.otp_attempts
        if attempts_left > 0:
            messages.error(request, f"Invalid code. {attempts_left} attempts remaining.")
        else:
            messages.error(request, "Invalid code. Too many failed attempts.")
            
        return redirect("forgot_password_verify_otp")

    # Mask the email for display
    parts = user.email.split("@")
    masked_email = parts[0][:2] + "***@" + parts[1]

    return render(request, "accounts/forgot_password_verify_otp.html", {
        "masked_email": masked_email,
    })


def forgot_password_reset(request):
    """
    Step 3 — Set a new password (only reachable after OTP verified).
    """
    user_id  = request.session.get("pw_reset_user_id")
    verified = request.session.get("pw_reset_verified", False)

    if not user_id or not verified:
        messages.error(request, "Session expired or invalid. Please start again.")
        return redirect("forgot_password")

    if request.method == "POST":
        password1 = request.POST.get("password1", "")
        password2 = request.POST.get("password2", "")

        if password1 != password2:
            messages.error(request, "Passwords do not match.")
            return redirect("forgot_password_reset")

        try:
            user = User.objects.get(pk=user_id)
            validate_password(password1, user=user)
        except User.DoesNotExist:
            messages.error(request, "User not found. Please start again.")
            return redirect("forgot_password")
        except ValidationError as e:
            for err in e.messages:
                messages.error(request, err)
            return redirect("forgot_password_reset")

        user.set_password(password1)
        user.save()

        # Clear password-reset session keys
        for key in ["pw_reset_user_id", "pw_reset_otp", "pw_reset_verified"]:
            request.session.pop(key, None)

        # Clear stored OTP in profile too
        try:
            profile = UserProfile.objects.get(user=user)
            profile.otp_code = None
            profile.save(update_fields=["otp_code"])
        except UserProfile.DoesNotExist:
            pass

        create_notification(
            user,
            title="Password Changed 🔐",
            message="Your PrimeLend password was successfully reset. If this wasn't you, contact support immediately.",
        )
        messages.success(request, "Password reset successfully! Please log in with your new password.")
        return redirect("login")

    return render(request, "accounts/forgot_password_reset.html")