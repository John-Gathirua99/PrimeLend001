from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum
from decimal import Decimal
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render


is_admin = user_passes_test(lambda u: u.is_staff, login_url="login")


@login_required
@is_admin
def admin_dashboard(request):
    from loans.models import LoanApplication
    from django.contrib.auth.models import User

    all_loans = LoanApplication.objects.select_related("user").order_by("-created_at")
    pending   = all_loans.filter(status__in=["Pending", "Pending KYC", "Under Review", "Info Required"])
    approved  = all_loans.filter(status="Approved").exclude(status="Funded")
    funded    = all_loans.filter(status="Funded")
    rejected  = all_loans.filter(status="Rejected").order_by("-created_at")[:50]

    system_wallet = None
    try:
        from wallet.models import SystemWallet
        system_wallet = SystemWallet.objects.first()
    except Exception:
        pass

    total_funded   = funded.count()
    fully_repaid   = funded.filter(fully_repaid=True).count()
    repayment_rate = round((fully_repaid / total_funded * 100) if total_funded else 0)

    open_tickets = 0
    try:
        from support.models import Ticket
        open_tickets = Ticket.objects.filter(status="Open").count()
    except Exception:
        pass

    stats = {
        "pending":           pending.count(),
        "approved":          approved.count(),
        "funded":            total_funded,
        "rejected":          all_loans.filter(status="Rejected").count(),
        "total_disbursed":   funded.aggregate(t=Sum("qualified_amount"))["t"] or 0,
        "total_outstanding": funded.filter(fully_repaid=False).aggregate(t=Sum("amount_remaining"))["t"] or 0,
        "fraud_flagged":     all_loans.filter(fraud_flag=True).count(),
        "pending_kyc": all_loans.filter(status="Pending KYC").count(),
        "total_users":       User.objects.count(),
        "repayment_rate":    repayment_rate,
        "open_tickets":      open_tickets,
    }

    # Add default risk predictions for funded loans
    funded_with_risk = []
    try:
        from ml_engine.default_predict import predict_default_risk
        for loan in funded.filter(fully_repaid=False)[:50]:
            risk = predict_default_risk(loan)
            funded_with_risk.append({
                "loan": loan,
                "default_risk": risk["risk_level"],
                "default_prob": round(risk["probability"] * 100, 1),
                "recommendation": risk["recommendation"],
            })
    except Exception:
        funded_with_risk = [{"loan": l, "default_risk": "N/A", "default_prob": 0, "recommendation": ""} for l in funded.filter(fully_repaid=False)[:50]]

    return render(request, "loans/admin_dashboard.html", {
        "pending":          pending,
        "approved":         approved,
        "funded":           funded,
        "funded_with_risk": funded_with_risk,
        "rejected":         rejected,
        "all_loans":        all_loans[:100],
        "stats":            stats,
        "system_wallet":    system_wallet,
        "now":              timezone.now(),
    })


@login_required
@is_admin
def admin_loan_detail(request, loan_id):
    """
    Full detail view for a pending loan — shows uploaded ID docs,
    OCR findings, user profile, and approve/reject actions.
    """
    from loans.models import LoanApplication
    loan = get_object_or_404(LoanApplication, id=loan_id)

    # Parse OCR issues out of rejection_reason for display
    ocr_issues = []
    if loan.rejection_reason and "ID verification issues:" in loan.rejection_reason:
        try:
            issues_part = loan.rejection_reason.split("ID verification issues:")[-1].strip()
            ocr_issues = [i.strip() for i in issues_part.split(";") if i.strip()]
        except Exception:
            pass
    elif loan.rejection_reason and "manual review" in loan.rejection_reason.lower():
        ocr_issues = [loan.rejection_reason]

    # User profile for context
    profile = None
    try:
        from accounts.models import UserProfile
        profile = loan.user.userprofile
    except Exception:
        pass

    return render(request, "loans/admin_loan_detail.html", {
        "loan":       loan,
        "ocr_issues": ocr_issues,
        "profile":    profile,
    })


@login_required
@is_admin
def admin_pending_loans(request):
    return redirect("admin_loan_dashboard")


