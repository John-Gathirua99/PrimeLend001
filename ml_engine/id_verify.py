"""
ml_engine/id_verify.py - Kenyan National ID verification via OCR
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
        raise ImportError("pytesseract not installed.")


def _preprocess(img):
    """Enhanced preprocessing for Kenyan ID photos."""
    import cv2
    import numpy as np
    h, w = img.shape[:2]
    # Upscale to at least 2000px wide
    if w < 2000:
        scale = 2000 / w
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Denoise
    try:
        gray = cv2.fastNlMeansDenoising(gray, h=10)
    except Exception:
        pass
    # CLAHE contrast enhancement
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    # Sharpen instead of threshold — preserves text better
    kernel = __import__('numpy').array([[0,-1,0],[-1,5,-1],[0,-1,0]])
    gray = cv2.filter2D(gray, -1, kernel)
    return gray


def _score_text(text):
    """Score OCR result - higher = more ID-like."""
    score = 0
    keywords = [
        "KENYA", "REPUBLIC", "NATIONAL", "IDENTITY", "MALE", "FEMALE",
        "SURNAME", "GIVEN", "NAMBA", "DATE", "BIRTH", "EXPIRY",
        "MUNICIPALITY", "KITAMBULISHO", "JAMHURI",
    ]
    upper = text.upper()
    for kw in keywords:
        if kw in upper:
            score += 10
    score += len(re.findall(r"\b\d{7,8}\b", text)) * 20
    score += len(re.findall(r"\d{2}[./]\d{2}[./]\d{4}", text)) * 15
    score += min(len(text), 400)
    return score


def _score_text(text):
    """Score OCR text - higher means more ID-like content."""
    score = 0
    keywords = [
        "KENYA", "REPUBLIC", "NATIONAL", "IDENTITY", "MALE", "FEMALE",
        "SURNAME", "GIVEN", "NAMBA", "DATE", "BIRTH", "EXPIRY",
        "MUNICIPALITY", "KITAMBULISHO", "JAMHURI", "MWANGI", "JOHN",
    ]
    upper = text.upper()
    for kw in keywords:
        if kw in upper:
            score += 10
    score += len(re.findall(r"\b\d{7,8}\b", text)) * 20
    score += len(re.findall(r"\d{2}[./]\d{2}[./]\d{4}", text)) * 15
    score += min(len(text), 400)
    return score


def extract_text_from_id(image_file) -> str:
    try:
        import cv2
    except ImportError:
        cv2 = None  # not available in production
    try:
        import numpy as np
    except ImportError:
        np = None
    from PIL import Image as PILImage

    pytesseract = _load_ocr()

    image_file.seek(0)
    img_bytes = image_file.read()
    image_file.seek(0)

    nparr = np.frombuffer(img_bytes, np.uint8)
    orig  = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if orig is None:
        return ""

    # Try all 4 rotations - pick whichever gives best OCR result
    rotations = [
        ("0deg",  orig.copy()),
        ("90cw",  cv2.rotate(orig, cv2.ROTATE_90_CLOCKWISE)),
        ("90ccw", cv2.rotate(orig, cv2.ROTATE_90_COUNTERCLOCKWISE)),
        ("180",   cv2.rotate(orig, cv2.ROTATE_180)),
    ]

    configs = [
        "--psm 6 --oem 3",
        "--psm 4 --oem 3",
        "--psm 11 --oem 3",
    ]

    best_text  = ""
    best_score = -1
    best_label = "none"

    for rot_label, rot_img in rotations:
        try:
            h, w = rot_img.shape[:2]
            if w > 1600:
                rot_img = cv2.resize(rot_img, None, fx=1200/w, fy=1200/w, interpolation=cv2.INTER_AREA)
            elif w < 800:
                rot_img = cv2.resize(rot_img, None, fx=1100/w, fy=1100/w, interpolation=cv2.INTER_CUBIC)

            gray      = cv2.cvtColor(rot_img, cv2.COLOR_BGR2GRAY)
            clahe     = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced  = clahe.apply(gray)
            kernel    = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
            processed = cv2.filter2D(enhanced, -1, kernel)
            pil_img   = PILImage.fromarray(processed)
        except Exception as e:
            logger.warning(f"[OCR] Preprocess failed for {rot_label}: {e}")
            continue

        for config in configs:
            try:
                text  = pytesseract.image_to_string(pil_img, config=config, timeout=25).strip()
                score = _score_text(text)
                logger.info(f"[OCR] {rot_label} {config[:7]} score={score} chars={len(text)}")
                if score > best_score:
                    best_score = score
                    best_text  = text
                    best_label = f"{rot_label}/{config[:7]}"
            except Exception:
                continue

    logger.info(f"[OCR] Winner: {best_label} score={best_score}")
    logger.info(f"[OCR] Text:\n{best_text[:400]}")
    return best_text
def extract_id_number(text: str) -> Optional[str]:
    cleaned = text.upper()

    # Fix common OCR errors only in mostly-digit sequences
    ocr_fixes = {"O": "0", "I": "1", "S": "5", "B": "8", "G": "6", "Z": "2", "Q": "0"}
    def fix_ocr_digits(m):
        s = m.group()
        digit_ratio = sum(1 for ch in s if ch.isdigit()) / len(s)
        if digit_ratio >= 0.5:
            return "".join(ocr_fixes.get(ch, ch) for ch in s)
        return s
    cleaned = re.sub(r"[A-Z0-9]{7,9}", fix_ocr_digits, cleaned)
    cleaned = re.sub(r"I(\d{6,7})", r"1", cleaned)

    patterns = [
        r"(?:ID\s*NAMBA)[\s:\-\.]*(?P<n>\d{7,8})",
        r"(?:NAMBA)[\s:\-\.]*(?P<n>\d{7,8})",
        r"(?:IDENTITY\s*(?:CARD|NO|NUMBER)?[\s:\-\.]*|ID\s*(?:NO|NUMBER|#|CARD)?[\s:\-\.]*)(?P<n>\d{7,8})",
        r"(?:SERIAL\s*(?:NO|NUMBER)?[\s:\-\.]*)(?P<n>\d{7,8})",
        r"(?:NAMBARI\s*(?:YA\s*KITAMBULISHO)?[\s:\-\.]*)(?P<n>\d{7,8})",
        r"(?:NO[\s:\-\.]+)(?P<n>\d{7,8})",
        r"(?:NUMBER[\s:\-\.]+)(?P<n>\d{7,8})",
        r"^\s*(?P<n>\d{7,8})\s*$",
        r"(?P<n>\d{8})",
        r"(?P<n>\d{7})",
        r"(?P<n>\d[\d\s]{5,9}\d)",
    ]

    for pattern in patterns:
        match = re.search(pattern, cleaned, re.IGNORECASE | re.MULTILINE)
        if match:
            candidate = re.sub(r"\s+", "", match.group("n").strip())
            if re.fullmatch(r"[1-9]\d{6,7}", candidate):
                logger.info(f"[OCR] Extracted ID: {candidate}")
                return candidate

    logger.warning("[OCR] Could not extract ID number")
    return None


def _next_line_value(text: str, label: str) -> Optional[str]:
    """
    Kenyan IDs put label on one line, value on next:
      SURNAME -> MWANGI
      GIVEN NAME -> JOHN GATHIRUA
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

    SKIP_WORDS = {
        "REPUBLIC", "KENYA", "JAMHURI", "NATIONAL", "IDENTITY", "CARD",
        "KITAMBULISHO", "TAIFA", "MALE", "FEMALE", "KEN", "SEX", "DATE",
        "BIRTH", "PLACE", "ISSUE", "EXPIRY", "MUNICIPALITY", "NATIONALITY",
        "NAMBA", "MEANT", "PATA", "OF", "CHA", "YA", "NA", "AND", "CEI",
    }
    # Heuristic: find uppercase word(s) between header and MALE/FEMALE line
    lines = [l.strip() for l in text.split("\n")]
    header_idx = -1
    gender_idx = -1
    for i, line in enumerate(lines):
        if "REPUBLIC" in line or "JAMHURI" in line or "NATIONAL IDENTITY" in line:
            header_idx = i
        if re.search(r"\bMALE\b|\bFEMALE\b", line):
            gender_idx = i
            break
    if header_idx >= 0 and gender_idx > header_idx:
        for line in lines[header_idx+1:gender_idx]:
            line = line.strip()
            cleaned = re.sub(r"[^A-Z\s]", "", line.upper()).strip()
            words = cleaned.split()
            if (1 <= len(words) <= 4
                    and all(len(w) >= 2 for w in words)
                    and not any(w in SKIP_WORDS for w in words)
                    and len(cleaned) >= 3):
                logger.info(f"[OCR] Name (between-header-gender): {cleaned}")
                return cleaned
    for line in lines:
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
        r"[\s:\-\.]*(?P<d>\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{2,4})",
        upper, re.IGNORECASE
    )
    if same:
        return same.group("d").strip()

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
    return re.sub(r"\s+", " ", text.upper().strip())


