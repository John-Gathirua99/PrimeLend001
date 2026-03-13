"""
ID Authenticity Checks — three independent layers:

  1. MRZ Validation     — checks Machine Readable Zone checksum math
  2. ELA Tampering      — Error Level Analysis detects image editing
  3. Face Detection     — confirms a face photo exists on the ID

Install requirements:
    pip install opencv-python-headless Pillow numpy pytesseract

Usage:
    from ml_engine.id_authenticity import check_id_authenticity
    result = check_id_authenticity(image_file)
"""

import io
import math
import logging
import re
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────────────────────

@dataclass
class AuthenticityResult:
    authentic:          bool            # overall verdict
    confidence:         float           # 0.0 – 1.0

    mrz_found:          Optional[bool]  = None
    mrz_valid:          Optional[bool]  = None
    mrz_details:        str             = ""

    ela_score:          Optional[float] = None   # 0=clean, 1=heavily tampered
    ela_tampered:       Optional[bool]  = None
    ela_details:        str             = ""

    face_found:         Optional[bool]  = None
    face_details:       str             = ""

    failures:           list            = field(default_factory=list)
    warnings:           list            = field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _load_image_cv2(image_file):
    """Load Django UploadedFile → OpenCV BGR array."""
    import cv2
    image_file.seek(0)
    raw = np.frombuffer(image_file.read(), np.uint8)
    image_file.seek(0)
    img = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    return img


def _load_image_pil(image_file):
    """Load Django UploadedFile → PIL Image (RGB)."""
    from PIL import Image
    image_file.seek(0)
    img = Image.open(io.BytesIO(image_file.read())).convert("RGB")
    image_file.seek(0)
    return img


# ─────────────────────────────────────────────────────────────
# CHECK 1 — MRZ Validation
# ─────────────────────────────────────────────────────────────
# Kenya National ID MRZ format (TD1 — 3 lines × 30 chars):
#   Line 1: IDKEN<document_number<check<...
#   Line 2: birth_date + check + sex + expiry + check + nationality + ...
#   Line 3: surname<<given_names
#
# MRZ check digit algorithm (ICAO 9303):
#   weights cycle 7, 3, 1 over character values
#   digits=face value, A-Z=10-35, <(filler)=0

MRZ_WEIGHTS = [7, 3, 1]
MRZ_VALUES  = {str(i): i for i in range(10)}
MRZ_VALUES.update({chr(i + 65): i + 10 for i in range(26)})
MRZ_VALUES['<'] = 0


def _mrz_check_digit(s: str) -> int:
    total = 0
    for i, ch in enumerate(s.upper()):
        total += MRZ_VALUES.get(ch, 0) * MRZ_WEIGHTS[i % 3]
    return total % 10


def _extract_mrz_lines(ocr_text: str) -> list:
    """
    Find MRZ lines in OCR text.
    MRZ lines are long strings containing only A-Z, 0-9, and <
    TD1 = 30 chars, TD3 = 44 chars
    """
    lines = []
    for line in ocr_text.split('\n'):
        clean = re.sub(r'[^A-Z0-9<]', '', line.upper())
        if len(clean) >= 28:   # allow slight OCR noise
            lines.append(clean)
    return lines