@login_required
@is_admin
def admin_approve_loan(request, loan_id):
    from loans.models import LoanApplication
    from notification.utils import create_notification

    loan = get_object_or_404(LoanApplication, id=loan_id)

    if request.method == "POST":
        note            = request.POST.get("admin_note", "").strip()
        adjusted_amount = request.POST.get("adjusted_amount", "").strip()
        adjusted_rate   = request.POST.get("adjusted_rate", "").strip()

        if adjusted_amount:
            try:
                new_amount = Decimal(adjusted_amount)
                if new_amount > 0:
                    loan.qualified_amount = new_amount
            except Exception:
                pass

        if adjusted_rate:
            try:
                new_rate = Decimal(adjusted_rate) / Decimal("100")
                if new_rate > 0:
                    loan.interest_rate = new_rate
            except Exception:
                pass

        loan.status           = "Approved"
        loan.admin_approved   = True
        loan.approved_at      = timezone.now()
        loan.approved_by      = request.user
        principal             = Decimal(str(loan.qualified_amount))
        rate                  = Decimal(str(loan.interest_rate))
        loan.amount_remaining = principal + (principal * rate)

        if note:
            loan.rejection_reason = (loan.rejection_reason or "") + f" | Admin note: {note}"
        loan.save()

        create_notification(
            loan.user,
            title="Loan Approved ✓",
            message=(
                f"Your loan of KES {loan.qualified_amount:,} has been approved "
                f"at {loan.interest_rate * 100:.0f}% interest. "
                f"Log in and accept the terms to proceed."
            ),
        )
        try:
            from loans.models import AuditLog
            AuditLog.objects.create(
                loan_id=loan_id, action="Approved",
                note=f"KES {loan.qualified_amount:,} @ {loan.interest_rate*100:.0f}%",
                actor=request.user.get_full_name() or request.user.username
            )
        except Exception: pass
        messages.success(request, f"Loan #{loan_id} approved — KES {loan.qualified_amount:,}.")
        return redirect("admin_loan_dashboard")

    return redirect("admin_loan_dashboard")


@login_required
@is_admin
def admin_reject_loan(request, loan_id):
    from loans.models import LoanApplication
    from notification.utils import create_notification

    loan = get_object_or_404(LoanApplication, id=loan_id)

    if request.method == "POST":
        reason = request.POST.get("rejection_reason", "").strip()
        if not reason:
            messages.error(request, "A rejection reason is required.")
            return redirect("admin_loan_dashboard")

        loan.status           = "Rejected"
        loan.admin_approved   = False
        loan.rejection_reason = reason
        loan.save()

        create_notification(
            loan.user,
            title="Loan Application Rejected",
            message=f"Your loan of KES {loan.qualified_amount:,} was not approved. Reason: {reason}",
        )
        try:
            from loans.models import AuditLog
            AuditLog.objects.create(
                loan_id=loan_id, action="Rejected", note=reason[:200],
                actor=request.user.get_full_name() or request.user.username
            )
        except Exception:
            logger.warning(f"AuditLog write failed for loan #{loan_id}")
        messages.success(request, f"Loan #{loan_id} rejected.")


    next_url = request.POST.get("next", "")
    if next_url == "detail":
        return redirect("admin_loan_dashboard")
    return redirect("admin_loan_dashboard")


@login_required
@is_admin
def admin_request_info(request, loan_id):
    from loans.models import LoanApplication
    from notification.utils import create_notification

    loan = get_object_or_404(LoanApplication, id=loan_id)

    if request.method == "POST":
        info_needed = request.POST.get("info_needed", "").strip()
        if not info_needed:
            messages.error(request, "Please specify what information is needed.")
            return redirect("admin_loan_dashboard")

        loan.rejection_reason = (
            (loan.rejection_reason or "") + f" | Info requested: {info_needed}"
        )
        loan.save()

        create_notification(
            loan.user,
            title="Additional Information Required",
            message=f"Regarding loan #{loan.id}: {info_needed}. Please contact support.",
        )
        messages.success(request, f"Request sent to {loan.user.username}.")

    return redirect("admin_loan_dashboard")


