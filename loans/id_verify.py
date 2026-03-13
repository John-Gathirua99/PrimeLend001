"""
ml_engine/id_verify.py — Kenyan National ID verification via OCR
"""

import re
import os
import logging
from dataclasses import dataclass, field
from typing import Optional, List

logger = logging.getLogger(__name__)

try:
    from ml_engine.id_authenticity import check_id_authenticity
    AUTHENTICITY_AVAILABLE = True
except ImportError:
    AUTHENTICITY_AVAILABLE = False

TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


@dataclass
class IDVerificationResult:
    passed: bool
    id_number_match: Optional[bool] = None
    name_match: Optional[bool] = None
    id_reused: bool = False
    extracted_id: Optional[str] = None
    extracted_name: Optional[str] = None
    extracted_dob: Optional[str] = None
    extracted_gender: Optional[str] = None
    ocr_text: Optional[str] = None
    authenticity: object = None
    failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _load_ocr():
    try:
        import pytesseract
        if os.path.exists(TESSERACT_PATH):
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
        return pytesseract
    except ImportError:
        raise ImportError("pytesseract not installed. Run: pip install pytesseract")


def _deskew(img):
    import cv2
    import numpy as np

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges   = cv2.Canny(blurred, 30, 120)
    edges   = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return img

    best = None
    best_area = 0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < (h * w * 0.10):
            continue
        peri   = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
        if len(approx) == 4 and area > best_area:
            best      = approx
            best_area = area

    if best is None:
        return img

    pts = best.reshape(4, 2).astype(np.float32)
    s   = pts.sum(axis=1)
    d   = np.diff(pts, axis=1)
    ordered = np.array([
        pts[np.argmin(s)],
        pts[np.argmin(d)],
        pts[np.argmax(s)],
        pts[np.argmax(d)],
    ], dtype=np.float32)

    card_w = int(max(
        np.linalg.norm(ordered[1] - ordered[0]),
        np.linalg.norm(ordered[2] - ordered[3])
    ))
    card_h = int(max(
        np.linalg.norm(ordered[3] - ordered[0]),
        np.linalg.norm(ordered[2] - ordered[1])
    ))

    if card_w < 100 or card_h < 60:
        return img

    dst = np.array([
        [0, 0], [card_w - 1, 0],
        [card_w - 1, card_h - 1], [0, card_h - 1]
    ], dtype=np.float32)

    M      = cv2.getPerspectiveTransform(ordered, dst)
    warped = cv2.warpPerspective(img, M, (card_w, card_h))

    # Enforce landscape — ID cards are always wider than tall
    wh, ww = warped.shape[:2]
    if wh > ww:
        warped = cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)
        wh, ww = ww, wh

    logger.info(f"[OCR] Deskewed: {w}x{h} -> {ww}x{wh}")
    return warped


def _preprocess_image(image_file):
    """
    1. Deskew the card
    2. Resize to ~1200px wide
    3. Grayscale + CLAHE contrast boost (NO binarization/threshold)
    4. Mild sharpen
    Avoids adaptive threshold which turns photos into black-and-white sketches.
    """
    try:
        import cv2
        import numpy as np
        from PIL import Image as PILImage
        import io

        image_file.seek(0)
        img_bytes = image_file.read()
        image_file.seek(0)

        nparr = np.frombuffer(img_bytes, np.uint8)
        img   = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            return PILImage.open(io.BytesIO(img_bytes)).convert("RGB")

        img    = _deskew(img)
        h, w   = img.shape[:2]

        if w > 1600:
            img = cv2.resize(img, None, fx=1200/w, fy=1200/w, interpolation=cv2.INTER_AREA)
        elif w < 800:
            img = cv2.resize(img, None, fx=1100/w, fy=1100/w, interpolation=cv2.INTER_CUBIC)

        gray     = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        clahe    = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        kernel   = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        result   = cv2.filter2D(enhanced, -1, kernel)

        return PILImage.fromarray(result)

    except Exception as e:
        logger.warning(f"Preprocessing failed, using raw: {e}")
        from PIL import Image as PILImage
        import io
        image_file.seek(0)
        return PILImage.open(io.BytesIO(image_file.read()))


def extract_text_from_id(image_file) -> str:
    pytesseract = _load_ocr()
    img         = _preprocess_image(image_file)

    configs = [
        "--psm 6 --oem 3",
        "--psm 4 --oem 3",
        "--psm 11 --oem 3",
    ]

    results = []
    for config in configs:
        try:
            text = pytesseract.image_to_string(img, config=config, timeout=25)
            results.append(text.strip())
        except Exception:
            continue

    if not results:
        return ""

    best = max(results, key=lambda t: len(t))
    logger.info(f"[OCR] Best result ({len(best)} chars):\n{best[:300]}")
    return best