def validate_mrz(image_file, ocr_text: str = "") -> dict:
    """
    Attempt to extract and validate MRZ from OCR text.
    Returns dict with found, valid, details.
    """
    result = {"found": False, "valid": None, "details": ""}

    # Try to find MRZ in existing OCR text
    mrz_lines = _extract_mrz_lines(ocr_text)

    # If not found in OCR, try re-scanning bottom 30% of image (MRZ zone)
    if len(mrz_lines) < 2:
        try:
            import pytesseract
            import cv2
            import os

            tesseract_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            if os.path.exists(tesseract_path):
                pytesseract.pytesseract.tesseract_cmd = tesseract_path

            img = _load_image_cv2(image_file)
            if img is not None:
                h, w = img.shape[:2]
                # Crop bottom 35% — MRZ zone
                mrz_region = img[int(h * 0.65):, :]
                # Upscale for better OCR
                mrz_region = cv2.resize(mrz_region, None, fx=2, fy=2,
                                        interpolation=cv2.INTER_CUBIC)
                gray = cv2.cvtColor(mrz_region, cv2.COLOR_BGR2GRAY)
                _, thresh = cv2.threshold(gray, 0, 255,
                                          cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                from PIL import Image as PILImage
                pil = PILImage.fromarray(thresh)
                # PSM 6 = uniform block, good for MRZ
                extra_text = pytesseract.image_to_string(
                    pil, config="--psm 6 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"
                )
                mrz_lines += _extract_mrz_lines(extra_text)
        except Exception as e:
            logger.debug(f"MRZ re-scan failed: {e}")

    if len(mrz_lines) < 2:
        result["found"]   = False
        result["details"] = "No MRZ detected — ID may be too blurry or non-standard format"
        return result

    result["found"] = True
    line1 = mrz_lines[0][:30].ljust(30, '<')
    line2 = mrz_lines[1][:30].ljust(30, '<') if len(mrz_lines) > 1 else ""

    checks_passed = 0
    checks_total  = 0
    details       = []

    if len(line2) >= 14:
        # Birth date (pos 0-5) + check (pos 6)
        dob_field = line2[0:6]
        dob_check = line2[6:7]
        if dob_check.isdigit():
            checks_total += 1
            expected = _mrz_check_digit(dob_field)
            if expected == int(dob_check):
                checks_passed += 1
                details.append("✓ Date of birth checksum valid")
            else:
                details.append(f"✗ Date of birth checksum FAIL (expected {expected}, got {dob_check})")

        # Expiry date (pos 8-13) + check (pos 14)
        if len(line2) >= 15:
            exp_field = line2[8:14]
            exp_check = line2[14:15]
            if exp_check.isdigit():
                checks_total += 1
                expected = _mrz_check_digit(exp_field)
                if expected == int(exp_check):
                    checks_passed += 1
                    details.append("✓ Expiry date checksum valid")
                else:
                    details.append(f"✗ Expiry date checksum FAIL (expected {expected}, got {exp_check})")

    # Document number from line1 (Kenya ID: pos 5-13) + check (pos 14)
    if len(line1) >= 15:
        doc_field = line1[5:14]
        doc_check = line1[14:15]
        if doc_check.isdigit():
            checks_total += 1
            expected = _mrz_check_digit(doc_field)
            if expected == int(doc_check):
                checks_passed += 1
                details.append("✓ Document number checksum valid")
            else:
                details.append(f"✗ Document number checksum FAIL (expected {expected}, got {doc_check})")

    if checks_total == 0:
        result["valid"]   = None
        result["details"] = "MRZ found but checksums could not be read (OCR noise likely)"
    else:
        result["valid"]   = (checks_passed == checks_total)
        rate = checks_passed / checks_total
        result["details"] = (
            f"MRZ checks: {checks_passed}/{checks_total} passed "
            f"({rate:.0%}) — " + "; ".join(details)
        )

    return result


# ─────────────────────────────────────────────────────────────
# CHECK 2 — ELA (Error Level Analysis) Tampering Detection
# ─────────────────────────────────────────────────────────────
# How it works:
#   1. Re-save the image at a known JPEG quality (95%)
#   2. Compute pixel-level difference between original and re-saved
#   3. Tampered regions had different original compression →
#      they show higher error levels than authentic regions
#   4. If high-error regions are clustered (not uniform noise),
#      it indicates copy-paste or local editing

def check_ela_tampering(image_file, quality: int = 95) -> dict:
    """
    Run Error Level Analysis on the ID image.
    Returns dict with tampered (bool), score (float 0-1), details.
    """
    result = {"tampered": None, "score": None, "details": ""}

    try:
        from PIL import Image, ImageChops, ImageEnhance
        import numpy as np

        original_pil = _load_image_pil(image_file)

        # Re-save at known quality
        buffer = io.BytesIO()
        original_pil.save(buffer, format="JPEG", quality=quality)
        buffer.seek(0)
        recompressed = Image.open(buffer).convert("RGB")

        # Pixel-level difference
        diff = ImageChops.difference(original_pil, recompressed)
        diff_arr = np.array(diff).astype(np.float32)

        # Amplify for analysis
        amplified = np.clip(diff_arr * 10, 0, 255)

        # Overall ELA score — mean error level (0=clean, 255=max tamper)
        mean_error = float(amplified.mean())
        ela_score  = min(1.0, mean_error / 30.0)   # normalise: >30 mean = very suspicious

        # Spatial variance — uniform noise = camera artifact, clustered = editing
        # Divide image into 8×8 blocks, check variance of block means
        h, w = amplified.shape[:2]
        block_means = []
        block_size  = max(1, min(h, w) // 8)
        for y in range(0, h - block_size, block_size):
            for x in range(0, w - block_size, block_size):
                block = amplified[y:y+block_size, x:x+block_size]
                block_means.append(float(block.mean()))

        if block_means:
            spatial_variance = float(np.var(block_means))
            # High variance = uneven error distribution = likely tampering
            variance_flag = spatial_variance > 200
        else:
            spatial_variance = 0
            variance_flag    = False

        # Combined decision
        tampered = ela_score > 0.55 or (ela_score > 0.30 and variance_flag)
        result["tampered"] = tampered
        result["score"]    = round(ela_score, 3)

        if tampered:
            result["details"] = (
                f"Possible image tampering detected — ELA score: {ela_score:.2f}, "
                f"spatial variance: {spatial_variance:.0f}. "
                f"Inconsistent compression suggests regions may have been edited."
            )
        else:
            result["details"] = (
                f"No significant tampering detected — ELA score: {ela_score:.2f} "
                f"(threshold 0.55). Image compression appears uniform."
            )

    except Exception as e:
        logger.warning(f"ELA check failed: {e}")
        result["details"] = f"ELA check could not run: {e}"

    return result


# ─────────────────────────────────────────────────────────────
# CHECK 3 — Face Detection
# ─────────────────────────────────────────────────────────────
# Uses OpenCV Haar cascade to find a face in the ID photo zone.
# Kenya National ID has a photo in the upper-left ~25% of the card.

def check_face_present(image_file) -> dict:
    """
    Detect whether a face photo exists on the ID document.
    Returns dict with found (bool), count, details.
    """
    result = {"found": None, "count": 0, "details": ""}

    try:
        import cv2
        import os

        img = _load_image_cv2(image_file)
        if img is None:
            result["details"] = "Could not decode image for face detection"
            return result

        h, w = img.shape[:2]

        # Focus on left 45% of card (photo zone on Kenya ID)
        photo_zone = img[:, :int(w * 0.45)]

        gray = cv2.cvtColor(photo_zone, cv2.COLOR_BGR2GRAY)
        # Upscale small images
        if w < 600:
            scale = 600 / w
            gray  = cv2.resize(gray, None, fx=scale, fy=scale,
                               interpolation=cv2.INTER_CUBIC)

        # Load Haar cascade (bundled with OpenCV)
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        if not os.path.exists(cascade_path):
            result["details"] = "Face cascade file not found — skipping face check"
            return result

        face_cascade = cv2.CascadeClassifier(cascade_path)
        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.05,
            minNeighbors=3,
            minSize=(30, 30),
            flags=cv2.CASCADE_SCALE_IMAGE,
        )

        count = len(faces) if hasattr(faces, '__len__') else 0
        result["count"] = count
        result["found"] = count >= 1

        if count >= 1:
            result["details"] = f"Face photo detected on ID ({count} face(s) found in photo zone)"
        else:
            # Try full image fallback before failing
            faces_full = face_cascade.detectMultiScale(
                cv2.cvtColor(img, cv2.COLOR_BGR2GRAY),
                scaleFactor=1.05, minNeighbors=3, minSize=(25, 25)
            )
            count_full = len(faces_full) if hasattr(faces_full, '__len__') else 0
            if count_full >= 1:
                result["found"]   = True
                result["count"]   = count_full
                result["details"] = f"Face detected on document ({count_full} found)"
            else:
                result["found"]   = False
                result["details"] = (
                    "No face photo detected on ID. "
                    "Document may be a photocopy, screenshot, or non-standard format."
                )

    except Exception as e:
        logger.warning(f"Face detection failed: {e}")
        result["details"] = f"Face detection could not run: {e}"

    return result


# ─────────────────────────────────────────────────────────────
# MASTER — run all three checks
# ─────────────────────────────────────────────────────────────

def check_id_authenticity(image_file, ocr_text: str = "") -> AuthenticityResult:
    """
    Run all three authenticity checks on an uploaded ID image.

    Args:
        image_file: Django UploadedFile (front of ID)
        ocr_text:   Pre-extracted OCR text (optional — avoids re-running OCR)

    Returns:
        AuthenticityResult dataclass
    """
    result = AuthenticityResult(authentic=False, confidence=0.0)

    scores   = []
    failures = []
    warnings = []

    # ── 1. MRZ ───────────────────────────────────────────────
    try:
        mrz = validate_mrz(image_file, ocr_text)
        result.mrz_found   = mrz["found"]
        result.mrz_valid   = mrz["valid"]
        result.mrz_details = mrz["details"]

        if mrz["found"] and mrz["valid"] is True:
            scores.append(1.0)
        elif mrz["found"] and mrz["valid"] is False:
            scores.append(0.0)
            failures.append("MRZ checksum failed — document may be forged or OCR was inaccurate")
        elif mrz["found"] and mrz["valid"] is None:
            scores.append(0.5)
            warnings.append("MRZ found but checksums could not be fully verified")
        else:
            scores.append(0.4)   # no MRZ = inconclusive, not hard fail
            warnings.append("No MRZ detected — image quality may be too low for full verification")
    except Exception as e:
        logger.error(f"MRZ check error: {e}")
        warnings.append(f"MRZ check skipped due to error: {e}")

    # ── 2. ELA Tampering ─────────────────────────────────────
    try:
        ela = check_ela_tampering(image_file)
        result.ela_score    = ela["score"]
        result.ela_tampered = ela["tampered"]
        result.ela_details  = ela["details"]

        if ela["tampered"] is True:
            scores.append(0.0)
            failures.append(f"Image tampering detected (ELA score: {ela['score']:.2f}) — possible forgery")
        elif ela["tampered"] is False:
            scores.append(1.0)
        else:
            scores.append(0.5)
            warnings.append("Tampering check inconclusive")
    except Exception as e:
        logger.error(f"ELA check error: {e}")
        warnings.append(f"Tampering check skipped: {e}")

    # ── 3. Face Detection ────────────────────────────────────
    try:
        face = check_face_present(image_file)
        result.face_found   = face["found"]
        result.face_details = face["details"]

        if face["found"] is True:
            scores.append(1.0)
        elif face["found"] is False:
            scores.append(0.0)
            failures.append("No face photo found on document — may be a photocopy or screenshot")
        else:
            scores.append(0.5)
            warnings.append("Face detection inconclusive")
    except Exception as e:
        logger.error(f"Face check error: {e}")
        warnings.append(f"Face detection skipped: {e}")

    # ── Overall verdict ───────────────────────────────────────
    confidence = float(np.mean(scores)) if scores else 0.0
    result.confidence = round(confidence, 3)
    result.failures   = failures
    result.warnings   = warnings

    # Hard fail on any definitive failure
    # Soft fail (flag for manual review) if confidence < 0.5
    if failures:
        result.authentic = False
    elif confidence >= 0.60:
        result.authentic = True
    else:
        result.authentic  = False
        result.warnings.append(
            f"Overall authenticity confidence too low ({confidence:.0%}) — flagged for manual review"
        )

    return result