@login_required
@is_admin
def loan_ocr_debug(request, loan_id):
    """
    Debug view — re-runs OCR on the stored ID image and shows:
    - The preprocessed image Tesseract actually sees
    - Raw OCR text output
    - Extracted ID number, name, DOB, gender
    - KYC selfie for visual comparison
    - Match results
    """
    import base64, io, os
    from django.conf import settings
    from loans.models import LoanApplication
    from django.core.files.storage import default_storage

    loan = get_object_or_404(LoanApplication, id=loan_id)

    debug = {
        'loan_id':         loan_id,
        'submitted_id':    loan.id_number,
        'account_name':    loan.user.get_full_name() or loan.user.username,
        'ocr_text':        None,
        'extracted_id':    None,
        'extracted_name':  None,
        'extracted_dob':   None,
        'extracted_gender':None,
        'id_match':        None,
        'name_match':      None,
        'preprocessed_b64':None,
        'face_crop_b64':None,
        'original_b64':    None,
        'selfie_b64':      None,
        'error':           None,
    }

    # ── Load original ID image ────────────────────────────────
    if loan.id_document_front:
        try:
            id_path = os.path.join(settings.MEDIA_ROOT, str(loan.id_document_front))
            with open(id_path, 'rb') as f:
                original_bytes = f.read()
            debug['original_b64'] = 'data:image/jpeg;base64,' + base64.b64encode(original_bytes).decode()
            debug['original_size'] = f"{len(original_bytes) / 1024:.0f} KB  ({_img_dims(original_bytes)})"
        except Exception as e:
            debug['error'] = f"Could not load ID image: {e}"

    # ── Run OCR and show preprocessed image ──────────────────
    if loan.id_document_front and not debug['error']:
        try:
            from ml_engine.id_verify import (
                _preprocess, extract_text_from_id,
                extract_id_number, extract_name, extract_dob,
                extract_gender, _names_match
            )
            import numpy as np
            from PIL import Image as PILImage

            # Re-open for preprocessing
            with open(id_path, 'rb') as f:
                from django.core.files.base import File
                class _BytesFile:
                    def __init__(self, data):
                        self._buf = io.BytesIO(data)
                    def seek(self, n): self._buf.seek(n)
                    def read(self): return self._buf.read()

                img_file = _BytesFile(original_bytes)

            import numpy as np
            img_bytes2 = open(id_path, 'rb').read()
            nparr2 = np.frombuffer(img_bytes2, np.uint8)
            import cv2
            raw_img = cv2.imdecode(nparr2, cv2.IMREAD_COLOR)
            preprocessed_arr = _preprocess(raw_img)
            from PIL import Image as PILImage
            preprocessed = PILImage.fromarray(preprocessed_arr)
            buf = io.BytesIO()
            preprocessed.save(buf, format='JPEG', quality=92)
            debug['preprocessed_b64'] = 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()

            # Use the new robust face extraction logic from kyc_face
            from ml_engine.kyc_face import _load_image_from_file, _best_id_crop
            import cv2
            
            id_img_cv = _load_image_from_file(loan.id_document_front)
            if id_img_cv is not None:
                found, face_crop = _best_id_crop(id_img_cv)
                face_crop_rgb = cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB)
                face_pil = PILImage.fromarray(face_crop_rgb)
                face_buf = io.BytesIO()
                face_pil.save(face_buf, format='JPEG')
                debug['face_crop_b64'] = 'data:image/jpeg;base64,' + base64.b64encode(face_buf.getvalue()).decode()
            else:
                debug['face_crop_b64'] = None
            
            debug['preprocessed_size'] = f"{len(buf.getvalue()) / 1024:.0f} KB  ({preprocessed.size[0]}×{preprocessed.size[1]})"

            # Re-run OCR
            import pytesseract, os as _os
            TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            if _os.path.exists(TESS):
                pytesseract.pytesseract.tesseract_cmd = TESS

            # Use main extraction logic
            best_text = extract_text_from_id(id_img_cv)
            debug['ocr_text']         = best_text
            debug['extracted_id']     = extract_id_number(best_text)
            debug['extracted_name']   = extract_name(best_text)
            debug['extracted_dob']    = extract_dob(best_text)
            debug['extracted_gender'] = extract_gender(best_text)

            # Compare
            if debug['extracted_id']:
                import re
                debug['id_match'] = re.sub(r'\D','', debug['extracted_id']) == re.sub(r'\D','', loan.id_number or '')
            if debug['extracted_name']:
                debug['name_match'] = _names_match(debug['extracted_name'], debug['account_name'])

        except Exception as e:
            import traceback
            debug['error'] = traceback.format_exc()

    # ── Load KYC selfie ───────────────────────────────────────
    if loan.kyc_selfie:
        try:
            selfie_path = os.path.join(settings.MEDIA_ROOT, str(loan.kyc_selfie))
            with open(selfie_path, 'rb') as f:
                selfie_bytes = f.read()
            debug['selfie_b64']  = 'data:image/jpeg;base64,' + base64.b64encode(selfie_bytes).decode()
            debug['selfie_size'] = f"{len(selfie_bytes) / 1024:.0f} KB  ({_img_dims(selfie_bytes)})"
            debug['kyc_match']   = loan.kyc_face_verified
            debug['kyc_conf']    = loan.kyc_confidence
        except Exception as e:
            debug['selfie_error'] = str(e)

    return render(request, 'loans/loan_ocr_debug.html', {'debug': debug, 'loan': loan})


def _img_dims(img_bytes):
    try:
        from PIL import Image as PILImage
        import io
        img = PILImage.open(io.BytesIO(img_bytes))
        return f"{img.size[0]}×{img.size[1]}"
    except Exception:
        return "?"