def _names_match(name_on_id: str, account_name: str, threshold: float = 0.55) -> bool:
    id_words   = {w for w in _normalize(name_on_id).split()   if len(w) > 1}
    acct_words = {w for w in _normalize(account_name).split() if len(w) > 1}
    if not id_words or not acct_words:
        return False
    overlap = id_words & acct_words
    shorter = min(len(id_words), len(acct_words))
    ratio   = len(overlap) / shorter
    logger.info(f"[OCR] Name match: {ratio:.2f} (need {threshold})")
    return ratio >= threshold


def _dob_matches_stated_age(dob_str: str, stated_age: int) -> Optional[bool]:
    import datetime
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y"):
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

        count      = loan_qs.values("user").distinct().count()
        seen_users = set()
        for app in loan_qs.select_related("user"):
            if app.user_id in seen_users:
                continue
            seen_users.add(app.user_id)
            email  = app.user.email
            parts  = email.split("@")
            masked = (parts[0][0] + "***@" + parts[1]) if len(parts) == 2 else "***"
            masked_emails.append(masked)

        try:
            profile_qs = UserProfile.objects.filter(national_id=id_number)
            if current_user:
                profile_qs = profile_qs.exclude(user=current_user)
            for p in profile_qs.select_related("user"):
                email  = p.user.email
                parts  = email.split("@")
                masked = (parts[0][0] + "***@" + parts[1]) if len(parts) == 2 else "***"
                if masked not in masked_emails:
                    masked_emails.append(masked)
                    count += 1
        except Exception:
            pass

        return {"reused": count > 0, "count": count, "masked_emails": masked_emails[:3]}

    except Exception as e:
        logger.error(f"[ID reuse check] Error: {e}")
        return {"reused": False, "count": 0, "masked_emails": []}