def extract_id_number(text: str) -> Optional[str]:
    cleaned = text.upper()
    cleaned = re.sub(r'\bI(\d{6,7})\b', r'1\1', cleaned)

    patterns = [
        r'(?:ID\s*NAMBA)[\s:\-\.]*(\d{7,8})',
        r'(?:NAMBA)[\s:\-\.]*(\d{7,8})',
        r'(?:IDENTITY\s*(?:CARD|NO|NUMBER)?[\s:\-\.]*|ID\s*(?:NO|NUMBER|#|CARD)?[\s:\-\.]*)(\d{7,8})',
        r'(?:SERIAL\s*(?:NO|NUMBER)?[\s:\-\.]*)(\d{7,8})',
        r'(?:NAMBARI\s*(?:YA\s*KITAMBULISHO)?[\s:\-\.]*)(\d{7,8})',
        r'(?:NO[\s:\-\.]+)(\d{7,8})',
        r'(?:NUMBER[\s:\-\.]+)(\d{7,8})',
        r'(?:REF[\s:\-\.]+)(\d{7,8})',
        r'^\s*(\d{7,8})\s*$',
        r'\b(\d{8})\b',
        r'\b(\d{7})\b',
    ]

    for pattern in patterns:
        match = re.search(pattern, cleaned, re.IGNORECASE | re.MULTILINE)
        if match:
            candidate = match.group(1).strip()
            if re.fullmatch(r'[1-9]\d{6,7}', candidate):
                logger.info(f"[OCR] Extracted ID: {candidate}")
                return candidate

    logger.warning("[OCR] Could not extract ID number")
    return None


def _next_line_value(text: str, label: str) -> Optional[str]:
    """
    Kenyan IDs put label on one line, value on the NEXT line:
      SURNAME       <- label line
      MWANGI        <- value line  (what we want)
      GIVEN NAME    <- label line
      JOHN GATHIRUA <- value line
    """
    SKIP = {
        "REPUBLIC", "KENYA", "JAMHURI", "NATIONAL", "IDENTITY", "CARD",
        "KITAMBULISHO", "TAIFA", "MEANT", "PATA", "OF", "CHA", "YA",
        "SURNAME", "GIVEN", "NAME", "NAMES", "SEX", "DATE", "BIRTH",
        "PLACE", "ISSUE", "EXPIRY", "NATIONALITY", "NAMBA", "ID",
        "SERIAL", "MUNICIPALITY", "AND", "THE", "JINSIA",
    }
    lines = [l.strip() for l in text.upper().split("\n")]
    for i, line in enumerate(lines):
        if label.upper() in line:
            for j in range(i + 1, min(i + 5, len(lines))):
                val = lines[j].strip()
                if not val:
                    continue
                val_clean = re.sub(r"[^A-Z\s]", "", val).strip()
                if len(val_clean) < 2:
                    continue
                val_words = set(val_clean.split())
                if val_words.issubset(SKIP):
                    continue
                if any(phrase in val_clean for phrase in [
                    "REPUBLIC OF KENYA", "NATIONAL IDENTITY",
                    "JAMHURI YA KENYA", "KITAMBULISHO CHA TAIFA",
                ]):
                    continue
                return val_clean
    return None