@login_required
@is_admin
def kyc_comparison_board(request):
    """
    Admin board — shows all loans with KYC selfie side by side with ID photo.
    Lets admin visually verify face matches at a glance.
    """
    from loans.models import LoanApplication
    import os
    from django.conf import settings

    # Filter: loans that have a selfie, ordered by most recent
    status_filter = request.GET.get('status', '')
    loans_qs = LoanApplication.objects.filter(
        kyc_selfie__isnull=False
    ).select_related('user').order_by('-created_at')

    if status_filter:
        loans_qs = loans_qs.filter(status=status_filter)

    # Build list with image URLs
    entries = []
    for loan in loans_qs[:100]:  # max 100 per page
        entry = {
            'loan':       loan,
            'selfie_url': None,
            'id_url':     None,
        }
        if loan.kyc_selfie:
            try:
                entry['selfie_url'] = loan.kyc_selfie.url
            except Exception:
                pass
        if loan.id_document_front:
            try:
                entry['id_url'] = loan.id_document_front.url
            except Exception:
                pass
        entries.append(entry)

    statuses = LoanApplication.objects.values_list('status', flat=True).distinct()

    return render(request, 'loans/kyc_comparison_board.html', {
        'entries':       entries,
        'status_filter': status_filter,
        'statuses':      statuses,
    })






@staff_member_required
def admin_nav(request):
    return render(request, "loans/admin_nav.html")

@staff_member_required
def admin_kyc_approve(request, loan_id):
    from loans.models import LoanApplication
    from ml_engine.credit_predict import predict_credit
    from datetime import timedelta
    from decimal import Decimal

    loan = get_object_or_404(LoanApplication, id=loan_id)

    if request.method != "POST":
        return render(request, "loans/admin_kyc_approve.html", {"loan": loan})

    note = request.POST.get("note", "Manually approved by admin").strip()
    try:
        loan.kyc_face_verified = True
        loan.kyc_confidence    = 100.0
        loan.save(update_fields=["kyc_face_verified", "kyc_confidence"])

        try:
            from accounts.models import UserProfile
            profile = UserProfile.objects.get(user=loan.user)
            profile.face_kyc_verified = True
            profile.save(update_fields=["face_kyc_verified"])
        except Exception:
            pass

        previous_loans = LoanApplication.objects.filter(user=loan.user).exclude(id=loan.id)
        prev_repaid    = previous_loans.filter(fully_repaid=True).count()
        past_default   = previous_loans.filter(
            fully_repaid=False, amount_remaining__gt=0, status="Funded",
            funded_at__lt=timezone.now() - timedelta(days=30)
        ).exists()

        prediction = predict_credit({
            "age":                    loan.age,
            "monthly_income":         float(loan.monthly_income),
            "loan_amount":            float(loan.qualified_amount),
            "repayment_period":       loan.repayment_period,
            "credit_history":         loan.credit_history,
            "debt_to_income_ratio":   float(loan.qualified_amount) / float(loan.monthly_income) if loan.monthly_income else 0,
            "past_default_flag":      int(past_default),
            "previous_loan_count":    previous_loans.count(),
            "on_time_repayment_count": prev_repaid,
            "fraud_score":            float(loan.fraud_score),
            "recent_application_count": previous_loans.filter(
                created_at__gte=timezone.now() - timedelta(days=7)
            ).count(),
            "kyc_face_verified":      True,
            "ocr_id_verified":        True,
            "id_reuse_flag":          bool(loan.fraud_flag),
            "needs_manual_review":    False,
            "ocr_name_match":         True,
        })

        prob        = prediction["probability"]
        emp_penalty = {"Unemployed": 0.25, "Student": 0.20, "Self-employed": 0.08}.get(loan.employment_status or "", 0.0)
        adjusted    = max(0.0, prob - emp_penalty)

        if adjusted < 0.40 or loan.fraud_flag:
            status        = "Rejected"
            interest_rate = Decimal("0.30")
            reason        = f"Rejected after manual KYC — score {adjusted:.0%}"
        elif adjusted < 0.78:
            status        = "Under Review"
            interest_rate = Decimal("0.25")
            reason        = f"Under Review — manual KYC approved, score {adjusted:.0%}"
        else:
            status        = "Approved"
            interest_rate = Decimal("0.15") if adjusted >= 0.90 else Decimal("0.20")
            reason        = f"Approved — manual KYC by admin. Score {adjusted:.0%}. Note: {note}"

        loan.status                = status
        loan.interest_rate         = interest_rate
        loan.predicted_probability = adjusted
        loan.rejection_reason      = reason
        loan.save(update_fields=["status", "interest_rate", "predicted_probability", "rejection_reason"])

        try:
            from notification.utils import create_notification
            create_notification(loan.user, title="KYC Verified ✓",
                message=f"Your identity has been manually verified. Loan status: {status}.")
        except Exception:
            pass

        try:
            from notification.email_service import send_loan_application_email
            send_loan_application_email(loan.user, loan)
        except Exception:
            pass

        messages.success(request, f"KYC approved for {loan.user.get_full_name()} — loan set to {status}.")

    except Exception as e:
        import traceback; traceback.print_exc()
        messages.error(request, f"KYC approval error: {str(e)}")

    return redirect("admin_loan_detail_view", loan_id=loan.id)










