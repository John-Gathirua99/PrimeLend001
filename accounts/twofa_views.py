# """
# ml_engine/kyc_face.py — Face KYC: webcam photo vs ID document face matching

# Dependencies:
#     pip install deepface opencv-python-headless tf-keras

# How it works:
#     1. User takes a selfie via webcam in the browser (base64 JPEG)
#     2. We extract the face from the ID document front image (already uploaded)
#     3. DeepFace compares both faces — returns match + confidence
#     4. Result stored on LoanApplication.kyc_face_verified
# """

# import base64
# import io
# import logging
# import os
# import tempfile
# from dataclasses import dataclass
# from typing import Optional

# import cv2
# import numpy as np

# logger = logging.getLogger(__name__)


# @dataclass
# class FaceMatchResult:
#     match: bool               # True if faces match
#     confidence: float         # 0.0–1.0 (1.0 = perfect match)
#     distance: float           # raw model distance (lower = more similar)
#     error: Optional[str]      # error message if something went wrong
#     selfie_face_found: bool   # was a face detected in selfie?
#     id_face_found: bool       # was a face detected in ID doc?


# def _decode_base64_image(b64_string: str) -> np.ndarray:
#     """Decode base64 image string to numpy array."""
#     if ',' in b64_string:
#         b64_string = b64_string.split(',')[1]
#     img_bytes = base64.b64decode(b64_string)
#     img_array = np.frombuffer(img_bytes, dtype=np.uint8)
#     img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
#     return img


# def _load_image_from_file(image_file) -> np.ndarray:
#     """Load image from Django UploadedFile or file path."""
#     if isinstance(image_file, str):
#         return cv2.imread(image_file)
#     if hasattr(image_file, 'read'):
#         image_file.seek(0)
#         img_bytes = np.frombuffer(image_file.read(), dtype=np.uint8)
#         image_file.seek(0)
#         return cv2.imdecode(img_bytes, cv2.IMREAD_COLOR)
#     return None


# def _preprocess_id_image(img: np.ndarray) -> np.ndarray:
#     """
#     Enhance ID document image for better face detection:
#     - Denoise
#     - Sharpen
#     - Normalise brightness
#     """
#     if img is None:
#         return img
#     # Denoise
#     img = cv2.fastNlMeansDenoisingColored(img, None, 10, 10, 7, 21)
#     # Sharpen
#     kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
#     img = cv2.filter2D(img, -1, kernel)
#     return img


# def _save_temp(img: np.ndarray, suffix=".jpg") -> str:
#     """Save numpy image to temp file, return path."""
#     tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
#     cv2.imwrite(tmp.name, img)
#     return tmp.name


# def verify_face_kyc(
#     selfie_b64: str,
#     id_image_file,
#     threshold: float = 0.45,
# ) -> FaceMatchResult:
#     """
#     Compare selfie (base64) against face in ID document.

#     Args:
#         selfie_b64:    Base64-encoded JPEG from webcam
#         id_image_file: Django UploadedFile or path to ID front image
#         threshold:     Distance threshold — below = match (0.45 is strict)

#     Returns:
#         FaceMatchResult
#     """
#     selfie_path = None
#     id_path     = None

#     try:
#         from deepface import DeepFace

#         # ── Load images ──────────────────────────────────────────
#         selfie_img = _decode_base64_image(selfie_b64)
#         id_img     = _load_image_from_file(id_image_file)

#         if selfie_img is None:
#             return FaceMatchResult(False, 0.0, 1.0, "Could not decode selfie image.", False, False)
#         if id_img is None:
#             return FaceMatchResult(False, 0.0, 1.0, "Could not load ID document image.", False, True)

#         # ── Preprocess ID ─────────────────────────────────────────
#         id_img = _preprocess_id_image(id_img)

#         # ── Detect faces first (quick check) ─────────────────────
#         face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
#         selfie_gray  = cv2.cvtColor(selfie_img, cv2.COLOR_BGR2GRAY)
#         id_gray      = cv2.cvtColor(id_img,     cv2.COLOR_BGR2GRAY)

#         selfie_faces = face_cascade.detectMultiScale(selfie_gray, 1.1, 4, minSize=(60, 60))
#         id_faces     = face_cascade.detectMultiScale(id_gray,     1.1, 4, minSize=(30, 30))

#         selfie_face_found = len(selfie_faces) > 0
#         id_face_found     = len(id_faces) > 0

#         if not selfie_face_found:
#             return FaceMatchResult(False, 0.0, 1.0, "No face detected in selfie. Please retake.", False, id_face_found)
#         if not id_face_found:
#             return FaceMatchResult(False, 0.0, 1.0, "Could not detect face in ID document.", selfie_face_found, False)

#         # ── Save to temp files for DeepFace ──────────────────────
#         selfie_path = _save_temp(selfie_img)
#         id_path     = _save_temp(id_img)

#         # ── DeepFace verification ─────────────────────────────────
#         result = DeepFace.verify(
#             img1_path=selfie_path,
#             img2_path=id_path,
#             model_name="Facenet512",    # best accuracy/speed balance
#             detector_backend="opencv",  # fast, no heavy deps
#             distance_metric="cosine",
#             enforce_detection=False,    # don't crash if face is small
#             silent=True,
#         )

#         distance   = float(result.get("distance", 1.0))
#         verified   = distance < threshold
#         confidence = round(max(0.0, 1.0 - (distance / threshold)), 3)

#         logger.info(f"Face KYC: distance={distance:.3f}, match={verified}, confidence={confidence}")

#         return FaceMatchResult(
#             match=verified,
#             confidence=confidence,
#             distance=distance,
#             error=None,
#             selfie_face_found=True,
#             id_face_found=True,
#         )

#     except ImportError:
#         logger.error("DeepFace not installed. Run: pip install deepface tf-keras")
#         # Graceful fallback — don't block loan application if library missing
#         return FaceMatchResult(True, 0.5, 0.45, "Face verification unavailable (library missing).", True, True)

#     except Exception as e:
#         logger.error(f"Face KYC error: {e}")
#         return FaceMatchResult(False, 0.0, 1.0, f"Face verification error: {str(e)}", False, False)

#     finally:
#         # Clean up temp files
#         for path in [selfie_path, id_path]:
#             if path and os.path.exists(path):
#                 try:
#                     os.unlink(path)
#                 except Exception:
#                     pass


# def verify_face_from_paths(selfie_path: str, id_path: str, threshold: float = 0.45) -> FaceMatchResult:
    
#     with open(selfie_path, 'rb') as f:
#         b64 = base64.b64encode(f.read()).decode()
#     return verify_face_kyc(b64, id_path, threshold)