def extract_name(text: str) -> Optional[str]:
    upper = text.upper()

    # Strategy 1: next-line labels (primary — Kenyan ID layout)
    surname    = _next_line_value(upper, "SURNAME")
    given_name = (
        _next_line_value(upper, "GIVEN NAME")
        or _next_line_value(upper, "GIVEN NAMES")
        or _next_line_value(upper, "OTHER NAMES")
        or _next_line_value(upper, "OTHER NAME")
    )

    if surname and given_name:
        full = re.sub(r"\s+", " ", f"{surname} {given_name}").strip()
        logger.info(f"[OCR] Name (surname+given): {full}")
        return full
    elif surname:
        logger.info(f"[OCR] Name (surname only): {surname}")
        return surname
    elif given_name:
        logger.info(f"[OCR] Name (given only): {given_name}")
        return given_name

    # Strategy 2: same-line patterns
    for pattern in [
        r"(?:FULL\s*NAME|JINA\s*KAMILI)[\s:\-\.]+([A-Z][A-Z\s]{4,45})",
        r"(?:SURNAME)[\s:\-\.]+([A-Z][A-Z\s]{2,30})",
        r"(?:GIVEN\s*NAMES?|OTHER\s*NAMES?)[\s:\-\.]+([A-Z][A-Z\s]{2,30})",
        r"(?:NAME|JINA)[\s:\-\.]+([A-Z][A-Z\s]{4,45})",
    ]:
        match = re.search(pattern, upper, re.IGNORECASE)
        if match:
            name = re.sub(r"\s+", " ", re.sub(r"[^A-Z\s]", "", match.group(1))).strip()
            if len(name) >= 3:
                logger.info(f"[OCR] Name (same-line): {name}")
                return name

    # Strategy 3: uppercase word-line heuristic
    SKIP_WORDS = {
        "REPUBLIC", "KENYA", "JAMHURI", "NATIONAL", "IDENTITY", "CARD",
        "KITAMBULISHO", "TAIFA", "MALE", "FEMALE", "KEN", "SEX", "DATE",
        "BIRTH", "PLACE", "ISSUE", "EXPIRY", "MUNICIPALITY", "NATIONALITY",
        "NAMBA", "MEANT", "PATA", "OF", "CHA", "YA", "NA", "AND", "CEI",
    }
    for line in text.split("\n"):
        line  = line.strip()
        words = line.split()
        if (1 <= len(words) <= 4
                and all(w.isalpha() and w.isupper() for w in words)
                and len(line) >= 4
                and not any(w in SKIP_WORDS for w in words)):
            logger.info(f"[OCR] Name (heuristic): {line}")
            return line

    logger.warning("[OCR] Could not extract name")
    return None


def extract_dob(text: str) -> Optional[str]:
    upper = text.upper()

    same = re.search(
        r"(?:DATE\s*OF\s*BIRTH|D\.O\.B|DOB|BORN|TAREHE\s*YA\s*KUZALIWA)"
        r"[\s:\-\.]*(\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{2,4})",
        upper, re.IGNORECASE
    )
    if same:
        return same.group(1).strip()

    dob_line = _next_line_value(upper, "DATE OF BIRTH")
    if dob_line:
        m = re.search(r"(\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{2,4})", dob_line)
        if m:
            return m.group(1)

    anywhere = re.search(r"\b(\d{2}\.\d{2}\.\d{4})\b", upper)
    if anywhere:
        return anywhere.group(1)

    return None


def extract_gender(text: str) -> Optional[str]:
    m = re.search(r"SEX[\s:\-\.]*(?:JINSIA[\s:\-\.]*)?(MALE|FEMALE)", text.upper())
    if m:
        return m.group(1)
    m = re.search(r"\b(MALE|FEMALE)\b", text.upper())
    if m:
        return m.group(1)
    return None


def _normalize(text: str) -> str:
    return re.sub(r'\s+', ' ', text.upper().strip())


def _names_match(name_on_id: str, account_name: str, threshold: float = 0.55) -> bool:
    id_words   = {w for w in _normalize(name_on_id).split()   if len(w) > 1}
    acct_words = {w for w in _normalize(account_name).split() if len(w) > 1}
    if not id_words or not acct_words:
        return False
    overlap = id_words & acct_words
    shorter = min(len(id_words), len(acct_words))
    ratio   = len(overlap) / shorter
    logger.info(f"[OCR] Name match: '{name_on_id}' vs '{account_name}' -> {ratio:.2f} (need {threshold})")
    return ratio >= threshold


def _dob_matches_stated_age(dob_str: str, stated_age: int) -> Optional[bool]:
    import datetime
    for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y', '%d/%m/%y', '%d-%m-%y'):
        try:
            dob        = datetime.datetime.strptime(dob_str, fmt).date()
            actual_age = (datetime.date.today() - dob).days // 365
            return abs(actual_age - stated_age) <= 2
        except ValueError:
            continue
    return None