def extract_fields_with_ai(ocr_text: str, submitted_id: str = "", account_name: str = "") -> dict:
    """
    Use Claude AI to extract ID fields from garbled OCR text.
    Much more robust than regex for poor quality scans.
    """
    try:
        import requests
        prompt = f"""You are analyzing OCR text extracted from a Kenyan National Identity Card.
The OCR may be garbled, have missing characters, or contain noise.

OCR TEXT:
{ocr_text}

The user claims:
- ID Number: {submitted_id}
- Full Name: {account_name}

Extract the following fields from the OCR text. Use context clues and the user's claimed values to help interpret garbled text.
Return ONLY a JSON object with these exact keys:
{{
  "id_number": "8-digit number or null",
  "surname": "surname or null", 
  "given_names": "given names or null",
  "full_name": "full name or null",
  "date_of_birth": "DD.MM.YYYY or null",
  "gender": "MALE or FEMALE or null",
  "place_of_birth": "place or null",
  "confidence": "HIGH or MEDIUM or LOW"
}}

Rules:
- ID number is 7-8 digits, never contains letters
- If OCR shows spaced digits like "4129 2983", join them: "41292983"  
- Fix obvious OCR errors: O->0, I->1 in number sequences
- Return null for fields you cannot determine with reasonable confidence
- Do not guess or hallucinate values not present in the OCR text"""

        from django.conf import settings as _settings
        api_key = getattr(_settings, "ANTHROPIC_API_KEY", "") or os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            logger.warning("[AI OCR] No API key")
            return {}
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"Content-Type": "application/json", "x-api-key": api_key, "anthropic-version": "2023-06-01"},
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 500,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=15
        )
        
        if response.status_code == 200:
            import json, re
            content = response.json()["content"][0]["text"]
            # Extract JSON from response
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                logger.info(f"[AI OCR] Extracted: {result}")
                return result
    except Exception as e:
        logger.warning(f"[AI OCR] Failed: {e}")
    
    return {}