@login_required
@is_admin
def admin_reevaluate_loan(request, loan_id):
    from loans.models import LoanApplication
    if request.method == "POST":
        loan = get_object_or_404(LoanApplication, id=loan_id)
        loan.status = "Pending"
        loan.rejection_reason = (loan.rejection_reason or "") + " | Re-opened for review by admin"
        loan.save()
        messages.success(request, f"Loan #{loan_id} moved back to Pending.")
    return redirect("admin_loan_dashboard")


@login_required
@is_admin
def admin_delete_loan(request, loan_id):
    from loans.models import LoanApplication
    if request.method == "POST":
        loan = get_object_or_404(LoanApplication, id=loan_id)
        loan.delete()
        messages.success(request, f"Loan #{loan_id} deleted.")
    return redirect("admin_loan_dashboard")


@login_required
@is_admin
def admin_analytics(request):
    from loans.models import LoanApplication, AuditLog
    from django.contrib.auth.models import User
    from django.utils import timezone
    from datetime import timedelta
    import json

    now = timezone.now()
    all_loans = LoanApplication.objects.all()

    # ── KPI stats ──────────────────────────────────────────
    total     = all_loans.count()
    approved  = all_loans.filter(status__in=["Approved", "Funded"]).count()
    funded    = all_loans.filter(status="Funded").count()
    rejected  = all_loans.filter(status="Rejected").count()
    repaid    = all_loans.filter(fully_repaid=True).count()
    approval_rate  = round(approved / total * 100) if total else 0
    repayment_rate = round(repaid / funded * 100) if funded else 0

    total_disbursed = all_loans.filter(status="Funded").aggregate(
        t=Sum("qualified_amount"))["t"] or 0

    # Overdue: funded, not repaid, funded_at > 30 days ago
    overdue_qs = all_loans.filter(
        status="Funded", fully_repaid=False,
        funded_at__lt=now - timedelta(days=30)
    )
    overdue_loans = []
    for loan in overdue_qs:
        days = (now.date() - loan.funded_at.date()).days - 30 if loan.funded_at else 0
        overdue_loans.append({"loan": loan, "days_overdue": max(0, days)})
    overdue_loans.sort(key=lambda x: x["days_overdue"], reverse=True)

    overdue_amount = sum(float(x["loan"].amount_remaining or 0) for x in overdue_loans)

    stats = {
        "total": total, "approved": approved, "funded": funded,
        "rejected": rejected, "fully_repaid": repaid,
        "approval_rate": approval_rate, "repayment_rate": repayment_rate,
        "total_disbursed": total_disbursed,
        "overdue_count": len(overdue_loans), "overdue_amount": overdue_amount,
        "this_month_count": all_loans.filter(
            created_at__month=now.month, created_at__year=now.year).count(),
    }

    # ── Chart data — last 6 months ──────────────────────────
    months_labels, counts_data, approved_data, rejected_data, amounts_data = [], [], [], [], []
    for i in range(5, -1, -1):
        d = now - timedelta(days=30 * i)
        label = d.strftime("%b")
        qs = all_loans.filter(created_at__month=d.month, created_at__year=d.year)
        months_labels.append(label)
        counts_data.append(qs.count())
        approved_data.append(qs.filter(status__in=["Approved", "Funded"]).count())
        rejected_data.append(qs.filter(status="Rejected").count())
        amt = qs.filter(status="Funded").aggregate(t=Sum("qualified_amount"))["t"] or 0
        amounts_data.append(float(amt))

    # Status breakdown
    from django.db.models import Count
    status_qs = all_loans.values("status").annotate(n=Count("id")).order_by("-n")
    status_labels = [x["status"] for x in status_qs]
    status_values = [x["n"] for x in status_qs]

    chart_data = {
        "months": json.dumps(months_labels),
        "counts": json.dumps(counts_data),
        "approved": json.dumps(approved_data),
        "rejected": json.dumps(rejected_data),
        "amounts": json.dumps(amounts_data),
        "status_labels": json.dumps(status_labels),
        "status_values": json.dumps(status_values),
    }

    # ── Audit log ───────────────────────────────────────────
    try:
        audit_logs = AuditLog.objects.all()[:50]
    except Exception:
        audit_logs = []

    return render(request, "loans/admin_analytics.html", {
        "stats": stats,
        "chart_data": chart_data,
        "overdue_loans": overdue_loans,
        "audit_logs": audit_logs,
        "now": now,
    })


