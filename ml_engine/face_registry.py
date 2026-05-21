"""
Face Registry — stores and checks face embeddings across all accounts.

When a user completes KYC:
1. Extract DeepFace embedding from their selfie
2. Compare against ALL embeddings in the system
3. If match found on different account → block (possible fake account)
4. If no match → save embedding to their profile

This prevents one person from creating multiple accounts.
"""
import json
import logging
import numpy as np

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.40   # cosine distance — lower = more similar
                               # 0.40 is strict; increase to 0.50 if too many false positives


def get_embedding(image_path_or_b64):
    """
    Extract a 512-dim face embedding from an image.
    Returns numpy array or None if face not found.
    """
    try:
        from deepface import DeepFace
        import tempfile, os, base64
        from PIL import Image
        import io

        # Handle base64 input
        if isinstance(image_path_or_b64, str) and image_path_or_b64.startswith('data:'):
            b64 = image_path_or_b64.split(',')[1]
            img_bytes = base64.b64decode(b64)
            img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
            tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
            img.save(tmp.name, 'JPEG', quality=92)
            path = tmp.name
            cleanup = True
        else:
            path = str(image_path_or_b64)
            cleanup = False

        repr_kwargs = dict(
            img_path=path,
            model_name='Facenet512',
            detector_backend='opencv',
            enforce_detection=False,
        )
        try:
            result = DeepFace.represent(**repr_kwargs, silent=True)
        except TypeError:
            result = DeepFace.represent(**repr_kwargs)

        if cleanup:
            try:
                os.unlink(path)
            except Exception:
                pass

        if result and len(result) > 0:
            return np.array(result[0]['embedding'], dtype=np.float32)
        return None

    except Exception as e:
        logger.error(f"Embedding extraction failed: {e}")
        return None


def cosine_distance(a, b):
    """Cosine distance between two embedding vectors (0=identical, 1=opposite)."""
    a = np.array(a, dtype=np.float32)
    b = np.array(b, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return float(1.0 - np.dot(a, b) / (norm_a * norm_b))


def check_face_uniqueness(selfie_b64, current_user):
    """
    Compare selfie embedding against all registered faces in the system.

    Returns dict:
        {
            'unique': True/False,
            'matched_user': User or None,   # if not unique
            'matched_email': str or None,   # masked email
            'distance': float,
            'embedding': list,              # extracted embedding to save
            'error': str or None,
        }
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    # Extract embedding from new selfie
    embedding = get_embedding(selfie_b64)
    if embedding is None:
        return {
            'unique': True,  # can't check, allow through
            'matched_user': None,
            'matched_email': None,
            'distance': 1.0,
            'embedding': None,
            'error': 'Could not extract face from selfie.',
        }

    # Load all profiles that have a stored embedding
    try:
        from accounts.models import UserProfile
        profiles = UserProfile.objects.exclude(
            face_embedding__isnull=True
        ).exclude(
            face_embedding=''
        ).select_related('user')
    except Exception as e:
        logger.error(f"Could not load profiles: {e}")
        return {
            'unique': True,
            'matched_user': None,
            'matched_email': None,
            'distance': 1.0,
            'embedding': embedding.tolist(),
            'error': None,
        }

    best_match_user     = None
    best_match_distance = 1.0

    for profile in profiles:
        try:
            stored = json.loads(profile.face_embedding)
            dist   = cosine_distance(embedding, stored)

            if dist < best_match_distance:
                best_match_distance = dist
                best_match_user     = profile.user
        except Exception:
            continue

    # Check if best match is below threshold
    if best_match_distance <= SIMILARITY_THRESHOLD and best_match_user is not None:
        if best_match_user.id == current_user.id:
            # Same user — already registered
            return {
                'unique': True,
                'already_registered': True,
                'matched_user': best_match_user,
                'matched_email': None,
                'distance': best_match_distance,
                'embedding': embedding.tolist(),
                'error': None,
            }
        else:
            # Different account — block
            email = best_match_user.email
            masked = mask_email(email)
            return {
                'unique': False,
                'already_registered': False,
                'matched_user': best_match_user,
                'matched_email': masked,
                'distance': best_match_distance,
                'embedding': embedding.tolist(),
                'error': None,
            }

    # No match found — face is unique
    return {
        'unique': True,
        'already_registered': False,
        'matched_user': None,
        'matched_email': None,
        'distance': best_match_distance,
        'embedding': embedding.tolist(),
        'error': None,
    }


def save_face_embedding(user, embedding_list):
    """Save face embedding to user profile."""
    try:
        from accounts.models import UserProfile
        profile = UserProfile.objects.get(user=user)
        profile.face_embedding     = json.dumps(embedding_list)
        profile.face_kyc_verified  = True
        profile.save(update_fields=['face_embedding', 'face_kyc_verified'])
        logger.info(f"Face embedding saved for user {user.id}")
        return True
    except Exception as e:
        logger.error(f"Could not save face embedding: {e}")
        return False


def mask_email(email):
    """Partially mask an email for display: j***@gmail.com"""
    try:
        local, domain = email.split('@')
        if len(local) <= 2:
            masked_local = '*' * len(local)
        else:
            masked_local = local[0] + '*' * (len(local) - 2) + local[-1]
        return f"{masked_local}@{domain}"
    except Exception:
        return "another account"