def check_id_reuse(id_number: str, current_user=None) -> dict:
    try:
        from loans.models import LoanApplication
        from accounts.models import UserProfile

        masked_emails = []
        loan_qs       = LoanApplication.objects.filter(id_number=id_number)
        if current_user:
            loan_qs = loan_qs.exclude(user=current_user)

        count      = loan_qs.values('user').distinct().count()
        seen_users = set()
        for app in loan_qs.select_related('user'):
            if app.user_id in seen_users:
                continue
            seen_users.add(app.user_id)
            email  = app.user.email
            parts  = email.split('@')
            masked = (parts[0][0] + '***@' + parts[1]) if len(parts) == 2 else '***'
            masked_emails.append(masked)

        try:
            profile_qs = UserProfile.objects.filter(national_id=id_number)
            if current_user:
                profile_qs = profile_qs.exclude(user=current_user)
            for p in profile_qs.select_related('user'):
                email  = p.user.email
                parts  = email.split('@')
                masked = (parts[0][0] + '***@' + parts[1]) if len(parts) == 2 else '***'
                if masked not in masked_emails:
                    masked_emails.append(masked)
                    count += 1
        except Exception:
            pass

        return {'reused': count > 0, 'count': count, 'masked_emails': masked_emails[:3]}

    except Exception as e:
        logger.error(f"[ID reuse check] Error: {e}")
        return {'reused': False, 'count': 0, 'masked_emails': []}


def verify_id_document(
    image_file,
    submitted_id_number: str,
    account_full_name: str,
    stated_age: int = None,
    existing_loan_qs=None,
    current_user=None,
) -> IDVerificationResult:
    result = IDVerificationResult(passed=False)

    try:
        ocr_text        = extract_text_from_id(image_file)
        result.ocr_text = ocr_text
    except Exception as e:
        result.failures.append(f"OCR engine error: {e}")
        result.warnings.append("Could not read ID document — flagged for manual review.")
        return result

    if not ocr_text or len(ocr_text) < 8:
        result.warnings.append("ID image unreadable — please upload a clearer photo.")
        result.failures.append("OCR returned no usable text")
        return result

    result.extracted_id     = extract_id_number(ocr_text)
    result.extracted_name   = extract_name(ocr_text)
    result.extracted_dob    = extract_dob(ocr_text)
    result.extracted_gender = extract_gender(ocr_text)

    if result.extracted_id:
        submitted_clean        = re.sub(r'\D', '', submitted_id_number.strip())
        extracted_clean        = re.sub(r'\D', '', result.extracted_id)
        result.id_number_match = (submitted_clean == extracted_clean)
        if not result.id_number_match:
            result.failures.append(
                f"ID number mismatch: entered '{submitted_id_number}' "
                f"but document shows '{result.extracted_id}'"
            )
    else:
        result.id_number_match = None
        result.warnings.append("Could not extract ID number — flagged for manual review.")

    if result.extracted_name and account_full_name:
        result.name_match = _names_match(result.extracted_name, account_full_name)
        if not result.name_match:
            result.failures.append(
                f"Name mismatch: document shows '{result.extracted_name}' "
                f"but account name is '{account_full_name}'"
            )
    else:
        result.name_match = None
        result.warnings.append("Could not extract name from document — manual review needed.")

    if result.extracted_dob and stated_age:
        age_ok = _dob_matches_stated_age(result.extracted_dob, stated_age)
        if age_ok is False:
            result.failures.append(
                f"Age mismatch: stated age {stated_age} does not match "
                f"DOB '{result.extracted_dob}' on document"
            )

    id_to_check     = result.extracted_id or re.sub(r'\D', '', submitted_id_number)
    submitted_clean = re.sub(r'\D', '', submitted_id_number.strip())

    if id_to_check:
        reuse_info = check_id_reuse(id_to_check, current_user=current_user)
        if not reuse_info['reused'] and submitted_clean != id_to_check:
            reuse_info = check_id_reuse(submitted_clean, current_user=current_user)
        result.id_reused = reuse_info['reused']
        if result.id_reused:
            masked = ', '.join(reuse_info['masked_emails']) or 'another account'
            result.failures.append(
                f"This ID number is already registered on {masked}. "
                f"Possible duplicate account or fraud attempt."
            )

    if AUTHENTICITY_AVAILABLE:
        try:
            auth = check_id_authenticity(image_file, ocr_text=ocr_text)
            result.authenticity = auth
            if not auth.authentic:
                for f in getattr(auth, 'failures', []):
                    result.failures.append(f"Authenticity: {f}")
                for w in getattr(auth, 'warnings', []):
                    result.warnings.append(f"Document: {w}")
        except Exception as e:
            logger.warning(f"Authenticity check failed: {e}")
            result.warnings.append("Document authenticity check incomplete — manual review.")

    hard_fails = [result.id_number_match is False, result.id_reused]
    soft_fails = [
        result.name_match is False,
        result.id_number_match is None,
        result.name_match is None,
    ]

    result.passed = not any(hard_fails)
    if any(soft_fails) and result.passed:
        result.warnings.append(
            "Some document details could not be fully verified — flagged for manual review."
        )

    return result