# ════════════════════════════════════════════════════════════
# BULK ACTIONS
# ════════════════════════════════════════════════════════════

@login_required
@is_admin
def admin_bulk_action(request):
    if request.method != "POST":
        return redirect("admin_loan_dashboard")
    from loans.models import LoanApplication
    from notification.models import Notification
    action = request.POST.get("action")
    loan_ids = request.POST.getlist("loan_ids")
    if not loan_ids:
        messages.warning(request, "No loans selected.")
        return redirect("admin_loan_dashboard")

    loans = LoanApplication.objects.filter(id__in=loan_ids)
    count = loans.count()

    if action == "bulk_reject":
        reason = request.POST.get("bulk_reason", "Bulk rejected by admin.")
        for loan in loans:
            loan.status = "Rejected"
            loan.rejection_reason = reason
            loan.save(update_fields=["status", "rejection_reason"])
            try:
                Notification.objects.create(
                    user=loan.user,
                    title="Loan Application Rejected",
                    message=f"Your loan #{loan.id} has been rejected. Reason: {reason}",
                    link=f"/loans/loan/result/{loan.id}/",
                )
            except Exception:
                pass
        messages.success(request, f"{count} loans rejected.")

    elif action == "bulk_approve":
        for loan in loans.filter(status__in=["Pending", "Under Review"]):
            loan.status = "Approved"
            loan.approved_at = timezone.now()
            loan.approved_by = request.user
            loan.save(update_fields=["status", "approved_at", "approved_by"])
            try:
                Notification.objects.create(
                    user=loan.user,
                    title="Loan Approved!",
                    message=f"Your loan #{loan.id} of KES {loan.qualified_amount} has been approved!",
                    link=f"/loans/loan/result/{loan.id}/",
                )
            except Exception:
                pass
        messages.success(request, f"{count} loans approved.")

    elif action == "bulk_delete":
        loans.delete()
        messages.success(request, f"{count} loans deleted.")

    elif action == "bulk_flag":
        for loan in loans:
            loan.is_flagged = True
            loan.save(update_fields=["is_flagged"])
        messages.success(request, f"{count} loans flagged for investigation.")

    return redirect("admin_loan_dashboard")


@login_required
@is_admin
def admin_export_loans(request):
    import csv
    from django.http import HttpResponse
    from loans.models import LoanApplication
    status_filter = request.GET.get("status", "all")
    loans = LoanApplication.objects.select_related("user").order_by("-created_at")
    if status_filter != "all":
        loans = loans.filter(status=status_filter)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="primelend_loans_{status_filter}.csv"'
    writer = csv.writer(response)
    writer.writerow([
        "ID", "Name", "Email", "Phone", "ID Number", "Age", "Employment",
        "Monthly Income", "Loan Amount", "Interest Rate", "Repayment Period",
        "Status", "Fraud Score", "Credit Score", "KYC Verified",
        "Applied Date", "Approved Date", "Funded Date", "Fully Repaid"
    ])
    for loan in loans:
        try:
            phone = loan.user.profile.phone_number or ""
        except Exception:
            phone = ""
        writer.writerow([
            loan.id, loan.full_name, loan.user.email, phone,
            loan.id_number or "", loan.age, loan.employment_status,
            loan.monthly_income, loan.qualified_amount,
            round(float(loan.interest_rate or 0) * 100, 1),
            loan.repayment_period, loan.status,
            round(float(loan.fraud_score or 0) * 100, 1),
            round(float(loan.predicted_probability or 0) * 100, 1),
            loan.kyc_face_verified,
            loan.created_at.strftime("%Y-%m-%d %H:%M") if loan.created_at else "",
            loan.approved_at.strftime("%Y-%m-%d") if loan.approved_at else "",
            loan.funded_at.strftime("%Y-%m-%d") if loan.funded_at else "",
            loan.fully_repaid,
        ])
    return response


# ════════════════════════════════════════════════════════════
# USER MANAGEMENT
# ════════════════════════════════════════════════════════════

@login_required
@is_admin
def admin_user_list(request):
    from django.contrib.auth.models import User
    from loans.models import LoanApplication
    search = request.GET.get("q", "")
    users = User.objects.select_related("profile").order_by("-date_joined")
    if search:
        users = users.filter(
            email__icontains=search
        ) | users.filter(
            first_name__icontains=search
        ) | users.filter(
            last_name__icontains=search
        )
    user_data = []
    for user in users[:100]:
        loans = LoanApplication.objects.filter(user=user)
        user_data.append({
            "user": user,
            "loan_count": loans.count(),
            "active_loans": loans.filter(status="Funded", fully_repaid=False).count(),
            "total_borrowed": loans.filter(status="Funded").aggregate(
                t=Sum("qualified_amount"))["t"] or 0,
            "is_suspended": not user.is_active,
            "trust_tier": getattr(getattr(user, "profile", None), "trust_tier", "NEW"),
            "kyc_verified": loans.filter(kyc_face_verified=True).exists(),
        })
    return render(request, "loans/admin_user_list.html", {
        "user_data": user_data, "search": search,
        "total": users.count(),
    })


