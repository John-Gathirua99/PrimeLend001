"""
ml_engine/kyc_face.py — Face KYC: webcam selfie vs ID document face matching
Improved: tries multiple ID crop regions, relaxed detection, better fallbacks.
"""

import base64
import io
import logging
import os
import tempfile
from dataclasses import dataclass
from typing import Optional

try:
    import cv2
except ImportError:
    cv2 = None  # not available in production
try:
    import numpy
except ImportError:
    numpy = None  # not available in production as np

logger = logging.getLogger(__name__)

MAX_PROCESS_WIDTH  = 900
MAX_PROCESS_HEIGHT = 700


@dataclass
class FaceMatchResult:
    match: bool
    confidence: float
    distance: float
    error: Optional[str]
    selfie_face_found: bool
    id_face_found: bool


def _decode_base64_image(b64_string: str) -> Optional[np.ndarray]:
    try:
        if ',' in b64_string:
            b64_string = b64_string.split(',')[1]
        img_bytes = base64.b64decode(b64_string)
        img_array = np.frombuffer(img_bytes, dtype=np.uint8)
        return cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    except Exception as e:
        logger.error(f"Base64 decode failed: {e}")
        return None


def _load_image_from_file(image_file) -> Optional[np.ndarray]:
    try:
        if isinstance(image_file, str):
            return cv2.imread(image_file)
        if hasattr(image_file, 'path'):
            return cv2.imread(image_file.path)
        if hasattr(image_file, 'read'):
            image_file.seek(0)
            img_bytes = np.frombuffer(image_file.read(), dtype=np.uint8)
            image_file.seek(0)
            return cv2.imdecode(img_bytes, cv2.IMREAD_COLOR)
        from django.conf import settings
        full_path = os.path.join(settings.MEDIA_ROOT, str(image_file))
        return cv2.imread(full_path)
    except Exception as e:
        logger.error(f"Image load failed: {e}")
        return None


def _resize_to_max(img: np.ndarray, max_w: int, max_h: int) -> np.ndarray:
    h, w = img.shape[:2]
    if w <= max_w and h <= max_h:
        return img
    scale = min(max_w / w, max_h / h)
    return cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def _get_id_crops(img: np.ndarray) -> list:
    """
    Return multiple candidate crops from the ID image.
    Kenyan IDs have the face on the LEFT side, but we try both sides
    plus full image as fallback.
    """
    h, w = img.shape[:2]

    # If portrait orientation, rotate to landscape first
    if h > w:
        img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        h, w = img.shape[:2]

    crops = [
        ("left_40",  img[0:h, 0:int(w*0.42)]),
        ("left_50",  img[0:h, 0:int(w*0.50)]),
        ("right_40", img[0:h, int(w*0.58):w]),
        ("full",     img),
    ]
    return [(label, crop) for label, crop in crops
            if crop.shape[0] > 40 and crop.shape[1] > 40]


def _detect_face_opencv(img: np.ndarray) -> bool:
    """Quick OpenCV face detection check."""
    try:
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        gray  = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, 1.05, 3, minSize=(20, 20))
        if len(faces) > 0:
            return True
        # Try with histogram equalization
        eq    = cv2.equalizeHist(gray)
        faces = cascade.detectMultiScale(eq, 1.05, 2, minSize=(15, 15))
        return len(faces) > 0
    except Exception:
        return False