def extract_fields_with_gemini(image_path: str, submitted_id: str = "", account_name: str = "") -> dict:
    """Use Gemini Vision to extract ID fields directly from image."""
    try:
        import requests, base64, json, re
        from django.conf import settings as _s
        api_key = getattr(_s, "GEMINI_API_KEY", "")
        if not api_key:
            return {}

        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        prompt = f"""This is a Kenyan National Identity Card photo.
Extract these fields and return ONLY valid JSON:
{{
  "id_number": "7 or 8 digit number only, no letters",
  "full_name": "full name as shown",
  "date_of_birth": "DD.MM.YYYY format",
  "gender": "MALE or FEMALE",
  "confidence": "HIGH or MEDIUM or LOW"
}}

User claims ID: {submitted_id}, Name: {account_name}
If a field is unclear return null. Never guess."""

        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
                    ]
                }]
            },
            timeout=20
        )

        if response.status_code == 200:
            text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                logger.info(f"[Gemini OCR] {result}")
                return result
        else:
            logger.warning(f"[Gemini OCR] {response.status_code}: {response.text[:100]}")
    except Exception as e:
        logger.warning(f"[Gemini OCR] Failed: {e}")
    return {}


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
        result.warnings.append("Could not read ID document - flagged for manual review.")
        return result

    if not ocr_text or len(ocr_text) < 8:
        result.warnings.append("ID image unreadable - please upload a clearer photo.")
        result.failures.append("OCR returned no usable text")
        return result

    result.extracted_id     = extract_id_number(ocr_text)
    result.extracted_name   = extract_name(ocr_text)
    result.extracted_dob    = extract_dob(ocr_text)
    result.extracted_gender = extract_gender(ocr_text)

    # If regex failed, try Gemini Vision fallback
    if not result.extracted_id or not result.extracted_name:
        logger.info("[OCR] Regex incomplete — trying Gemini Vision")
        try:
            from django.conf import settings as _s
            id_disk_path = os.path.join(__import__('django.conf', fromlist=['settings']).settings.MEDIA_ROOT, str(image_file) if not hasattr(image_file, 'read') else '')
        except Exception:
            id_disk_path = ""
        ai_result = extract_fields_with_gemini(id_disk_path, submitted_id_number, account_full_name) if id_disk_path and os.path.exists(id_disk_path) else {}
        if ai_result:
            if not result.extracted_id and ai_result.get("id_number"):
                result.extracted_id = ai_result["id_number"]
                logger.info(f"[AI OCR] ID: {result.extracted_id}")
            if not result.extracted_name:
                result.extracted_name = (
                    ai_result.get("full_name") or
                    " ".join(filter(None, [ai_result.get("surname"), ai_result.get("given_names")]))
                ) or None
                logger.info(f"[AI OCR] Name: {result.extracted_name}")
            if not result.extracted_dob and ai_result.get("date_of_birth"):
                result.extracted_dob = ai_result["date_of_birth"]
            if not result.extracted_gender and ai_result.get("gender"):
                result.extracted_gender = ai_result["gender"]

    if result.extracted_id:
        submitted_clean        = re.sub(r"\D", "", submitted_id_number.strip())
        extracted_clean        = re.sub(r"\D", "", result.extracted_id)
        result.id_number_match = (submitted_clean == extracted_clean)
        if not result.id_number_match:
            result.failures.append(
                f"ID number mismatch: entered '{submitted_id_number}' "
                f"but document shows '{result.extracted_id}'"
            )
    else:
        result.id_number_match = None
        result.warnings.append("Could not extract ID number - flagged for manual review.")

    if result.extracted_name and account_full_name:
        result.name_match = _names_match(result.extracted_name, account_full_name)
        if not result.name_match:
            result.failures.append(
                f"Name mismatch: document shows '{result.extracted_name}' "
                f"but account name is '{account_full_name}'"
            )
    else:
        result.name_match = None
        result.warnings.append("Could not extract name - manual review needed.")

    if result.extracted_dob and stated_age:
        age_ok = _dob_matches_stated_age(result.extracted_dob, stated_age)
        if age_ok is False:
            result.failures.append(
                f"Age mismatch: stated age {stated_age} does not match "
                f"DOB '{result.extracted_dob}' on document"
            )

    id_to_check     = result.extracted_id or re.sub(r"\D", "", submitted_id_number)
    submitted_clean = re.sub(r"\D", "", submitted_id_number.strip())

    if id_to_check:
        reuse_info = check_id_reuse(id_to_check, current_user=current_user)
        if not reuse_info["reused"] and submitted_clean != id_to_check:
            reuse_info = check_id_reuse(submitted_clean, current_user=current_user)
        result.id_reused = reuse_info["reused"]
        if result.id_reused:
            masked = ", ".join(reuse_info["masked_emails"]) or "another account"
            result.failures.append(
                f"This ID number is already registered on {masked}. "
                f"Possible duplicate account or fraud attempt."
            )

    if AUTHENTICITY_AVAILABLE:
        try:
            auth = check_id_authenticity(image_file, ocr_text=ocr_text)
            result.authenticity = auth
            if not auth.authentic:
                for f in getattr(auth, "failures", []):
                    result.failures.append(f"Authenticity: {f}")
                for w in getattr(auth, "warnings", []):
                    result.warnings.append(f"Document: {w}")
        except Exception as e:
            logger.warning(f"Authenticity check failed: {e}")
            result.warnings.append("Document authenticity check incomplete - manual review.")

    hard_fails = [result.id_number_match is False, result.id_reused]
    soft_fails = [
        result.name_match is False,
        result.id_number_match is None,
        result.name_match is None,
    ]

    result.passed = not any(hard_fails)
    if any(soft_fails) and result.passed:
        result.warnings.append(
            "Some document details could not be fully verified - flagged for manual review."
        )

    return result