@login_required
@is_admin
def admin_user_detail(request, user_id):
    from django.contrib.auth.models import User
    from loans.models import LoanApplication
    target_user = get_object_or_404(User, id=user_id)
    loans = LoanApplication.objects.filter(user=target_user).order_by("-created_at")
    return render(request, "loans/admin_user_detail.html", {
        "target_user": target_user,
        "loans": loans,
        "profile": getattr(target_user, "profile", None),
        "total_borrowed": loans.filter(status="Funded").aggregate(t=Sum("qualified_amount"))["t"] or 0,
        "active_loans": loans.filter(status="Funded", fully_repaid=False).count(),
    })


@login_required
@is_admin
def admin_suspend_user(request, user_id):
    from django.contrib.auth.models import User
    target_user = get_object_or_404(User, id=user_id)
    if target_user.is_staff:
        messages.error(request, "Cannot suspend an admin user.")
        return redirect("admin_user_detail", user_id=user_id)
    target_user.is_active = not target_user.is_active
    target_user.save()
    action = "activated" if target_user.is_active else "suspended"
    messages.success(request, f"User {target_user.email} has been {action}.")
    return redirect("admin_user_detail", user_id=user_id)


@login_required
@is_admin
def admin_reset_kyc(request, user_id):
    from django.contrib.auth.models import User
    from loans.models import LoanApplication
    target_user = get_object_or_404(User, id=user_id)
    LoanApplication.objects.filter(user=target_user).update(
        kyc_face_verified=False, kyc_confidence=0
    )
    try:
        profile = target_user.profile
        profile.face_embedding = None
        profile.face_kyc_verified = False
        profile.save(update_fields=["face_embedding", "face_kyc_verified"])
    except Exception:
        pass
    messages.success(request, f"KYC reset for {target_user.email}. They must re-verify.")
    return redirect("admin_user_detail", user_id=user_id)


@login_required
@is_admin
def admin_set_tier(request, user_id):
    from django.contrib.auth.models import User
    if request.method != "POST":
        return redirect("admin_user_detail", user_id=user_id)
    target_user = get_object_or_404(User, id=user_id)
    new_tier = request.POST.get("tier")
    valid_tiers = ["NEW", "BRONZE", "SILVER", "GOLD", "PLATINUM"]
    if new_tier not in valid_tiers:
        messages.error(request, "Invalid tier.")
        return redirect("admin_user_detail", user_id=user_id)
    try:
        profile = target_user.profile
        profile.trust_tier = new_tier
        profile.save(update_fields=["trust_tier"])
        messages.success(request, f"Trust tier updated to {new_tier} for {target_user.email}.")
    except Exception as e:
        messages.error(request, f"Could not update tier: {e}")
    return redirect("admin_user_detail", user_id=user_id)


# ════════════════════════════════════════════════════════════
# LOAN MANAGEMENT
# ════════════════════════════════════════════════════════════

@login_required
@is_admin
def admin_extend_loan(request, loan_id):
    from loans.models import LoanApplication
    if request.method != "POST":
        return redirect("admin_loan_detail", loan_id=loan_id)
    loan = get_object_or_404(LoanApplication, id=loan_id)
    extra_months = int(request.POST.get("extra_months", 1))
    reason = request.POST.get("reason", "")
    loan.repayment_period = (loan.repayment_period or 12) + extra_months
    loan.save(update_fields=["repayment_period"])
    try:
        from notification.models import Notification
        Notification.objects.create(
            user=loan.user,
            title="Loan Period Extended",
            message=f"Your loan #{loan.id} repayment period has been extended by {extra_months} month(s). New period: {loan.repayment_period} months.",
            link=f"/loans/loan/result/{loan.id}/",
        )
    except Exception:
        pass
    messages.success(request, f"Loan #{loan_id} extended by {extra_months} month(s). Reason: {reason}")
    return redirect("admin_loan_detail", loan_id=loan_id)


@login_required
@is_admin
def admin_mark_default(request, loan_id):
    from loans.models import LoanApplication
    if request.method != "POST":
        return redirect("admin_loan_detail", loan_id=loan_id)
    loan = get_object_or_404(LoanApplication, id=loan_id)
    loan.status = "Defaulted"
    loan.rejection_reason = request.POST.get("reason", "Loan marked as defaulted by admin.")
    loan.save(update_fields=["status", "rejection_reason"])
    try:
        profile = loan.user.profile
        profile.trust_tier = "NEW"
        profile.save(update_fields=["trust_tier"])
    except Exception:
        pass
    try:
        from notification.models import Notification
        Notification.objects.create(
            user=loan.user,
            title="Loan Defaulted",
            message=f"Your loan #{loan.id} has been marked as defaulted. Please contact support.",
            link="/support/",
        )
    except Exception:
        pass
    messages.warning(request, f"Loan #{loan_id} marked as defaulted. User trust tier reset.")
    return redirect("admin_loan_detail", loan_id=loan_id)