def _save_temp(img: np.ndarray, suffix=".jpg") -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    cv2.imwrite(tmp.name, img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return tmp.name


def _best_id_crop(id_img: np.ndarray) -> tuple:
    """
    Try all crop regions, pick the one where OpenCV detects a face.
    Falls back to left crop if none detected.
    """
    crops = _get_id_crops(id_img)
    for label, crop in crops:
        resized = _resize_to_max(crop, MAX_PROCESS_WIDTH, MAX_PROCESS_HEIGHT)
        if _detect_face_opencv(resized):
            logger.info(f"[KYC] Face found in ID crop: {label}")
            return True, resized
    # No face found by OpenCV — return left crop and let DeepFace try
    logger.warning("[KYC] OpenCV found no face in ID — using left crop for DeepFace")
    _, left_crop = crops[0]
    return False, _resize_to_max(left_crop, MAX_PROCESS_WIDTH, MAX_PROCESS_HEIGHT)


def verify_face_kyc(
    selfie_b64: str,
    id_image_file,
    threshold: float = 0.55,
) -> FaceMatchResult:
    """
    Compare selfie (base64) against face in ID document.
    Returns FaceMatchResult.
    """
    selfie_path = None
    id_path     = None

    try:
        from deepface import DeepFace
        from django.conf import settings

        # Validate ID file on disk
        id_disk_path = os.path.join(settings.MEDIA_ROOT, str(id_image_file))
        if not os.path.exists(id_disk_path):
            return FaceMatchResult(False, 0.0, 1.0,
                "ID document file not found. Please re-upload your ID.",
                False, False)

        # Load images
        selfie_img = _decode_base64_image(selfie_b64)
        id_img     = cv2.imread(id_disk_path)

        if selfie_img is None:
            return FaceMatchResult(False, 0.0, 1.0,
                "Could not decode selfie image.", False, False)
        if id_img is None:
            return FaceMatchResult(False, 0.0, 1.0,
                "Could not load ID document image.", False, False)

        logger.info(f"[KYC] Selfie: {selfie_img.shape[1]}x{selfie_img.shape[0]} | "
                    f"ID: {id_img.shape[1]}x{id_img.shape[0]}")

        # Resize selfie
        selfie_img = _resize_to_max(selfie_img, MAX_PROCESS_WIDTH, MAX_PROCESS_HEIGHT)
        selfie_face_found = _detect_face_opencv(selfie_img)

        if not selfie_face_found:
            logger.warning("[KYC] No face in selfie via OpenCV — letting DeepFace try anyway")

        # Get best ID crop
        id_face_found, id_crop = _best_id_crop(id_img)

        # Save to temp files
        selfie_path = _save_temp(selfie_img)
        id_path     = _save_temp(id_crop)

        logger.info(f"[KYC] Comparing selfie vs ID crop "
                    f"({id_crop.shape[1]}x{id_crop.shape[0]})")

        # Try multiple model/backend combos for robustness
        attempts = [
            ("Facenet512", "opencv",  0.55),
            ("Facenet",    "opencv",  0.50),
            ("Facenet512", "skip",    0.55),
            ("VGG-Face",   "opencv",  0.68),
        ]

        last_error  = None
        best_result = None
        best_dist   = 1.0

        for model, backend, thresh in attempts:
            try:
                kwargs = dict(
                    img1_path=selfie_path,
                    img2_path=id_path,
                    model_name=model,
                    detector_backend=backend,
                    distance_metric="cosine",
                    enforce_detection=False,
                )
                try:
                    r = DeepFace.verify(**kwargs, silent=True)
                except TypeError:
                    r = DeepFace.verify(**kwargs)

                dist = float(r.get('distance', 1.0))
                logger.info(f"[KYC] {model}/{backend} dist={dist:.4f} thresh={thresh}")

                if dist < best_dist:
                    best_dist   = dist
                    best_result = r
                    # If clearly matched, stop early
                    if dist <= thresh:
                        break

            except Exception as e:
                last_error = str(e)
                logger.warning(f"[KYC] {model}/{backend} failed: {e}")
                continue

        if best_result is None:
            return FaceMatchResult(False, 0.0, 1.0,
                f"Face comparison failed: {last_error}",
                selfie_face_found, id_face_found)

        verified   = best_dist <= threshold
        confidence = max(0.0, min(1.0, 1.0 - (best_dist / threshold)))

        logger.info(f"[KYC] Final — dist={best_dist:.4f} match={verified} "
                    f"confidence={confidence:.1%}")

        return FaceMatchResult(
            match=verified,
            confidence=confidence,
            distance=best_dist,
            error=None,
            selfie_face_found=selfie_face_found,
            id_face_found=id_face_found,
        )

    except ImportError:
        return FaceMatchResult(False, 0.0, 1.0,
            "Verification service unavailable — DeepFace not installed.",
            False, False)

    except Exception as e:
        logger.error(f"[KYC] Unexpected error: {e}", exc_info=True)
        return FaceMatchResult(False, 0.0, 1.0,
            f"Verification error: {str(e)[:120]}",
            False, False)

    finally:
        for path in [selfie_path, id_path]:
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except Exception:
                    pass



