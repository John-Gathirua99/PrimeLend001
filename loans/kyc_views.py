"""
Add to loans/views.py or a new loans/kyc_views.py
"""
import json
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib import messages
from loans.models import LoanApplication


@login_required
def kyc_verify_page(request):
    """Show KYC webcam page before loan application."""
    # Check DB first (permanent), then session (temporary)
    verified_loan = LoanApplication.objects.filter(
        user=request.user,
        kyc_face_verified=True,
        kyc_selfie__isnull=False
    ).order_by('-created_at').first()

    session_verified = request.session.get('kyc_face_verified')

    if verified_loan or session_verified is not None:
        kyc_verified   = verified_loan.kyc_face_verified if verified_loan else session_verified
        kyc_confidence = verified_loan.kyc_confidence if verified_loan else round((request.session.get('kyc_confidence') or 0) * 100, 1)
        loan           = verified_loan or LoanApplication.objects.filter(
            user=request.user, kyc_selfie__isnull=False
        ).order_by('-created_at').first()

        return render(request, 'loans/kyc_already_verified.html', {
            'kyc_verified':   kyc_verified,
            'kyc_confidence': kyc_confidence,
            'loan':           loan,
            'user':           request.user,
        })

    import os
    from django.conf import settings

    latest_loan = None
    candidates = LoanApplication.objects.filter(
        user=request.user,
        id_document_front__isnull=False
    ).order_by('-created_at')

    for candidate in candidates:
        path = os.path.join(settings.MEDIA_ROOT, str(candidate.id_document_front))
        if os.path.exists(path):
            latest_loan = candidate
            break

    loan_id = latest_loan.id if latest_loan else None

    if request.method == 'POST':
        action = request.POST.get('kyc_action')
        if action == 'verify':
            selfie_b64 = request.POST.get('selfie_b64', '')
            if selfie_b64 and latest_loan:
                from ml_engine.kyc_face import verify_face_kyc
                result = verify_face_kyc(selfie_b64, latest_loan.id_document_front)
                # Store result in session
                request.session['kyc_face_verified'] = result.match
                request.session['kyc_confidence']    = result.confidence
                if result.match:
                    messages.success(request, f"Identity verified ✅ (confidence: {result.confidence:.0%})")
                else:
                    messages.warning(request, "Face match failed — your application will be reviewed manually.")
            next_url = request.session.pop('kyc_next', None) or reverse('loan_apply')
            return redirect(next_url)

    return render(request, 'loans/kyc_verify.html', {'loan_id': loan_id})


@login_required
def kyc_verify_ajax(request):
    """AJAX endpoint for live face verification."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data       = json.loads(request.body)
        selfie_b64 = data.get('selfie_b64', '')
        loan_id    = data.get('loan_id')

        if not selfie_b64:
            return JsonResponse({'error': 'No selfie data received.'})

        # Get ID document — always initialise loan to None first
        loan     = None
        id_image = None
        if loan_id:
            try:
                loan     = LoanApplication.objects.get(id=loan_id, user=request.user)
                id_image = loan.id_document_front
            except LoanApplication.DoesNotExist:
                pass

        # Try profile ID doc as fallback
        if id_image is None:
            latest = LoanApplication.objects.filter(
                user=request.user,
                id_document_front__isnull=False
            ).order_by('-created_at').first()
            if latest:
                id_image   = latest.id_document_front
                loan = loan or latest

        if id_image is None:
            # No ID doc yet — store selfie in session, verify later when ID is uploaded
            request.session['kyc_selfie_b64'] = selfie_b64[:500]  # store reference only
            return JsonResponse({
                'match': True,
                'confidence': 0.5,
                'message': 'Selfie saved — will be verified against your ID document.',
                'warning': True,
            })

        # ── Step 1: Check face uniqueness across all accounts ──────
        from ml_engine.face_registry import check_face_uniqueness, save_face_embedding
        uniqueness = check_face_uniqueness(selfie_b64, request.user)

        if not uniqueness['unique']:
            # Face matches a DIFFERENT account — block
            return JsonResponse({
                'match':   False,
                'blocked': True,
                'error':   (
                    f"This face is already registered to another account "
                    f"({uniqueness['matched_email']}). "
                    f"Please log in to your existing account instead of creating a new one."
                ),
                'confidence': 0,
            })

        # ── Step 2: Verify selfie matches their own ID document ──
        from ml_engine.kyc_face import verify_face_kyc
        result = verify_face_kyc(selfie_b64, id_image)

        # ── Step 3: Save embedding + send email if verified ─────────
        if result.match and uniqueness.get('embedding'):
            save_face_embedding(request.user, uniqueness['embedding'])
            try:
                from notification.email_service import send_kyc_verified_email
                send_kyc_verified_email(request.user, confidence=round(result.confidence * 100, 1))
            except Exception as email_err:
                logger.warning(f"KYC email failed: {email_err}")

        # Store in session for loan application to pick up
        request.session['kyc_face_verified'] = result.match
        request.session['kyc_confidence']    = result.confidence

        # Save compressed selfie to loan record for admin review
        if loan and selfie_b64:
            try:
                try:
                    from loans.image_utils import compress_selfie
                except ImportError:
                    # Inline fallback if image_utils not yet deployed
                    import base64, io
                    from django.core.files.base import ContentFile
                    def compress_selfie(b64, filename="selfie.jpg"):
                        try:
                            from PIL import Image
                            img_data = base64.b64decode(b64.split(",")[-1])
                            img = Image.open(io.BytesIO(img_data)).convert("RGB")
                            img.thumbnail((600, 600))
                            buf = io.BytesIO()
                            img.save(buf, format="JPEG", quality=88)
                            return ContentFile(buf.getvalue(), name=filename)
                        except Exception:
                            return None
                selfie_file = compress_selfie(selfie_b64, filename=f"kyc_selfie_{loan.id}.jpg")
                if selfie_file:
                    loan.kyc_selfie        = selfie_file
                    loan.kyc_face_verified = result.match
                    loan.kyc_confidence    = round(result.confidence * 100, 1)
                    loan.save(update_fields=['kyc_selfie', 'kyc_face_verified', 'kyc_confidence'])
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Could not save KYC selfie: {e}")

        response = {
            'match':      result.match,
            'confidence': result.confidence,
            'distance':   result.distance,
        }
        if result.error:
            response['error'] = result.error
        if not result.selfie_face_found:
            response['error'] = 'No face detected in your selfie. Please ensure good lighting and look directly at the camera.'
        if not result.id_face_found:
            response['error'] = 'Could not find a face in your ID document. Please ensure your ID photo is clear.'

        # ── Tell frontend where to redirect after KYC ─────────
        pending_loan_id = request.session.get('pending_kyc_loan_id')
        kyc_next        = request.session.pop('kyc_next', None)
        if pending_loan_id:
            response['redirect'] = f'/loans/finalize/{pending_loan_id}/'
        elif kyc_next:
            response['redirect'] = kyc_next
        else:
            response['redirect'] = '/loans/my-loans/'

        return JsonResponse(response)

    except Exception as e:
        return JsonResponse({'error': f'Verification failed: {str(e)}'})


@login_required
def kyc_redo(request):
    """Clear KYC session and send back to verification page."""
    request.session.pop('kyc_face_verified', None)
    request.session.pop('kyc_confidence', None)
    request.session.pop('kyc_selfie_b64', None)
    messages.info(request, "Face verification cleared — please verify again.")
    return redirect('kyc_verify')