@login_required
@is_admin
def admin_write_off(request, loan_id):
    from loans.models import LoanApplication
    if request.method != "POST":
        return redirect("admin_loan_detail", loan_id=loan_id)
    loan = get_object_or_404(LoanApplication, id=loan_id)
    loan.status = "Written Off"
    loan.fully_repaid = True
    loan.amount_remaining = 0
    loan.rejection_reason = f"Written off by {request.user.username}: {request.POST.get('reason', '')}"
    loan.save(update_fields=["status", "fully_repaid", "amount_remaining", "rejection_reason"])
    messages.success(request, f"Loan #{loan_id} written off as bad debt.")
    return redirect("admin_loan_detail", loan_id=loan_id)


@login_required
@is_admin
def admin_send_reminder(request, loan_id):
    from loans.models import LoanApplication
    loan = get_object_or_404(LoanApplication, id=loan_id)
    try:
        from notification.models import Notification
        Notification.objects.create(
            user=loan.user,
            title="⚠ Payment Reminder",
            message=f"This is a reminder that your loan #{loan.id} repayment of KES {loan.amount_remaining} is due. Please make payment to avoid penalties.",
            link=f"/wallet/",
        )
        messages.success(request, f"Payment reminder sent to {loan.user.email}.")
    except Exception as e:
        messages.error(request, f"Could not send reminder: {e}")
    return redirect("admin_loan_detail", loan_id=loan_id)


@login_required
@is_admin
def admin_add_note(request, loan_id):
    from loans.models import LoanApplication
    if request.method != "POST":
        return redirect("admin_loan_detail", loan_id=loan_id)
    loan = get_object_or_404(LoanApplication, id=loan_id)
    note = request.POST.get("note", "").strip()
    if note:
        existing = loan.rejection_reason or ""
        timestamp = timezone.now().strftime("%d/%m/%Y %H:%M")
        loan.rejection_reason = f"{existing}\n[{timestamp}] Admin note by {request.user.username}: {note}".strip()
        loan.save(update_fields=["rejection_reason"])
        messages.success(request, "Note added.")
    return redirect("admin_loan_detail", loan_id=loan_id)


@login_required
@is_admin
def admin_flag_loan(request, loan_id):
    from loans.models import LoanApplication
    loan = get_object_or_404(LoanApplication, id=loan_id)
    try:
        loan.is_flagged = not getattr(loan, "is_flagged", False)
        loan.save(update_fields=["is_flagged"])
        status = "flagged" if loan.is_flagged else "unflagged"
        messages.success(request, f"Loan #{loan_id} {status} for investigation.")
    except Exception as e:
        messages.error(request, f"Could not flag loan: {e}")
    return redirect("admin_loan_detail", loan_id=loan_id)


# ════════════════════════════════════════════════════════════
# SYSTEM CONTROLS
# ════════════════════════════════════════════════════════════

@login_required
@is_admin
def admin_system_settings(request):
    from loans.models import SystemSettings
    settings_obj, _ = SystemSettings.objects.get_or_create(id=1)

    if request.method == "POST":
        settings_obj.loans_enabled = request.POST.get("loans_enabled") == "on"
        settings_obj.min_loan_amount = int(request.POST.get("min_loan_amount", 1000))
        settings_obj.max_loan_amount_new = int(request.POST.get("max_loan_amount_new", 10000))
        settings_obj.max_loan_amount_bronze = int(request.POST.get("max_loan_amount_bronze", 30000))
        settings_obj.max_loan_amount_silver = int(request.POST.get("max_loan_amount_silver", 75000))
        settings_obj.max_loan_amount_gold = int(request.POST.get("max_loan_amount_gold", 150000))
        settings_obj.max_loan_amount_platinum = int(request.POST.get("max_loan_amount_platinum", 500000))
        settings_obj.min_interest_rate = float(request.POST.get("min_interest_rate", 10))
        settings_obj.max_interest_rate = float(request.POST.get("max_interest_rate", 25))
        settings_obj.maintenance_message = request.POST.get("maintenance_message", "")
        settings_obj.save()
        messages.success(request, "System settings updated.")
        return redirect("admin_system_settings")

    return render(request, "loans/admin_system_settings.html", {
        "settings": settings_obj,
    })
